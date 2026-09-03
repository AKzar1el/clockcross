from pathlib import Path

from clockcross.config import Settings


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/competition-runtime.yml"
RUNTIME = ROOT / "src/clockcross/runtime.py"


def test_settings_accept_optional_featherless_secret() -> None:
    settings = Settings(
        ALPACA_API_KEY="your-key-here",
        ALPACA_SECRET_KEY="your-secret-here",
        FEATHERLESS_API_KEY="featherless-key",
    )
    assert settings.featherless_api_key == "featherless-key"


def test_featherless_is_not_required_for_normal_runtime_settings() -> None:
    settings = Settings(
        ALPACA_API_KEY="your-key-here",
        ALPACA_SECRET_KEY="your-secret-here",
    )
    assert settings.featherless_api_key is None


def test_competition_workflow_exposes_featherless_secret_only_to_runtime_job() -> None:
    text = WORKFLOW.read_text()
    assert "environment: competition" in text
    assert "FEATHERLESS_API_KEY: ${{ secrets.FEATHERLESS_API_KEY }}" in text


def test_competition_runtime_wires_shadow_without_changing_build_runtime_authority() -> None:
    text = RUNTIME.read_text()
    assert "FeatherlessShadowObserver" in text
    assert "shadow_observer=shadow_observer" in text
    build_runtime_text = text.split("def build_competition_runtime", 1)[0]
    assert "FeatherlessShadowObserver" not in build_runtime_text
