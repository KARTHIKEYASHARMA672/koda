"""Supervised lifecycle manager for the local `opencode.EXE serve` daemon."""

from __future__ import annotations

import asyncio
import atexit
import os
import subprocess
import time
from pathlib import Path

from koda.opencode.client import OpenCodeClient, OpenCodeError


class OpenCodeSupervisor:
    """Starts, authenticates, monitors, and cleanly shuts down `opencode.EXE serve`."""

    def __init__(
        self,
        *,
        exe_path: Path,
        host: str = "127.0.0.1",
        port: int = 4096,
        username: str = "opencode",
        password: str = "",
        log_path: Path | None = None,
    ) -> None:
        self.exe_path = exe_path
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.log_path = log_path
        self._process: subprocess.Popen[bytes] | None = None
        self._log_file = None
        atexit.register(self.stop)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def build_command(self) -> list[str]:
        return [
            str(self.exe_path),
            "serve",
            "--hostname",
            self.host,
            "--port",
            str(self.port),
        ]

    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["OPENCODE_SERVER_USERNAME"] = self.username
        env["OPENCODE_SERVER_PASSWORD"] = self.password
        return env

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    async def is_ready(self, client: OpenCodeClient) -> bool:
        """Verify both `/api/info` and `/api/model` (plugins activated) respond cleanly."""
        try:
            await client.health()
            models = await client.list_models()
            return len(models) > 0
        except OpenCodeError:
            return False

    async def start(self, *, ready_timeout_sec: float = 30.0) -> None:
        """Start `opencode.EXE serve` if needed and wait until `/api/info` and `/api/model` succeed."""
        client = OpenCodeClient(
            base_url=self.base_url,
            username=self.username,
            password=self.password,
            timeout_sec=3.0,
        )
        try:
            # Reuse an already-running managed instance on the same port if healthy.
            if await self.is_ready(client):
                return

            if not self.exe_path.exists():
                raise FileNotFoundError(f"OpenCode executable not found at {self.exe_path}")

            stdout_target = subprocess.DEVNULL
            if self.log_path is not None:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                self._log_file = open(self.log_path, "ab")
                stdout_target = self._log_file

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen(
                self.build_command(),
                env=self.build_env(),
                stdout=stdout_target,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )

            deadline = time.monotonic() + ready_timeout_sec
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    raise RuntimeError(f"opencode.EXE serve exited early with code {self._process.returncode}")
                if await self.is_ready(client):
                    return
                await asyncio.sleep(0.3)

            self.stop()
            raise TimeoutError(f"opencode.EXE serve did not become ready within {ready_timeout_sec}s")
        finally:
            await client.close()

    def stop(self) -> None:
        """Terminate spawned `opencode.EXE serve` child process cleanly."""
        proc = self._process
        self._process = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        if self._log_file is not None:
            try:
                self._log_file.close()
            finally:
                self._log_file = None
