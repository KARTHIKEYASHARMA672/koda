# 🤖 KODA — Zero-Cost Jarvis-Class Personal AI OS for Windows

> [!IMPORTANT]
> **Strict Zero-Cost Mandate (`$0.00` Hard Cap):** Koda performs **100% of LLM reasoning exclusively through free `$0` OpenCode AI models** via a managed `opencode.EXE serve` runtime (`allow_paid_models = false` by default). No slow local LLMs and zero paid API calls unless explicitly overridden.

> [!NOTE]
> **Automatic Token-Exhaustion Failover:** Whenever an OpenCode free model hits `402` quota exhaustion, `429` rate limits, context overflow, or timeouts, Koda's circuit-breaker router immediately shifts to the next healthy `$0` model in that lane (`< 100 ms`), carrying over canonical SQLite memory, pinned user facts, and active tool context seamlessly.

---

## 📋 Project Properties

| Property | Value |
| :--- | :--- |
| **Project Name** | **Koda** (`KODA`) |
| **Category** | Personal Jarvis-Class AI Operating System (Windows) |
| **Inference Engine** | Managed `opencode.EXE serve` (`v2.2.6`) — verified `$0` model pool |
| **Backend Stack** | Python `3.13` · FastAPI · Pydantic v2 · SQLite WAL + FTS5 · Playwright · `psutil` · `pywinauto` |
| **Voice Stack** | `openWakeWord` (`"Hey Jarvis"`) · VAD · `faster-whisper` local STT · `edge-tts` + `< 150 ms` Barge-In |
| **Frontend & Desktop UI** | React `19` + Vite `6` + TypeScript Spatial Command Deck · PySide6 Always-On-Top Dynamic Island & System Tray |
| **Safety Architecture** | 4-Tier `SafetyGate` (`AUTO` · `NOTIFY` · `CONFIRM` · `DENY`) + Canonical Path Containment |
| **License / Status** | Personal / Local-First Desktop OS · All Phases (`0–6`) Implemented & Tested |

---

## 🧭 Table of Contents

