from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from clockcross.domain import OptionLeg, OrderSide, RiskDecision, SpreadCandidate
from clockcross.ledger import Ledger
from clockcross.trading.execution import (
    AlpacaPaperTradingRestClient,
    ExecutionService,
    IndeterminateOrderError,
    build_client_order_id,
)


def candidate():
    return SpreadCandidate(
        underlying="COIN",
        expiration=date(2026, 9, 11),
        long_leg=OptionLeg(symbol="COIN260911C00300000", side=OrderSide.BUY, ratio=1),
        short_leg=OptionLeg(symbol="COIN260911C00310000", side=OrderSide.SELL, ratio=1),
        net_debit=Decimal("2.50"),
        max_loss=Decimal("250.00"),
        quote_timestamp=datetime(2026, 8, 31, 13, 54, 55, tzinfo=timezone.utc),
        metadata={"structure": "call_debit_spread"},
    )


def approved():
    return RiskDecision(approved=True, max_loss=Decimal("250"), aggregate_defined_loss=Decimal("250"))


def test_client_order_id_is_deterministic_and_short():
    one = build_client_order_id("episode-abc", candidate())
    two = build_client_order_id("episode-abc", candidate())
    assert one == two
    assert one.startswith("clockcross-")
    assert len(one) <= 64


def test_live_trading_url_is_rejected():
    with pytest.raises(ValueError, match="paper"):
        AlpacaPaperTradingRestClient("key", "secret", base_url="https://api.alpaca.markets")


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self):
        self.posts = []
        self.gets = []
        self.deletes = []

    def post(self, url, *, headers, json, timeout):
        self.posts.append((url, headers, json, timeout))
        return FakeResponse({"id": "alpaca-1", "status": "accepted", "client_order_id": json["client_order_id"]})

    def get(self, url, *, headers, params, timeout):
        self.gets.append((url, headers, params, timeout))
        if url.endswith("/v2/clock"):
            return FakeResponse({"is_open": True})
        return FakeResponse({}, status=404)

    def delete(self, url, *, headers, timeout):
        self.deletes.append((url, headers, timeout))
        return FakeResponse({}, status=204)


def test_rest_client_submits_atomic_debit_vertical_payload():
    http = FakeHttp()
    client = AlpacaPaperTradingRestClient("key", "secret", http_client=http)
    result = client.submit_vertical(candidate(), client_order_id="clockcross-test")
    assert result["id"] == "alpaca-1"
    body = http.posts[0][2]
    assert body["order_class"] == "mleg"
    assert body["qty"] == "1"
    assert body["type"] == "limit"
    assert body["limit_price"] == "2.50"
    assert body["time_in_force"] == "day"
    assert "symbol" not in body and "side" not in body
    assert body["legs"] == [
        {"symbol": "COIN260911C00300000", "ratio_qty": "1", "side": "buy", "position_intent": "buy_to_open"},
        {"symbol": "COIN260911C00310000", "ratio_qty": "1", "side": "sell", "position_intent": "sell_to_open"},
    ]


def test_rest_client_reads_paper_market_clock():
    http = FakeHttp()
    client = AlpacaPaperTradingRestClient("key", "secret", http_client=http)

    result = client.clock()

    assert result == {"is_open": True}
    assert http.gets[0][0] == "https://paper-api.alpaca.markets/v2/clock"
    assert http.gets[0][2] == {}


def test_rest_client_cancels_parent_order_by_id():
    http = FakeHttp()
    client = AlpacaPaperTradingRestClient("key", "secret", http_client=http)

    client.cancel_order("alpaca-1")

    assert http.deletes[0][0] == "https://paper-api.alpaca.markets/v2/orders/alpaca-1"


