from __future__ import annotations

import asyncio
from pathlib import Path

from koda.memory.store import MemoryStore
from koda.safety.gate import RiskTier, SafetyGate


def test_safety_gate_enforces_path_containment_and_secrets_deny(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    env_file = workspace / ".env"
    env_file.write_text("API_KEY=secret", encoding="utf-8")
    safe_file = workspace / "notes.txt"
    safe_file.write_text("hello", encoding="utf-8")

    gate = SafetyGate(allowed_roots=[workspace])

    # Read inside allowed workspace -> AUTO
    d_read = gate.evaluate("read_file", {"path": str(safe_file)})
    assert d_read.tier == RiskTier.AUTO
    assert d_read.allowed is True

    # Read .env inside workspace -> DENY
    d_env = gate.evaluate("read_file", {"path": str(env_file)})
    assert d_env.tier == RiskTier.DENY
    assert d_env.blocked is True

    # Traversal outside workspace -> DENY
    d_trav = gate.evaluate("read_file", {"path": str(workspace / ".." / "outside.txt")})
    assert d_trav.tier == RiskTier.DENY
    assert d_trav.blocked is True

    # Windows system path -> DENY
    d_win = gate.evaluate("write_file", {"path": r"C:\Windows\System32\drivers\etc\hosts"})
    assert d_win.tier == RiskTier.DENY
    assert d_win.blocked is True


def test_safety_gate_classifies_notify_confirm_and_destructive_shell(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "draft.txt"
    target.write_text("existing", encoding="utf-8")

    gate = SafetyGate(allowed_roots=[workspace])

    assert gate.evaluate("open_app", {"name": "notepad"}).tier == RiskTier.NOTIFY
    assert gate.evaluate("delete_file", {"path": str(target)}).tier == RiskTier.CONFIRM
    assert gate.evaluate("write_file", {"path": str(target), "content": "overwrite"}).tier == RiskTier.CONFIRM
    assert gate.evaluate("run_shell", {"command": "git status"}).tier == RiskTier.CONFIRM
    assert gate.evaluate("run_shell", {"command": "rm -rf /"}).tier == RiskTier.DENY
    assert gate.evaluate("run_shell", {"command": "powershell -EncodedCommand ZQBjAGgAbwA="}).tier == RiskTier.DENY


def test_safety_gate_async_hitl_approval_flow(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    memory = MemoryStore(db_path=tmp_path / "koda.db")
    gate = SafetyGate(allowed_roots=[workspace], memory=memory)

    async def run() -> bool:
        pending_task = asyncio.create_task(
            gate.await_approval(
                approval_id="apr_1",
                tool_name="run_shell",
                args={"command": "pytest"},
                summary="Run pytest in workspace",
                timeout_sec=5.0,
            )
        )
        await asyncio.sleep(0.05)
        pending = memory.list_approvals(status="pending")
        assert [p.id for p in pending] == ["apr_1"]

        resolved = gate.resolve_approval("apr_1", approved=True)
        assert resolved is True
        return await pending_task

    assert asyncio.run(run()) is True
    assert memory.list_approvals(status="pending") == []
