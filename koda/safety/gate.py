"""Four-tier permission gate (`AUTO`, `NOTIFY`, `CONFIRM`, `DENY`) with path containment."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from koda.memory.store import ApprovalRecord, MemoryStore


class RiskTier(StrEnum):
    AUTO = "AUTO"
    NOTIFY = "NOTIFY"
    CONFIRM = "CONFIRM"
    DENY = "DENY"


class PermissionDecision(BaseModel):
    tier: RiskTier
    allowed: bool
    requires_confirmation: bool
    blocked: bool
    summary: str
    reason: str


AUTO_TOOLS = frozenset(
    {
        "read_file",
        "list_dir",
        "search_files",
        "git_status",
        "git_diff",
        "system_metrics",
        "active_window",
        "list_windows",
        "memory_search",
        "clipboard_list",
        "web_fetch",
        "capture_screen",
        "read_note",
    }
)

NOTIFY_TOOLS = frozenset(
    {
        "open_app",
        "focus_window",
        "set_volume",
        "media_control",
        "browser_open",
        "browser_search",
        "browser_youtube",
        "save_note",
        "type_text",
        "run_routine",
    }
)

CONFIRM_TOOLS = frozenset(
    {
        "write_file",
        "delete_file",
        "run_shell",
        "kill_process",
        "send_telegram",
        "ha_call_service",
        "trigger_webhook",
    }
)

_SENSITIVE_FILENAMES = frozenset(
    {
        ".env",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
        "secrets.json",
        "login data",
        "cookies",
    }
)

_PROTECTED_SYSTEM_PREFIXES = (
    r"c:\windows",
    r"c:\program files",
    r"c:\program files (x86)",
    r"c:\programdata\microsoft",
)

_DANGEROUS_SHELL_PATTERNS = (
    re.compile(r"\brm\s+-[a-z]*rf\s+[/\\]", re.IGNORECASE),
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    re.compile(r"\bdel\s+/[sqf]+\s+c:\\", re.IGNORECASE),
    re.compile(r"\breg\s+(add|delete)\b", re.IGNORECASE),
    re.compile(r"powershell[^\n]*-enc(?:odedcommand)?\b", re.IGNORECASE),
    re.compile(r"\b(iex|invoke-expression)\b", re.IGNORECASE),
    re.compile(r"\bshutdown\s+/[sr]", re.IGNORECASE),
)


def is_sensitive_path(path: Path) -> bool:
    """Identify secret files, private keys, browser credentials, or protected OS directories."""
    resolved = path.expanduser().resolve()
    name_lower = resolved.name.lower()
    full_lower = str(resolved).lower()

    if name_lower != ".env.example" and (name_lower == ".env" or name_lower.startswith(".env.")):
        return True
    if name_lower in _SENSITIVE_FILENAMES:
        return True
    if resolved.suffix.lower() in {".pem", ".key", ".pfx", ".p12"}:
        return True
    if full_lower.endswith(r"\.git\config") or full_lower.endswith("/.git/config"):
        return True
    if any(full_lower.startswith(prefix) for prefix in _PROTECTED_SYSTEM_PREFIXES):
        return True
    return False


class SafetyGate:
    """Enforces 4-tier tool governance, canonical path checks, and HITL approvals."""

    def __init__(
        self,
        *,
        allowed_roots: list[Path],
        memory: MemoryStore | None = None,
        on_approval_requested: Callable[[ApprovalRecord], Any] | None = None,
    ) -> None:
        self.allowed_roots = [p.expanduser().resolve() for p in allowed_roots] or [Path(".").resolve()]
        self.memory = memory
        self.on_approval_requested = on_approval_requested
        self._waiters: dict[str, asyncio.Future[bool]] = {}

    def default_tier(self, tool_name: str) -> RiskTier:
        """Return static catalog tier without failing empty-arg runtime guards."""
        name = tool_name.strip()
        if name in AUTO_TOOLS:
            return RiskTier.AUTO
        if name in NOTIFY_TOOLS:
            return RiskTier.NOTIFY
        if name in CONFIRM_TOOLS:
            return RiskTier.CONFIRM
        return RiskTier.DENY

    def is_within_allowed_roots(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        for root in self.allowed_roots:
            try:
                if resolved.is_relative_to(root):
                    return True
            except ValueError:
                continue
        return False

    def _validate_path_arg(self, raw_path: Any, *, allow_outside_read: bool = False) -> PermissionDecision | None:
        if not raw_path:
            return PermissionDecision(
                tier=RiskTier.DENY,
                allowed=False,
                requires_confirmation=False,
                blocked=True,
                summary="Missing path argument",
                reason="Tool requires a target path",
            )
        target = Path(str(raw_path)).expanduser().resolve()
        if is_sensitive_path(target):
            return PermissionDecision(
                tier=RiskTier.DENY,
                allowed=False,
                requires_confirmation=False,
                blocked=True,
                summary=f"Blocked access to sensitive path: {target}",
                reason="Protected credential or OS system path",
            )
        if not allow_outside_read and not self.is_within_allowed_roots(target):
            return PermissionDecision(
                tier=RiskTier.DENY,
                allowed=False,
                requires_confirmation=False,
                blocked=True,
                summary=f"Blocked traversal outside workspace: {target}",
                reason="Target path is outside configured KODA_ALLOWED_ROOTS",
            )
        return None

    def evaluate(self, tool_name: str, args: dict[str, Any]) -> PermissionDecision:
        name = tool_name.strip()

        if name == "run_shell":
            cmd = str(args.get("command", "")).strip()
            if not cmd or any(p.search(cmd) for p in _DANGEROUS_SHELL_PATTERNS):
                return PermissionDecision(
                    tier=RiskTier.DENY,
                    allowed=False,
                    requires_confirmation=False,
                    blocked=True,
                    summary=f"Blocked unsafe shell command: {cmd[:120]}",
                    reason="Command matches prohibited destructive or obfuscated pattern",
                )
            return PermissionDecision(
                tier=RiskTier.CONFIRM,
                allowed=False,
                requires_confirmation=True,
                blocked=False,
                summary=f"Execute shell command: `{cmd[:160]}`",
                reason="Shell execution requires user confirmation",
            )

        if name in {"read_file", "list_dir", "search_files"}:
            target = args.get("path", self.allowed_roots[0])
            violation = self._validate_path_arg(target)
            if violation:
                return violation
            return PermissionDecision(
                tier=RiskTier.AUTO,
                allowed=True,
                requires_confirmation=False,
                blocked=False,
                summary=f"{name}: {target}",
                reason="Read-only inspection inside allowed workspace",
            )

        if name in {"write_file", "delete_file"}:
            target_raw = args.get("path")
            violation = self._validate_path_arg(target_raw)
            if violation:
                return violation
            target = Path(str(target_raw)).expanduser().resolve()
            if name == "delete_file" or target.exists():
                return PermissionDecision(
                    tier=RiskTier.CONFIRM,
                    allowed=False,
                    requires_confirmation=True,
                    blocked=False,
                    summary=f"{name}: {target}",
                    reason="Overwriting or deleting an existing file requires confirmation",
                )
            return PermissionDecision(
                tier=RiskTier.NOTIFY,
                allowed=True,
                requires_confirmation=False,
                blocked=False,
                summary=f"Create new file: {target}",
                reason="Creating a new file inside workspace",
            )

        if name == "save_note":
            return PermissionDecision(
                tier=RiskTier.NOTIFY,
                allowed=True,
                requires_confirmation=False,
                blocked=False,
                summary=f"Save Markdown note `{args.get('title', 'note')}`",
                reason="Writing note into Koda notes directory",
            )

        if name in AUTO_TOOLS:
            return PermissionDecision(
                tier=RiskTier.AUTO,
                allowed=True,
                requires_confirmation=False,
                blocked=False,
                summary=f"{name}",
                reason="Safe read-only telemetry or lookup",
            )

        if name in NOTIFY_TOOLS:
            return PermissionDecision(
                tier=RiskTier.NOTIFY,
                allowed=True,
                requires_confirmation=False,
                blocked=False,
                summary=f"{name}({args})",
                reason="Reversible OS/browser action",
            )

        if name in CONFIRM_TOOLS:
            return PermissionDecision(
                tier=RiskTier.CONFIRM,
                allowed=False,
                requires_confirmation=True,
                blocked=False,
                summary=f"{name}({args})",
                reason="External or mutating action requires explicit confirmation",
            )

        return PermissionDecision(
            tier=RiskTier.DENY,
            allowed=False,
            requires_confirmation=False,
            blocked=True,
            summary=f"Unknown tool `{name}`",
            reason="Unregistered tools are denied by default",
        )

    async def await_approval(
        self,
        *,
        approval_id: str,
        tool_name: str,
        args: dict[str, Any],
        summary: str,
        timeout_sec: float = 120.0,
    ) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._waiters[approval_id] = future

        if self.memory is not None:
            record = self.memory.create_approval(
                approval_id=approval_id,
                tool_name=tool_name,
                args_json=json.dumps(args),
                summary=summary,
                tier=RiskTier.CONFIRM.value,
            )
            if self.on_approval_requested is not None:
                self.on_approval_requested(record)

        try:
            approved = await asyncio.wait_for(future, timeout=timeout_sec)
            return bool(approved)
        except TimeoutError:
            if self.memory is not None:
                self.memory.resolve_approval(approval_id, approved=False)
            return False
        finally:
            self._waiters.pop(approval_id, None)

    def resolve_approval(self, approval_id: str, *, approved: bool) -> bool:
        resolved_db = True
        if self.memory is not None:
            rec = self.memory.resolve_approval(approval_id, approved=approved)
            resolved_db = rec is not None
        waiter = self._waiters.get(approval_id)
        if waiter is not None and not waiter.done():
            waiter.set_result(approved)
            return True
        return resolved_db
