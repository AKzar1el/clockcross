from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.trading.execution import CloseInstruction

_CENTS = Decimal("0.01")
_MAX_QUOTE_AGE_SECONDS = 60


def _find_exact(
    chain: OptionChainSnapshot, long_symbol: str, short_symbol: str
) -> tuple[OptionContractSnapshot, OptionContractSnapshot]:
    by_symbol = {contract.symbol: contract for contract in chain.contracts}
    long_leg = by_symbol.get(long_symbol)
    short_leg = by_symbol.get(short_symbol)
    if long_leg is None or short_leg is None:
        raise ValueError("exact opening contracts are not present in current option chain")
    return long_leg, short_leg


def _require_quote(contract: OptionContractSnapshot, *, now: datetime) -> None:
    if contract.bid <= 0 or contract.ask <= 0 or contract.ask < contract.bid:
        raise ValueError(f"invalid close quote for {contract.symbol}")
    age = (
        now.astimezone(timezone.utc)
        - contract.quote_timestamp.astimezone(timezone.utc)
    ).total_seconds()
    if age < 0 or age > _MAX_QUOTE_AGE_SECONDS:
        raise ValueError(f"stale close quote for {contract.symbol}")


def _require_same_vertical(
    long_leg: OptionContractSnapshot, short_leg: OptionContractSnapshot
) -> None:
    if long_leg.underlying != "COIN" or short_leg.underlying != "COIN":
        raise ValueError("ClockCross close contracts must be COIN options")
    if long_leg.expiration != short_leg.expiration:
        raise ValueError("close contracts must share an expiration")
    if long_leg.option_type != short_leg.option_type:
        raise ValueError("close contracts must share an option type")
    if long_leg.option_type == "call" and long_leg.strike >= short_leg.strike:
        raise ValueError("close contracts do not form the opening call vertical")
    if long_leg.option_type == "put" and long_leg.strike <= short_leg.strike:
        raise ValueError("close contracts do not form the opening put vertical")


def build_close_instruction(
    chain: OptionChainSnapshot,
    *,
    long_symbol: str,
    short_symbol: str,
    now: datetime,
    attempt: int = 0,
) -> CloseInstruction:
    """Price a deterministic close for the exact opening spread using fresh quotes."""
    if now.tzinfo is None:
        raise ValueError("close instruction time must be timezone-aware")
    if attempt not in {0, 1}:
        raise ValueError("close attempt must be 0 or 1")
    if chain.underlying != "COIN":
        raise ValueError("ClockCross close chain must be COIN")

    long_leg, short_leg = _find_exact(chain, long_symbol, short_symbol)
    _require_same_vertical(long_leg, short_leg)
    _require_quote(long_leg, now=now)
    _require_quote(short_leg, now=now)

    if attempt == 1:
        credit = _CENTS
    else:
        natural_credit = long_leg.bid - short_leg.ask
        rounded_credit = natural_credit.quantize(_CENTS, rounding=ROUND_DOWN)
        credit = max(_CENTS, rounded_credit)

    return CloseInstruction(
        long_symbol=long_symbol,
        short_symbol=short_symbol,
        limit_price=-credit,
        quote_timestamp=min(long_leg.quote_timestamp, short_leg.quote_timestamp),
        attempt=attempt,
    )
