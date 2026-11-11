# 🎨 KODA — Visual Design & Interaction Specification (`DESIGN.md`)

> [!NOTE]
> **Aesthetic Declaration:**
> - **Vibe:** Precision Spatial Studio / Dark Luxury Telemetry Deck (clean obsidian hardware instrumentation + warm porcelain legibility + crisp jewel status signals — zero generic purple-gradient AI slop).
> - **Core Font Pairing:** `Syne` (Display & HUD headings) + `Plus Jakarta Sans` (UI copy & action cards) + `JetBrains Mono` (Router telemetry, token rates, MCP logs).
> - **Dominant Color Palette:** Obsidian Ink (`#0A0D14`), Elevated Slate Glass (`#111622`), Warm Porcelain Text (`#F5F0E6`), Sapphire Cobalt Primary (`#3B82F6`), Teal Cyan Voice Pulse (`#22D3EE`), Champagne Amber Thinking/Shift (`#D9A441`), Emerald Speaking (`#10B981`).

---

## 📋 Metadata

| Property | Value |
| :--- | :--- |
| **Surface Architecture** | 1. **Dynamic Island Pill** (always-on-top mini orb) · 2. **Spatial Command Deck** (expandable desktop/web HUD) · 3. **System Tray Menu** |
| **Contrast Standard** | WCAG 2.2 AA (`>= 4.5:1` normal text, `>= 3:1` large text & UI indicators) |
| **Motion Ethos** | Crisp cubic-bezier (`200–350ms`), 60fps canvas waveform, respects `prefers-reduced-motion` |
| **Last Updated** | `2026-11-11` |

---

## 🧭 Table of Contents

