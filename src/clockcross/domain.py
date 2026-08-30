from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, PositiveInt


class AgentAction(StrEnum):
    CONTINUATION = "continuation"
    REVERSION = "reversion"
    ABSTAIN = "abstain"


class AgentDriver(StrEnum):
    CRYPTO_CROSS_MARKET = "crypto_cross_market"
    COMPANY_SPECIFIC = "company_specific"
    MACRO = "macro"
    UNCLEAR = "unclear"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class EpisodeState(StrEnum):
    COLLECTING = "COLLECTING"
    FEATURES_FROZEN = "FEATURES_FROZEN"
    OPENING_CONFIRMATION = "OPENING_CONFIRMATION"
    CANDIDATE_READY = "CANDIDATE_READY"
    AI_REVIEWED = "AI_REVIEWED"
    RISK_APPROVED = "RISK_APPROVED"
    ABSTAINED = "ABSTAINED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    MONITORING = "MONITORING"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    CLOSED = "CLOSED"


class MarketSession(BaseModel):
    session_date: date
    feature_freeze: datetime
    opening_start: datetime
    confirmation_end: datetime
    decision_earliest: datetime
    regular_close: datetime


class FeatureVector(BaseModel):
    session_date: date
    underlying: str
    crypto_driver: str = "BTC/USD"
    btc_return: float
    prior_close: float
    premarket_price: float
    equity_premarket_return: float
    beta: float
    expected_return: float
    residual: float
    opening_10m_return: float | None = None


class DecisionEpisode(BaseModel):
    episode_id: str
    state: EpisodeState = EpisodeState.COLLECTING
    features: FeatureVector | None = None
    created_at: datetime
    updated_at: datetime


class AgentDecision(BaseModel):
    action: AgentAction
    confidence: float = Field(ge=0.0, le=1.0)
    idiosyncratic_news_detected: bool = False
    driver: AgentDriver
    reason: str = Field(min_length=1, max_length=600)


class OptionLeg(BaseModel):
    symbol: str = Field(min_length=1)
    side: OrderSide
    ratio: PositiveInt = 1


class SpreadCandidate(BaseModel):
    underlying: str
    expiration: date
    long_leg: OptionLeg
    short_leg: OptionLeg
    net_debit: Decimal = Field(gt=Decimal("0"))
    max_loss: Decimal = Field(gt=Decimal("0"))
    quote_timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskDecision(BaseModel):
    approved: bool
    reasons: list[str] = Field(default_factory=list)
    max_loss: Decimal | None = None
    aggregate_defined_loss: Decimal | None = None
