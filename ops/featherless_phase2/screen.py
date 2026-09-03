from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from clockcross.research.featherless_phase2 import Action

from featherless_phase2.config import (
    ALL_RESEARCH_MODELS,
    CONTRACT_CONTEXTS,
    CONTRACT_MAX_LIMIT_SECONDS,
    CONTRACT_P95_LIMIT_SECONDS,
    CONTRACT_REPEATS,
    PHASE2_MODELS,
)
from featherless_phase2.data import synthetic_contract_contexts
from featherless_phase2.provider import (
    BudgetStop,
    FeatherlessClient,
    compact_detail,
)


def run_contract_screen(
    client: FeatherlessClient,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], bool]:
    results: dict[str, Any] = {}
    details: dict[str, dict[str, Any]] = {}
    budget_stopped = False
    contexts = synthetic_contract_contexts()

    for model in ALL_RESEARCH_MODELS:
        try:
            detail = client.model_detail(model)
        except Exception as exc:
            results[model] = {
                "passed": False,
                "reason": f"model_detail:{type(exc).__name__}",
            }
            continue
        details[model] = detail
        if not client.model_available(detail):
            results[model] = {
                "passed": False,
                "reason": "unavailable",
                "detail": compact_detail(detail),
            }
            continue

        context_records: list[dict[str, Any]] = []
        all_latencies: list[float] = []
        all_valid = True
        unanimous = True
        transport_error: str | None = None
        try:
            for context_index, context in enumerate(contexts):
                actions: list[Action] = []
                records: list[dict[str, Any]] = []
                for _ in range(CONTRACT_REPEATS):
                    decision, valid, metadata = client.decide(
                        model=model,
                        detail=detail,
                        context=context,
                    )
                    action = decision.action.value
                    actions.append(action)
                    all_valid = all_valid and valid
                    all_latencies.append(float(metadata["latency_seconds"]))
                    records.append(
                        {
                            "action": action,
                            "valid": valid,
                            "metadata": metadata,
                        }
                    )
                context_unanimous = len(set(actions)) == 1
                unanimous = unanimous and context_unanimous
                context_records.append(
                    {
                        "context_index": context_index,
                        "vote_counts": dict(sorted(Counter(actions).items())),
                        "unanimous": context_unanimous,
                        "observations": records,
                    }
                )
        except BudgetStop:
            budget_stopped = True
            transport_error = "budget_stop"
        except Exception as exc:
            transport_error = f"transport:{type(exc).__name__}"

        latency_p95 = (
            float(np.quantile(all_latencies, 0.95))
            if all_latencies
            else float("inf")
        )
        latency_max = max(all_latencies) if all_latencies else float("inf")
        passed = (
            transport_error is None
            and all_valid
            and unanimous
            and len(all_latencies) == CONTRACT_CONTEXTS * CONTRACT_REPEATS
            and latency_p95 <= CONTRACT_P95_LIMIT_SECONDS
            and latency_max <= CONTRACT_MAX_LIMIT_SECONDS
        )
        results[model] = {
            "passed": passed,
            "phase2_promotion_eligible": model in PHASE2_MODELS,
            "detail": compact_detail(detail),
            "all_schema_valid": all_valid,
            "all_contexts_unanimous": unanimous,
            "latency_p95_seconds": latency_p95,
            "latency_max_seconds": latency_max,
            "error": transport_error,
            "contexts": context_records,
        }
        if budget_stopped:
            break
    return results, details, budget_stopped
