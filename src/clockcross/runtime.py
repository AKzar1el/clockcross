from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from clockcross.ledger import Ledger
from clockcross.live_signal import LiveSignalPolicy
from clockcross.trading.risk import PortfolioState

PAPER_TRADING_URL = "https://paper-api.alpaca.markets"
AccountRole = Literal["development", "competition"]
RunMode = Literal["dry-run", "paper"]


class AlpacaPaperAccountRestClient:
    """Read-only account/configuration/position client pinned to Alpaca paper."""

    def __init__(self, api_key: str, secret_key: str, *, base_url: str = PAPER_TRADING_URL, http_client: Any | None = None, timeout_seconds: float = 20.0) -> None:
        import httpx
        normalized = base_url.rstrip("/")
        if normalized != PAPER_TRADING_URL:
            raise ValueError("ClockCross account access permits only the Alpaca paper endpoint")
        self._base_url = normalized
        self._http = http_client or httpx.Client(timeout=timeout_seconds)
        self._timeout = timeout_seconds
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    def _get(self, path: str) -> Any:
        response = self._http.get(f"{self._base_url}{path}", headers=self._headers, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def account(self) -> dict[str, Any]:
        payload = self._get("/v2/account")
        if not isinstance(payload, dict):
            raise ValueError("unexpected Alpaca account response")
        return payload

    def configuration(self) -> dict[str, Any]:
        payload = self._get("/v2/account/configurations")
        if not isinstance(payload, dict):
            raise ValueError("unexpected Alpaca account configuration response")
        return payload

    def positions(self) -> list[dict[str, Any]]:
        payload = self._get("/v2/positions")
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("unexpected Alpaca positions response")
        return payload


def _decimal_field(payload: dict[str, Any], key: str, *, fallback: str | None = None) -> Decimal:
    raw = payload.get(key)
    if raw is None and fallback is not None:
        raw = payload.get(fallback)
    if raw is None:
        raise ValueError(f"Alpaca account is missing {key}")
    return Decimal(str(raw))


def _underlying_for_position(symbol: str) -> str:
    return "COIN" if symbol.startswith("COIN") else symbol


class AlpacaPortfolioGateway:
    def __init__(self, account: AlpacaPaperAccountRestClient, *, starting_equity: Decimal) -> None:
        self._account = account
        self._starting_equity = starting_equity

    def current(self) -> PortfolioState:
        account = self._account.account()
        positions = self._account.positions()
        underlyings = tuple(sorted({_underlying_for_position(str(item.get("symbol", ""))) for item in positions if item.get("symbol")}))
        return PortfolioState(
            starting_equity=self._starting_equity,
            current_equity=_decimal_field(account, "equity"),
            buying_power=_decimal_field(account, "options_buying_power", fallback="buying_power"),
            aggregate_defined_loss=Decimal("0"),
            open_underlyings=underlyings,
        )

    def public_status(self) -> dict[str, Any]:
        account = self._account.account()
        positions = self._account.positions()
        return {
            "status": account.get("status"),
            "equity": _decimal_field(account, "equity"),
            "options_buying_power": _decimal_field(account, "options_buying_power", fallback="buying_power"),
            "options_approved_level": int(account.get("options_approved_level", 0)),
            "options_trading_level": int(account.get("options_trading_level", 0)),
            "trading_blocked": bool(account.get("trading_blocked", False)),
            "open_position_count": len(positions),
        }


class AccountReadinessGate:
    """Protect development order opt-in and pristine competition-account start."""

    def __init__(self, *, account: AlpacaPaperAccountRestClient, ledger: Ledger, account_role: AccountRole, allow_dev_order: bool, starting_equity: Decimal) -> None:
        self._account = account
        self._ledger = ledger
        self._role = account_role
        self._allow_dev_order = allow_dev_order
        self._starting_equity = starting_equity

    def require_ready(self, *, mode: RunMode) -> None:
        if self._role == "competition" and self._allow_dev_order:
            raise RuntimeError("competition account refuses the development-order flag")
        if mode == "paper" and self._role == "development" and not self._allow_dev_order:
            raise RuntimeError("development order opt-in is required for paper mode")
        if mode == "dry-run":
            return
        account = self._account.account()
        config = self._account.configuration()
        positions = self._account.positions()
        if str(account.get("status", "")).upper() != "ACTIVE":
            raise RuntimeError("Alpaca paper account is not ACTIVE")
        if bool(account.get("trading_blocked", False)):
            raise RuntimeError("Alpaca paper account trading is blocked")
        if int(account.get("options_trading_level", 0)) < 3:
            raise RuntimeError("Alpaca paper account requires options Level 3 for spreads")
        if int(config.get("max_options_trading_level", 0)) < 3:
            raise RuntimeError("Alpaca maximum options trading level must permit Level 3")
        if self._role == "competition" and self._ledger.count_rows("episodes") == 0:
            equity = _decimal_field(account, "equity")
            if equity != self._starting_equity:
                raise RuntimeError(f"fresh competition account equity must be exactly {self._starting_equity}")
            if positions:
                raise RuntimeError("fresh competition account must have no open positions")


class AlpacaOptionChainGateway:
    def __init__(self, client: Any, *, feed: Literal["indicative", "opra"]) -> None:
        self._client = client
        self._feed = feed

    def get_chain(self, underlying: str, *, now: datetime) -> Any:
        if underlying != "COIN":
            raise ValueError("ClockCross live option-chain access is restricted to COIN")
        if now.tzinfo is None:
            raise ValueError("option-chain runtime time must be timezone-aware")
        return self._client.fetch_chain(underlying, feed=self._feed, expiration_gte=now.date() + timedelta(days=7), expiration_lte=now.date() + timedelta(days=21))


class CompositeReadinessGate:
    def __init__(self, *gates: Any) -> None:
        self._gates = gates

    def require_ready(self, *, mode: RunMode) -> None:
        for gate in self._gates:
            gate.require_ready(mode=mode)


def load_live_signal_policy(path: str | Path) -> LiveSignalPolicy:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("live signal policy must be a JSON object")
    return LiveSignalPolicy.model_validate(payload)


def _load_coin_research_mean(path: str | Path) -> float | None:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("research verdict must be a JSON object")
    symbols = payload.get("symbols")
    if not isinstance(symbols, dict):
        return None
    coin = symbols.get("COIN")
    if not isinstance(coin, dict):
        return None
    mean = coin.get("mean_test_return")
    return float(mean) if isinstance(mean, (int, float)) else None


class RuntimeBundle:
    def __init__(self, *, scheduler: Any, ledger: Ledger, account_provider: AlpacaPortfolioGateway) -> None:
        self.scheduler = scheduler
        self.ledger = ledger
        self.account_provider = account_provider

    def close(self) -> None:
        self.ledger.close()


def build_runtime(settings: Any, *, now: Any | None = None) -> RuntimeBundle:
    """Build the real paper runtime without performing an order or network call."""
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY must be configured before ClockCross runtime start")
    if not settings.llm_model:
        raise RuntimeError("LLM_MODEL must be configured before ClockCross runtime start")
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from clockcross.agent.adjudicator import Adjudicator
    from clockcross.alpaca.historical import AlpacaRestHistoryClient, HistoricalDataGateway
    from clockcross.alpaca.mcp import AlpacaMcpGateway, DefaultAlpacaMcpRunner
    from clockcross.alpaca.options import AlpacaOptionChainRestClient
    from clockcross.live_signal import LiveCoinSignalGateway
    from clockcross.scheduler import ApprovedMutationGate, Scheduler
    from clockcross.trading.execution import AlpacaPaperTradingRestClient, ExecutionService
    from clockcross.trading.risk import RiskGovernor, RiskPolicy

    clock = now or (lambda: datetime.now(timezone.utc))
    ledger = Ledger(settings.db_path)
    try:
        account_client = AlpacaPaperAccountRestClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_trading_base_url).rstrip("/"))
        portfolio = AlpacaPortfolioGateway(account_client, starting_equity=settings.competition_starting_equity)
        account_gate = AccountReadinessGate(account=account_client, ledger=ledger, account_role=settings.clockcross_account_role, allow_dev_order=settings.clockcross_allow_dev_order, starting_equity=settings.competition_starting_equity)
        mutation_gate = ApprovedMutationGate(verdict_path=settings.research_verdict_path, mutation_spec_path=settings.mutation_spec_path, expected_config_hash=settings.research_config_hash, mutation_id="coin-options-2026-08-29")
        readiness = CompositeReadinessGate(mutation_gate, account_gate)
        history_rest = AlpacaRestHistoryClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_data_base_url).rstrip("/"))
        history = HistoricalDataGateway(stock_fetcher=lambda symbol, begin, finish: history_rest.fetch_stock_bars(symbol, begin, finish, feed="sip"), crypto_fetcher=lambda symbol, begin, finish: history_rest.fetch_crypto_bars(symbol, begin, finish), cache_root=None, stock_feed="sip")
        policy = load_live_signal_policy(settings.live_signal_policy_path)
        signal = LiveCoinSignalGateway(history=history, policy=policy, historical_mean_signed_return=_load_coin_research_mean(settings.research_verdict_path))
        chain_client = AlpacaOptionChainRestClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_data_base_url).rstrip("/"))
        chains = AlpacaOptionChainGateway(chain_client, feed=settings.option_feed)
        mcp = AlpacaMcpGateway(runner=DefaultAlpacaMcpRunner(api_key=settings.alpaca_api_key, secret_key=settings.alpaca_secret_key))
        adjudicator = Adjudicator(base_url=str(settings.llm_base_url).rstrip("/"), api_key=settings.llm_api_key, model=settings.llm_model)
        final_cutoff = None
        if settings.clockcross_account_role == "competition":
            final_cutoff = datetime(2026, 9, 4, 10, 20, tzinfo=ZoneInfo("America/New_York"))
        risk = RiskGovernor(RiskPolicy(final_entry_cutoff=final_cutoff))
        trading = AlpacaPaperTradingRestClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_trading_base_url).rstrip("/"))
        execution = ExecutionService(ledger=ledger, trading=trading)
        scheduler = Scheduler(ledger=ledger, readiness_gate=readiness, signal_gateway=signal, chain_gateway=chains, mcp_gateway=mcp, adjudicator=adjudicator, portfolio_gateway=portfolio, risk_governor=risk, execution=execution, now=clock)
        return RuntimeBundle(scheduler=scheduler, ledger=ledger, account_provider=portfolio)
    except Exception:
        ledger.close()
        raise


