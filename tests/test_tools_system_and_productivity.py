from __future__ import annotations

import asyncio
from pathlib import Path

from koda.memory.store import MemoryStore
from koda.safety.gate import SafetyGate
from koda.tools.productivity import ProductivityTools
from koda.tools.registry import ToolRegistry
from koda.tools.system_os import SystemOSController


def test_system_os_metrics_and_active_window() -> None:
    os_ctrl = SystemOSController()

    async def run() -> None:
        metrics = await os_ctrl.system_metrics()
        assert metrics["ok"] is True
        assert metrics["ram_total_gb"] > 0
        assert 0.0 <= metrics["cpu_percent"] <= 100.0

        wins = await os_ctrl.list_windows()
        assert wins["ok"] is True
        assert isinstance(wins["windows"], list)

        # Reject non-allowlisted executable
        bad = await os_ctrl.open_app("evil_unknown_binary_xyz")
        assert bad["ok"] is False

    asyncio.run(run())


def test_productivity_notes_sanitizes_traversal_and_writes_notion_markdown(tmp_path: Path) -> None:
    memory = MemoryStore(db_path=tmp_path / "koda.db")
    notes_dir = tmp_path / "notes"
    prod = ProductivityTools(memory=memory, notes_dir=notes_dir)

    async def run() -> None:
        res = await prod.save_note("../../escape_attempt", "Study plan details", tags=["ai", "koda"])
        assert res["ok"] is True
        saved_path = Path(res["path"]).resolve()
        # Verify note stayed inside notes_dir (no path traversal!)
        assert saved_path.is_relative_to(notes_dir.resolve())
        text = saved_path.read_text(encoding="utf-8")
        assert "| **Tags**" in text
        assert "Study plan details" in text

        read_back = await prod.read_note(saved_path.stem)
        assert read_back["ok"] is True
        assert "Study plan details" in read_back["content"]

        memory.upsert_fact("preference", "editor", "VS Code")
        mem_res = await prod.memory_search("VS Code")
        assert mem_res["ok"] is True
        assert len(mem_res["facts"]) == 1

    asyncio.run(run())


def test_tool_registry_blocks_deny_and_formats_catalog(tmp_path: Path) -> None:
    gate = SafetyGate(allowed_roots=[tmp_path])
    reg = ToolRegistry(safety_gate=gate)

    async def dummy_shell(command: str = "") -> dict:
        return {"ok": True, "command": command}

    reg.register(
        name="run_shell",
        description="Execute a shell command inside workspace",
        args_schema={"command": "str"},
        handler=dummy_shell,
    )

    assert "run_shell" in reg.catalog_prompt()

    async def run() -> None:
        denied = await reg.dispatch("run_shell", {"command": "rm -rf /"}, approved=True)
        assert denied["ok"] is False
        assert denied["blocked"] is True

    asyncio.run(run())
