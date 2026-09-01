from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

OptionType = Literal["call", "put"]
OptionFeed = Literal["indicative", "opra"]
Structure = Literal["call_debit_spread", "put_debit_spread"]


class OptionContractSnapshot(BaseModel):
    symbol: str = Field(min_length=1)
    underlying: str = Field(min_length=1)
    expiration: date
    strike: Decimal = Field(gt=Decimal("0"))
    option_type: OptionType
    bid: Decimal = Field(ge=Decimal("0"))
    ask: Decimal = Field(ge=Decimal("0"))
    quote_timestamp: datetime
    delta: Decimal | None = None
    open_interest: int | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_quote_timestamp(self) -> "OptionContractSnapshot":
        if self.quote_timestamp.tzinfo is None:
            raise ValueError("option quote timestamp must be timezone-aware")
        return self


class OptionChainSnapshot(BaseModel):
    underlying: str = Field(min_length=1)
    feed: OptionFeed
    contracts: list[OptionContractSnapshot]
    retrieved_at: datetime | None = None


class OptionFeasibilityPolicy(BaseModel):
    approved_underlying: str = "COIN"
    min_dte: int = Field(default=7, ge=1)
    max_dte: int = Field(default=21, ge=1)
    max_quote_age_seconds: int = Field(default=60, ge=1)
    max_relative_spread: Decimal = Field(default=Decimal("0.25"), gt=Decimal("0"))
    require_delta: bool = True
    long_delta_min: Decimal = Field(default=Decimal("0.45"), ge=Decimal("0"), le=Decimal("1"))
    long_delta_max: Decimal = Field(default=Decimal("0.65"), ge=Decimal("0"), le=Decimal("1"))
    min_net_delta: Decimal = Field(default=Decimal("0.30"), gt=Decimal("0"), le=Decimal("1"))

    @model_validator(mode="after")
    def validate_range(self) -> "OptionFeasibilityPolicy":
        if self.max_dte < self.min_dte:
            raise ValueError("max_dte must be >= min_dte")
        if self.long_delta_max < self.long_delta_min:
            raise ValueError("long_delta_max must be >= long_delta_min")
        return self


class OptionFeasibilityResult(BaseModel):
    feasible: bool
    underlying: str
    feed: OptionFeed
    reasons: list[str] = Field(default_factory=list)
    available_structures: tuple[Structure, ...] = ()
    eligible_contract_count: int = 0
    evaluated_at: datetime


def _quote_age_seconds(contract: OptionContractSnapshot, now: datetime) -> float:
    return (now.astimezone(timezone.utc) - contract.quote_timestamp.astimezone(timezone.utc)).total_seconds()


def _relative_spread(contract: OptionContractSnapshot) -> Decimal | None:
    if contract.bid <= 0 or contract.ask <= 0 or contract.ask < contract.bid:
        return None
    midpoint = (contract.ask + contract.bid) / Decimal("2")
    if midpoint <= 0:
        return None
    return (contract.ask - contract.bid) / midpoint


def _quote_eligible(
    contract: OptionContractSnapshot,
    *,
    now: datetime,
    policy: OptionFeasibilityPolicy,
) -> bool:
    if contract.underlying != policy.approved_underlying:
        return False
    dte = (contract.expiration - now.date()).days
    if dte < policy.min_dte or dte > policy.max_dte:
        return False
    age = _quote_age_seconds(contract, now)
    if age < 0 or age > policy.max_quote_age_seconds:
        return False
    spread = _relative_spread(contract)
    if spread is None or spread > policy.max_relative_spread:
        return False
    return True


def _long_delta_eligible(
    contract: OptionContractSnapshot, policy: OptionFeasibilityPolicy
) -> bool:
    if contract.delta is None:
        return False
    magnitude = abs(contract.delta)
    return policy.long_delta_min <= magnitude <= policy.long_delta_max


def _has_vertical(
    contracts: list[OptionContractSnapshot],
    *,
    option_type: OptionType,
    policy: OptionFeasibilityPolicy,
) -> bool:
    typed = [contract for contract in contracts if contract.option_type == option_type]
    for expiration in sorted({contract.expiration for contract in typed}):
        same_expiry = [contract for contract in typed if contract.expiration == expiration]
        long_legs = [
            contract for contract in same_expiry if _long_delta_eligible(contract, policy)
        ]
        short_legs = [contract for contract in same_expiry if contract.delta is not None]
        for long_leg in long_legs:
            assert long_leg.delta is not None
            for short_leg in short_legs:
                assert short_leg.delta is not None
                if long_leg.symbol == short_leg.symbol:
                    continue
                if option_type == "call" and long_leg.strike >= short_leg.strike:
                    continue
                if option_type == "put" and long_leg.strike <= short_leg.strike:
                    continue
                debit = long_leg.ask - short_leg.bid
                width = abs(short_leg.strike - long_leg.strike)
                if debit <= 0 or debit >= width:
                    continue
                net_delta = abs(long_leg.delta) - abs(short_leg.delta)
                if net_delta >= policy.min_net_delta:
                    return True
    return False


