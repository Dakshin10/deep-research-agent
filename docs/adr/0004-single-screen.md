# ADR 0004: Single-Screen, Type-Only Assistant Architecture

**Status**: Accepted  
**Date**: 2026-10-27  
**Author**: Principal Product Engineer & Designer  
**Scope**: `apps/web`, `core/chat/`, `docs/chat-protocol.md`, `config/autonomy.yaml`

---

## 1. Context & Motivation

In previous iterations of `deep-research-agent`, user interactions were fragmented across:
1. Multi-tab tools (Streamlit/Gradio with Deep Research, Crawl Monitor, Idea Explorer, Trends, Idea Generator).
2. Separate web routes (`/`, `/memory`).
3. Explicit mode/tool selection and manual model dropdowns (`fast`, `strong`, `code`).
4. Loud visual chrome (stat badges, version counters, permanent sidebars, and always-visible complex shard panels).

This forced cognitive load onto the user: *“Should I be in research mode or idea mode? Which model is best? Where do I go to see memory?”*

Claude and modern ambient assistants demonstrated that users want **one conversation surface**: you type anything—from a mental math question to a multi-stage research paper or hackathon idea generation—and the agent decides the path, executes silently, streams clean prose, and progressively discloses details on demand.

---

## 2. Decision

We establish the **Single-Screen Type-Only Assistant** pattern (branded as **Aether**):
- **Single URL (`/`)**: Exactly one page route in `apps/web`. No separate pages for memory or settings.
- **Overlay Navigation**: All secondary surfaces (Artifact Drawer, Sources Sheet, Memory Graph Canvas, Settings Modal, History Drawer) are rendered as overlays on `/`, with their state synchronized to query parameters (e.g., `?overlay=memory`, `?overlay=artifact&id=art_123`) for shareability and browser back-button support without page reloads.
- **Agent Decides Everything**: All mode concepts, tool pickers, and model selector dropdowns are removed from the primary UI. Model selection is handled automatically by the intent router in `core/chat/` mapping to `config/models.yaml` (`fast`, `strong`, `code`).
- **Quiet Progressive Disclosure**: Heavy work (shards, code execution, budget) is collapsed into a single animated shimmer status line (e.g., *"Searching 14 sources..."*), expanding only when clicked, and collapsing to a 1-line recap upon completion.
- **Natural Language UI Control (`ui_action`)**: Frontend actions (`open_memory_graph`, `set_private_mode`, `export_vault`, `open_settings`) can be triggered directly by typing into the composer (e.g., *"show my memory graph"* or *"go private"*).

---

## 3. What We Are Removing, Merging, and Adding

### A. What We Are Removing
1. **Separate Pages**: Remove the `/memory` page route. All memory inspection, force graph visualization, and vault controls become a full-screen overlay component rendered on `/`.
2. **Model Dropdown in Primary UI**: Remove the `<select>` dropdown from the chat sidebar and composer. The model is assigned per turn and disclosed only within the expanded details accordion.
3. **Tool Toggles & Mode Tabs**: Remove any manual switches for Deep Research vs. Idea Miner vs. Crawler.
4. **Dashboard Chrome**: Remove version badges (`v3.0`), permanent architecture descriptions, system metric badges, and tenant labels from the main viewport (tenant details move inside the Settings overlay).
5. **Loud Inline Cards by Default**: Code blocks and shard tables no longer clutter the direct answer flow unless explicitly toggled open.

### B. What We Are Merging
1. **History Sidebar -> Slide-Over Drawer & Command Palette (`Cmd/Ctrl+K`)**:
   - The permanent 64px/256px sidebar is replaced with a slide-over sheet triggered by a top-left hamburger icon or keyboard shortcut `Cmd/Ctrl+K`.
2. **Sources & Evidence -> Sources Sheet Overlay**:
   - Citation chips (`[1]`, `[2]`) in text open the source at the exact location via Text Fragment URL (`#:~:text=`). Clicking "Sources" opens a focused slide-over sheet without leaving the conversation.
3. **Artifact Drawer -> Auto Slide-In Panel**:
   - Opens on the right when an artifact is produced, closing on `Esc` or background tap.

### C. What We Are Adding
1. **Calm Empty State**:
   - Centered greeting, minimal composer, and at most 3 clean suggestion chips.
2. **Reading Column Typography**:
   - Strict ~720px max-width reading column, warm neutral palette (`#FAF9F6` light / `#18181B` dark), humanist typography for assistant prose, and responsive mobile-first padding.
3. **Single Shimmer Status Line**:
   - Real-time work indicator above assistant responses showing stage, elapsed time, and collapsed metrics.
4. **Resumable Event Stream (`Last-Event-ID`)**:
   - Background jobs continue on the server. If the user refreshes or closes the tab, reconnecting to `POST /v1/chat` with `Last-Event-ID` replays pending state.
5. **Autonomy Policy (`config/autonomy.yaml`)**:
   - Configures read-only actions (instant), long-running jobs (auto-start with cancel option), and mutating actions (inline approval card).
6. **UI Actions Engine (`ui_action` SSE Event)**:
   - Typed SSE event emitted when the model recognizes UI intents, invoking client-side overlay states without manual clicks.

---

## 4. Consequences & Impact

- **Zero-Friction User Experience**: Users never face decision fatigue regarding tools, models, or modes.
- **Maintainability**: The existing backend services (`MainChatAgent`, Code Mode, `MemoryService`, research engines) remain completely intact; only the client-side presentation layer and routing heuristics are upgraded.
- **Test Compatibility**: All backend, gate, memory, and chat persistence tests remain 100% green. New end-to-end scenarios test zero-click workflows.
