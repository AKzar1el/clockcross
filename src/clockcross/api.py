from __future__ import annotations

import html
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from clockcross.ledger import Ledger

_SENSITIVE_FRAGMENTS = ("account_id", "api_key", "secret", "token", "authorization", "credential", "header")


class AccountStatusProvider(Protocol):
    def public_status(self) -> dict[str, Any]: ...


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(fragment in lowered for fragment in _SENSITIVE_FRAGMENTS):
                continue
            out[key] = _sanitize(item)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, Decimal):
        return round(float(value), 2)
    if isinstance(value, float):
        return round(value, 2)
    return value


def _load_research(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError("research artifact must contain an object")
    return payload


def _compact_research(path: Path) -> dict[str, Any]:
    raw = _load_research(path)
    symbols = raw.get("symbols") if isinstance(raw.get("symbols"), dict) else {}
    coin = symbols.get("COIN") if isinstance(symbols.get("COIN"), dict) else {}
    mstr = symbols.get("MSTR") if isinstance(symbols.get("MSTR"), dict) else {}
    mean_coin = coin.get("mean_test_return")
    mean_mstr = mstr.get("mean_test_return")
    return {
        "verdict": raw.get("verdict"),
        "timing": {
            "feature_freeze_et": raw.get("feature_freeze_et"),
            "confirmation_end_et": raw.get("confirmation_end_et"),
            "decision_time_et": raw.get("decision_time_et"),
        },
        "feeds": {
            "historical": raw.get("historical_stock_feed"),
            "live": raw.get("live_stock_feed"),
        },
        "coin": {
            "role": "live_candidate",
            "verdict": coin.get("verdict"),
            "total_signals": coin.get("total_signals"),
            "mean_test_return_bps": None if not isinstance(mean_coin, (int, float)) else round(mean_coin * 10_000, 2),
            "config_hash": (coin.get("metadata") or {}).get("config_hash") if isinstance(coin.get("metadata"), dict) else None,
        },
        "mstr": {
            "role": "negative_evidence_only",
            "verdict": mstr.get("verdict"),
            "mean_test_return_bps": None if not isinstance(mean_mstr, (int, float)) else round(mean_mstr * 10_000, 2),
        },
        "limitations": [
            "Paper-trading results are hypothetical.",
            "The original 100 bps underlying-friction check failed and remains published.",
            "MSTR is not execution-eligible under the approved mutation.",
        ],
    }


def _public_db_ping(path: Path) -> bool:
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT 1").fetchone()
    return bool(row and row[0] == 1)


def _public_episode_summaries(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or limit > 1000:
        raise ValueError("episode summary limit must be between 1 and 1000")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM episodes ORDER BY session_date DESC, created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            reason_row = conn.execute(
                "SELECT payload_json FROM transitions WHERE episode_id = ? AND to_state = 'ABSTAINED' "
                "ORDER BY transition_id DESC LIMIT 1",
                (row["episode_id"],),
            ).fetchone()
            reason = None
            if reason_row is not None:
                try:
                    payload = json.loads(reason_row["payload_json"] or "{}")
                except json.JSONDecodeError:
                    payload = {}
                if isinstance(payload, dict) and payload.get("reason") is not None:
                    reason = str(payload["reason"])
            result.append({
                "episode_id": row["episode_id"],
                "session_date": row["session_date"],
                "underlying": row["underlying"],
                "state": row["state"],
                "reason": reason,
                "updated_at": row["updated_at"],
            })
        return result
    finally:
        conn.close()


def create_app(
    *,
    ledger: Ledger | None = None,
    research_path: str | Path | None = None,
    account_provider: AccountStatusProvider | None = None,
) -> FastAPI:
    owned_ledger = ledger is None
    ledger = ledger or Ledger(os.getenv("CLOCKCROSS_DB_PATH", "data/clockcross.sqlite3"))
    research = Path(research_path or os.getenv("CLOCKCROSS_RESEARCH_PATH", "artifacts/research/verdict.json"))
    template = Path(__file__).with_name("templates") / "index.html"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if owned_ledger:
                ledger.close()

    app = FastAPI(
        title="ClockCross Evidence Console",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    def status_payload() -> dict[str, Any]:
        episodes = _public_episode_summaries(ledger.path, limit=1)
        account = {} if account_provider is None else _sanitize(account_provider.public_status())
        return {
            "account": account,
            "latest_episode": episodes[0] if episodes else None,
            "mode": "paper_only",
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> JSONResponse:
        try:
            db_ok = _public_db_ping(ledger.path)
            _load_research(research)
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return JSONResponse(status_code=200 if db_ok else 503, content={"status": "ready" if db_ok else "not_ready"})

    @app.get("/api/status")
    def api_status() -> dict[str, Any]:
        return status_payload()

    @app.get("/api/episodes")
    def api_episodes() -> dict[str, Any]:
        return {"episodes": _public_episode_summaries(ledger.path, limit=100)}

    @app.get("/api/research")
    def api_research() -> dict[str, Any]:
        return _compact_research(research)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        status = json.dumps(status_payload(), indent=2, default=str)
        research_payload = json.dumps(_compact_research(research), indent=2, default=str)
        episodes = json.dumps(_public_episode_summaries(ledger.path, limit=20), indent=2, default=str)
        text = template.read_text()
        text = text.replace("__STATUS__", html.escape(status))
        text = text.replace("__RESEARCH__", html.escape(research_payload))
        text = text.replace("__EPISODES__", html.escape(episodes))
        return HTMLResponse(text)

    return app