class FakeTrading:
    def __init__(self, *, existing=None, submit_result=None, submit_exc=None, reconcile_after_error=None):
        self.existing = existing
        self.submit_result = submit_result or {"id": "alpaca-1", "status": "accepted"}
        self.submit_exc = submit_exc
        self.reconcile_after_error = reconcile_after_error
        self.lookup_count = 0
        self.submit_count = 0

    def get_by_client_order_id(self, client_order_id):
        self.lookup_count += 1
        if self.lookup_count == 1:
            return self.existing
        return self.reconcile_after_error

    def submit_vertical(self, candidate, *, client_order_id):
        self.submit_count += 1
        if self.submit_exc is not None:
            raise self.submit_exc
        return {**self.submit_result, "client_order_id": client_order_id}


def make_episode(ledger):
    return ledger.create_episode(date(2026, 8, 31), "COIN")


def test_execution_reconciles_existing_remote_order_before_post(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = make_episode(ledger)
    trading = FakeTrading(existing={"id": "alpaca-existing", "status": "accepted"})
    result = ExecutionService(ledger=ledger, trading=trading).submit(episode.episode_id, candidate(), approved())
    assert result.alpaca_order_id == "alpaca-existing"
    assert result.reconciled is True
    assert trading.submit_count == 0
    assert ledger.count_rows("orders") == 1
    ledger.close()


def test_timeout_reconciles_by_client_id_without_second_post(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = make_episode(ledger)
    trading = FakeTrading(submit_exc=TimeoutError("uncertain"), reconcile_after_error={"id": "alpaca-after-timeout", "status": "accepted"})
    result = ExecutionService(ledger=ledger, trading=trading).submit(episode.episode_id, candidate(), approved())
    assert result.alpaca_order_id == "alpaca-after-timeout"
    assert result.reconciled is True
    assert trading.submit_count == 1
    assert trading.lookup_count == 2
    ledger.close()


def test_timeout_without_reconciliation_is_indeterminate_and_never_reposts(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = make_episode(ledger)
    trading = FakeTrading(submit_exc=TimeoutError("uncertain"), reconcile_after_error=None)
    with pytest.raises(IndeterminateOrderError):
        ExecutionService(ledger=ledger, trading=trading).submit(episode.episode_id, candidate(), approved())
    assert trading.submit_count == 1
    stored = ledger.get_order_by_client_id(build_client_order_id(episode.episode_id, candidate()))
    assert stored is not None and stored.status == "indeterminate"
    ledger.close()


def test_rejected_risk_never_calls_trading(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = make_episode(ledger)
    trading = FakeTrading()
    with pytest.raises(ValueError, match="risk"):
        ExecutionService(ledger=ledger, trading=trading).submit(episode.episode_id, candidate(), RiskDecision(approved=False, reasons=["cap"]))
    assert trading.lookup_count == 0 and trading.submit_count == 0
    ledger.close()


def test_httpx_timeout_is_indeterminate_not_rejected(tmp_path):
    import httpx

    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = make_episode(ledger)
    trading = FakeTrading(submit_exc=httpx.ReadTimeout("uncertain"), reconcile_after_error=None)
    with pytest.raises(IndeterminateOrderError):
        ExecutionService(ledger=ledger, trading=trading).submit(episode.episode_id, candidate(), approved())
    stored = ledger.get_order_by_client_id(build_client_order_id(episode.episode_id, candidate()))
    assert stored is not None and stored.status == "indeterminate"
    ledger.close()


def test_reconcile_known_order_queries_only_and_updates_ledger(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    episode = make_episode(ledger)
    order = ledger.record_order(episode.episode_id, client_order_id="clockcross-known", alpaca_order_id="alpaca-known", status="accepted")
    trading = FakeTrading(existing={"id": "alpaca-known", "status": "filled"})
    result = ExecutionService(ledger=ledger, trading=trading).reconcile(order)
    assert result.reconciled is True
    assert result.status == "filled"
    assert trading.lookup_count == 1
    assert trading.submit_count == 0
    stored = ledger.get_order_by_client_id("clockcross-known")
    assert stored is not None and stored.status == "filled"
    ledger.close()
