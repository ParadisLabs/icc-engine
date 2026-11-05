import json
import unittest

from icc_v2.data.oanda_fx import OandaPracticeFx, OandaFxAuthenticationError


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class OandaFxTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"candles": [
            {"time": "2026-01-01T00:00:00.000000000Z", "volume": 123,
             "complete": True, "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"}},
            {"time": "2026-01-01T00:15:00Z", "volume": 5,
             "complete": False, "mid": {"o": "1.15", "h": "1.2", "l": "1.1", "c": "1.18"}},
        ]}

    def test_candles_label_oanda_volume_as_price_updates_not_exchange_volume(self):
        seen = {}
        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["authorization"] = request.get_header("Authorization")
            return FakeResponse(self.payload)

        adapter = OandaPracticeFx("test-token", urlopen_fn=opener)
        candles = adapter.candles("eur_usd", "M15", count=2)
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].instrument, "EUR_USD")
        self.assertEqual(candles[0].price_update_count, 123)
        self.assertEqual(candles[0].volume_kind, "broker_price_update_count")
        self.assertEqual(candles[0].market_type, "forex_spot")
        self.assertIn("/v3/instruments/EUR_USD/candles", seen["url"])
        self.assertEqual(seen["authorization"], "Bearer test-token")
        self.assertNotIn("token", seen["url"])

    def test_can_include_incomplete_candle_when_explicitly_requested(self):
        adapter = OandaPracticeFx("test-token", urlopen_fn=lambda *_a, **_k: FakeResponse(self.payload))
        candles = adapter.candles("GBP_USD", complete_only=False)
        self.assertEqual(len(candles), 2)

    def test_rejects_live_endpoint_and_invalid_requests(self):
        with self.assertRaises(ValueError):
            OandaPracticeFx("token", base_url="https://api-fxtrade.oanda.com")
        adapter = OandaPracticeFx("token", urlopen_fn=lambda *_a, **_k: FakeResponse(self.payload))
        with self.assertRaises(ValueError):
            adapter.candles("EURUSD")
        with self.assertRaises(ValueError):
            adapter.candles("EUR_USD", "BAD")
        with self.assertRaises(ValueError):
            adapter.candles("EUR_USD", count=0)

    def test_authentication_failure_does_not_expose_token(self):
        from urllib.error import HTTPError
        def opener(*_args, **_kwargs):
            raise HTTPError("https://api-fxpractice.oanda.com", 401, "unauthorized", {}, None)
        adapter = OandaPracticeFx("secret-token", urlopen_fn=opener, retries=0)
        with self.assertRaises(OandaFxAuthenticationError) as ctx:
            adapter.candles("EUR_USD")
        self.assertNotIn("secret-token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
