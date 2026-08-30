from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, model_validator

from clockcross.domain import RiskDecision, SpreadCandidate
from clockcross.ledger import Ledger, OrderRecord

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


class CloseInstruction(BaseModel):
    """Deterministic close request for the exact opening vertical."""

    long_symbol: str = Field(min_length=1)
    short_symbol: str = Field(min_length=1)
    limit_price: Decimal = Field(lt=Decimal("0"))
    quote_timestamp: datetime
    attempt: int = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_instruction(self) -> "CloseInstruction":
        if self.long_symbol == self.short_symbol:
            raise ValueError("close legs must be distinct")
        if self.quote_timestamp.tzinfo is None:
            raise ValueError("close quote timestamp must be timezone-aware")
        return self


class TradingGateway(Protocol):
    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None: ...
    def submit_vertical(
        self, candidate: SpreadCandidate, *, client_order_id: str
    ) -> dict[str, Any]: ...
    def submit_close_vertical(
        self, instruction: CloseInstruction, *, client_order_id: str
    ) -> dict[str, Any]: ...


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


def build_close_client_order_id(episode_id: str, attempt: int) -> str:
    if attempt not in {0, 1}:
        raise ValueError("close attempt must be 0 or 1")
    material = {"episode_id": episode_id, "phase": "close", "attempt": attempt}
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()[:28]
    return f"clockcross-close-{digest}"


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

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        base_url: str = PAPER_TRADING_URL,
        http_client: Any | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
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

    def clock(self) -> dict[str, Any]:
        response = self._http.get(
            f"{self._base_url}/v2/clock",
            headers=self._headers,
            params={},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("unexpected Alpaca market clock response")
        return payload

    def cancel_order(self, order_id: str) -> None:
        if not order_id.strip():
            raise ValueError("Alpaca order id is required for cancellation")
        response = self._http.delete(
            f"{self._base_url}/v2/orders/{order_id}",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()

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

    def _post_order(self, body: dict[str, Any]) -> dict[str, Any]:
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

    def submit_vertical(
        self, candidate: SpreadCandidate, *, client_order_id: str
    ) -> dict[str, Any]:
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
                {
                    "symbol": candidate.long_leg.symbol,
                    "ratio_qty": str(candidate.long_leg.ratio),
                    "side": "buy",
                    "position_intent": "buy_to_open",
                },
                {
                    "symbol": candidate.short_leg.symbol,
                    "ratio_qty": str(candidate.short_leg.ratio),
                    "side": "sell",
                    "position_intent": "sell_to_open",
                },
            ],
        }
        return self._post_order(body)

    def submit_close_vertical(
        self, instruction: CloseInstruction, *, client_order_id: str
    ) -> dict[str, Any]:
        if not instruction.long_symbol.startswith("COIN") or not instruction.short_symbol.startswith(
            "COIN"
        ):
            raise ValueError("ClockCross close execution is restricted to COIN")
        body = {
            "order_class": "mleg",
            "qty": "1",
            "type": "limit",
            "limit_price": _decimal_text(instruction.limit_price),
            "time_in_force": "day",
            "client_order_id": client_order_id,
            "legs": [
                {
                    "symbol": instruction.long_symbol,
                    "ratio_qty": "1",
                    "side": "sell",
                    "position_intent": "sell_to_close",
                },
                {
                    "symbol": instruction.short_symbol,
                    "ratio_qty": "1",
                    "side": "buy",
                    "position_intent": "buy_to_close",
                },
            ],
        }
        return self._post_order(body)


