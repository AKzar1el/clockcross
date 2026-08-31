import pytest

from clockcross.domain import EpisodeState
from clockcross.state import EpisodeMachine, InvalidTransition


def test_legal_episode_path_reaches_monitoring_and_closed():
    machine = EpisodeMachine(EpisodeState.COLLECTING)
    for state in (
        EpisodeState.FEATURES_FROZEN,
        EpisodeState.OPENING_CONFIRMATION,
        EpisodeState.CANDIDATE_READY,
        EpisodeState.AI_REVIEWED,
        EpisodeState.RISK_APPROVED,
        EpisodeState.ORDER_SUBMITTED,
        EpisodeState.ORDER_FILLED,
        EpisodeState.MONITORING,
        EpisodeState.EXIT_SUBMITTED,
        EpisodeState.CLOSED,
    ):
        assert machine.advance(state) is state
    assert machine.state is EpisodeState.CLOSED


def test_direct_collecting_to_order_submitted_is_invalid():
    machine = EpisodeMachine(EpisodeState.COLLECTING)
    try:
        machine.advance(EpisodeState.ORDER_SUBMITTED)
    except InvalidTransition as exc:
        assert exc.current is EpisodeState.COLLECTING
        assert exc.requested is EpisodeState.ORDER_SUBMITTED
    else:
        raise AssertionError("expected InvalidTransition")


def test_abstained_is_terminal():
    machine = EpisodeMachine(EpisodeState.OPENING_CONFIRMATION)
    assert machine.advance(EpisodeState.ABSTAINED) is EpisodeState.ABSTAINED
    try:
        machine.advance(EpisodeState.CANDIDATE_READY)
    except InvalidTransition:
        pass
    else:
        raise AssertionError("ABSTAINED must be terminal")


def test_cancelled_and_rejected_orders_can_close_without_monitoring():
    for terminal in (EpisodeState.ORDER_CANCELLED, EpisodeState.ORDER_REJECTED):
        machine = EpisodeMachine(EpisodeState.ORDER_SUBMITTED)
        machine.advance(terminal)
        assert machine.advance(EpisodeState.CLOSED) is EpisodeState.CLOSED


def test_filled_position_requires_explicit_exit_submission_before_close():
    machine = EpisodeMachine(EpisodeState.ORDER_FILLED)
    assert machine.advance(EpisodeState.MONITORING) is EpisodeState.MONITORING
    assert machine.advance(EpisodeState.EXIT_SUBMITTED) is EpisodeState.EXIT_SUBMITTED
    assert machine.advance(EpisodeState.CLOSED) is EpisodeState.CLOSED


def test_monitoring_cannot_jump_directly_to_closed():
    machine = EpisodeMachine(EpisodeState.MONITORING)
    with pytest.raises(InvalidTransition):
        machine.advance(EpisodeState.CLOSED)
