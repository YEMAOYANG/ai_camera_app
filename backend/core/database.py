from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg import ClientCursor
from psycopg.rows import dict_row
from psycopg.types.string import TextLoader


DatabaseRow = Mapping[str, Any]

# Driver errors, re-exported so callers never import the driver directly.
DatabaseError = psycopg.Error
IntegrityError = psycopg.IntegrityError
OperationalError = psycopg.OperationalError

# Backend tables live in this schema; the classroom runtime owns `public`.
DEFAULT_SCHEMA = "app"

_UNIQUE_VIOLATION = "23505"
_RETRYABLE_CONFLICTS = {"40P01", "40001"}  # deadlock_detected, serialization_failure
_LOCK_NOT_AVAILABLE = "55P03"


def error_sqlstate(exc: BaseException) -> str:
    return str(getattr(exc, "sqlstate", "") or "")


def is_unique_violation(exc: BaseException) -> bool:
    return error_sqlstate(exc) == _UNIQUE_VIOLATION


def is_retryable_conflict(exc: BaseException) -> bool:
    """True for a deadlock or serialization failure; PostgreSQL rolled back the transaction."""
    return error_sqlstate(exc) in _RETRYABLE_CONFLICTS


def is_lock_timeout(exc: BaseException) -> bool:
    return error_sqlstate(exc) == _LOCK_NOT_AVAILABLE


def lock_for_allocation(conn, scope: str, key: str) -> None:
    """Serialize next-number allocation for one key until the transaction ends.

    MySQL's `SELECT MAX(...) ... FOR UPDATE` also blocked concurrent inserts
    through gap locks. PostgreSQL rejects locking an aggregate and its row
    locks never block new rows, so allocation takes a transaction-scoped
    advisory lock instead. Test doubles without a dialect take no lock.
    """
    if getattr(conn, "dialect", None) == "postgresql":
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(?), hashtext(?))", (scope, key))


class DatabaseCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class DatabaseConnection:
    def __init__(self, connection, *, dialect: str):
        self._connection = connection
        self.dialect = dialect

    def execute(self, sql: str, params: Any = ()) -> DatabaseCursor:
        cursor = self._connection.cursor()
        # Booleans bind as 1/0, as PyMySQL did: flag columns are smallint.
        values = tuple(int(value) if isinstance(value, bool) else value for value in (params or ()))
        cursor.execute(self._adapt_sql(sql), values)
        return DatabaseCursor(cursor)

    def executescript(self, script: str) -> None:
        """Run DDL/SQL text verbatim: no placeholders, so ? and % stay literal."""
        cursor = self._connection.cursor()
        for statement in _split_sql_script(script):
            cursor.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def _adapt_sql(self, sql: str) -> str:
        return sql.replace("?", "%s")


class Database:
    def __init__(self, database_url: str | Path):
        self.database_url = str(database_url)
        parsed = urlparse(self.database_url)
        scheme = parsed.scheme.split("+", 1)[0]
        if scheme not in {"postgresql", "postgres"}:
            raise ValueError("Only PostgreSQL database URLs are supported.")
        self.dialect = "postgresql"
        self.allow_runtime_schema_creation = False

    def connect(self) -> DatabaseConnection:
        parsed = urlparse(self.database_url)
        kwargs: dict[str, Any] = {}
        if "options" not in parse_qs(parsed.query):
            # Only the backend schema, so no statement can fall through to
            # the classroom runtime's tables in `public`.
            # lock_timeout matches MySQL's default innodb_lock_wait_timeout.
            kwargs["options"] = f"-c search_path={DEFAULT_SCHEMA} -c lock_timeout=50s"
        conninfo = parsed._replace(scheme="postgresql").geturl()
        conn = psycopg.connect(
            conninfo,
            autocommit=False,
            row_factory=dict_row,
            cursor_factory=ClientCursor,
            **kwargs,
        )
        # Keep the PyMySQL contract: JSON columns arrive as their text.
        conn.adapters.register_loader("json", TextLoader)
        conn.adapters.register_loader("jsonb", TextLoader)
        return DatabaseConnection(conn, dialect=self.dialect)

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _split_sql_script(script: str) -> list[str]:
    """Split on top-level semicolons, honouring quotes, -- comments and $$ bodies."""
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_dollar_body = False
    in_line_comment = False
    index = 0
    length = len(script)

    while index < length:
        char = script[index]
        pair = script[index:index + 2]
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                current.append(char)
            index += 1
            continue
        if not (in_single_quote or in_double_quote):
            if pair == "$$":
                in_dollar_body = not in_dollar_body
                current.append(pair)
                index += 2
                continue
            if not in_dollar_body and pair == "--":
                in_line_comment = True
                index += 2
                continue
        if not in_dollar_body:
            if char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == ";" and not in_single_quote and not in_double_quote:
                statement = "".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
                index += 1
                continue
        current.append(char)
        index += 1

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements
