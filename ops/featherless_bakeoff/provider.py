from __future__ import annotations

import json
import time
from typing import Any

import httpx

from clockcross.agent.adjudicator import AgentContext
from clockcross.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from clockcross.domain import AgentAction, AgentDecision, AgentDriver
from clockcross.research.featherless_bakeoff import (
    BudgetLedger,
    prompt_token_upper_bound,
)

from featherless_bakeoff.config import FEATHERLESS_BASE_URL, MAX_TOKENS


class BudgetStop(RuntimeError):
    pass


class FeatherlessResearchClient:
    def __init__(self, api_key: str, budget: BudgetLedger) -> None:
        self._http = httpx.Client(timeout=90.0)
        self._budget = budget
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/AKzar1el/clockcross",
            "X-Title": "ClockCross Research",
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
    def _prices(detail: dict[str, Any]) -> tuple[float, float, float]:
        pricing = detail.get("pricing")
        if not isinstance(pricing, dict):
            raise RuntimeError("Featherless model detail is missing pricing")
        return (
            float(pricing.get("prompt", "0")),
            float(pricing.get("completion", "0")),
            float(pricing.get("request", "0")),
        )

    def effective_context(self, detail: dict[str, Any]) -> int:
        model_context = int(detail.get("context_length") or 0)
        plan_raw = self.plan.get("max_context_length")
        plan_context = int(plan_raw) if plan_raw is not None else model_context
        candidates = [value for value in (model_context, plan_context) if value > 0]
        if not candidates:
            raise RuntimeError("model/plan context length is unavailable")
        return min(candidates)

    def worst_case_cost(
        self, detail: dict[str, Any], *, message_contents: list[str]
    ) -> float:
        prompt_price, completion_price, request_price = self._prices(detail)
        prompt_tokens = prompt_token_upper_bound(
            message_contents,
            context_limit=self.effective_context(detail),
            completion_tokens=MAX_TOKENS,
            chat_overhead_tokens=1024,
        )
        return prompt_tokens * prompt_price + MAX_TOKENS * completion_price + request_price

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(3):
            response = self._http.post(
                f"{FEATHERLESS_BASE_URL}/chat/completions",
                headers=self._headers,
                json=body,
            )
            if response.status_code != 429 and response.status_code < 500:
                return response
            if attempt < 2:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else 2.0 * (attempt + 1)
                except ValueError:
                    delay = 2.0 * (attempt + 1)
                time.sleep(max(0.0, min(delay, 20.0)))
        assert response is not None
        return response

    def decide(
        self,
        *,
        model: str,
        detail: dict[str, Any],
        context: AgentContext,
    ) -> tuple[AgentDecision, bool, dict[str, Any]]:
        user_prompt = build_user_prompt(context)
        worst_case = self.worst_case_cost(
            detail, message_contents=[SYSTEM_PROMPT, user_prompt]
        )
        if not self._budget.can_start(worst_case_cost_usd=worst_case):
            raise BudgetStop("hard Featherless research budget would be exceeded")
        response = self._post(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "max_tokens": MAX_TOKENS,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Featherless completion payload is not an object")

        usage = payload.get("usage")
        prompt_price, completion_price, request_price = self._prices(detail)
        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            usage_missing = False
        else:
            prompt_tokens = prompt_token_upper_bound(
                [SYSTEM_PROMPT, user_prompt],
                context_limit=self.effective_context(detail),
                completion_tokens=MAX_TOKENS,
                chat_overhead_tokens=1024,
            )
            completion_tokens = MAX_TOKENS
            usage_missing = True
        cost = self._budget.record_success(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_price=prompt_price,
            completion_price=completion_price,
            request_price=request_price,
        )

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

        choices = payload.get("choices")
        finish_reason = None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish_reason = choices[0].get("finish_reason")
        return decision, valid, {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "usage_missing": usage_missing,
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
