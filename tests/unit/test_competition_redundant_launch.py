from datetime import date, datetime
from zoneinfo import ZoneInfo

from clockcross.competition import CompetitionOrchestrator
from clockcross.domain import EpisodeState
from clockcross.ledger import Ledger

ET = ZoneInfo("America/New_York")
SESSION = date(2026, 9, 1)


class NeverScheduler:
    def __init__(self) -> None:
        self.calls = 0

    def run_session(self, session_date: date, *, mode: str):
        self.calls += 1
        raise AssertionError("terminal redundant launch must not rerun the daily scheduler")


class UnusedDependency:
    def __getattr__(self, name: str):
        raise AssertionError(f"terminal redundant launch must not use {name}")


def unused_close_builder(*args, **kwargs):
    raise AssertionError("terminal redundant launch must not construct a close")


def seed_closed_episode(ledger: Ledger) -> str:
    episode = ledger.create_episode(SESSION, "COIN")
    for state in (
        EpisodeState.FEATURES_FROZEN,
        EpisodeState.OPENING_CONFIRMATION,
        EpisodeState.CANDIDATE_READY,
        EpisodeState.AI_REVIEWED,
        EpisodeState.RISK_APPROVED,
        EpisodeState.ORDER_SUBMITTED,
        EpisodeState.ORDER_CANCELLED,
        EpisodeState.CLOSED,
    ):
        ledger.transition(episode.episode_id, state, event="test")
    return episode.episode_id


def test_session_episode_lookup_is_read_only(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    try:
        assert ledger.get_episode_for_session(SESSION, "COIN") is None
        assert ledger.count_rows("episodes") == 0
    finally:
        ledger.close()


def test_delayed_backup_after_terminal_episode_returns_existing_terminal_state(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    seed_closed_episode(ledger)
    scheduler = NeverScheduler()
    orchestrator = CompetitionOrchestrator(
        ledger=ledger,
        scheduler=scheduler,
        chain_gateway=UnusedDependency(),
        trading=UnusedDependency(),
        execution=UnusedDependency(),
        now=lambda: datetime(2026, 9, 1, 10, 56, tzinfo=ET),
        sleeper=lambda seconds: None,
        close_builder=unused_close_builder,
    )

    try:
        result = orchestrator.run(SESSION)
        assert result.state is EpisodeState.CLOSED
        assert result.reason == "terminal_episode"
        assert scheduler.calls == 0
        assert ledger.count_rows("episodes") == 1
    finally:
        ledger.close()
