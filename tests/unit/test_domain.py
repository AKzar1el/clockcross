import pytest
from pydantic import ValidationError

from clockcross.domain import AgentDecision, OptionLeg


def test_agent_decision_rejects_unsupported_action() -> None:
    with pytest.raises(ValidationError):
        AgentDecision(
            action="buy_everything",
            confidence=1.0,
            driver="unclear",
            reason="x",
        )


def test_option_leg_requires_buy_or_sell() -> None:
    with pytest.raises(ValidationError):
        OptionLeg(symbol="COIN260918C00300000", side="hold", ratio=1)
