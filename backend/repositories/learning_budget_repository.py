"""Durable budget mutations share one DB lock, including separate workers."""
from __future__ import annotations

from contextlib import contextmanager
import json

from content.learning_budget_policy import canonical


class LearningBudgetRepository:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def locked(self):
        with self.database.transaction() as conn:
            # UPDATE takes an InnoDB exclusive row lock until commit/rollback.
            # Do not replace with a process-local lock or unlocked read/check/write.
            cursor = conn.execute("UPDATE learning_budget_control SET revision = revision + 1 WHERE id = 1")
            if cursor.rowcount != 1:
                raise RuntimeError("budget migration is not installed")
            yield conn

    def control(self, conn):
        return conn.execute("SELECT * FROM learning_budget_control WHERE id = 1").fetchone()

    def halt(self, conn, reason):
        conn.execute("UPDATE learning_budget_control SET halted = 1, reason_code = ? WHERE id = 1", (reason,))

    def authorization(self, conn, identity):
        return conn.execute("SELECT * FROM learning_budget_authorizations WHERE id = ?", (identity,)).fetchone()

    # price_keys_json holds {keys, prices}: frozen full versioned price profiles.
    def insert_authorization(self, conn, identity, scope, maximum, prices, policy, expires, now):
        conn.execute("""INSERT INTO learning_budget_authorizations
            (id, scope_json, limits_json, price_keys_json, policy_sha256, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (identity, canonical(scope), canonical(maximum), canonical(prices), policy, expires, now))

    def reservation(self, conn, identity):
        return conn.execute("SELECT * FROM learning_budget_reservations WHERE id = ?", (identity,)).fetchone()

    def insert_reservation(self, conn, values):
        columns = ("id", "authorization_id", "dispatch_id", "request_sha256", "request_identity_sha256",
                   "purpose", "user_key", "course_key", "policy_sha256", "price_json", "max_units_json",
                   "state", "created_at", "charge_at")
        conn.execute(f"INSERT INTO learning_budget_reservations ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                     tuple(values[k] for k in columns))

    def ledger(self, conn, *, since, authorization_id, course_key):
        return conn.execute("""SELECT * FROM learning_budget_reservations
            WHERE state IN ('reserved', 'dispatched', 'unknown') OR charge_at >= ?
              OR authorization_id = ? OR course_key = ?""", (since, authorization_id, course_key)).fetchall()

    def open_authorizations(self, conn, now):
        return conn.execute("SELECT * FROM learning_budget_authorizations WHERE revoked_at IS NULL AND expires_at > ?", (now,)).fetchall()

    def authorization_ledger(self, conn, identity):
        return conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id = ? AND state <> 'released'", (identity,)).fetchall()

    def event(self, conn, identity, kind, evidence, now):
        conn.execute("""INSERT INTO learning_budget_events
            (reservation_id, event_type, evidence_json, created_at) VALUES (?, ?, ?, ?)""",
            (identity, kind, canonical(evidence), now))

    def status(self, conn):
        rows = conn.execute("SELECT state, COUNT(*) AS count FROM learning_budget_reservations GROUP BY state").fetchall()
        return {row["state"]: int(row["count"]) for row in rows}
