"""Workspace-contained filesystem, git, and gated shell tools."""

from __future__ import annotations

import asyncio
import fnmatch
import subprocess
from pathlib import Path
from typing import Any

from koda.safety.gate import SafetyGate


class WorkspaceFileTools:
    """Executes read, write, search, git, and workspace shell tools under canonical path rules."""

    def __init__(self, *, allowed_roots: list[Path], safety_gate: SafetyGate) -> None:
        self.allowed_roots = [p.expanduser().resolve() for p in allowed_roots] or [Path(".").resolve()]
        self.safety_gate = safety_gate

    def _guard_path(self, tool_name: str, raw_path: str) -> tuple[Path | None, dict[str, Any] | None]:
        decision = self.safety_gate.evaluate(tool_name, {"path": raw_path})
        if decision.blocked:
            return None, {"ok": False, "blocked": True, "reason": decision.reason}
        return Path(raw_path).expanduser().resolve(), None

    async def read_file(self, path: str, *, start_line: int = 1, max_lines: int = 200) -> dict[str, Any]:
        target, blocked = self._guard_path("read_file", path)
        if blocked is not None:
            return blocked
        assert target is not None
        if not target.exists() or not target.is_file():
            return {"ok": False, "error": f"File not found: {target}"}

        def _read() -> dict[str, Any]:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            start = max(0, start_line - 1)
            chunk = lines[start : start + max_lines]
            return {
                "ok": True,
                "path": str(target),
                "total_lines": len(lines),
                "start_line": start + 1,
                "content": "\n".join(chunk),
            }

        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        target, blocked = self._guard_path("write_file", path)
        if blocked is not None:
            return blocked
        assert target is not None

        def _write() -> dict[str, Any]:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"ok": True, "path": str(target), "bytes": len(content.encode("utf-8"))}

        return await asyncio.to_thread(_write)

    async def delete_file(self, path: str) -> dict[str, Any]:
        target, blocked = self._guard_path("delete_file", path)
        if blocked is not None:
            return blocked
        assert target is not None
        if not target.exists() or not target.is_file():
            return {"ok": False, "error": f"File not found: {target}"}
        await asyncio.to_thread(target.unlink)
        return {"ok": True, "deleted": str(target)}

    async def list_dir(self, path: str = ".") -> dict[str, Any]:
        target_raw = path if path != "." else str(self.allowed_roots[0])
        target, blocked = self._guard_path("list_dir", target_raw)
        if blocked is not None:
            return blocked
        assert target is not None
        if not target.is_dir():
            return {"ok": False, "error": f"Directory not found: {target}"}

        def _list() -> list[dict[str, Any]]:
            items = []
            for entry in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:100]:
                items.append({"name": entry.name, "type": "dir" if entry.is_dir() else "file"})
            return items

        entries = await asyncio.to_thread(_list)
        return {"ok": True, "path": str(target), "entries": entries}

    async def search_files(self, query: str, path: str = ".") -> dict[str, Any]:
        target_raw = path if path != "." else str(self.allowed_roots[0])
        target, blocked = self._guard_path("search_files", target_raw)
        if blocked is not None:
            return blocked
        assert target is not None

        def _search() -> list[dict[str, Any]]:
            matches: list[dict[str, Any]] = []
            needle = query.lower()
            for root_file in target.rglob("*"):
                if not root_file.is_file():
                    continue
                if any(part in {".git", "node_modules", "__pycache__", ".venv"} for part in root_file.parts):
                    continue
                if fnmatch.fnmatch(root_file.name, ".env*"):
                    continue
                try:
                    text = root_file.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for idx, line in enumerate(text.splitlines(), start=1):
                    if needle in line.lower():
                        matches.append({"file": str(root_file), "line": idx, "text": line.strip()[:180]})
                        if len(matches) >= 30:
                            return matches
            return matches

        found = await asyncio.to_thread(_search)
        return {"ok": True, "query": query, "matches": found}

    async def _run_proc(self, cmd: list[str] | str, cwd: Path, *, shell: bool = False) -> dict[str, Any]:
        def _exec() -> dict[str, Any]:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                shell=shell,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[:4000],
                "stderr": proc.stderr[:2000],
            }

        try:
            return await asyncio.to_thread(_exec)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Command timed out after 15s"}

    async def git_status(self, path: str = ".") -> dict[str, Any]:
        target_raw = path if path != "." else str(self.allowed_roots[0])
        target, blocked = self._guard_path("list_dir", target_raw)
        if blocked is not None:
            return blocked
        assert target is not None
        return await self._run_proc(["git", "status", "--short"], target)

    async def git_diff(self, path: str = ".") -> dict[str, Any]:
        target_raw = path if path != "." else str(self.allowed_roots[0])
        target, blocked = self._guard_path("list_dir", target_raw)
        if blocked is not None:
            return blocked
        assert target is not None
        return await self._run_proc(["git", "diff", "--stat"], target)

    async def run_shell(self, command: str, cwd: str = ".") -> dict[str, Any]:
        decision = self.safety_gate.evaluate("run_shell", {"command": command})
        if decision.blocked:
            return {"ok": False, "blocked": True, "reason": decision.reason}
        work_dir_raw = cwd if cwd != "." else str(self.allowed_roots[0])
        work_dir = Path(work_dir_raw).expanduser().resolve()
        if not self.safety_gate.is_within_allowed_roots(work_dir):
            return {"ok": False, "blocked": True, "reason": "Working directory outside allowed roots"}
        return await self._run_proc(command, work_dir, shell=True)
