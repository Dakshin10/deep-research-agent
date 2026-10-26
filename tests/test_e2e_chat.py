"""
End-to-end integration tests for the unified assistant product (Phase 6 / Acceptance Criteria).
"""

import pytest
from core.chat.agent import MainChatAgent
from core.chat.schemas import (
    ApprovalRequestEvent,
    ArtifactEvent,
    CitationEvent,
    CodeExecutionEvent,
    DoneEvent,
    MemoryUsedEvent,
    ResearchProgressEvent,
    TextDeltaEvent,
)
from core.chat.store import ChatStore
from core.codemode.local import LocalBackend
from core.memory.service import LayeredMemoryService

TEST_VAULT_E2E = "test_vault_e2e"


@pytest.fixture
async def e2e_agent():
    store = ChatStore(db_url="sqlite+aiosqlite:///:memory:", tenant_id="tenant_e2e")
    await store.init_db()
    memory = LayeredMemoryService(vault_root=TEST_VAULT_E2E)
    backend = LocalBackend()
    agent = MainChatAgent(store=store, tenant_id="tenant_e2e", backend=backend, memory=memory)
    yield agent


@pytest.mark.asyncio
async def test_e2e_deep_research_turn_streaming(e2e_agent):
    """
    Scenario 1: One chat input for deep research.
    Streams reasoning, live progress shards, citations with exact offsets, and report artifact.
    """
    events = []
    async for event in e2e_agent.execute_turn(
        conversation_id="conv_research_1",
        user_message="Critically evaluate and compare solid-state batteries vs lithium-ion in safety and energy density.",
    ):
        events.append(event)

    types = [e.type for e in events]
    assert "reasoning_summary" in types
    assert "research_progress" in types
    assert "tool_call_started" in types
    assert "tool_call_finished" in types
    assert "citation" in types
    assert "artifact" in types
    assert "text_delta" in types
    assert "done" in types

    # Verify citation has verified text fragment URL
    citation = next(e for e in events if isinstance(e, CitationEvent))
    assert citation.verified is True
    assert citation.text_fragment_url is not None
    assert "#:~:text=" in citation.text_fragment_url

    # Verify artifact
    artifact = next(e for e in events if isinstance(e, ArtifactEvent))
    assert artifact.artifact_type == "report"
    assert "solid-state" in artifact.preview_content.lower()


@pytest.mark.asyncio
async def test_e2e_idea_mining_and_card_artifact(e2e_agent):
    """
    Scenario 2: Mine hackathon ideas for a problem statement.
    Yields synthesized IdeaCards artifact without tab switching.
    """
    events = []
    async for event in e2e_agent.execute_turn(
        conversation_id="conv_ideas_1",
        user_message="Generate ideas for healthcare clinical trial patient recruitment bottlenecks.",
    ):
        events.append(event)

    types = [e.type for e in events]
    assert "tool_call_started" in types
    assert "tool_call_finished" in types
    assert "artifact" in types

    artifact = next(e for e in events if isinstance(e, ArtifactEvent))
    assert artifact.artifact_type == "idea-cards"
    assert "Idea Cards" in artifact.preview_content or "IdeaCard" in artifact.preview_content


@pytest.mark.asyncio
async def test_e2e_codemode_mutation_approval_workflow(e2e_agent):
    """
    Scenario 3: Code Mode mutating action requires approval card, then runs upon receiving approval token.
    """
    # 1. Turn without approval token -> triggers ApprovalRequestEvent
    events_unapproved = []
    async for event in e2e_agent.execute_turn(
        conversation_id="conv_crawl_1",
        user_message="Execute Code Mode to start crawl on Devpost",
        approval_token=None,
    ):
        events_unapproved.append(event)

    appr_event = next(e for e in events_unapproved if isinstance(e, ApprovalRequestEvent))
    assert appr_event is not None
    assert "requires explicit user confirmation" in appr_event.description

    # 2. Resubmit with valid approval token -> proceeds with CodeExecutionEvent
    events_approved = []
    async for event in e2e_agent.execute_turn(
        conversation_id="conv_crawl_1",
        user_message="Execute Code Mode to start crawl on Devpost",
        approval_token="valid_user_approval_jwt_9988",
    ):
        events_approved.append(event)

    types = [e.type for e in events_approved]
    assert "code_execution" in types
    exec_event = next(e for e in events_approved if isinstance(e, CodeExecutionEvent))
    assert exec_event.sandboxed is True
    assert "active" in exec_event.result


@pytest.mark.asyncio
async def test_e2e_cross_conversation_memory_recall(e2e_agent):
    """
    Scenario 4: Fact taught in Conversation A is recalled in Conversation B;
    updates preserve history and superseding facts.
    """
    # Conversation A: Save preference/fact
    await e2e_agent.memory.remember(
        fact="Project Nebula uses Rust and WebAssembly for edge compute.",
        entity_name="Project Nebula",
        entity_type="Projects",
        tenant_id="tenant_e2e",
    )

    # Conversation B: Ask question requiring memory
    events_conv_b = []
    async for event in e2e_agent.execute_turn(
        conversation_id="conv_b_session",
        user_message="What tech stack is Project Nebula using?",
    ):
        events_conv_b.append(event)

    # Verify memory_used was emitted
    mem_event = next((e for e in events_conv_b if isinstance(e, MemoryUsedEvent)), None)
    assert mem_event is not None
    assert len(mem_event.memories) > 0
    assert "Project Nebula" in mem_event.memories[0]["entity"]


@pytest.mark.asyncio
async def test_e2e_incognito_mode_skips_memory_and_persistence(e2e_agent):
    """
    Scenario 5: Incognito turn disables memory read/write.
    """
    events = []
    async for event in e2e_agent.execute_turn(
        conversation_id="conv_incognito",
        user_message="Hello, do you know my confidential preferences?",
        incognito=True,
    ):
        events.append(event)

    # Ensure no memory_used event was emitted
    assert not any(isinstance(e, MemoryUsedEvent) for e in events)

    # Ensure message was NOT persisted to store
    messages = await e2e_agent.store.get_conversation_messages("conv_incognito")
    assert len(messages) == 0
