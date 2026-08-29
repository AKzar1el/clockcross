from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.domain import AgentAction, OptionLeg, OrderSide, SpreadCandidate

Direction = Literal["bullish", "bearish"]
_CENTS = Decimal("0.01")
_CONTRACT_MULTIPLIER = Decimal("100")


class ConstructionPolicy(BaseModel):
    approved_underlying: str = "COIN"
    min_dte: int = Field(default=7, ge=1)
    max_dte: int = Field(default=21, ge=1)
    max_quote_age_seconds: int = Field(default=60, ge=1)
    max_relative_spread: Decimal = Field(default=Decimal("0.25"), gt=Decimal("0"))
    long_delta_target: Decimal = Decimal("0.55")
    short_delta_target: Decimal = Decimal("0.35")
    delta_tolerance: Decimal = Decimal("0.15")
    min_open_interest: int = Field(default=100, ge=0)
    min_volume: int = Field(default=1, ge=0)
    max_net_debit: Decimal | None = Field(default=None, gt=Decimal("0"))

    @model_validator(mode="after")
    def validate_dte_range(self) -> "ConstructionPolicy":
        if self.max_dte < self.min_dte:
            raise ValueError("max_dte must be >= min_dte")
        return self


def direction_from_agent(action: AgentAction, residual_sign: int) -> Direction | None:
    if action is AgentAction.ABSTAIN:
        return None
    if residual_sign not in {-1, 1}:
        raise ValueError("residual_sign must be -1 or 1")
    continuation_is_bullish = residual_sign > 0
    if action is AgentAction.REVERSION:
        continuation_is_bullish = not continuation_is_bullish
    return "bullish" if continuation_is_bullish else "bearish"


def _relative_spread(contract: OptionContractSnapshot) -> Decimal | None:
    if contract.bid <= 0 or contract.ask <= 0 or contract.ask < contract.bid:
        return None
    midpoint = (contract.bid + contract.ask) / Decimal("2")
    if midpoint <= 0:
        return None
    return (contract.ask - contract.bid) / midpoint


def _eligible(
    contract: OptionContractSnapshot,
    *,
    now: datetime,
    option_type: Literal["call", "put"],
    policy: ConstructionPolicy,
) -> bool:
    if contract.underlying != policy.approved_underlying or contract.option_type != option_type:
        return False
    dte = (contract.expiration - now.date()).days
    if not policy.min_dte <= dte <= policy.max_dte:
        return False
    age = (
        now.astimezone(timezone.utc) - contract.quote_timestamp.astimezone(timezone.utc)
    ).total_seconds()
    if age < 0 or age > policy.max_quote_age_seconds:
        return False
    spread = _relative_spread(contract)
    if spread is None or spread > policy.max_relative_spread:
        return False
    if contract.delta is None:
        return False
    if contract.open_interest is not None and contract.open_interest < policy.min_open_interest:
        return False
    if contract.volume is not None and contract.volume < policy.min_volume:
        return False
    return True


def _delta_distance(contract: OptionContractSnapshot, target: Decimal) -> Decimal:
    assert contract.delta is not None
    return abs(abs(contract.delta) - target)


def _candidate_pairs(
    contracts: list[OptionContractSnapshot],
    *,
    direction: Direction,
    policy: ConstructionPolicy,
) -> list[tuple[tuple[object, ...], OptionContractSnapshot, OptionContractSnapshot, Decimal]]:
    option_type: Literal["call", "put"] = "call" if direction == "bullish" else "put"
    pairs: list[tuple[tuple[object, ...], OptionContractSnapshot, OptionContractSnapshot, Decimal]] = []
    for expiration in sorted({item.expiration for item in contracts}):
        same_expiry = [item for item in contracts if item.expiration == expiration]
        long_legs = [
            item
            for item in same_expiry
            if _delta_distance(item, policy.long_delta_target) <= policy.delta_tolerance
        ]
        short_legs = [
            item
            for item in same_expiry
            if _delta_distance(item, policy.short_delta_target) <= policy.delta_tolerance
        ]
        for long_leg in long_legs:
            for short_leg in short_legs:
                if long_leg.symbol == short_leg.symbol:
                    continue
                if option_type == "call" and long_leg.strike >= short_leg.strike:
                    continue
                if option_type == "put" and long_leg.strike <= short_leg.strike:
                    continue
                width = abs(short_leg.strike - long_leg.strike)
                debit = long_leg.ask - short_leg.bid
                if debit <= 0 or debit >= width:
                    continue
                if policy.max_net_debit is not None and debit > policy.max_net_debit:
                    continue
                key = (
                    _delta_distance(long_leg, policy.long_delta_target),
                    _delta_distance(short_leg, policy.short_delta_target),
                    expiration,
                    long_leg.symbol,
                    short_leg.symbol,
                )
                pairs.append((key, long_leg, short_leg, debit))
    return pairs


def construct_vertical(
    chain: OptionChainSnapshot,
    *,
    direction: Direction,
    now: datetime,
    policy: ConstructionPolicy | None = None,
) -> SpreadCandidate | None:
    if now.tzinfo is None:
        raise ValueError("construction time must be timezone-aware")
    policy = policy or ConstructionPolicy()
    if chain.underlying != policy.approved_underlying:
        return None

    option_type: Literal["call", "put"] = "call" if direction == "bullish" else "put"
    eligible = [
        contract
        for contract in chain.contracts
        if _eligible(contract, now=now, option_type=option_type, policy=policy)
    ]
    if not eligible:
        return None

    pairs = _candidate_pairs(eligible, direction=direction, policy=policy)
    if not pairs:
        return None
    _, long_leg, short_leg, debit = min(pairs, key=lambda item: item[0])

    debit = debit.quantize(_CENTS, rounding=ROUND_HALF_UP)
    max_loss = (debit * _CONTRACT_MULTIPLIER).quantize(_CENTS, rounding=ROUND_HALF_UP)
    quote_timestamp = min(long_leg.quote_timestamp, short_leg.quote_timestamp)
    structure = "call_debit_spread" if direction == "bullish" else "put_debit_spread"
    return SpreadCandidate(
        underlying=chain.underlying,
        expiration=long_leg.expiration,
        long_leg=OptionLeg(symbol=long_leg.symbol, side=OrderSide.BUY, ratio=1),
        short_leg=OptionLeg(symbol=short_leg.symbol, side=OrderSide.SELL, ratio=1),
        net_debit=debit,
        max_loss=max_loss,
        quote_timestamp=quote_timestamp,
        metadata={
            "structure": structure,
            "feed": chain.feed,
            "long_delta": str(long_leg.delta),
            "short_delta": str(short_leg.delta),
            "long_strike": str(long_leg.strike),
            "short_strike": str(short_leg.strike),
        },
    )
