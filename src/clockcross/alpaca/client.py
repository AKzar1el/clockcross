from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clockcross.config import Settings


@dataclass(frozen=True)
class AlpacaClients:
    """Lazy Alpaca client factory so pure research code has no SDK import side effects."""

    settings: Settings

    def _require_sdk(self) -> dict[str, Any]:
        try:
            from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
            from alpaca.trading.client import TradingClient
        except ImportError as exc:  # pragma: no cover - exercised only in integration environment
            raise RuntimeError("alpaca-py is required for live Alpaca access") from exc
        return {
            "CryptoHistoricalDataClient": CryptoHistoricalDataClient,
            "StockHistoricalDataClient": StockHistoricalDataClient,
            "TradingClient": TradingClient,
        }

    def stock_data(self) -> Any:
        sdk = self._require_sdk()
        return sdk["StockHistoricalDataClient"](
            self.settings.alpaca_api_key,
            self.settings.alpaca_secret_key,
        )

    def crypto_data(self) -> Any:
        sdk = self._require_sdk()
        return sdk["CryptoHistoricalDataClient"](
            self.settings.alpaca_api_key,
            self.settings.alpaca_secret_key,
        )

    def trading(self) -> Any:
        sdk = self._require_sdk()
        return sdk["TradingClient"](
            self.settings.alpaca_api_key,
            self.settings.alpaca_secret_key,
            paper=True,
        )
