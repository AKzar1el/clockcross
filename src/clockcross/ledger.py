from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from clockcross.domain import AgentDecision, EpisodeState, RiskDecision
from clockcross.state import EpisodeMachine


@dataclass(frozen=True)
class EpisodeRecord:
    episode_id: str
    session_date: date
    underlying: str
    state: EpisodeState
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class OrderRecord:
    order_id: int
    episode_id: str
    client_order_id: str
    alpaca_order_id: str | None
    status: str
    payload: dict[str, Any]
    created_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {"value": decoded}


class Ledger:
    """Durable SQLite audit ledger with idempotent episode and order identities."""

    _COUNTABLE_TABLES = {"episodes", "transitions", "features", "agent_decisions", "risk_decisions", "orders", "marks"}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

    def close(self) -> None:
        self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY, session_date TEXT NOT NULL, underlying TEXT NOT NULL,
                state TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(session_date, underlying)
            );
            CREATE TABLE IF NOT EXISTS transitions (
                transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
                from_state TEXT NOT NULL, to_state TEXT NOT NULL, event TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS features (
                episode_id TEXT PRIMARY KEY REFERENCES episodes(episode_id) ON DELETE CASCADE,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agent_decisions (
                episode_id TEXT PRIMARY KEY REFERENCES episodes(episode_id) ON DELETE CASCADE,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS risk_decisions (
                episode_id TEXT PRIMARY KEY REFERENCES episodes(episode_id) ON DELETE CASCADE,
                payload_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
                client_order_id TEXT NOT NULL UNIQUE, alpaca_order_id TEXT,
                status TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS marks (
                mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
                marked_at TEXT NOT NULL, value TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        self._conn.commit()

    @staticmethod
    def _episode(row: sqlite3.Row) -> EpisodeRecord:
        return EpisodeRecord(
            episode_id=row["episode_id"], session_date=date.fromisoformat(row["session_date"]),
            underlying=row["underlying"], state=EpisodeState(row["state"]),
            created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _order(row: sqlite3.Row) -> OrderRecord:
        return OrderRecord(
            order_id=int(row["order_id"]), episode_id=row["episode_id"], client_order_id=row["client_order_id"],
            alpaca_order_id=row["alpaca_order_id"], status=row["status"], payload=_decode(row["payload_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create_episode(self, session_date: date, underlying: str) -> EpisodeRecord:
        now = _utcnow().isoformat()
        episode_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO episodes (episode_id, session_date, underlying, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (episode_id, session_date.isoformat(), underlying, EpisodeState.COLLECTING.value, now, now),
            )
            row = self._conn.execute(
                "SELECT * FROM episodes WHERE session_date = ? AND underlying = ?",
                (session_date.isoformat(), underlying),
            ).fetchone()
        assert row is not None
        return self._episode(row)

    def get_episode(self, episode_id: str) -> EpisodeRecord | None:
        row = self._conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
        return None if row is None else self._episode(row)

    def get_episode_for_session(
        self, session_date: date, underlying: str
    ) -> EpisodeRecord | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE session_date = ? AND underlying = ?",
            (session_date.isoformat(), underlying),
        ).fetchone()
        return None if row is None else self._episode(row)

    def get_open_episode(self, session_date: date, underlying: str) -> EpisodeRecord | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE session_date = ? AND underlying = ? AND state NOT IN (?, ?)",
            (session_date.isoformat(), underlying, EpisodeState.ABSTAINED.value, EpisodeState.CLOSED.value),
        ).fetchone()
        return None if row is None else self._episode(row)

    def get_unresolved_episode(self, underlying: str) -> EpisodeRecord | None:
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE underlying = ? AND state NOT IN (?, ?) ORDER BY session_date ASC, created_at ASC LIMIT 1",
            (underlying, EpisodeState.ABSTAINED.value, EpisodeState.CLOSED.value),
        ).fetchone()
        return None if row is None else self._episode(row)

    def transition(self, episode_id: str, requested: EpisodeState, *, event: str, payload: dict[str, Any] | None = None) -> EpisodeRecord:
        with self._conn:
            row = self._conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown episode: {episode_id}")
            current = EpisodeState(row["state"])
            if requested == current:
                return self._episode(row)
            EpisodeMachine(current).advance(requested)
            now = _utcnow().isoformat()
            self._conn.execute(
                "INSERT INTO transitions (episode_id, from_state, to_state, event, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (episode_id, current.value, requested.value, event, _json(payload or {}), now),
            )
            self._conn.execute("UPDATE episodes SET state = ?, updated_at = ? WHERE episode_id = ?", (requested.value, now, episode_id))
            updated = self._conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
        assert updated is not None
        return self._episode(updated)

    def _record_once(self, table: str, episode_id: str, payload: Any) -> None:
        if table not in {"features", "agent_decisions", "risk_decisions"}:
            raise ValueError("unsupported singleton ledger table")
        with self._conn:
            self._conn.execute(
                f"INSERT OR IGNORE INTO {table} (episode_id, payload_json, created_at) VALUES (?, ?, ?)",
                (episode_id, _json(payload), _utcnow().isoformat()),
            )

    def record_features(self, episode_id: str, payload: Any) -> None:
        self._record_once("features", episode_id, payload)

    def record_decision(self, episode_id: str, decision: AgentDecision) -> None:
        self._record_once("agent_decisions", episode_id, decision)

    def record_risk(self, episode_id: str, decision: RiskDecision) -> None:
        self._record_once("risk_decisions", episode_id, decision)

    def record_order(self, episode_id: str, *, client_order_id: str, alpaca_order_id: str | None, status: str, payload: dict[str, Any] | None = None) -> OrderRecord:
        now = _utcnow().isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO orders (episode_id, client_order_id, alpaca_order_id, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (episode_id, client_order_id, alpaca_order_id, status, _json(payload or {}), now, now),
            )
            row = self._conn.execute("SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)).fetchone()
        assert row is not None
        return self._order(row)

    def get_order_by_client_id(self, client_order_id: str) -> OrderRecord | None:
        row = self._conn.execute("SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)).fetchone()
        return None if row is None else self._order(row)

    def get_orders_for_episode(self, episode_id: str) -> list[OrderRecord]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE episode_id = ? ORDER BY order_id ASC", (episode_id,)
        ).fetchall()
        return [self._order(row) for row in rows]

    def get_latest_order_for_episode(self, episode_id: str) -> OrderRecord | None:
        row = self._conn.execute(
            "SELECT * FROM orders WHERE episode_id = ? ORDER BY order_id DESC LIMIT 1", (episode_id,)
        ).fetchone()
        return None if row is None else self._order(row)

    def get_latest_order_for_phase(self, episode_id: str, phase: str) -> OrderRecord | None:
        for order in reversed(self.get_orders_for_episode(episode_id)):
            if order.payload.get("phase") == phase:
                return order
        return None

    def update_order(self, client_order_id: str, *, alpaca_order_id: str | None, status: str, payload: dict[str, Any] | None = None) -> OrderRecord:
        now = _utcnow().isoformat()
        with self._conn:
            self._conn.execute(
                "UPDATE orders SET alpaca_order_id = COALESCE(?, alpaca_order_id), status = ?, payload_json = ?, updated_at = ? WHERE client_order_id = ?",
                (alpaca_order_id, status, _json(payload or {}), now, client_order_id),
            )
            row = self._conn.execute("SELECT * FROM orders WHERE client_order_id = ?", (client_order_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown client order id: {client_order_id}")
        return self._order(row)

    def record_mark(self, episode_id: str, *, marked_at: datetime, value: str, payload: dict[str, Any] | None = None) -> None:
        if marked_at.tzinfo is None:
            raise ValueError("mark timestamp must be timezone-aware")
        with self._conn:
            self._conn.execute(
                "INSERT INTO marks (episode_id, marked_at, value, payload_json) VALUES (?, ?, ?, ?)",
                (episode_id, marked_at.isoformat(), value, _json(payload or {})),
            )

    def get_latest_mark_payload(self, episode_id: str, value: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload_json FROM marks WHERE episode_id = ? AND value = ? ORDER BY mark_id DESC LIMIT 1",
            (episode_id, value),
        ).fetchone()
        return None if row is None else _decode(row["payload_json"])

    def count_rows(self, table: str) -> int:
        if table not in self._COUNTABLE_TABLES:
            raise ValueError("unsupported table")
        row = self._conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        assert row is not None
        return int(row["count"])