def build_reconciliation_runtime(settings: Any) -> RuntimeBundle:
    """Build only the durable paper-order recovery path; no LLM/signal stack."""
    from datetime import datetime, timezone
    from clockcross.scheduler import Scheduler
    from clockcross.trading.execution import AlpacaPaperTradingRestClient, ExecutionService
    ledger = Ledger(settings.db_path)
    try:
        account_client = AlpacaPaperAccountRestClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_trading_base_url).rstrip("/"))
        portfolio = AlpacaPortfolioGateway(account_client, starting_equity=settings.competition_starting_equity)
        trading = AlpacaPaperTradingRestClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_trading_base_url).rstrip("/"))
        execution = ExecutionService(ledger=ledger, trading=trading)
        scheduler = Scheduler(ledger=ledger, readiness_gate=None, signal_gateway=None, chain_gateway=None, mcp_gateway=None, adjudicator=None, portfolio_gateway=portfolio, risk_governor=None, execution=execution, now=lambda: datetime.now(timezone.utc))
        return RuntimeBundle(scheduler=scheduler, ledger=ledger, account_provider=portfolio)
    except Exception:
        ledger.close()
        raise


def build_public_account_provider(settings: Any) -> AlpacaPortfolioGateway:
    client = AlpacaPaperAccountRestClient(settings.alpaca_api_key, settings.alpaca_secret_key, base_url=str(settings.alpaca_trading_base_url).rstrip("/"))
    return AlpacaPortfolioGateway(client, starting_equity=settings.competition_starting_equity)


def build_evidence_app(settings: Any) -> Any:
    from clockcross.api import create_app
    return create_app(research_path=settings.research_verdict_path, account_provider=build_public_account_provider(settings))
