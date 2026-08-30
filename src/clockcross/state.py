from __future__ import annotations

from clockcross.domain import EpisodeState


class InvalidTransition(ValueError):
    def __init__(self, current: EpisodeState, requested: EpisodeState) -> None:
        self.current = current
        self.requested = requested
        super().__init__(f"invalid ClockCross transition: {current.value} -> {requested.value}")


_ALLOWED: dict[EpisodeState, frozenset[EpisodeState]] = {
    EpisodeState.COLLECTING: frozenset({EpisodeState.FEATURES_FROZEN, EpisodeState.ABSTAINED}),
    EpisodeState.FEATURES_FROZEN: frozenset({EpisodeState.OPENING_CONFIRMATION, EpisodeState.ABSTAINED}),
    EpisodeState.OPENING_CONFIRMATION: frozenset({EpisodeState.CANDIDATE_READY, EpisodeState.ABSTAINED}),
    EpisodeState.CANDIDATE_READY: frozenset({EpisodeState.AI_REVIEWED, EpisodeState.ABSTAINED}),
    EpisodeState.AI_REVIEWED: frozenset({EpisodeState.RISK_APPROVED, EpisodeState.ABSTAINED}),
    EpisodeState.RISK_APPROVED: frozenset({EpisodeState.ORDER_SUBMITTED, EpisodeState.ABSTAINED}),
    EpisodeState.ORDER_SUBMITTED: frozenset(
        {EpisodeState.ORDER_FILLED, EpisodeState.ORDER_CANCELLED, EpisodeState.ORDER_REJECTED}
    ),
    EpisodeState.ORDER_FILLED: frozenset({EpisodeState.MONITORING}),
    EpisodeState.ORDER_CANCELLED: frozenset({EpisodeState.CLOSED}),
    EpisodeState.ORDER_REJECTED: frozenset({EpisodeState.CLOSED}),
    EpisodeState.MONITORING: frozenset({EpisodeState.EXIT_SUBMITTED}),
    EpisodeState.EXIT_SUBMITTED: frozenset({EpisodeState.CLOSED}),
    EpisodeState.ABSTAINED: frozenset(),
    EpisodeState.CLOSED: frozenset(),
}


class EpisodeMachine:
    def __init__(self, state: EpisodeState) -> None:
        self.state = state

    def advance(self, requested: EpisodeState) -> EpisodeState:
        if requested == self.state:
            return self.state
        if requested not in _ALLOWED[self.state]:
            raise InvalidTransition(self.state, requested)
        self.state = requested
        return self.state

    @staticmethod
    def can_transition(current: EpisodeState, requested: EpisodeState) -> bool:
        return requested == current or requested in _ALLOWED[current]
