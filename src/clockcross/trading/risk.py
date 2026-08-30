from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from clockcross.domain import RiskDecision, SpreadCandidate

ET = ZoneInfo("America/New_York")


class PortfolioState(BaseModel):
    starting_equity: Decimal = Field(gt=Decimal("0"))
    current_equity: Decimal = Field(gt=Decimal("0"))
    buying_power: Decimal = Field(ge=Decimal("0"))
    aggregate_defined_loss: Decimal = Field(ge=Decimal("0"))
    open_underlyings: tuple[str, ...] = ()


class RiskPolicy(BaseModel):
    approved_underlying: str = "COIN"
    per_position_loss_fraction: Decimal = Field(default=Decimal("0.01"), gt=0, le=1)
    aggregate_loss_fraction: Decimal = Field(default=Decimal("0.05"), gt=0, le=1)
    max_quote_age_seconds: int = Field(default=60, ge=1)
    entry_start_et: time = time(9, 55)
    entry_end_et: time = time(15, 30)
    final_entry_cutoff: datetime | None = None


class RiskGovernor:
    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy()

    def evaluate(
        self,
        candidate: SpreadCandidate,
        portfolio: PortfolioState,
        *,
        now: datetime,
    ) -> RiskDecision:
        reasons: list[str] = []
        aggregate_after = portfolio.aggregate_defined_loss + candidate.max_loss

        if now.tzinfo is None:
            reasons.append("naive_time")
            return RiskDecision(
                approved=False,
                reasons=reasons,
                max_loss=candidate.max_loss,
                aggregate_defined_loss=aggregate_after,
            )

        if candidate.underlying != self.policy.approved_underlying:
            reasons.append("underlying_not_approved")
        if candidate.underlying in portfolio.open_underlyings:
            reasons.append("underlying_already_open")

        position_cap = portfolio.starting_equity * self.policy.per_position_loss_fraction
        aggregate_cap = portfolio.starting_equity * self.policy.aggregate_loss_fraction
        if candidate.max_loss > position_cap:
            reasons.append("per_position_loss_cap")
        if aggregate_after > aggregate_cap:
            reasons.append("aggregate_loss_cap")
        if candidate.max_loss > portfolio.buying_power:
            reasons.append("insufficient_buying_power")

        age = (
            now.astimezone(timezone.utc)
            - candidate.quote_timestamp.astimezone(timezone.utc)
        ).total_seconds()
        if age < 0 or age > self.policy.max_quote_age_seconds:
            reasons.append("stale_quote")

        local_now = now.astimezone(ET)
        wall = local_now.time().replace(tzinfo=None)
        if wall < self.policy.entry_start_et or wall > self.policy.entry_end_et:
            reasons.append("outside_entry_window")

        if self.policy.final_entry_cutoff is not None:
            cutoff = self.policy.final_entry_cutoff
            if cutoff.tzinfo is None:
                raise ValueError("final_entry_cutoff must be timezone-aware")
            if now.astimezone(timezone.utc) >= cutoff.astimezone(timezone.utc):
                reasons.append("final_event_cutoff")

        return RiskDecision(
            approved=not reasons,
            reasons=reasons,
            max_loss=candidate.max_loss,
            aggregate_defined_loss=aggregate_after,
        )
