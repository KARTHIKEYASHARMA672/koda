from __future__ import annotations

import asyncio
from pathlib import Path

from koda.daemon.scheduler import MorningBriefingBuilder, ProactiveDaemon, is_privacy_sensitive_window
from koda.daemon.telegram_bridge import TelegramBridge
from koda.memory.store import MemoryStore


def test_screen_recall_privacy_filter_and_retention(tmp_path: Path) -> None:
    memory = MemoryStore(db_path=tmp_path / "koda.db")

    assert is_privacy_sensitive_window("Google Chrome - InPrivate") is True
    assert is_privacy_sensitive_window("1Password - Vault") is True
    assert is_privacy_sensitive_window("Visual Studio Code - koda") is False

    daemon = ProactiveDaemon(memory=memory, recall_enabled=True)
    assert daemon.capture_recall_sample("chrome.exe", "Banking Login - Password") is None
    rec = daemon.capture_recall_sample("Code.exe", "ARCHITECTURE.md - Koda")
    assert rec is not None
    assert len(memory.search_recall(query="ARCHITECTURE")) == 1


def test_proactive_briefing_and_timers(tmp_path: Path) -> None:
    memory = MemoryStore(db_path=tmp_path / "koda.db")
    memory.upsert_fact("identity", "preferred_name", "Karthikeya")
    memory.upsert_routine(name="Morning Setup", trigger_phrase="morning", steps=[], cron_expr="09:00")

    fired: list[str] = []
    daemon = ProactiveDaemon(
        memory=memory,
        on_notification=lambda msg: fired.append(msg),
    )

    briefing = MorningBriefingBuilder(memory=memory).build_prompt_context(
        metrics={"cpu_percent": 12.0, "ram_percent": 41.0, "disk_free_gb": 120.5}
    )
    assert "Karthikeya" in briefing
    assert "Morning Setup" in briefing

    async def run() -> None:
        daemon.schedule_timer("Standup Reminder", delay_sec=0.05)
        await asyncio.sleep(0.15)

    asyncio.run(run())
    assert any("Standup Reminder" in msg for msg in fired)


def test_telegram_bridge_enforces_user_allowlist_and_approvals() -> None:
    prompts: list[str] = []
    approvals: list[tuple[str, bool]] = []

    async def fake_prompt(text: str) -> str:
        prompts.append(text)
        return "All systems green."

    async def fake_approve(approval_id: str, approved: bool) -> bool:
        approvals.append((approval_id, approved))
        return True

    bridge = TelegramBridge(
        bot_token="123:TEST",
        allowed_user_id="999001",
        on_prompt=fake_prompt,
        on_approve=fake_approve,
    )

    async def run() -> None:
        # Unauthorized Telegram user must be rejected
        unauth = await bridge.handle_update({"message": {"from": {"id": 111111}, "text": "status"}})
        assert unauth["ok"] is False
        assert unauth["unauthorized"] is True
        assert prompts == []

        ok_msg = await bridge.handle_update({"message": {"from": {"id": 999001}, "text": "status"}})
        assert ok_msg["ok"] is True
        assert ok_msg["reply"] == "All systems green."

        ok_apr = await bridge.handle_update({"message": {"from": {"id": 999001}, "text": "/approve apr_99"}})
        assert ok_apr["ok"] is True
        assert approvals == [("apr_99", True)]

    asyncio.run(run())
