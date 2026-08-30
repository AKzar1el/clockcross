from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from clockcross.domain import OptionLeg, OrderSide, SpreadCandidate
from clockcross.trading.risk import PortfolioState, RiskGovernor, RiskPolicy

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 8, 31, 9, 55, tzinfo=ET)


def candidate(*, underlying="COIN", max_loss="250", age=5, reference_time=NOW):
    return SpreadCandidate(
        underlying=underlying,
        expiration=date(2026, 9, 11),
        long_leg=OptionLeg(symbol="COIN300C", side=OrderSide.BUY, ratio=1),
        short_leg=OptionLeg(symbol="COIN310C", side=OrderSide.SELL, ratio=1),
        net_debit=Decimal(max_loss) / Decimal("100"),
        max_loss=Decimal(max_loss),
        quote_timestamp=reference_time.astimezone(timezone.utc) - timedelta(seconds=age),
        metadata={"structure": "call_debit_spread"},
    )


def portfolio(**overrides):
    data = dict(
        starting_equity=Decimal("100000"),
        current_equity=Decimal("100000"),
        buying_power=Decimal("100000"),
        aggregate_defined_loss=Decimal("0"),
        open_underlyings=(),
    )
    data.update(overrides)
    return PortfolioState(**data)


def test_approves_candidate_inside_envelope():
    result = RiskGovernor().evaluate(candidate(), portfolio(), now=NOW)
    assert result.approved is True
    assert result.max_loss == Decimal("250")


def test_rejects_non_coin_and_duplicate_underlying():
    wrong = RiskGovernor().evaluate(candidate(underlying="MSTR"), portfolio(), now=NOW)
    duplicate = RiskGovernor().evaluate(candidate(), portfolio(open_underlyings=("COIN",)), now=NOW)
    assert wrong.approved is False and "underlying_not_approved" in wrong.reasons
    assert duplicate.approved is False and "underlying_already_open" in duplicate.reasons


def test_rejects_per_position_and_aggregate_loss_caps():
    too_large = RiskGovernor().evaluate(candidate(max_loss="1100"), portfolio(), now=NOW)
    aggregate = RiskGovernor().evaluate(
        candidate(max_loss="600"),
        portfolio(aggregate_defined_loss=Decimal("4500")),
        now=NOW,
    )
    assert "per_position_loss_cap" in too_large.reasons
    assert "aggregate_loss_cap" in aggregate.reasons


def test_rejects_insufficient_buying_power_and_stale_quote():
    buying = RiskGovernor().evaluate(
        candidate(max_loss="500"), portfolio(buying_power=Decimal("400")), now=NOW
    )
    stale = RiskGovernor().evaluate(candidate(age=61), portfolio(), now=NOW)
    assert "insufficient_buying_power" in buying.reasons
    assert "stale_quote" in stale.reasons


def test_rejects_outside_entry_window():
    early = datetime(2026, 8, 31, 9, 54, tzinfo=ET)
    late = datetime(2026, 8, 31, 15, 31, tzinfo=ET)
    assert "outside_entry_window" in RiskGovernor().evaluate(candidate(), portfolio(), now=early).reasons
    assert "outside_entry_window" in RiskGovernor().evaluate(candidate(), portfolio(), now=late).reasons


def test_rejects_at_or_after_final_event_entry_cutoff():
    cutoff = datetime(2026, 9, 4, 10, 20, tzinfo=ET)
    policy = RiskPolicy(final_entry_cutoff=cutoff)
    before_time = datetime(2026, 9, 4, 10, 19, tzinfo=ET)
    before = RiskGovernor(policy).evaluate(
        candidate(reference_time=before_time), portfolio(), now=before_time
    )
    at = RiskGovernor(policy).evaluate(candidate(reference_time=cutoff), portfolio(), now=cutoff)
    assert before.approved is True
    assert at.approved is False
    assert "final_event_cutoff" in at.reasons


def test_rejects_naive_now():
    result = RiskGovernor().evaluate(candidate(), portfolio(), now=datetime(2026, 8, 31, 9, 55))
    assert result.approved is False
    assert "naive_time" in result.reasons
