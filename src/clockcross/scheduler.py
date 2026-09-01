from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel

from clockcross.agent.adjudicator import AgentContext
from clockcross.alpaca.mcp import McpContextRequest, McpToolRequest
from clockcross.alpaca.options import OptionChainSnapshot, evaluate_option_feasibility
from clockcross.domain import (
    AgentAction,
    AgentDecision,
    EpisodeState,
    FeatureVector,
    RiskDecision,
    SpreadCandidate,
)
from clockcross.ledger import Ledger
from clockcross.trading.constructor import (
    ConstructionPolicy,
    construct_vertical,
    direction_from_agent,
)
from clockcross.trading.execution import ExecutionResult, IndeterminateOrderError

RunMode = Literal["dry-run", "paper"]


class SignalEvidence(BaseModel):
    approved: bool
    reason: str
    residual_z: float | None = None
    historical_mean_signed_return: float | None = None


@dataclass(frozen=True)
class EpisodeSummary:
    episode_id: str
    state: EpisodeState
    reason: str | None = None
    decision: AgentDecision | None = None
    candidate: SpreadCandidate | None = None
    risk: RiskDecision | None = None
    order: ExecutionResult | None = None


class ReadinessGate(Protocol):
    def require_ready(self, *, mode: RunMode) -> None: ...


