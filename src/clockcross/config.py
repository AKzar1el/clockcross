from __future__ import annotations

from datetime import time
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_trading_base_url: AnyHttpUrl = AnyHttpUrl(PAPER_TRADING_URL)
    alpaca_data_base_url: AnyHttpUrl = AnyHttpUrl("https://data.alpaca.markets")
    historical_stock_feed: Literal["iex", "sip"] = "sip"
    live_stock_feed: Literal["iex", "sip", "delayed_sip"] = "delayed_sip"
    option_feed: Literal["indicative", "opra"] = "indicative"
    llm_base_url: AnyHttpUrl = AnyHttpUrl(
        "https://clockcross-ai-gateway.tomi-seregi99.workers.dev/v1"
    )
    llm_api_key: str | None = None
    llm_model: str | None = "clockcross-cloudflare-llama-3.3-70b"
    featherless_api_key: str | None = None
    clockcross_account_role: Literal["development", "competition"] = "development"
    clockcross_allow_dev_order: bool = False
    competition_starting_equity: Decimal = Decimal(100000)
    competition_open_fill_seconds: int = Field(default=180, gt=0)
    competition_close_fill_seconds: int = Field(default=120, gt=0)
    competition_cancel_confirm_seconds: int = Field(default=30, gt=0)
    competition_poll_seconds: int = Field(default=5, gt=0)
    competition_latest_entry_time: time = time(10, 5)
    competition_exit_time: time = time(10, 55)
    competition_max_close_attempts: int = Field(default=2, ge=1)
    research_verdict_path: Path = Path("artifacts/research/verdict.json")
    live_signal_policy_path: Path = Path("docs/research/2026-08-29-live-signal-policy.json")
    mutation_spec_path: Path = Path("docs/superpowers/specs/2026-08-29-coin-options-mutation.md")
    research_config_hash: str = "2b452f02bea99067"
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

    @model_validator(mode="after")
    def validate_competition_policy(self) -> Settings:
        if self.competition_exit_time <= self.decision_time:
            raise ValueError("competition exit must be after decision time")
        if self.competition_latest_entry_time < self.decision_time:
            raise ValueError("competition latest entry must not precede decision time")
        if self.competition_max_close_attempts != 2:
            raise ValueError("competition close attempts are frozen at two")
        return self

    @model_validator(mode="after")
    def require_alpaca_credentials(self) -> Settings:
        if not self.alpaca_api_key.strip() or not self.alpaca_secret_key.strip():
            raise ValueError("Alpaca API credentials are required")
        return self
