from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import SQLiteDatabase
from models.rewards import REDEMPTION_CANCELLED, REDEMPTION_FULFILLED, REDEMPTION_REDEEMED, REWARD_ACTIVE


class RewardRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self.ensure_schema()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.database.transaction() as conn:
            yield conn

    def ensure_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reward_items (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  child_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  description TEXT,
                  points_cost INTEGER NOT NULL,
                  category TEXT,
                  status TEXT NOT NULL,
                  icon TEXT,
                  created_by TEXT,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reward_redemptions (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  child_id TEXT NOT NULL,
                  reward_item_id TEXT NOT NULL,
                  reward_title TEXT NOT NULL,
                  points_cost INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  requested_by TEXT NOT NULL,
                  fulfilled_by TEXT,
                  cancelled_by TEXT,
                  requested_at INTEGER NOT NULL,
                  fulfilled_at INTEGER,
                  cancelled_at INTEGER
                );
                """
            )

    def child_exists(self, conn: sqlite3.Connection, *, family_id: str, child_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def create_item(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        child_id: str,
        title: str,
        description: str | None,
        points_cost: int,
        category: str | None,
        icon: str | None,
        created_by: str | None,
        now: int,
    ) -> sqlite3.Row:
        item_id = f"reward_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO reward_items(
              id, family_id, child_id, title, description, points_cost,
              category, status, icon, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                family_id,
                child_id,
                title,
                description,
                points_cost,
                category,
                REWARD_ACTIVE,
                icon,
                created_by,
                now,
                now,
            ),
        )
        return self.get_item(conn, family_id=family_id, item_id=item_id)

    def list_items(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        child_id: str | None = None,
        status: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["family_id = ?"]
        values: list[str] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        return list(
            conn.execute(
                f"""
                SELECT * FROM reward_items
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                """,
                values,
            ).fetchall()
        )

    def get_item(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        item_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM reward_items WHERE family_id = ? AND id = ?",
            (family_id, item_id),
        ).fetchone()

    def update_item(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        item_id: str,
        fields: dict,
        now: int,
    ) -> sqlite3.Row | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, family_id, item_id]
            conn.execute(
                f"""
                UPDATE reward_items
                SET {', '.join(assignments)}, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                values,
            )
        return self.get_item(conn, family_id=family_id, item_id=item_id)

    def create_redemption(
        self,
        conn: sqlite3.Connection,
        *,
        redemption_id: str,
        family_id: str,
        child_id: str,
        reward_item_id: str,
        reward_title: str,
        points_cost: int,
        requested_by: str,
        now: int,
    ) -> sqlite3.Row:
        conn.execute(
            """
            INSERT INTO reward_redemptions(
              id, family_id, child_id, reward_item_id, reward_title, points_cost,
              status, requested_by, requested_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                redemption_id,
                family_id,
                child_id,
                reward_item_id,
                reward_title,
                points_cost,
                REDEMPTION_REDEEMED,
                requested_by,
                now,
            ),
        )
        return self.get_redemption(conn, family_id=family_id, redemption_id=redemption_id)

    def list_redemptions(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        child_id: str | None = None,
        status: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["family_id = ?"]
        values: list[str] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        return list(
            conn.execute(
                f"""
                SELECT * FROM reward_redemptions
                WHERE {' AND '.join(clauses)}
                ORDER BY requested_at DESC
                """,
                values,
            ).fetchall()
        )

    def get_redemption(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        redemption_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM reward_redemptions WHERE family_id = ? AND id = ?",
            (family_id, redemption_id),
        ).fetchone()

    def fulfill_redemption(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        redemption_id: str,
        fulfilled_by: str,
        now: int,
    ) -> sqlite3.Row | None:
        conn.execute(
            """
            UPDATE reward_redemptions
            SET status = ?, fulfilled_by = ?, fulfilled_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (REDEMPTION_FULFILLED, fulfilled_by, now, family_id, redemption_id),
        )
        return self.get_redemption(conn, family_id=family_id, redemption_id=redemption_id)

    def cancel_redemption(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        redemption_id: str,
        cancelled_by: str,
        now: int,
    ) -> sqlite3.Row | None:
        conn.execute(
            """
            UPDATE reward_redemptions
            SET status = ?, cancelled_by = ?, cancelled_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (REDEMPTION_CANCELLED, cancelled_by, now, family_id, redemption_id),
        )
        return self.get_redemption(conn, family_id=family_id, redemption_id=redemption_id)
