import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from icc_v2.execution.risk import RiskLimits, evaluate_order
from icc_v2.execution.ledger import ExecutionLedger

class RiskGateTests(unittest.TestCase):
    def setUp(self):
        self.intent = {"side":"BUY","entry":Decimal("100"),"stop_loss":Decimal("99"),"take_profit":Decimal("102"),"risk_pct":Decimal("0.25"),"unit_value":Decimal("1"),"quantity_step":Decimal("0.01"),"min_quantity":Decimal("0.01"),"max_quantity":Decimal("100")}
        self.account = {"equity":Decimal("10000"),"open_positions":0,"daily_realized_pnl":Decimal("0"),"peak_equity":Decimal("10000"),"open_risk":Decimal("0")}
        self.quote = {"bid":Decimal("99.99"),"ask":Decimal("100.01"),"received_at_ms":1000}
        self.limits = RiskLimits(enabled=True,max_spread=Decimal("0.05"))

    def test_position_size_uses_stop_distance_and_risk_budget(self):
        ok, reason, qty = evaluate_order(self.intent,self.account,self.quote,self.limits,1200)
        self.assertTrue(ok, reason)
        self.assertEqual(qty,Decimal("25.00"))

    def test_disabled_by_default(self):
        limits = RiskLimits(max_spread=Decimal("0.05"))
        self.assertEqual(evaluate_order(self.intent,self.account,self.quote,limits,1200)[1],"EXECUTION_DISABLED")

    def test_kill_switch_blocks(self):
        self.assertEqual(evaluate_order(self.intent,self.account,self.quote,self.limits,1200,True)[1],"KILL_SWITCH_ACTIVE")

    def test_stale_quote_blocks(self):
        self.assertEqual(evaluate_order(self.intent,self.account,self.quote,self.limits,4000)[1],"STALE_QUOTE")

    def test_daily_loss_blocks(self):
        self.account["daily_realized_pnl"] = Decimal("-200")
        self.assertEqual(evaluate_order(self.intent,self.account,self.quote,self.limits,1200)[1],"DAILY_LOSS_LIMIT")

    def test_wide_spread_blocks(self):
        self.quote["ask"] = Decimal("100.10")
        self.assertEqual(evaluate_order(self.intent,self.account,self.quote,self.limits,1200)[1],"SPREAD_LIMIT")

class LedgerTests(unittest.TestCase):
    def test_idempotent_and_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = ExecutionLedger(Path(d) / "ledger.sqlite")
            args = ("event-1","intent-1","SIGNAL",1000,{"symbol":"EURUSD"})
            self.assertTrue(ledger.append(*args))
            self.assertFalse(ledger.append(*args))
            self.assertEqual(len(ledger.for_intent("intent-1")),1)

if __name__ == "__main__":
    unittest.main()
