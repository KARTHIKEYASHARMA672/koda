# 🗓️ KODA — Phased Implementation Roadmap (`PHASES.md`)

> [!NOTE]
> **Execution Protocol:** Work strictly phase-by-phase using Test-Driven Development (`pytest` / `vitest`). A phase moves to `Done` only after its acceptance tests, lint/type checks, and visual/live checks pass and are recorded in `MEMORY.md`.

---

## 📋 Metadata

| Property | Value |
| :--- | :--- |
| **Project** | **Koda** — Jarvis-Class Personal AI OS for Windows |
| **Core Mandate** | OpenCode AI **Free Models Only** + **Automatic Token-Exhaustion Routing** |
| **UI Stack** | React + Vite + TypeScript Spatial Command Deck + Native PySide6 Dynamic Island & System Tray |
| **Last Updated** | `2026-11-11` |

---

## 🧭 Phase Overview & Status Tracker

| Phase | Name | Outcome | Status |
| :---: | :--- | :--- | :--- |
| **Phase 0** | **Docs & Contract Lock** | Canonical Notion-style docs (`PRD`, `ARCHITECTURE`, `RULES`, `DESIGN`, `MEMORY`, `PHASES`, `AGENTS`) + `.gitignore` + `.env.example` + verified live OpenCode API contract. | `Done` |
| **Phase 1** | **OpenCode Daemon & Free-Model Router** | Supervised `opencode serve` lifecycle, strict `cost == 0` dynamic model pool discovery, 4-lane task router, SQLite quota telemetry, and automatic token-exhaustion circuit breaker with context handoff. | `Done` |
| **Phase 2** | **Koda Gateway, Hybrid Memory & Safety Gate** | FastAPI + WebSocket/SSE hub, SQLite + FTS5 persistent memory (`facts`, `episodes`, `notes`, `routines`), 4-tier HITL permission gate, and CLI (`koda`). | `Done` |
| **Phase 3** | **OS Hands, MCP Bus & Extended Jarvis Skills** | Windows UIA (`pywinauto`) app/window control, Playwright browser & YouTube automation, scoped file/git/shell tools, smart clipboard history, Obsidian/Markdown notes, and IoT/Home Assistant webhook bridge. | `Done` |
| **Phase 4** | **Full-Duplex Voice Pipeline** | `"Hey Koda"` wake word (`openWakeWord`), `Silero VAD` / RMS speech segmentation, `faster-whisper` local STT, `edge-tts` / `kokoro-onnx` streaming TTS, voice dictation typing, and `< 100 ms` barge-in. | `Done` |
| **Phase 5** | **Spatial Command Deck & Dynamic Island HUD** | Dark-luxury React Spatial HUD (Chat + Inline Tool/Approval Cards + Live 12-Model Router Matrix + Memory/Timeline Inspector + Routines) + Always-on-top PySide6 Dynamic Island & Tray + `Ctrl+Space` global hotkey. | `Done` |
| **Phase 6** | **Proactive Daemon, Recall & Hardening** | Morning briefings, timers/cron scheduler, opt-in Screenpipe-lite local window/OCR recall, optional Telegram remote bridge, Windows `run_koda.bat`, full test/visual audit, GitHub push & memory sync. | `Done` |

---

## 🎯 Detailed Phase Gates & Acceptance Criteria

### Phase 1 — OpenCode Daemon & Free-Model Router
- **In-Scope:** Managed `opencode.EXE serve` subprocess launcher (ephemeral/configured port + Basic Auth), dynamic `/api/model` parser enforcing `cost == 0`, 4-lane router (`fast`, `vision`, `deep_1m`, `multimodal`), circuit-breaker state machine (`HEALTHY` / `SOFT_SHIFTED` / `COOLDOWN` / `HALF_OPEN`), SSE `/api/event` stream listener, and context-preserving failover across sibling sessions.
- **Verification Gate:**
  - `pytest tests/test_router.py tests/test_opencode_bridge.py` passes with deterministic simulated `402`/`429`/timeout/context-limit failovers.
  - Live integration check proves `POST /api/session/{id}/prompt` responds cleanly via a verified `$0` OpenCode model.

### Phase 2 — Koda Gateway, Hybrid Memory & Safety Gate
- **In-Scope:** FastAPI server (`/health`, `/api/chat`, `/api/router/status`, `/api/memory`, `/api/approvals`, `/ws/events`), SQLite FTS5 memory store with auto-fact extraction, 4-tier tool permission evaluator (`AUTO`, `NOTIFY`, `CONFIRM`, `DENY`), and `koda` CLI.
- **Verification Gate:**
  - `pytest tests/test_memory.py tests/test_safety.py tests/test_gateway.py` passes; Tier-3/4 actions block without approval token.

### Phase 3 — OS Hands, MCP Bus & Extended Jarvis Skills
- **In-Scope:** Tool registry + MCP bridge (`Windows UIA`, `Playwright Browser`, `Filesystem/Git`, `System Metrics`, `Clipboard`, `Markdown/Obsidian Notes`, `Web Research`, `IoT/Webhook/MQTT bridge`), all routed through the 4-tier permission gate.
- **Verification Gate:**
  - `pytest tests/test_tools_*.py` passes; real safe tool execution (system metrics, notepad/UIA query, scoped file write/read, Playwright headless test) verified.

### Phase 4 — Full-Duplex Voice Pipeline
- **In-Scope:** Non-blocking audio worker (`openWakeWord`, `faster-whisper`, `edge-tts` / `kokoro-onnx` optional weights), barge-in playback interrupt event, and live dictation into focused window.
- **Verification Gate:**
  - `pytest tests/test_voice_pipeline.py` passes using deterministic synthetic PCM audio fixtures + barge-in cancellation timing `< 150 ms`.

### Phase 5 — Spatial Command Deck & Dynamic Island HUD
- **In-Scope:** Vite + React + TypeScript HUD adhering strictly to `DESIGN.md` tokens (`#0A0D14` Obsidian, `#F5F0E6` Porcelain, `#3B82F6` Cobalt, `#22D3EE` Cyan, `#D9A441` Gold), live Free-Model Router Monitor, HITL Approval Cards, Memory/Routine views, plus PySide6 Dynamic Island pill & tray launcher.
- **Verification Gate:**
  - `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run build` all pass with `0` errors; live Chromium Playwright screenshot audit at `1440×900` & `430×900` with `0` console/HTTP errors.

### Phase 6 — Proactive Daemon, Recall & Hardening
- **In-Scope:** Scheduler/timers/morning briefing generator, opt-in privacy-filtered local window-title/OCR Recall index, saved multi-step Workflow Routines, optional Telegram bot bridge (`.env`-gated), `run_koda.bat` launcher, final independent review, Public GitHub push (`KARTHIKEYASHARMA672/koda`), and `KARTHIKEYASHARMA672/memory` sync.
- **Verification Gate:**
  - Full backend + frontend test suites green, zero secret leaks (`git status` + pattern scan), end-to-end live verification recorded in `MEMORY.md`.
