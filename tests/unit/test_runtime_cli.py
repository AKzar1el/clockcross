from __future__ import annotations

import argparse
from datetime import date

from clockcross.domain import EpisodeState
from clockcross.scheduler import EpisodeSummary


def parser():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="command", required=True)
    from clockcross.runtime_cli import register_runtime_subcommands
    register_runtime_subcommands(sub)
    return p


def test_runtime_cli_registers_run_once_reconcile_and_serve():
    p = parser()
    run = p.parse_args(["run-once", "--date", "2026-08-31", "--mode", "dry-run"])
    rec = p.parse_args(["reconcile", "--date", "2026-08-31"])
    serve = p.parse_args(["serve", "--host", "127.0.0.1", "--port", "8000"])
    assert run.date == date(2026, 8, 31) and run.mode == "dry-run"
    assert rec.date == date(2026, 8, 31)
    assert serve.host == "127.0.0.1" and serve.port == 8000


def test_run_once_builds_runtime_executes_and_closes(capsys):
    from clockcross.runtime_cli import execute_runtime_command
    calls=[]
    class Scheduler:
        def run_session(self, day, *, mode):
            calls.append(("run", day, mode))
            return EpisodeSummary("ep", EpisodeState.RISK_APPROVED, reason="dry_run_would_submit")
    class Runtime:
        scheduler=Scheduler()
        def close(self): calls.append(("close",))
    args=parser().parse_args(["run-once","--date","2026-08-31","--mode","dry-run"])
    rc=execute_runtime_command(args, settings_factory=lambda: object(), runtime_builder=lambda settings: Runtime())
    assert rc == 0
    assert calls == [("run", date(2026,8,31), "dry-run"), ("close",)]
    assert '"state": "RISK_APPROVED"' in capsys.readouterr().out


def test_reconcile_uses_recovery_builder_not_full_runtime(capsys):
    from clockcross.runtime_cli import execute_runtime_command
    calls=[]
    class Scheduler:
        def reconcile_session(self, day):
            calls.append(("reconcile", day))
            return EpisodeSummary("ep", EpisodeState.MONITORING)
    class Runtime:
        scheduler=Scheduler()
        def close(self): calls.append(("close",))
    def forbidden(_):
        raise AssertionError("full runtime must not be built for reconcile")
    args=parser().parse_args(["reconcile","--date","2026-08-31"])
    rc=execute_runtime_command(
        args,
        settings_factory=lambda: object(),
        runtime_builder=forbidden,
        reconciliation_builder=lambda settings: Runtime(),
    )
    assert rc == 0
    assert calls == [("reconcile", date(2026,8,31)), ("close",)]
    assert '"state": "MONITORING"' in capsys.readouterr().out


def test_serve_constructs_read_only_app_and_invokes_uvicorn():
    from clockcross.runtime_cli import execute_runtime_command
    calls=[]
    args=parser().parse_args(["serve","--host","0.0.0.0","--port","8123"])
    app=object()
    rc=execute_runtime_command(
        args,
        settings_factory=lambda: object(),
        app_builder=lambda settings: app,
        uvicorn_runner=lambda actual_app, *, host, port: calls.append((actual_app, host, port)),
    )
    assert rc == 0
    assert calls == [(app, "0.0.0.0", 8123)]
