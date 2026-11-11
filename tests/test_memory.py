from __future__ import annotations

from pathlib import Path

from koda.memory.extractor import extract_candidate_facts
from koda.memory.store import MemoryStore


def test_memory_store_facts_episodes_and_fts_search(tmp_path: Path) -> None:
    db_path = tmp_path / "koda.db"
    store = MemoryStore(db_path=db_path)

    f1 = store.upsert_fact("identity", "preferred_name", "Karthikeya")
    f2 = store.upsert_fact("preference", "theme", "Dark obsidian spatial UI")
    assert f1.id > 0
    assert len(store.list_facts()) == 2

    hits = store.search_facts("obsidian")
    assert [h.id for h in hits] == [f2.id]

    store.record_episode("conv_1", "user", "Check GPU utilization on RTX 3050", model_id="iceman-free", lane="fast")
    store.record_episode("conv_1", "assistant", "GPU is idle at 2 percent.", model_id="iceman-free", lane="fast")

    turns = store.recent_turns("conv_1", limit=10)
    assert [t.role for t in turns] == ["user", "assistant"]

    ep_hits = store.search_episodes("RTX 3050")
    assert len(ep_hits) == 1
    assert "RTX 3050" in ep_hits[0].content

    assert store.delete_fact(f2.id) is True
    assert store.search_facts("obsidian") == []

    # Verify Windows file handle release cleanly
    db_path.unlink()
    assert not db_path.exists()


def test_clipboard_and_routines_persistence_skips_secrets(tmp_path: Path) -> None:
    store = MemoryStore(db_path=tmp_path / "koda.db")

    assert store.save_clipboard("sk-" + "live-supersecret1234567890", source_app="notepad.exe") is None
    assert store.save_clipboard("ghp_" + "1234567890abcdef1234567890abcdef", source_app="terminal") is None

    saved = store.save_clipboard("https://localhost:8765/health", source_app="chrome.exe")
    assert saved is not None
    # Deduplicated identical consecutive clip
    assert store.save_clipboard("https://localhost:8765/health", source_app="chrome.exe") is None
    assert len(store.list_clipboard()) == 1

    routine = store.upsert_routine(
        name="Morning Dev Setup",
        trigger_phrase="start morning setup",
        steps=[{"tool": "system_metrics", "args": {}}],
        cron_expr="0 9 * * 1-5",
    )
    assert routine.name == "Morning Dev Setup"
    assert len(store.list_routines()) == 1


def test_extract_candidate_facts_ignores_questions() -> None:
    facts = extract_candidate_facts("My name is Karthikeya and I prefer concise bullet points.")
    assert ("identity", "preferred_name", "Karthikeya") in facts
    assert any(k == "preference" for _, k, _ in facts)

    assert extract_candidate_facts("What is my name?") == []
