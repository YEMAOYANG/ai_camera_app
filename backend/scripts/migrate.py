from __future__ import annotations

import sys
import hashlib
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AppConfig
from core.database import DEFAULT_SCHEMA, Database, _split_sql_script
from core.security import now_ms

# First key of the two-integer advisory lock; the classroom runtime uses the
# single-bigint lock space, which never overlaps with this one.
_LOCK_NAMESPACE = 0x4D495241  # "MIRA"


def main() -> int:
    config = AppConfig.from_env()
    config.validate()
    run_migrations(config.DATABASE_URL)
    return 0


def run_migrations(database_url: str, *, verbose: bool = True, stop_before: str | None = None) -> None:
    """Apply pending migrations in name order; `stop_before` leaves that file and later ones pending."""
    database = Database(database_url)
    migrations_dir = ROOT / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    if stop_before is not None:
        if not (migrations_dir / stop_before).is_file():
            raise ValueError(f"unknown migration {stop_before}")
        files = [path for path in files if path.name < stop_before]

    with database.transaction() as conn:
        target = conn.execute(
            "SELECT current_database() AS migration_database, current_schema() AS migration_schema"
        ).fetchone()
        database_name = target["migration_database"]
        if not database_name:
            raise RuntimeError("Cannot migrate without a selected database.")
        if target["migration_schema"] != DEFAULT_SCHEMA:
            raise RuntimeError(
                f"Schema {DEFAULT_SCHEMA!r} is missing or not first on the search path. No migration was started."
            )
        # A session lock outlives the per-file commits below.
        lock_key = int.from_bytes(hashlib.sha256(database_name.encode("utf-8")).digest()[:4], "big", signed=True)
        acquired = conn.execute(
            "SELECT pg_try_advisory_lock(?, ?) AS acquired", (_LOCK_NAMESPACE, lock_key)
        ).fetchone()
        if acquired is None or not acquired["acquired"]:
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
            conn.commit()
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
                        conn.executescript(statement)
                    step = "registering the completed migration version"
                    conn.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, now_ms()),
                    )
                    step = "committing the migration version"
                    conn.commit()
                except Exception as exc:
                    raise RuntimeError(
                        f"Migration {version} failed while {step}. Its transaction was rolled back, "
                        "so this file left no changes; earlier files remain applied."
                    ) from exc
                if verbose:
                    print(f"applied {version}", flush=True)
        except BaseException:
            # Clear an aborted transaction before the unlock below.
            with suppress(Exception):
                conn.rollback()
            raise
        finally:
            # Closing the connection also releases this lock. Avoid hiding the
            # precise migration error with a cleanup error.
            with suppress(Exception):
                conn.execute("SELECT pg_advisory_unlock(?, ?)", (_LOCK_NAMESPACE, lock_key))

    if verbose:
        print("migrations complete")


if __name__ == "__main__":
    raise SystemExit(main())
