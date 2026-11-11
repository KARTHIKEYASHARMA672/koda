"""SQLite-persisted circuit-breaker state and EWMA telemetry per free model."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class CircuitState(StrEnum):
    """Health state of an individual free OpenCode model."""

    HEALTHY = "HEALTHY"
    SOFT_SHIFTED = "SOFT_SHIFTED"
    COOLDOWN = "COOLDOWN"
    HALF_OPEN = "HALF_OPEN"
    DISABLED = "DISABLED"


class ModelHealthRecord(BaseModel):
    """Snapshot of model health and latency telemetry."""

    model_id: str
    state: CircuitState = CircuitState.HEALTHY
    fail_count: int = 0
    cooldown_until: float = 0.0
    ewma_latency_ms: float = 0.0
    total_requests: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    last_error: str = ""
    updated_at: float = 0.0


class RouterShiftRecord(BaseModel):
    """Audit row for an automatic failover model shift."""

    id: int
    from_model: str
    to_model: str
    reason: str
    lane: str
    conversation_id: str
    created_at: float


class RouterTelemetryStore:
    """Thread/restart-safe SQLite store backing Koda's model circuit breakers."""

    def __init__(
        self,
        *,
        db_path: Path,
        clock: Callable[[], float] | None = None,
        base_cooldown_sec: float = 30.0,
        max_cooldown_sec: float = 1800.0,
    ) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or time.time
        self.base_cooldown_sec = base_cooldown_sec
        self.max_cooldown_sec = max_cooldown_sec
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS router_telemetry (
                    model_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    cooldown_until REAL NOT NULL DEFAULT 0.0,
                    ewma_latency_ms REAL NOT NULL DEFAULT 0.0,
                    total_requests INTEGER NOT NULL DEFAULT 0,
                    total_tokens_in INTEGER NOT NULL DEFAULT 0,
                    total_tokens_out INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL DEFAULT 0.0
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS router_shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_model TEXT NOT NULL,
                    to_model TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    conversation_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                """
            )

    def get_state(self, model_id: str) -> ModelHealthRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM router_telemetry WHERE model_id = ?", (model_id,)).fetchone()
        if row is None:
            return ModelHealthRecord(model_id=model_id)
        return ModelHealthRecord(
            model_id=row["model_id"],
            state=CircuitState(row["state"]),
            fail_count=int(row["fail_count"]),
            cooldown_until=float(row["cooldown_until"]),
            ewma_latency_ms=float(row["ewma_latency_ms"]),
            total_requests=int(row["total_requests"]),
            total_tokens_in=int(row["total_tokens_in"]),
            total_tokens_out=int(row["total_tokens_out"]),
            last_error=str(row["last_error"]),
            updated_at=float(row["updated_at"]),
        )

    def all_states(self) -> list[ModelHealthRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM router_telemetry ORDER BY model_id").fetchall()
        return [
            ModelHealthRecord(
                model_id=row["model_id"],
                state=self.effective_state(row["model_id"]),
                fail_count=int(row["fail_count"]),
                cooldown_until=float(row["cooldown_until"]),
                ewma_latency_ms=float(row["ewma_latency_ms"]),
                total_requests=int(row["total_requests"]),
                total_tokens_in=int(row["total_tokens_in"]),
                total_tokens_out=int(row["total_tokens_out"]),
                last_error=str(row["last_error"]),
                updated_at=float(row["updated_at"]),
            )
            for row in rows
        ]

    def effective_state(self, model_id: str) -> CircuitState:
        record = self.get_state(model_id)
        if record.state == CircuitState.COOLDOWN and self._clock() >= record.cooldown_until:
            return CircuitState.HALF_OPEN
        return record.state

    def record_success(
        self,
        model_id: str,
        *,
        latency_ms: float,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> ModelHealthRecord:
        now = self._clock()
        prev = self.get_state(model_id)
        new_ewma = latency_ms if prev.ewma_latency_ms <= 0 else (0.3 * latency_ms + 0.7 * prev.ewma_latency_ms)
        updated = ModelHealthRecord(
            model_id=model_id,
            state=CircuitState.HEALTHY,
            fail_count=0,
            cooldown_until=0.0,
            ewma_latency_ms=new_ewma,
            total_requests=prev.total_requests + 1,
            total_tokens_in=prev.total_tokens_in + tokens_in,
            total_tokens_out=prev.total_tokens_out + tokens_out,
            last_error="",
            updated_at=now,
        )
        self._upsert(updated)
        return updated

    def record_failure(
        self,
        model_id: str,
        *,
        reason: str,
        hard_quota: bool = False,
    ) -> ModelHealthRecord:
        now = self._clock()
        prev = self.get_state(model_id)
        next_fails = prev.fail_count + 1

        if hard_quota or prev.state in (CircuitState.SOFT_SHIFTED, CircuitState.HALF_OPEN, CircuitState.COOLDOWN):
            # Exponential backoff on repeated or quota failures.
            exponent = max(0, next_fails - 2) if not hard_quota else max(0, next_fails - 1)
            cooldown_dur = min(self.base_cooldown_sec * (2**exponent), self.max_cooldown_sec)
            next_state = CircuitState.COOLDOWN
            cooldown_until = now + cooldown_dur
        else:
            next_state = CircuitState.SOFT_SHIFTED
            cooldown_until = 0.0

        updated = ModelHealthRecord(
            model_id=model_id,
            state=next_state,
            fail_count=next_fails,
            cooldown_until=cooldown_until,
            ewma_latency_ms=prev.ewma_latency_ms,
            total_requests=prev.total_requests + 1,
            total_tokens_in=prev.total_tokens_in,
            total_tokens_out=prev.total_tokens_out,
            last_error=reason[:400],
            updated_at=now,
        )
        self._upsert(updated)
        return updated

    def set_disabled(self, model_id: str, disabled: bool) -> ModelHealthRecord:
        now = self._clock()
        prev = self.get_state(model_id)
        next_state = CircuitState.DISABLED if disabled else CircuitState.HEALTHY
        updated = prev.model_copy(
            update={
                "state": next_state,
                "fail_count": 0 if not disabled else prev.fail_count,
                "cooldown_until": 0.0,
                "updated_at": now,
            }
        )
        self._upsert(updated)
        return updated

    def record_shift(
        self,
        *,
        from_model: str,
        to_model: str,
        reason: str,
        lane: str,
        conversation_id: str = "",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO router_shifts (from_model, to_model, reason, lane, conversation_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (from_model, to_model, reason[:400], lane, conversation_id, self._clock()),
            )

    def recent_shifts(self, *, limit: int = 20) -> list[RouterShiftRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM router_shifts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            RouterShiftRecord(
                id=int(r["id"]),
                from_model=r["from_model"],
                to_model=r["to_model"],
                reason=r["reason"],
                lane=r["lane"],
                conversation_id=r["conversation_id"],
                created_at=float(r["created_at"]),
            )
            for r in rows
        ]

    def earliest_retry_after_sec(self, model_ids: list[str]) -> float:
        now = self._clock()
        waits: list[float] = []
        for model_id in model_ids:
            rec = self.get_state(model_id)
            if rec.state == CircuitState.COOLDOWN and rec.cooldown_until > now:
                waits.append(rec.cooldown_until - now)
        return min(waits) if waits else 0.0

    def _upsert(self, rec: ModelHealthRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO router_telemetry (
                    model_id, state, fail_count, cooldown_until, ewma_latency_ms,
                    total_requests, total_tokens_in, total_tokens_out, last_error, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_id) DO UPDATE SET
                    state = excluded.state,
                    fail_count = excluded.fail_count,
                    cooldown_until = excluded.cooldown_until,
                    ewma_latency_ms = excluded.ewma_latency_ms,
                    total_requests = excluded.total_requests,
                    total_tokens_in = excluded.total_tokens_in,
                    total_tokens_out = excluded.total_tokens_out,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    rec.model_id,
                    rec.state.value,
                    rec.fail_count,
                    rec.cooldown_until,
                    rec.ewma_latency_ms,
                    rec.total_requests,
                    rec.total_tokens_in,
                    rec.total_tokens_out,
                    rec.last_error,
                    rec.updated_at,
                ),
            )
