"""CLI entry point for a read-only ICC V2 post-news shadow scan."""
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from decimal import Decimal

from icc_v2.data.oanda_fx import OandaPracticeFx
from icc_v2.strategy.news_reaction import NewsEvent
from icc_v2.strategy.news_scan import OandaNewsFxScanner

def plain(value):
    if is_dataclass(value): return plain(asdict(value))
    if isinstance(value, dict): return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [plain(v) for v in value]
    if isinstance(value, Decimal): return str(value)
    return value

def main():
    raw = os.environ.get("ICC_NEWS_EVENT_JSON", "")
    token = os.environ.get("OANDA_PRACTICE_TOKEN", "")
    if not raw: raise SystemExit("ICC_NEWS_EVENT_JSON is required")
    if not token: raise SystemExit("OANDA_PRACTICE_TOKEN is required for the read-only practice data adapter")
    payload = json.loads(raw)
    allowed = {"event_id", "currency", "event_time_ms", "impact", "title", "actual", "forecast", "previous"}
    event_payload = {key: value for key, value in payload.items() if key in allowed}
    event = NewsEvent(**event_payload)
    scanner = OandaNewsFxScanner(OandaPracticeFx(token))
    results = scanner.scan_event(event)
    print(json.dumps({"mode":"shadow_only","event":plain(event),"results":plain(results)},sort_keys=True))
    if not results: raise SystemExit("No event-relevant instruments configured; refusing silent success")

if __name__ == "__main__":
    main()
