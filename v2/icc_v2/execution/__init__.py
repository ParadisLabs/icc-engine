"""ICC V2 broker execution boundary.

The cTrader integration is intentionally demo-only and read-only until
account identity, symbol metadata and risk-gate wiring are verified.
"""
from .ctrader import (
    CTraderConfigurationError,
    CTraderDemoAdapter,
    CTraderDemoConfig,
    CTraderExecutionDisabled,
)
from .ledger import ExecutionLedger
from .risk import RiskLimits, evaluate_order

__all__ = [
    "CTraderConfigurationError",
    "CTraderDemoAdapter",
    "CTraderDemoConfig",
    "CTraderExecutionDisabled",
    "ExecutionLedger",
    "RiskLimits",
    "evaluate_order",
]
