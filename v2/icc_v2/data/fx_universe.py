"""Configured OANDA FX universe and event-currency relevance helpers.

OANDA instrument availability is account/region dependent. This module does not
call account endpoints or assume every listed pair is enabled: callers may pass
an explicit supported-instrument allowlist from their own configuration. The
default list is a research shortlist, not a guarantee of broker availability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Common OANDA FX spot instruments. Confirm availability in the user's practice
# environment before enabling a symbol; unsupported instruments fail per-symbol.
DEFAULT_FX_INSTRUMENTS = (
    "EUR_USD", "GBP_USD", "USD_JPY", "USD_CHF", "USD_CAD", "AUD_USD", "NZD_USD",
    "EUR_GBP", "EUR_JPY", "EUR_CHF", "EUR_CAD", "EUR_AUD", "EUR_NZD",
    "GBP_JPY", "GBP_CHF", "GBP_CAD", "GBP_AUD", "GBP_NZD",
    "AUD_JPY", "AUD_CHF", "AUD_CAD", "AUD_NZD",
    "NZD_JPY", "NZD_CHF", "NZD_CAD", "CAD_JPY", "CAD_CHF", "CHF_JPY",
)


@dataclass(frozen=True)
class FxInstrument:
    instrument: str
    base_currency: str
    quote_currency: str


def normalize_instrument(value: str) -> str:
    normalized = value.strip().upper()
    parts = normalized.split("_")
    if len(parts) != 2 or any(len(part) != 3 or not part.isalpha() for part in parts):
        raise ValueError("FX instrument must use BASE_QUOTE format, e.g. EUR_USD")
    if parts[0] == parts[1]:
        raise ValueError("base and quote currencies must differ")
    return normalized


def parse_instrument(value: str) -> FxInstrument:
    normalized = normalize_instrument(value)
    base, quote = normalized.split("_")
    return FxInstrument(normalized, base, quote)


def event_relevant_instruments(
    currency: str,
    instruments: Iterable[str] = DEFAULT_FX_INSTRUMENTS,
) -> tuple[str, ...]:
    """Return configured FX pairs containing the event currency, without bias.

    Currency relevance selects what to inspect; it does not imply a buy/sell
    direction. Pair orientation is retained exactly as supplied.
    """
    code = currency.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("event currency must be a three-letter currency code")
    selected = []
    seen = set()
    for raw in instruments:
        instrument = parse_instrument(raw).instrument
        base, quote = instrument.split("_")
        if code in {base, quote} and instrument not in seen:
            selected.append(instrument)
            seen.add(instrument)
    return tuple(selected)


def validate_fx_universe(instruments: Iterable[str]) -> tuple[str, ...]:
    """Normalize, de-duplicate and validate an explicit provider allowlist."""
    result = []
    seen = set()
    for raw in instruments:
        instrument = parse_instrument(raw).instrument
        if instrument not in seen:
            result.append(instrument)
            seen.add(instrument)
    if not result:
        raise ValueError("FX universe cannot be empty")
    return tuple(result)
