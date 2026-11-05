import json
import unittest
from collections import deque
from decimal import Decimal

from icc_v2.data.binance_stream import BinanceSpotWebSocket


class FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.closed = False

    def recv(self):
        if not self.messages:
            return ""
        return json.dumps(self.messages.pop(0))

    def close(self):
        self.closed = True


class FakeSnapshot:
    last_update_id = 100
    bids = (type("Level", (), {"price": Decimal("99"), "quantity": Decimal("2")})(),)
    asks = (type("Level", (), {"price": Decimal("101"), "quantity": Decimal("3")})(),)


class FakeRest:
    def __init__(self):
        self.calls = 0

    def order_book(self, symbol, limit=1000):
        self.calls += 1
        self.asserted_symbol = symbol
        return FakeSnapshot()


class BinanceSpotStreamTests(unittest.TestCase):
    def test_trade_and_depth_events_are_normalized_and_book_bootstrapped(self):
        messages = [
            {"stream": "btcusdt@trade", "data": {
                "e": "trade", "s": "BTCUSDT", "t": 7, "T": 1000,
                "p": "100", "q": "0.5", "m": False,
            }},
            {"stream": "btcusdt@trade", "data": {
                "e": "trade", "s": "BTCUSDT", "t": 7, "T": 1000,
                "p": "100", "q": "0.5", "m": False,
            }},
            {"stream": "btcusdt@depth@100ms", "data": {
                "e": "depthUpdate", "s": "BTCUSDT", "E": 1100,
                "U": 101, "u": 101, "b": [["99", "4"]], "a": [],
            }},
        ]
        sock = FakeSocket(messages)
        rest = FakeRest()
        client = BinanceSpotWebSocket(
            ["BTCUSDT"], rest=rest, socket_factory=lambda _: sock, clock_ms=lambda: 1200
        )
        events = []
        count = client.run_once(events.append, max_messages=3)
        self.assertEqual(count, 3)
        self.assertTrue(sock.closed)
        self.assertEqual(rest.calls, 1)
        self.assertEqual([e.kind for e in events], ["trade", "depth"])
        self.assertEqual(events[0].payload["aggressor_side"], "buy")
        self.assertEqual(events[1].payload["last_update_id"], 101)
        self.assertEqual(events[1].payload["bids"][0], ["99", "4"])
        self.assertFalse(client.books["btcusdt"].synchronized)

    def test_trade_aggressor_side_respects_buyer_is_maker_flag(self):
        client = BinanceSpotWebSocket(["ETHUSDT"], rest=FakeRest(), socket_factory=lambda _: None)
        buffers = {"ethusdt": deque()}
        snapshots = {"ethusdt": None}
        event = client._handle({
            "e": "trade", "s": "ETHUSDT", "t": 1, "T": 1000,
            "p": "10", "q": "2", "m": True,
        }, 1100, buffers, snapshots)
        self.assertEqual(event.payload["aggressor_side"], "sell")


    def test_unbridgeable_snapshot_is_refetched(self):
        class ChangingRest:
            def __init__(self):
                self.ids = [100, 101]
                self.calls = 0

            def order_book(self, symbol, limit=1000):
                self.calls += 1
                snap = type("Snapshot", (), {
                    "last_update_id": self.ids.pop(0),
                    "bids": FakeSnapshot.bids,
                    "asks": FakeSnapshot.asks,
                })()
                return snap

        rest = ChangingRest()
        client = BinanceSpotWebSocket(["BTCUSDT"], rest=rest, socket_factory=lambda _: None)
        buffers = {"btcusdt": deque()}
        snapshots = {"btcusdt": None}
        first = client._handle({
            "e": "depthUpdate", "s": "BTCUSDT", "E": 1000,
            "U": 103, "u": 103, "b": [], "a": [],
        }, 1100, buffers, snapshots)
        self.assertIsNone(first)
        self.assertIsNone(snapshots["btcusdt"])
        second = client._handle({
            "e": "depthUpdate", "s": "BTCUSDT", "E": 1100,
            "U": 102, "u": 103, "b": [["99", "4"]], "a": [],
        }, 1200, buffers, snapshots)
        self.assertIsNotNone(second)
        self.assertEqual(rest.calls, 2)
        self.assertTrue(second.payload["synchronized"])

    def test_combined_stream_symbol_limit_is_enforced(self):
        with self.assertRaises(ValueError):
            BinanceSpotWebSocket([f"SYM{i}" for i in range(513)])

    def test_invalid_symbols_and_empty_universe_are_rejected(self):
        with self.assertRaises(ValueError):
            BinanceSpotWebSocket([])
        with self.assertRaises(ValueError):
            BinanceSpotWebSocket(["BTC/USDT"])


if __name__ == "__main__":
    unittest.main()
