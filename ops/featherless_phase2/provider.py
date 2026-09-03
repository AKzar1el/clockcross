from __future__ import annotations

import json
import time
from typing import Any

import httpx

from clockcross.agent.adjudicator import AgentContext
from clockcross.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from clockcross.domain import AgentAction, AgentDecision, AgentDriver
from clockcross.research.featherless_phase2 import BudgetLedger

from featherless_phase2.config import FEATHERLESS_BASE_URL, PRIOR_CORRECTION_MODEL


class BudgetStop(RuntimeError):
    pass


class FeatherlessClient:
    def __init__(self, api_key: str, budget: BudgetLedger) -> None:
        self._http = httpx.Client(timeout=90.0)
        self._budget = budget
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/AKzar1el/clockcross",
            "X-Title": "ClockCross Phase-2 Research",
        }
        self.plan = self._get_json("/plan")

    def _get_json(self, path: str) -> dict[str, Any]:
        response = self._http.get(f"{FEATHERLESS_BASE_URL}{path}", headers=self._headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected Featherless response for {path}")
        return payload

    def model_detail(self, model: str) -> dict[str, Any]:
        return self._get_json(f"/models/{model}")

    @staticmethod
    def model_available(detail: dict[str, Any]) -> bool:
        return detail.get("status") == "active" and detail.get("available_on_current_plan") is True

    @staticmethod
    def prices(detail: dict[str, Any]) -> tuple[float, float, float]:
        pricing = detail.get("pricing")
        if not isinstance(pricing, dict):
            raise RuntimeError("model detail is missing pricing")
        return (
            float(pricing.get("prompt", "0")),
            float(pricing.get("completion", "0")),
            float(pricing.get("request", "0")),
        )

    def effective_context(self, detail: dict[str, Any]) -> int:
        model_context = int(detail.get("context_length") or 0)
        plan_raw = self.plan.get("max_context_length")
        plan_context = int(plan_raw) if plan_raw is not None else model_context
        values = [value for value in (model_context, plan_context) if value > 0]
        if not values:
            raise RuntimeError("model/plan context unavailable")
        return min(values)

    def worst_case_cost(
        self,
        detail: dict[str, Any],
        *,
        prompt: str,
        max_tokens: int,
    ) -> float:
        prompt_price, completion_price, request_price = self.prices(detail)
        context_limit = self.effective_context(detail)
        upper_prompt_tokens = min(
            context_limit - max_tokens,
            len((SYSTEM_PROMPT + prompt).encode("utf-8")) + 1024,
        )
        return (
            upper_prompt_tokens * prompt_price
            + max_tokens * completion_price
            + request_price
        )

    def decide(
        self,
        *,
        model: str,
        detail: dict[str, Any],
        context: AgentContext,
    ) -> tuple[AgentDecision, bool, dict[str, Any]]:
        prompt = build_user_prompt(context)
        max_tokens = 512
        worst_case = self.worst_case_cost(detail, prompt=prompt, max_tokens=max_tokens)
        if not self._budget.can_start(worst_case):
            raise BudgetStop("hard Phase-2 Featherless budget would be exceeded")

        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if model == PRIOR_CORRECTION_MODEL:
            body["reasoning_effort"] = "low"

        started = time.monotonic()
        response: httpx.Response | None = None
        attempts = 0
        for attempt in range(2):
            attempts = attempt + 1
            response = self._http.post(
                f"{FEATHERLESS_BASE_URL}/chat/completions",
                headers=self._headers,
                json=body,
            )
            if response.status_code != 429 and response.status_code < 500:
                break
            if attempt == 0:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else 1.0
                except ValueError:
                    delay = 1.0
                time.sleep(max(0.0, min(delay, 5.0)))
        latency = time.monotonic() - started
        assert response is not None
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("completion response is not an object")

        prompt_price, completion_price, request_price = self.prices(detail)
        usage = payload.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            usage_missing = False
            cost = (
                prompt_tokens * prompt_price
                + completion_tokens * completion_price
                + request_price
            )
        else:
            usage_missing = True
            prompt_tokens = 0
            completion_tokens = 0
            cost = worst_case
        self._budget.record_success(cost)

        valid = False
        fail_code = "invalid_response_shape"
        decision = self._fail_closed(fail_code)
        try:
            choices = payload["choices"]
            content = choices[0]["message"]["content"]
            if not isinstance(content, str):
                fail_code = "non_text_response"
            else:
                decoded = json.loads(content)
                expected = {
                    "action",
                    "confidence",
                    "idiosyncratic_news_detected",
                    "driver",
                    "reason",
                }
                if not isinstance(decoded, dict) or set(decoded) != expected:
                    fail_code = "invalid_response_shape"
                else:
                    parsed = AgentDecision.model_validate(decoded)
                    if parsed.idiosyncratic_news_detected:
                        parsed = AgentDecision(
                            action=AgentAction.ABSTAIN,
                            confidence=parsed.confidence,
                            idiosyncratic_news_detected=True,
                            driver=AgentDriver.COMPANY_SPECIFIC,
                            reason=parsed.reason,
                        )
                    decision = parsed
                    valid = True
        except Exception as exc:
            fail_code = f"parse_or_schema:{type(exc).__name__}"
        if not valid:
            decision = self._fail_closed(fail_code)

        finish_reason = None
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish_reason = choices[0].get("finish_reason")
        return decision, valid, {
            "latency_seconds": latency,
            "attempts": attempts,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "usage_missing": usage_missing,
            "cost_usd": cost,
            "finish_reason": finish_reason,
        }

    @staticmethod
    def _fail_closed(code: str) -> AgentDecision:
        return AgentDecision(
            action=AgentAction.ABSTAIN,
            confidence=0.0,
            idiosyncratic_news_detected=False,
            driver=AgentDriver.UNCLEAR,
            reason=f"fail_closed:{code}"[:600],
        )


def serializable_decision(decision: AgentDecision) -> dict[str, Any]:
    return decision.model_dump(mode="json")


def compact_detail(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": detail.get("status"),
        "available_on_current_plan": detail.get("available_on_current_plan"),
        "is_gated": detail.get("is_gated"),
        "availability": detail.get("availability"),
        "pricing": detail.get("pricing"),
        "context_length": detail.get("context_length"),
        "concurrency_cost": detail.get("concurrency_cost"),
    }