class ApprovedMutationGate:
    """Require the immutable research MUTATE artifact and approved COIN amendment."""

    CANONICAL_MUTATION_ID = "coin-options-2026-08-29"

    def __init__(
        self,
        *,
        verdict_path: str | Path,
        mutation_spec_path: str | Path,
        expected_config_hash: str,
        mutation_id: str,
    ) -> None:
        self._verdict_path = Path(verdict_path)
        self._mutation_spec_path = Path(mutation_spec_path)
        self._expected_config_hash = expected_config_hash
        self._mutation_id = mutation_id

    def require_ready(self, *, mode: RunMode) -> None:
        if self._mutation_id != self.CANONICAL_MUTATION_ID:
            raise RuntimeError("unapproved strategy mutation id")
        if not self._mutation_spec_path.is_file():
            raise RuntimeError("approved mutation spec is missing")
        if not self._verdict_path.is_file():
            raise RuntimeError("research verdict artifact is missing")
        try:
            payload = json.loads(self._verdict_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("research verdict artifact is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("verdict") != "MUTATE":
            raise RuntimeError("ClockCross paper mode requires the approved MUTATE verdict")
        if (
            payload.get("historical_stock_feed") != "sip"
            or payload.get("live_stock_feed") != "delayed_sip"
        ):
            raise RuntimeError("research/live feed metadata does not match the frozen SIP policy")
        expected_clock = {
            "feature_freeze_et": "09:25:00",
            "confirmation_end_et": "09:40:00",
            "decision_time_et": "09:55:00",
        }
        for key, expected in expected_clock.items():
            if payload.get(key) != expected:
                raise RuntimeError(f"research timing metadata drifted: {key}")
        symbols = payload.get("symbols")
        if not isinstance(symbols, dict):
            raise RuntimeError("research verdict is missing COIN evidence")
        coin = symbols.get("COIN")
        if not isinstance(coin, dict) or coin.get("verdict") != "MUTATE":
            raise RuntimeError("COIN evidence is not the approved MUTATE result")
        metadata = coin.get("metadata")
        if (
            not isinstance(metadata, dict)
            or metadata.get("config_hash") != self._expected_config_hash
        ):
            raise RuntimeError("research config hash does not match the frozen configuration")


class SignalGateway(Protocol):
    def collect_premarket(self, session_date: date) -> FeatureVector | None: ...
    def opening_confirmation(self, features: FeatureVector) -> FeatureVector | None: ...
    def evaluate(self, features: FeatureVector) -> SignalEvidence: ...


class ChainGateway(Protocol):
    def get_chain(self, underlying: str, *, now: datetime) -> OptionChainSnapshot: ...


class PortfolioGateway(Protocol):
    def current(self) -> Any: ...


class RiskGateway(Protocol):
    def max_candidate_net_debit(self, portfolio: Any) -> Decimal: ...
    def evaluate(
        self, candidate: SpreadCandidate, portfolio: Any, *, now: datetime
    ) -> RiskDecision: ...


class ExecutionGateway(Protocol):
    def submit(
        self, episode_id: str, candidate: SpreadCandidate, risk: RiskDecision
    ) -> ExecutionResult: ...
    def reconcile(self, order: Any) -> ExecutionResult: ...


def _news_summary(evidence: Any) -> str:
    payloads: list[Any] = []
    for item in evidence.items:
        if item.tool_name == "get_news" and item.success:
            payloads.append(item.content)
    text = json.dumps(payloads, sort_keys=True, default=str, separators=(",", ":"))
    return text[:1600]


class Scheduler:
    """One-session state-driven orchestrator; no background threads or hidden retries."""

    def __init__(
        self,
        *,
        ledger: Ledger,
        readiness_gate: ReadinessGate | None,
        signal_gateway: SignalGateway | None,
        chain_gateway: ChainGateway | None,
        mcp_gateway: Any,
        adjudicator: Any,
        portfolio_gateway: PortfolioGateway,
        risk_governor: RiskGateway | None,
        execution: ExecutionGateway,
        now: Callable[[], datetime],
    ) -> None:
        self._ledger = ledger
        self._readiness = readiness_gate
        self._signal = signal_gateway
        self._chains = chain_gateway
        self._mcp = mcp_gateway
        self._ai = adjudicator
        self._portfolio = portfolio_gateway
        self._risk = risk_governor
        self._execution = execution
        self._now = now

    def _abstain(self, episode_id: str, reason: str) -> EpisodeSummary:
        record = self._ledger.transition(
            episode_id,
            EpisodeState.ABSTAINED,
            event="abstain",
            payload={"reason": reason},
        )
        return EpisodeSummary(episode_id=episode_id, state=record.state, reason=reason)

    def _resume_submitted(self, episode_id: str) -> EpisodeSummary:
        order = self._ledger.get_latest_order_for_episode(episode_id)
        if order is None:
            raise RuntimeError("ORDER_SUBMITTED episode has no durable order identity")
        result = self._execution.reconcile(order)
        status = result.status.lower()
        state = EpisodeState.ORDER_SUBMITTED
        if status in {"filled", "partially_filled"}:
            if status == "filled":
                self._ledger.transition(
                    episode_id, EpisodeState.ORDER_FILLED, event="reconciled_filled"
                )
                self._ledger.transition(
                    episode_id, EpisodeState.MONITORING, event="begin_monitoring"
                )
                state = EpisodeState.MONITORING
        elif status in {"canceled", "cancelled", "expired"}:
            self._ledger.transition(
                episode_id, EpisodeState.ORDER_CANCELLED, event="reconciled_cancelled"
            )
            self._ledger.transition(
                episode_id, EpisodeState.CLOSED, event="closed_after_cancel"
            )
            state = EpisodeState.CLOSED
        elif status in {"rejected", "suspended"}:
            self._ledger.transition(
                episode_id, EpisodeState.ORDER_REJECTED, event="reconciled_rejected"
            )
            self._ledger.transition(
                episode_id, EpisodeState.CLOSED, event="closed_after_reject"
            )
            state = EpisodeState.CLOSED
        return EpisodeSummary(episode_id=episode_id, state=state, order=result)

    def reconcile_session(self, session_date: date) -> EpisodeSummary:
        episode = self._ledger.get_open_episode(session_date, "COIN")
        if episode is None or episode.state is not EpisodeState.ORDER_SUBMITTED:
            raise RuntimeError("reconcile requires an existing ORDER_SUBMITTED COIN episode")
        return self._resume_submitted(episode.episode_id)

    def run_session(
        self, session_date: date, *, mode: RunMode = "dry-run"
    ) -> EpisodeSummary:
        if (
            self._readiness is None
            or self._signal is None
            or self._chains is None
            or self._mcp is None
            or self._ai is None
            or self._risk is None
        ):
            raise RuntimeError("full runtime dependencies are required for run_session")
        self._readiness.require_ready(mode=mode)
        episode = self._ledger.create_episode(session_date, "COIN")

        if episode.state is EpisodeState.ORDER_SUBMITTED:
            return self._resume_submitted(episode.episode_id)
        if episode.state in {EpisodeState.ABSTAINED, EpisodeState.CLOSED}:
            return EpisodeSummary(
                episode_id=episode.episode_id,
                state=episode.state,
                reason="terminal_episode",
            )
        if episode.state is not EpisodeState.COLLECTING:
            raise RuntimeError(f"cannot safely resume episode from {episode.state.value}")

        premarket = self._signal.collect_premarket(session_date)
        if premarket is None or premarket.underlying != "COIN":
            return self._abstain(episode.episode_id, "premarket_features_unavailable")
        self._ledger.transition(
            episode.episode_id,
            EpisodeState.FEATURES_FROZEN,
            event="features_frozen",
        )

        features = self._signal.opening_confirmation(premarket)
        if features is None or features.opening_10m_return is None:
            return self._abstain(
                episode.episode_id, "opening_confirmation_unavailable"
            )
        self._ledger.record_features(episode.episode_id, features)
        self._ledger.transition(
            episode.episode_id,
            EpisodeState.OPENING_CONFIRMATION,
            event="opening_confirmation_complete",
        )

        evidence = self._signal.evaluate(features)
        if not evidence.approved:
            return self._abstain(episode.episode_id, evidence.reason)
        self._ledger.transition(
            episode.episode_id,
            EpisodeState.CANDIDATE_READY,
            event="cross_market_evidence_passed",
            payload={"reason": evidence.reason},
        )

        now = self._now()
        if now.tzinfo is None:
            return self._abstain(episode.episode_id, "naive_runtime_clock")
        chain = self._chains.get_chain("COIN", now=now)
        feasibility = evaluate_option_feasibility(chain, now=now)
        self._ledger.record_mark(
            episode.episode_id,
            marked_at=now,
            value="option_feasibility",
            payload=feasibility.model_dump(mode="json"),
        )
        if not feasibility.feasible:
            reason = (
                feasibility.reasons[0]
                if feasibility.reasons
                else "option_surface_unavailable"
            )
            return self._abstain(episode.episode_id, reason)

        mcp_request = McpContextRequest(
            calls=(
                McpToolRequest(name="get_news", arguments={"symbols": "COIN"}),
                McpToolRequest(name="get_clock", arguments={}),
            )
        )
        mcp_evidence = self._mcp.collect_context(mcp_request)
        self._ledger.record_mark(
            episode.episode_id,
            marked_at=now,
            value="mcp_evidence",
            payload={
                "complete": mcp_evidence.complete,
                "items": [
                    item.model_dump(mode="json", exclude={"content"})
                    for item in mcp_evidence.items
                ],
            },
        )
        if not mcp_evidence.complete:
            return self._abstain(episode.episode_id, "mcp_context_unavailable")

        if features.residual == 0:
            return self._abstain(episode.episode_id, "zero_residual")
        context = AgentContext(
            underlying="COIN",
            residual=features.residual,
            residual_z=evidence.residual_z,
            residual_sign=1 if features.residual > 0 else -1,
            btc_return=features.btc_return,
            opening_10m_return=features.opening_10m_return,
            historical_mean_signed_return=evidence.historical_mean_signed_return,
            option_feed=chain.feed,
            available_structures=feasibility.available_structures,
            news_summary=_news_summary(mcp_evidence),
        )
        decision = self._ai.decide(context)
        self._ledger.record_decision(episode.episode_id, decision)
        self._ledger.transition(
            episode.episode_id,
            EpisodeState.AI_REVIEWED,
            event="ai_adjudicated",
            payload={"action": decision.action.value},
        )
        if decision.action is AgentAction.ABSTAIN:
            return self._abstain(episode.episode_id, decision.reason)

        direction = direction_from_agent(decision.action, context.residual_sign)
        if direction is None:
            return self._abstain(episode.episode_id, "no_direction")

        portfolio = self._portfolio.current()
        max_net_debit = self._risk.max_candidate_net_debit(portfolio)
        if max_net_debit <= 0:
            return self._abstain(episode.episode_id, "risk_budget_exhausted")
        candidate = construct_vertical(
            chain,
            direction=direction,
            now=now,
            policy=ConstructionPolicy(max_net_debit=max_net_debit),
        )
        if candidate is None:
            return self._abstain(episode.episode_id, "no_constructible_vertical")

        exposure_keys = (
            "long_delta",
            "short_delta",
            "net_delta",
            "net_debit",
            "delta_per_debit",
        )
        self._ledger.record_mark(
            episode.episode_id,
            marked_at=now,
            value="spread_candidate",
            payload={key: candidate.metadata[key] for key in exposure_keys},
        )

        risk = self._risk.evaluate(candidate, portfolio, now=now)
        self._ledger.record_risk(episode.episode_id, risk)
        if not risk.approved:
            reason = risk.reasons[0] if risk.reasons else "risk_rejected"
            return self._abstain(episode.episode_id, reason)
        self._ledger.transition(
            episode.episode_id,
            EpisodeState.RISK_APPROVED,
            event="risk_approved",
            payload={"max_loss": str(risk.max_loss)},
        )

        if mode == "dry-run":
            return EpisodeSummary(
                episode_id=episode.episode_id,
                state=EpisodeState.RISK_APPROVED,
                reason="dry_run_would_submit",
                decision=decision,
                candidate=candidate,
                risk=risk,
            )

        self._ledger.transition(
            episode.episode_id,
            EpisodeState.ORDER_SUBMITTED,
            event="submission_started",
        )
        try:
            order = self._execution.submit(episode.episode_id, candidate, risk)
        except IndeterminateOrderError:
            return EpisodeSummary(
                episode_id=episode.episode_id,
                state=EpisodeState.ORDER_SUBMITTED,
                reason="order_indeterminate",
                decision=decision,
                candidate=candidate,
                risk=risk,
            )
        except Exception:
            self._ledger.transition(
                episode.episode_id,
                EpisodeState.ORDER_REJECTED,
                event="submission_failed",
            )
            self._ledger.transition(
                episode.episode_id,
                EpisodeState.CLOSED,
                event="closed_after_submission_failure",
            )
            raise

        if self._ledger.get_order_by_client_id(order.client_order_id) is None:
            self._ledger.record_order(
                episode.episode_id,
                client_order_id=order.client_order_id,
                alpaca_order_id=order.alpaca_order_id,
                status=order.status,
            )
        return EpisodeSummary(
            episode_id=episode.episode_id,
            state=EpisodeState.ORDER_SUBMITTED,
            decision=decision,
            candidate=candidate,
            risk=risk,
            order=order,
        )
