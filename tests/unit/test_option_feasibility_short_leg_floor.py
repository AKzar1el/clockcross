from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.options import (
    OptionChainSnapshot,
    OptionContractSnapshot,
    evaluate_option_feasibility,
)

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


def test_feasibility_rejects_call_surface_with_only_near_zero_delta_short() -> None:
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("LONG", 180, "call", 0.55, 4.8, 5.0),
            contract("SHORT_LOTTERY", 235, "call", 0.02, 0.08, 0.09),
        ],
    )

    result = evaluate_option_feasibility(chain, now=NOW)

    assert result.feasible is False
    assert "no_compatible_vertical" in result.reasons


def test_feasibility_rejects_put_surface_with_only_near_zero_delta_short() -> None:
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("LONG", 180, "put", -0.55, 4.8, 5.0),
            contract("SHORT_LOTTERY", 125, "put", -0.02, 0.08, 0.09),
        ],
    )

    result = evaluate_option_feasibility(chain, now=NOW)

    assert result.feasible is False
    assert "no_compatible_vertical" in result.reasons
