from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.smoke import run_mleg_smoke

NOW = datetime(2026, 8, 31, 14, 0, tzinfo=timezone.utc)
EXP = date(2026, 9, 11)


def contract(symbol: str, strike: str, delta: str, bid: str, ask: str):
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=EXP,
        strike=Decimal(strike),
        option_type="call",
        bid=Decimal(bid),
        ask=Decimal(ask),
        quote_timestamp=NOW - timedelta(seconds=5),
        delta=Decimal(delta),
    )


def chain(displayed_debit: Decimal = Decimal("2.50")) -> OptionChainSnapshot:
    # long ask - short bid = displayed_debit
    long_ask = Decimal("5.20")
    short_bid = long_ask - displayed_debit
    short_ask = short_bid + Decimal("0.20")
    return OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract("COIN260911C00300000", "300", "0.55", "5.00", str(long_ask)),
            contract(
                "COIN260911C00310000",
                "310",
                "0.15",
                str(short_bid),
                str(short_ask),
            ),
        ],
    )


class ChainGateway:
    def __init__(self, value: OptionChainSnapshot):
        self.value = value
        self.calls = []

    def get_chain(self, underlying: str, *, now: datetime):
        self.calls.append((underlying, now))
        return self.value


class TradingGateway:
    def __init__(self, *, is_open: bool = True):
        self.is_open = is_open
        self.submitted = []
        self.cancelled = []
        self.lookup_calls = []
        self.remote = None

    def clock(self):
        return {"is_open": self.is_open}

    def get_by_client_order_id(self, client_order_id: str):
        self.lookup_calls.append(client_order_id)
        return self.remote

    def submit_vertical(self, candidate, *, client_order_id: str):
        self.submitted.append((candidate, client_order_id))
        self.remote = {
            "id": "alpaca-order-1",
            "client_order_id": client_order_id,
            "status": "accepted",
        }
        return dict(self.remote)

    def cancel_order(self, order_id: str):
        self.cancelled.append(order_id)
        assert self.remote is not None
        self.remote["status"] = "canceled"


def run(*, role="development", allow=True, trading=None, chain_value=None):
    return run_mleg_smoke(
        account_role=role,
        allow_dev_order=allow,
        account_payload={
            "status": "ACTIVE",
            "trading_blocked": False,
            "options_approved_level": 3,
            "options_trading_level": 3,
        },
        configuration_payload={},
        chain_gateway=ChainGateway(chain_value or chain()),
        trading=trading or TradingGateway(),
        now=NOW,
        sleeper=lambda _: None,
        max_polls=2,
    )


def test_smoke_requires_development_role_and_explicit_opt_in():
    with pytest.raises(RuntimeError, match="development account"):
        run(role="competition", allow=True)
    with pytest.raises(RuntimeError, match="opt-in"):
        run(role="development", allow=False)


def test_smoke_requires_active_level3_account_and_open_market():
    with pytest.raises(RuntimeError, match="market is not open"):
        run(trading=TradingGateway(is_open=False))

    with pytest.raises(RuntimeError, match="Level 3"):
        run_mleg_smoke(
            account_role="development",
            allow_dev_order=True,
            account_payload={
                "status": "ACTIVE",
                "trading_blocked": False,
                "options_approved_level": 2,
                "options_trading_level": 2,
            },
            configuration_payload={},
            chain_gateway=ChainGateway(chain()),
            trading=TradingGateway(),
            now=NOW,
            sleeper=lambda _: None,
        )


def test_smoke_uses_deliberately_non_marketable_one_cent_debit_and_confirms_cancel():
    trading = TradingGateway()
    result = run(trading=trading)

    assert result.ok is True
    assert result.displayed_net_debit == Decimal("2.50")
    assert result.submitted_limit == Decimal("0.01")
    assert result.final_status == "canceled"
    assert len(trading.submitted) == 1
    candidate, client_order_id = trading.submitted[0]
    assert candidate.underlying == "COIN"
    assert candidate.net_debit == Decimal("0.01")
    assert candidate.max_loss == Decimal("1.00")
    assert client_order_id.startswith("clockcross-")
    assert trading.cancelled == ["alpaca-order-1"]


def test_smoke_aborts_if_displayed_vertical_is_too_close_to_probe_price():
    with pytest.raises(RuntimeError, match="natural debit"):
        run(chain_value=chain(Decimal("0.25")))


def test_smoke_refuses_duplicate_client_order_identity():
    trading = TradingGateway()
    trading.remote = {"id": "existing", "status": "accepted"}
    with pytest.raises(RuntimeError, match="already exists"):
        run(trading=trading)
    assert trading.submitted == []
    assert trading.cancelled == []
