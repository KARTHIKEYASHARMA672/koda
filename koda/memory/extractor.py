"""Lightweight deterministic fact extraction and rolling summary helpers."""

from __future__ import annotations

import re

_NAME_PATTERN = re.compile(r"\b(?:my name is|call me)\s+([A-Za-z][A-Za-z0-9_-]{1,30})\b", re.IGNORECASE)
_PREFER_PATTERN = re.compile(r"\b(?:i prefer|always use|please remember(?: that)?)\s+([^.!?\n]{3,90})", re.IGNORECASE)


def extract_candidate_facts(user_text: str) -> list[tuple[str, str, str]]:
    """Extract explicit user identity/preference statements without false-positive questions."""
    cleaned = user_text.strip()
    if not cleaned or cleaned.endswith("?"):
        return []

    found: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    name_match = _NAME_PATTERN.search(cleaned)
    if name_match:
        name = name_match.group(1).strip()
        key = ("identity", "preferred_name")
        if key not in seen:
            found.append((key[0], key[1], name))
            seen.add(key)

    for idx, pref_match in enumerate(_PREFER_PATTERN.finditer(cleaned), start=1):
        val = pref_match.group(1).strip(" .,")
        if not val or "?" in val:
            continue
        pref_key = "preference" if idx == 1 else f"preference_{idx}"
        key = ("preference", pref_key)
        if key not in seen:
            found.append((key[0], key[1], val))
            seen.add(key)

    return found


def update_rolling_summary(existing_summary: str, user_text: str, assistant_text: str) -> str:
    """Maintain a compact rolling summary preserving intent across model switches."""
    snippet = f"U: {user_text.strip()[:180]} | A: {assistant_text.strip()[:220]}"
    parts = [p for p in existing_summary.splitlines() if p.strip()]
    parts.append(snippet)
    return "\n".join(parts[-8:])
