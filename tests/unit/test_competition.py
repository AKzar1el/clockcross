from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from clockcross.competition import CompetitionOrchestrator, CompetitionPolicy
from clockcross.domain import EpisodeState
from clockcross.ledger import Ledger
from clockcross.scheduler import EpisodeSummary
from clockcross.trading.execution import CloseInstruction, ExecutionResult

ET = ZoneInfo("America/New_York")
SESSION = date(2026, 8, 31)
LONG = "COIN260911C00300000"
SHORT = "COIN260911C00310000"


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += timedelta(seconds=seconds)


class FakeScheduler:
    def __init__(self, ledger: Ledger, *, statuses: list[str] | None = None) -> None:
        self.ledger = ledger
        self.statuses = list(statuses or ["filled"])
        self.last_status = self.statuses[-1] if self.statuses else "accepted"
        self.run_session_calls = 0
        self.reconcile_calls = 0
        self.cancelled = False

    def _seed_opening(self, day: date) -> str:
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
        self.ledger.record_order(
            episode.episode_id,
            client_order_id=f"open-{day.isoformat()}",
            alpaca_order_id="alpaca-open",
            status="accepted",
            payload={
                "phase": "open",
                "long_leg": LONG,
                "short_leg": SHORT,
            },
        )
        return episode.episode_id

    def run_session(self, day: date, *, mode: str) -> EpisodeSummary:
        self.run_session_calls += 1
        assert mode == "paper"
        episode_id = self._seed_opening(day)
        order = self.ledger.get_latest_order_for_phase(episode_id, "open")
        assert order is not None
        return EpisodeSummary(
            episode_id=episode_id,
            state=EpisodeState.ORDER_SUBMITTED,
            order=ExecutionResult(order.client_order_id, order.alpaca_order_id, order.status, False),
        )

    def reconcile_session(self, day: date) -> EpisodeSummary:
        self.reconcile_calls += 1
        episode = self.ledger.get_open_episode(day, "COIN")
        assert episode is not None
        order = self.ledger.get_latest_order_for_phase(episode.episode_id, "open")
        assert order is not None
        if self.cancelled:
            status = "canceled"
        elif self.statuses:
            status = self.statuses.pop(0)
            self.last_status = status
        else:
            status = self.last_status
        self.ledger.update_order(
            order.client_order_id,
            alpaca_order_id=order.alpaca_order_id,
            status=status,
            payload={**order.payload, "provider_status": status},
        )
        if status == "filled" and episode.state is EpisodeState.ORDER_SUBMITTED:
            self.ledger.transition(episode.episode_id, EpisodeState.ORDER_FILLED, event="filled")
            self.ledger.transition(episode.episode_id, EpisodeState.MONITORING, event="monitor")
            state = EpisodeState.MONITORING
        elif status in {"canceled", "cancelled"} and episode.state is EpisodeState.ORDER_SUBMITTED:
            self.ledger.transition(episode.episode_id, EpisodeState.ORDER_CANCELLED, event="cancelled")
            self.ledger.transition(episode.episode_id, EpisodeState.CLOSED, event="closed")
            state = EpisodeState.CLOSED
        else:
            state = episode.state
        return EpisodeSummary(
            episode_id=episode.episode_id,
            state=state,
            order=ExecutionResult(order.client_order_id, order.alpaca_order_id, status, True),
        )


class FakeTrading:
    def __init__(self, scheduler: FakeScheduler, *, prove_cancel: bool = True) -> None:
        self.scheduler = scheduler
        self.prove_cancel = prove_cancel
        self.cancel_count = 0

    def cancel_order(self, order_id: str) -> None:
        assert order_id
        self.cancel_count += 1
        if self.prove_cancel:
            self.scheduler.cancelled = True


class FakeChains:
    def __init__(self) -> None:
        self.calls = 0

    def get_chain(self, underlying: str, *, now: datetime):
        self.calls += 1
        assert underlying == "COIN"
        return object()


