from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import date
from enum import Enum
from typing import Any, cast

from pydantic import BaseModel


def register_runtime_subcommands(subparsers: Any) -> None:
    subparsers.add_parser("preflight")
    subparsers.add_parser("smoke-mleg")
    run_once = subparsers.add_parser("run-once")
    run_once.add_argument("--date", required=True, type=date.fromisoformat)
    run_once.add_argument("--mode", choices=("dry-run", "paper"), default="dry-run")
    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--date", required=True, type=date.fromisoformat)
    competition = subparsers.add_parser("competition-session")
    competition.add_argument("--date", required=True, type=date.fromisoformat)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            key: _jsonable(item)
            for key, item in asdict(cast(Any, value)).items()
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


from dataclasses import asdict, is_dataclass


def execute_runtime_command(
    args: argparse.Namespace,
    *,
    settings_factory: Callable[[], Any] | None = None,
    preflight_builder: Callable[[Any], Any] | None = None,
    smoke_builder: Callable[[Any], Any] | None = None,
    runtime_builder: Callable[[Any], Any] | None = None,
    reconciliation_builder: Callable[[Any], Any] | None = None,
    competition_builder: Callable[[Any], Any] | None = None,
    app_builder: Callable[[Any], Any] | None = None,
    uvicorn_runner: Callable[..., Any] | None = None,
) -> int | None:
    from clockcross.config import Settings
    from clockcross.preflight_runtime import build_preflight_report
    from clockcross.runtime import (
        build_competition_runtime,
        build_evidence_app,
        build_reconciliation_runtime,
        build_runtime,
    )

    settings_builder: Callable[[], Any] = settings_factory or Settings
    preflight_build: Callable[[Any], Any] = preflight_builder or build_preflight_report
    runtime_build: Callable[[Any], Any] = runtime_builder or build_runtime
    reconciliation_build: Callable[[Any], Any] = (
        reconciliation_builder or build_reconciliation_runtime
    )
    competition_build: Callable[[Any], Any] = (
        competition_builder or build_competition_runtime
    )
    app_build: Callable[[Any], Any] = app_builder or build_evidence_app

    if args.command == "preflight":
        report = preflight_build(settings_builder())
        payload = {
            "ok": bool(report.ok),
            "checks": [_jsonable(check) for check in report.checks],
        }
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return 0 if report.ok else 2
    if args.command == "smoke-mleg":
        if smoke_builder is None:
            from clockcross.runtime import build_mleg_smoke_result

            smoke_builder = build_mleg_smoke_result
        try:
            result = smoke_builder(settings_builder())
        except RuntimeError as exc:
            print(
                json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(_jsonable(result), indent=2, sort_keys=True, default=str))
        return 0 if bool(result.ok) else 2
    if args.command == "run-once":
        runtime = runtime_build(settings_builder())
        try:
            summary = runtime.scheduler.run_session(args.date, mode=args.mode)
            print(json.dumps(_jsonable(summary), indent=2, sort_keys=True, default=str))
        finally:
            runtime.close()
        return 0
    if args.command == "reconcile":
        runtime = reconciliation_build(settings_builder())
        try:
            summary = runtime.scheduler.reconcile_session(args.date)
            print(json.dumps(_jsonable(summary), indent=2, sort_keys=True, default=str))
        finally:
            runtime.close()
        return 0
    if args.command == "competition-session":
        runtime = competition_build(settings_builder())
        try:
            result = runtime.orchestrator.run(args.date)
            print(json.dumps(_jsonable(result), indent=2, sort_keys=True, default=str))
        finally:
            runtime.close()
        return 0
    if args.command == "serve":
        if uvicorn_runner is None:
            import uvicorn

            uvicorn_runner = uvicorn.run
        app = app_build(settings_builder())
        uvicorn_runner(app, host=args.host, port=args.port)
        return 0
    return None
