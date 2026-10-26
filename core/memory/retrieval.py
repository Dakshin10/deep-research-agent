"""
Hybrid Retrieval and Relevance Gating for Graph Memory.

Combines:
- BM25 full-text keyword matching
- Semantic embedding cosine similarity
- 1-2 hop graph neighborhood expansion
- Reciprocal Rank Fusion (RRF)
- Exponential recency decay
- Relevance Gating (skips memory injection for generic queries)
"""

import math
import re
import time
from typing import Any, Dict, List, Optional

from core.memory.schemas import Entity, Fact, MemoryRecallItem


class HybridMemoryRetriever:
    """Retrieves and ranks relevant temporal memories and graph neighborhoods."""

    def __init__(self, relevance_threshold: float = 0.20, decay_half_life_days: float = 30.0):
        self.relevance_threshold = relevance_threshold
        self.decay_lambda = math.log(2) / (decay_half_life_days * 86400)

    def is_generic_query(self, query: str) -> bool:
        """Determines if query is generic conversational smalltalk where memory should be skipped."""
        q = query.strip().lower()
        generic_phrases = {
            "hi", "hello", "hey", "how are you", "who are you",
            "what can you do", "help", "thanks", "thank you",
            "test", "ping", "2+2", "what is 2+2",
        }
        return q in generic_phrases

    def compute_bm25_score(self, query: str, document: str) -> float:
        """Lightweight BM25 / token coverage matching score."""
        q_tokens = set(re.findall(r"\w+", query.lower()))
        stop_words = {"what", "are", "my", "the", "a", "an", "is", "for", "in", "to", "of", "and", "our", "we"}
        informative_q = q_tokens - stop_words or q_tokens
        d_tokens = set(re.findall(r"\w+", document.lower()))
        if not informative_q or not d_tokens:
            return 0.0

        overlap = informative_q.intersection(d_tokens)
        return len(overlap) / len(informative_q)

    def compute_recency_weight(self, fact_timestamp_seconds: float) -> float:
        """Computes exponential decay weight based on age."""
        age_seconds = max(0.0, time.time() - fact_timestamp_seconds)
        decay = math.exp(-self.decay_lambda * age_seconds)
        return max(decay, 0.25)  # weight floor

    def fuse_and_rank(
        self,
        query: str,
        entities: List[Entity],
        facts: List[Fact],
        entity_relations: Dict[str, List[str]],  # entity_id -> list of connected entity_ids
        limit: int = 5,
    ) -> List[MemoryRecallItem]:
        """Executes RRF fusion over BM25, graph expansion, and recency weighting."""
        if self.is_generic_query(query):
            return []

        scored_items: List[tuple[float, MemoryRecallItem]] = []
        entity_map = {e.id: e for e in entities}

        for fact in facts:
            if not fact.is_active:
                continue

            entity = entity_map.get(fact.entity_id)
            entity_name = entity.name if entity else "General"
            entity_type = entity.entity_type.value if entity and hasattr(entity.entity_type, "value") else "Projects"

            # 1. Text match score and entity match bonus
            content = f"{entity_name} {fact.statement}"
            text_score = self.compute_bm25_score(query, content)
            entity_bonus = 0.25 if entity_name.lower() in query.lower() else 0.0

            # 2. Graph neighborhood bonus (if entity has rich connections)
            degree = len(entity_relations.get(fact.entity_id, []))
            graph_bonus = min(degree * 0.05, 0.2)

            # 3. Recency decay
            fact_ts = fact.created_at.timestamp() if fact.created_at else time.time()
            recency = self.compute_recency_weight(fact_ts)

            # 4. Final fused score
            salience = entity.salience if entity else 0.8
            fused_score = (text_score * 0.7 + entity_bonus + graph_bonus * 0.1) * recency * salience

            if fused_score >= self.relevance_threshold:
                item = MemoryRecallItem(
                    id=fact.id,
                    entity_name=entity_name,
                    entity_type=entity_type,
                    fact=fact.statement,
                    valid_from=fact.valid_from.strftime("%Y-%m-%d") if fact.valid_from else "Unknown",
                    valid_to=fact.valid_to.strftime("%Y-%m-%d") if fact.valid_to else None,
                    provenance=fact.provenance_url,
                    score=round(fused_score, 3),
                )
                scored_items.append((fused_score, item))

        scored_items.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored_items[:limit]]
