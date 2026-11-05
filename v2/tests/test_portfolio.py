import unittest

from icc_v2.strategy.core import Bar, SetupCandidate
from icc_v2.strategy.walk_forward import CandidatePath
from icc_v2.strategy.portfolio import simulate_portfolio


def path(index, *, stop_hit=False, delayed=False, signal_step=1000):
    signal_time = index * signal_step
    candidate = SetupCandidate(
        symbol=f"COIN{index}", side="LONG", signal_time_ms=signal_time,
        reference_price=100.0, stop_loss=98.0, take_profit=102.0,
        risk_per_unit=2.0, score=70.0, features={},
    )
    if delayed:
        first = Bar(signal_time + 1, 100.0, 101.0, 99.0, 100.0)
        second = (Bar(signal_time + 2000, 100.0, 101.0, 97.0, 97.5) if stop_hit
                  else Bar(signal_time + 2000, 100.0, 103.0, 99.0, 102.5))
        return CandidatePath(candidate, (first, second))
    bar = (Bar(signal_time + 1, 100.0, 101.0, 97.0, 97.5) if stop_hit
           else Bar(signal_time + 1, 100.0, 103.0, 99.0, 102.5))
    return CandidatePath(candidate, (bar,))


class PortfolioSimulationTests(unittest.TestCase):
    def limits(self, **overrides):
        values = dict(
            initial_equity=10000, risk_per_trade_pct=1.0,
            max_open_risk_pct=2.0, max_open_positions=3,
            max_daily_loss_pct=3.0, max_total_drawdown_pct=10.0,
            fee_bps_per_side=0, slippage_bps_per_side=0,
        )
        values.update(overrides)
        return values

    def test_concurrent_open_risk_is_capped(self):
        report = simulate_portfolio(
            [path(0, delayed=True), path(1, delayed=True)],
            **self.limits(max_open_risk_pct=1.0, max_open_positions=3),
        )
        self.assertEqual(len(report.accepted_trades), 1)
        self.assertEqual(report.rejected_by_reason["MAX_OPEN_RISK"], 1)

    def test_daily_loss_limit_blocks_later_entries_after_realized_loss(self):
        report = simulate_portfolio(
            [path(0, stop_hit=True, delayed=True, signal_step=3000), path(1, signal_step=3000)],
            **self.limits(max_daily_loss_pct=0.5, max_open_risk_pct=2.0),
        )
        self.assertEqual(len(report.accepted_trades), 1)
        self.assertEqual(report.rejected_by_reason["DAILY_LOSS_LIMIT"], 1)
        self.assertLess(report.final_equity, report.initial_equity)

    def test_max_open_positions_is_enforced(self):
        report = simulate_portfolio(
            [path(0, delayed=True, signal_step=500), path(1, delayed=True, signal_step=500), path(2, delayed=True, signal_step=500)],
            **self.limits(max_open_positions=1, max_open_risk_pct=3.0),
        )
        self.assertEqual(len(report.accepted_trades), 1)
        self.assertEqual(report.rejected_by_reason["MAX_OPEN_POSITIONS"], 2)

    def test_rejects_unsafe_or_invalid_risk_configuration(self):
        with self.assertRaises(ValueError):
            simulate_portfolio([], **self.limits(initial_equity=0))
        with self.assertRaises(ValueError):
            simulate_portfolio([], **self.limits(risk_per_trade_pct=0))
        with self.assertRaises(ValueError):
            simulate_portfolio([], **self.limits(max_open_risk_pct=0.5))


if __name__ == "__main__":
    unittest.main()
