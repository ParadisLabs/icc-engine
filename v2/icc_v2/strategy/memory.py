"""Durable, append-oriented ICC V2 setup memory.

Stores research hypotheses and their finalized outcomes. It does not modify strategy
weights or create trade instructions; adaptive learning is a separate evaluation step.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

from .core import SetupCandidate


@dataclass(frozen=True)
class MemoryStats:
    symbol: str
    side: str
    timeframe: str
    closed_setups: int
    wins: int
    losses: int
    win_rate_pct: float
    expectancy_r: float


class SetupMemoryStore:
    """SQLite-backed setup/outcome ledger with idempotent writes."""

    def __init__(self, path: str | Path = "data/icc_v2_memory.sqlite3") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, timeout=10.0, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode = WAL")
            self._db.execute("PRAGMA synchronous = FULL")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._db:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS setup_memory (
                    event_id TEXT PRIMARY KEY,
                    venue TEXT NOT NULL,
                    market_type TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT')),
                    signal_time_ms INTEGER NOT NULL,
                    reference_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    risk_per_unit REAL NOT NULL,
                    score REAL NOT NULL,
                    features_json TEXT NOT NULL,
                    outcome_r REAL,
                    outcome_status TEXT NOT NULL DEFAULT 'OPEN'
                        CHECK (outcome_status IN ('OPEN', 'CLOSED')),
                    created_at_ms INTEGER NOT NULL,
                    closed_at_ms INTEGER
                )
            """)
            self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_setup_memory_lookup
                ON setup_memory(symbol, side, timeframe, signal_time_ms)
            """)

    @staticmethod
    def _event_id(venue: str, market_type: str, candidate: SetupCandidate) -> str:
        raw = "|".join((
            venue.lower(), market_type.lower(), candidate.symbol.upper(),
            candidate.side.upper(), str(candidate.signal_time_ms),
        ))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def record_setup(
        self,
        candidate: SetupCandidate,
        *,
        venue: str,
        market_type: str,
        timeframe: str = "15m",
        created_at_ms: int | None = None,
    ) -> tuple[str, bool]:
        """Insert once; repeated delivery of the same setup is idempotent."""
        if not venue.strip() or not market_type.strip() or not timeframe.strip():
            raise ValueError("venue, market_type and timeframe are required")
        if candidate.side not in {"LONG", "SHORT"}:
            raise ValueError("candidate side must be LONG or SHORT")
        numbers = (
            candidate.reference_price, candidate.stop_loss, candidate.take_profit,
            candidate.risk_per_unit, candidate.score,
        )
        if not all(math.isfinite(float(value)) for value in numbers):
            raise ValueError("candidate numeric fields must be finite")
        features_json = json.dumps(candidate.features, sort_keys=True, separators=(",", ":"), allow_nan=False)
        event_id = self._event_id(venue, market_type, candidate)
        now = int(created_at_ms if created_at_ms is not None else time.time() * 1000)
        with self._lock, self._db:
            cursor = self._db.execute("""
                INSERT OR IGNORE INTO setup_memory (
                    event_id, venue, market_type, symbol, timeframe, side,
                    signal_time_ms, reference_price, stop_loss, take_profit,
                    risk_per_unit, score, features_json, created_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id, venue.lower(), market_type.lower(), candidate.symbol.upper(),
                timeframe, candidate.side, int(candidate.signal_time_ms),
                float(candidate.reference_price), float(candidate.stop_loss),
                float(candidate.take_profit), float(candidate.risk_per_unit),
                float(candidate.score), features_json, now,
            ))
            return event_id, cursor.rowcount == 1

    def record_outcome(self, event_id: str, outcome_r: float, *, closed_at_ms: int | None = None) -> bool:
        """Finalize an open setup once; conflicting rewrites are rejected."""
        outcome = float(outcome_r)
        if not math.isfinite(outcome):
            raise ValueError("outcome_r must be finite")
        closed = int(closed_at_ms if closed_at_ms is not None else time.time() * 1000)
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT outcome_r, outcome_status FROM setup_memory WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown setup event_id: {event_id}")
            if row["outcome_status"] == "CLOSED":
                if float(row["outcome_r"]) == outcome:
                    return False
                raise ValueError("finalized setup outcomes are immutable")
            self._db.execute("""
                UPDATE setup_memory
                SET outcome_r = ?, outcome_status = 'CLOSED', closed_at_ms = ?
                WHERE event_id = ? AND outcome_status = 'OPEN'
            """, (outcome, closed, event_id))
            return True

    def stats(self, *, min_samples: int = 1) -> list[MemoryStats]:
        if min_samples < 1:
            raise ValueError("min_samples must be positive")
        with self._lock:
            rows = self._db.execute("""
                SELECT symbol, side, timeframe, COUNT(*) AS n,
                       SUM(CASE WHEN outcome_r > 0 THEN 1 ELSE 0 END) AS wins,
                       SUM(CASE WHEN outcome_r < 0 THEN 1 ELSE 0 END) AS losses,
                       AVG(outcome_r) AS expectancy
                FROM setup_memory
                WHERE outcome_status = 'CLOSED'
                GROUP BY symbol, side, timeframe
                HAVING COUNT(*) >= ?
                ORDER BY expectancy DESC, n DESC
            """, (min_samples,)).fetchall()
        return [
            MemoryStats(
                symbol=row["symbol"], side=row["side"], timeframe=row["timeframe"],
                closed_setups=int(row["n"]), wins=int(row["wins"]), losses=int(row["losses"]),
                win_rate_pct=float(row["wins"]) / int(row["n"]) * 100.0,
                expectancy_r=float(row["expectancy"]),
            )
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "SetupMemoryStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