class FakeExecution:
    def __init__(self, ledger: Ledger, *, reconcile_status: str = "filled") -> None:
        self.ledger = ledger
        self.reconcile_status = reconcile_status
        self.submit_close_count = 0
        self.close_instructions: list[CloseInstruction] = []
        self.reconcile_count = 0

    def submit_close(self, episode_id: str, instruction: CloseInstruction) -> ExecutionResult:
        self.submit_close_count += 1
        self.close_instructions.append(instruction)
        client_id = f"close-{instruction.attempt}"
        self.ledger.record_order(
            episode_id,
            client_order_id=client_id,
            alpaca_order_id=f"alpaca-{client_id}",
            status="filled",
            payload={
                "phase": "close",
                "attempt": instruction.attempt,
                "long_leg": instruction.long_symbol,
                "short_leg": instruction.short_symbol,
            },
        )
        return ExecutionResult(client_id, f"alpaca-{client_id}", "filled", False)

    def reconcile(self, order) -> ExecutionResult:
        self.reconcile_count += 1
        self.ledger.update_order(
            order.client_order_id,
            alpaca_order_id=order.alpaca_order_id,
            status=self.reconcile_status,
            payload={**order.payload, "provider_status": self.reconcile_status},
        )
        return ExecutionResult(
            order.client_order_id,
            order.alpaca_order_id,
            self.reconcile_status,
            True,
        )


def close_builder(chain, *, long_symbol: str, short_symbol: str, now: datetime, attempt: int):
    return CloseInstruction(
        long_symbol=long_symbol,
        short_symbol=short_symbol,
        limit_price="-1.00" if attempt == 0 else "-0.01",
        quote_timestamp=now,
        attempt=attempt,
    )


def seed_monitoring(ledger: Ledger, day: date = SESSION) -> str:
    scheduler = FakeScheduler(ledger)
    episode_id = scheduler._seed_opening(day)
    ledger.transition(episode_id, EpisodeState.ORDER_FILLED, event="filled")
    ledger.transition(episode_id, EpisodeState.MONITORING, event="monitor")
    return episode_id


def build_orchestrator(
    ledger: Ledger,
    clock: FakeClock,
    *,
    scheduler: FakeScheduler | None = None,
    trading: FakeTrading | None = None,
    execution: FakeExecution | None = None,
    policy: CompetitionPolicy | None = None,
):
    actual_scheduler = scheduler or FakeScheduler(ledger)
    actual_trading = trading or FakeTrading(actual_scheduler)
    actual_execution = execution or FakeExecution(ledger)
    return CompetitionOrchestrator(
        ledger=ledger,
        scheduler=actual_scheduler,
        chain_gateway=FakeChains(),
        trading=actual_trading,
        execution=actual_execution,
        policy=policy or CompetitionPolicy(),
        now=clock,
        sleeper=clock.sleep,
        close_builder=close_builder,
    )


