from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IdentityRepository:
    """Local SQLite repository for customers, face templates and conversation memory.

    The database stores float32 face embeddings but never stores raw camera frames.
    A fresh SQLite connection is opened for each operation so API and vision threads
    can safely share the repository.
    """

    def __init__(self, database_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[1] / "data" / "customer_memory.db"
        self.database_path = Path(database_path or os.getenv("CUSTOMER_MEMORY_DB", default_path))
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema_lock = threading.RLock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _ensure_schema(self) -> None:
        with self._schema_lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    consent_at TEXT NOT NULL,
                    consent_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS face_templates (
                    template_id TEXT PRIMARY KEY,
                    customer_id TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    dimension INTEGER NOT NULL,
                    quality_score REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_face_templates_customer
                ON face_templates(customer_id, active);

                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    provider_mode TEXT,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ended_at TEXT,
                    profile_json TEXT NOT NULL DEFAULT '{}',
                    summary TEXT NOT NULL DEFAULT '',
                    returning_context TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_customer_updated
                ON conversation_sessions(customer_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS conversation_turns (
                    turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_turns_session
                ON conversation_turns(session_id, turn_id);

                CREATE TABLE IF NOT EXISTS identity_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT,
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    score REAL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(customer_id) REFERENCES customers(customer_id) ON DELETE SET NULL
                );
                """
            )

    def create_customer(
        self,
        *,
        display_name: str | None,
        consent_version: str = "face-memory-mvp-v1",
    ) -> str:
        customer_id = f"customer-{uuid.uuid4().hex}"
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO customers(
                    customer_id, display_name, consent_at, consent_version,
                    created_at, updated_at, last_seen_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (customer_id, display_name or None, now, consent_version, now, now, now),
            )
        return customer_id

    def add_face_template(
        self,
        *,
        customer_id: str,
        embedding: np.ndarray,
        quality_score: float,
        model_name: str,
        model_version: str,
    ) -> str:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        template_id = f"template-{uuid.uuid4().hex}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO face_templates(
                    template_id, customer_id, model_name, model_version,
                    embedding, dimension, quality_score, created_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    template_id,
                    customer_id,
                    model_name,
                    model_version,
                    sqlite3.Binary(vector.tobytes()),
                    int(vector.size),
                    float(quality_score),
                    utc_now(),
                ),
            )
        return template_id

    def load_active_templates(
        self,
        *,
        model_name: str,
        model_version: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT ft.template_id, ft.customer_id, ft.embedding, ft.dimension,
                       ft.quality_score, c.display_name
                FROM face_templates ft
                JOIN customers c ON c.customer_id = ft.customer_id
                WHERE ft.active = 1 AND c.active = 1
                  AND ft.model_name = ? AND ft.model_version = ?
                ORDER BY ft.customer_id, ft.quality_score DESC
                """,
                (model_name, model_version),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            vector = np.frombuffer(row["embedding"], dtype=np.float32, count=row["dimension"]).copy()
            output.append(
                {
                    "template_id": row["template_id"],
                    "customer_id": row["customer_id"],
                    "display_name": row["display_name"],
                    "quality_score": float(row["quality_score"]),
                    "embedding": vector,
                }
            )
        return output

    def customer_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM customers WHERE active = 1").fetchone()
        return int(row["count"] if row else 0)

    def face_template_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM face_templates WHERE active = 1").fetchone()
        return int(row["count"] if row else 0)

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM customers WHERE customer_id = ? AND active = 1",
                (customer_id,),
            ).fetchone()
        return dict(row) if row else None

    def mark_seen(self, customer_id: str) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE customers SET last_seen_at = ?, updated_at = ? WHERE customer_id = ?",
                (now, now, customer_id),
            )

    def create_or_update_session(
        self,
        *,
        session_id: str,
        customer_id: str | None,
        provider_mode: str,
        profile: dict[str, Any] | None = None,
        summary: str = "",
        returning_context: str = "",
    ) -> None:
        now = utc_now()
        profile_json = json.dumps(profile or {}, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_sessions(
                    session_id, customer_id, provider_mode, started_at, updated_at,
                    profile_json, summary, returning_context
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    provider_mode = excluded.provider_mode,
                    updated_at = excluded.updated_at,
                    profile_json = excluded.profile_json,
                    summary = excluded.summary,
                    returning_context = CASE
                        WHEN excluded.returning_context <> '' THEN excluded.returning_context
                        ELSE conversation_sessions.returning_context
                    END
                """,
                (
                    session_id,
                    customer_id,
                    provider_mode,
                    now,
                    now,
                    profile_json,
                    summary,
                    returning_context,
                ),
            )

    def append_turn(self, *, session_id: str, role: str, text: str) -> None:
        if role not in {"customer", "assistant", "system"}:
            raise ValueError(f"Unsupported conversation role: {role}")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversation_turns(session_id, role, text, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, text, utc_now()),
            )

    def finish_session(self, *, session_id: str, summary: str, profile: dict[str, Any]) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE conversation_sessions
                SET ended_at = ?, updated_at = ?, summary = ?, profile_json = ?
                WHERE session_id = ?
                """,
                (
                    now,
                    now,
                    summary,
                    json.dumps(profile, ensure_ascii=False, separators=(",", ":")),
                    session_id,
                ),
            )

    def get_session_customer_id(self, session_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT customer_id FROM conversation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return str(row["customer_id"]) if row and row["customer_id"] else None

    def latest_customer_profile(self, customer_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT profile_json
                FROM conversation_sessions
                WHERE customer_id = ? AND profile_json <> '{}'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (customer_id,),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["profile_json"])
            return data if isinstance(data, dict) else None
        except (TypeError, json.JSONDecodeError):
            return None

    def recent_session_memories(self, customer_id: str, limit: int = 3) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT session_id, started_at, ended_at, updated_at, summary,
                       profile_json, provider_mode
                FROM conversation_sessions
                WHERE customer_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (customer_id, max(1, int(limit))),
            ).fetchall()
        memories: list[dict[str, Any]] = []
        for row in rows:
            try:
                profile = json.loads(row["profile_json"])
            except (TypeError, json.JSONDecodeError):
                profile = {}
            memories.append(
                {
                    "session_id": row["session_id"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "updated_at": row["updated_at"],
                    "summary": row["summary"],
                    "profile": profile if isinstance(profile, dict) else {},
                    "provider_mode": row["provider_mode"],
                }
            )
        return memories

    def record_identity_event(
        self,
        *,
        event_type: str,
        customer_id: str | None = None,
        session_id: str | None = None,
        score: float | None = None,
        detail: str = "",
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO identity_events(customer_id, session_id, event_type, score, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (customer_id, session_id, event_type, score, detail, utc_now()),
            )

    def delete_customer(self, customer_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT customer_id FROM customers WHERE customer_id = ?",
                (customer_id,),
            ).fetchone()
            if not row:
                return False
            connection.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
        return True
