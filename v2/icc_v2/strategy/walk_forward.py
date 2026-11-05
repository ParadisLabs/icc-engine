"""Chronological walk-forward evaluation for pre-generated ICC hypotheses.

This evaluates setup outcomes out of sample. It is not a portfolio simulator:
overlapping positions, capital allocation, cross-asset correlation and execution
constraints remain separate work.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .backtest import TradeOutcome, simulate_trade, summarize_outcomes
from .core import Bar, SetupCandidate


@dataclass(frozen=True)
class CandidatePath:
    candidate: SetupCandidate
    future_bars: tuple[Bar, ...]


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    training_candidates: int
    training_closed_trades: int
    test_candidates: int
    test_outcomes: tuple[TradeOutcome, ...]
    training_metrics: dict[str, float | int]
    test_metrics: dict[str, float | int]
    test_start_ms: int
    test_end_ms: int


def evaluate_walk_forward(
    paths: Sequence[CandidatePath],
    *,
    train_candidates: int = 50,
    test_candidates: int = 20,
    step_candidates: int | None = None,
    min_training_trades: int = 10,
    max_holding_bars: int = 96,
    fee_bps_per_side: float = 4.0,
    slippage_bps_per_side: float = 2.0,
) -> tuple[WalkForwardFold, ...]:
    """Evaluate successive chronological test blocks against prior closed history.

    Training outcomes are admitted only when their simulated exit precedes the
    first test signal, preventing outcomes from the test period leaking into the
    training summary. Folds expand their training history by default.
    """
    if train_candidates < 1 or test_candidates < 1:
        raise ValueError("training and test window sizes must be positive")
    step = test_candidates if step_candidates is None else step_candidates
    if step < 1 or min_training_trades < 0:
        raise ValueError("step must be positive and min_training_trades non-negative")
    ordered = sorted(paths, key=lambda item: item.candidate.signal_time_ms)
    if len(ordered) < train_candidates + test_candidates:
        return ()

    folds: list[WalkForwardFold] = []
    fold_number = 0
    test_start_index = train_candidates
    while test_start_index + test_candidates <= len(ordered):
        training = ordered[:test_start_index]
        testing = ordered[test_start_index:test_start_index + test_candidates]
        test_start_ms = testing[0].candidate.signal_time_ms
        test_end_ms = testing[-1].candidate.signal_time_ms

        training_outcomes: list[TradeOutcome] = []
        for item in training:
            outcome = simulate_trade(
                item.candidate, item.future_bars,
                max_holding_bars=max_holding_bars,
                fee_bps_per_side=fee_bps_per_side,
                slippage_bps_per_side=slippage_bps_per_side,
            )
            if outcome is not None and outcome.exit_time_ms < test_start_ms:
                training_outcomes.append(outcome)

        if len(training_outcomes) >= min_training_trades:
            test_outcomes = []
            for item in testing:
                outcome = simulate_trade(
                    item.candidate, item.future_bars,
                    max_holding_bars=max_holding_bars,
                    fee_bps_per_side=fee_bps_per_side,
                    slippage_bps_per_side=slippage_bps_per_side,
                )
                if outcome is not None:
                    test_outcomes.append(outcome)
            fold_number += 1
            folds.append(WalkForwardFold(
                fold=fold_number,
                training_candidates=len(training),
                training_closed_trades=len(training_outcomes),
                test_candidates=len(testing),
                test_outcomes=tuple(test_outcomes),
                training_metrics=summarize_outcomes(training_outcomes),
                test_metrics=summarize_outcomes(test_outcomes),
                test_start_ms=test_start_ms,
                test_end_ms=test_end_ms,
            ))
        test_start_index += step
    return tuple(folds)
