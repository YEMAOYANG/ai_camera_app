from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Iterator

from pymysql.err import IntegrityError

from core.database import Database, DatabaseConnection, DatabaseRow
from core.errors import ApiError


class PointRepository:
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
                CREATE TABLE IF NOT EXISTS point_accounts (
                  family_id VARCHAR(255) NOT NULL,
                  child_id VARCHAR(255) NOT NULL,
                  balance INTEGER NOT NULL DEFAULT 0,
                  stage_notice_handled_balance INTEGER NOT NULL DEFAULT 0,
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL,
                  PRIMARY KEY (family_id, child_id)
                );

                CREATE TABLE IF NOT EXISTS point_ledger (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  child_id VARCHAR(255) NOT NULL,
                  delta INTEGER NOT NULL,
                  balance_after INTEGER NOT NULL,
                  type VARCHAR(255) NOT NULL,
                  source_type VARCHAR(255),
                  source_id VARCHAR(255),
                  note TEXT,
                  created_at BIGINT NOT NULL
                );
                """
            )

    def child_exists(self, conn: DatabaseConnection, *, family_id: str, child_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def list_children(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                "SELECT * FROM children WHERE family_id = ? ORDER BY created_at",
                (family_id,),
            ).fetchall()
        )

    def list_app_option_items(
        self,
        conn: DatabaseConnection,
        *,
        catalog_key: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT *
                FROM app_option_items
                WHERE catalog_key = ? AND enabled = 1
                ORDER BY sort_order, item_key
                """,
                (catalog_key,),
            ).fetchall()
        )

    def get_or_create_account(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        now: int,
        for_update: bool = False,
    ) -> DatabaseRow:
        row = conn.execute(
            "SELECT * FROM point_accounts WHERE family_id = ? AND child_id = ?"
            + (" FOR UPDATE" if for_update else ""),
            (family_id, child_id),
        ).fetchone()
        if row is None:
            try:
                conn.execute(
                    """
                    INSERT INTO point_accounts(family_id, child_id, balance, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?)
                    """,
                    (family_id, child_id, now, now),
                )
            except IntegrityError:
                pass
            row = conn.execute(
                "SELECT * FROM point_accounts WHERE family_id = ? AND child_id = ?"
                + (" FOR UPDATE" if for_update else ""),
                (family_id, child_id),
            ).fetchone()
        return row

    def list_accounts(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                "SELECT * FROM point_accounts WHERE family_id = ? ORDER BY created_at",
                (family_id,),
            ).fetchall()
        )

    def adjust_points(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        delta: int,
        ledger_type: str,
        source_type: str | None,
        source_id: str | None,
        note: str | None,
        now: int,
    ) -> DatabaseRow:
        account = self.get_or_create_account(
            conn,
            family_id=family_id,
            child_id=child_id,
            now=now,
            for_update=True,
        )
        balance_after = account["balance"] + delta
        if balance_after < 0:
            raise ApiError("insufficient_points", "积分不足，无法完成操作", 400)
        conn.execute(
            """
            UPDATE point_accounts SET balance = ?, updated_at = ?
            WHERE family_id = ? AND child_id = ?
            """,
            (balance_after, now, family_id, child_id),
        )
        ledger_id = f"ledger_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO point_ledger(
              id, family_id, child_id, delta, balance_after, type,
              source_type, source_id, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ledger_id,
                family_id,
                child_id,
                delta,
                balance_after,
                ledger_type,
                source_type,
                source_id,
                note,
                now,
            ),
        )
        return conn.execute("SELECT * FROM point_ledger WHERE id = ?", (ledger_id,)).fetchone()

    def acknowledge_stage_notice(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        now: int,
    ) -> DatabaseRow:
        account = self.get_or_create_account(
            conn,
            family_id=family_id,
            child_id=child_id,
            now=now,
            for_update=True,
        )
        conn.execute(
            """
            UPDATE point_accounts
            SET stage_notice_handled_balance = ?, updated_at = ?
            WHERE family_id = ? AND child_id = ?
            """,
            (account["balance"], now, family_id, child_id),
        )
        return conn.execute(
            "SELECT * FROM point_accounts WHERE family_id = ? AND child_id = ?",
            (family_id, child_id),
        ).fetchone()

    def list_ledger(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
    ) -> list[DatabaseRow]:
        clauses = ["family_id = ?"]
        values: list[str] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        return list(
            conn.execute(
                f"""
                SELECT * FROM point_ledger
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                """,
                values,
            ).fetchall()
        )

    def get_setting(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        key: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM app_settings WHERE family_id = ? AND setting_key = ?",
            (family_id, key),
        ).fetchone()

    def upsert_setting(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        key: str,
        value: dict,
        now: int,
    ) -> DatabaseRow:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        existing = self.get_setting(conn, family_id=family_id, key=key)
        if existing:
            conn.execute(
                """
                UPDATE app_settings
                SET value = ?, updated_at = ?
                WHERE family_id = ? AND setting_key = ?
                """,
                (encoded, now, family_id, key),
            )
        else:
            conn.execute(
                """
                INSERT INTO app_settings(family_id, setting_key, value, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_id, key, encoded, now),
            )
        return self.get_setting(conn, family_id=family_id, key=key)
