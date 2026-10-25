from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Union


class DocumentParser:
    """Parses PDF, DOCX, Markdown, Text, CSV, and JSON into clean text."""

    @classmethod
    def parse_bytes(cls, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix.lower()

        if suffix == ".pdf":
            return cls._parse_pdf(content)
        elif suffix in [".docx", ".doc"]:
            return cls._parse_docx(content)
        elif suffix in [".json"]:
            return cls._parse_json(content)
        else:
            # Fallback text/markdown/csv
            return cls._parse_text(content)

    @classmethod
    def _parse_pdf(cls, content: bytes) -> str:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages).strip()
        except Exception:
            # Fallback simple string extraction
            return content.decode("utf-8", errors="ignore").strip()

    @classmethod
    def _parse_docx(cls, content: bytes) -> str:
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs).strip()
        except Exception:
            return content.decode("utf-8", errors="ignore").strip()

    @classmethod
    def _parse_json(cls, content: bytes) -> str:
        try:
            data = json.loads(content.decode("utf-8", errors="ignore"))
            return json.dumps(data, indent=2)
        except Exception:
            return content.decode("utf-8", errors="ignore").strip()

    @classmethod
    def _parse_text(cls, content: bytes) -> str:
        try:
            return content.decode("utf-8").strip()
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="ignore").strip()
