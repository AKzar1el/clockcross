import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from clockcross.alpaca.mcp import McpEvidence, McpEvidenceItem
from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.domain import AgentAction, AgentDecision, AgentDriver, EpisodeState, FeatureVector
from clockcross.ledger import Ledger
from clockcross.scheduler import Scheduler, SignalEvidence
from clockcross.trading.risk import PortfolioState, RiskGovernor

SESSION = date(2026, 9, 1)
NOW = datetime(2026, 9, 1, 13, 55, tzinfo=timezone.utc)
EXPIRATION = date(2026, 9, 11)


def contract(symbol: str, strike: str, delta: str, bid: str, ask: str) -> OptionContractSnapshot:
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=EXPIRATION,
        strike=Decimal(strike),
        option_type="call",
        bid=Decimal(bid),
        ask=Decimal(ask),
        quote_timestamp=NOW - timedelta(seconds=5),
        delta=Decimal(delta),
    )


class Ready:
    def require_ready(self, *, mode: str) -> None:
        return None


class Signal:
    def collect_premarket(self, session_date: date) -> FeatureVector:
        assert session_date == SESSION
        return FeatureVector(
            session_date=session_date,
            underlying="COIN",
            btc_return=-0.0148,
            prior_close=186.55,
            premarket_price=180.18,
            equity_premarket_return=-0.0341,
            beta=1.15,
            expected_return=-0.0170,
            residual=-0.0171,
        )

    def opening_confirmation(self, features: FeatureVector) -> FeatureVector:
        return features.model_copy(update={"opening_10m_return": -0.0143})

    def evaluate(self, features: FeatureVector) -> SignalEvidence:
        return SignalEvidence(
            approved=True,
            reason="cross_market_evidence_passed",
            residual_z=-2.0,
            historical_mean_signed_return=0.0084,
        )


class Chains:
    def get_chain(self, underlying: str, *, now: datetime) -> OptionChainSnapshot:
        assert underlying == "COIN"
        assert now == NOW
        return OptionChainSnapshot(
            underlying="COIN",
            feed="indicative",
            contracts=[
                contract("COIN_LONG", "180", "0.55", "4.80", "5.00"),
                contract("COIN_SHORT_NEAR", "192.5", "0.35", "2.50", "2.70"),
                contract("COIN_SHORT_FAR", "200", "0.15", "1.00", "1.20"),
            ],
        )


class Mcp:
    def collect_context(self, request: object) -> McpEvidence:
        return McpEvidence(
            items=[
                McpEvidenceItem(
                    tool_name="get_news",
                    arguments={"symbols": "COIN"},
                    invoked_at=NOW,
                    success=True,
                    result_sha256="news",
                    content=[],
                ),
                McpEvidenceItem(
                    tool_name="get_clock",
                    arguments={},
                    invoked_at=NOW,
                    success=True,
                    result_sha256="clock",
                    content={"is_open": True},
                ),
            ]
        )


class Ai:
    def decide(self, context: object) -> AgentDecision:
        return AgentDecision(
            action=AgentAction.REVERSION,
            confidence=0.55,
            driver=AgentDriver.MACRO,
            reason="Sep 1 regression: preserve AI direction flexibility",
        )


class Portfolio:
    def current(self) -> PortfolioState:
        return PortfolioState(
            starting_equity=Decimal("100000"),
            current_equity=Decimal("99965"),
            buying_power=Decimal("100000"),
            aggregate_defined_loss=Decimal("0"),
            open_underlyings=(),
        )


class TrackingRisk(RiskGovernor):
    def __init__(self) -> None:
        super().__init__()
        self.constructor_budget_calls = 0

    def max_candidate_net_debit(self, portfolio: PortfolioState) -> Decimal:
        self.constructor_budget_calls += 1
        return Decimal("10")


class Execution:
    def submit(self, episode_id: str, candidate: object, risk: object) -> object:
        raise AssertionError("dry-run must not submit")

    def reconcile(self, order: object) -> object:
        raise AssertionError("dry-run must not reconcile")


def test_scheduler_applies_risk_budget_and_records_directional_exposure(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    risk = TrackingRisk()
    scheduler = Scheduler(
        ledger=ledger,
        readiness_gate=Ready(),
        signal_gateway=Signal(),
        chain_gateway=Chains(),
        mcp_gateway=Mcp(),
        adjudicator=Ai(),
        portfolio_gateway=Portfolio(),
        risk_governor=risk,
        execution=Execution(),
        now=lambda: NOW,
    )

    try:
        result = scheduler.run_session(SESSION, mode="dry-run")
        assert result.state is EpisodeState.RISK_APPROVED
        assert result.decision is not None
        assert result.decision.action is AgentAction.REVERSION
        assert result.candidate is not None
        assert result.candidate.long_leg.symbol == "COIN_LONG"
        assert result.candidate.short_leg.symbol == "COIN_SHORT_FAR"
        assert risk.constructor_budget_calls == 1

        row = ledger._conn.execute(
            "SELECT payload_json FROM marks WHERE episode_id = ? AND value = ?",
            (result.episode_id, "spread_candidate"),
        ).fetchone()
        assert row is not None
        payload = json.loads(row["payload_json"])
        assert Decimal(payload["long_delta"]) == Decimal("0.55")
        assert Decimal(payload["short_delta"]) == Decimal("0.15")
        assert Decimal(payload["net_delta"]) == Decimal("0.40")
        assert Decimal(payload["net_debit"]) == Decimal("4.00")
        assert Decimal(payload["delta_per_debit"]) == Decimal("0.10")
    finally:
        ledger.close()
