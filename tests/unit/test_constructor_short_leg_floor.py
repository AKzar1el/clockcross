from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.trading.constructor import construct_vertical

NOW = datetime(2026, 9, 1, 13, 55, tzinfo=timezone.utc)
EXP = date(2026, 9, 11)


def contract(symbol: str, strike: int, kind: str, delta: float, bid: float, ask: float) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=EXP,
        strike=Decimal(str(strike)),
        option_type=kind,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        quote_timestamp=NOW - timedelta(seconds=5),
        delta=Decimal(str(delta)),
    )


def test_default_constructor_rejects_near_zero_delta_call_short() -> None:
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("LONG", 180, "call", 0.55, 4.8, 5.0),
            contract("SHORT_MEANINGFUL", 195, "call", 0.15, 1.0, 1.2),
            contract("SHORT_LOTTERY", 235, "call", 0.02, 0.05, 0.10),
        ],
    )

    candidate = construct_vertical(chain, direction="bullish", now=NOW)

    assert candidate is not None
    assert candidate.short_leg.symbol == "SHORT_MEANINGFUL"
    assert Decimal(candidate.metadata["short_abs_delta"]) >= Decimal("0.10")


def test_default_constructor_rejects_near_zero_delta_put_short() -> None:
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("LONG", 180, "put", -0.55, 4.8, 5.0),
            contract("SHORT_MEANINGFUL", 165, "put", -0.15, 1.0, 1.2),
            contract("SHORT_LOTTERY", 125, "put", -0.02, 0.05, 0.10),
        ],
    )

    candidate = construct_vertical(chain, direction="bearish", now=NOW)

    assert candidate is not None
    assert candidate.short_leg.symbol == "SHORT_MEANINGFUL"
    assert Decimal(candidate.metadata["short_abs_delta"]) >= Decimal("0.10")