- [1. Core Capabilities](#-1-core-capabilities)
- [2. Architecture & $0 Model Router](#-2-architecture--0-model-router)
- [3. Four-Tier Safety & Privacy Gate](#-3-four-tier-safety--privacy-gate)
- [4. Quickstart (Windows)](#-4-quickstart-windows)
- [5. CLI & Gateway Endpoints](#-5-cli--gateway-endpoints)
- [6. Configuration (`.env`)](#-6-configuration-env)
- [7. Repository Structure & Companion Docs](#-7-repository-structure--companion-docs)

---

## ⚡ 1. Core Capabilities

- **4-Lane Free OpenCode Model Routing & Failover:** Dynamically inspects `/api/model`, rejects any model with `cost > 0`, organizes free models into `fast`, `vision`, `deep_1m`, and `multimodal` lanes, tracks EWMA latency + token spend in SQLite, and auto-shifts across sibling OpenCode sessions with rolling context preservation.
- **Spatial Command Deck & Dynamic Island:**
  - **Web HUD (`http://127.0.0.1:8765`):** Obsidian Dark Luxury Telemetry UI (`#0A0D14` / `#F5F0E6` / `#3B82F6` / `#22D3EE` / `#D9A441`) featuring a 60fps canvas Acoustic Core Orb, Omnibar (`Ctrl+Space`), live 12-model Router Matrix, HITL Approval Cards, Tools/MCP inspector, Memory/Recall manager, and Proactive Timers & Briefings.
  - **PySide6 Desktop Overlay (`koda island`):** Always-on-top rounded Dynamic Island pill (`idle`, `listening`, `thinking`, `shifting`, `speaking`, `confirm_needed`) + System Tray menu + real-time WebSocket state sync.
- **Full-Duplex Voice & Dictation (`koda/voice/pipeline.py`):** Wake-word listener, RMS/VAD speech endpointing, local Whisper transcription (`faster-whisper`), neural voice playback (`edge-tts`), live dictation mode, and instant hardware/software barge-in cancellation.
- **25 Safety-Gated OS, Web & Productivity Tools (`koda/tools/`):**
  - **Windows OS & Hardware:** CPU, RAM, disk, battery, NVIDIA GPU telemetry (`system_metrics`), active/all window enumeration & focusing (`pywinauto`), allowlisted app launcher (`open_app`), screenshot capture (`capture_screen`), media & volume control.
  - **Playwright Browser & Web:** Headless Chromium navigation & summarization (`browser_open`), DuckDuckGo snippet search (`browser_search`), YouTube search (`browser_youtube`), clean article fetching (`web_fetch`).
  - **Workspace Files & Git:** Strictly path-contained `read_file`, `write_file`, `delete_file`, `list_dir`, `search_files`, `git_status`, and HITL-gated `run_shell`.
  - **Productivity & IoT:** Notion-style Markdown / Obsidian Vault notes (`save_note`, `read_note`), smart privacy-filtered clipboard history, persistent episodic/fact search, multi-step saved routines, Home Assistant service calls, and webhooks.
- **Proactive Daemon & Remote Bridge (`koda/daemon/`):** Morning Briefings assembled from telemetry + facts + routines via the `deep_1m` free lane, non-blocking async timers, **opt-in privacy-filtered Screenpipe-lite recall** (never captures incognito/banking/password-manager windows), and optional `.env`-gated **Telegram Bridge** with strict sender user-ID allowlist and `/approve` / `/deny` support.

---

## 🧠 2. Architecture & `$0` Model Router

```
  [Voice / Dynamic Island / Spatial Command Deck / Telegram]
                             │
                             ▼
               ┌──────────────────────────┐
               │  Koda FastAPI + WS Hub   │ ◄── http://127.0.0.1:8765
               └─────┬──────────────┬─────┘
                     │              │
      ┌──────────────▼──┐        ┌──▼─────────────────────────┐
      │ FreeModelRouter │        │ 4-Tier SafetyGate + Tools  │
      │ (4 Lanes, $0)   │        │ AUTO/NOTIFY/CONFIRM/DENY   │
      └──────┬──────────┘        └────────────────────────────┘
             │ Supervised Subprocess (Basic Auth)
             ▼
    C:\Users\karth\.opencode\bin\opencode.EXE serve (v2.2.6)
    ├── Lane Fast       ──► Quick chat, shell & tool plans ($0)
    ├── Lane Vision     ──► Screenshots, OCR & UI parsing ($0)
    ├── Lane 1M Deep    ──► Codebase synthesis & briefings ($0)
    └── Lane Multimodal ──► Audio/video & doc understanding ($0)
```

| OpenCode Circuit State | Meaning & Transition Rule |
| :--- | :--- |
| **`HEALTHY`** | Passing `$0` cost verification; prioritized by lane affinity + lowest EWMA latency. |
| **`SOFT_SHIFTED`** | Single transient error (`429`/timeout); routed around temporarily while keeping short retry eligibility. |
| **`COOLDOWN`** | Repeated/quota exhaustion (`402`); exponential backoff window persisted in SQLite (`data/koda.db`). |
| **`HALF_OPEN`** | Cooldown elapsed; allowed one probe turn — restores to `HEALTHY` on success or re-opens cooldown on failure. |
| **`DISABLED`** | Manually muted via Spatial Command Deck toggle. |

---

## 🔒 3. Four-Tier Safety & Privacy Gate

| Tier | Classification | Examples | Execution Policy |
| :---: | :--- | :--- | :--- |
| **`AUTO`** | Read-only local queries | `system_metrics`, `read_file`, `list_dir`, `git_status`, `memory_search` | Runs immediately & silently |
| **`NOTIFY`** | Reversible desktop actions | `open_app` (allowlisted), `focus_window`, `media_control`, `browser_open` | Runs with audit log & HUD pill notice |
| **`CONFIRM`** | Mutating or external side-effects | `run_shell`, `delete_file`, `ha_call_service`, `trigger_webhook`, writes | **Pauses** until explicit `[Approve]` / `[Deny]` via HUD, Island, or Telegram |
| **`DENY`** | Forbidden system/secret targets | `.env`, credential stores, `C:\Windows`, registry edits, path traversal | **Hard blocked** before execution & logged |

---

## 🚀 4. Quickstart (Windows)

### Prerequisites
- **Python `3.11+`** (`3.13` verified) with project dependencies (`pip install -e .[dev]`)
- **Node.js `20+`** (`v24` verified) for building/developing the React HUD
- **OpenCode CLI** installed at `C:\Users\karth\.opencode\bin\opencode.EXE` (or set `OPENCODE_EXE` in `.env`)

### Install Dependencies & Build HUD

```powershell
# 1. Install Python package & dev/test dependencies
pip install -e .[dev]

# 2. Build the React Spatial Command Deck into frontend/dist/
Set-Location frontend
npm install
npm run build
Set-Location ..
```

### 1-Click Launch (Gateway + Spatial HUD + Dynamic Island)

```powershell
# Run diagnostics first
python -m koda.cli doctor

# Option A: Launch everything via 1-click Windows batch script
.\run_koda.bat

# Option B: Launch manually
python -m koda.cli serve --host 127.0.0.1 --port 8765
# Then open http://127.0.0.1:8765/ and optionally in another terminal:
python -m koda.cli island
```

---

## 💻 5. CLI & Gateway Endpoints

### CLI Commands (`python -m koda.cli`)
| Command | Description |
| :--- | :--- |
| `koda doctor` | Validates OpenCode binary, free-only config (`allow_paid_models=false`), and allowed roots |
| `koda serve --host 127.0.0.1 --port 8765` | Starts managed `opencode.EXE serve` + FastAPI/WebSocket gateway + static HUD |
| `koda ask "<prompt>"` | Sends a single free-routed prompt via `FreeModelRouter` from the terminal |
| `koda island` | Starts the native always-on-top PySide6 Dynamic Island overlay & System Tray |

### Core REST & WebSocket Routes
- `GET /health` · `POST /api/chat` · `WS /ws/events`
- `GET /api/router/status` · `POST /api/router/refresh` · `POST /api/router/models/{id}/state`
- `GET /api/tools` · `POST /api/tools/run` · `GET /api/approvals` · `POST /api/approvals/{id}/resolve` · `GET /api/audit`
- `GET/POST/DELETE /api/memory/facts` · `GET /api/memory/search` · `GET/POST /api/routines` · `GET /api/clipboard`
- `GET /api/voice/status` · `POST /api/voice/listen` · `POST /api/voice/speak` · `POST /api/voice/barge-in` · `POST /api/voice/dictation`
- `POST /api/briefing` · `POST /api/timers` · `GET /api/recall` · `GET /api/recall/status` · `POST /api/recall/toggle`

---

## ⚙️ 6. Configuration (`.env`)

Copy `.env.example` to `.env` (`.env` is gitignored — never commit secrets):

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `KODA_ALLOW_PAID_MODELS` | `false` | Enforces `$0.00` hard cap on all OpenCode models |
| `OPENCODE_EXE` | `C:\Users\karth\.opencode\bin\opencode.EXE` | Explicit OpenCode binary path |
| `KODA_ALLOWED_ROOTS` | `L:\pr 26.2(jarvis anti` | Comma-separated canonical filesystem jail roots |
| `KODA_WAKE_WORD` | `hey_jarvis` | `openWakeWord` trigger model |
| `KODA_TTS_VOICE` | `en-GB-RyanNeural` | Default `edge-tts` neural voice |
| `KODA_TELEGRAM_BOT_TOKEN` | *(blank)* | Optional Telegram remote bridge token |
| `KODA_TELEGRAM_ALLOWED_USER_ID` | *(blank)* | Required numeric allowlist ID when Telegram bridge is enabled |

---

## 📁 7. Repository Structure & Companion Docs

- **Architecture & Spec Suite (Notion-Style):** [`PRD.md`](./PRD.md) · [`ARCHITECTURE.md`](./ARCHITECTURE.md) · [`RULES.md`](./RULES.md) · [`DESIGN.md`](./DESIGN.md) · [`PHASES.md`](./PHASES.md) · [`MEMORY.md`](./MEMORY.md) · [`AGENTS.md`](./AGENTS.md)
- **Backend Core:** [`koda/opencode/`](./koda/opencode/) · [`koda/router/`](./koda/router/) · [`koda/memory/`](./koda/memory/) · [`koda/safety/`](./koda/safety/) · [`koda/tools/`](./koda/tools/) · [`koda/voice/`](./koda/voice/) · [`koda/daemon/`](./koda/daemon/) · [`koda/ui/`](./koda/ui/) · [`koda/gateway/`](./koda/gateway/)
- **Spatial HUD:** [`frontend/src/`](./frontend/src/)
- **Automated Tests:** [`tests/`](./tests/) & [`frontend/src/App.test.tsx`](./frontend/src/App.test.tsx)
