from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_trading_base_url: AnyHttpUrl = PAPER_TRADING_URL
    alpaca_data_base_url: AnyHttpUrl = "https://data.alpaca.markets"
    historical_stock_feed: Literal["iex", "sip"] = "sip"
    live_stock_feed: Literal["iex", "sip", "delayed_sip"] = "delayed_sip"
    option_feed: Literal["indicative", "opra"] = "indicative"
    db_path: Path = Path("data/clockcross.sqlite3")
    artifacts_dir: Path = Path("artifacts")
    timezone: str = "America/New_York"
    feature_freeze_time: time = time(9, 25)
    opening_start_time: time = time(9, 30)
    confirmation_end_time: time = time(9, 40)
    decision_time: time = time(9, 55)
    paper_trading: Literal[True] = True

    @field_validator("alpaca_trading_base_url")
    @classmethod
    def reject_non_paper_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if str(value).rstrip("/") != PAPER_TRADING_URL:
            raise ValueError("ClockCross only permits Alpaca paper trading")
        return value
