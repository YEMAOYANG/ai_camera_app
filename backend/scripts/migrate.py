from __future__ import annotations

import sys
import hashlib
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AppConfig
from core.database import Database, _split_sql_script
from core.security import now_ms


def main() -> int:
    config = AppConfig.from_env()
    config.validate()
    run_migrations(config.DATABASE_URL)
    return 0


def run_migrations(database_url: str, *, verbose: bool = True) -> None:
    database = Database(database_url)
    migrations_dir = ROOT / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))

    with database.transaction() as conn:
        database_name = conn.execute("SELECT DATABASE() AS migration_database").fetchone()["migration_database"]
        if not database_name:
            raise RuntimeError("Cannot migrate without a selected database.")
        # MySQL named locks survive the implicit commits caused by DDL. A row
        # lock inside the transaction would be released by the first ALTER.
        lock_name = "mira:migrations:" + hashlib.sha256(database_name.encode("utf-8")).hexdigest()[:40]
        acquired = conn.execute("SELECT GET_LOCK(?, 0) AS acquired", (lock_name,)).fetchone()
        if acquired is None or acquired["acquired"] != 1:
            raise RuntimeError("Another migration is running for this database, or the migration lock is unavailable. No migration was started.")
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  version VARCHAR(255) PRIMARY KEY,
                  applied_at BIGINT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for path in files:
                version = path.name
                if version in applied:
                    continue
                step = "reading the migration file"
                try:
                    statements = _split_sql_script(path.read_text(encoding="utf-8"))
                    for index, statement in enumerate(statements, 1):
                        step = f"SQL statement {index}/{len(statements)}"
                        conn.execute(statement)
                    step = "registering the completed migration version"
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, now_ms()),
                    )
                    step = "committing the migration version"
                    conn.commit()
                except Exception as exc:
                    raise RuntimeError(
                        f"Migration {version} failed while {step}. MySQL DDL may already "
                        "have committed; rollback does not restore the earlier schema. "
                        "Inspect the current schema, schema_migrations and the saved backup "
                        "before resuming. Do not blindly rerun the migration."
                    ) from exc
                if verbose:
                    print(f"applied {version}", flush=True)
        except BaseException:
            # Release pending DML before another process can acquire the lock.
            # Previously committed DDL and completed files remain in place.
            with suppress(Exception):
                conn.rollback()
            raise
        finally:
            # A failed connection also releases this lock when closed. Avoid
            # hiding the precise migration error with a cleanup error.
            with suppress(Exception):
                conn.execute("SELECT RELEASE_LOCK(?)", (lock_name,))

    if verbose:
        print("migrations complete")


if __name__ == "__main__":
    raise SystemExit(main())
