"""SQLite WAL + FTS5 persistence for facts, episodes, clipboard, routines, recall, and audit logs."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


class FactRecord(BaseModel):
    id: int
    category: str
    key: str
    value: str
    confidence: float = 0.95
    source: str = "user"
    updated_at: float


class EpisodeRecord(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    model_id: str = ""
    lane: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    created_at: float


class ClipboardRecord(BaseModel):
    id: int
    content: str
    content_hash: str
    source_app: str = ""
    pinned: bool = False
    created_at: float


class RoutineRecord(BaseModel):
    id: int
    name: str
    trigger_phrase: str
    steps: list[dict[str, Any]] = Field(default_factory=list)
    cron_expr: str = ""
    enabled: bool = True
    last_run_at: float = 0.0


class RecallRecord(BaseModel):
    id: int
    app_name: str
    window_title: str
    summary_text: str
    created_at: float


class ApprovalRecord(BaseModel):
    id: str
    tool_name: str
    args_json: str
    summary: str
    tier: str
    status: str
    created_at: float
    resolved_at: float = 0.0


class AuditLogRecord(BaseModel):
    id: int
    actor: str
    tool_name: str
    tier: str
    decision: str
    summary: str
    result_status: str
    created_at: float


def _sanitize_fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]+", query)
    if not tokens:
        return ""
    return " OR ".join(f'"{tok}"*' for tok in tokens[:8])


def looks_like_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


class MemoryStore:
    """Thread/restart-safe SQLite + FTS5 persistence store."""

    def __init__(self, *, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.95,
                    source TEXT NOT NULL DEFAULT 'user',
                    updated_at REAL NOT NULL,
                    UNIQUE(category, key)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
                    fact_id UNINDEXED,
                    category,
                    key,
                    value
                );

                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model_id TEXT NOT NULL DEFAULT '',
                    lane TEXT NOT NULL DEFAULT '',
                    tokens_in INTEGER NOT NULL DEFAULT 0,
                    tokens_out INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                    episode_id UNINDEXED,
                    conversation_id UNINDEXED,
                    content
                );

                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_app TEXT NOT NULL DEFAULT '',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    trigger_phrase TEXT NOT NULL DEFAULT '',
                    steps_json TEXT NOT NULL,
                    cron_expr TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_at REAL NOT NULL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS recall_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT NOT NULL,
                    window_title TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS recall_fts USING fts5(
                    recall_id UNINDEXED,
                    app_name,
                    window_title,
                    summary_text
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    args_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    resolved_at REAL NOT NULL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    result_status TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )

    def upsert_fact(
        self,
        category: str,
        key: str,
        value: str,
        *,
        source: str = "user",
        confidence: float = 0.95,
    ) -> FactRecord:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (category, key, value, confidence, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value = excluded.value,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (category.strip(), key.strip(), value.strip(), confidence, source, now),
            )
            row = conn.execute(
                "SELECT * FROM facts WHERE category = ? AND key = ?",
                (category.strip(), key.strip()),
            ).fetchone()
            assert row is not None
            fact_id = int(row["id"])
            conn.execute("DELETE FROM facts_fts WHERE fact_id = ?", (fact_id,))
            conn.execute(
                "INSERT INTO facts_fts (fact_id, category, key, value) VALUES (?, ?, ?, ?)",
                (fact_id, row["category"], row["key"], row["value"]),
            )
        return FactRecord(**dict(row))

    def list_facts(self, *, limit: int = 100) -> list[FactRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [FactRecord(**dict(r)) for r in rows]

    def search_facts(self, query: str, *, limit: int = 10) -> list[FactRecord]:
        fts_q = _sanitize_fts_query(query)
        if not fts_q:
            return self.list_facts(limit=limit)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.* FROM facts f
                JOIN facts_fts fts ON f.id = fts.fact_id
                WHERE facts_fts MATCH ?
                ORDER BY f.updated_at DESC
                LIMIT ?
                """,
                (fts_q, limit),
            ).fetchall()
        return [FactRecord(**dict(r)) for r in rows]

    def delete_fact(self, fact_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.execute("DELETE FROM facts_fts WHERE fact_id = ?", (fact_id,))
            return cur.rowcount > 0

    def record_episode(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        model_id: str = "",
        lane: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> EpisodeRecord:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO episodes (conversation_id, role, content, model_id, lane, tokens_in, tokens_out, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content, model_id, lane, tokens_in, tokens_out, now),
            )
            ep_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO episodes_fts (episode_id, conversation_id, content) VALUES (?, ?, ?)",
                (ep_id, conversation_id, content),
            )
            row = conn.execute("SELECT * FROM episodes WHERE id = ?", (ep_id,)).fetchone()
            assert row is not None
        return EpisodeRecord(**dict(row))

    def recent_turns(self, conversation_id: str, *, limit: int = 12) -> list[EpisodeRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM (
                    SELECT * FROM episodes WHERE conversation_id = ? ORDER BY id DESC LIMIT ?
                ) sub ORDER BY id ASC
                """,
                (conversation_id, limit),
            ).fetchall()
        return [EpisodeRecord(**dict(r)) for r in rows]

    def search_episodes(self, query: str, *, limit: int = 10) -> list[EpisodeRecord]:
        fts_q = _sanitize_fts_query(query)
        if not fts_q:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.* FROM episodes e
                JOIN episodes_fts fts ON e.id = fts.episode_id
                WHERE episodes_fts MATCH ?
                ORDER BY e.id DESC
                LIMIT ?
                """,
                (fts_q, limit),
            ).fetchall()
        return [EpisodeRecord(**dict(r)) for r in rows]

    def get_summary(self, conversation_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary FROM conversation_summaries WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return str(row["summary"]) if row else ""

    def set_summary(self, conversation_id: str, summary: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_summaries (conversation_id, summary, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = excluded.updated_at
                """,
                (conversation_id, summary, time.time()),
            )

    def save_clipboard(self, content: str, *, source_app: str = "") -> ClipboardRecord | None:
        cleaned = content.strip()
        if not cleaned or len(cleaned) > 16_000 or looks_like_secret(cleaned):
            return None
        digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
        now = time.time()
        with self._connect() as conn:
            latest = conn.execute(
                "SELECT content_hash FROM clipboard_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if latest and latest["content_hash"] == digest:
                return None
            cur = conn.execute(
                """
                INSERT INTO clipboard_history (content, content_hash, source_app, pinned, created_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (cleaned, digest, source_app, now),
            )
            row = conn.execute("SELECT * FROM clipboard_history WHERE id = ?", (cur.lastrowid,)).fetchone()
            assert row is not None
        return ClipboardRecord(
            id=int(row["id"]),
            content=row["content"],
            content_hash=row["content_hash"],
            source_app=row["source_app"],
            pinned=bool(row["pinned"]),
            created_at=float(row["created_at"]),
        )

    def list_clipboard(self, *, query: str = "", limit: int = 20) -> list[ClipboardRecord]:
        with self._connect() as conn:
            if query.strip():
                rows = conn.execute(
                    "SELECT * FROM clipboard_history WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                    (f"%{query.strip()}%", limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM clipboard_history ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            ClipboardRecord(
                id=int(r["id"]),
                content=r["content"],
                content_hash=r["content_hash"],
                source_app=r["source_app"],
                pinned=bool(r["pinned"]),
                created_at=float(r["created_at"]),
            )
            for r in rows
        ]

    def upsert_routine(
        self,
        *,
        name: str,
        trigger_phrase: str = "",
        steps: list[dict[str, Any]],
        cron_expr: str = "",
        enabled: bool = True,
    ) -> RoutineRecord:
        steps_json = json.dumps(steps)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO routines (name, trigger_phrase, steps_json, cron_expr, enabled)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    trigger_phrase = excluded.trigger_phrase,
                    steps_json = excluded.steps_json,
                    cron_expr = excluded.cron_expr,
                    enabled = excluded.enabled
                """,
                (name.strip(), trigger_phrase.strip(), steps_json, cron_expr.strip(), int(enabled)),
            )
            row = conn.execute("SELECT * FROM routines WHERE name = ?", (name.strip(),)).fetchone()
            assert row is not None
        return self._row_to_routine(row)

    def list_routines(self) -> list[RoutineRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM routines ORDER BY id ASC").fetchall()
        return [self._row_to_routine(r) for r in rows]

    def get_routine(self, name: str) -> RoutineRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM routines WHERE LOWER(name) = LOWER(?)", (name.strip(),)).fetchone()
        return self._row_to_routine(row) if row else None

    def mark_routine_run(self, name: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE routines SET last_run_at = ? WHERE name = ?", (time.time(), name.strip()))

    @staticmethod
    def _row_to_routine(row: sqlite3.Row) -> RoutineRecord:
        return RoutineRecord(
            id=int(row["id"]),
            name=row["name"],
            trigger_phrase=row["trigger_phrase"],
            steps=json.loads(row["steps_json"]),
            cron_expr=row["cron_expr"],
            enabled=bool(row["enabled"]),
            last_run_at=float(row["last_run_at"]),
        )

    def record_recall(self, *, app_name: str, window_title: str, summary_text: str) -> RecallRecord:
        now = time.time()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO recall_events (app_name, window_title, summary_text, created_at) VALUES (?, ?, ?, ?)",
                (app_name, window_title, summary_text, now),
            )
            rec_id = int(cur.lastrowid or 0)
            conn.execute(
                "INSERT INTO recall_fts (recall_id, app_name, window_title, summary_text) VALUES (?, ?, ?, ?)",
                (rec_id, app_name, window_title, summary_text),
            )
            row = conn.execute("SELECT * FROM recall_events WHERE id = ?", (rec_id,)).fetchone()
            assert row is not None
        return RecallRecord(**dict(row))

    def search_recall(self, *, query: str = "", limit: int = 30) -> list[RecallRecord]:
        fts_q = _sanitize_fts_query(query)
        with self._connect() as conn:
            if fts_q:
                rows = conn.execute(
                    """
                    SELECT r.* FROM recall_events r
                    JOIN recall_fts fts ON r.id = fts.recall_id
                    WHERE recall_fts MATCH ?
                    ORDER BY r.id DESC
                    LIMIT ?
                    """,
                    (fts_q, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM recall_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [RecallRecord(**dict(r)) for r in rows]

    def prune_old_recall(self, *, max_age_sec: float = 7 * 86400) -> int:
        cutoff = time.time() - max_age_sec
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM recall_events WHERE created_at < ?", (cutoff,)).fetchall()
            ids = [int(r["id"]) for r in rows]
            if not ids:
                return 0
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM recall_fts WHERE recall_id IN ({placeholders})", ids)
            cur = conn.execute(f"DELETE FROM recall_events WHERE id IN ({placeholders})", ids)
            return cur.rowcount

    def create_approval(
        self,
        *,
        approval_id: str,
        tool_name: str,
        args_json: str,
        summary: str,
        tier: str,
    ) -> ApprovalRecord:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, tool_name, args_json, summary, tier, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (approval_id, tool_name, args_json, summary, tier, now),
            )
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            assert row is not None
        return ApprovalRecord(**dict(row))

    def resolve_approval(self, approval_id: str, *, approved: bool) -> ApprovalRecord | None:
        status = "approved" if approved else "denied"
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ? AND status = 'pending'",
                (status, now, approval_id),
            )
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return ApprovalRecord(**dict(row)) if row else None

    def list_approvals(self, *, status: str | None = "pending", limit: int = 50) -> list[ApprovalRecord]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [ApprovalRecord(**dict(r)) for r in rows]

    def log_audit(
        self,
        *,
        actor: str,
        tool_name: str,
        tier: str,
        decision: str,
        summary: str,
        result_status: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (actor, tool_name, tier, decision, summary, result_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (actor, tool_name, tier, decision, summary[:400], result_status, time.time()),
            )

    def list_audit_logs(self, *, limit: int = 50) -> list[AuditLogRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [AuditLogRecord(**dict(r)) for r in rows]
