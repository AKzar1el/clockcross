from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.options import (
    OptionChainSnapshot,
    OptionContractSnapshot,
    OptionFeasibilityPolicy,
    evaluate_option_feasibility,
)

NOW = datetime(2026, 8, 31, 13, 55, tzinfo=timezone.utc)


def contract(
    symbol: str,
    *,
    strike: str,
    option_type: str,
    delta: str | None = None,
    bid: str = "4.90",
    ask: str = "5.10",
    age_seconds: int = 5,
    expiration: date = date(2026, 9, 11),
) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=expiration,
        strike=Decimal(strike),
        option_type=option_type,
        bid=Decimal(bid),
        ask=Decimal(ask),
        quote_timestamp=NOW - timedelta(seconds=age_seconds),
        delta=None if delta is None else Decimal(delta),
    )


def test_rejects_non_coin_underlying():
    chain = OptionChainSnapshot(underlying="MSTR", feed="indicative", contracts=[])
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is False
    assert "underlying_not_approved" in result.reasons


def test_rejects_stale_or_zero_quotes():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN1", strike="300", option_type="call", delta="0.55", age_seconds=61),
            contract("COIN2", strike="310", option_type="call", delta="0.35", bid="0", ask="1"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is False
    assert "no_eligible_contracts" in result.reasons


def test_rejects_0dte_and_out_of_range_expiration():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN0", strike="300", option_type="call", delta="0.55", expiration=NOW.date()),
            contract("COIN30", strike="310", option_type="call", delta="0.35", expiration=date(2026, 10, 2)),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is False


def test_requires_greeks_for_delta_policy_by_default():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN300C", strike="300", option_type="call"),
            contract("COIN310C", strike="310", option_type="call"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is False
    assert "missing_required_delta" in result.reasons


def test_reports_bull_call_surface_and_records_feed():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN300C", strike="300", option_type="call", delta="0.56", bid="5.00", ask="5.20"),
            contract("COIN310C", strike="310", option_type="call", delta="0.36", bid="2.70", ask="2.90"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is True
    assert result.feed == "indicative"
    assert result.available_structures == ("call_debit_spread",)
    assert result.eligible_contract_count == 2


def test_reports_bear_put_surface():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN300P", strike="300", option_type="put", delta="-0.55", bid="5.00", ask="5.20"),
            contract("COIN290P", strike="290", option_type="put", delta="-0.35", bid="2.70", ask="2.90"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is True
    assert result.available_structures == ("put_debit_spread",)


def test_reports_both_surfaces_without_choosing_a_trade():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="opra",
        contracts=[
            contract("COIN300C", strike="300", option_type="call", delta="0.55"),
            contract("COIN310C", strike="310", option_type="call", delta="0.35"),
            contract("COIN300P", strike="300", option_type="put", delta="-0.55"),
            contract("COIN290P", strike="290", option_type="put", delta="-0.35"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.available_structures == ("call_debit_spread", "put_debit_spread")
    assert result.feed == "opra"


def test_policy_rejects_excessive_relative_spread():
    policy = OptionFeasibilityPolicy(max_relative_spread=Decimal("0.25"))
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN300C", strike="300", option_type="call", delta="0.55", bid="1", ask="2"),
            contract("COIN310C", strike="310", option_type="call", delta="0.35", bid="1", ask="2"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW, policy=policy)
    assert result.feasible is False
    assert "no_eligible_contracts" in result.reasons


def test_rejects_crossed_quote():
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN300C", strike="300", option_type="call", delta="0.55", bid="5.20", ask="5.10"),
            contract("COIN310C", strike="310", option_type="call", delta="0.35"),
        ],
    )
    result = evaluate_option_feasibility(chain, now=NOW)
    assert result.feasible is False
