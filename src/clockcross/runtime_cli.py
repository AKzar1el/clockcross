from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel


def register_runtime_subcommands(subparsers: Any) -> None:
    run_once = subparsers.add_parser("run-once")
    run_once.add_argument("--date", required=True, type=date.fromisoformat)
    run_once.add_argument("--mode", choices=("dry-run", "paper"), default="dry-run")
    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--date", required=True, type=date.fromisoformat)
    serve = subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def execute_runtime_command(
    args: argparse.Namespace,
    *,
    settings_factory: Callable[[], Any] | None = None,
    runtime_builder: Callable[[Any], Any] | None = None,
    reconciliation_builder: Callable[[Any], Any] | None = None,
    app_builder: Callable[[Any], Any] | None = None,
    uvicorn_runner: Callable[..., Any] | None = None,
) -> int | None:
    from clockcross.config import Settings
    from clockcross.runtime import build_evidence_app, build_reconciliation_runtime, build_runtime
    settings_factory = settings_factory or Settings
    runtime_builder = runtime_builder or build_runtime
    reconciliation_builder = reconciliation_builder or build_reconciliation_runtime
    app_builder = app_builder or build_evidence_app
    if args.command == "run-once":
        runtime = runtime_builder(settings_factory())
        try:
            summary = runtime.scheduler.run_session(args.date, mode=args.mode)
            print(json.dumps(_jsonable(summary), indent=2, sort_keys=True, default=str))
        finally:
            runtime.close()
        return 0
    if args.command == "reconcile":
        runtime = reconciliation_builder(settings_factory())
        try:
            summary = runtime.scheduler.reconcile_session(args.date)
            print(json.dumps(_jsonable(summary), indent=2, sort_keys=True, default=str))
        finally:
            runtime.close()
        return 0
    if args.command == "serve":
        if uvicorn_runner is None:
            import uvicorn
            uvicorn_runner = uvicorn.run
        app = app_builder(settings_factory())
        uvicorn_runner(app, host=args.host, port=args.port)
        return 0
    return None
