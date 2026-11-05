import tempfile
import unittest
from pathlib import Path

from icc_v2.strategy.core import SetupCandidate
from icc_v2.strategy.memory import SetupMemoryStore


def candidate(symbol="BTCUSDT", side="LONG", timestamp=1000):
    return SetupCandidate(
        symbol=symbol, side=side, signal_time_ms=timestamp,
        reference_price=100.0, stop_loss=98.0, take_profit=103.0,
        risk_per_unit=2.0, score=75.0, features={"rsi": 58.0, "volume_ratio": "unavailable"},
    )


class SetupMemoryTests(unittest.TestCase):
    def test_setup_is_idempotent_and_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            store = SetupMemoryStore(path)
            event_id, inserted = store.record_setup(
                candidate(), venue="binance", market_type="spot", created_at_ms=1100
            )
            self.assertTrue(inserted)
            same_id, inserted_again = store.record_setup(
                candidate(), venue="BINANCE", market_type="SPOT", created_at_ms=1200
            )
            self.assertEqual(event_id, same_id)
            self.assertFalse(inserted_again)
            store.close()

            reopened = SetupMemoryStore(path)
            self.assertTrue(reopened.record_outcome(event_id, 1.5, closed_at_ms=2000))
            self.assertFalse(reopened.record_outcome(event_id, 1.5, closed_at_ms=2100))
            stats = reopened.stats()
            self.assertEqual(len(stats), 1)
            self.assertEqual(stats[0].symbol, "BTCUSDT")
            self.assertEqual(stats[0].wins, 1)
            self.assertEqual(stats[0].expectancy_r, 1.5)
            reopened.close()

    def test_outcomes_are_immutable_and_unknown_ids_rejected(self):
        with SetupMemoryStore(":memory:") as store:
            event_id, _ = store.record_setup(candidate(), venue="binance", market_type="spot")
            store.record_outcome(event_id, -1.0)
            with self.assertRaises(ValueError):
                store.record_outcome(event_id, 0.5)
            with self.assertRaises(KeyError):
                store.record_outcome("missing", 1.0)

    def test_rejects_non_finite_outcomes_and_invalid_sample_threshold(self):
        with SetupMemoryStore(":memory:") as store:
            event_id, _ = store.record_setup(candidate(), venue="binance", market_type="spot")
            with self.assertRaises(ValueError):
                store.record_outcome(event_id, float("nan"))
            with self.assertRaises(ValueError):
                store.stats(min_samples=0)


if __name__ == "__main__":
    unittest.main()
