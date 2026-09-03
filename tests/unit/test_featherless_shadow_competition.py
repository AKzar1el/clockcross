from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from clockcross.agent.adjudicator import AgentContext
from clockcross.agent.shadow import ShadowAudit
from clockcross.competition import CompetitionOrchestrator, CompetitionPolicy
from clockcross.domain import AgentAction, AgentDecision, AgentDriver, EpisodeState
from clockcross.ledger import Ledger
from clockcross.scheduler import EpisodeSummary
from clockcross.trading.execution import CloseInstruction, ExecutionResult

ET = ZoneInfo("America/New_York")
SESSION = date(2026, 9, 4)
LONG = "COIN260911C00300000"
SHORT = "COIN260911C00310000"


def primary_decision() -> AgentDecision:
    return AgentDecision(
        action=AgentAction.CONTINUATION,
        confidence=0.7,
        driver=AgentDriver.CRYPTO_CROSS_MARKET,
        reason="Primary.",
    )


def agent_context() -> AgentContext:
    return AgentContext(
        underlying="COIN",
        residual=0.02,
        residual_sign=1,
        btc_return=0.01,
        opening_10m_return=0.005,
        historical_mean_signed_return=0.0027,
        option_feed="indicative",
        available_structures=("call_debit_spread",),
        news_summary="[]",
    )


def seed_shadow_input(ledger: Ledger, episode_id: str, now: datetime) -> None:
    ledger.record_mark(
        episode_id,
        marked_at=now,
        value="featherless_shadow_input",
        payload={
            "context": agent_context().model_dump(mode="json"),
            "authoritative_decision": primary_decision().model_dump(mode="json"),
        },
    )


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class FakeShadow:
    def __init__(self) -> None:
        self.calls: list[tuple[AgentContext, AgentDecision]] = []

    def observe(self, context: AgentContext, authoritative: AgentDecision) -> ShadowAudit:
        self.calls.append((context, authoritative))
        return ShadowAudit(
            status="ok",
            model="zai-org/GLM-5.3",
            decision=AgentDecision(
                action=AgentAction.REVERSION,
                confidence=0.6,
                driver=AgentDriver.MACRO,
                reason="Independent disagreement.",
            ),
            action_agreement=False,
            driver_agreement=False,
            idiosyncratic_news_agreement=True,
            reason="observed",
        )


class FilledScheduler:
    def __init__(self, ledger: Ledger, shadow: FakeShadow) -> None:
        self.ledger = ledger
        self.shadow = shadow
        self.reconciled = False

    def run_session(self, day: date, *, mode: str) -> EpisodeSummary:
        assert mode == "paper"
        episode = self.ledger.create_episode(day, "COIN")
        for state in (
            EpisodeState.FEATURES_FROZEN,
            EpisodeState.OPENING_CONFIRMATION,
            EpisodeState.CANDIDATE_READY,
            EpisodeState.AI_REVIEWED,
            EpisodeState.RISK_APPROVED,
            EpisodeState.ORDER_SUBMITTED,
        ):
            self.ledger.transition(episode.episode_id, state, event="test")
        seed_shadow_input(
            self.ledger,
            episode.episode_id,
            datetime(2026, 9, 4, 9, 55, tzinfo=ET),
        )
        order = self.ledger.record_order(
            episode.episode_id,
            client_order_id="open",
            alpaca_order_id="alpaca-open",
            status="accepted",
            payload={"phase": "open", "long_leg": LONG, "short_leg": SHORT},
        )
        return EpisodeSummary(
            episode_id=episode.episode_id,
            state=EpisodeState.ORDER_SUBMITTED,
            order=ExecutionResult(order.client_order_id, order.alpaca_order_id, "accepted", False),
        )

    def reconcile_session(self, day: date) -> EpisodeSummary:
        assert self.shadow.calls == [], "shadow must not run before opening fill is resolved"
        episode = self.ledger.get_open_episode(day, "COIN")
        assert episode is not None
        order = self.ledger.get_latest_order_for_phase(episode.episode_id, "open")
        assert order is not None
        if not self.reconciled:
            self.reconciled = True
            self.ledger.update_order(
                order.client_order_id,
                alpaca_order_id=order.alpaca_order_id,
                status="filled",
                payload=order.payload,
            )
            self.ledger.transition(episode.episode_id, EpisodeState.ORDER_FILLED, event="filled")
            self.ledger.transition(episode.episode_id, EpisodeState.MONITORING, event="monitor")
        return EpisodeSummary(
            episode_id=episode.episode_id,
            state=EpisodeState.MONITORING,
            order=ExecutionResult(order.client_order_id, order.alpaca_order_id, "filled", True),
        )


class AbstainingAfterAiScheduler:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def run_session(self, day: date, *, mode: str) -> EpisodeSummary:
        assert mode == "paper"
        episode = self.ledger.create_episode(day, "COIN")
        for state in (
            EpisodeState.FEATURES_FROZEN,
            EpisodeState.OPENING_CONFIRMATION,
            EpisodeState.CANDIDATE_READY,
            EpisodeState.AI_REVIEWED,
        ):
            self.ledger.transition(episode.episode_id, state, event="test")
        seed_shadow_input(
            self.ledger,
            episode.episode_id,
            datetime(2026, 9, 4, 9, 55, tzinfo=ET),
        )
        self.ledger.transition(episode.episode_id, EpisodeState.ABSTAINED, event="primary_abstain")
        return EpisodeSummary(
            episode_id=episode.episode_id,
            state=EpisodeState.ABSTAINED,
            reason="primary_abstain",
            decision=primary_decision().model_copy(update={"action": AgentAction.ABSTAIN}),
        )


class FakeTrading:
    def cancel_order(self, order_id: str) -> None:
        raise AssertionError("cancel not expected")


