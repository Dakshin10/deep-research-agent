from __future__ import annotations

import re
from typing import List


class TextChunker:
    """Chunks text into chunks of approx chunk_size tokens with chunk_overlap tokens overlap."""

    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> List[str]:
        if not text or not text.strip():
            return []

        # Split into words/tokens
        words = re.findall(r"\S+|\n", text)
        if len(words) <= self.chunk_size:
            return [text.strip()]

        chunks: List[str] = []
        start = 0
        step = max(1, self.chunk_size - self.chunk_overlap)

        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunk_slice = words[start:end]
            chunk_str = " ".join(chunk_slice).strip()
            # Clean up newline spacing
            chunk_str = re.sub(r" \n ", "\n", chunk_str)
            if chunk_str:
                chunks.append(chunk_str)
            if end >= len(words):
                break
            start += step

        return chunks
