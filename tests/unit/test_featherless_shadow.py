from __future__ import annotations

import json
from dataclasses import dataclass

from clockcross.agent.adjudicator import AgentContext
from clockcross.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from clockcross.agent.shadow import (
    FEATHERLESS_BASE_URL,
    FEATHERLESS_MODEL,
    FeatherlessShadowObserver,
)
from clockcross.domain import AgentAction, AgentDecision, AgentDriver


@dataclass
class FakeResponse:
    payload: dict
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self.payload


class FakeHttp:
    def __init__(self, content: object = None, *, exc: Exception | None = None) -> None:
        self.content = content
        self.exc = exc
        self.calls: list[tuple[str, dict, dict, float]] = []

    def post(self, url: str, *, headers: dict, json: dict, timeout: float) -> FakeResponse:
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


def primary() -> AgentDecision:
    return AgentDecision(
        action=AgentAction.CONTINUATION,
        confidence=0.74,
        idiosyncratic_news_detected=False,
        driver=AgentDriver.CRYPTO_CROSS_MARKET,
        reason="Primary decision.",
    )


def valid_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "action": "continuation",
        "confidence": 0.71,
        "idiosyncratic_news_detected": False,
        "driver": "crypto_cross_market",
        "reason": "Independent bounded review.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def make(http: FakeHttp) -> FeatherlessShadowObserver:
    return FeatherlessShadowObserver(api_key="test-key", http_client=http)


def test_shadow_uses_same_bounded_prompt_and_fixed_glm_policy() -> None:
    http = FakeHttp(valid_json())

    audit = make(http).observe(context(), primary())

    assert audit.status == "ok"
    assert audit.model == FEATHERLESS_MODEL == "zai-org/GLM-5.3"
    assert audit.decision is not None
    assert audit.decision.action is AgentAction.CONTINUATION
    assert audit.action_agreement is True
    assert audit.driver_agreement is True
    assert audit.idiosyncratic_news_agreement is True

    url, headers, body, timeout = http.calls[0]
    assert url == f"{FEATHERLESS_BASE_URL}/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert body["model"] == "zai-org/GLM-5.3"
    assert body["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(context())},
    ]
    assert body["temperature"] == 0
    assert body["max_tokens"] == 512
    assert body["reasoning_effort"] == "low"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert timeout <= 8.0
    assert len(http.calls) == 1


def test_shadow_normalizes_company_specific_news_to_abstain() -> None:
    http = FakeHttp(
        valid_json(
            action="continuation",
            confidence=0.61,
            idiosyncratic_news_detected=True,
            driver="company_specific",
        )
    )

    audit = make(http).observe(context(), primary())

    assert audit.status == "ok"
    assert audit.decision is not None
    assert audit.decision.action is AgentAction.ABSTAIN
    assert audit.decision.driver is AgentDriver.COMPANY_SPECIFIC
    assert audit.decision.idiosyncratic_news_detected is True
    assert audit.action_agreement is False
    assert audit.idiosyncratic_news_agreement is False


def test_shadow_transport_failure_is_non_throwing_and_single_attempt() -> None:
    http = FakeHttp(exc=TimeoutError("slow"))

    audit = make(http).observe(context(), primary())

    assert audit.status == "unavailable"
    assert audit.decision is None
    assert audit.reason == "transport_or_response"
    assert len(http.calls) == 1


def test_shadow_malformed_json_is_non_throwing_invalid_audit() -> None:
    http = FakeHttp("not-json")

    audit = make(http).observe(context(), primary())

    assert audit.status == "invalid"
    assert audit.decision is None
    assert audit.reason == "malformed_json"
    assert len(http.calls) == 1
