import unittest
from types import SimpleNamespace

from icc_v2.strategy.news_reaction import NewsEvent
from icc_v2.strategy.news_scan import OandaNewsFxScanner


class FakeOanda:
    def __init__(self, event_time):
        self.event_time = event_time
        self.calls = []

    def candles(self, instrument, granularity, *, count):
        self.calls.append((instrument, granularity, count))
        if granularity != "M1":
            raise AssertionError("higher timeframes should not be fetched without a reaction")
        rows = []
        for i in range(20):
            rows.append(SimpleNamespace(
                timestamp_ms=self.event_time - (20 - i) * 60_000,
                open=1.1000, high=1.1005, low=1.0995, close=1.1000,
                complete=True,
            ))
        for i in range(3):
            rows.append(SimpleNamespace(
                timestamp_ms=self.event_time + (i + 1) * 60_000,
                open=1.1000, high=1.1005, low=1.0995, close=1.1000,
                complete=True,
            ))
        return rows


class OandaNewsFxScannerTests(unittest.TestCase):
    def test_scans_only_event_relevant_pairs_and_stops_after_no_reaction(self):
        event_time = 1_000_000
        adapter = FakeOanda(event_time)
        scanner = OandaNewsFxScanner(
            adapter, instruments=("EUR_USD", "USD_JPY", "GBP_USD"),
            max_instruments=8,
        )
        results = scanner.scan_event(NewsEvent(
            event_id="evt", currency="EUR", event_time_ms=event_time,
        ))
        self.assertEqual([result.instrument for result in results], ["EUR_USD"])
        self.assertEqual(adapter.calls, [("EUR_USD", "M1", 500)])
        self.assertIsNone(results[0].candidate)
        self.assertFalse(results[0].reaction.eligible)

    def test_caps_relevant_pairs(self):
        event_time = 1_000_000
        adapter = FakeOanda(event_time)
        scanner = OandaNewsFxScanner(
            adapter, instruments=("EUR_USD", "EUR_GBP", "EUR_JPY", "USD_JPY"),
            max_instruments=2,
        )
        results = scanner.scan_event(NewsEvent(
            event_id="evt", currency="EUR", event_time_ms=event_time,
        ))
        self.assertEqual(len(results), 2)
        self.assertEqual([x[0] for x in adapter.calls], ["EUR_USD", "EUR_GBP"])


if __name__ == "__main__":
    unittest.main()
