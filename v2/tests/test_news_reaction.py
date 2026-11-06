import unittest

from icc_v2.strategy.core import Bar, SetupCandidate
from icc_v2.strategy.news_reaction import (
    NewsEvent, assess_post_release_reaction, confirm_news_candidate,
)


def bars_for_event(event_time=1_000_000):
    bars = []
    # Stable pre-event baseline: 0.001 range per one-minute candle.
    for i in range(20):
        ts = event_time - (20 - i) * 60_000
        bars.append(Bar(ts, 1.1000, 1.1005, 1.0995, 1.1000))
    # Three closed post-release candles with a material upward move.
    for i in range(3):
        ts = event_time + (i + 1) * 60_000
        base = 1.1010 + i * 0.0010
        bars.append(Bar(ts, base, base + 0.0020, base - 0.0002, base + 0.0015))
    return bars


def candidate(side="LONG", signal_time=1_000_000 + 5 * 60_000, symbol="EUR_USD"):
    return SetupCandidate(
        symbol=symbol, side=side, signal_time_ms=signal_time,
        reference_price=1.1040, stop_loss=1.1020, take_profit=1.1070,
        risk_per_unit=0.0020, score=80.0, features={},
    )


class NewsReactionTests(unittest.TestCase):
    def setUp(self):
        self.event = NewsEvent(
            event_id="event-1", currency="EUR", event_time_ms=1_000_000,
            title="High impact release", actual="1.2", forecast="1.0",
        )

    def test_measures_observed_move_not_actual_forecast_direction(self):
        reaction = assess_post_release_reaction(self.event, "EUR_USD", bars_for_event())
        self.assertTrue(reaction.eligible)
        self.assertEqual(reaction.direction, "UP")
        self.assertGreaterEqual(reaction.move_atr, 0.5)
        self.assertGreaterEqual(reaction.range_expansion, 1.2)

    def test_waits_for_closed_post_release_bars_and_baseline(self):
        reaction = assess_post_release_reaction(self.event, "EUR_USD", bars_for_event()[:21])
        self.assertFalse(reaction.eligible)
        self.assertIn("WAITING_FOR_CLOSED_POST_RELEASE_BARS", reaction.reasons)

    def test_candidate_must_be_delayed_fresh_and_aligned(self):
        reaction = assess_post_release_reaction(self.event, "EUR_USD", bars_for_event())
        decision = confirm_news_candidate(self.event, candidate(), reaction)
        self.assertTrue(decision.eligible)
        wrong_side = confirm_news_candidate(self.event, candidate("SHORT"), reaction)
        self.assertFalse(wrong_side.eligible)
        self.assertIn("SETUP_NOT_ALIGNED_WITH_OBSERVED_REACTION", wrong_side.reasons)

    def test_rejects_wrong_pair_or_too_early_setup(self):
        with self.assertRaises(ValueError):
            assess_post_release_reaction(self.event, "USD_JPY", bars_for_event())
        reaction = assess_post_release_reaction(self.event, "EUR_USD", bars_for_event())
        early = confirm_news_candidate(
            self.event, candidate(signal_time=self.event.event_time_ms + 60_000), reaction
        )
        self.assertFalse(early.eligible)
        self.assertIn("TOO_EARLY_AFTER_RELEASE", early.reasons)

    def test_excludes_the_minute_candle_that_overlaps_release(self):
        event_time = 100_050_000  # 30 seconds after the candle's open
        event = NewsEvent(event_id="offset", currency="EUR", event_time_ms=event_time)
        bars = []
        for i in range(20):
            ts = event_time - (20 - i) * 60_000 - 30_000
            bars.append(Bar(ts, 1.1000, 1.1005, 1.0995, 1.1000))
        # This candle starts before the release and closes after it; it must not
        # be counted as either pre-event baseline or post-event reaction.
        bars.append(Bar(event_time - 30_000, 1.1000, 1.1050, 1.0950, 1.1040))
        for i in range(3):
            ts = event_time + 30_000 + i * 60_000
            base = 1.1010 + i * 0.0010
            bars.append(Bar(ts, base, base + 0.0020, base - 0.0002, base + 0.0015))
        reaction = assess_post_release_reaction(event, "EUR_USD", bars)
        self.assertTrue(reaction.eligible)
        self.assertEqual(reaction.post_release_bars, 3)

    def test_rejects_duplicate_or_out_of_order_bars(self):
        bad = bars_for_event()
        bad[-1] = bad[-2]
        with self.assertRaises(ValueError):
            assess_post_release_reaction(self.event, "EUR_USD", bad)


if __name__ == "__main__":
    unittest.main()
