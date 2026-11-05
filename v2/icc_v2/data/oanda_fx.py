"""Read-only OANDA practice FX candle adapter.

OANDA candle volume is the number of prices created in the candle, not centralized
exchange-traded volume. This adapter exposes it only as price_update_count /
broker_price_update_count. It never accesses accounts, orders, positions or live endpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PRACTICE_URL = "https://api-fxpractice.oanda.com"
_ALLOWED_GRANULARITIES = {
    "S5", "S10", "S15", "S30", "M1", "M2", "M4", "M5", "M10", "M15",
    "M30", "H1", "H2", "H3", "H4", "H6", "H8", "H12", "D", "W", "M",
}


class OandaFxError(RuntimeError):
    pass


class OandaFxAuthenticationError(OandaFxError):
    pass


@dataclass(frozen=True)
class OandaFxCandle:
    provider: str
    venue: str
    market_type: str
    instrument: str
    granularity: str
    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    price_update_count: int
    volume_kind: str
    price_component: str
    complete: bool


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise OandaFxError(f"Invalid decimal in {field}") from exc
    if not number.is_finite():
        raise OandaFxError(f"Non-finite decimal in {field}")
    return number


def _timestamp_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise OandaFxError("Invalid OANDA candle timestamp") from exc
    if parsed.tzinfo is None:
        raise OandaFxError("OANDA candle timestamp must include a timezone")
    return int(parsed.timestamp() * 1000)


class OandaPracticeFx:
    """Fetch FX candles from OANDA's practice environment using public market data."""

    venue = "oanda"
    market_type = "forex_spot"
    volume_kind = "broker_price_update_count"

    def __init__(
        self,
        token: str,
        *,
        base_url: str = PRACTICE_URL,
        timeout: float = 10.0,
        retries: int = 2,
        urlopen_fn: Callable[..., Any] = urlopen,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token or not token.strip():
            raise ValueError("OANDA practice API token is required")
        if base_url.rstrip("/") != PRACTICE_URL:
            raise ValueError("Only the OANDA practice endpoint is allowed by this adapter")
        self._token = token.strip()
        self.base_url = PRACTICE_URL
        self.timeout = timeout
        self.retries = max(0, retries)
        self.urlopen_fn = urlopen_fn
        self.sleep_fn = sleep_fn

    @staticmethod
    def _instrument(value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]+_[A-Z0-9]+", normalized):
            raise ValueError("OANDA instrument must use BASE_QUOTE format, e.g. EUR_USD")
        return normalized

    def _get(self, instrument: str, params: dict[str, Any]) -> Any:
        query = urlencode(params)
        url = f"{self.base_url}/v3/instruments/{instrument}/candles?{query}"
        request = Request(url, headers={
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "ICC-V2-read-only-FX/0.1",
        }, method="GET")
        for attempt in range(self.retries + 1):
            try:
                with self.urlopen_fn(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict) or not isinstance(payload.get("candles"), list):
                    raise OandaFxError("Unexpected OANDA candles response")
                return payload
            except HTTPError as exc:
                if exc.code == 401:
                    raise OandaFxAuthenticationError("OANDA practice token was rejected") from exc
                if exc.code == 429 or exc.code >= 500:
                    if attempt >= self.retries:
                        raise OandaFxError(f"OANDA practice request failed with HTTP {exc.code}") from exc
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    delay = float(retry_after) if retry_after else min(2 ** attempt, 8)
                    self.sleep_fn(max(0.0, min(delay, 30.0)))
                    continue
                raise OandaFxError(f"OANDA practice request failed with HTTP {exc.code}") from exc
            except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                if attempt >= self.retries:
                    raise OandaFxError("OANDA practice market-data request failed") from exc
                self.sleep_fn(min(2 ** attempt, 8))
        raise OandaFxError("OANDA practice retries exhausted")

    def candles(
        self,
        instrument: str,
        granularity: str = "M15",
        *,
        count: int = 500,
        price_component: str = "M",
        complete_only: bool = True,
    ) -> list[OandaFxCandle]:
        """Return FX spot candles; price_update_count is not traded volume."""
        normalized = self._instrument(instrument)
        if granularity not in _ALLOWED_GRANULARITIES:
            raise ValueError(f"Unsupported OANDA granularity: {granularity}")
        if not 1 <= count <= 5000:
            raise ValueError("count must be between 1 and 5000")
        if price_component not in {"M", "B", "A"}:
            raise ValueError("price_component must be M, B or A")
        payload = self._get(normalized, {
            "granularity": granularity, "count": count, "price": price_component,
        })
        candles = []
        for row in payload["candles"]:
            if not isinstance(row, dict):
                raise OandaFxError("Malformed OANDA candle row")
            complete = bool(row.get("complete", False))
            if complete_only and not complete:
                continue
            component = row.get({"M": "mid", "B": "bid", "A": "ask"}[price_component])
            if not isinstance(component, dict):
                raise OandaFxError("Requested OANDA price component is missing")
            try:
                price_count = int(row["volume"])
            except (KeyError, TypeError, ValueError) as exc:
                raise OandaFxError("OANDA candle price count is missing or invalid") from exc
            if price_count < 0:
                raise OandaFxError("OANDA candle price count cannot be negative")
            candles.append(OandaFxCandle(
                provider="oanda", venue="oanda", market_type="forex_spot",
                instrument=normalized, granularity=granularity,
                timestamp_ms=_timestamp_ms(row["time"]),
                open=_decimal(component["o"], "open"),
                high=_decimal(component["h"], "high"),
                low=_decimal(component["l"], "low"),
                close=_decimal(component["c"], "close"),
                price_update_count=price_count,
                volume_kind=self.volume_kind,
                price_component=price_component,
                complete=complete,
            ))
        return candles
