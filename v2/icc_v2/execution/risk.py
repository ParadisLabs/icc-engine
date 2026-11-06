"""Fail-closed risk checks for a future ICC demo adapter."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

@dataclass(frozen=True)
class RiskLimits:
    enabled: bool = False
    max_risk_pct: Decimal = Decimal("0.25")
    max_open_risk_pct: Decimal = Decimal("0.75")
    max_daily_loss_pct: Decimal = Decimal("2.0")
    max_drawdown_pct: Decimal = Decimal("5.0")
    max_positions: int = 2
    max_spread: Decimal = Decimal("0")
    max_quote_age_ms: int = 2000

def evaluate_order(intent, account, quote, limits, now_ms, kill_switch=False):
    """Return (approved, reason, quantity); never communicates with a broker."""
    reject = lambda reason: (False, reason, Decimal("0"))
    if not limits.enabled: return reject("EXECUTION_DISABLED")
    if kill_switch: return reject("KILL_SWITCH_ACTIVE")
    if account["equity"] <= 0: return reject("INVALID_EQUITY")
    if quote["bid"] <= 0 or quote["ask"] < quote["bid"]: return reject("INVALID_QUOTE")
    if now_ms < quote["received_at_ms"] or now_ms - quote["received_at_ms"] > limits.max_quote_age_ms: return reject("STALE_QUOTE")
    spread = quote["ask"] - quote["bid"]
    if limits.max_spread <= 0 or spread > limits.max_spread: return reject("SPREAD_LIMIT")
    if account["open_positions"] >= limits.max_positions: return reject("MAX_POSITIONS")
    equity = account["equity"]
    if account["daily_realized_pnl"] <= -(equity * limits.max_daily_loss_pct / 100): return reject("DAILY_LOSS_LIMIT")
    if equity <= account["peak_equity"] * (1 - limits.max_drawdown_pct / 100): return reject("MAX_DRAWDOWN_LIMIT")
    risk_pct = intent["risk_pct"]
    if risk_pct <= 0 or risk_pct > limits.max_risk_pct: return reject("RISK_PER_TRADE_LIMIT")
    entry, stop, target = intent["entry"], intent["stop_loss"], intent["take_profit"]
    if intent["side"] == "BUY" and not stop < entry < target: return reject("INVALID_LONG_PROTECTION")
    if intent["side"] == "SELL" and not target < entry < stop: return reject("INVALID_SHORT_PROTECTION")
    if intent["side"] not in ("BUY", "SELL"): return reject("INVALID_SIDE")
    unit_value, step = intent["unit_value"], intent["quantity_step"]
    if unit_value <= 0 or step <= 0: return reject("INVALID_INSTRUMENT_METADATA")
    risk_amount = equity * risk_pct / 100
    if account["open_risk"] + risk_amount > equity * limits.max_open_risk_pct / 100: return reject("MAX_OPEN_RISK")
    raw = risk_amount / (abs(entry - stop) * unit_value)
    quantity = (raw / step).to_integral_value(rounding=ROUND_DOWN) * step
    if quantity < intent["min_quantity"] or quantity > intent["max_quantity"]: return reject("QUANTITY_OUT_OF_BOUNDS")
    return True, "APPROVED_FOR_DEMO_ADAPTER", quantity
