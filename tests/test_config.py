from __future__ import annotations

from pathlib import Path

from koda.config import KodaSettings


def test_default_settings_enforce_zero_cost_mandate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KODA_ALLOW_PAID_MODELS", raising=False)
    monkeypatch.delenv("KODA_ALLOW_GOOGLE_FREE", raising=False)

    settings = KodaSettings(_env_file=None, data_dir=tmp_path)

    assert settings.allow_paid_models is False
    assert settings.allow_google_free is False
    assert settings.opencode_serve_port == 4096
    assert settings.opencode_serve_url == "http://127.0.0.1:4096"


def test_allowed_roots_parses_comma_separated_paths(monkeypatch, tmp_path: Path) -> None:
    dir_a = tmp_path / "alpha"
    dir_b = tmp_path / "beta"
    dir_a.mkdir()
    dir_b.mkdir()

    monkeypatch.setenv("KODA_ALLOWED_ROOTS", f"{dir_a} , {dir_b}")
    settings = KodaSettings(_env_file=None, data_dir=tmp_path)

    assert settings.parsed_allowed_roots == [dir_a.resolve(), dir_b.resolve()]


def test_redacted_summary_never_leaks_secrets(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "super_secret_pw")
    monkeypatch.setenv("KODA_TELEGRAM_BOT_TOKEN", "123456:SECRET_TOKEN")

    settings = KodaSettings(_env_file=None, data_dir=tmp_path)
    summary = settings.safe_public_summary()

    assert "super_secret_pw" not in str(summary)
    assert "SECRET_TOKEN" not in str(summary)
    assert summary["allow_paid_models"] is False
