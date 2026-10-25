from __future__ import annotations

import io
import re
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup

from core.fetch.base import DocumentPage, DocumentSection, DocumentTimestamp

try:
    import pymupdf  # PyMuPDF
    _PYMUPDF_AVAILABLE = True
except ImportError:
    try:
        import fitz
        _PYMUPDF_AVAILABLE = True
    except ImportError:
        _PYMUPDF_AVAILABLE = False

try:
    import trafilatura
    _TRAFILATURA_AVAILABLE = True
except ImportError:
    _TRAFILATURA_AVAILABLE = False

try:
    import docx
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False


def extract_from_html(html_text: str, url: str = "") -> Tuple[str, str, List[DocumentSection]]:
    """
    Extract title, linearized plain text, and hierarchical sections with character offsets from HTML.
    Uses trafilatura when available for article filtering, and BeautifulSoup for precise heading trees.
    """
    if not html_text or not html_text.strip():
        return "", "", []

    soup = BeautifulSoup(html_text, "html.parser")

    # Extract title
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "svg"]):
        tag.decompose()

    # If trafilatura is available, use it to get clean content text as well
    clean_article_text = ""
    if _TRAFILATURA_AVAILABLE:
        try:
            extracted = trafilatura.extract(
                html_text,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            if extracted:
                clean_article_text = extracted.strip()
        except Exception:
            pass

    # Build hierarchical sections and linearized text with exact char offsets
    sections: List[DocumentSection] = []
    heading_stack: List[Tuple[int, str]] = []  # (level, text)
    linearized_parts: List[str] = []
    current_char = 0

    current_section_path: List[str] = []
    current_section_text: List[str] = []
    section_start_char = 0

    body = soup.body or soup
    # Traverse top-level content blocks
    for elem in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "td", "th"]):
        tag_name = elem.name.lower()
        text_content = elem.get_text(" ", strip=True)
        if not text_content:
            continue

        if tag_name.startswith("h") and len(tag_name) == 2 and tag_name[1].isdigit():
            level = int(tag_name[1])
            # Save previous section if it had content
            if current_section_text:
                full_sec_text = "\n".join(current_section_text).strip()
                if full_sec_text:
                    sections.append(
                        DocumentSection(
                            heading_path=list(current_section_path),
                            char_start=section_start_char,
                            char_end=current_char,
                            text=full_sec_text,
                        )
                    )
                current_section_text = []

            # Update heading stack
            heading_stack = [h for h in heading_stack if h[0] < level]
            heading_stack.append((level, text_content))
            current_section_path = [h[1] for h in heading_stack]

            # Add heading line to linearized text
            line = f"### {text_content}\n" if not linearized_parts else f"\n### {text_content}\n"
            linearized_parts.append(line)
            current_char += len(line)
            section_start_char = current_char
        else:
            line = text_content + "\n"
            linearized_parts.append(line)
            current_section_text.append(text_content)
            current_char += len(line)

    # Flush final section
    if current_section_text:
        full_sec_text = "\n".join(current_section_text).strip()
        if full_sec_text:
            sections.append(
                DocumentSection(
                    heading_path=list(current_section_path),
                    char_start=section_start_char,
                    char_end=current_char,
                    text=full_sec_text,
                )
            )

    linearized_text = "".join(linearized_parts)
    if not linearized_text and clean_article_text:
        linearized_text = clean_article_text
        sections = [DocumentSection(heading_path=[], char_start=0, char_end=len(clean_article_text), text=clean_article_text)]

    return title, linearized_text, sections


