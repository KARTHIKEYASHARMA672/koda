# 🤖 KODA — Agent & Contributor Operating Guide (`AGENTS.md`)

> [!IMPORTANT]
> **Purpose:** Concise working instructions for every AI agent or developer editing `l:\pr 26.2(jarvis anti`.

---

## 📋 Metadata

| Property | Value |
| :--- | :--- |
| **Project** | **Koda** — Jarvis-Class Personal AI OS for Windows |
| **Primary Stack** | Python `3.13` (FastAPI + Pydantic v2 + PySide6) + React/Vite/TypeScript |
| **Core Reference Docs** | `RULES.md` · `DESIGN.md` · `PRD.md` · `ARCHITECTURE.md` · `PHASES.md` · `MEMORY.md` |
| **Last Updated** | `2026-11-11` |

---

## 1. 📖 Mandatory Pre-Edit Checklist

1. Read `MEMORY.md` for current phase status and verified API quirks.
2. Read the phase gate in `PHASES.md` and design contract in `ARCHITECTURE.md`.
3. When editing UI components, read `DESIGN.md` and use semantic CSS variables (`--bg-canvas`, `--text-primary`, `--accent-*`).
4. Respect `RULES.md` invariants: **zero paid models**, **4-tier permission gate**, **canonical path containment**, **no secrets in repo**.

---

## 2. 🧪 Engineering Workflow (Strict TDD)

1. Write failing `pytest` / `vitest` tests FIRST covering normal paths, edge cases, and failure/safety boundaries.
2. Verify tests fail for the expected reason before writing implementation code.
3. Write the smallest clean, typed, documented implementation to make tests pass.
4. Refactor without duplicating logic or blocking the async event loop.
5. Run validation gates (`pytest`, plus `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run build` for frontend phases).
6. For UI changes, verify live rendered output in headless/live Chromium at `1440×900` and `430×900` with `0` console/HTTP errors.
7. Update `MEMORY.md` and `PHASES.md` with honest command results (or mark `Not run — reason`).

---

## 3. ⚠️ Forbidden Shortcuts

- Never bypass `SafetyGate` (`CONFIRM` / `DENY`) in OS, shell, browser, filesystem, or integration tools.
- Never allow non-zero `cost` models unless `KODA_ALLOW_PAID_MODELS=true` is explicitly configured.
- Never parse OpenCode `cost` assuming it is a `dict` (it is a `list` of tier objects in `v2.2.6`).
- Never call `/api/experimental/usage/limits` on critical/startup paths.
- Never write non-Notion-style `.md` files or commit `.env` / tokens / runtime `.db` artifacts.
