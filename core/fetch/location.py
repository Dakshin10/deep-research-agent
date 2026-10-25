from __future__ import annotations

import difflib
import re
import unicodedata
from typing import List, Optional, Tuple
import urllib.parse

from core.fetch.base import FetchedDocument


def normalize_for_matching(text: str) -> str:
    """Normalize text using NFKC and collapse whitespace for resilient matching."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    # Collapse whitespace
    return re.sub(r"\s+", " ", normalized).strip()


def generate_text_fragment_url(base_url: str, excerpt: str) -> str:
    """
    Generate a W3C / Chrome Scroll-to-Text Fragment URL:
    https://example.com/page#:~:text=[textStart][,textEnd]
    """
    if not base_url or not excerpt:
        return base_url

    # Strip existing fragment if present
    parsed = urllib.parse.urlsplit(base_url)
    clean_base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))

    words = re.findall(r"\S+", excerpt.strip())
    if not words:
        return base_url

    if len(words) <= 5:
        # Short excerpt: encode entire phrase
        encoded_text = urllib.parse.quote(" ".join(words))
        fragment = f"#:~:text={encoded_text}"
    else:
        # Longer excerpt: use start and end text boundaries
        start_phrase = " ".join(words[:4])
        end_phrase = " ".join(words[-4:])
        encoded_start = urllib.parse.quote(start_phrase)
        encoded_end = urllib.parse.quote(end_phrase)
        fragment = f"#:~:text={encoded_start},{encoded_end}"

    return f"{clean_base}{fragment}"


def verify_excerpt_in_document(
    excerpt: str,
    doc: FetchedDocument,
    similarity_threshold: float = 0.90,
) -> Tuple[bool, Optional[int], Optional[int], Optional[int], List[str], str]:
    """
    HARD RULE Verification:
    Verifies that the verbatim excerpt exists in the fetched document.
    1. Tests exact substring match in doc.raw_text.
    2. If not found, tests normalized whitespace/Unicode fuzzy match with threshold >= 0.90.
    3. Resolves char_start, char_end, page_no (if PDF), heading_path (if sections exist),
       and generates a clickable text-fragment URL.
    4. If unverified, returns (False, None, None, None, [], "").
    """
    if not excerpt or not doc or not doc.raw_text:
        return False, None, None, None, [], ""

    clean_excerpt = excerpt.strip()
    raw_text = doc.raw_text

    char_start: Optional[int] = None
    char_end: Optional[int] = None
    is_verified = False

    # 1. Exact Substring Match
    idx = raw_text.find(clean_excerpt)
    if idx != -1:
        char_start = idx
        char_end = idx + len(clean_excerpt)
        is_verified = True
    else:
        # 2. Normalized Fuzzy Match
        norm_excerpt = normalize_for_matching(clean_excerpt)
        norm_raw = normalize_for_matching(raw_text)

        norm_idx = norm_raw.find(norm_excerpt)
        if norm_idx != -1:
            # Found in normalized text
            ratio = 1.0
            is_verified = True
        else:
            # Sliding window similarity over candidate slices
            excerpt_len = len(norm_excerpt)
            step = max(1, excerpt_len // 4)
            best_ratio = 0.0
            best_start = -1

            for start_pos in range(0, max(1, len(norm_raw) - excerpt_len + 1), step):
                window = norm_raw[start_pos : start_pos + excerpt_len]
                sm = difflib.SequenceMatcher(None, norm_excerpt, window)
                r = sm.ratio()
                if r > best_ratio:
                    best_ratio = r
                    best_start = start_pos
                    if r >= 0.98:
                        break

            if best_ratio >= similarity_threshold and best_start != -1:
                is_verified = True
                norm_idx = best_start
            else:
                is_verified = False

        if is_verified and norm_idx is not None and norm_idx >= 0:
            # Estimate character positions in original raw_text
            # Scan original text counting normalized characters
            orig_pos = 0
            norm_count = 0
            while orig_pos < len(raw_text) and norm_count < norm_idx:
                if not raw_text[orig_pos].isspace() or (orig_pos > 0 and not raw_text[orig_pos - 1].isspace()):
                    norm_count += 1
                orig_pos += 1
            char_start = orig_pos

            norm_end_count = norm_idx + len(norm_excerpt)
            while orig_pos < len(raw_text) and norm_count < norm_end_count:
                if not raw_text[orig_pos].isspace() or (orig_pos > 0 and not raw_text[orig_pos - 1].isspace()):
                    norm_count += 1
                orig_pos += 1
            char_end = min(len(raw_text), orig_pos)

    if not is_verified or char_start is None:
        return False, None, None, None, [], ""

    # 3. Determine PDF page number if pages are present
    page_no: Optional[int] = None
    if doc.pages:
        for p in doc.pages:
            if p.char_start <= char_start < p.char_end:
                page_no = p.page_no
                break
        if page_no is None and doc.pages:
            # Closest page
            closest = min(doc.pages, key=lambda p: abs(p.char_start - char_start))
            page_no = closest.page_no

    # 4. Determine heading path if sections are present
    heading_path: List[str] = []
    if doc.sections:
        for s in doc.sections:
            if s.char_start <= char_start < s.char_end:
                heading_path = list(s.heading_path)
                break
        if not heading_path and doc.sections:
            # Pick latest preceding section
            preceding = [s for s in doc.sections if s.char_start <= char_start]
            if preceding:
                heading_path = list(preceding[-1].heading_path)

    # 5. Generate Text Fragment URL
    fragment_url = generate_text_fragment_url(doc.final_url or doc.url, clean_excerpt)

    return True, char_start, char_end, page_no, heading_path, fragment_url
