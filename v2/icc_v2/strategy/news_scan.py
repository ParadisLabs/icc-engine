"""OANDA practice-data orchestration for post-news FX shadow scans.

The scanner is opt-in and read-only. It fetches event-relevant FX pairs, measures
closed one-minute reaction first, and only then requests higher timeframes for
the existing ICC trend/sweep hypothesis. It emits research decisions, never orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..data.fx_universe import DEFAULT_FX_INSTRUMENTS, event_relevant_instruments, validate_fx_universe
from ..data.oanda_fx import OandaPracticeFx, OandaFxCandle
from .core import Bar, SetupCandidate, analyze_closed_bars
from .news_reaction import (
    NewsCandidateDecision,
    NewsEvent,
    NewsReaction,
    assess_post_release_reaction,
    confirm_news_candidate,
)


_GRANULARITY_MS = {"M1": 60_000, "M15": 900_000, "H1": 3_600_000, "D": 86_400_000}


@dataclass(frozen=True)
class NewsFxScanResult:
    instrument: str
    reaction: NewsReaction | None
    candidate: SetupCandidate | None
    decision: NewsCandidateDecision | None
    error: str | None = None


def _to_bars(candles: Sequence[OandaFxCandle], granularity: str, *, close_time: bool) -> list[Bar]:
    duration = _GRANULARITY_MS[granularity]
    return [
        Bar(
            timestamp_ms=item.timestamp_ms + (duration if close_time else 0),
            open=float(item.open), high=float(item.high), low=float(item.low), close=float(item.close),
            # OANDA price_update_count is intentionally NOT mapped to exchange volume.
            volume=None, quote_volume=None,
        )
        for item in candles if item.complete
    ]


class OandaNewsFxScanner:
    """Scan a bounded, configured OANDA practice FX universe after a release."""

    def __init__(
        self,
        adapter: OandaPracticeFx,
        *,
        instruments: Sequence[str] = DEFAULT_FX_INSTRUMENTS,
        max_instruments: int = 8,
        min_abs_move_atr: float = 0.50,
        min_range_expansion: float = 1.20,
        minimum_delay_ms: int = 3 * 60_000,
        maximum_delay_ms: int = 30 * 60_000,
    ) -> None:
        if max_instruments < 1:
            raise ValueError("max_instruments must be positive")
        self.adapter = adapter
        self.instruments = validate_fx_universe(instruments)
        self.max_instruments = max_instruments
        self.min_abs_move_atr = min_abs_move_atr
        self.min_range_expansion = min_range_expansion
        self.minimum_delay_ms = minimum_delay_ms
        self.maximum_delay_ms = maximum_delay_ms

    def scan_event(self, event: NewsEvent) -> tuple[NewsFxScanResult, ...]:
        """Return per-pair shadow results; provider failures remain visible per pair."""
        relevant = event_relevant_instruments(event.currency, self.instruments)
        results: list[NewsFxScanResult] = []
        for instrument in relevant[:self.max_instruments]:
            try:
                one_minute = self.adapter.candles(instrument, "M1", count=500)
                reaction_bars = _to_bars(one_minute, "M1", close_time=False)
                reaction = assess_post_release_reaction(
                    event, instrument, reaction_bars,
                    min_abs_move_atr=self.min_abs_move_atr,
                    min_range_expansion=self.min_range_expansion,
                )
                if not reaction.eligible:
                    results.append(NewsFxScanResult(
                        instrument, reaction, None, None,
                    ))
                    continue

                fifteen = _to_bars(self.adapter.candles(instrument, "M15", count=200), "M15", close_time=True)
                hourly = _to_bars(self.adapter.candles(instrument, "H1", count=100), "H1", close_time=True)
                daily = _to_bars(self.adapter.candles(instrument, "D", count=100), "D", close_time=True)
                candidate = analyze_closed_bars(instrument, fifteen, hourly, daily)
                if candidate is None:
                    results.append(NewsFxScanResult(
                        instrument, reaction, None, None, "NO_CONFIRMED_ICC_SETUP",
                    ))
                    continue
                decision = confirm_news_candidate(
                    event, candidate, reaction,
                    minimum_delay_ms=self.minimum_delay_ms,
                    maximum_delay_ms=self.maximum_delay_ms,
                )
                results.append(NewsFxScanResult(instrument, reaction, candidate, decision))
            except Exception as exc:
                # Keep the failure visible without leaking request headers/tokens.
                results.append(NewsFxScanResult(
                    instrument, None, None, None,
                    f"{type(exc).__name__}: {str(exc)[:180]}",
                ))
        return tuple(results)
