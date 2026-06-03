from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow
from models.rewards import REDEMPTION_CANCELLED, REDEMPTION_FULFILLED, REDEMPTION_REDEEMED, REWARD_ACTIVE


class RewardRepository:
    def __init__(self, database: Database):
        self.database = database
        self.ensure_schema()

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def ensure_schema(self) -> None:
        if not self.database.allow_runtime_schema_creation:
            return
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS reward_items (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  child_id VARCHAR(255) NOT NULL,
                  title VARCHAR(255) NOT NULL,
                  description TEXT,
                  points_cost INTEGER NOT NULL,
                  category VARCHAR(255),
                  status VARCHAR(255) NOT NULL,
                  icon VARCHAR(255),
                  created_by VARCHAR(255),
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reward_redemptions (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  child_id VARCHAR(255) NOT NULL,
                  reward_item_id VARCHAR(255) NOT NULL,
                  reward_title VARCHAR(255) NOT NULL,
                  points_cost INTEGER NOT NULL,
                  status VARCHAR(255) NOT NULL,
                  requested_by VARCHAR(255) NOT NULL,
                  fulfilled_by VARCHAR(255),
                  cancelled_by VARCHAR(255),
                  requested_at BIGINT NOT NULL,
                  fulfilled_at BIGINT,
                  cancelled_at BIGINT
                );
                """
            )

    def child_exists(self, conn: DatabaseConnection, *, family_id: str, child_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def create_item(
        self,
        conn: DatabaseConnection,
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
    ) -> DatabaseRow:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        status: str | None = None,
    ) -> list[DatabaseRow]:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        item_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM reward_items WHERE family_id = ? AND id = ?",
            (family_id, item_id),
        ).fetchone()

    def update_item(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        item_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
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
        conn: DatabaseConnection,
        *,
        redemption_id: str,
        family_id: str,
        child_id: str,
        reward_item_id: str,
        reward_title: str,
        points_cost: int,
        requested_by: str,
        now: int,
    ) -> DatabaseRow:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        status: str | None = None,
    ) -> list[DatabaseRow]:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        redemption_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM reward_redemptions WHERE family_id = ? AND id = ?",
            (family_id, redemption_id),
        ).fetchone()

    def fulfill_redemption(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        redemption_id: str,
        fulfilled_by: str,
        now: int,
    ) -> DatabaseRow | None:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        redemption_id: str,
        cancelled_by: str,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE reward_redemptions
            SET status = ?, cancelled_by = ?, cancelled_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (REDEMPTION_CANCELLED, cancelled_by, now, family_id, redemption_id),
        )
        return self.get_redemption(conn, family_id=family_id, redemption_id=redemption_id)
