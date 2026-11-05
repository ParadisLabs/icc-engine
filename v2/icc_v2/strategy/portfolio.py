"""Event-driven portfolio simulation with explicit concurrent-risk limits.

Trade paths are simulated with the conservative OHLC engine, then admitted in
entry-time order. This models capital/risk concurrency, not venue margin,
funding, market impact or cross-asset correlation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .backtest import TradeOutcome, simulate_trade
from .core import Bar, SetupCandidate
from .walk_forward import CandidatePath


@dataclass(frozen=True)
class PortfolioTrade:
    outcome: TradeOutcome
    risk_amount: float
    pnl: float
    equity_after_exit: float


@dataclass(frozen=True)
class PortfolioReport:
    initial_equity: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    accepted_trades: tuple[PortfolioTrade, ...]
    rejected_by_reason: dict[str, int]


def simulate_portfolio(
    paths: Sequence[CandidatePath],
    *,
    initial_equity: float,
    risk_per_trade_pct: float,
    max_open_risk_pct: float,
    max_open_positions: int,
    max_daily_loss_pct: float,
    max_total_drawdown_pct: float,
    max_holding_bars: int = 96,
    fee_bps_per_side: float = 4.0,
    slippage_bps_per_side: float = 2.0,
) -> PortfolioReport:
    """Simulate a multi-symbol portfolio with chronological risk admission.

    Daily loss is measured against realized PnL and the equity at the first
    realized close of each UTC day. Open positions reserve their original
    monetary risk. A trade that gaps through its stop can lose more than 1R.
    """
    values = (
        initial_equity, risk_per_trade_pct, max_open_risk_pct,
        max_daily_loss_pct, max_total_drawdown_pct,
    )
    if any(not isinstance(value, (int, float)) for value in values):
        raise ValueError("equity and risk limits must be numeric")
    if initial_equity <= 0:
        raise ValueError("initial_equity must be positive")
    if not 0 < risk_per_trade_pct <= 100:
        raise ValueError("risk_per_trade_pct must be in (0, 100]")
    if not risk_per_trade_pct <= max_open_risk_pct <= 100:
        raise ValueError("max_open_risk_pct must be at least per-trade risk and at most 100")
    if max_open_positions < 1:
        raise ValueError("max_open_positions must be positive")
    if not 0 < max_daily_loss_pct <= 100 or not 0 < max_total_drawdown_pct <= 100:
        raise ValueError("loss and drawdown limits must be in (0, 100]")

    simulated = []
    for item in paths:
        outcome = simulate_trade(
            item.candidate, item.future_bars,
            max_holding_bars=max_holding_bars,
            fee_bps_per_side=fee_bps_per_side,
            slippage_bps_per_side=slippage_bps_per_side,
        )
        if outcome is not None:
            simulated.append(outcome)
    simulated.sort(key=lambda item: (item.entry_time_ms, item.signal_time_ms, item.symbol))

    equity = float(initial_equity)
    peak = equity
    max_drawdown = 0.0
    active: list[PortfolioTrade] = []
    accepted: list[PortfolioTrade] = []
    closed_trades: list[PortfolioTrade] = []
    rejected: dict[str, int] = {}
    daily_start_equity: dict[int, float] = {}
    daily_realized_pnl: dict[int, float] = {}

    def close_until(timestamp_ms: int) -> None:
        nonlocal equity, peak, max_drawdown, active
        closing = sorted(
            (item for item in active if item.outcome.exit_time_ms <= timestamp_ms),
            key=lambda item: (item.outcome.exit_time_ms, item.outcome.symbol),
        )
        for trade in closing:
            day = trade.outcome.exit_time_ms // 86_400_000
            daily_start_equity.setdefault(day, equity)
            equity += trade.pnl
            daily_realized_pnl[day] = daily_realized_pnl.get(day, 0.0) + trade.pnl
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)
            active.remove(trade)
            closed_trades.append(PortfolioTrade(
                outcome=trade.outcome, risk_amount=trade.risk_amount,
                pnl=trade.pnl, equity_after_exit=equity,
            ))

    for outcome in simulated:
        close_until(outcome.entry_time_ms)
        day = outcome.entry_time_ms // 86_400_000
        daily_start = daily_start_equity.get(day, equity)
        daily_pnl = daily_realized_pnl.get(day, 0.0)
        if daily_pnl <= -(daily_start * max_daily_loss_pct / 100.0):
            rejected["DAILY_LOSS_LIMIT"] = rejected.get("DAILY_LOSS_LIMIT", 0) + 1
            continue
        if peak > 0 and (peak - equity) / peak * 100.0 >= max_total_drawdown_pct:
            rejected["MAX_DRAWDOWN_LIMIT"] = rejected.get("MAX_DRAWDOWN_LIMIT", 0) + 1
            continue
        if len(active) >= max_open_positions:
            rejected["MAX_OPEN_POSITIONS"] = rejected.get("MAX_OPEN_POSITIONS", 0) + 1
            continue
        risk_amount = equity * risk_per_trade_pct / 100.0
        open_risk_amount = sum(item.risk_amount for item in active)
        if (open_risk_amount + risk_amount) > equity * max_open_risk_pct / 100.0 + 1e-12:
            rejected["MAX_OPEN_RISK"] = rejected.get("MAX_OPEN_RISK", 0) + 1
            continue
        trade = PortfolioTrade(
            outcome=outcome, risk_amount=risk_amount,
            pnl=risk_amount * outcome.net_r, equity_after_exit=0.0,
        )
        accepted.append(trade)
        active.append(trade)

    close_until(float("inf"))
    total_return = (equity - initial_equity) / initial_equity * 100.0
    return PortfolioReport(
        initial_equity=float(initial_equity), final_equity=equity,
        total_return_pct=total_return, max_drawdown_pct=max_drawdown,
        accepted_trades=tuple(sorted(closed_trades, key=lambda item: (item.outcome.entry_time_ms, item.outcome.symbol))), rejected_by_reason=rejected,
    )
