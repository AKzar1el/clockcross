from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/featherless-bakeoff.yml"


def test_featherless_workflow_reuses_competition_secret_boundary() -> None:
    text = WORKFLOW.read_text()
    assert "environment: competition" in text
    assert "secrets.ALPACA_COMPETITION_API_KEY" in text
    assert "secrets.ALPACA_COMPETITION_SECRET_KEY" in text
    assert "secrets.CLOCKCROSS_AI_GATEWAY_BEARER" in text
    assert "secrets.FEATHERLESS_API_KEY" in text


def test_featherless_workflow_does_not_leak_secrets_into_test_process() -> None:
    text = WORKFLOW.read_text()
    before_steps = text.split("    steps:\n", 1)[0]
    assert "${{ secrets." not in before_steps
    assert text.count("secrets.ALPACA_COMPETITION_API_KEY") == 2
    assert text.count("secrets.ALPACA_COMPETITION_SECRET_KEY") == 2
    assert text.count("secrets.CLOCKCROSS_AI_GATEWAY_BEARER") == 2
    assert text.count("secrets.FEATHERLESS_API_KEY") == 2