def extract_from_pdf(pdf_bytes: bytes) -> Tuple[str, List[DocumentPage], List[DocumentSection]]:
    """
    Extract title, pages with 1-indexed numbers and character spans, and sections from PDF bytes.
    Uses PyMuPDF (fitz) with fallback to pypdf.
    """
    pages: List[DocumentPage] = []
    sections: List[DocumentSection] = []
    linearized_parts: List[str] = []
    title = ""
    current_char = 0

    if _PYMUPDF_AVAILABLE:
        try:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            if doc.metadata and doc.metadata.get("title"):
                title = doc.metadata["title"]

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_text = page.get_text().strip()
                page_start = current_char

                if page_text:
                    line = f"[Page {page_idx + 1}]\n{page_text}\n\n"
                    linearized_parts.append(line)
                    current_char += len(line)

                pages.append(
                    DocumentPage(
                        page_no=page_idx + 1,
                        char_start=page_start,
                        char_end=current_char,
                        text=page_text,
                    )
                )

                # Page-level section
                sections.append(
                    DocumentSection(
                        heading_path=[f"Page {page_idx + 1}"],
                        char_start=page_start,
                        char_end=current_char,
                        text=page_text,
                    )
                )
            doc.close()
            return title, pages, sections
        except Exception:
            pass

    # Fallback to pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title

        for page_idx, page in enumerate(reader.pages):
            page_text = (page.extract_text() or "").strip()
            page_start = current_char

            if page_text:
                line = f"[Page {page_idx + 1}]\n{page_text}\n\n"
                linearized_parts.append(line)
                current_char += len(line)

            pages.append(
                DocumentPage(
                    page_no=page_idx + 1,
                    char_start=page_start,
                    char_end=current_char,
                    text=page_text,
                )
            )
            sections.append(
                DocumentSection(
                    heading_path=[f"Page {page_idx + 1}"],
                    char_start=page_start,
                    char_end=current_char,
                    text=page_text,
                )
            )
    except Exception:
        pass

    return title, pages, sections


def extract_from_docx(docx_bytes: bytes) -> Tuple[str, List[DocumentSection]]:
    """Extract document title and hierarchical sections from DOCX bytes."""
    sections: List[DocumentSection] = []
    title = ""
    if not _DOCX_AVAILABLE:
        return title, sections

    try:
        doc = docx.Document(io.BytesIO(docx_bytes))
        current_char = 0
        heading_stack: List[Tuple[int, str]] = []
        current_path: List[str] = []
        current_sec_text: List[str] = []
        sec_start = 0

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue

            style_name = p.style.name if p.style else ""
            if "Heading 1" in style_name:
                level = 1
            elif "Heading 2" in style_name:
                level = 2
            elif "Heading 3" in style_name:
                level = 3
            elif "Title" in style_name:
                title = text
                level = 0
            else:
                level = None

            if level is not None:
                if current_sec_text:
                    full_txt = "\n".join(current_sec_text).strip()
                    if full_txt:
                        sections.append(
                            DocumentSection(
                                heading_path=list(current_path),
                                char_start=sec_start,
                                char_end=current_char,
                                text=full_txt,
                            )
                        )
                    current_sec_text = []

                heading_stack = [h for h in heading_stack if h[0] < level]
                heading_stack.append((level, text))
                current_path = [h[1] for h in heading_stack]
                sec_start = current_char
            else:
                current_sec_text.append(text)

            current_char += len(text) + 1

        if current_sec_text:
            full_txt = "\n".join(current_sec_text).strip()
            if full_txt:
                sections.append(
                    DocumentSection(
                        heading_path=list(current_path),
                        char_start=sec_start,
                        char_end=current_char,
                        text=full_txt,
                    )
                )
    except Exception:
        pass

    return title, sections


def extract_from_text(plain_text: str) -> Tuple[str, List[DocumentSection]]:
    """Extract title and sections from plain text or markdown."""
    lines = plain_text.splitlines()
    sections: List[DocumentSection] = []
    title = ""
    current_char = 0
    current_sec_path: List[str] = []
    current_sec_lines: List[str] = []
    sec_start = 0

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in lines:
        match = heading_pattern.match(line)
        if match:
            if current_sec_lines:
                sec_text = "\n".join(current_sec_lines).strip()
                if sec_text:
                    sections.append(
                        DocumentSection(
                            heading_path=list(current_sec_path),
                            char_start=sec_start,
                            char_end=current_char,
                            text=sec_text,
                        )
                    )
                current_sec_lines = []

            level = len(match.group(1))
            h_text = match.group(2).strip()
            if not title:
                title = h_text

            current_sec_path = [h_text]
            sec_start = current_char
        else:
            current_sec_lines.append(line)

        current_char += len(line) + 1

    if current_sec_lines:
        sec_text = "\n".join(current_sec_lines).strip()
        if sec_text:
            sections.append(
                DocumentSection(
                    heading_path=list(current_sec_path),
                    char_start=sec_start,
                    char_end=current_char,
                    text=sec_text,
                )
            )

    return title, sections
