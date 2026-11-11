# 🧠 KODA — Engineering Memory & Verified Facts (`MEMORY.md`)

> [!NOTE]
> **Purpose:** Single source of truth for verified environment facts, empirical OpenCode API discoveries, completed phase evidence, and exact verification commands.

---

## 📋 Metadata

| Property | Value |
| :--- | :--- |
| **Current Phase** | `All Phases (0–6) Complete & Verified` |
| **Workspace Root** | `l:\pr 26.2(jarvis anti` |
| **Workstation OS / GPU** | Windows · `NVIDIA GeForce RTX 3050 Laptop GPU` (4 GB VRAM) |
| **Last Updated** | `2026-11-11` |

---

## 🧭 Table of Contents

- [1. Verified Local Environment & Toolchains](#1--verified-local-environment--toolchains)
- [2. Verified OpenCode v2.2.6 Empirical Contract](#2--verified-opencode-v226-empirical-contract)
- [3. Architecture & Technology Decisions](#3--architecture--technology-decisions)
- [4. Phase Verification Log](#4--phase-verification-log)
- [5. Verified Commands Quick Reference](#5--verified-commands-quick-reference)

---

## 1. 🖥️ Verified Local Environment & Toolchains

- **Runtimes Verified:** Python `3.13.7`, Node.js `v24.14.1`, `npm 11.11.0`, `git 2.51.0.windows.1`, Docker, Playwright `1.58.0`.
- **Missing Tools (Confirmed Absent):** `rustc`, `cargo`, `uv`.
- **OpenCode Binary Verified:** `C:\Users\karth\.opencode\bin\opencode.EXE` (`serve` runs version `2.2.6`). Note: PowerShell `opencode` resolves to an alias (`Start-Opencode`), so subprocess calls MUST invoke `opencode.EXE` explicitly via `OPENCODE_EXE`.
- **Pre-Installed Python Libraries (`pip list`):** `fastapi 0.116.2`, `uvicorn 0.35.0`, `httpx 0.28.1`, `pydantic 2.12.5`, `pydantic-settings 2.13.1`, `pytest 9.0.2`, `faster-whisper 1.2.1`, `openwakeword 0.6.0`, `onnxruntime 1.24.4`, `torch 2.13.0`, `torchaudio 2.11.0+cu128`, `edge-tts 7.2.8`, `sounddevice 0.5.5`, `PyAudio 0.2.14`, `pywinauto 0.6.9`, `PyAutoGUI 0.9.54`, `keyboard 0.13.5`, `psutil 7.2.2`, `chromadb 1.5.5`, `PySide6 6.11.0`. (`kokoro-onnx` is not pre-installed; `edge-tts` is installed and ready.)

---

## 2. 🔌 Verified OpenCode `v2.2.6` Empirical Contract

- **Direct `opencode.ai/zen/v1` blocked:** Direct raw HTTP calls outside `opencode.EXE` fail with `HTTP 403 FreeTierError` — all inference MUST run through a managed `opencode.EXE serve` subprocess.
- **API Prefix:** `/` HTML paths serve the OpenCode Web UI; all JSON REST endpoints are prefixed with **`/api/`** (`/api/info`, `/api/model`, `/api/session`, `/api/event`).
- **Basic Auth:** Passing `OPENCODE_SERVER_USERNAME` and `OPENCODE_SERVER_PASSWORD` into the `opencode.EXE serve` environment cleanly enforces HTTP Basic Auth on `/api/*` and `/openapi.json`.
- **Schema Gotchas Verified Live:**
  1. `GET /api/model` returns `cost` as a **`list`** of tier dicts (e.g., `[{"input": 0, "output": 0, ...}]`), NOT a `dict`.
  2. `POST /api/session` returns `{"data": {"id": "ses_...", ...}}`.
  3. `POST /api/session/{id}/model` requires `{"model": {"providerID": "opencode", "id": "<model_id>"}}` (`id`, NOT `modelID`) and returns `204`.
  4. `POST /api/session/{id}/prompt` accepts `{"text": "..."}` (`additionalProperties: false`).
  5. `GET /api/experimental/usage/limits` timed out (`httpx.ReadTimeout` at `5s`) -> keep out of critical/startup paths.
- **Verified Live `$0` `opencode` Models in `v2.2.6`:**
  - Text: `iceman-free`, `flint-40b-free`, `beam-free`, `nemotron-3.5-lightning-free`, `big-pickle`
  - Vision: `nemotron-3.5-super-vl-free`, `deepseek-v4.1-flash-free`, `inkling-2-small-free`, `longcat-2.5-free`
  - Video + Vision: `minimax-m3.1-flash-free`, `glm-5.3-flash-free`
  - Audio + Video + Vision: `mimo-v2.6-flash-free`
  - Live zero-cost prompt test confirmed `opencode/iceman-free` returned `"KODA_ONLINE"` with `"cost": 0`.

---

## 3. 🧭 Architecture & Technology Decisions

| Decision | Choice | Why |
| :--- | :--- | :--- |
| **Desktop Shell** | PySide6 Dynamic Island + React/Vite/TS HUD | `rustc`/`cargo` are absent, preventing Tauri v2 builds; PySide6 `6.11.0` + React delivers both a native always-on-top Windows orb and a spatial telemetry deck immediately. |
| **LLM Inference** | Managed `opencode.EXE serve` (`cost == 0` only) | Satisfies user mandate against slow local LLMs while maintaining strict `$0` spending and live `/api/model` rotation safety. |
| **Memory Store** | SQLite WAL + FTS5 (`data/koda.db`) | Zero external daemon friction, ACID context persistence across model shifts, fast full-text + structured recall. |
| **TTS Primary Engine** | `edge-tts` (`en-GB-RyanNeural`) + optional `kokoro-onnx` adapter | `edge-tts` is pre-installed (`7.2.8`) and high quality; supports streaming chunk playback with instant event-driven barge-in. |

---

## 4. ✅ Phase Verification Log

| Phase | Date | Checks Run | Result |
| :---: | :--- | :--- | :---: |
| **Phase 0** | `2026-11-11` | Verified `opencode.EXE 2.2.6`, Python `3.13.7`, Node `24.14.1`, live `$0` prompt test, all canonical Notion-style docs written (`PRD`, `ARCHITECTURE`, `RULES`, `DESIGN`, `PHASES`, `MEMORY`, `AGENTS`). | `PASS` |
| **Phase 1** | `2026-11-11` | `python -m pytest` (`17 passed`) + live `opencode.EXE serve` integration smoke test (`12` free models discovered, `iceman-free` returned `'KODA_PHASE1_LIVE_OK'`, `COST=0.0`, clean SQLite handle release). Fixed plugin-activation `/api/model` readiness check & Windows SQLite connection closing. | `PASS` |
| **Phase 2** | `2026-11-11` | `python -m pytest` (`26 passed`) + `python -m koda.cli doctor` (exit `0`). Verified SQLite + FTS5 memory, 4-tier HITL gate, WS event stream, failover routing, and audit log. | `PASS` |
| **Phase 3** | `2026-11-11` | `python -m pytest` (`32 passed`). Verified `SystemOSController` (`psutil`, UIA windows, safe app allowlist), `WorkspaceFileTools` (canonical path containment & safe shell), `ProductivityTools` (Notion-style notes, clipboard, routines), `WebAndIoTTools` (`web_fetch`, Home Assistant/webhook), and real Playwright headless Chromium navigation. | `PASS` |
| **Phase 4** | `2026-11-11` | `python -m pytest` (`35 passed`). Verified PCM RMS calculation, `VadEndpointTracker` framing, `< 150ms` TTS barge-in cancellation, `VoicePipeline` state transitions, and `/api/voice/*` gateway endpoints. | `PASS` |
| **Phase 5** | `2026-11-11` | `npm run lint` (`0` errors), `npx tsc --noEmit`, `npm test` (Vitest `1/1`), `npm run build` (`vite build`), `pytest tests/test_ui_island.py` (PySide6 pill + WS/Tray), and headless Playwright Chromium visual & DOM audit at `1440×900` & `430×900` (`0` console/page/HTTP errors, `0` horizontal overflow). Fixed `ToolRegistry.list_tools()` static `default_tier()` reporting (`CONFIRM` instead of `DENY` for `write_file`/`delete_file`/`run_shell`). | `PASS` |
| **Phase 6** | `2026-11-11` | `python -m pytest` (`40 passed`), `python -m koda.cli doctor` (exit `0`), live `opencode.EXE serve` end-to-end check (`GET /health` `200`, `GET /` `200`, `12` free models, `POST /api/chat` -> `"KODA_E2E_ZERO_COST_OK"` via `iceman-free` at `cost: 0.0`), proactive briefing + async timers + Screenpipe-lite privacy filter + allowlisted Telegram bridge + `run_koda.bat` + `README.md`. | `PASS` |

---

## 5. ⚡ Verified Commands Quick Reference

```powershell
# Backend test suite (40 tests)
python -m pytest

# Frontend lint, typecheck, test, build
Set-Location frontend
npm run lint
npx tsc --noEmit
npm test
npm run build
Set-Location ..

# Workstation health check & Launch
python -m koda.cli doctor
python -m koda.cli serve --host 127.0.0.1 --port 8765
python -m koda.cli island

# Manual OpenCode server diagnostics
C:\Users\karth\.opencode\bin\opencode.EXE serve --hostname 127.0.0.1 --port 4096
```
