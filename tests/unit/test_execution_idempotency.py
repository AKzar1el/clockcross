from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from clockcross.domain import OptionLeg, OrderSide, RiskDecision, SpreadCandidate
from clockcross.ledger import Ledger
from clockcross.trading.execution import CloseInstruction, ExecutionService, IndeterminateOrderError


def _candidate() -> SpreadCandidate:
    return SpreadCandidate(
        underlying="COIN",
        expiration=date(2026, 9, 11),
        long_leg=OptionLeg(symbol="COIN260911C00300000", side=OrderSide.BUY, ratio=1),
        short_leg=OptionLeg(symbol="COIN260911C00310000", side=OrderSide.SELL, ratio=1),
        net_debit=Decimal("2.50"),
        max_loss=Decimal("250.00"),
        quote_timestamp=datetime(2026, 8, 31, 13, 54, 55, tzinfo=timezone.utc),
    )


def _close() -> CloseInstruction:
    return CloseInstruction(
        long_symbol="COIN260911C00300000",
        short_symbol="COIN260911C00310000",
        limit_price=Decimal("-1.25"),
        quote_timestamp=datetime(2026, 8, 31, 14, 55, tzinfo=timezone.utc),
        attempt=0,
    )


class AlwaysUncertainTrading:
    def __init__(self) -> None:
        self.open_posts = 0
        self.close_posts = 0
        self.lookups = 0

    def get_by_client_order_id(self, client_order_id: str):
        self.lookups += 1
        return None

    def submit_vertical(self, candidate: SpreadCandidate, *, client_order_id: str):
        self.open_posts += 1
        raise TimeoutError("uncertain")

    def submit_close_vertical(self, instruction: CloseInstruction, *, client_order_id: str):
        self.close_posts += 1
        raise TimeoutError("uncertain")


def test_indeterminate_open_order_is_never_posted_again(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    trading = AlwaysUncertainTrading()
    service = ExecutionService(ledger=ledger, trading=trading)
    risk = RiskDecision(
        approved=True,
        max_loss=Decimal("250"),
        aggregate_defined_loss=Decimal("250"),
    )

    with pytest.raises(IndeterminateOrderError):
        service.submit(episode.episode_id, _candidate(), risk)
    assert trading.open_posts == 1

    with pytest.raises(IndeterminateOrderError):
        service.submit(episode.episode_id, _candidate(), risk)
    assert trading.open_posts == 1
    ledger.close()


def test_indeterminate_close_order_is_never_posted_again(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = ledger.create_episode(date(2026, 8, 31), "COIN")
    trading = AlwaysUncertainTrading()
    service = ExecutionService(ledger=ledger, trading=trading)

    with pytest.raises(IndeterminateOrderError):
        service.submit_close(episode.episode_id, _close())
    assert trading.close_posts == 1

    with pytest.raises(IndeterminateOrderError):
        service.submit_close(episode.episode_id, _close())
    assert trading.close_posts == 1
    ledger.close()
