from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from clockcross.agent.adjudicator import AgentContext
from clockcross.domain import AgentAction, AgentDecision, AgentDriver

FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"
FEATHERLESS_MODEL = "zai-org/GLM-5.3"


class ShadowAudit(BaseModel):
    status: Literal["ok", "unavailable", "invalid", "skipped"]
    model: str = FEATHERLESS_MODEL
    decision: AgentDecision | None = None
    action_agreement: bool | None = None
    driver_agreement: bool | None = None
    idiosyncratic_news_agreement: bool | None = None
    reason: str


class FeatherlessShadowObserver:
    """Independent model-risk observer with no trading authority or retries."""

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
        api_key: str,
        http_client: Any | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        import httpx

        self._api_key = api_key
        self._http = http_client or httpx.Client(timeout=timeout_seconds)
        self._timeout = min(float(timeout_seconds), 8.0)

    @staticmethod
    def _audit_failure(status: Literal["unavailable", "invalid"], reason: str) -> ShadowAudit:
        return ShadowAudit(status=status, reason=reason)

    def observe(self, context: AgentContext, authoritative: AgentDecision) -> ShadowAudit:
        from clockcross.agent.prompts import SYSTEM_PROMPT, build_user_prompt

        try:
            response = self._http.post(
                f"{FEATHERLESS_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/AKzar1el/clockcross",
                    "X-Title": "ClockCross Shadow Observer",
                },
                json={
                    "model": FEATHERLESS_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(context)},
                    ],
                    "temperature": 0,
                    "max_tokens": 512,
                    "reasoning_effort": "low",
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except Exception:
            return self._audit_failure("unavailable", "transport_or_response")

        if not isinstance(content, str):
            return self._audit_failure("invalid", "non_text_response")
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return self._audit_failure("invalid", "malformed_json")
        if not isinstance(decoded, dict) or set(decoded) != self._EXPECTED_KEYS:
            return self._audit_failure("invalid", "invalid_response_shape")
        try:
            decision = AgentDecision.model_validate(decoded)
        except ValidationError:
            return self._audit_failure("invalid", "schema_validation")

        if decision.idiosyncratic_news_detected:
            decision = AgentDecision(
                action=AgentAction.ABSTAIN,
                confidence=decision.confidence,
                idiosyncratic_news_detected=True,
                driver=AgentDriver.COMPANY_SPECIFIC,
                reason=decision.reason,
            )

        return ShadowAudit(
            status="ok",
            decision=decision,
            action_agreement=decision.action is authoritative.action,
            driver_agreement=decision.driver is authoritative.driver,
            idiosyncratic_news_agreement=(
                decision.idiosyncratic_news_detected
                is authoritative.idiosyncratic_news_detected
            ),
            reason="observed",
        )
