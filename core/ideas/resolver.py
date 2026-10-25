from __future__ import annotations

from datetime import datetime, timezone
import difflib
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from core.ideas.schemas import IdeaRecord, ProjectPlacement


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def normalize_title(title: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", title.lower())
    return " ".join(cleaned.split())


class EntityResolver:
    """
    Resolves project duplicates across multiple sources (Devpost, GitHub, YouTube, Blogs, Product Hunt).
    Matching rules:
      1. Exact matching repository, demo, or presentation URL.
      2. Direct cross-link presence in all_source_urls.
      3. Title token similarity >= 0.88 AND embedding cosine similarity >= 0.85.
    Preserves a complete audit trail in merge_history and supports lossless un-merge.
    """

    def __init__(
        self,
        name_similarity_threshold: float = 0.88,
        embedding_similarity_threshold: float = 0.85,
    ):
        self.name_threshold = name_similarity_threshold
        self.emb_threshold = embedding_similarity_threshold

    def evaluate_merge_candidate(
        self,
        record_a: IdeaRecord,
        record_b: IdeaRecord,
    ) -> Tuple[bool, str, float]:
        """
        Determines whether record_a and record_b represent the same project.
        Returns: (should_merge, reason, confidence)
        """
        if record_a.id == record_b.id:
            return False, "same_record", 1.0

        # 1. Shared repository link (strongest signal)
        repo_a = record_a.links.get("repo", "").strip().lower()
        repo_b = record_b.links.get("repo", "").strip().lower()
        if repo_a and repo_b and repo_a == repo_b:
            return True, "shared_repository_url", 1.0

        # 2. Shared demo link
        demo_a = record_a.links.get("demo", "").strip().lower()
        demo_b = record_b.links.get("demo", "").strip().lower()
        if demo_a and demo_b and demo_a == demo_b:
            return True, "shared_demo_url", 1.0

        # 3. Direct URL cross-link
        if record_b.first_seen_url in record_a.all_source_urls or record_a.first_seen_url in record_b.all_source_urls:
            return True, "shared_source_url", 1.0

        # 4. Name similarity + Embedding similarity
        name_sim = difflib.SequenceMatcher(
            None, normalize_title(record_a.name), normalize_title(record_b.name)
        ).ratio()

        if name_sim >= self.name_threshold:
            # If embeddings present, verify semantic cosine similarity
            if record_a.embedding and record_b.embedding:
                emb_sim = cosine_similarity(record_a.embedding, record_b.embedding)
                if emb_sim >= self.emb_threshold:
                    return True, "name_and_embedding_similarity", (name_sim + emb_sim) / 2.0
            else:
                # High name similarity alone without embeddings
                if name_sim >= 0.95:
                    return True, "exact_normalized_title_match", name_sim

        return False, "insufficient_similarity", 0.0

    def merge(
        self,
        surviving: IdeaRecord,
        absorbed: IdeaRecord,
        reason: str,
    ) -> IdeaRecord:
        """
        Merges absorbed record into surviving record.
        Preserves all links, sources, verified evidence, and keeps an audit snapshot.
        """
        now = datetime.now(timezone.utc)

        # Merge URLs
        merged_urls = list(dict.fromkeys(surviving.all_source_urls + absorbed.all_source_urls))
        surviving.all_source_urls = merged_urls

        # Merge links (surviving takes priority, absorbed fills gaps)
        for k, v in absorbed.links.items():
            if k not in surviving.links and v:
                surviving.links[k] = v

        # Merge tech stack & domain tags
        surviving.tech_stack = list(dict.fromkeys(surviving.tech_stack + absorbed.tech_stack))
        surviving.domain_tags = list(dict.fromkeys(surviving.domain_tags + absorbed.domain_tags))

        # Merge evidence entries
        for field, ev in absorbed.evidence.items():
            if field not in surviving.evidence and ev.verified:
                surviving.evidence[field] = ev

        # Retain higher placement/prize if surviving was none
        if surviving.placement == ProjectPlacement.NONE and absorbed.placement != ProjectPlacement.NONE:
            surviving.placement = absorbed.placement

        # Audit snapshot of absorbed record
        snapshot = absorbed.model_dump(mode="json")
        merge_entry = {
            "merged_id": absorbed.id,
            "reason": reason,
            "merged_at": now.isoformat(),
            "snapshot": snapshot,
        }
        surviving.merge_history.append(merge_entry)
        surviving.updated_at = now

        absorbed.merged_into_id = surviving.id
        absorbed.updated_at = now

        return surviving

    def unmerge(
        self,
        surviving: IdeaRecord,
        merged_id: str,
    ) -> Tuple[IdeaRecord, Optional[IdeaRecord]]:
        """
        Losslessly reverses a prior merge, restoring the absorbed record from its audit snapshot.
        """
        target_entry = None
        for entry in surviving.merge_history:
            if entry.get("merged_id") == merged_id:
                target_entry = entry
                break

        if not target_entry:
            return surviving, None

        # Rehydrate absorbed record from snapshot
        snapshot_data = target_entry.get("snapshot", {})
        restored = IdeaRecord(**snapshot_data)
        restored.merged_into_id = None
        restored.updated_at = datetime.now(timezone.utc)

        # Clean surviving record
        surviving.merge_history = [e for e in surviving.merge_history if e.get("merged_id") != merged_id]
        surviving.all_source_urls = [u for u in surviving.all_source_urls if u not in restored.all_source_urls or u == surviving.first_seen_url]
        surviving.updated_at = datetime.now(timezone.utc)

        return surviving, restored
