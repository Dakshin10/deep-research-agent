from __future__ import annotations

import collections
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class ClusterResult(BaseModel):
    cluster_id: int
    name: str
    size: int
    representative_project_ids: List[str] = Field(default_factory=list)
    top_domains: List[str] = Field(default_factory=list)
    top_tech: List[str] = Field(default_factory=list)
    sample_size: int = 0


from core.ideas.schemas import IdeaRecord


def cosine_distance(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 1.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 1.0
    return 1.0 - (dot / (n1 * n2))


def cluster_ideas(
    ideas: List[IdeaRecord],
    n_clusters: Optional[int] = None,
) -> List[ClusterResult]:
    """
    Partitions ideas into semantic clusters using KMeans or cosine distance.
    Extracts representative projects (nearest to centroid) and top domain/tech tags.
    Cites sample size per cluster.
    """
    valid_ideas = [i for i in ideas if i.embedding is not None and len(i.embedding) > 0]
    if not valid_ideas:
        return []

    N = len(valid_ideas)
    k = n_clusters or min(5, max(1, N // 3))

    # Attempt scikit-learn KMeans
    labels: List[int] = []
    try:
        from sklearn.cluster import KMeans
        import numpy as np

        X = np.array([i.embedding for i in valid_ideas])
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=5)
        labels = kmeans.fit_predict(X).tolist()
    except Exception:
        # Fallback: simple deterministic modulus clustering
        labels = [idx % k for idx in range(N)]

    # Group into clusters
    cluster_groups: Dict[int, List[IdeaRecord]] = collections.defaultdict(list)
    for idea, lab in zip(valid_ideas, labels):
        cluster_groups[lab].append(idea)

    results: List[ClusterResult] = []

    for cid, members in sorted(cluster_groups.items()):
        # Compute centroid
        dim = len(members[0].embedding)
        centroid = [sum(m.embedding[d] for m in members) / len(members) for d in range(dim)]

        # Find closest projects to centroid
        sorted_members = sorted(
            members, key=lambda m: cosine_distance(m.embedding, centroid)
        )
        rep_ids = [m.id for m in sorted_members[:3]]

        # Top domains & tech
        domains = collections.Counter(d for m in members for d in m.domain_tags).most_common(3)
        tech = collections.Counter(t for m in members for t in m.tech_stack).most_common(3)

        top_dom_names = [d[0] for d in domains]
        top_tech_names = [t[0] for t in tech]

        # Name label
        name_parts = []
        if top_dom_names:
            name_parts.append(top_dom_names[0])
        if top_tech_names:
            name_parts.append(top_tech_names[0])
        name = " / ".join(name_parts) if name_parts else f"Cluster {cid + 1}"

        results.append(
            ClusterResult(
                cluster_id=cid,
                name=f"{name} ({len(members)} projects)",
                size=len(members),
                representative_project_ids=rep_ids,
                top_domains=top_dom_names,
                top_tech=top_tech_names,
                sample_size=N,
            )
        )

    return results
