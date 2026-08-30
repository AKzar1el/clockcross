from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from clockcross.alpaca.options import OptionChainSnapshot
from clockcross.domain import SpreadCandidate
from clockcross.preflight import options_level_3_status
from clockcross.trading.constructor import construct_vertical
from clockcross.trading.execution import build_client_order_id

_PROBE_DEBIT = Decimal("0.01")
_PROBE_MAX_LOSS = Decimal("1.00")
_MIN_NATURAL_DEBIT = Decimal("0.50")
_CANCELLED = {"canceled", "cancelled"}
_UNSAFE_TERMINAL = {"filled", "partially_filled", "rejected", "expired"}


class SmokeChainGateway(Protocol):
    def get_chain(self, underlying: str, *, now: datetime) -> OptionChainSnapshot: ...


class SmokeTradingGateway(Protocol):
    def clock(self) -> dict[str, Any]: ...

    def get_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None: ...

    def submit_vertical(
        self,
        candidate: SpreadCandidate,
        *,
        client_order_id: str,
    ) -> dict[str, Any]: ...

    def cancel_order(self, order_id: str) -> None: ...


class MlegSmokeResult(BaseModel):
    ok: bool
    client_order_id: str
    alpaca_order_id: str
    displayed_net_debit: Decimal
    submitted_limit: Decimal
    submit_status: str
    final_status: str
    long_leg: str
    short_leg: str


def _require_development_smoke(account_role: str, allow_dev_order: bool) -> None:
    if account_role != "development":
        raise RuntimeError("MLeg smoke requires the development account")
    if not allow_dev_order:
        raise RuntimeError("development order opt-in is required for MLeg smoke")


def _require_account_ready(
    account_payload: dict[str, Any],
    configuration_payload: dict[str, Any],
) -> None:
    if str(account_payload.get("status", "")).upper() != "ACTIVE":
        raise RuntimeError("development Alpaca paper account is not ACTIVE")
    if bool(account_payload.get("trading_blocked", False)):
        raise RuntimeError("development Alpaca paper account is trading-blocked")
    level_ok, level_state = options_level_3_status(
        account_payload,
        configuration_payload,
    )
    if not level_ok:
        raise RuntimeError(
            f"development Alpaca paper account requires options Level 3 ({level_state})"
        )


def _choose_smoke_candidate(
    chain: OptionChainSnapshot,
    *,
    now: datetime,
) -> SpreadCandidate:
    candidates = [
        candidate
        for candidate in (
            construct_vertical(chain, direction="bullish", now=now),
            construct_vertical(chain, direction="bearish", now=now),
        )
        if candidate is not None
    ]
    if not candidates:
        raise RuntimeError("no fresh COIN vertical is available for the MLeg smoke")

    candidate = max(
        candidates,
        key=lambda item: (item.net_debit, item.expiration, item.long_leg.symbol),
    )
    if candidate.net_debit < _MIN_NATURAL_DEBIT:
        raise RuntimeError(
            "displayed natural debit is too close to the one-cent smoke probe price"
        )
    return candidate


def _smoke_order(candidate: SpreadCandidate) -> SpreadCandidate:
    metadata = dict(candidate.metadata)
    metadata.update(
        {
            "smoke_probe": True,
            "displayed_net_debit": format(candidate.net_debit, "f"),
        }
    )
    return candidate.model_copy(
        update={
            "net_debit": _PROBE_DEBIT,
            "max_loss": _PROBE_MAX_LOSS,
            "metadata": metadata,
        }
    )


def run_mleg_smoke(
    *,
    account_role: str,
    allow_dev_order: bool,
    account_payload: dict[str, Any],
    configuration_payload: dict[str, Any],
    chain_gateway: SmokeChainGateway,
    trading: SmokeTradingGateway,
    now: datetime,
    sleeper: Callable[[float], None] = time.sleep,
    max_polls: int = 10,
) -> MlegSmokeResult:
    """Submit and cancel one deliberately non-marketable development-paper MLeg."""
    if now.tzinfo is None:
        raise ValueError("MLeg smoke time must be timezone-aware")
    if max_polls < 1:
        raise ValueError("max_polls must be at least 1")

    _require_development_smoke(account_role, allow_dev_order)
    _require_account_ready(account_payload, configuration_payload)

    clock = trading.clock()
    if not bool(clock.get("is_open", False)):
        raise RuntimeError("U.S. market is not open; refusing MLeg smoke")

    chain = chain_gateway.get_chain("COIN", now=now)
    displayed = _choose_smoke_candidate(chain, now=now)
    submitted_candidate = _smoke_order(displayed)
    episode_identity = f"smoke-{now.date().isoformat()}"
    client_order_id = build_client_order_id(episode_identity, submitted_candidate)

    if trading.get_by_client_order_id(client_order_id) is not None:
        raise RuntimeError(
            f"MLeg smoke client_order_id already exists: {client_order_id}"
        )

    remote = trading.submit_vertical(
        submitted_candidate,
        client_order_id=client_order_id,
    )
    raw_id = remote.get("id")
    if raw_id is None or not str(raw_id).strip():
        raise RuntimeError("Alpaca MLeg smoke submission returned no order id")
    alpaca_order_id = str(raw_id)
    submit_status = str(remote.get("status") or "unknown").lower()
    if submit_status in {"filled", "partially_filled"}:
        raise RuntimeError(
            "MLeg smoke unexpectedly filled before cancellation; inspect development account"
        )
    if submit_status in {"rejected", "expired"}:
        raise RuntimeError(f"MLeg smoke submission ended as {submit_status}")

    trading.cancel_order(alpaca_order_id)

    final_status = "unknown"
    for poll in range(max_polls):
        current = trading.get_by_client_order_id(client_order_id)
        if current is not None:
            final_status = str(current.get("status") or "unknown").lower()
            if final_status in _CANCELLED:
                final_status = "canceled"
                return MlegSmokeResult(
                    ok=True,
                    client_order_id=client_order_id,
                    alpaca_order_id=alpaca_order_id,
                    displayed_net_debit=displayed.net_debit,
                    submitted_limit=submitted_candidate.net_debit,
                    submit_status=submit_status,
                    final_status=final_status,
                    long_leg=submitted_candidate.long_leg.symbol,
                    short_leg=submitted_candidate.short_leg.symbol,
                )
            if final_status in _UNSAFE_TERMINAL:
                raise RuntimeError(
                    f"MLeg smoke ended as {final_status}; inspect development account"
                )
        if poll + 1 < max_polls:
            sleeper(0.5)

    raise RuntimeError(
        f"MLeg smoke cancel was not confirmed after {max_polls} polls; "
        f"last status={final_status}"
    )
