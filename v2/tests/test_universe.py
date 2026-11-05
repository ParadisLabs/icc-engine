import unittest
from decimal import Decimal

from icc_v2.data.universe import BinanceSpotUniverseScanner, BinanceUsdmUniverseScanner


class FakeAdapter:
    def __init__(self):
        self.metadata_calls = 0
        self.ticker_calls = 0

    def exchange_info(self, *, quote_assets=None):
        self.metadata_calls += 1
        return [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"},
            {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT"},
            {"symbol": "USDCUSDT", "baseAsset": "USDC", "quoteAsset": "USDT"},
            {"symbol": "BTCUPUSDT", "baseAsset": "BTCUP", "quoteAsset": "USDT"},
            {"symbol": "LOWUSDT", "baseAsset": "LOW", "quoteAsset": "USDT"},
            {"symbol": "XRPUSDC", "baseAsset": "XRP", "quoteAsset": "USDC"},
            {"symbol": "WRONGBTC", "baseAsset": "WRONG", "quoteAsset": "BTC"},
        ]

    def tickers_24h(self):
        self.ticker_calls += 1
        def row(symbol, quote_volume, trades=10):
            return {
                "symbol": symbol, "last_price": Decimal("10"),
                "base_volume_24h": Decimal("100"),
                "quote_volume_24h": Decimal(str(quote_volume)),
                "trade_count_24h": trades,
                "price_change_percent_24h": Decimal("1"),
            }
        return [
            row("BTCUSDT", 100000000, 500),
            row("ETHUSDT", 50000000, 400),
            row("USDCUSDT", 999999999),
            row("BTCUPUSDT", 999999999),
            row("LOWUSDT", 100),
            row("XRPUSDC", 70000000, 300),
        ]


class UniverseScannerTests(unittest.TestCase):
    def test_ranks_by_reported_quote_turnover_and_applies_filters(self):
        adapter = FakeAdapter()
        scanner = BinanceSpotUniverseScanner(adapter, max_symbols=2, min_quote_volume="1000000")
        results = scanner.scan()
        self.assertEqual([x.symbol for x in results], ["BTCUSDT", "XRPUSDC"])
        self.assertEqual(results[0].quote_volume_24h, Decimal("100000000"))
        self.assertEqual(results[0].market_type, "spot")
        self.assertEqual(adapter.metadata_calls, 1)
        self.assertEqual(adapter.ticker_calls, 1)

    def test_empty_or_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            BinanceSpotUniverseScanner(max_symbols=0)
        with self.assertRaises(ValueError):
            BinanceSpotUniverseScanner(min_quote_volume="-1")
        with self.assertRaises(ValueError):
            BinanceSpotUniverseScanner(quote_assets=set())

    def test_caps_universe_size(self):
        scanner = BinanceSpotUniverseScanner(FakeAdapter(), max_symbols=1, min_quote_volume="0")
        self.assertEqual(len(scanner.scan()), 1)



class FakeFuturesAdapter:
    def __init__(self):
        self.metadata_calls = 0
        self.ticker_calls = 0

    def exchange_info(self, *, quote_assets=None):
        self.metadata_calls += 1
        return [
            {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"},
            {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT"},
            {"symbol": "USDCUSDT", "baseAsset": "USDC", "quoteAsset": "USDT"},
        ]

    def tickers_24h(self):
        self.ticker_calls += 1
        def row(symbol, quote_volume):
            return {
                "symbol": symbol, "last_price": Decimal("10"),
                "base_volume_24h": Decimal("100"),
                "quote_volume_24h": Decimal(str(quote_volume)),
                "trade_count_24h": 10,
                "price_change_percent_24h": Decimal("1"),
            }
        return [row("BTCUSDT", 100000000), row("ETHUSDT", 150000000), row("USDCUSDT", 999999999)]


class UsdmUniverseScannerTests(unittest.TestCase):
    def test_ranks_perpetuals_separately_and_uses_one_ticker_snapshot(self):
        adapter = FakeFuturesAdapter()
        results = BinanceUsdmUniverseScanner(adapter, max_symbols=1, min_quote_volume="1000000").scan()
        self.assertEqual([x.symbol for x in results], ["ETHUSDT"])
        self.assertEqual(results[0].market_type, "perpetual")
        self.assertEqual(adapter.metadata_calls, 1)
        self.assertEqual(adapter.ticker_calls, 1)

    def test_empty_quote_filter_is_rejected(self):
        with self.assertRaises(ValueError):
            BinanceUsdmUniverseScanner(quote_assets=set())


if __name__ == "__main__":
    unittest.main()