class ExecutionService:
    """Idempotent order submission: reconcile, submit once, reconcile uncertainty."""

    def __init__(self, *, ledger: Ledger, trading: TradingGateway) -> None:
        self._ledger = ledger
        self._trading = trading

    def _record_remote(
        self,
        episode_id: str,
        client_order_id: str,
        remote: dict[str, Any],
        *,
        reconciled: bool,
        base_payload: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        alpaca_order_id, status = _remote_fields(remote)
        existing = self._ledger.get_order_by_client_id(client_order_id)
        payload = dict(existing.payload if existing is not None else (base_payload or {}))
        payload["provider_status"] = status
        if existing is None:
            self._ledger.record_order(
                episode_id,
                client_order_id=client_order_id,
                alpaca_order_id=alpaca_order_id,
                status=status,
                payload=payload,
            )
        else:
            self._ledger.update_order(
                client_order_id,
                alpaca_order_id=alpaca_order_id,
                status=status,
                payload=payload,
            )
        return ExecutionResult(
            client_order_id=client_order_id,
            alpaca_order_id=alpaca_order_id,
            status=status,
            reconciled=reconciled,
        )

    def _update_status(
        self,
        order: OrderRecord,
        *,
        status: str,
        additions: dict[str, Any],
    ) -> None:
        payload = {**order.payload, **additions}
        self._ledger.update_order(
            order.client_order_id,
            alpaca_order_id=order.alpaca_order_id,
            status=status,
            payload=payload,
        )

    def reconcile(self, order: OrderRecord) -> ExecutionResult:
        remote = self._trading.get_by_client_order_id(order.client_order_id)
        if remote is None:
            self._update_status(
                order,
                status="indeterminate",
                additions={"reason": "reconciliation_lookup_missing"},
            )
            raise IndeterminateOrderError(order.client_order_id)
        return self._record_remote(
            order.episode_id, order.client_order_id, remote, reconciled=True
        )

    def submit(
        self, episode_id: str, candidate: SpreadCandidate, risk: RiskDecision
    ) -> ExecutionResult:
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
        entry_payload = {
            "phase": "open",
            "underlying": candidate.underlying,
            "expiration": candidate.expiration.isoformat(),
            "long_leg": candidate.long_leg.symbol,
            "short_leg": candidate.short_leg.symbol,
            "net_debit": _decimal_text(candidate.net_debit),
            "quote_timestamp": candidate.quote_timestamp.isoformat(),
        }
        local = self._ledger.get_order_by_client_id(client_order_id)
        if local is not None and local.alpaca_order_id is not None:
            return ExecutionResult(
                client_order_id=client_order_id,
                alpaca_order_id=local.alpaca_order_id,
                status=local.status,
                reconciled=True,
            )

        remote = self._trading.get_by_client_order_id(client_order_id)
        if remote is not None:
            return self._record_remote(
                episode_id,
                client_order_id,
                remote,
                reconciled=True,
                base_payload=entry_payload,
            )

        if local is None:
            local = self._ledger.record_order(
                episode_id,
                client_order_id=client_order_id,
                alpaca_order_id=None,
                status="pending_submission",
                payload=entry_payload,
            )

        try:
            submitted = self._trading.submit_vertical(candidate, client_order_id=client_order_id)
        except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
            reconciled = self._trading.get_by_client_order_id(client_order_id)
            if reconciled is not None:
                return self._record_remote(
                    episode_id, client_order_id, reconciled, reconciled=True
                )
            self._update_status(
                local,
                status="indeterminate",
                additions={"error_type": type(exc).__name__},
            )
            raise IndeterminateOrderError(client_order_id) from exc
        except Exception:
            self._update_status(
                local,
                status="rejected",
                additions={"reason": "definite_submission_failure"},
            )
            raise

        return self._record_remote(
            episode_id, client_order_id, submitted, reconciled=False
        )

    def submit_close(
        self, episode_id: str, instruction: CloseInstruction
    ) -> ExecutionResult:
        episode = self._ledger.get_episode(episode_id)
        if episode is None:
            raise ValueError(f"unknown episode: {episode_id}")
        if episode.underlying != "COIN":
            raise ValueError("ClockCross close execution is restricted to COIN")

        client_order_id = build_close_client_order_id(episode_id, instruction.attempt)
        close_payload = {
            "phase": "close",
            "attempt": instruction.attempt,
            "long_leg": instruction.long_symbol,
            "short_leg": instruction.short_symbol,
            "limit_price": _decimal_text(instruction.limit_price),
            "quote_timestamp": instruction.quote_timestamp.isoformat(),
        }
        local = self._ledger.get_order_by_client_id(client_order_id)
        if local is not None and local.alpaca_order_id is not None:
            return ExecutionResult(
                client_order_id=client_order_id,
                alpaca_order_id=local.alpaca_order_id,
                status=local.status,
                reconciled=True,
            )

        remote = self._trading.get_by_client_order_id(client_order_id)
        if remote is not None:
            return self._record_remote(
                episode_id,
                client_order_id,
                remote,
                reconciled=True,
                base_payload=close_payload,
            )

        if local is None:
            local = self._ledger.record_order(
                episode_id,
                client_order_id=client_order_id,
                alpaca_order_id=None,
                status="pending_submission",
                payload=close_payload,
            )

        try:
            submitted = self._trading.submit_close_vertical(
                instruction, client_order_id=client_order_id
            )
        except (TimeoutError, ConnectionError, httpx.TransportError) as exc:
            reconciled = self._trading.get_by_client_order_id(client_order_id)
            if reconciled is not None:
                return self._record_remote(
                    episode_id, client_order_id, reconciled, reconciled=True
                )
            self._update_status(
                local,
                status="indeterminate",
                additions={"error_type": type(exc).__name__},
            )
            raise IndeterminateOrderError(client_order_id) from exc
        except Exception:
            self._update_status(
                local,
                status="rejected",
                additions={"reason": "definite_submission_failure"},
            )
            raise

        return self._record_remote(
            episode_id, client_order_id, submitted, reconciled=False
        )
