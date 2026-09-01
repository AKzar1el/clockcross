from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import TypeVar

from clockcross.domain import AgentAction, AgentDecision

_T = TypeVar("_T", bound=str | bool)


def _consistency(values: Sequence[_T]) -> float:
    if not values:
        raise ValueError("at least one observation is required")
    counts = Counter(values)
    return max(counts.values()) / len(values)


def summarize_decisions(
    observations: Sequence[AgentDecision],
    *,
    expected_action: AgentAction | None = None,
    expected_idiosyncratic: bool | None = None,
) -> dict[str, object]:
    """Summarize repeated bounded AI decisions without judging market direction."""
    if not observations:
        raise ValueError("at least one AI decision is required")

    action_values = [decision.action.value for decision in observations]
    driver_values = [decision.driver.value for decision in observations]
    idiosyncratic_values = [decision.idiosyncratic_news_detected for decision in observations]
    confidences = [float(decision.confidence) for decision in observations]
    fail_closed = [
        decision
        for decision in observations
        if decision.action is AgentAction.ABSTAIN
        and decision.reason.startswith("fail_closed:")
    ]

    result: dict[str, object] = {
        "count": len(observations),
        "actions": dict(sorted(Counter(action_values).items())),
        "drivers": dict(sorted(Counter(driver_values).items())),
        "idiosyncratic_news_detected": {
            "false": idiosyncratic_values.count(False),
            "true": idiosyncratic_values.count(True),
        },
        "action_consistency": _consistency(action_values),
        "driver_consistency": _consistency(driver_values),
        "idiosyncratic_consistency": _consistency(idiosyncratic_values),
        "fail_closed_count": len(fail_closed),
        "fail_closed_rate": len(fail_closed) / len(observations),
        "confidence_min": min(confidences),
        "confidence_mean": sum(confidences) / len(confidences),
        "confidence_max": max(confidences),
        "unique_reason_count": len({decision.reason for decision in observations}),
    }

    if expected_action is not None:
        result["expected_action"] = expected_action.value
        result["expected_action_rate"] = (
            sum(decision.action is expected_action for decision in observations)
            / len(observations)
        )
    else:
        result["expected_action"] = None
        result["expected_action_rate"] = None

    if expected_idiosyncratic is not None:
        result["expected_idiosyncratic"] = expected_idiosyncratic
        result["expected_idiosyncratic_rate"] = (
            sum(
                decision.idiosyncratic_news_detected is expected_idiosyncratic
                for decision in observations
            )
            / len(observations)
        )
    else:
        result["expected_idiosyncratic"] = None
        result["expected_idiosyncratic_rate"] = None

    return result
