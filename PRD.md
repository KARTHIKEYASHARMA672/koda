# 🎯 KODA — Product Requirements Document (`PRD.md`)

> [!IMPORTANT]
> **Vision:** **Koda** is a local-first, privacy-respecting, Jarvis-class personal AI OS for Windows that thinks exclusively through **OpenCode AI free models (`$0.00` hard cap)**, seamlessly fails over across models upon token/quota exhaustion without losing context, hears/speaks in real time, sees the screen, and executes safe Windows, browser, workflow, and smart-home actions behind a 4-tier permission gate.

---

## 📋 Metadata

| Property | Value |
| :--- | :--- |
| **Product Name** | **Koda** |
| **Target Platform** | Windows 11/10 (Local Workstation + RTX 3050 GPU Acceleration for STT/Audio) |
| **Inference Engine** | Managed `opencode.EXE serve` (`v2.2.6+`) — Strict `$0` Free-Model Routing Only |
| **UI Surfaces** | Spatial Command Deck (React + Vite + TS HUD) + Native PySide6 Dynamic Island Pill & Tray + `koda` CLI |
| **Safety Posture** | 4-Tier Permission Engine (`AUTO`, `NOTIFY`, `CONFIRM`, `DENY`) + Canonical Path Containment |
| **Document Status** | `Locked for Phase 1–6 Execution` (`2026-11-11`) |

---

## 🧭 Table of Contents