class FakeChains:
    def get_chain(self, underlying: str, *, now: datetime) -> object:
        assert underlying == "COIN"
        return object()


class FakeExecution:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger

    def submit_close(self, episode_id: str, instruction: CloseInstruction) -> ExecutionResult:
        order = self.ledger.record_order(
            episode_id,
            client_order_id="close",
            alpaca_order_id="alpaca-close",
            status="filled",
            payload={
                "phase": "close",
                "attempt": instruction.attempt,
                "long_leg": instruction.long_symbol,
                "short_leg": instruction.short_symbol,
            },
        )
        return ExecutionResult(order.client_order_id, order.alpaca_order_id, "filled", False)

    def reconcile(self, order: object) -> ExecutionResult:
        raise AssertionError("close reconciliation not expected")


def close_builder(
    chain: object,
    *,
    long_symbol: str,
    short_symbol: str,
    now: datetime,
    attempt: int,
) -> CloseInstruction:
    return CloseInstruction(
        long_symbol=long_symbol,
        short_symbol=short_symbol,
        limit_price="-1.00",
        quote_timestamp=now,
        attempt=attempt,
    )


def build(
    ledger: Ledger,
    clock: FakeClock,
    scheduler: object,
    shadow: FakeShadow,
) -> CompetitionOrchestrator:
    return CompetitionOrchestrator(
        ledger=ledger,
        scheduler=scheduler,
        chain_gateway=FakeChains(),
        trading=FakeTrading(),
        execution=FakeExecution(ledger),
        policy=CompetitionPolicy(poll_seconds=60),
        now=clock,
        sleeper=clock.sleep,
        close_builder=close_builder,
        shadow_observer=shadow,
    )


def test_shadow_runs_only_after_opening_order_is_filled_and_is_persisted(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    shadow = FakeShadow()
    scheduler = FilledScheduler(ledger, shadow)
    clock = FakeClock(datetime(2026, 9, 4, 9, 57, tzinfo=ET))
    try:
        result = build(ledger, clock, scheduler, shadow).run(SESSION)

        assert result.state is EpisodeState.CLOSED
        assert len(shadow.calls) == 1
        audit = ledger.get_latest_mark_payload(result.session_date.isoformat() if False else ledger.get_episode_for_session(SESSION, "COIN").episode_id, "featherless_shadow")
        assert audit is not None
        assert audit["status"] == "ok"
        assert audit["action_agreement"] is False
    finally:
        ledger.close()


def test_primary_abstention_is_returned_unchanged_even_when_shadow_disagrees(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    shadow = FakeShadow()
    scheduler = AbstainingAfterAiScheduler(ledger)
    clock = FakeClock(datetime(2026, 9, 4, 9, 57, tzinfo=ET))
    try:
        result = build(ledger, clock, scheduler, shadow).run(SESSION)

        assert result.state is EpisodeState.ABSTAINED
        assert result.reason == "primary_abstain"
        assert len(shadow.calls) == 1
        episode = ledger.get_episode_for_session(SESSION, "COIN")
        assert episode is not None
        assert ledger.count_rows("orders") == 0
        assert ledger.get_latest_mark_payload(episode.episode_id, "featherless_shadow") is not None
    finally:
        ledger.close()


def test_existing_shadow_audit_makes_observation_idempotent(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    shadow = FakeShadow()
    scheduler = FilledScheduler(ledger, shadow)
    original = scheduler.run_session

    def seeded(day: date, *, mode: str) -> EpisodeSummary:
        summary = original(day, mode=mode)
        ledger.record_mark(
            summary.episode_id,
            marked_at=datetime(2026, 9, 4, 9, 55, tzinfo=ET),
            value="featherless_shadow",
            payload={"status": "ok", "reason": "already_recorded"},
        )
        return summary

    scheduler.run_session = seeded  # type: ignore[method-assign]
    clock = FakeClock(datetime(2026, 9, 4, 9, 57, tzinfo=ET))
    try:
        result = build(ledger, clock, scheduler, shadow).run(SESSION)
        assert result.state is EpisodeState.CLOSED
        assert shadow.calls == []
    finally:
        ledger.close()


def test_resumed_monitoring_skips_remote_shadow_to_protect_exit_deadline(tmp_path) -> None:
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    shadow = FakeShadow()
    episode = ledger.create_episode(SESSION, "COIN")
    for state in (
        EpisodeState.FEATURES_FROZEN,
        EpisodeState.OPENING_CONFIRMATION,
        EpisodeState.CANDIDATE_READY,
        EpisodeState.AI_REVIEWED,
        EpisodeState.RISK_APPROVED,
        EpisodeState.ORDER_SUBMITTED,
        EpisodeState.ORDER_FILLED,
        EpisodeState.MONITORING,
    ):
        ledger.transition(episode.episode_id, state, event="test")
    seed_shadow_input(ledger, episode.episode_id, datetime(2026, 9, 4, 9, 55, tzinfo=ET))
    ledger.record_order(
        episode.episode_id,
        client_order_id="open",
        alpaca_order_id="alpaca-open",
        status="filled",
        payload={"phase": "open", "long_leg": LONG, "short_leg": SHORT},
    )
    clock = FakeClock(datetime(2026, 9, 4, 10, 54, 50, tzinfo=ET))
    try:
        result = build(ledger, clock, object(), shadow).run(SESSION)

        assert result.state is EpisodeState.CLOSED
        assert shadow.calls == []
        audit = ledger.get_latest_mark_payload(episode.episode_id, "featherless_shadow")
        assert audit == {"reason": "resume_monitoring_safety", "status": "skipped"}
        assert clock.current >= datetime(2026, 9, 4, 10, 55, tzinfo=ET)
    finally:
        ledger.close()
