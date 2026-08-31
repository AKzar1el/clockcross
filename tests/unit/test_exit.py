from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from clockcross.alpaca.options import OptionChainSnapshot, OptionContractSnapshot
from clockcross.trading.exit import build_close_instruction

NOW = datetime(2026, 8, 31, 14, 55, 0, tzinfo=timezone.utc)
LONG = "COIN260911C00300000"
SHORT = "COIN260911C00310000"


def contract(symbol: str, strike: str, bid: str, ask: str, *, age_seconds: int = 0):
    return OptionContractSnapshot(
        symbol=symbol,
        underlying="COIN",
        expiration=date(2026, 9, 11),
        strike=Decimal(strike),
        option_type="call",
        bid=Decimal(bid),
        ask=Decimal(ask),
        quote_timestamp=NOW - timedelta(seconds=age_seconds),
        delta=Decimal("0.55") if symbol == LONG else Decimal("0.35"),
    )


def chain_with(*, long_bid: str, long_ask: str, short_bid: str, short_ask: str, age_seconds: int = 0):
    return OptionChainSnapshot(
        underlying="COIN",
        feed="indicative",
        contracts=[
            contract(LONG, "300", long_bid, long_ask, age_seconds=age_seconds),
            contract(SHORT, "310", short_bid, short_ask, age_seconds=age_seconds),
        ],
        retrieved_at=NOW,
    )


def test_close_instruction_uses_exact_contracts_and_natural_credit():
    instruction = build_close_instruction(
        chain_with(long_bid="3.10", long_ask="3.20", short_bid="1.70", short_ask="1.80"),
        long_symbol=LONG,
        short_symbol=SHORT,
        now=NOW,
        attempt=0,
    )
    assert instruction.long_symbol == LONG
    assert instruction.short_symbol == SHORT
    assert instruction.limit_price == Decimal("-1.30")
    assert instruction.attempt == 0


def test_close_replacement_uses_fixed_one_cent_credit_floor():
    instruction = build_close_instruction(
        chain_with(long_bid="0.05", long_ask="0.10", short_bid="0.05", short_ask="0.10"),
        long_symbol=LONG,
        short_symbol=SHORT,
        now=NOW,
        attempt=1,
    )
    assert instruction.limit_price == Decimal("-0.01")
    assert instruction.attempt == 1


def test_close_instruction_floors_negative_natural_credit_at_one_cent():
    instruction = build_close_instruction(
        chain_with(long_bid="0.05", long_ask="0.10", short_bid="0.20", short_ask="0.25"),
        long_symbol=LONG,
        short_symbol=SHORT,
        now=NOW,
        attempt=0,
    )
    assert instruction.limit_price == Decimal("-0.01")


def test_close_instruction_rejects_stale_quotes():
    with pytest.raises(ValueError, match="stale"):
        build_close_instruction(
            chain_with(
                long_bid="3.10",
                long_ask="3.20",
                short_bid="1.70",
                short_ask="1.80",
                age_seconds=61,
            ),
            long_symbol=LONG,
            short_symbol=SHORT,
            now=NOW,
            attempt=0,
        )


def test_close_instruction_rejects_missing_exact_contract():
    chain = chain_with(long_bid="3.10", long_ask="3.20", short_bid="1.70", short_ask="1.80")
    with pytest.raises(ValueError, match="exact opening contracts"):
        build_close_instruction(
            chain,
            long_symbol=LONG,
            short_symbol="COIN260911C00320000",
            now=NOW,
            attempt=0,
        )


def test_close_instruction_rejects_crossed_or_zero_quotes():
    with pytest.raises(ValueError, match="quote"):
        build_close_instruction(
            chain_with(long_bid="0", long_ask="0.10", short_bid="0.05", short_ask="0.10"),
            long_symbol=LONG,
            short_symbol=SHORT,
            now=NOW,
            attempt=0,
        )
    with pytest.raises(ValueError, match="quote"):
        build_close_instruction(
            chain_with(long_bid="0.20", long_ask="0.10", short_bid="0.05", short_ask="0.10"),
            long_symbol=LONG,
            short_symbol=SHORT,
            now=NOW,
            attempt=0,
        )


def test_close_instruction_allows_only_two_fixed_attempts():
    with pytest.raises(ValueError, match="attempt"):
        build_close_instruction(
            chain_with(long_bid="3.10", long_ask="3.20", short_bid="1.70", short_ask="1.80"),
            long_symbol=LONG,
            short_symbol=SHORT,
            now=NOW,
            attempt=2,
        )
