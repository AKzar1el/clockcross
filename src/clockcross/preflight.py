from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from clockcross.agent.adjudicator import AgentContext
from clockcross.alpaca.mcp import McpContextRequest, McpToolRequest
from clockcross.alpaca.options import OptionChainSnapshot
from clockcross.domain import AgentDecision


class PreflightCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class PreflightReport(BaseModel):
    checks: list[PreflightCheck]

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(check.ok for check in self.checks)


class AccountProbe(Protocol):
    def account(self) -> dict[str, Any]: ...
    def configuration(self) -> dict[str, Any]: ...


class ChainProbe(Protocol):
    def get_chain(self, underlying: str, *, now: datetime) -> OptionChainSnapshot: ...


class McpProbe(Protocol):
    def collect_context(self, request: McpContextRequest) -> Any: ...


class AiProbe(Protocol):
    def decide(self, context: AgentContext) -> AgentDecision: ...


def _check_account(
    account: AccountProbe,
) -> tuple[PreflightCheck, PreflightCheck]:
    try:
        payload = account.account()
    except Exception:
        return (
            PreflightCheck(
                name="account_active_unblocked",
                ok=False,
                detail="Alpaca paper account could not be read",
            ),
            PreflightCheck(
                name="options_level_3",
                ok=False,
                detail="options level unavailable because account read failed",
            ),
        )

    active = str(payload.get("status", "")).upper() == "ACTIVE"
    unblocked = not bool(payload.get("trading_blocked", False))
    account_check = PreflightCheck(
        name="account_active_unblocked",
        ok=active and unblocked,
        detail=(
            "paper account is ACTIVE and unblocked"
            if active and unblocked
            else "paper account must be ACTIVE and unblocked"
        ),
    )

    try:
        config = account.configuration()
        trading_level = int(payload.get("options_trading_level", 0))
        max_level = int(config.get("max_options_trading_level", 0))
        level_ok = trading_level >= 3 and max_level >= 3
        level_detail = (
            f"options Level 3 available (trading={trading_level}, max={max_level})"
            if level_ok
            else f"options Level 3 required (trading={trading_level}, max={max_level})"
        )
    except Exception:
        level_ok = False
        level_detail = "options level configuration could not be read"
    level_check = PreflightCheck(
        name="options_level_3",
        ok=level_ok,
        detail=level_detail,
    )
    return account_check, level_check


def _check_chain(
    chain_gateway: ChainProbe,
    *,
    now: datetime,
) -> tuple[PreflightCheck, OptionChainSnapshot | None]:
    try:
        chain = chain_gateway.get_chain("COIN", now=now)
    except Exception:
        return (
            PreflightCheck(
                name="coin_option_chain",
                ok=False,
                detail="COIN option chain could not be read or normalized",
            ),
            None,
        )

    dte_contracts = [
        contract
        for contract in chain.contracts
        if 7 <= (contract.expiration - now.date()).days <= 21
    ]
    ok = chain.underlying == "COIN" and chain.feed in {"indicative", "opra"} and bool(dte_contracts)
    detail = (
        f"parsed {len(dte_contracts)} COIN contracts in the 7-21 DTE window via {chain.feed}"
        if ok
        else "no parseable COIN contracts in the 7-21 DTE window"
    )
    return PreflightCheck(name="coin_option_chain", ok=ok, detail=detail), chain


def _check_mcp(mcp_gateway: McpProbe) -> PreflightCheck:
    request = McpContextRequest(
        calls=(McpToolRequest(name="get_clock", arguments={}),)
    )
    try:
        evidence = mcp_gateway.collect_context(request)
        complete = bool(getattr(evidence, "complete", False))
    except Exception:
        complete = False
    return PreflightCheck(
        name="alpaca_mcp",
        ok=complete,
        detail=(
            "read-only Alpaca MCP get_clock succeeded"
            if complete
            else "read-only Alpaca MCP get_clock failed"
        ),
    )


def _check_ai(
    adjudicator: AiProbe | None,
    *,
    chain: OptionChainSnapshot | None,
) -> PreflightCheck:
    if adjudicator is None:
        return PreflightCheck(
            name="ai_provider",
            ok=False,
            detail="AI provider is not configured",
        )

    feed = "indicative" if chain is None else chain.feed
    context = AgentContext(
        underlying="COIN",
        residual=0.015,
        residual_z=1.5,
        residual_sign=1,
        btc_return=0.02,
        opening_10m_return=0.001,
        historical_mean_signed_return=0.0084,
        option_feed=feed,
        available_structures=("call_debit_spread",),
        news_summary="Preflight schema probe. Do not infer a live trade.",
    )
    try:
        decision = adjudicator.decide(context)
        ok = not decision.reason.startswith("fail_closed:")
    except Exception:
        ok = False
    return PreflightCheck(
        name="ai_provider",
        ok=ok,
        detail=(
            "AI provider returned a schema-valid bounded decision"
            if ok
            else "AI provider connectivity or response schema failed"
        ),
    )


def run_read_only_preflight(
    *,
    account: AccountProbe,
    chain_gateway: ChainProbe,
    mcp_gateway: McpProbe,
    adjudicator: AiProbe | None,
    now: datetime,
) -> PreflightReport:
    """Probe external runtime dependencies without creating episodes or orders."""
    if now.tzinfo is None:
        raise ValueError("preflight time must be timezone-aware")

    account_check, options_check = _check_account(account)
    chain_check, chain = _check_chain(chain_gateway, now=now)
    mcp_check = _check_mcp(mcp_gateway)
    ai_check = _check_ai(adjudicator, chain=chain)
    return PreflightReport(
        checks=[
            account_check,
            options_check,
            chain_check,
            mcp_check,
            ai_check,
        ]
    )
