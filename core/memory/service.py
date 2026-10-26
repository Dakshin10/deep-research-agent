"""
Layered Memory Service (L0-L4).

Provides unified MemoryService interface:
- L0 Working memory
- L1 Episodic memory
- L2 Semantic temporal knowledge graph
- L3 Obsidian vault bidirectional sync
- L4 Evidence links
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from core.memory.policy import MemoryPolicyEnforcer
from core.memory.retrieval import HybridMemoryRetriever
from core.memory.schemas import (
    Entity,
    EntityType,
    Fact,
    MemoryGraphSubgraph,
    MemoryRecallItem,
    Relation,
)
from core.memory.vault import VaultManager

logger = logging.getLogger(__name__)


@runtime_checkable
class MemoryService(Protocol):
    """Abstract interface for Memory implementations."""

    async def recall(
        self,
        query: str,
        entity_name: Optional[str] = None,
        limit: int = 5,
        tenant_id: str = "default_tenant",
    ) -> List[MemoryRecallItem]:
        ...

    async def remember(
        self,
        fact: str,
        entity_name: str,
        entity_type: str = "Projects",
        relation: Optional[str] = None,
        target_name: Optional[str] = None,
        provenance_url: Optional[str] = None,
        provenance_location: Optional[str] = None,
        tenant_id: str = "default_tenant",
    ) -> Fact:
        ...

    async def forget(
        self,
        entity_name_or_id: str,
        tenant_id: str = "default_tenant",
    ) -> bool:
        ...

    async def timeline(
        self,
        entity_name: str,
        tenant_id: str = "default_tenant",
    ) -> List[Fact]:
        ...

    async def graph(
        self,
        tenant_id: str = "default_tenant",
        depth: int = 2,
    ) -> MemoryGraphSubgraph:
        ...


class LayeredMemoryService(MemoryService):
    """
    Unified layered memory implementation with temporal validity,
    PII security fencing, and bidirectional Obsidian vault synchronization.
    """

    def __init__(self, vault_root: str = "vault", policy_config_path: str = "config/memory_policy.yaml"):
        self.vault = VaultManager(vault_root=vault_root)
        self.policy = MemoryPolicyEnforcer(config_path=policy_config_path)
        self.retriever = HybridMemoryRetriever()

        # Multi-tenant in-memory graph storage
        # { tenant_id: { entity_id: Entity } }
        self._entities: Dict[str, Dict[str, Entity]] = {}
        # { tenant_id: { entity_name_lower: entity_id } }
        self._entity_names: Dict[str, Dict[str, str]] = {}
        # { tenant_id: [Fact] }
        self._facts: Dict[str, List[Fact]] = {}
        # { tenant_id: [Relation] }
        self._relations: Dict[str, List[Relation]] = {}

    def _get_tenant_maps(self, tenant_id: str):
        if tenant_id not in self._entities:
            self._entities[tenant_id] = {}
            self._entity_names[tenant_id] = {}
            self._facts[tenant_id] = []
            self._relations[tenant_id] = []
        return (
            self._entities[tenant_id],
            self._entity_names[tenant_id],
            self._facts[tenant_id],
            self._relations[tenant_id],
        )

    async def remember(
        self,
        fact: str,
        entity_name: str,
        entity_type: str = "Projects",
        relation: Optional[str] = None,
        target_name: Optional[str] = None,
        provenance_url: Optional[str] = None,
        provenance_location: Optional[str] = None,
        tenant_id: str = "default_tenant",
    ) -> Fact:
        """Commits a fact to L2 temporal graph and writes note to L3 Obsidian vault."""
        # 1. PII and Secret Security Guard
        allowed, reason = self.policy.check_fact(fact)
        if not allowed:
            raise ValueError(f"Security policy rejection: {reason}")

        entities, entity_names, facts, relations = self._get_tenant_maps(tenant_id)
        now = datetime.now(timezone.utc)

        # 2. Resolve or create primary Entity
        clean_name = entity_name.strip()
        name_key = clean_name.lower()
        if name_key in entity_names:
            ent_id = entity_names[name_key]
            entity = entities[ent_id]
            entity.updated_at = now
        else:
            ent_type_val = EntityType.PROJECT
            for t in EntityType:
                if t.value.lower() == entity_type.lower():
                    ent_type_val = t
                    break
            entity = Entity(
                tenant_id=tenant_id,
                name=clean_name,
                entity_type=ent_type_val,
                summary=f"Entity tracked in graph memory for {tenant_id}.",
                created_at=now,
                updated_at=now,
            )
            entities[entity.id] = entity
            entity_names[name_key] = entity.id

        # 3. Contradiction and Temporal Invalidation Handling
        # If an active fact for this entity covers the same topic, supersede it
        for f in facts:
            if f.entity_id == entity.id and f.is_active:
                # Contradiction heuristic: matching key terms or prefix
                words_old = set(f.statement.lower().split()[:3])
                words_new = set(fact.lower().split()[:3])
                if words_old and words_new and len(words_old.intersection(words_new)) >= 2:
                    f.is_active = False
                    f.valid_to = now

        # 4. Create and store new Fact
        new_fact = Fact(
            tenant_id=tenant_id,
            entity_id=entity.id,
            statement=fact,
            valid_from=now,
            valid_to=None,
            is_active=True,
            provenance_url=provenance_url,
            provenance_location=provenance_location,
            created_at=now,
        )
        facts.append(new_fact)

        # 5. Resolve Relation if specified
        connected_relations = []
        if relation and target_name:
            t_clean = target_name.strip()
            t_key = t_clean.lower()
            if t_key in entity_names:
                target_ent = entities[entity_names[t_key]]
            else:
                target_ent = Entity(
                    tenant_id=tenant_id,
                    name=t_clean,
                    entity_type=EntityType.TOOL,
                    summary=f"Related tool/target for {clean_name}.",
                    created_at=now,
                    updated_at=now,
                )
                entities[target_ent.id] = target_ent
                entity_names[t_key] = target_ent.id

            rel = Relation(
                tenant_id=tenant_id,
                source_id=entity.id,
                target_id=target_ent.id,
                relation_type=relation.upper(),
                valid_from=now,
                is_active=True,
            )
            relations.append(rel)
            connected_relations.append({"relation": rel.relation_type, "target": target_ent.name})

        # 6. Synchronize to Obsidian Markdown Vault
        entity_facts = [f for f in facts if f.entity_id == entity.id]
        self.vault.write_entity_note(
            entity=entity,
            facts=entity_facts,
            relations=connected_relations,
        )

        return new_fact

    async def recall(
        self,
        query: str,
        entity_name: Optional[str] = None,
        limit: int = 5,
        tenant_id: str = "default_tenant",
    ) -> List[MemoryRecallItem]:
        """Hybrid search across entities, facts, and graph relations."""
        entities, entity_names, facts, relations = self._get_tenant_maps(tenant_id)

        # Build entity connection adjacency list
        adjacency: Dict[str, List[str]] = {}
        for r in relations:
            adjacency.setdefault(r.source_id, []).append(r.target_id)
            adjacency.setdefault(r.target_id, []).append(r.source_id)

        target_entities = list(entities.values())
        if entity_name:
            key = entity_name.strip().lower()
            if key in entity_names:
                target_id = entity_names[key]
                target_entities = [entities[target_id]]

        return self.retriever.fuse_and_rank(
            query=query,
            entities=target_entities,
            facts=facts,
            entity_relations=adjacency,
            limit=limit,
        )

    async def timeline(
        self,
        entity_name: str,
        tenant_id: str = "default_tenant",
    ) -> List[Fact]:
        """Returns chronological history of all facts (active and superseded)."""
        entities, entity_names, facts, _ = self._get_tenant_maps(tenant_id)
        key = entity_name.strip().lower()
        if key not in entity_names:
            return []

        ent_id = entity_names[key]
        entity_facts = [f for f in facts if f.entity_id == ent_id]
        entity_facts.sort(key=lambda f: f.valid_from)
        return entity_facts

    async def forget(
        self,
        entity_name_or_id: str,
        tenant_id: str = "default_tenant",
    ) -> bool:
        """Hard delete from graph, facts list, and Obsidian vault."""
        entities, entity_names, facts, relations = self._get_tenant_maps(tenant_id)

        key = entity_name_or_id.strip().lower()
        ent_id = None
        entity_obj = None

        if entity_name_or_id in entities:
            ent_id = entity_name_or_id
            entity_obj = entities[ent_id]
        elif key in entity_names:
            ent_id = entity_names[key]
            entity_obj = entities[ent_id]

        if not ent_id or not entity_obj:
            return False

        # 1. Remove from graph maps
        del entities[ent_id]
        if key in entity_names:
            del entity_names[key]

        # 2. Remove facts
        self._facts[tenant_id] = [f for f in facts if f.entity_id != ent_id]

        # 3. Remove relations
        self._relations[tenant_id] = [
            r for r in relations if r.source_id != ent_id and r.target_id != ent_id
        ]

        # 4. Remove from Obsidian markdown vault
        folder = entity_obj.entity_type.value if hasattr(entity_obj.entity_type, "value") else str(entity_obj.entity_type)
        self.vault.delete_entity_note(entity_obj.name, folder)

        return True

    async def graph(
        self,
        tenant_id: str = "default_tenant",
        depth: int = 2,
    ) -> MemoryGraphSubgraph:
        """Returns nodes and edges formatted for interactive UI rendering."""
        entities, _, facts, relations = self._get_tenant_maps(tenant_id)

        nodes = []
        for ent in entities.values():
            folder = ent.entity_type.value if hasattr(ent.entity_type, "value") else "Projects"
            nodes.append({
                "id": ent.id,
                "name": ent.name,
                "type": folder,
                "summary": ent.summary,
                "salience": ent.salience,
                "valid_from": ent.created_at.strftime("%Y-%m-%d"),
            })

        edges = []
        for rel in relations:
            edges.append({
                "source": rel.source_id,
                "target": rel.target_id,
                "relation": rel.relation_type,
            })

        return MemoryGraphSubgraph(nodes=nodes, edges=edges)
