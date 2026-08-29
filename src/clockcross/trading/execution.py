from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx

from clockcross.domain import RiskDecision, SpreadCandidate
from clockcross.ledger import Ledger

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"


class IndeterminateOrderError(RuntimeError):
    """Submission outcome could not be proven after an uncertain transport failure."""

    def __init__(self, client_order_id: str) -> None:
        self.client_order_id = client_order_id
        super().__init__(f"indeterminate Alpaca order state for {client_order_id}")


@dataclass(frozen=True)
class ExecutionResult:
    client_order_id: str
    alpaca_order_id: str | None
    status: str
    reconciled: bool


class TradingGateway(Protocol):
    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None: ...
    def submit_vertical(self, candidate: SpreadCandidate, *, client_order_id: str) -> dict[str, Any]: ...


def build_client_order_id(episode_id: str, candidate: SpreadCandidate) -> str:
    material = {
        "episode_id": episode_id,
        "underlying": candidate.underlying,
        "expiration": candidate.expiration.isoformat(),
        "long": candidate.long_leg.symbol,
        "short": candidate.short_leg.symbol,
        "debit": format(candidate.net_debit, "f"),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:32]
    return f"clockcross-{digest}"


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _remote_fields(remote: dict[str, Any]) -> tuple[str | None, str]:
    raw_id = remote.get("id")
    alpaca_order_id = str(raw_id) if raw_id is not None else None
    raw_status = remote.get("status")
    status = str(raw_status) if raw_status is not None else "unknown"
    return alpaca_order_id, status


class AlpacaPaperTradingRestClient:
    """Minimal paper-only Trading REST adapter for atomic option MLeg orders."""

    def __init__(self, api_key: str, secret_key: str, *, base_url: str = PAPER_TRADING_URL, http_client: Any | None = None, timeout_seconds: float = 20.0) -> None:
        normalized = base_url.rstrip("/")
        if normalized != PAPER_TRADING_URL:
            raise ValueError("ClockCross execution permits only the Alpaca paper endpoint")
        self._http = http_client or httpx.Client(timeout=timeout_seconds)
        self._base_url = normalized
        self._timeout = timeout_seconds
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        }

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        response = self._http.get(
            f"{self._base_url}/v2/orders:by_client_order_id",
            headers=self._headers,
            params={"client_order_id": client_order_id},
            timeout=self._timeout,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected Alpaca order lookup response")
        return payload

    def submit_vertical(self, candidate: SpreadCandidate, *, client_order_id: str) -> dict[str, Any]:
        if candidate.underlying != "COIN":
            raise ValueError("ClockCross execution is restricted to COIN")
        if candidate.long_leg.ratio != 1 or candidate.short_leg.ratio != 1:
            raise ValueError("ClockCross supports only 1:1 vertical spreads")
        body = {
            "order_class": "mleg",
            "qty": "1",
            "type": "limit",
            "limit_price": _decimal_text(candidate.net_debit),
            "time_in_force": "day",
            "client_order_id": client_order_id,
            "legs": [
                {"symbol": candidate.long_leg.symbol, "ratio_qty": str(candidate.long_leg.ratio), "side": "buy", "position_intent": "buy_to_open"},
                {"symbol": candidate.short_leg.symbol, "ratio_qty": str(candidate.short_leg.ratio), "side": "sell", "position_intent": "sell_to_open"},
            ],
        }
        response = self._http.post(
            f"{self._base_url}/v2/orders",
            headers=self._headers,
            json=body,
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected Alpaca order submission response")
        return payload


class ExecutionService:
    """Idempotent order submission: reconcile, submit once, reconcile uncertainty."""

    def __init__(self, *, ledger: Ledger, trading: TradingGateway) -> None:
        self._ledger = ledger
        self._trading = trading

    def _record_remote(self, episode_id: str, client_order_id: str, remote: dict[str, Any], *, reconciled: bool) -> ExecutionResult:
        alpaca_order_id, status = _remote_fields(remote)
        existing = self._ledger.get_order_by_client_id(client_order_id)
        if existing is None:
            self._ledger.record_order(
                episode_id,
                client_order_id=client_order_id,
                alpaca_order_id=alpaca_order_id,
                status=status,
                payload={"provider_status": status},
            )
        else:
            self._ledger.update_order(
                client_order_id,
                alpaca_order_id=alpaca_order_id,
                status=status,
                payload={"provider_status": status},
            )
        return ExecutionResult(client_order_id=client_order_id, alpaca_order_id=alpaca_order_id, status=status, reconciled=reconciled)

    def submit(self, episode_id: str, candidate: SpreadCandidate, risk: RiskDecision) -> ExecutionResult:
        if not risk.approved:
            raise ValueError("risk decision must be approved before execution")
        episode = self._ledger.get_episode(episode_id)
        if episode is None:
            raise ValueError(f"unknown episode: {episode_id}")
        if candidate.underlying != episode.underlying:
            raise ValueError("candidate underlying does not match ledger episode")
        if candidate.underlying != "COIN":
            raise ValueError("ClockCross execution is restricted to COIN")

        client_order_id = build_client_order_id(episode_id, candidate)
        local = self._ledger.get_order_by_client_id(client_order_id)
        if local is not None and local.alpaca_order_id is not None:
            return ExecutionResult(client_order_id=client_order_id, alpaca_order_id=local.alpaca_order_id, status=local.status, reconciled=True)

        remote = self._trading.get_by_client_order_id(client_order_id)
        if remote is not None:
            return self._record_remote(episode_id, client_order_id, remote, reconciled=True)

        if local is None:
            self._ledger.record_order(
                episode_id,
                client_order_id=client_order_id,
                alpaca_order_id=None,
                status="pending_submission",
                payload={
                    "underlying": candidate.underlying,
                    "expiration": candidate.expiration.isoformat(),
                    "long_leg": candidate.long_leg.symbol,
                    "short_leg": candidate.short_leg.symbol,
                    "net_debit": _decimal_text(candidate.net_debit),
                },
            )

        try:
            submitted = self._trading.submit_vertical(candidate, client_order_id=client_order_id)
        except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
            reconciled = self._trading.get_by_client_order_id(client_order_id)
            if reconciled is not None:
                return self._record_remote(episode_id, client_order_id, reconciled, reconciled=True)
            self._ledger.update_order(client_order_id, alpaca_order_id=None, status="indeterminate", payload={"error_type": type(exc).__name__})
            raise IndeterminateOrderError(client_order_id) from exc
        except Exception:
            self._ledger.update_order(client_order_id, alpaca_order_id=None, status="rejected", payload={"reason": "definite_submission_failure"})
            raise

        return self._record_remote(episode_id, client_order_id, submitted, reconciled=False)
