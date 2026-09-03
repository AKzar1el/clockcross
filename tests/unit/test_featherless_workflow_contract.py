from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/featherless-bakeoff.yml"


def test_featherless_workflow_reuses_competition_secret_boundary() -> None:
    text = WORKFLOW.read_text()
    assert "environment: competition" in text
    assert "secrets.ALPACA_COMPETITION_API_KEY" in text
    assert "secrets.ALPACA_COMPETITION_SECRET_KEY" in text
    assert "secrets.CLOCKCROSS_AI_GATEWAY_BEARER" in text
    assert "secrets.FEATHERLESS_API_KEY" in text
