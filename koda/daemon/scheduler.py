"""Proactive timers, morning briefing assembly, and privacy-filtered Screenpipe-lite recall."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from koda.memory.store import MemoryStore, RecallRecord

logger = logging.getLogger(__name__)

_PRIVACY_KEYWORDS = (
    "incognito",
    "inprivate",
    "private browsing",
    "1password",
    "bitwarden",
    "keepass",
    "lastpass",
    "password",
    "banking",
    ".env",
    "credential",
    "secret",
    "authenticator",
)


def is_privacy_sensitive_window(title_or_app: str) -> bool:
    """Block Screenpipe-lite recall capture on sensitive windows and credential managers."""
    lower = title_or_app.lower()
    return any(kw in lower for kw in _PRIVACY_KEYWORDS)


class MorningBriefingBuilder:
    """Composes a structured prompt summarizing user facts, routines, recall, and live telemetry."""

    def __init__(self, *, memory: MemoryStore) -> None:
        self.memory = memory

    def build_prompt_context(self, *, metrics: dict[str, Any] | None = None) -> str:
        facts = self.memory.list_facts(limit=10)
        routines = [r for r in self.memory.list_routines() if r.enabled]
        recent_recall = self.memory.search_recall(limit=5)

        lines = [
            "Generate a crisp, structured Morning Briefing for the user.",
            f"Current time: {time.strftime('%Y-%m-%d %H:%M')}",
        ]
        if metrics:
            lines.append(
                "System health: "
                f"CPU {metrics.get('cpu_percent', '?')}%, "
                f"RAM {metrics.get('ram_percent', '?')}%, "
                f"Disk Free {metrics.get('disk_free_gb', '?')} GB"
            )
        if facts:
            lines.append("User facts/preferences: " + "; ".join(f"{f.key}={f.value}" for f in facts))
        if routines:
            lines.append("Configured routines: " + ", ".join(r.name for r in routines))
        if recent_recall:
            lines.append(
                "Recent focus windows: "
                + "; ".join(f"{r.app_name}: {r.window_title[:60]}" for r in recent_recall)
            )
        return "\n".join(lines)


class ProactiveDaemon:
    """Manages async timers, opt-in local window recall, and background maintenance."""

    def __init__(
        self,
        *,
        memory: MemoryStore,
        recall_enabled: bool = False,
        on_notification: Callable[[str], Any] | None = None,
    ) -> None:
        self.memory = memory
        self.recall_enabled = recall_enabled
        self.on_notification = on_notification
        self._tasks: set[asyncio.Task[None]] = set()
        self._last_window_sig = ""

    def capture_recall_sample(self, app_name: str, window_title: str) -> RecallRecord | None:
        """Record sanitized active window context only when opt-in recall is enabled and safe."""
        if not self.recall_enabled:
            return None
        combined = f"{app_name} {window_title}".strip()
        if not combined or is_privacy_sensitive_window(combined):
            return None
        if combined == self._last_window_sig:
            return None
        self._last_window_sig = combined
        clean_title = re.sub(r"\s+", " ", window_title).strip()[:180]
        return self.memory.record_recall(
            app_name=app_name[:80],
            window_title=clean_title,
            summary_text=f"Active in {app_name}: {clean_title}",
        )

    def schedule_timer(self, label: str, *, delay_sec: float) -> asyncio.Task[None]:
        async def _timer_job() -> None:
            try:
                await asyncio.sleep(max(0.0, delay_sec))
                if self.on_notification is not None:
                    self.on_notification(f"Timer complete: {label}")
            except asyncio.CancelledError:
                return

        task = asyncio.create_task(_timer_job())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
