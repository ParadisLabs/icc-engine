"""Append-only SQLite ledger for signals, orders, fills and outcomes."""
import json
import sqlite3

class ExecutionLedger:
    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY, intent_id TEXT NOT NULL,
                event_type TEXT NOT NULL, occurred_at_ms INTEGER NOT NULL,
                payload TEXT NOT NULL)""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events BEGIN
                SELECT RAISE(ABORT, "append-only ledger"); END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events BEGIN
                SELECT RAISE(ABORT, "append-only ledger"); END""")

    def append(self, event_id, intent_id, event_type, occurred_at_ms, payload):
        if not event_id or not intent_id or not event_type or occurred_at_ms <= 0:
            raise ValueError("valid event identity and timestamp required")
        with sqlite3.connect(self.path) as db:
            cur = db.execute("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)",
                (event_id, intent_id, event_type, occurred_at_ms,
                 json.dumps(payload, sort_keys=True, separators=(",", ":"))))
            return cur.rowcount == 1

    def for_intent(self, intent_id):
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT event_id,event_type,occurred_at_ms,payload FROM events WHERE intent_id=? ORDER BY occurred_at_ms,event_id", (intent_id,)).fetchall()
        return [{"event_id": r[0], "event_type": r[1], "occurred_at_ms": r[2], "payload": json.loads(r[3])} for r in rows]
