import os

import pytest


@pytest.mark.skipif(
    os.getenv("CLOCKCROSS_INTEGRATION") != "1",
    reason="requires explicit integration opt-in and Alpaca credentials",
)
def test_alpaca_historical_contract_requires_real_integration_environment() -> None:
    pytest.importorskip("alpaca")
    assert os.getenv("ALPACA_API_KEY")
    assert os.getenv("ALPACA_SECRET_KEY")
