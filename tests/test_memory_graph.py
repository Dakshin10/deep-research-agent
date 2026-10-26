"""
Unit and integration tests for Layered Graph Memory, Obsidian Vault, and PII Policy.
"""

import os
import shutil
import pytest
from core.memory.service import LayeredMemoryService

TEST_VAULT_DIR = "test_vault_tmp"


@pytest.fixture
def memory_service():
    if os.path.exists(TEST_VAULT_DIR):
        shutil.rmtree(TEST_VAULT_DIR)
    service = LayeredMemoryService(vault_root=TEST_VAULT_DIR)
    yield service
    if os.path.exists(TEST_VAULT_DIR):
        shutil.rmtree(TEST_VAULT_DIR)


@pytest.mark.asyncio
async def test_temporal_facts_and_contradiction_invalidation(memory_service):
    # 1. Record initial fact
    fact1 = await memory_service.remember(
        fact="Uses PostgreSQL for vector search embeddings.",
        entity_name="Search Infrastructure",
        entity_type="Projects",
        tenant_id="tenant_1",
    )
    assert fact1.is_active is True
    assert fact1.valid_to is None

    # 2. Record superseding fact (contradiction)
    fact2 = await memory_service.remember(
        fact="Uses PostgreSQL and FalkorDB graph index for hybrid search.",
        entity_name="Search Infrastructure",
        entity_type="Projects",
        tenant_id="tenant_1",
    )
    assert fact2.is_active is True

    # 3. Verify history preserved in timeline
    history = await memory_service.timeline("Search Infrastructure", tenant_id="tenant_1")
    assert len(history) == 2
    # Old fact should now be marked inactive with valid_to set
    assert history[0].is_active is False
    assert history[0].valid_to is not None
    # New fact is active
    assert history[1].is_active is True


@pytest.mark.asyncio
async def test_pii_fence_rejection(memory_service):
    # Test credentials / secret rejection
    with pytest.raises(ValueError) as exc1:
        await memory_service.remember(
            fact="Admin API key is api_key=sk-1234567890abcdef1234567890abcdef",
            entity_name="Config",
            tenant_id="tenant_1",
        )
    assert "Security policy rejection" in str(exc1.value)

    # Test credit card rejection
    with pytest.raises(ValueError) as exc2:
        await memory_service.remember(
            fact="User card number is 4111 2222 3333 4444",
            entity_name="Billing",
            tenant_id="tenant_1",
        )
    assert "Security policy rejection" in str(exc2.value)


@pytest.mark.asyncio
async def test_obsidian_vault_sync(memory_service):
    await memory_service.remember(
        fact="Orchestrates multi-shard web crawlers across Devpost and Devfolio.",
        entity_name="Idea Miner",
        entity_type="Projects",
        relation="USES_TOOL",
        target_name="SearXNG",
        tenant_id="tenant_1",
    )

    note_path = memory_service.vault.get_note_path("Idea Miner", "Projects")
    assert os.path.exists(note_path)

    parsed = memory_service.vault.parse_note(note_path)
    assert parsed is not None
    assert parsed["frontmatter"]["name"] == "Idea Miner"
    assert "SearXNG" in parsed["wikilinks"]


@pytest.mark.asyncio
async def test_hard_forget_removes_everywhere(memory_service):
    await memory_service.remember(
        fact="Candidate hackathon idea for autonomous clinical trials.",
        entity_name="Clinical Trial Bot",
        entity_type="Ideas",
        tenant_id="tenant_1",
    )

    # Verify exists
    recalls = await memory_service.recall("clinical trials", tenant_id="tenant_1")
    assert len(recalls) > 0
    note_path = memory_service.vault.get_note_path("Clinical Trial Bot", "Ideas")
    assert os.path.exists(note_path)

    # Execute hard forget
    forgotten = await memory_service.forget("Clinical Trial Bot", tenant_id="tenant_1")
    assert forgotten is True

    # Verify gone from recall and vault file deleted
    post_recalls = await memory_service.recall("clinical trials", tenant_id="tenant_1")
    assert len(post_recalls) == 0
    assert not os.path.exists(note_path)


@pytest.mark.asyncio
async def test_multi_tenant_isolation_leakage(memory_service):
    # Tenant A records proprietary knowledge
    await memory_service.remember(
        fact="Project Stealth uses confidential gallium nitride semiconductor patents.",
        entity_name="Project Stealth",
        tenant_id="tenant_alpha",
    )

    # Tenant B attempts to recall
    leaked = await memory_service.recall("gallium nitride semiconductor", tenant_id="tenant_beta")
    assert len(leaked) == 0

    # Tenant A recalls successfully
    recalled = await memory_service.recall("gallium nitride semiconductor", tenant_id="tenant_alpha")
    assert len(recalled) > 0
    assert "gallium nitride" in recalled[0].fact


@pytest.mark.asyncio
async def test_relevance_gating_skips_generic_queries(memory_service):
    await memory_service.remember(
        fact="Prefers concise bulleted answers in dark mode.",
        entity_name="User Preferences",
        entity_type="Preferences",
        tenant_id="tenant_1",
    )

    # Generic query -> should be gated out
    assert await memory_service.recall("hello", tenant_id="tenant_1") == []
    assert await memory_service.recall("2+2", tenant_id="tenant_1") == []

    # Specific preference query -> should be retrieved
    recalled = await memory_service.recall("what are my user preferences", tenant_id="tenant_1")
    assert len(recalled) > 0
    assert "bulleted answers" in recalled[0].fact
