"""Typed runtime settings and zero-cost invariants for Koda."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class KodaSettings(BaseSettings):
    """Application settings loaded from environment variables and optional `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Server & Security
    host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("KODA_HOST", "host"))
    port: int = Field(default=8765, validation_alias=AliasChoices("KODA_PORT", "port"))
    allow_paid_models: bool = Field(
        default=False,
        validation_alias=AliasChoices("KODA_ALLOW_PAID_MODELS", "allow_paid_models"),
    )
    allow_google_free: bool = Field(
        default=False,
        validation_alias=AliasChoices("KODA_ALLOW_GOOGLE_FREE", "allow_google_free"),
    )

    # Storage paths
    data_dir: Path = Field(default=Path("data"), validation_alias=AliasChoices("KODA_DATA_DIR", "data_dir"))
    allowed_roots_raw: str = Field(
        default=".",
        validation_alias=AliasChoices("KODA_ALLOWED_ROOTS", "allowed_roots_raw"),
    )

    # Managed OpenCode Serve settings
    opencode_exe: Path = Field(
        default=Path(r"C:\Users\karth\.opencode\bin\opencode.EXE"),
        validation_alias=AliasChoices("OPENCODE_EXE", "opencode_exe"),
    )
    opencode_serve_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("OPENCODE_SERVE_HOST", "opencode_serve_host"),
    )
    opencode_serve_port: int = Field(
        default=4096,
        validation_alias=AliasChoices("OPENCODE_SERVE_PORT", "opencode_serve_port"),
    )
    opencode_server_username: str = Field(
        default="opencode",
        validation_alias=AliasChoices("OPENCODE_SERVER_USERNAME", "opencode_server_username"),
    )
    opencode_server_password: SecretStr = Field(
        default=SecretStr("koda_local_only"),
        validation_alias=AliasChoices("OPENCODE_SERVER_PASSWORD", "opencode_server_password"),
    )
    opencode_timeout_sec: float = Field(
        default=45.0,
        validation_alias=AliasChoices("KODA_OPENCODE_TIMEOUT_SEC", "opencode_timeout_sec"),
    )

    # Voice settings
    wake_word: str = Field(default="hey_jarvis", validation_alias=AliasChoices("KODA_WAKE_WORD", "wake_word"))
    stt_model: str = Field(default="base.en", validation_alias=AliasChoices("KODA_STT_MODEL", "stt_model"))
    tts_engine: str = Field(default="edge-tts", validation_alias=AliasChoices("KODA_TTS_ENGINE", "tts_engine"))
    tts_voice: str = Field(default="en-GB-RyanNeural", validation_alias=AliasChoices("KODA_TTS_VOICE", "tts_voice"))

    # Optional external integrations
    telegram_bot_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("KODA_TELEGRAM_BOT_TOKEN", "telegram_bot_token"),
    )
    telegram_allowed_user_id: str = Field(
        default="",
        validation_alias=AliasChoices("KODA_TELEGRAM_ALLOWED_USER_ID", "telegram_allowed_user_id"),
    )
    home_assistant_url: str = Field(
        default="",
        validation_alias=AliasChoices("KODA_HOME_ASSISTANT_URL", "home_assistant_url"),
    )
    home_assistant_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("KODA_HOME_ASSISTANT_TOKEN", "home_assistant_token"),
    )
    obsidian_vault_path: str = Field(
        default="",
        validation_alias=AliasChoices("KODA_OBSIDIAN_VAULT_PATH", "obsidian_vault_path"),
    )

    @property
    def opencode_serve_url(self) -> str:
        return f"http://{self.opencode_serve_host}:{self.opencode_serve_port}"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "koda.db"

    @property
    def parsed_allowed_roots(self) -> list[Path]:
        roots: list[Path] = []
        for raw in self.allowed_roots_raw.split(","):
            cleaned = raw.strip()
            if cleaned:
                roots.append(Path(cleaned).expanduser().resolve())
        return roots or [Path(".").resolve()]

    def safe_public_summary(self) -> dict[str, Any]:
        """Return diagnostic configuration metadata with all credentials redacted."""
        return {
            "host": self.host,
            "port": self.port,
            "allow_paid_models": self.allow_paid_models,
            "allow_google_free": self.allow_google_free,
            "opencode_serve_url": self.opencode_serve_url,
            "opencode_exe_exists": self.opencode_exe.exists(),
            "allowed_roots": [str(p) for p in self.parsed_allowed_roots],
            "db_path": str(self.db_path),
            "wake_word": self.wake_word,
            "stt_model": self.stt_model,
            "tts_engine": self.tts_engine,
            "tts_voice": self.tts_voice,
            "telegram_configured": bool(self.telegram_bot_token.get_secret_value().strip()),
            "home_assistant_configured": bool(
                self.home_assistant_url.strip() and self.home_assistant_token.get_secret_value().strip()
            ),
        }
