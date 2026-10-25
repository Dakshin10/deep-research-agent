from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

try:
    from sentence_transformers import CrossEncoder
    _CROSS_ENCODER_AVAILABLE = True
except ImportError:
    _CROSS_ENCODER_AVAILABLE = False


class PassageReranker:
    """
    Reranks candidate document passages against the target query before claim extraction.
    Supports sentence-transformers cross-encoders (e.g. bge-reranker-base) with a fast,
    CPU-friendly BM25 / token cross-scoring fallback.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name
        self._cross_encoder = None
        if _CROSS_ENCODER_AVAILABLE and model_name:
            try:
                self._cross_encoder = CrossEncoder(model_name)
            except Exception:
                self._cross_encoder = None

    def rerank(self, query: str, passages: List[str], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Rerank a list of candidate passages against a query.
        Returns top_k tuples of (passage_text, score) sorted descending by score.
        """
        if not passages:
            return []

        # 1. Neural Cross-Encoder path if loaded
        if self._cross_encoder:
            try:
                pairs = [[query, p] for p in passages]
                scores = self._cross_encoder.predict(pairs)
                ranked = sorted(zip(passages, [float(s) for s in scores]), key=lambda x: x[1], reverse=True)
                return ranked[:top_k]
            except Exception:
                pass

        # 2. Fast CPU BM25 / Lexical Cross-Scorer Fallback
        return self._bm25_cross_rank(query, passages, top_k=top_k)

    def _bm25_cross_rank(self, query: str, passages: List[str], top_k: int = 5) -> List[Tuple[str, float]]:
        """Lightweight BM25 score implementation for CPU cross-scoring."""
        query_tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        if not query_tokens:
            return [(p, 0.5) for p in passages[:top_k]]

        # Tokenize passages
        tokenized_passages = [
            [t.lower() for t in re.findall(r"\w+", p)] for p in passages
        ]
        avg_doc_len = sum(len(tp) for tp in tokenized_passages) / max(1, len(tokenized_passages))

        # Doc frequencies for IDF
        num_docs = len(passages)
        idf = {}
        for q in set(query_tokens):
            count = sum(1 for tp in tokenized_passages if q in tp)
            idf[q] = math.log(1.0 + (num_docs - count + 0.5) / (count + 0.5))

        k1 = 1.2
        b = 0.75
        scores: List[Tuple[str, float]] = []

        for p_idx, tp in enumerate(tokenized_passages):
            doc_len = len(tp)
            tf_score = 0.0
            term_freqs = {}
            for t in tp:
                term_freqs[t] = term_freqs.get(t, 0) + 1

            for q in query_tokens:
                freq = term_freqs.get(q, 0)
                if freq > 0:
                    numerator = freq * (k1 + 1.0)
                    denominator = freq + k1 * (1.0 - b + b * (doc_len / max(1.0, avg_doc_len)))
                    tf_score += idf.get(q, 0.5) * (numerator / max(0.1, denominator))

            # Normalize to 0.0 - 1.0 range
            norm_score = 1.0 / (1.0 + math.exp(-tf_score / 5.0))
            scores.append((passages[p_idx], norm_score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]
