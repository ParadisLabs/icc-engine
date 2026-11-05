import unittest

from icc_v2.strategy.core import Bar, SetupCandidate
from icc_v2.strategy.walk_forward import CandidatePath, evaluate_walk_forward


def path(index):
    signal_time = index * 1000
    candidate = SetupCandidate(
        symbol="BTCUSDT", side="LONG", signal_time_ms=signal_time,
        reference_price=100.0, stop_loss=98.0, take_profit=102.0,
        risk_per_unit=2.0, score=70.0, features={},
    )
    future = (Bar(signal_time + 1, 100.0, 103.0, 99.0, 102.0),)
    return CandidatePath(candidate, future)


class WalkForwardTests(unittest.TestCase):
    def test_expanding_walk_forward_uses_prior_closed_outcomes(self):
        folds = evaluate_walk_forward(
            [path(i) for i in range(6)],
            train_candidates=2, test_candidates=2, step_candidates=2,
            min_training_trades=1, fee_bps_per_side=0, slippage_bps_per_side=0,
        )
        self.assertEqual(len(folds), 2)
        self.assertEqual(folds[0].training_closed_trades, 2)
        self.assertEqual(folds[0].test_metrics["trades"], 2)
        self.assertEqual(folds[1].training_candidates, 4)
        self.assertEqual(folds[1].training_closed_trades, 4)

    def test_training_threshold_skips_undersized_first_fold(self):
        folds = evaluate_walk_forward(
            [path(i) for i in range(6)],
            train_candidates=2, test_candidates=2, step_candidates=2,
            min_training_trades=3, fee_bps_per_side=0, slippage_bps_per_side=0,
        )
        self.assertEqual(len(folds), 1)
        self.assertEqual(folds[0].fold, 1)
        self.assertEqual(folds[0].training_closed_trades, 4)

    def test_rejects_invalid_windows_and_returns_empty_when_insufficient(self):
        with self.assertRaises(ValueError):
            evaluate_walk_forward([path(i) for i in range(6)], train_candidates=0)
        self.assertEqual(evaluate_walk_forward([path(i) for i in range(3)], train_candidates=2, test_candidates=2), ())


if __name__ == "__main__":
    unittest.main()
