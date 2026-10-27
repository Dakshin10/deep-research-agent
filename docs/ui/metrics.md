# Aether Single-Screen UI Metrics & Performance Report

**Date**: 2026-10-27  
**Scope**: `apps/web` (Next.js 14 App Router, TailwindCSS, TypeScript strict)  
**Target**: Single-Screen, Type-Only Assistant UX Quality Bar

---

## 1. Core Performance & Responsiveness Metrics (Measured)

All values below were measured via automated test runs and CLI executions in this session. Raw JSON outputs and logs are committed under `docs/ui/raw/`.

| Metric | Target | Measured Result | Command / Source | Raw Log |
|---|---|---|---|---|
| **Lighthouse Desktop Accessibility** | >= 95 | **100 / 100** | `npx lighthouse http://127.0.0.1:3000 --preset=desktop` | [`docs/ui/raw/lighthouse_desktop.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/lighthouse_desktop.json) |
| **Lighthouse Desktop Best Practices**| >= 90 | **96 / 100** | `npx lighthouse http://127.0.0.1:3000 --preset=desktop` | [`docs/ui/raw/lighthouse_desktop.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/lighthouse_desktop.json) |
| **Lighthouse Desktop Performance**   | >= 80 | **88 / 100** | `npx lighthouse http://127.0.0.1:3000 --preset=desktop` | [`docs/ui/raw/lighthouse_desktop.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/lighthouse_desktop.json) |
| **Lighthouse Mobile Accessibility**  | >= 95 | **100 / 100** | `npx lighthouse http://127.0.0.1:3000 --form-factor=mobile` | [`docs/ui/raw/lighthouse_mobile.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/lighthouse_mobile.json) |
| **Lighthouse Mobile Best Practices** | >= 90 | **96 / 100** | `npx lighthouse http://127.0.0.1:3000 --form-factor=mobile` | [`docs/ui/raw/lighthouse_mobile.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/lighthouse_mobile.json) |
| **Lighthouse Mobile Performance**    | >= 75 | **79 / 100** | `npx lighthouse http://127.0.0.1:3000 --form-factor=mobile` | [`docs/ui/raw/lighthouse_mobile.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/lighthouse_mobile.json) |
| **Axe-core Violations (Serious/Crit)**| 0 | **0 violations** | `@axe-core/playwright` WCAG 2.1 AA scan | [`docs/ui/raw/axe_active_state.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/axe_active_state.json) |
| **Cumulative Layout Shift (CLS)**    | < 0.100 | **0.0085** | `PerformanceObserver({type: 'layout-shift'})` | [`docs/ui/raw/cls_measurement.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/cls_measurement.json) |
| **Time to First Status (TTFS)**      | < 2,000 ms | **1,394 ms** | `npx playwright test e2e/measurements.spec.ts` | [`docs/ui/raw/latency_measurements.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/latency_measurements.json) |
| **Time to First Token (TTFT)**       | < 2,000 ms | **1,399 ms** | `npx playwright test e2e/measurements.spec.ts` | [`docs/ui/raw/latency_measurements.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/latency_measurements.json) |
| **Initial JS Bundle Size (`/`)**     | < 120 kB | **104 kB** (16.9 kB route + 87.3 kB shared) | `npm run build` | [`docs/ui/raw/bundle_size.txt`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/bundle_size.txt) |
| **Prefers-Reduced-Motion**           | Compliant | **Active & Verified** | `emulateMedia({ reducedMotion: 'reduce' })` | [`docs/ui/raw/reduced_motion.json`](file:///d:/Dakshin_learn/agentic_ai_and_rag/deep-research-agent/docs/ui/raw/reduced_motion.json) |


---

## 2. Visual Regression & Screen Coverage

The interface operates strictly on a single viewport route (`/`) with fluid overlays:

1. **Empty State**:
   - Clean, centered greeting (*"What would you like to explore?"*).
   - Exactly 3 suggestion chips.
   - Zero dashboard noise, no version numbers, no architecture diagrams.
2. **Streaming Prose & Progressive Disclosure**:
   - Assistant answers stream as clean, readable serif/humanist prose (not bubble blocks).
   - Work details (parallel shards, code execution, budget bar) stay collapsed inside `WorkStatusLine` with shimmer animation until clicked.
   - Collapses to a 1-line summary when complete.
3. **Citations & Deep Links**:
   - Numbered inline chips (`[1]`, `[2]`).
   - Hover reveals title, verified excerpt, location offset, and Scroll-to-Text deep link (`#:~:text=`).
4. **Artifact Panel**:
   - Automatically slides in from the right when reports, decks, or idea-card tables are generated.
   - Closes with `Esc` or background tap.
5. **Memory Graph Canvas**:
   - Full-screen overlay on `/?overlay=memory`.
   - SVG circular force layout, node inspector, search, pin/forget controls, and vault sync.
6. **Settings Sheet**:
   - Accessible from `...` menu or by typing *"open settings"*.
   - Models, Code Mode backend switcher, and host allowlist.

---

## 3. Keyboard Accessibility Walkthrough

| Shortcut | Action | Verification Result |
|---|---|---|
| `Enter` | Submit message from composer | ✅ Verified |
| `Shift + Enter` | Multiline newline inside composer | ✅ Verified |
| `Esc` | Stop active generation / Close any active overlay | ✅ Verified |
| `Cmd/Ctrl + K` | Open global Command Palette (search chats & actions) | ✅ Verified |
| `Tab` / `Shift + Tab` | Focus cycle across composer, chips, and overlays | ✅ Verified |

---

## 4. Mobile Viewport Adaptations (360px - 768px)

- **Reading Column**: Expands to `100vw` with `16px` padding on mobile devices while maintaining comfortable line lengths on desktop (`720px`).
- **Touch Targets**: All interactive buttons (attach `+`, send, history toggle, citation chips) enforce minimum touch dimensions of `44px x 44px`.
- **Slide-overs**: History drawer and Artifact drawer expand to `88vw` with gesture-friendly backdrops.
