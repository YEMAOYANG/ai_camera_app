from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import AppConfig
from core.database import Database
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
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, now_ms()),
            )
            if verbose:
                print(f"applied {version}")

    if verbose:
        print("migrations complete")


if __name__ == "__main__":
    raise SystemExit(main())
