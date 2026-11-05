"""Bounded Binance Spot universe discovery and liquidity ranking.

This module selects research candidates, not trade signals. Ranking is based on
exchange-reported 24h quote turnover only; strategy quality is evaluated later.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .binance_public import BinancePublicSpot
from .binance_usdm import BinanceUsdmPublic


class BinanceUsdmUniverseScanner:
    """Discover active USD-M perpetuals and rank a bounded liquidity shortlist."""

    def __init__(
        self,
        adapter: BinanceUsdmPublic | None = None,
        *,
        quote_assets: set[str] | None = None,
        max_symbols: int = 100,
        min_quote_volume: Decimal | str = Decimal("10000000"),
        excluded_base_assets: set[str] | None = None,
    ) -> None:
        if max_symbols < 1:
            raise ValueError("max_symbols must be positive")
        self.adapter = adapter or BinanceUsdmPublic()
        self.quote_assets = {x.upper() for x in ({"USDT", "USDC"} if quote_assets is None else quote_assets)}
        if not self.quote_assets:
            raise ValueError("at least one quote asset is required")
        self.max_symbols = max_symbols
        self.min_quote_volume = Decimal(str(min_quote_volume))
        if not self.min_quote_volume.is_finite() or self.min_quote_volume < 0:
            raise ValueError("min_quote_volume must be finite and non-negative")
        self.excluded_base_assets = BinanceSpotUniverseScanner.DEFAULT_STABLE_BASES | {
            x.upper() for x in (excluded_base_assets or set())
        }

    def scan(self) -> list[UniverseCandidate]:
        """Use one Futures metadata request and one all-symbol ticker snapshot."""
        instruments = self.adapter.exchange_info(quote_assets=self.quote_assets)
        tickers = self.adapter.tickers_24h()
        by_symbol = {row["symbol"]: row for row in tickers}
        candidates: list[UniverseCandidate] = []
        for instrument in instruments:
            symbol = str(instrument.get("symbol", "")).upper()
            base = str(instrument.get("baseAsset", "")).upper()
            quote = str(instrument.get("quoteAsset", "")).upper()
            if not symbol or not base or quote not in self.quote_assets:
                continue
            if base in self.excluded_base_assets:
                continue
            ticker = by_symbol.get(symbol)
            if ticker is None:
                continue
            turnover = ticker["quote_volume_24h"]
            if turnover < self.min_quote_volume:
                continue
            candidates.append(UniverseCandidate(
                venue="binance", market_type="perpetual", symbol=symbol,
                base_asset=base, quote_asset=quote,
                last_price=ticker["last_price"],
                base_volume_24h=ticker["base_volume_24h"],
                quote_volume_24h=turnover,
                trade_count_24h=ticker["trade_count_24h"],
                price_change_percent_24h=ticker["price_change_percent_24h"],
            ))
        candidates.sort(key=lambda item: (item.quote_volume_24h, item.trade_count_24h), reverse=True)
        return candidates[:self.max_symbols]



@dataclass(frozen=True)
class UniverseCandidate:
    venue: str
    market_type: str
    symbol: str
    base_asset: str
    quote_asset: str
    last_price: Decimal
    base_volume_24h: Decimal
    quote_volume_24h: Decimal
    trade_count_24h: int
    price_change_percent_24h: Decimal


class BinanceSpotUniverseScanner:
    """Discover active Spot pairs and rank a bounded shortlist by quote turnover."""

    DEFAULT_STABLE_BASES = frozenset({
        "USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "GBP",
    })
    LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")

    def __init__(
        self,
        adapter: BinancePublicSpot | None = None,
        *,
        quote_assets: set[str] | None = None,
        max_symbols: int = 100,
        min_quote_volume: Decimal | str = Decimal("5000000"),
        excluded_base_assets: set[str] | None = None,
    ) -> None:
        if max_symbols < 1:
            raise ValueError("max_symbols must be positive")
        self.adapter = adapter or BinancePublicSpot()
        self.quote_assets = {x.upper() for x in ({"USDT", "USDC"} if quote_assets is None else quote_assets)}
        if not self.quote_assets:
            raise ValueError("at least one quote asset is required")
        self.max_symbols = max_symbols
        self.min_quote_volume = Decimal(str(min_quote_volume))
        if not self.min_quote_volume.is_finite() or self.min_quote_volume < 0:
            raise ValueError("min_quote_volume must be finite and non-negative")
        self.excluded_base_assets = self.DEFAULT_STABLE_BASES | {
            x.upper() for x in (excluded_base_assets or set())
        }

    def scan(self) -> list[UniverseCandidate]:
        """Use one metadata request and one all-symbol ticker request per scan."""
        instruments = self.adapter.exchange_info(quote_assets=self.quote_assets)
        tickers = self.adapter.tickers_24h()
        by_symbol = {row["symbol"]: row for row in tickers}
        candidates: list[UniverseCandidate] = []

        for instrument in instruments:
            symbol = str(instrument.get("symbol", "")).upper()
            base = str(instrument.get("baseAsset", "")).upper()
            quote = str(instrument.get("quoteAsset", "")).upper()
            if not symbol or not base or quote not in self.quote_assets:
                continue
            if base in self.excluded_base_assets:
                continue
            if base.endswith(self.LEVERAGED_SUFFIXES):
                continue
            ticker = by_symbol.get(symbol)
            if ticker is None:
                continue
            turnover = ticker["quote_volume_24h"]
            if turnover < self.min_quote_volume:
                continue
            candidates.append(UniverseCandidate(
                venue="binance", market_type="spot", symbol=symbol,
                base_asset=base, quote_asset=quote,
                last_price=ticker["last_price"],
                base_volume_24h=ticker["base_volume_24h"],
                quote_volume_24h=turnover,
                trade_count_24h=ticker["trade_count_24h"],
                price_change_percent_24h=ticker["price_change_percent_24h"],
            ))

        candidates.sort(key=lambda item: (item.quote_volume_24h, item.trade_count_24h), reverse=True)
        return candidates[:self.max_symbols]
