from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
from pymysql.cursors import DictCursor


DatabaseRow = Mapping[str, Any]


class DatabaseCursor:
    def __init__(self, cursor):
        self._cursor = cursor

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
        cursor.execute(self._adapt_sql(sql), tuple(params or ()))
        return DatabaseCursor(cursor)

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def _adapt_sql(self, sql: str) -> str:
        if self.dialect == "mysql":
            return sql.replace("?", "%s")
        return sql


class Database:
    def __init__(self, database_url: str | Path):
        self.database_url = str(database_url)
        parsed = urlparse(self.database_url)
        self.dialect = parsed.scheme.split("+", 1)[0]
        if self.dialect != "mysql":
            raise ValueError("Only MySQL database URLs are supported.")
        self.allow_runtime_schema_creation = False

    def connect(self) -> DatabaseConnection:
        parsed = urlparse(self.database_url)
        query = parse_qs(parsed.query)
        conn = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            database=parsed.path.lstrip("/"),
            charset=query.get("charset", ["utf8mb4"])[0],
            cursorclass=DictCursor,
            autocommit=False,
        )
        return DatabaseConnection(conn, dialect="mysql")

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
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in script:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)

    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements
