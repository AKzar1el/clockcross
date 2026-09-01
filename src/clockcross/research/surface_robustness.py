from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Literal, TypedDict

import numpy as np

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.trading.constructor import ConstructionPolicy, construct_vertical

Direction = Literal["bullish", "bearish"]
_CENTS = Decimal("0.01")
_DELTA_QUANTUM = Decimal("0.000001")
_CONTRACT_MULTIPLIER = Decimal("100")


class CandidatePayload(TypedDict):
    long_symbol: str
    short_symbol: str
    expiration: str
    net_delta: float
    net_debit: float
    delta_per_debit: float
    max_loss: float


@dataclass(frozen=True)
class PerturbationBand:
    name: str
    midpoint_fraction: float
    spread_fraction: float
    delta_absolute: float

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("perturbation band name is required")
        for field_name in ("midpoint_fraction", "spread_fraction", "delta_absolute"):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")


DEFAULT_BANDS = (
    PerturbationBand("micro", 0.0025, 0.10, 0.005),
    PerturbationBand("small", 0.0050, 0.20, 0.010),
    PerturbationBand("moderate", 0.0100, 0.40, 0.020),
)


def _quantize_quote(value: float) -> Decimal:
    return max(Decimal("0.01"), Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP))


def _perturb_contract(
    contract: OptionContractSnapshot,
    *,
    band: PerturbationBand,
    rng: random.Random,
) -> OptionContractSnapshot:
    bid = float(contract.bid)
    ask = float(contract.ask)
    midpoint = (bid + ask) / 2.0
    half_spread = max(0.0, (ask - bid) / 2.0)

    perturbed_midpoint = midpoint * (
        1.0 + rng.uniform(-band.midpoint_fraction, band.midpoint_fraction)
    )
    perturbed_half_spread = half_spread * (
        1.0 + rng.uniform(-band.spread_fraction, band.spread_fraction)
    )
    perturbed_half_spread = max(0.0, perturbed_half_spread)

    new_bid = _quantize_quote(max(0.01, perturbed_midpoint - perturbed_half_spread))
    new_ask = _quantize_quote(max(float(new_bid), perturbed_midpoint + perturbed_half_spread))
    if new_ask < new_bid:
        new_ask = new_bid

    new_delta = contract.delta
    if new_delta is not None:
        sign = Decimal("1") if new_delta >= 0 else Decimal("-1")
        magnitude = abs(float(new_delta)) + rng.uniform(-band.delta_absolute, band.delta_absolute)
        magnitude = min(0.999999, max(0.000001, magnitude))
        new_delta = (sign * Decimal(str(magnitude))).quantize(
            _DELTA_QUANTUM, rounding=ROUND_HALF_UP
        )

    return contract.model_copy(update={"bid": new_bid, "ask": new_ask, "delta": new_delta})


def _perturb_chain(
    chain: OptionChainSnapshot,
    *,
    band: PerturbationBand,
    rng: random.Random,
) -> OptionChainSnapshot:
    return chain.model_copy(
        update={
            "contracts": [
                _perturb_contract(contract, band=band, rng=rng)
                for contract in chain.contracts
            ]
        }
    )


def _candidate_payload(candidate: object) -> CandidatePayload:
    from clockcross.domain import SpreadCandidate

    if not isinstance(candidate, SpreadCandidate):
        raise TypeError("expected SpreadCandidate")
    return {
        "long_symbol": candidate.long_leg.symbol,
        "short_symbol": candidate.short_leg.symbol,
        "expiration": candidate.expiration.isoformat(),
        "net_delta": float(Decimal(str(candidate.metadata["net_delta"]))),
        "net_debit": float(candidate.net_debit),
        "delta_per_debit": float(Decimal(str(candidate.metadata["delta_per_debit"]))),
        "max_loss": float(candidate.max_loss),
    }


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=float), probability))


def evaluate_surface_robustness(
    chain: OptionChainSnapshot,
    *,
    direction: Direction,
    now: datetime,
    max_net_debit: Decimal,
    bands: tuple[PerturbationBand, ...] = DEFAULT_BANDS,
    trials: int = 2_000,
    seed: int = 20260901,
) -> dict[str, object]:
    """Stress a constructor decision against bounded quote/Greek perturbations.

    This is a sensitivity diagnostic, not a probabilistic model of Alpaca's
    indicative-feed error. Each band is an explicitly declared perturbation
    envelope around the observed snapshot.
    """
    if now.tzinfo is None:
        raise ValueError("surface robustness time must be timezone-aware")
    if max_net_debit <= 0:
        raise ValueError("max_net_debit must be positive")
    if trials <= 0:
        raise ValueError("trials must be positive")
    if len({band.name for band in bands}) != len(bands):
        raise ValueError("perturbation band names must be unique")

    policy = ConstructionPolicy(max_net_debit=max_net_debit)
    baseline_candidate = construct_vertical(chain, direction=direction, now=now, policy=policy)
    if baseline_candidate is None:
        return {
            "direction": direction,
            "feed": chain.feed,
            "contract_count": len(chain.contracts),
            "trials_per_band": trials,
            "baseline_constructible": False,
            "baseline": None,
            "bands": {},
        }

    baseline = _candidate_payload(baseline_candidate)
    results: dict[str, dict[str, object]] = {}
    risk_cap = max_net_debit * _CONTRACT_MULTIPLIER

    for band_index, band in enumerate(bands):
        rng = random.Random(seed + band_index * 1_000_003)
        selected_count = 0
        same_pair = 0
        same_long = 0
        same_short = 0
        same_expiration = 0
        invariant_violations = 0
        pair_counts: Counter[str] = Counter()
        net_deltas: list[float] = []
        max_losses: list[float] = []
        debits: list[float] = []
        scores: list[float] = []

        for _ in range(trials):
            perturbed = _perturb_chain(chain, band=band, rng=rng)
            candidate = construct_vertical(
                perturbed,
                direction=direction,
                now=now,
                policy=policy,
            )
            if candidate is None:
                continue

            selected_count += 1
            payload = _candidate_payload(candidate)
            pair_key = f"{payload['long_symbol']}|{payload['short_symbol']}"
            pair_counts[pair_key] += 1
            same_long += int(payload["long_symbol"] == baseline["long_symbol"])
            same_short += int(payload["short_symbol"] == baseline["short_symbol"])
            same_expiration += int(payload["expiration"] == baseline["expiration"])
            same_pair += int(
                payload["long_symbol"] == baseline["long_symbol"]
                and payload["short_symbol"] == baseline["short_symbol"]
            )

            net_delta = payload["net_delta"]
            max_loss = payload["max_loss"]
            debit = payload["net_debit"]
            score = payload["delta_per_debit"]
            net_deltas.append(net_delta)
            max_losses.append(max_loss)
            debits.append(debit)
            scores.append(score)

            if (
                candidate.net_debit > max_net_debit
                or candidate.max_loss > risk_cap
                or Decimal(str(candidate.metadata["net_delta"])) < policy.min_net_delta
                or candidate.net_debit <= 0
            ):
                invariant_violations += 1

        denominator = float(trials)
        candidate_denominator = float(selected_count) if selected_count else 1.0
        results[band.name] = {
            "midpoint_fraction": band.midpoint_fraction,
            "spread_fraction": band.spread_fraction,
            "delta_absolute": band.delta_absolute,
            "candidate_count": selected_count,
            "abstention_count": trials - selected_count,
            "candidate_rate": selected_count / denominator,
            "same_pair_rate": same_pair / candidate_denominator if selected_count else 0.0,
            "same_long_rate": same_long / candidate_denominator if selected_count else 0.0,
            "same_short_rate": same_short / candidate_denominator if selected_count else 0.0,
            "same_expiration_rate": (
                same_expiration / candidate_denominator if selected_count else 0.0
            ),
            "risk_invariant_violations": invariant_violations,
            "net_delta_p05": _quantile(net_deltas, 0.05),
            "net_delta_p50": _quantile(net_deltas, 0.50),
            "net_delta_p95": _quantile(net_deltas, 0.95),
            "max_loss_p05": _quantile(max_losses, 0.05),
            "max_loss_p50": _quantile(max_losses, 0.50),
            "max_loss_p95": _quantile(max_losses, 0.95),
            "net_debit_p05": _quantile(debits, 0.05),
            "net_debit_p50": _quantile(debits, 0.50),
            "net_debit_p95": _quantile(debits, 0.95),
            "delta_per_debit_p05": _quantile(scores, 0.05),
            "delta_per_debit_p50": _quantile(scores, 0.50),
            "delta_per_debit_p95": _quantile(scores, 0.95),
            "top_pairs": [
                {"pair": pair, "count": count, "rate": count / candidate_denominator}
                for pair, count in pair_counts.most_common(5)
            ],
        }

    return {
        "direction": direction,
        "feed": chain.feed,
        "contract_count": len(chain.contracts),
        "trials_per_band": trials,
        "max_net_debit": float(max_net_debit),
        "baseline_constructible": True,
        "baseline": baseline,
        "bands": results,
    }
