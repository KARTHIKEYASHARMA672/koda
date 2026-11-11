# 📐 KODA — Engineering & Behavior Rules (`RULES.md`)

> [!IMPORTANT]
> **Purpose:** Non-negotiable engineering standards, safety boundaries, and verification rules governing all development in `l:\pr 26.2(jarvis anti`.

---

## 📋 Metadata

| Property | Value |
| :--- | :--- |
| **Project** | **Koda** — Jarvis-Class Personal AI OS for Windows |
| **Rule Precedence** | System/Safety Rules → User Request → `RULES.md` → Global Skills → Codebase Conventions |
| **Cost Guardrail** | **Strict Zero-Cost (`allow_paid_models = false`)** — OpenCode free models only |
| **Primary Stack** | Python `3.13` (FastAPI, Pydantic v2, asyncio, SQLite, MCP, Voice, UIA) + React/Vite/TS HUD + PySide6/WebEngine Native Island/Tray |
| **Last Updated** | `2026-11-11` |

---

## 🧭 Table of Contents

- [1. Reading Order Before Changes](#1--reading-order-before-changes)
- [2. Zero-Cost & Model Routing Invariants](#2--zero-cost--model-routing-invariants)
- [3. Security, Secrets & Action Permission Gates](#3--security-secrets--action-permission-gates)
- [4. Code Style, Architecture & TDD Discipline](#4--code-style-architecture--tdd-discipline)
- [5. Testing, Lint & Visual Verification Gates](#5--testing-lint--visual-verification-gates)
- [6. Documentation & Memory Sync Rules](#6--documentation--memory-sync-rules)

---

## 1. 📖 Reading Order Before Changes

Before implementing or modifying any module:
1. Read `MEMORY.md` to confirm current phase, known issues, and verified commands.
2. Read the relevant section of `PRD.md`, `ARCHITECTURE.md`, and `PHASES.md`.
3. Read `DESIGN.md` before modifying any HUD, React component, CSS token, or Dynamic Island overlay.

---

## 2. 💸 Zero-Cost & Model Routing Invariants

- **Strict Free-Only Gate:** Every model added to the active routing pool MUST satisfy `cost.input == 0` AND `cost.output == 0` in OpenCode model metadata (unless `KODA_ALLOW_PAID_MODELS=true` is explicitly toggled by the user).
- **Managed OpenCode Runtime Only:** Never bypass OpenCode's client restriction by hitting `https://opencode.ai/zen/v1` directly with raw HTTP headers. Always invoke free models through Koda's supervised `opencode serve` process.
- **No Unbounded Retries:** Router failover MUST cap retries per turn (e.g., max `min(len(healthy_models), 5)` attempts), mark exhausted models in `COOLDOWN` with exponential backoff, and surface a clear status error if all free models are temporarily exhausted.
- **No Silent Context Wipe:** When shifting models mid-conversation due to token/quota exhaustion, Koda MUST carry over the canonical rolling summary + recent turns + pending tool state from SQLite.

---

## 3. 🔒 Security, Secrets & Action Permission Gates

- **Never Expose or Commit Secrets:** Store any optional user tokens (e.g., Telegram bot token) strictly in `.env` (gitignored). Provide `.env.example` with placeholders only.
- **Four-Tier Tool Safety Policy:**
  - `AUTO` (Read-only): System stats, weather, read inside allowed roots, memory recall, screen Q&A.
  - `NOTIFY` (Reversible OS actions): Launch allowlisted app, switch/snap window, media/volume/brightness, browser navigation.
  - `CONFIRM` (Mutating / External side effects): File delete/overwrite, arbitrary shell command execution, killing OS processes, sending emails/WhatsApp/Telegram messages -> **MUST pause and obtain explicit user approval via HUD or voice `"Confirm"` before execution**.
  - `DENY` (Blocked): Accessing `.env`/credential stores, modifying `C:\Windows` or system registry, bypassing CAPTCHAs/auth walls, escalating privileges.
- **Path Containment:** Filesystem tools resolve canonical paths (`Path.resolve()`) and reject traversal outside user-configured allowed workspace directories unless explicitly confirmed.

---

## 4. 🧩 Code Style, Architecture & TDD Discipline

- **Test-Driven Development (TDD):** Write failing unit/integration tests (`pytest` for backend, `vitest` for frontend) BEFORE implementing feature logic. Watch tests fail for the expected reason, write minimal clean code to pass, then refactor.
- **Type Safety & Validation:**
  - Python: Strict type annotations (`from __future__ import annotations`), Pydantic v2 schemas at API/tool boundaries, structured `logging` (no `print()` debugging in production modules).
  - TypeScript/React: Strict TS (`noEmit` clean), centralized CSS tokens from `DESIGN.md` (zero hardcoded arbitrary colors scattered in JSX).
- **Non-Blocking Event Loop:** Never block FastAPI's `asyncio` loop or GUI threads with synchronous audio, OCR, Playwright, or subprocess calls (`asyncio.to_thread` or dedicated worker processes).
- **Clean Lifecycles:** Every spawned background child process (`opencode serve`, voice pipeline, screen watcher) MUST register graceful shutdown cleanup on daemon exit.

---

## 5. ✅ Testing, Lint & Visual Verification Gates

Every phase is marked `Done` ONLY after running and recording real command output:
- **Backend:** `pytest` (all green), `ruff check` (if installed) / syntax + type check.
- **Frontend:** `npm run lint`, `npx tsc --noEmit`, `npm run build`, `npm test` (`vitest`).
- **UI & End-to-End:** Headless/live Chromium screenshot inspection via Playwright or browser subagent verifying `0` console/page/HTTP errors and readable contrast.

---

## 6. 📝 Documentation & Memory Sync Rules

- All `.md` documentation files in this repo MUST follow **Notion-style formatting** (title header, callouts, properties table, `---` dividers, structured tables/checklists, TOC).
- Update `MEMORY.md` and `PHASES.md` after every completed phase with exact verified commands and outputs.
