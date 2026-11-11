"""Smart clipboard history, Notion-style Markdown notes, memory recall, and workflow routines."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from koda.memory.store import MemoryStore


class ProductivityTools:
    """Handles Notion-style Markdown notes, clipboard intelligence, and saved routines."""

    def __init__(
        self,
        *,
        memory: MemoryStore,
        notes_dir: Path | None = None,
        routine_step_runner: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        self.memory = memory
        self.notes_dir = (notes_dir or Path("data/notes")).expanduser().resolve()
        self.routine_step_runner = routine_step_runner

    def _safe_note_path(self, title: str) -> Path:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(title).name).strip("._-")
        if not slug:
            slug = f"note_{int(time.time())}"
        if not slug.lower().endswith(".md"):
            slug = f"{slug}.md"
        candidate = (self.notes_dir / slug).resolve()
        if not candidate.is_relative_to(self.notes_dir):
            candidate = (self.notes_dir / f"note_{int(time.time())}.md").resolve()
        return candidate

    async def save_note(self, title: str, body: str, *, tags: list[str] | None = None) -> dict[str, Any]:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        target = self._safe_note_path(title)
        tag_str = ", ".join(tags or ["koda"])
        clean_title = Path(title).name or target.stem
        markdown = (
            f"# 📝 {clean_title}\n\n"
            "> [!NOTE]\n"
            "> Captured by **Koda Personal AI OS**.\n\n"
            "---\n\n"
            "| Property | Value |\n"
            "| :--- | :--- |\n"
            f"| **Tags** | `{tag_str}` |\n"
            f"| **Saved At** | `{time.strftime('%Y-%m-%d %H:%M:%S')}` |\n\n"
            "---\n\n"
            f"{body.strip()}\n"
        )
        await asyncio.to_thread(target.write_text, markdown, encoding="utf-8")
        return {"ok": True, "path": str(target), "title": clean_title}

    async def read_note(self, title: str) -> dict[str, Any]:
        target = self._safe_note_path(title)
        if not target.exists():
            return {"ok": False, "error": f"Note `{target.name}` not found"}
        text = await asyncio.to_thread(target.read_text, encoding="utf-8")
        return {"ok": True, "path": str(target), "content": text}

    async def clipboard_save_current(self) -> dict[str, Any]:
        def _grab_clip() -> str:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            try:
                return str(root.clipboard_get())
            except tk.TclError:
                return ""
            finally:
                root.destroy()

        try:
            clip = await asyncio.to_thread(_grab_clip)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        rec = self.memory.save_clipboard(clip, source_app="clipboard")
        return {"ok": True, "saved": rec is not None, "preview": clip[:120] if rec else ""}

    async def clipboard_list(self, query: str = "") -> dict[str, Any]:
        items = self.memory.list_clipboard(query=query, limit=15)
        return {"ok": True, "items": [i.model_dump() for i in items]}

    async def memory_search(self, query: str) -> dict[str, Any]:
        return {
            "ok": True,
            "facts": [f.model_dump() for f in self.memory.search_facts(query)],
            "episodes": [e.model_dump() for e in self.memory.search_episodes(query)],
            "recall": [r.model_dump() for r in self.memory.search_recall(query=query)],
        }

    async def run_routine(self, name: str) -> dict[str, Any]:
        routine = self.memory.get_routine(name)
        if routine is None:
            return {"ok": False, "error": f"Routine `{name}` not found"}
        if self.routine_step_runner is None:
            return {"ok": False, "error": "Routine step runner not initialized"}
        results = []
        for step in routine.steps:
            tool = str(step.get("tool", ""))
            args = dict(step.get("args", {}) or {})
            out = await self.routine_step_runner(tool, args)
            results.append({"tool": tool, "result": out})
        self.memory.mark_routine_run(routine.name)
        return {"ok": True, "routine": routine.name, "steps": results}
