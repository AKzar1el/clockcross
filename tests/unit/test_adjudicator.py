from __future__ import annotations

import json
from dataclasses import dataclass

from clockcross.agent.adjudicator import Adjudicator, AgentContext
from clockcross.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from clockcross.domain import AgentAction, AgentDriver


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, content=None, *, exc=None):
        self.content = content
        self.exc = exc
        self.calls = []

    def post(self, url, *, headers, json, timeout):
        self.calls.append((url, headers, json, timeout))
        if self.exc is not None:
            raise self.exc
        return FakeResponse({"choices": [{"message": {"content": self.content}}]})


def context() -> AgentContext:
    return AgentContext(
        underlying="COIN",
        residual=0.032,
        residual_z=1.4,
        residual_sign=1,
        btc_return=0.021,
        opening_10m_return=0.004,
        historical_mean_signed_return=0.0084,
        option_feed="indicative",
        available_structures=("call_debit_spread", "put_debit_spread"),
        news_summary="No company-specific breaking news detected.",
    )


def valid_json(**overrides):
    payload = {
        "action": "continuation",
        "confidence": 0.74,
        "idiosyncratic_news_detected": False,
        "driver": "crypto_cross_market",
        "reason": "Residual and opening confirmation align.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def make(http):
    return Adjudicator(
        base_url="https://clockcross-ai-gateway.example/v1",
        api_key="test-key",
        model="clockcross-test-model",
        http_client=http,
    )


def test_prompt_is_bounded_and_states_authority_limits():
    assert len(SYSTEM_PROMPT) < 2600
    assert "COIN" in SYSTEM_PROMPT
    assert "MSTR" in SYSTEM_PROMPT and "not tradable" in SYSTEM_PROMPT.lower()
    assert "QQQ" in SYSTEM_PROMPT and "control" in SYSTEM_PROMPT.lower()
    assert "continuation" in SYSTEM_PROMPT
    assert "reversion" in SYSTEM_PROMPT
    assert "abstain" in SYSTEM_PROMPT
    assert "cannot override" in SYSTEM_PROMPT.lower()
    assert "company-specific" in SYSTEM_PROMPT.lower()
    user = build_user_prompt(context())
    assert "api_key" not in user.lower()
    assert len(user) < 2200


def test_valid_decision_is_schema_validated():
    http = FakeHttp(valid_json())
    decision = make(http).decide(context())
    assert decision.action is AgentAction.CONTINUATION
    assert decision.driver is AgentDriver.CRYPTO_CROSS_MARKET
    assert http.calls[0][0] == "https://clockcross-ai-gateway.example/v1/chat/completions"
    assert http.calls[0][2]["temperature"] == 0
    assert "chat_template_kwargs" not in http.calls[0][2]


def test_application_attribution_headers_are_sent():
    http = FakeHttp(valid_json())
    make(http).decide(context())
    headers = http.calls[0][1]
    assert headers["X-Title"] == "ClockCross"
    assert headers["HTTP-Referer"] == "https://github.com/AKzar1el/clockcross"


def test_valid_reversion_and_abstain_are_allowed():
    reversion = make(FakeHttp(valid_json(action="reversion"))).decide(context())
    abstain = make(FakeHttp(valid_json(action="abstain", confidence=0.2))).decide(context())
    assert reversion.action is AgentAction.REVERSION
    assert abstain.action is AgentAction.ABSTAIN


def test_malformed_json_fails_closed_to_abstain():
    decision = make(FakeHttp("not-json")).decide(context())
    assert decision.action is AgentAction.ABSTAIN
    assert decision.driver is AgentDriver.UNCLEAR
    assert decision.reason.startswith("fail_closed:")


def test_unsupported_action_and_invalid_confidence_fail_closed():
    action = make(FakeHttp(valid_json(action="buy_everything"))).decide(context())
    confidence = make(FakeHttp(valid_json(confidence=4.0))).decide(context())
    assert action.action is AgentAction.ABSTAIN
    assert confidence.action is AgentAction.ABSTAIN


def test_timeout_fails_closed():
    decision = make(FakeHttp(exc=TimeoutError("slow"))).decide(context())
    assert decision.action is AgentAction.ABSTAIN
    assert "transport" in decision.reason


def test_company_specific_news_forces_abstention():
    decision = make(
        FakeHttp(
            valid_json(
                action="continuation",
                idiosyncratic_news_detected=True,
                driver="company_specific",
            )
        )
    ).decide(context())
    assert decision.action is AgentAction.ABSTAIN
    assert decision.idiosyncratic_news_detected is True
    assert decision.driver is AgentDriver.COMPANY_SPECIFIC
