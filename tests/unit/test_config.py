from datetime import time

from pydantic import ValidationError
import pytest

from clockcross.config import Settings


def test_settings_default_to_paper_and_reject_live_url() -> None:
    settings = Settings(
        alpaca_api_key="x",
        alpaca_secret_key="y",
        alpaca_trading_base_url="https://paper-api.alpaca.markets",
    )
    assert settings.paper_trading is True

    with pytest.raises(ValidationError):
        Settings(
            alpaca_api_key="x",
            alpaca_secret_key="y",
            alpaca_trading_base_url="https://api.alpaca.markets",
        )


def test_settings_use_sip_history_and_delayed_sip_live_by_default() -> None:
    settings = Settings(alpaca_api_key="x", alpaca_secret_key="y")
    assert settings.historical_stock_feed == "sip"
    assert settings.live_stock_feed == "delayed_sip"


def test_settings_default_to_proven_clockcross_ai_gateway_without_embedding_key() -> None:
    settings = Settings(alpaca_api_key="x", alpaca_secret_key="y")

    assert str(settings.llm_base_url).rstrip("/") == (
        "https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1"
    )
    assert settings.llm_model == "clockcross-cloudflare-llama-3.3-70b"
    assert settings.llm_api_key is None


def test_competition_lifecycle_defaults_are_frozen() -> None:
    settings = Settings(alpaca_api_key="x", alpaca_secret_key="y")

    assert settings.competition_open_fill_seconds == 180
    assert settings.competition_close_fill_seconds == 120
    assert settings.competition_cancel_confirm_seconds == 30
    assert settings.competition_poll_seconds == 5
    assert settings.competition_latest_entry_time == time(10, 5)
    assert settings.competition_exit_time == time(10, 55)
    assert settings.competition_max_close_attempts == 2


def test_competition_exit_must_follow_frozen_decision_time() -> None:
    with pytest.raises(ValidationError, match="competition exit"):
        Settings(
            alpaca_api_key="x",
            alpaca_secret_key="y",
            competition_exit_time=time(9, 55),
        )


def test_competition_latest_entry_cannot_precede_decision_time() -> None:
    with pytest.raises(ValidationError, match="latest entry"):
        Settings(
            alpaca_api_key="x",
            alpaca_secret_key="y",
            competition_latest_entry_time=time(9, 54),
        )


def test_competition_close_attempt_count_is_frozen_at_two() -> None:
    with pytest.raises(ValidationError, match="close attempts"):
        Settings(
            alpaca_api_key="x",
            alpaca_secret_key="y",
            competition_max_close_attempts=3,
        )