- [1. Semantic Design Tokens](#1--semantic-design-tokens)
- [2. Typography & Spacing Scale](#2--typography--spacing-scale)
- [3. Component Inventory & States](#3--component-inventory--states)
- [4. Screen & Surface Specifications](#4--screen--surface-specifications)
- [5. Accessibility & Visual QA Checklist](#5--accessibility--visual-qa-checklist)

---

## 1. 🎨 Semantic Design Tokens

```css
:root {
  /* Surfaces */
  --bg-canvas: #0A0D14;
  --bg-surface: #111622;
  --bg-surface-elevated: #171E2E;
  --bg-glass: rgba(17, 22, 34, 0.82);

  /* Borders & Dividers */
  --border-subtle: rgba(245, 240, 230, 0.10);
  --border-strong: rgba(245, 240, 230, 0.22);

  /* Typography */
  --text-primary: #F5F0E6;     /* Warm porcelain (~15.8:1 on #0A0D14) */
  --text-muted: #A4AEBF;       /* Slate silver (~7.3:1 on #0A0D14) */
  --text-subtle: #6E788C;

  /* Brand & Jewel Status Accents */
  --accent-primary: #3B82F6;   /* Sapphire Cobalt */
  --accent-primary-hover: #2563EB;
  --accent-cyan: #22D3EE;      /* Listening / Waveform */
  --accent-gold: #D9A441;      /* Processing / Model Shift Notice */
  --accent-emerald: #10B981;   /* Speaking / Healthy Model */
  --accent-crimson: #EF4444;   /* Cooldown / Exhausted / Tier-3 Danger */
}
```

> [!TIP]
> **Status Dual-Coding Rule:** Never communicate model health (`Healthy` / `Cooldown` / `Exhausted`) or Koda state (`Idle` / `Listening` / `Thinking` / `Speaking`) by color alone — always pair color with an explicit text label and icon/shape.

---

## 2. 🔤 Typography & Spacing Scale

| Role | Font Family | Size / Weight | Line Height | Usage |
| :--- | :--- | :--- | :---: | :--- |
| **Brand / Panel Title** | `Syne`, sans-serif | `20px–28px` / `700` | `1.15` | KODA header, Command Deck section headers |
| **Section Heading** | `Plus Jakarta Sans`, sans-serif | `15px–17px` / `600` | `1.3` | Card titles, Modal headers, Approval prompts |
| **Body / Chat Copy** | `Plus Jakarta Sans`, sans-serif | `14px` / `400–500` | `1.55` | Assistant responses, memory cards, brief items |
| **Telemetry / Mono** | `JetBrains Mono`, monospace | `12px` / `500` | `1.45` | Active model ID, token counts, latency `ms`, MCP trace |

- **Spacing Grid:** `4px` base unit (`8px`, `12px`, `16px`, `24px` card padding); `14px–18px` outer HUD radius, `999px` pill radius for Dynamic Island & status chips.

---

## 3. 🧩 Component Inventory & States

| Component | Variants / States | Interaction Behavior |
| :--- | :--- | :--- |
| **Dynamic Island Pill** | `idle` · `listening` · `thinking` · `shifting` · `speaking` · `confirm_needed` | Anchored top-center (`48px` collapsed icon pill -> `260px` active status -> `340px` transient toast on model shift or HITL prompt). Click toggles Command Deck. |
| **Acoustic Core Orb** | Animated 60fps Canvas ring reactive to mic RMS & TTS amplitude | Cyan ripples on mic input, warm gold orbit while reasoning, emerald harmonic wave while speaking. |
| **Free-Model Router Matrix** | `HEALTHY` · `SOFT_SHIFTED` · `COOLDOWN (Xs)` · `DISABLED` | Displays all 12 OpenCode free models grouped by Lane (`Fast`, `Vision`, `1M Deep`, `Audio/Video`), live latency `ms`, token count, and 1-click pin/override. |
| **HITL Approval Card** | `Pending` · `Approved` · `Denied` · `Expired` | High-contrast amber-bordered card summarizing exact command/file/message target + `[Approve]` / `[Deny]` buttons + voice `"Confirm"` support. |
| **Omnibar Command Input** | Default · Focus (`Ctrl+Space`) · Attached Screen/File | Single prompt bar supporting text, `/commands`, image/PDF drop, mic toggle, and instant screen-capture attach button. |

---

## 4. 🖥️ Screen & Surface Specifications

### Primary View: Spatial Command Deck (`localhost` Web HUD + Native Desktop Shell)
1. **Top Bar (Compact 56px):** KODA wordmark + live `opencode serve` connection badge + active Lane & Model pill (e.g., `Lane A · nemotron-3.5-lightning-free · $0.00`) + Mic / Screen-Capture / Settings triggers.
2. **Main Split Canvas (Responsive 2-column on desktop `>= 1024px`, tabbed drawer on compact `< 1024px`):**
   - **Left/Center Stream (62%):** Conversational Timeline + Inline Rich Cards (Live Tool Execution steps, Model Failover notice badge, HITL Confirmation cards, Screen Vision preview thumbnails) anchored above the Omnibar.
   - **Right Telemetry Rail (38%):** Tabbed inspector with 4 clean panels:
     - **Router:** Live health & quota grid of all 12 free models + shift history log.
     - **Tools & MCP:** Connected MCP servers (`Windows UIA`, `Playwright`, `Filesystem`, `IoT/Webhook`), live action feed.
     - **Memory & Timeline:** Stored user facts, episodic search, Screenpipe-lite context snippets, 1-click delete/edit.
     - **Proactive & Macros:** Scheduled briefings, timers, saved multi-step routines (`Morning Dev Setup`, `Study Mode`).

---

## 5. ✅ Accessibility & Visual QA Checklist

- [ ] Every interactive button/toggle has keyboard focus ring (`2px solid #3B82F6`, `2px` offset) and `aria-label`.
- [ ] `Escape` closes drawers/modals; `Ctrl+Space` focuses Omnibar or triggers Push-to-Talk.
- [ ] Verify rendered DOM in headless Chromium at `1440×900` and `430×900` (compact pane) with `0` console/page/HTTP errors.
- [ ] Confirm contrast across text, muted badges, and model cooldown chips.
