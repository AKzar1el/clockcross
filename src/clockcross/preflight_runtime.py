from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from clockcross.agent.adjudicator import Adjudicator
from clockcross.alpaca.mcp import AlpacaMcpGateway, DefaultAlpacaMcpRunner
from clockcross.alpaca.options import AlpacaOptionChainRestClient
from clockcross.preflight import PreflightReport, run_read_only_preflight
from clockcross.runtime import AlpacaOptionChainGateway, AlpacaPaperAccountRestClient


def build_preflight_report(
    settings: Any,
    *,
    now: datetime | None = None,
) -> PreflightReport:
    """Build and execute only read-only external dependency probes."""
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise ValueError("preflight time must be timezone-aware")

    account = AlpacaPaperAccountRestClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        base_url=str(settings.alpaca_trading_base_url).rstrip("/"),
    )
    chain_client = AlpacaOptionChainRestClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        base_url=str(settings.alpaca_data_base_url).rstrip("/"),
    )
    chains = AlpacaOptionChainGateway(chain_client, feed=settings.option_feed)
    mcp = AlpacaMcpGateway(
        runner=DefaultAlpacaMcpRunner(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
    )

    adjudicator = None
    if settings.llm_api_key and settings.llm_model:
        adjudicator = Adjudicator(
            base_url=str(settings.llm_base_url).rstrip("/"),
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

    return run_read_only_preflight(
        account=account,
        chain_gateway=chains,
        mcp_gateway=mcp,
        adjudicator=adjudicator,
        now=checked_at,
    )
