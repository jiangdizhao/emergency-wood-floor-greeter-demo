from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CRMRepository:
    """Local SQLite CRM store for explicit contact and marketing consent.

    Contact values never enter the LLM prompt. This repository intentionally uses
    the same local database file as face memory, while keeping CRM tables separate.
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
                CREATE TABLE IF NOT EXISTS sales_leads (
                    lead_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    customer_id TEXT,
                    display_name TEXT,
                    contact_channel TEXT NOT NULL,
                    contact_value TEXT NOT NULL,
                    contact_opt_in INTEGER NOT NULL DEFAULT 0,
                    marketing_opt_in INTEGER NOT NULL DEFAULT 0,
                    consent_version TEXT NOT NULL,
                    contact_consent_at TEXT,
                    marketing_consent_at TEXT,
                    contact_purposes_json TEXT NOT NULL DEFAULT '[]',
                    preferred_contact_time TEXT,
                    lead_temperature TEXT NOT NULL DEFAULT 'warm',
                    sales_stage TEXT NOT NULL DEFAULT 'lead_capture',
                    promotion_ids_json TEXT NOT NULL DEFAULT '[]',
                    follow_up_status TEXT NOT NULL DEFAULT '待发送方案',
                    next_follow_up_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    revoked_at TEXT,
                    active INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_sales_leads_status_due
                ON sales_leads(active, follow_up_status, next_follow_up_at);

                CREATE INDEX IF NOT EXISTS idx_sales_leads_customer
                ON sales_leads(customer_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS lead_consent_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    contact_opt_in INTEGER NOT NULL,
                    marketing_opt_in INTEGER NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(lead_id) REFERENCES sales_leads(lead_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS lead_follow_up_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    scheduled_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(lead_id) REFERENCES sales_leads(lead_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_follow_up_events_lead
                ON lead_follow_up_events(lead_id, event_id DESC);
                """
            )

    def upsert_lead(
        self,
        *,
        session_id: str,
        customer_id: str | None,
        display_name: str | None,
        contact_channel: str,
        contact_value: str,
        contact_opt_in: bool,
        marketing_opt_in: bool,
        contact_purposes: list[str],
        preferred_contact_time: str | None,
        lead_temperature: str,
        sales_stage: str,
        promotion_ids: list[str],
        consent_version: str = "lead-contact-v1",
        next_follow_up_days: int = 3,
    ) -> dict[str, Any]:
        if not contact_opt_in:
            raise ValueError("Contact consent is required before storing contact details.")

        existing = self.get_by_session(session_id, include_inactive=True)
        lead_id = str(existing["lead_id"]) if existing else f"lead-{uuid.uuid4().hex}"
        now = utc_now()
        next_follow_up_at = (datetime.now(timezone.utc) + timedelta(days=max(1, next_follow_up_days))).isoformat()
        contact_consent_at = now
        marketing_consent_at = now if marketing_opt_in else None

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sales_leads(
                    lead_id, session_id, customer_id, display_name, contact_channel,
                    contact_value, contact_opt_in, marketing_opt_in, consent_version,
                    contact_consent_at, marketing_consent_at, contact_purposes_json,
                    preferred_contact_time, lead_temperature, sales_stage,
                    promotion_ids_json, follow_up_status, next_follow_up_at,
                    created_at, updated_at, revoked_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)
                ON CONFLICT(session_id) DO UPDATE SET
                    customer_id = excluded.customer_id,
                    display_name = excluded.display_name,
                    contact_channel = excluded.contact_channel,
                    contact_value = excluded.contact_value,
                    contact_opt_in = 1,
                    marketing_opt_in = excluded.marketing_opt_in,
                    consent_version = excluded.consent_version,
                    contact_consent_at = excluded.contact_consent_at,
                    marketing_consent_at = excluded.marketing_consent_at,
                    contact_purposes_json = excluded.contact_purposes_json,
                    preferred_contact_time = excluded.preferred_contact_time,
                    lead_temperature = excluded.lead_temperature,
                    sales_stage = excluded.sales_stage,
                    promotion_ids_json = excluded.promotion_ids_json,
                    follow_up_status = '待发送方案',
                    next_follow_up_at = excluded.next_follow_up_at,
                    updated_at = excluded.updated_at,
                    revoked_at = NULL,
                    active = 1
                """,
                (
                    lead_id,
                    session_id,
                    customer_id,
                    display_name or None,
                    contact_channel,
                    contact_value,
                    int(marketing_opt_in),
                    consent_version,
                    contact_consent_at,
                    marketing_consent_at,
                    json.dumps(contact_purposes, ensure_ascii=False, separators=(",", ":")),
                    preferred_contact_time or None,
                    lead_temperature,
                    sales_stage,
                    json.dumps(promotion_ids, ensure_ascii=False, separators=(",", ":")),
                    "待发送方案",
                    next_follow_up_at,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO lead_consent_events(
                    lead_id, action, contact_opt_in, marketing_opt_in, detail, created_at
                ) VALUES (?, 'granted_or_updated', 1, ?, ?, ?)
                """,
                (
                    lead_id,
                    int(marketing_opt_in),
                    "contact purposes=" + ",".join(contact_purposes),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO lead_follow_up_events(
                    lead_id, status, note, scheduled_at, completed_at, created_at
                ) VALUES (?, '待发送方案', '客户已授权针对本次方案联系；默认三天后复核跟进。', ?, NULL, ?)
                """,
                (lead_id, next_follow_up_at, now),
            )
        result = self.get_by_session(session_id)
        if result is None:
            raise RuntimeError("Lead was written but could not be reloaded.")
        return result

    def get_by_session(self, session_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
        query = "SELECT * FROM sales_leads WHERE session_id = ?"
        params: list[Any] = [session_id]
        if not include_inactive:
            query += " AND active = 1"
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return self._decode_row(row) if row else None

    def get_by_id(self, lead_id: str, *, include_inactive: bool = False) -> dict[str, Any] | None:
        query = "SELECT * FROM sales_leads WHERE lead_id = ?"
        params: list[Any] = [lead_id]
        if not include_inactive:
            query += " AND active = 1"
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return self._decode_row(row) if row else None

    def list_leads(
        self,
        *,
        status: str | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if active_only:
            clauses.append("active = 1")
        if status:
            clauses.append("follow_up_status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM sales_leads{where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def due_follow_ups(self, *, now: datetime | None = None, limit: int = 100) -> list[dict[str, Any]]:
        current = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sales_leads
                WHERE active = 1
                  AND contact_opt_in = 1
                  AND next_follow_up_at IS NOT NULL
                  AND next_follow_up_at <= ?
                  AND follow_up_status NOT IN ('已完成', '已关闭', '已撤回')
                ORDER BY next_follow_up_at ASC
                LIMIT ?
                """,
                (current, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._decode_row(row) for row in rows]

    def update_follow_up(
        self,
        *,
        lead_id: str,
        status: str,
        note: str = "",
        next_follow_up_at: str | None = None,
    ) -> dict[str, Any] | None:
        now = utc_now()
        completed_at = now if status in {"已完成", "已关闭"} else None
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sales_leads
                SET follow_up_status = ?,
                    next_follow_up_at = ?,
                    updated_at = ?
                WHERE lead_id = ? AND active = 1
                """,
                (status, next_follow_up_at, now, lead_id),
            )
            if cursor.rowcount <= 0:
                return None
            connection.execute(
                """
                INSERT INTO lead_follow_up_events(
                    lead_id, status, note, scheduled_at, completed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (lead_id, status, note, next_follow_up_at, completed_at, now),
            )
        return self.get_by_id(lead_id)

    def update_consents(
        self,
        *,
        session_id: str,
        contact_opt_in: bool,
        marketing_opt_in: bool,
    ) -> dict[str, Any] | None:
        existing = self.get_by_session(session_id, include_inactive=True)
        if not existing:
            return None
        now = utc_now()
        active = 1 if contact_opt_in else 0
        revoked_at = None if contact_opt_in else now
        status = existing["follow_up_status"] if contact_opt_in else "已撤回"
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sales_leads
                SET contact_opt_in = ?, marketing_opt_in = ?, active = ?, revoked_at = ?,
                    marketing_consent_at = CASE WHEN ? = 1 THEN ? ELSE NULL END,
                    follow_up_status = ?, next_follow_up_at = CASE WHEN ? = 1 THEN next_follow_up_at ELSE NULL END,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    int(contact_opt_in),
                    int(marketing_opt_in and contact_opt_in),
                    active,
                    revoked_at,
                    int(marketing_opt_in and contact_opt_in),
                    now,
                    status,
                    int(contact_opt_in),
                    now,
                    session_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO lead_consent_events(
                    lead_id, action, contact_opt_in, marketing_opt_in, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    existing["lead_id"],
                    "updated" if contact_opt_in else "revoked",
                    int(contact_opt_in),
                    int(marketing_opt_in and contact_opt_in),
                    "Consent preferences changed by customer.",
                    now,
                ),
            )
        return self.get_by_session(session_id, include_inactive=True)

    def delete_by_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sales_leads WHERE session_id = ?", (session_id,))
        return cursor.rowcount > 0

    def delete_by_customer(self, customer_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sales_leads WHERE customer_id = ?", (customer_id,))
        return int(cursor.rowcount)

    def count_active(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM sales_leads WHERE active = 1").fetchone()
        return int(row["count"] if row else 0)

    @staticmethod
    def masked_contact(lead: dict[str, Any]) -> str:
        value = str(lead.get("contact_value") or "")
        channel = str(lead.get("contact_channel") or "")
        if channel == "email" and "@" in value:
            local, domain = value.split("@", 1)
            return (local[:2] + "***@" + domain) if local else "***@" + domain
        if len(value) <= 4:
            return "*" * len(value)
        return value[:2] + "*" * max(2, len(value) - 4) + value[-2:]

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("contact_purposes_json", "promotion_ids_json"):
            raw = data.pop(key, "[]")
            output_key = key.removesuffix("_json")
            try:
                parsed = json.loads(raw or "[]")
            except (TypeError, json.JSONDecodeError):
                parsed = []
            data[output_key] = parsed if isinstance(parsed, list) else []
        for key in ("contact_opt_in", "marketing_opt_in", "active"):
            data[key] = bool(data.get(key))
        return data
