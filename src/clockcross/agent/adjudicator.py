from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from clockcross.domain import AgentAction, AgentDecision, AgentDriver


class AgentContext(BaseModel):
    underlying: Literal["COIN"]
    residual: float
    residual_z: float | None = None
    residual_sign: Literal[-1, 1]
    btc_return: float
    opening_10m_return: float | None = None
    historical_mean_signed_return: float | None = None
    option_feed: Literal["indicative", "opra"]
    available_structures: tuple[
        Literal["call_debit_spread", "put_debit_spread"], ...
    ]
    news_summary: str = Field(max_length=1600)


class Adjudicator:
    """OpenAI-compatible bounded adjudicator that always fails closed."""

    _EXPECTED_KEYS = {
        "action",
        "confidence",
        "idiosyncratic_news_detected",
        "driver",
        "reason",
    }

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        http_client: Any | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        import httpx

        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._http = http_client or httpx.Client()
        self._timeout = timeout_seconds

    @staticmethod
    def _fail_closed(code: str) -> AgentDecision:
        return AgentDecision(
            action=AgentAction.ABSTAIN,
            confidence=0.0,
            idiosyncratic_news_detected=False,
            driver=AgentDriver.UNCLEAR,
            reason=f"fail_closed:{code}",
        )

    def decide(self, context: AgentContext) -> AgentDecision:
        from clockcross.agent.prompts import SYSTEM_PROMPT, build_user_prompt

        try:
            response = self._http.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/AKzar1el/clockcross",
                    "X-Title": "ClockCross",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(context)},
                    ],
                    "temperature": 0,
                    "max_tokens": 220,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except Exception:
            return self._fail_closed("transport_or_response")

        if not isinstance(content, str):
            return self._fail_closed("non_text_response")
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return self._fail_closed("malformed_json")
        if not isinstance(decoded, dict) or set(decoded) != self._EXPECTED_KEYS:
            return self._fail_closed("invalid_response_shape")
        try:
            decision = AgentDecision.model_validate(decoded)
        except ValidationError:
            return self._fail_closed("schema_validation")

        if decision.idiosyncratic_news_detected:
            return AgentDecision(
                action=AgentAction.ABSTAIN,
                confidence=decision.confidence,
                idiosyncratic_news_detected=True,
                driver=AgentDriver.COMPANY_SPECIFIC,
                reason=decision.reason,
            )
        return decision
