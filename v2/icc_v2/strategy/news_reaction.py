"""Conservative post-release reaction measurements for ICC V2 shadow research.

This module measures what price did after a scheduled event. It never converts
actual-vs-forecast values into a directional prediction and never places orders.
A news candidate still needs the existing ICC multi-timeframe setup and manual
approval outside this research package.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from ..data.fx_universe import normalize_instrument
from .core import Bar, SetupCandidate


@dataclass(frozen=True)
class NewsEvent:
    event_id: str
    currency: str
    event_time_ms: int
    impact: str = "HIGH"
    title: str = ""
    actual: str | None = None
    forecast: str | None = None
    previous: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        code = self.currency.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a three-letter code")
        if self.event_time_ms <= 0:
            raise ValueError("event_time_ms must be positive")
        object.__setattr__(self, "currency", code)
        object.__setattr__(self, "impact", self.impact.strip().upper())


@dataclass(frozen=True)
class NewsReaction:
    event_id: str
    instrument: str
    direction: str
    move_atr: float
    range_expansion: float
    post_release_bars: int
    observed_through_ms: int
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class NewsCandidateDecision:
    eligible: bool
    reasons: tuple[str, ...]
    event_id: str
    instrument: str
    candidate_side: str | None
    reaction_direction: str


def assess_post_release_reaction(
    event: NewsEvent,
    instrument: str,
    bars_1m: Sequence[Bar],
    *,
    min_post_release_bars: int = 3,
    max_post_release_bars: int = 15,
    min_abs_move_atr: float = 0.50,
    min_range_expansion: float = 1.20,
) -> NewsReaction:
    """Measure the first 3–15 closed one-minute bars against a pre-event baseline.

    At least 20 pre-event bars are required to estimate the median range. Only
    bars strictly after the scheduled release are considered. This is a
    volatility/reaction gate, not a direction forecast or entry signal.
    """
    pair = normalize_instrument(instrument)
    if event.currency not in pair.split("_"):
        raise ValueError("instrument is not relevant to the event currency")
    if min_post_release_bars < 1 or max_post_release_bars < min_post_release_bars:
        raise ValueError("invalid post-release bar window")
    if min_abs_move_atr < 0 or min_range_expansion < 0:
        raise ValueError("reaction thresholds must be non-negative")

    ordered = list(bars_1m)
    timestamps = [bar.timestamp_ms for bar in ordered]
    if timestamps != sorted(set(timestamps)):
        raise ValueError("one-minute bars must be strictly chronological and unique")
    if any(bar.high < max(bar.open, bar.close, bar.low) or
           bar.low > min(bar.open, bar.close, bar.high) for bar in ordered):
        raise ValueError("invalid OHLC bar")

    minute_ms = 60_000
    # Exclude the candle containing the release from both baseline and reaction:
    # it mixes pre- and post-event prices and would bias the measured impulse.
    pre = [bar for bar in ordered if bar.timestamp_ms + minute_ms <= event.event_time_ms]
    post = [bar for bar in ordered if bar.timestamp_ms >= event.event_time_ms + minute_ms]
    reasons: list[str] = []
    if len(pre) < 20:
        reasons.append("INSUFFICIENT_PRE_EVENT_BASELINE")
    if len(post) < min_post_release_bars:
        reasons.append("WAITING_FOR_CLOSED_POST_RELEASE_BARS")

    sample = post[:max_post_release_bars]
    if len(sample) < min_post_release_bars or len(pre) < 20:
        return NewsReaction(
            event_id=event.event_id, instrument=pair, direction="FLAT",
            move_atr=0.0, range_expansion=0.0, post_release_bars=len(sample),
            observed_through_ms=sample[-1].timestamp_ms if sample else 0,
            eligible=False, reasons=tuple(reasons),
        )

    baseline_ranges = [bar.high - bar.low for bar in pre[-20:]]
    baseline_range = median(baseline_ranges)
    if baseline_range <= 0:
        reasons.append("INVALID_PRE_EVENT_RANGE_BASELINE")
        return NewsReaction(
            event.event_id, pair, "FLAT", 0.0, 0.0, len(sample),
            sample[-1].timestamp_ms, False, tuple(reasons),
        )

    first_price = pre[-1].close
    last_price = sample[-1].close
    move_atr = (last_price - first_price) / baseline_range
    post_ranges = [bar.high - bar.low for bar in sample]
    range_expansion = median(post_ranges) / baseline_range if baseline_range else 0.0
    direction = "UP" if move_atr > 0 else "DOWN" if move_atr < 0 else "FLAT"

    if abs(move_atr) < min_abs_move_atr:
        reasons.append("POST_RELEASE_MOVE_TOO_SMALL")
    if range_expansion < min_range_expansion:
        reasons.append("NO_RANGE_EXPANSION")
    eligible = not reasons
    if not eligible and not reasons:
        reasons.append("REACTION_NOT_CONFIRMED")

    return NewsReaction(
        event_id=event.event_id, instrument=pair, direction=direction,
        move_atr=move_atr, range_expansion=range_expansion,
        post_release_bars=len(sample), observed_through_ms=sample[-1].timestamp_ms,
        eligible=eligible, reasons=tuple(reasons),
    )


def confirm_news_candidate(
    event: NewsEvent,
    candidate: SetupCandidate,
    reaction: NewsReaction,
    *,
    minimum_delay_ms: int = 3 * 60_000,
    maximum_delay_ms: int = 30 * 60_000,
) -> NewsCandidateDecision:
    """Require observed post-release movement and a fresh aligned ICC setup."""
    pair = normalize_instrument(reaction.instrument)
    reasons = []
    if event.event_id != reaction.event_id:
        reasons.append("EVENT_ID_MISMATCH")
    if event.currency not in pair.split("_"):
        reasons.append("IRRELEVANT_EVENT_CURRENCY")
    if not reaction.eligible:
        reasons.extend(reaction.reasons or ("REACTION_NOT_CONFIRMED",))
    delay = candidate.signal_time_ms - event.event_time_ms
    if delay < minimum_delay_ms:
        reasons.append("TOO_EARLY_AFTER_RELEASE")
    if delay > maximum_delay_ms:
        reasons.append("POST_RELEASE_SETUP_STALE")
    expected_side = {"UP": "LONG", "DOWN": "SHORT"}.get(reaction.direction)
    if expected_side is None or candidate.side != expected_side:
        reasons.append("SETUP_NOT_ALIGNED_WITH_OBSERVED_REACTION")
    if candidate.symbol.upper().replace("/", "_") != pair:
        reasons.append("CANDIDATE_INSTRUMENT_MISMATCH")
    return NewsCandidateDecision(
        eligible=not reasons, reasons=tuple(dict.fromkeys(reasons)),
        event_id=event.event_id, instrument=pair,
        candidate_side=candidate.side, reaction_direction=reaction.direction,
    )