def test_prior_unresolved_coin_episode_blocks_new_session(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    old = ledger.create_episode(date(2026, 8, 31), "COIN")
    ledger.transition(old.episode_id, EpisodeState.FEATURES_FROZEN, event="freeze")
    clock = FakeClock(datetime(2026, 9, 1, 9, 57, tzinfo=ET))
    orchestrator = build_orchestrator(ledger, clock)
    with pytest.raises(RuntimeError, match="unresolved COIN lifecycle"):
        orchestrator.run(date(2026, 9, 1))
    ledger.close()


def test_accepted_open_order_is_polled_until_filled_then_exited(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    scheduler = FakeScheduler(ledger, statuses=["accepted", "filled"])
    execution = FakeExecution(ledger)
    clock = FakeClock(datetime(2026, 8, 31, 9, 57, tzinfo=ET))
    orchestrator = build_orchestrator(
        ledger, clock, scheduler=scheduler, execution=execution
    )
    result = orchestrator.run(SESSION)
    assert result.entry_order_status == "filled"
    assert result.close_order_status == "filled"
    assert result.state is EpisodeState.CLOSED
    assert scheduler.run_session_calls == 1
    assert scheduler.reconcile_calls == 2
    assert execution.submit_close_count == 1
    ledger.close()


def test_unfilled_open_order_is_cancelled_after_180_seconds_and_proven_closed(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    scheduler = FakeScheduler(ledger, statuses=["accepted"])
    trading = FakeTrading(scheduler, prove_cancel=True)
    clock = FakeClock(datetime(2026, 8, 31, 9, 57, tzinfo=ET))
    orchestrator = build_orchestrator(
        ledger,
        clock,
        scheduler=scheduler,
        trading=trading,
        policy=CompetitionPolicy(open_fill_seconds=180, poll_seconds=30),
    )
    result = orchestrator.run(SESSION)
    assert trading.cancel_count == 1
    assert result.state is EpisodeState.CLOSED
    assert result.reason == "opening_order_unfilled_cancelled"
    ledger.close()


def test_unproven_open_cancel_never_closes_episode(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    scheduler = FakeScheduler(ledger, statuses=["accepted"])
    trading = FakeTrading(scheduler, prove_cancel=False)
    clock = FakeClock(datetime(2026, 8, 31, 9, 57, tzinfo=ET))
    orchestrator = build_orchestrator(
        ledger,
        clock,
        scheduler=scheduler,
        trading=trading,
        policy=CompetitionPolicy(
            open_fill_seconds=60,
            poll_seconds=10,
            cancel_confirm_seconds=20,
        ),
    )
    with pytest.raises(RuntimeError, match="cancellation"):
        orchestrator.run(SESSION)
    episode = ledger.get_open_episode(SESSION, "COIN")
    assert episode is not None and episode.state is EpisodeState.ORDER_SUBMITTED
    ledger.close()


def test_monitoring_waits_until_1055_then_submits_exact_close(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    seed_monitoring(ledger)
    scheduler = FakeScheduler(ledger)
    execution = FakeExecution(ledger)
    clock = FakeClock(datetime(2026, 8, 31, 10, 54, 50, tzinfo=ET))
    orchestrator = build_orchestrator(
        ledger, clock, scheduler=scheduler, execution=execution
    )
    result = orchestrator.run(SESSION)
    assert clock.current >= datetime(2026, 8, 31, 10, 55, tzinfo=ET)
    assert execution.close_instructions[0].long_symbol == LONG
    assert execution.close_instructions[0].short_symbol == SHORT
    assert result.state is EpisodeState.CLOSED
    assert scheduler.run_session_calls == 0
    assert scheduler.reconcile_calls == 0
    ledger.close()


def test_restart_from_monitoring_does_not_invoke_signal_or_llm_path(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    seed_monitoring(ledger)
    scheduler = FakeScheduler(ledger)
    execution = FakeExecution(ledger)
    clock = FakeClock(datetime(2026, 8, 31, 10, 55, tzinfo=ET))
    result = build_orchestrator(
        ledger, clock, scheduler=scheduler, execution=execution
    ).run(SESSION)
    assert result.state is EpisodeState.CLOSED
    assert scheduler.run_session_calls == 0
    assert scheduler.reconcile_calls == 0
    assert execution.submit_close_count == 1
    ledger.close()


def test_restart_from_exit_submitted_reconciles_only_existing_close(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode_id = seed_monitoring(ledger)
    ledger.transition(episode_id, EpisodeState.EXIT_SUBMITTED, event="exit_submitted")
    ledger.record_order(
        episode_id,
        client_order_id="close-0",
        alpaca_order_id="alpaca-close-0",
        status="accepted",
        payload={"phase": "close", "attempt": 0, "long_leg": LONG, "short_leg": SHORT},
    )
    scheduler = FakeScheduler(ledger)
    execution = FakeExecution(ledger, reconcile_status="filled")
    clock = FakeClock(datetime(2026, 8, 31, 10, 56, tzinfo=ET))
    result = build_orchestrator(
        ledger, clock, scheduler=scheduler, execution=execution
    ).run(SESSION)
    assert result.state is EpisodeState.CLOSED
    assert execution.submit_close_count == 0
    assert execution.reconcile_count == 1
    assert scheduler.run_session_calls == 0
    ledger.close()
