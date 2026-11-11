from __future__ import annotations

import asyncio
from pathlib import Path

from koda.safety.gate import SafetyGate
from koda.tools.filesystem import WorkspaceFileTools


def test_workspace_file_tools_read_write_search_git_and_containment(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("top_secret", encoding="utf-8")
    env_file = root / ".env"
    env_file.write_text("TOKEN=123", encoding="utf-8")

    gate = SafetyGate(allowed_roots=[root])
    fs = WorkspaceFileTools(allowed_roots=[root], safety_gate=gate)

    async def run() -> None:
        w = await fs.write_file(str(root / "hello.txt"), "alpha\nbeta\ngamma")
        assert w["ok"] is True

        r = await fs.read_file(str(root / "hello.txt"))
        assert r["ok"] is True
        assert "beta" in r["content"]

        s = await fs.search_files("beta", str(root))
        assert s["ok"] is True
        assert len(s["matches"]) == 1

        # Path containment blocks outside reads & .env reads even via tool layer directly
        r_out = await fs.read_file(str(outside))
        assert r_out["ok"] is False
        assert r_out["blocked"] is True

        r_env = await fs.read_file(str(env_file))
        assert r_env["ok"] is False
        assert r_env["blocked"] is True

        # Safe workspace shell command works
        sh = await fs.run_shell("python --version", cwd=str(root))
        assert sh["ok"] is True
        assert "Python 3." in sh["stdout"] or "Python 3." in sh["stderr"]

    asyncio.run(run())
