"""In-memory transaction adapter for service regressions, never a MySQL reset.

Production Database.transaction supplies commit/rollback behavior. SQLite has no
row locks: this fixture serializes its connection and records FOR UPDATE SQL so
tests can check the service's locking contract without claiming MySQL coverage.
"""
import re
import sqlite3
from threading import RLock

from core.database import Database, DatabaseConnection


class MemoryDatabase(Database):
    def __init__(self):
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.raw.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        self.allow_runtime_schema_creation = True
        self.statements = []
        self.lock = RLock()

    def connect(self):
        self.lock.acquire()
        return _MemoryConnection(self)

    def one(self, sql, params=()):
        with self.transaction() as conn:
            return conn.execute(sql, params).fetchone()

    def close(self):
        self.raw.close()


class _MemoryConnection(DatabaseConnection):
    def __init__(self, database):
        super().__init__(database.raw, dialect="sqlite")
        self.database = database

    def _adapt_sql(self, sql):
        self.database.statements.append(sql)
        return re.sub(r"\s+FOR UPDATE\b(?: OF [\w, ]+)?", "", sql)

    def close(self):
        self.database.lock.release()
