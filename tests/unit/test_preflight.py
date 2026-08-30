from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.mcp import McpEvidence, McpEvidenceItem
from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.domain import AgentAction, AgentDecision, AgentDriver
from clockcross.preflight import run_read_only_preflight

NOW = datetime(2026, 8, 30, 13, 0, tzinfo=timezone.utc)


class AccountProbe:
    def __init__(self, *, trading_level: int = 3, max_level: int = 3) -> None:
        self.trading_level = trading_level
        self.max_level = max_level

    def account(self):
        return {
            "status": "ACTIVE",
            "trading_blocked": False,
            "options_trading_level": self.trading_level,
        }

    def configuration(self):
        return {"max_options_trading_level": self.max_level}


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


def test_preflight_reports_missing_options_level_and_empty_chain_without_throwing():
    report = run_read_only_preflight(
        account=AccountProbe(trading_level=2, max_level=2),
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
