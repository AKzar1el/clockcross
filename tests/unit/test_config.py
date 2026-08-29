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
