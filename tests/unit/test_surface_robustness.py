from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.research import surface_robustness

NOW = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
EXPIRATION = date(2026, 9, 11)


def contract(
    symbol: str,
    strike: str,
    delta: str,
    bid: str,
    ask: str,
    *,
    option_type: str = "call",
) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=EXPIRATION,
        strike=Decimal(strike),
        option_type=option_type,
        bid=Decimal(bid),
        ask=Decimal(ask),
        quote_timestamp=NOW - timedelta(seconds=5),
        delta=Decimal(delta),
    )


def clear_chain() -> OptionChainSnapshot:
    return OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("LONG", "180", "0.55", "4.80", "5.00"),
            contract("SHORT_CLEAR", "200", "0.15", "1.50", "1.60"),
            contract("SHORT_ALT", "205", "0.12", "0.70", "0.80"),
        ],
    )


def near_tie_chain() -> OptionChainSnapshot:
    return OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("LONG", "180", "0.55", "4.80", "5.00"),
            contract("SHORT_A", "200", "0.15", "1.00", "1.10"),
            contract("SHORT_B", "205", "0.12", "0.70", "0.80"),
        ],
    )


def test_micro_perturbations_preserve_clear_structure_and_risk_invariants() -> None:
    evaluator = getattr(surface_robustness, "evaluate_surface_robustness", None)
    assert callable(evaluator), "surface robustness evaluator must exist"

    result = evaluator(
        clear_chain(),
        direction="bullish",
        now=NOW,
        max_net_debit=Decimal("10"),
        bands=(surface_robustness.PerturbationBand("micro", 0.0025, 0.10, 0.005),),
        trials=500,
        seed=11,
    )

    assert result["baseline_constructible"] is True
    assert result["baseline"]["long_symbol"] == "LONG"
    assert result["baseline"]["short_symbol"] == "SHORT_CLEAR"
    micro = result["bands"]["micro"]
    assert micro["candidate_rate"] == 1.0
    assert micro["same_long_rate"] > 0.95
    assert micro["same_pair_rate"] > 0.80
    assert micro["risk_invariant_violations"] == 0
    assert micro["net_delta_p05"] >= 0.30
    assert micro["max_loss_p95"] <= 1000.0


def test_near_tie_surface_reports_churn_without_risk_escape() -> None:
    result = surface_robustness.evaluate_surface_robustness(
        near_tie_chain(),
        direction="bullish",
        now=NOW,
        max_net_debit=Decimal("10"),
        bands=(surface_robustness.PerturbationBand("small", 0.005, 0.20, 0.01),),
        trials=1000,
        seed=17,
    )

    small = result["bands"]["small"]
    assert small["candidate_rate"] == 1.0
    assert small["same_long_rate"] > 0.90
    assert small["same_pair_rate"] < 0.95
    assert len(small["top_pairs"]) >= 2
    assert small["risk_invariant_violations"] == 0


def test_surface_robustness_is_deterministic_for_fixed_seed() -> None:
    kwargs = dict(
        direction="bullish",
        now=NOW,
        max_net_debit=Decimal("10"),
        bands=(surface_robustness.PerturbationBand("micro", 0.0025, 0.10, 0.005),),
        trials=100,
        seed=23,
    )
    first = surface_robustness.evaluate_surface_robustness(clear_chain(), **kwargs)
    second = surface_robustness.evaluate_surface_robustness(clear_chain(), **kwargs)
    assert first == second


def test_unconstructible_baseline_fails_closed() -> None:
    chain = OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[contract("ONLY", "180", "0.55", "4.80", "5.00")],
    )

    result = surface_robustness.evaluate_surface_robustness(
        chain,
        direction="bullish",
        now=NOW,
        max_net_debit=Decimal("10"),
        trials=50,
        seed=5,
    )

    assert result["baseline_constructible"] is False
    assert result["baseline"] is None
    assert result["bands"] == {}
