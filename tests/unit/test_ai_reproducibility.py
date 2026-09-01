from clockcross.domain import AgentAction, AgentDecision, AgentDriver
from clockcross.research import ai_reproducibility


def decision(
    action: AgentAction,
    *,
    driver: AgentDriver = AgentDriver.CRYPTO_CROSS_MARKET,
    idiosyncratic: bool = False,
    reason: str = "stable",
) -> AgentDecision:
    return AgentDecision(
        action=action,
        confidence=0.75,
        idiosyncratic_news_detected=idiosyncratic,
        driver=driver,
        reason=reason,
    )


def test_identical_core_decisions_are_fully_reproducible() -> None:
    observations = [decision(AgentAction.CONTINUATION) for _ in range(5)]

    result = ai_reproducibility.summarize_decisions(observations)

    assert result["count"] == 5
    assert result["action_consistency"] == 1.0
    assert result["driver_consistency"] == 1.0
    assert result["idiosyncratic_consistency"] == 1.0
    assert result["fail_closed_rate"] == 0.0
    assert result["actions"] == {"continuation": 5}


def test_action_flip_is_reported_even_when_responses_are_schema_valid() -> None:
    observations = [
        decision(AgentAction.REVERSION),
        decision(AgentAction.REVERSION),
        decision(AgentAction.REVERSION),
        decision(AgentAction.CONTINUATION),
    ]

    result = ai_reproducibility.summarize_decisions(observations)

    assert result["action_consistency"] == 0.75
    assert result["actions"] == {"continuation": 1, "reversion": 3}


def test_fail_closed_abstention_is_counted_separately() -> None:
    observations = [
        decision(AgentAction.CONTINUATION),
        decision(
            AgentAction.ABSTAIN,
            driver=AgentDriver.UNCLEAR,
            reason="fail_closed:transport_or_response",
        ),
    ]

    result = ai_reproducibility.summarize_decisions(observations)

    assert result["fail_closed_count"] == 1
    assert result["fail_closed_rate"] == 0.5


def test_expectation_rates_capture_safety_semantics() -> None:
    observations = [
        decision(
            AgentAction.ABSTAIN,
            driver=AgentDriver.COMPANY_SPECIFIC,
            idiosyncratic=True,
            reason="company event",
        )
        for _ in range(4)
    ] + [decision(AgentAction.CONTINUATION)]

    result = ai_reproducibility.summarize_decisions(
        observations,
        expected_action=AgentAction.ABSTAIN,
        expected_idiosyncratic=True,
    )

    assert result["expected_action_rate"] == 0.8
    assert result["expected_idiosyncratic_rate"] == 0.8