def evaluate_option_feasibility(
    chain: OptionChainSnapshot,
    *,
    now: datetime,
    policy: OptionFeasibilityPolicy | None = None,
) -> OptionFeasibilityResult:
    if now.tzinfo is None:
        raise ValueError("feasibility evaluation time must be timezone-aware")
    policy = policy or OptionFeasibilityPolicy()
    reasons: list[str] = []

    if chain.underlying != policy.approved_underlying:
        return OptionFeasibilityResult(
            feasible=False,
            underlying=chain.underlying,
            feed=chain.feed,
            reasons=["underlying_not_approved"],
            evaluated_at=now,
        )

    quote_eligible = [
        contract for contract in chain.contracts if _quote_eligible(contract, now=now, policy=policy)
    ]
    if not quote_eligible:
        reasons.append("no_eligible_contracts")
        return OptionFeasibilityResult(
            feasible=False,
            underlying=chain.underlying,
            feed=chain.feed,
            reasons=reasons,
            evaluated_at=now,
        )

    if policy.require_delta and not any(contract.delta is not None for contract in quote_eligible):
        reasons.append("missing_required_delta")
        return OptionFeasibilityResult(
            feasible=False,
            underlying=chain.underlying,
            feed=chain.feed,
            reasons=reasons,
            eligible_contract_count=len(quote_eligible),
            evaluated_at=now,
        )

    structures: list[Structure] = []
    if _has_vertical(quote_eligible, option_type="call", policy=policy):
        structures.append("call_debit_spread")
    if _has_vertical(quote_eligible, option_type="put", policy=policy):
        structures.append("put_debit_spread")

    if not structures:
        reasons.append("no_compatible_vertical")
    return OptionFeasibilityResult(
        feasible=bool(structures),
        underlying=chain.underlying,
        feed=chain.feed,
        reasons=reasons,
        available_structures=tuple(structures),
        eligible_contract_count=len(quote_eligible),
        evaluated_at=now,
    )


_OCC_SUFFIX = re.compile(r"(?P<date>\d{6})(?P<kind>[CP])(?P<strike>\d{8})$")


@dataclass(frozen=True)
class ParsedOccOption:
    expiration: date
    option_type: OptionType
    strike: Decimal


def parse_occ_option_symbol(symbol: str) -> ParsedOccOption:
    match = _OCC_SUFFIX.search(symbol)
    if match is None:
        raise ValueError(f"unsupported OCC option symbol: {symbol}")
    expiration = datetime.strptime(match.group("date"), "%y%m%d").date()
    option_type: OptionType = "call" if match.group("kind") == "C" else "put"
    strike = Decimal(int(match.group("strike"))) / Decimal("1000")
    return ParsedOccOption(expiration=expiration, option_type=option_type, strike=strike)


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("option quote timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("option quote timestamp must be timezone-aware")
    return parsed


def normalize_option_chain_payload(
    underlying: str,
    payload: Mapping[str, Any],
    *,
    feed: OptionFeed,
) -> OptionChainSnapshot:
    raw_snapshots = payload.get("snapshots", {})
    if not isinstance(raw_snapshots, Mapping):
        raise ValueError("option-chain snapshots must be a mapping")
    contracts: list[OptionContractSnapshot] = []
    for symbol, raw in raw_snapshots.items():
        if not isinstance(symbol, str) or not isinstance(raw, Mapping):
            continue
        quote = raw.get("latestQuote")
        if not isinstance(quote, Mapping):
            continue
        if "t" not in quote or "bp" not in quote or "ap" not in quote:
            continue
        parsed = parse_occ_option_symbol(symbol)
        greeks = raw.get("greeks")
        delta: Decimal | None = None
        if isinstance(greeks, Mapping) and greeks.get("delta") is not None:
            delta = Decimal(str(greeks["delta"]))
        contracts.append(
            OptionContractSnapshot(
                symbol=symbol,
                underlying=underlying,
                expiration=parsed.expiration,
                strike=parsed.strike,
                option_type=parsed.option_type,
                bid=Decimal(str(quote["bp"])),
                ask=Decimal(str(quote["ap"])),
                quote_timestamp=_parse_timestamp(quote["t"]),
                delta=delta,
            )
        )
    return OptionChainSnapshot(
        underlying=underlying,
        feed=feed,
        contracts=sorted(contracts, key=lambda item: (item.expiration, item.option_type, item.strike)),
        retrieved_at=datetime.now(timezone.utc),
    )


class AlpacaOptionChainRestClient:
    """Read-only Alpaca option-chain client with explicit feed and pagination."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        base_url: str = "https://data.alpaca.markets",
        http_client: Any | None = None,
    ) -> None:
        import httpx

        self._client = http_client or httpx.Client(timeout=30.0)
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

    def fetch_chain(
        self,
        underlying: str,
        *,
        feed: OptionFeed,
        expiration_gte: date,
        expiration_lte: date,
    ) -> OptionChainSnapshot:
        if underlying != "COIN":
            raise ValueError("ClockCross live option-chain access is restricted to COIN")
        params: dict[str, str | int] = {
            "feed": feed,
            "limit": 1000,
        }
        snapshots: dict[str, Any] = {}
        page_token: str | None = None
        while True:
            page_params = dict(params)
            if page_token is not None:
                page_params["page_token"] = page_token
            response = self._client.get(
                f"{self._base_url}/v1beta1/options/snapshots/{underlying}",
                params=page_params,
                headers=self._headers,
            )
            response.raise_for_status()
            payload = response.json()
            page_snapshots = payload.get("snapshots", {})
            if not isinstance(page_snapshots, Mapping):
                raise ValueError("Alpaca option-chain snapshots must be a mapping")
            snapshots.update(page_snapshots)
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        chain = normalize_option_chain_payload(
            underlying,
            {"snapshots": snapshots},
            feed=feed,
        )
        return chain.model_copy(
            update={
                "contracts": [
                    contract
                    for contract in chain.contracts
                    if expiration_gte <= contract.expiration <= expiration_lte
                ]
            }
        )
