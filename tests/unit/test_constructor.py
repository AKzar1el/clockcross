from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.domain import AgentAction, OrderSide
from clockcross.trading.constructor import (
    ConstructionPolicy,
    construct_vertical,
    direction_from_agent,
)

NOW = datetime(2026, 8, 31, 13, 55, tzinfo=timezone.utc)
EXP = date(2026, 9, 11)


def c(symbol, strike, kind, delta, bid, ask, *, expiration=EXP, age=5):
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=expiration,
        strike=Decimal(str(strike)),
        option_type=kind,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        quote_timestamp=NOW - timedelta(seconds=age),
        delta=Decimal(str(delta)) if delta is not None else None,
    )


def test_direction_maps_action_and_residual_sign():
    assert direction_from_agent(AgentAction.CONTINUATION, 1) == "bullish"
    assert direction_from_agent(AgentAction.CONTINUATION, -1) == "bearish"
    assert direction_from_agent(AgentAction.REVERSION, 1) == "bearish"
    assert direction_from_agent(AgentAction.REVERSION, -1) == "bullish"
    assert direction_from_agent(AgentAction.ABSTAIN, 1) is None


def test_constructs_bull_call_debit_spread_with_exact_max_loss():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            c("COIN300C", 300, "call", 0.55, 5.00, 5.20),
            c("COIN310C", 310, "call", 0.35, 2.70, 2.90),
        ],
    )
    candidate = construct_vertical(chain, direction="bullish", now=NOW)
    assert candidate is not None
    assert candidate.long_leg.symbol == "COIN300C"
    assert candidate.long_leg.side is OrderSide.BUY
    assert candidate.short_leg.symbol == "COIN310C"
    assert candidate.short_leg.side is OrderSide.SELL
    assert candidate.long_leg.ratio == 1 and candidate.short_leg.ratio == 1
    assert candidate.net_debit == Decimal("2.50")
    assert candidate.max_loss == Decimal("250.00")
    assert candidate.metadata["structure"] == "call_debit_spread"
    assert candidate.metadata["feed"] == "indicative"


def test_constructs_bear_put_debit_spread():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            c("COIN300P", 300, "put", -0.55, 5.00, 5.20),
            c("COIN290P", 290, "put", -0.35, 2.70, 2.90),
        ],
    )
    candidate = construct_vertical(chain, direction="bearish", now=NOW)
    assert candidate is not None
    assert candidate.long_leg.symbol == "COIN300P"
    assert candidate.short_leg.symbol == "COIN290P"
    assert candidate.net_debit == Decimal("2.50")


def test_selects_nearest_delta_pair_deterministically():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="opra",
        contracts=[
            c("L1", 300, "call", 0.60, 5.0, 5.2),
            c("L2", 301, "call", 0.55, 4.8, 5.0),
            c("S1", 310, "call", 0.40, 2.7, 2.9),
            c("S2", 311, "call", 0.35, 2.5, 2.7),
        ],
    )
    candidate = construct_vertical(chain, direction="bullish", now=NOW)
    assert candidate is not None
    assert candidate.long_leg.symbol == "L2"
    assert candidate.short_leg.symbol == "S2"


def test_returns_none_for_stale_missing_greeks_or_wrong_expiration():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            c("STALE", 300, "call", 0.55, 5, 5.2, age=90),
            c("NOGREEK", 310, "call", None, 2.7, 2.9),
            c("0DTE", 320, "call", 0.35, 1, 1.1, expiration=NOW.date()),
        ],
    )
    assert construct_vertical(chain, direction="bullish", now=NOW) is None


def test_rejects_debit_equal_to_or_wider_than_spread_width():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            c("L", 300, "call", 0.55, 12, 12),
            c("S", 310, "call", 0.35, 2, 2),
        ],
    )
    assert construct_vertical(chain, direction="bullish", now=NOW) is None


def test_policy_can_bound_maximum_debit_before_risk_governor():
    policy = ConstructionPolicy(max_net_debit=Decimal("2.00"))
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            c("L", 300, "call", 0.55, 5, 5.2),
            c("S", 310, "call", 0.35, 2.7, 2.9),
        ],
    )
    assert construct_vertical(chain, direction="bullish", now=NOW, policy=policy) is None


def test_live_liquidity_policy_does_not_advertise_unpopulated_oi_or_volume_gates():
    fields = ConstructionPolicy.model_fields
    assert "min_open_interest" not in fields
    assert "min_volume" not in fields


def test_alpaca_normalized_contracts_without_oi_or_volume_use_real_quote_controls_only():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            c("COIN300C", 300, "call", 0.55, 5.00, 5.20),
            c("COIN310C", 310, "call", 0.35, 2.70, 2.90),
        ],
    )
    assert all(item.open_interest is None and item.volume is None for item in chain.contracts)
    assert construct_vertical(chain, direction="bullish", now=NOW) is not None
