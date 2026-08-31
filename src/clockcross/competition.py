from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from clockcross.domain import EpisodeState
from clockcross.ledger import Ledger, OrderRecord
from clockcross.trading.execution import CloseInstruction, ExecutionResult

ET = ZoneInfo("America/New_York")


class CloseBuilder(Protocol):
    def __call__(
        self,
        chain: Any,
        *,
        long_symbol: str,
        short_symbol: str,
        now: datetime,
        attempt: int,
    ) -> CloseInstruction: ...


class CompetitionPolicy(BaseModel):
    open_fill_seconds: int = Field(default=180, gt=0)
    poll_seconds: int = Field(default=5, gt=0)
    cancel_confirm_seconds: int = Field(default=30, gt=0)
    entry_time_et: time = time(9, 55)
    exit_time_et: time = time(10, 55)
    close_fill_seconds: int = Field(default=120, gt=0)
    max_close_attempts: int = Field(default=2, ge=1, le=2)
    latest_entry_time_et: time = time(10, 5)


class CompetitionSessionResult(BaseModel):
    session_date: date
    state: EpisodeState
    reason: str | None = None
    entry_order_status: str | None = None
    close_order_status: str | None = None
    close_attempts: int = 0


class CompetitionOrchestrator:
    """Own one competition session from entry invocation through terminal spread exit."""

    def __init__(
        self,
        *,
        ledger: Ledger,
        scheduler: Any,
        chain_gateway: Any,
        trading: Any,
        execution: Any,
        policy: CompetitionPolicy | None = None,
        now: Callable[[], datetime],
        sleeper: Callable[[float], None],
        close_builder: CloseBuilder,
    ) -> None:
        self._ledger = ledger
        self._scheduler = scheduler
        self._chains = chain_gateway
        self._trading = trading
        self._execution = execution
        self._policy = policy or CompetitionPolicy()
        self._now = now
        self._sleep = sleeper
        self._close_builder = close_builder

    def _current_time(self) -> datetime:
        current = self._now()
        if current.tzinfo is None:
            raise RuntimeError("competition runtime clock must be timezone-aware")
        return current

    def _sleep_poll(self, deadline: datetime) -> None:
        current = self._current_time()
        remaining = (deadline - current).total_seconds()
        if remaining > 0:
            self._sleep(min(float(self._policy.poll_seconds), remaining))

    def _wait_until(self, target: datetime) -> None:
        while self._current_time() < target:
            self._sleep_poll(target)

    @staticmethod
    def _status(result: ExecutionResult | None, fallback: str | None = None) -> str | None:
        if result is None:
            return fallback
        return result.status.lower()

    def _result(
        self,
        session_date: date,
        state: EpisodeState,
        *,
        reason: str | None = None,
        entry_status: str | None = None,
        close_status: str | None = None,
        close_attempts: int = 0,
    ) -> CompetitionSessionResult:
        return CompetitionSessionResult(
            session_date=session_date,
            state=state,
            reason=reason,
            entry_order_status=entry_status,
            close_order_status=close_status,
            close_attempts=close_attempts,
        )

    def _prepare_new_session(self, session_date: date) -> CompetitionSessionResult | None:
        existing = self._ledger.get_episode_for_session(session_date, "COIN")
        if existing is not None and existing.state in {
            EpisodeState.ABSTAINED,
            EpisodeState.CLOSED,
        }:
            return self._result(session_date, existing.state, reason="terminal_episode")

        entry = datetime.combine(session_date, self._policy.entry_time_et, tzinfo=ET)
        latest = datetime.combine(session_date, self._policy.latest_entry_time_et, tzinfo=ET)
        self._wait_until(entry)
        if self._current_time() <= latest:
            return None

        episode = self._ledger.create_episode(session_date, "COIN")
        abstained = self._ledger.transition(
            episode.episode_id,
            EpisodeState.ABSTAINED,
            event="competition_entry_window_closed",
            payload={"latest_entry_time_et": self._policy.latest_entry_time_et.isoformat()},
        )
        return self._result(
            session_date,
            abstained.state,
            reason="competition_entry_window_closed",
        )

    def run(self, session_date: date) -> CompetitionSessionResult:
        unresolved = self._ledger.get_unresolved_episode("COIN")
        if unresolved is not None and unresolved.session_date != session_date:
            raise RuntimeError(
                "unresolved COIN lifecycle from prior session blocks new competition entry"
            )

        if unresolved is None:
            timing_result = self._prepare_new_session(session_date)
            if timing_result is not None:
                return timing_result
            summary = self._scheduler.run_session(session_date, mode="paper")
            if summary.state in {EpisodeState.ABSTAINED, EpisodeState.CLOSED}:
                return self._result(
                    session_date,
                    summary.state,
                    reason=summary.reason,
                    entry_status=self._status(summary.order),
                )
            episode = self._ledger.get_episode(summary.episode_id)
            if episode is None:
                raise RuntimeError("competition scheduler returned an unknown episode")
        else:
            episode = unresolved

        if episode.state is EpisodeState.ORDER_SUBMITTED:
            return self._manage_opening(session_date, episode.episode_id)
        if episode.state is EpisodeState.ORDER_FILLED:
            self._ledger.transition(
                episode.episode_id,
                EpisodeState.MONITORING,
                event="resume_filled_position",
            )
            episode = self._ledger.get_episode(episode.episode_id)
            assert episode is not None
        if episode.state is EpisodeState.MONITORING:
            open_order = self._require_open_order(episode.episode_id)
            return self._manage_monitoring(
                session_date,
                episode.episode_id,
                entry_status=open_order.status.lower(),
            )
        if episode.state is EpisodeState.EXIT_SUBMITTED:
            open_order = self._require_open_order(episode.episode_id)
            return self._manage_close(
                session_date,
                episode.episode_id,
                entry_status=open_order.status.lower(),
                initial=None,
            )
        if episode.state in {EpisodeState.ORDER_CANCELLED, EpisodeState.ORDER_REJECTED}:
            closed = self._ledger.transition(
                episode.episode_id,
                EpisodeState.CLOSED,
                event="resume_terminal_open_order",
            )
            return self._result(session_date, closed.state, reason="opening_order_terminal")
        if episode.state in {EpisodeState.ABSTAINED, EpisodeState.CLOSED}:
            return self._result(session_date, episode.state, reason="terminal_episode")

        raise RuntimeError(
            f"cannot safely resume competition episode from {episode.state.value}"
        )

    def _require_open_order(self, episode_id: str) -> OrderRecord:
        order = self._ledger.get_latest_order_for_phase(episode_id, "open")
        if order is None:
            raise RuntimeError("competition episode has no durable opening-order identity")
        return order

    def _manage_opening(
        self, session_date: date, episode_id: str
    ) -> CompetitionSessionResult:
        deadline = self._current_time() + __import__("datetime").timedelta(
            seconds=self._policy.open_fill_seconds
        )
        while True:
            summary = self._scheduler.reconcile_session(session_date)
            status = self._status(summary.order)
            if status == "partially_filled":
                raise RuntimeError("partially filled opening MLeg requires explicit reconciliation")
            if summary.state is EpisodeState.MONITORING:
                return self._manage_monitoring(
                    session_date, episode_id, entry_status=status or "filled"
                )
            if summary.state is EpisodeState.CLOSED:
                return self._result(
                    session_date,
                    EpisodeState.CLOSED,
                    reason="opening_order_terminal",
                    entry_status=status,
                )

            if self._current_time() >= deadline:
                order = self._require_open_order(episode_id)
                if order.alpaca_order_id is None:
                    raise RuntimeError("opening order has no proven Alpaca id for cancellation")
                self._trading.cancel_order(order.alpaca_order_id)
                cancel_deadline = self._current_time() + __import__("datetime").timedelta(
                    seconds=self._policy.cancel_confirm_seconds
                )
                while self._current_time() < cancel_deadline:
                    confirmed = self._scheduler.reconcile_session(session_date)
                    confirmed_status = self._status(confirmed.order)
                    if confirmed_status == "partially_filled":
                        raise RuntimeError(
                            "partially filled opening MLeg requires explicit reconciliation"
                        )
                    if confirmed.state is EpisodeState.CLOSED:
                        if confirmed_status not in {"canceled", "cancelled"}:
                            raise RuntimeError(
                                "opening cancellation reached unexpected terminal status"
                            )
                        return self._result(
                            session_date,
                            EpisodeState.CLOSED,
                            reason="opening_order_unfilled_cancelled",
                            entry_status="canceled",
                        )
                    self._sleep_poll(cancel_deadline)
                raise RuntimeError("opening order cancellation could not be proven")

            self._sleep_poll(deadline)

    def _manage_monitoring(
        self,
        session_date: date,
        episode_id: str,
        *,
        entry_status: str,
    ) -> CompetitionSessionResult:
        target = datetime.combine(session_date, self._policy.exit_time_et, tzinfo=ET)
        self._wait_until(target)

        open_order = self._require_open_order(episode_id)
        long_symbol = open_order.payload.get("long_leg")
        short_symbol = open_order.payload.get("short_leg")
        if not isinstance(long_symbol, str) or not isinstance(short_symbol, str):
            raise RuntimeError("opening order is missing exact spread contract identities")

        current = self._current_time()
        chain = self._chains.get_chain("COIN", now=current)
        instruction = self._close_builder(
            chain,
            long_symbol=long_symbol,
            short_symbol=short_symbol,
            now=current,
            attempt=0,
        )
        self._ledger.transition(
            episode_id,
            EpisodeState.EXIT_SUBMITTED,
            event="exit_due_60m",
            payload={"attempt": 0},
        )
        submitted = self._execution.submit_close(episode_id, instruction)
        return self._manage_close(
            session_date,
            episode_id,
            entry_status=entry_status,
            initial=submitted,
        )

    def _latest_close_order(self, episode_id: str) -> OrderRecord:
        order = self._ledger.get_latest_order_for_phase(episode_id, "close")
        if order is None:
            raise RuntimeError("EXIT_SUBMITTED episode has no durable close-order identity")
        return order

    @staticmethod
    def _attempt(order: OrderRecord) -> int:
        raw = order.payload.get("attempt", 0)
        if not isinstance(raw, int) or raw not in {0, 1}:
            raise RuntimeError("close order has invalid persisted attempt")
        return raw

    def _close_filled(
        self,
        session_date: date,
        episode_id: str,
        *,
        entry_status: str,
        close_status: str,
        attempts: int,
    ) -> CompetitionSessionResult:
        closed = self._ledger.transition(
            episode_id,
            EpisodeState.CLOSED,
            event="exit_filled",
            payload={"close_status": close_status, "attempts": attempts},
        )
        return self._result(
            session_date,
            closed.state,
            reason="research_horizon_exit_filled",
            entry_status=entry_status,
            close_status=close_status,
            close_attempts=attempts,
        )

    def _confirm_close_cancel(self, order: OrderRecord) -> str:
        deadline = self._current_time() + __import__("datetime").timedelta(
            seconds=self._policy.cancel_confirm_seconds
        )
        while self._current_time() < deadline:
            result = cast(ExecutionResult, self._execution.reconcile(order))
            status = result.status.lower()
            if status in {"canceled", "cancelled"}:
                return "canceled"
            if status in {"filled", "partially_filled"}:
                return status
            self._sleep_poll(deadline)
        raise RuntimeError("close order cancellation could not be proven")

    def _submit_replacement(
        self, episode_id: str, open_order: OrderRecord, *, attempt: int
    ) -> ExecutionResult:
        if attempt >= self._policy.max_close_attempts:
            raise RuntimeError("no additional deterministic close attempt is permitted")
        long_symbol = open_order.payload.get("long_leg")
        short_symbol = open_order.payload.get("short_leg")
        if not isinstance(long_symbol, str) or not isinstance(short_symbol, str):
            raise RuntimeError("opening order is missing exact spread contract identities")
        current = self._current_time()
        chain = self._chains.get_chain("COIN", now=current)
        instruction = self._close_builder(
            chain,
            long_symbol=long_symbol,
            short_symbol=short_symbol,
            now=current,
            attempt=attempt,
        )
        return cast(ExecutionResult, self._execution.submit_close(episode_id, instruction))

    def _manage_close(
        self,
        session_date: date,
        episode_id: str,
        *,
        entry_status: str,
        initial: ExecutionResult | None,
    ) -> CompetitionSessionResult:
        open_order = self._require_open_order(episode_id)
        order = self._latest_close_order(episode_id)
        status = self._status(initial, order.status.lower()) or "unknown"

        while True:
            order = self._latest_close_order(episode_id)
            attempt = self._attempt(order)
            attempts_used = attempt + 1

            if status == "filled":
                return self._close_filled(
                    session_date,
                    episode_id,
                    entry_status=entry_status,
                    close_status=status,
                    attempts=attempts_used,
                )
            if status == "partially_filled":
                raise RuntimeError("partially filled close MLeg requires explicit reconciliation")
            if status in {"rejected", "expired", "suspended"}:
                raise RuntimeError(f"close MLeg reached unsafe terminal status: {status}")
            if status in {"canceled", "cancelled"}:
                next_attempt = attempt + 1
                replacement = self._submit_replacement(
                    episode_id, open_order, attempt=next_attempt
                )
                status = replacement.status.lower()
                continue

            deadline = self._current_time() + __import__("datetime").timedelta(
                seconds=self._policy.close_fill_seconds
            )
            while self._current_time() < deadline:
                refreshed = self._execution.reconcile(order)
                status = refreshed.status.lower()
                if status == "filled":
                    return self._close_filled(
                        session_date,
                        episode_id,
                        entry_status=entry_status,
                        close_status=status,
                        attempts=attempts_used,
                    )
                if status == "partially_filled":
                    raise RuntimeError(
                        "partially filled close MLeg requires explicit reconciliation"
                    )
                if status in {"rejected", "expired", "suspended"}:
                    raise RuntimeError(f"close MLeg reached unsafe terminal status: {status}")
                if status in {"canceled", "cancelled"}:
                    break
                self._sleep_poll(deadline)

            if status in {"canceled", "cancelled"}:
                next_attempt = attempt + 1
                replacement = self._submit_replacement(
                    episode_id, open_order, attempt=next_attempt
                )
                status = replacement.status.lower()
                continue

            current_order = self._latest_close_order(episode_id)
            if current_order.alpaca_order_id is None:
                raise RuntimeError("close order has no proven Alpaca id for cancellation")
            self._trading.cancel_order(current_order.alpaca_order_id)
            cancel_status = self._confirm_close_cancel(current_order)
            if cancel_status == "filled":
                return self._close_filled(
                    session_date,
                    episode_id,
                    entry_status=entry_status,
                    close_status=cancel_status,
                    attempts=attempts_used,
                )
            if cancel_status == "partially_filled":
                raise RuntimeError("close MLeg partially filled while cancellation was pending")

            next_attempt = attempt + 1
            if next_attempt >= self._policy.max_close_attempts:
                raise RuntimeError(
                    "final deterministic close attempt did not fill; position remains unresolved"
                )
            replacement = self._submit_replacement(
                episode_id, open_order, attempt=next_attempt
            )
            status = replacement.status.lower()
