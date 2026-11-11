"""Optional `.env`-gated Telegram remote control bridge with strict user ID allowlist."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TelegramBridge:
    """Strictly allowlisted Telegram command and HITL approval bridge."""

    def __init__(
        self,
        *,
        bot_token: str,
        allowed_user_id: str,
        on_prompt: Callable[[str], Awaitable[str]],
        on_approve: Callable[[str, bool], Awaitable[bool]],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.allowed_user_id = allowed_user_id.strip()
        self.on_prompt = on_prompt
        self.on_approve = on_approve
        self.transport = transport

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.allowed_user_id)

    async def handle_update(self, update: Mapping[str, Any]) -> dict[str, Any]:
        message = update.get("message")
        if not isinstance(message, Mapping):
            return {"ok": False, "ignored": True}

        sender = message.get("from")
        sender_id = str(sender.get("id", "")).strip() if isinstance(sender, Mapping) else ""
        if not self.enabled or sender_id != self.allowed_user_id:
            logger.warning("Blocked unauthorized Telegram sender_id=%s", sender_id)
            return {"ok": False, "unauthorized": True}

        text = str(message.get("text", "")).strip()
        if not text:
            return {"ok": False, "error": "Empty message"}

        if text.startswith("/approve "):
            apr_id = text.split(maxsplit=1)[1].strip()
            resolved = await self.on_approve(apr_id, True)
            return {"ok": resolved, "action": "approve", "approval_id": apr_id}

        if text.startswith("/deny "):
            apr_id = text.split(maxsplit=1)[1].strip()
            resolved = await self.on_approve(apr_id, False)
            return {"ok": resolved, "action": "deny", "approval_id": apr_id}

        reply = await self.on_prompt(text)
        return {"ok": True, "reply": reply}

    async def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.transport) as client:
                resp = await client.post(url, json={"chat_id": self.allowed_user_id, "text": text[:4000]})
                return resp.is_success
        except Exception as exc:
            logger.warning("Telegram send_message failed: %s", exc)
            return False
