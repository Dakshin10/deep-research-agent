from __future__ import annotations

import math
import re
from typing import List


class EmbeddingModel:
    """Generates normalized vector embeddings of dimension 384 for text."""

    DIMENSION = 384

    def embed_text(self, text: str) -> List[float]:
        # Clean tokens
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return [0.0] * self.DIMENSION

        vector = [0.0] * self.DIMENSION

        # Multi-resolution n-gram hashing for robust semantic matching
        for i, token in enumerate(tokens):
            h = hash(token)
            idx = abs(h) % self.DIMENSION
            vector[idx] += 1.0

            # Subword bi-grams
            if len(token) > 3:
                for j in range(len(token) - 2):
                    sub = token[j : j + 3]
                    h_sub = hash(sub)
                    idx_sub = abs(h_sub) % self.DIMENSION
                    vector[idx_sub] += 0.5

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        return sum(a * b for a, b in zip(v1, v2))
