from pathlib import Path


WORKFLOW = Path(".github/workflows/competition-runtime.yml")


def workflow_text() -> str:
    return WORKFLOW.read_text()


def test_competition_workflow_is_timezone_aware_event_bounded_and_secret_backed():
    text = workflow_text()
    assert 'timezone: "America/New_York"' in text
    assert 'cron: "57 9 31 8 *"' in text
    assert 'cron: "55 9 1-4 9 *"' in text
    assert 'cron: "0 10 1-4 9 *"' in text
    assert 'cron: "57 9 1-4 9 *"' not in text
    assert "environment: competition" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "CLOCKCROSS_ACCOUNT_ROLE: competition" in text
    assert 'CLOCKCROSS_ALLOW_DEV_ORDER: "false"' in text
    assert "ALPACA_COMPETITION_API_KEY" in text
    assert "ALPACA_COMPETITION_SECRET_KEY" in text
    assert "CLOCKCROSS_AI_GATEWAY_BEARER" in text
    assert "competition-session" in text
    assert "concurrency:" in text
    for session_date in (
        "2026-08-31",
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
        "2026-09-04",
    ):
        assert session_date in text


def test_competition_workflow_restores_and_persists_durable_state():
    text = workflow_text()
    assert "gh run list" in text
    assert "gh run download" in text
    assert "clockcross-state" in text
    assert "data/clockcross.sqlite3" in text
    assert "actions/upload-artifact@v4" in text
    assert "if: always()" in text
    assert "retention-days: 10" in text


def test_competition_workflow_runs_read_only_preflight_before_order_capable_command():
    text = workflow_text()
    preflight = text.index("uv run clockcross preflight")
    competition = text.index("uv run clockcross competition-session")
    assert preflight < competition


def test_competition_workflow_does_not_echo_or_embed_credentials():
    text = workflow_text()
    assert "set -x" not in text
    assert "env |" not in text
    assert "printenv" not in text
    assert "APCA-API-KEY-ID" not in text
    assert "APCA-API-SECRET-KEY" not in text
    assert "sk-proj-" not in text
    assert "cfut_" not in text
