from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from clockcross.alpaca.mcp import McpEvidence, McpEvidenceItem
from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.domain import AgentAction, AgentDecision, AgentDriver
from clockcross.ledger import Ledger
from clockcross.preflight import run_read_only_preflight
from clockcross.runtime import AccountReadinessGate, AlpacaPaperAccountRestClient

NOW = datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)


class AccountProbe:
    def __init__(
        self,
        *,
        approved_level: int = 3,
        trading_level: int = 3,
        max_level: int | None = 3,
        equity: str = "100000",
        positions: list[dict[str, Any]] | None = None,
        orders: list[dict[str, Any]] | None = None,
    ) -> None:
        self.approved_level = approved_level
        self.trading_level = trading_level
        self.max_level = max_level
        self.equity = equity
        self._positions = list(positions or [])
        self._orders = list(orders or [])

    def account(self):
        return {
            "status": "ACTIVE",
            "trading_blocked": False,
            "options_approved_level": self.approved_level,
            "options_trading_level": self.trading_level,
            "equity": self.equity,
        }

    def configuration(self):
        if self.max_level is None:
            return {}
        return {"max_options_trading_level": self.max_level}

    def positions(self):
        return list(self._positions)

    def orders(self):
        return list(self._orders)


class ChainProbe:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.calls = []

    def get_chain(self, underlying: str, *, now: datetime) -> OptionChainSnapshot:
        self.calls.append((underlying, now))
        contracts = [] if self.empty else [
            OptionContractSnapshot(
                symbol="COIN260909C00300000",
                underlying="COIN",
                expiration=(now + timedelta(days=10)).date(),
                strike=Decimal("300"),
                option_type="call",
                bid=Decimal("5.00"),
                ask=Decimal("5.50"),
                quote_timestamp=now - timedelta(days=2),
                delta=Decimal("0.50"),
            )
        ]
        return OptionChainSnapshot(
            underlying="COIN",
            feed="indicative",
            contracts=contracts,
            retrieved_at=now,
        )


class McpProbe:
    def collect_context(self, request):
        assert len(request.calls) == 1
        assert request.calls[0].name == "get_clock"
        return McpEvidence(
            items=[
                McpEvidenceItem(
                    tool_name="get_clock",
                    arguments={},
                    invoked_at=NOW,
                    success=True,
                    result_sha256="abc123",
                    content={"is_open": False},
                )
            ]
        )


class AiProbe:
    def decide(self, context):
        assert context.underlying == "COIN"
        assert context.news_summary.startswith("Preflight")
        return AgentDecision(
            action=AgentAction.ABSTAIN,
            confidence=0.5,
            idiosyncratic_news_detected=False,
            driver=AgentDriver.UNCLEAR,
            reason="preflight_schema_ok",
        )


class ResponseProbe:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self.payload


class HttpProbe:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.urls: list[str] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> ResponseProbe:
        assert headers["APCA-API-KEY-ID"] == "key"
        assert headers["APCA-API-SECRET-KEY"] == "secret"
        assert timeout == 20.0
        self.urls.append(url)
        return ResponseProbe(self.payload)


def run_preflight(account: AccountProbe):
    return run_read_only_preflight(
        account=account,
        chain_gateway=ChainProbe(),
        mcp_gateway=McpProbe(),
        adjudicator=AiProbe(),
        now=NOW,
    )


def test_read_only_preflight_accepts_closed_market_chain_and_checks_external_surfaces():
    chain = ChainProbe()
    report = run_read_only_preflight(
        account=AccountProbe(),
        chain_gateway=chain,
        mcp_gateway=McpProbe(),
        adjudicator=AiProbe(),
        now=NOW,
    )

    assert report.ok is True
    assert [check.name for check in report.checks] == [
        "account_active_unblocked",
        "options_level_3",
        "coin_option_chain",
        "alpaca_mcp",
        "ai_provider",
    ]
    assert all(check.ok for check in report.checks)
    assert chain.calls == [("COIN", NOW)]


def test_preflight_accepts_level3_account_when_configuration_omits_max_level():
    report = run_preflight(AccountProbe(max_level=None))
    check = {item.name: item for item in report.checks}["options_level_3"]

    assert check.ok is True
    assert "approved=3" in check.detail
    assert "trading=3" in check.detail
    assert "not_reported" in check.detail


def test_preflight_rejects_account_not_approved_for_level3():
    report = run_preflight(AccountProbe(approved_level=2, trading_level=3, max_level=3))
    check = {item.name: item for item in report.checks}["options_level_3"]

    assert check.ok is False


def test_preflight_reports_missing_options_level_and_empty_chain_without_throwing():
    report = run_read_only_preflight(
        account=AccountProbe(approved_level=2, trading_level=2, max_level=2),
        chain_gateway=ChainProbe(empty=True),
        mcp_gateway=McpProbe(),
        adjudicator=None,
        now=NOW,
    )

    checks = {check.name: check for check in report.checks}
    assert report.ok is False
    assert checks["options_level_3"].ok is False
    assert checks["coin_option_chain"].ok is False
    assert checks["ai_provider"].ok is False
    assert "not configured" in checks["ai_provider"].detail


def build_readiness_gate(tmp_path, account: AccountProbe) -> tuple[AccountReadinessGate, Ledger]:
    ledger = Ledger(tmp_path / "readiness.db")
    gate = AccountReadinessGate(
        account=account,
        ledger=ledger,
        account_role="development",
        allow_dev_order=True,
        starting_equity=Decimal("100000"),
    )
    return gate, ledger


def build_competition_readiness_gate(
    tmp_path, account: AccountProbe
) -> tuple[AccountReadinessGate, Ledger]:
    ledger = Ledger(tmp_path / "competition-readiness.db")
    gate = AccountReadinessGate(
        account=account,
        ledger=ledger,
        account_role="competition",
        allow_dev_order=False,
        starting_equity=Decimal("100000"),
    )
    return gate, ledger


def test_paper_readiness_accepts_level3_account_when_configuration_omits_max_level(tmp_path):
    gate, ledger = build_readiness_gate(tmp_path, AccountProbe(max_level=None))
    try:
        gate.require_ready(mode="paper")
    finally:
        ledger.close()


def test_paper_readiness_rejects_account_not_approved_for_level3(tmp_path):
    gate, ledger = build_readiness_gate(
        tmp_path,
        AccountProbe(approved_level=2, trading_level=3, max_level=3),
    )
    try:
        with pytest.raises(RuntimeError, match="Level 3"):
            gate.require_ready(mode="paper")
    finally:
        ledger.close()


def test_fresh_competition_readiness_accepts_pristine_account(tmp_path):
    gate, ledger = build_competition_readiness_gate(tmp_path, AccountProbe())
    try:
        gate.require_ready(mode="paper")
    finally:
        ledger.close()


def test_fresh_competition_readiness_rejects_existing_order_history(tmp_path):
    gate, ledger = build_competition_readiness_gate(
        tmp_path,
        AccountProbe(orders=[{"id": "prior-order", "status": "canceled"}]),
    )
    try:
        with pytest.raises(RuntimeError, match="order history"):
            gate.require_ready(mode="paper")
    finally:
        ledger.close()


def test_account_client_orders_requests_latest_order_history():
    http = HttpProbe([{"id": "prior-order", "status": "canceled"}])
    client = AlpacaPaperAccountRestClient("key", "secret", http_client=http)

    assert client.orders() == [{"id": "prior-order", "status": "canceled"}]
    assert http.urls == [
        "https://paper-api.alpaca.markets/v2/orders?status=all&limit=1&direction=desc"
    ]