- [1. Target Personas & Primary Workflows](#1--target-personas--primary-workflows)
- [2. Core Mandate: Zero-Cost Multi-Model Failover](#2--core-mandate-zero-cost-multi-model-failover)
- [3. Functional Requirements & Extended Jarvis Capabilities](#3--functional-requirements--extended-jarvis-capabilities)
- [4. Non-Functional Requirements & SLAs](#4--non-functional-requirements--slas)
- [5. Explicit Non-Goals & Safety Exclusions](#5--explicit-non-goals--safety-exclusions)

---

## 1. 👤 Target Personas & Primary Workflows

| Persona | Core Need | Primary Koda Workflow |
| :--- | :--- | :--- |
| **Daily Power User / Developer** | Zero-cost, hands-free desktop copilot that replaces scattered tabs, terminals, and paid subscriptions. | Press `Ctrl+Space` or say `"Hey Koda"`, ask a coding/screen/research question, trigger multi-step dev workspace setup, or dictate text directly into the focused editor. |
| **Multitasking Researcher / Student** | Long-horizon reading, web synthesis, clean Obsidian/Markdown notes, and contextual recall across apps. | Capture screen or URL, summarize PDFs/pages via 1M-context free models, save structured Notion-style notes, and query past activity via Screenpipe-lite recall. |
| **Remote / Smart-Space User** | Safe automation of PC routines, browser playback, and optional mobile/smart-home triggers. | Run `"Study Mode"` routine, control YouTube/Spotify playback, check system telemetry, approve sensitive actions from HUD or optional Telegram bridge, or trigger Home Assistant webhooks. |

---

## 2. 💸 Core Mandate: Zero-Cost Multi-Model Failover

> [!WARNING]
> **Non-Negotiable Cost Rule:** Primary reasoning MUST NOT run on slow local LLMs and MUST NEVER incur API charges (`$0.00` strict cap unless the user explicitly overrides `KODA_ALLOW_PAID_MODELS=true`).

1. **Dynamic Zero-Cost Discovery:** On startup and periodic refresh, Koda queries OpenCode's live `/api/model` catalog and filters strictly for active `opencode` provider models whose every pricing tier has `input == 0` and `output == 0`.
2. **4-Lane Capability Routing:**
   - **Lane A (`fast`):** Ultra-responsive chat, intent triage, tool selection, voice replies (`iceman-free`, `flint-40b-free`, `beam-free`, `nemotron-3.5-lightning-free`).
   - **Lane B (`vision`):** Screenshot understanding, UI element reasoning, OCR assistance, visual debugging (`nemotron-3.5-super-vl-free`, `deepseek-v4.1-flash-free`, `inkling-2-small-free`, `longcat-2.5-free`).
   - **Lane C (`deep_1m`):** Multi-file architecture synthesis, large PDF/codebase reasoning, morning briefing synthesis (`nemotron-3.5-lightning-free`, `minimax-m3.1-flash-free`, `glm-5.3-flash-free`).
   - **Lane D (`multimodal`):** Native audio/video/document multimodal prompts (`mimo-v2.6-flash-free`, `minimax-m3.1-flash-free`, `glm-5.3-flash-free`).
3. **Automatic Token & Quota Exhaustion Failover:**
   - Detects HTTP `402` / `429`, SSE `session.execution.failed`, assistant `provider.quota` / rate-limit errors, empty/stalled responses, or context-window overflow.
   - Places the failing model into exponential-backoff `COOLDOWN`, selects the next healthiest sibling model in the target lane (or cross-lane fallback), carries over the canonical SQLite rolling summary + last `N` turns into a fresh OpenCode session, emits a `model_shifted` telemetry notice (`D9A441` Champagne Amber pill), and completes the turn transparently.

---

## 3. ⚡ Functional Requirements & Extended Jarvis Capabilities

| ID | Category | Requirement | Priority | Phase |
| :--- | :--- | :--- | :---: | :---: |
| **FR-001** | **OpenCode Daemon** | Supervise `opencode.EXE serve` with Basic Auth, crash auto-restart, and clean shutdown. | `P0` | Phase 1 |
| **FR-002** | **Free-Only Allowlist** | Filter `/api/model` dynamically so only verified `$0` OpenCode models enter the active routing pool. | `P0` | Phase 1 |
| **FR-003** | **Failover Router** | Auto-shift to next healthy free model on quota/rate-limit/timeout/error with exponential cooldown & telemetry. | `P0` | Phase 1 |
| **FR-004** | **Context Handoff** | Preserve rolling summary, pinned memory facts, and recent conversation turns across model switches. | `P0` | Phase 1 |
| **FR-005** | **Gateway & WS Hub** | FastAPI REST + bidirectional WebSocket server (`/health`, `/api/chat`, `/api/router`, `/api/memory`, `/api/approvals`). | `P0` | Phase 2 |
| **FR-006** | **Hybrid Memory** | Persistent SQLite + FTS5 store for user `facts`, `episodes`, automatic preference extraction, and optional vector similarity. | `P0` | Phase 2 |
| **FR-007** | **4-Tier Safety Gate** | Classify every tool execution into `AUTO`, `NOTIFY`, `CONFIRM`, or `DENY`; pause Tier-3 actions pending explicit approval. | `P0` | Phase 2 |
| **FR-008** | **Windows UIA & Apps** | Inspect active window/UIA accessibility tree, list/focus/snap windows, launch allowlisted apps, control volume/media. | `P0` | Phase 3 |
| **FR-009** | **System Telemetry** | Read live CPU, RAM, RTX 3050 GPU/VRAM (if accessible), disk, battery, network, and top process stats. | `P0` | Phase 3 |
| **FR-010** | **Playwright Browser** | Headless/controlled browser navigation, DOM text extraction, YouTube/web playback & search automation. | `P0` | Phase 3 |
| **FR-011** | **Scoped Files & Git** | Read/write/diff/search files strictly inside `KODA_ALLOWED_ROOTS`, plus read-only git status/diff/log & gated shell commands. | `P0` | Phase 3 |
| **FR-012** | **Smart Clipboard** | Monitor clipboard history locally (with password-manager/length guard) and search/reuse recent snippets. | `P1` | Phase 3 |
| **FR-013** | **Obsidian / Notes** | Save and index clean Notion-style Markdown notes (`notes/` or configured `KODA_OBSIDIAN_VAULT_PATH`). | `P1` | Phase 3 |
| **FR-014** | **Web Research & Digest** | Fetch clean article/documentation text and synthesize cited summaries without raw HTML bloat. | `P1` | Phase 3 |
| **FR-015** | **IoT & Webhook Bridge** | Call configured Home Assistant REST entities or user-defined local/LAN webhooks (`CONFIRM` or allowlisted `NOTIFY`). | `P2` | Phase 3 |
| **FR-016** | **Wake Word & VAD** | Hands-free `"Hey Koda"` (`openWakeWord` + RMS/VAD speech endpointing) + push-to-talk hotkey (`Ctrl+Space`). | `P0` | Phase 4 |
| **FR-017** | **Local STT & Dictation** | Real-time transcription via `faster-whisper` (`base.en`), including live typing mode into the active Windows app. | `P0` | Phase 4 |
| **FR-018** | **Streaming TTS & Barge-In** | Low-latency natural speech (`edge-tts`, optional `kokoro-onnx`) with `< 150 ms` instant cancellation on speech/key interrupt. | `P0` | Phase 4 |
| **FR-019** | **Spatial Command Deck** | Obsidian Dark-Luxury React HUD (`DESIGN.md`): chat timeline, inline tool & approval cards, live 12-model router grid, memory & routine panels. | `P0` | Phase 5 |
| **FR-020** | **Dynamic Island & Tray** | Native always-on-top PySide6 status pill (`idle/listening/thinking/shifting/speaking/confirm`) + Windows tray menu + global shortcut. | `P0` | Phase 5 |
| **FR-021** | **Workflow Routines** | Multi-step reusable macros (e.g., `"Morning Dev Setup"`, `"Focus Mode"`) combining app launches, URLs, notes, and prompts. | `P1` | Phase 5/6 |
| **FR-022** | **Proactive Scheduler** | Cron/interval scheduler for timers, reminders, battery/disk alerts, and custom daily Morning Briefings. | `P1` | Phase 6 |
| **FR-023** | **Screenpipe-Lite Recall** | Opt-in privacy-filtered local window-title + periodic active-window context log (exclusions for incognito/password apps). | `P1` | Phase 6 |
| **FR-024** | **Telegram Remote Bridge** | Optional `.env`-gated Telegram bot allowing allowlisted user ID to send prompts and approve/deny actions remotely. | `P2` | Phase 6 |

---

## 4. 📏 Non-Functional Requirements & SLAs

| Metric | Target | Verification Method |
| :--- | :--- | :--- |
| **Direct Inference API Cost** | **`$0.00` strict (`allow_paid_models=false`)** | Unit tests rejecting non-zero `cost` models + runtime assertion |
| **Failover Recovery Latency** | **`< 1.5s`** overhead to detect error, record cooldown, and dispatch sibling session | Deterministic fault-injection router test (`pytest`) |
| **Barge-In Audio Stop** | **`< 150 ms`** from interrupt signal to playback silence | Deterministic voice cancellation timing test (`pytest`) |
| **Local UI / Event Loop Latency** | Zero synchronous stalls in FastAPI/PySide6 UI threads | Async workload separation + responsive WS checks |
| **Visual & Accessibility QA** | WCAG AA contrast (`>= 4.5:1`), `0` console/HTTP errors at `1440×900` & `430×900` | Live Chromium Playwright DOM & screenshot inspection |

---

## 5. 🚫 Explicit Non-Goals & Safety Exclusions

- No unrequested cloud telemetry or external analytics SaaS.
- No bypass of CAPTCHAs, anti-bot walls, DRM, OS privilege boundaries, or OpenCode authentication gates.
- No unapproved deletion of user files, system registry modification (`HKLM`/`C:\Windows`), or unapproved external messaging/shell execution.
- No fake mocks disguised as live integrations in production code paths.
