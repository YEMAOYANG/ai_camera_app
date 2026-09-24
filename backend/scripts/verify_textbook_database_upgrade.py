"""Back up an explicitly named local DB; restore/migrate/import on a private copy.

Never migrates the source. Backup files contain private data and must remain in
an ignored, access-restricted directory. Credentials are passed via a temporary
0600 MySQL defaults file, never command arguments or output.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pymysql
from pymysql.cursors import DictCursor
from core.config import AppConfig
from core.database import Database, DatabaseConnection
from repositories.textbook_repository import TextbookRepository
from services.textbook_learning_service import TextbookLearningService

MIGRATIONS = ("082_fixed_textbook_learning.sql", "083_textbook_course_previews.sql")


def fingerprint(db):
    result = {}
    with db.transaction() as conn:
        for entry in conn.execute("SHOW FULL TABLES WHERE Table_type='BASE TABLE'").fetchall():
            name = next(v for k, v in entry.items() if k != "Table_type")
            if not name.replace("_", "").isalnum():
                raise RuntimeError("Unsupported table identifier")
            rows = conn.execute(f"SELECT * FROM `{name}`").fetchall()
            hashes = sorted(hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest() for row in rows)
            result[name] = {"rows": len(rows), "sha256": hashlib.sha256("".join(hashes).encode()).hexdigest()}
    return result


class CopyDatabase:
    def __init__(self, socket):
        self.socket = socket

    @contextmanager
    def transaction(self):
        raw = pymysql.connect(unix_socket=self.socket, user="root", database="textbook_upgrade_copy", charset="utf8mb4", cursorclass=DictCursor, autocommit=False)
        conn = DatabaseConnection(raw, dialect="mysql")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    parsed = urlparse(AppConfig.from_env().DATABASE_URL)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path.lstrip("/") != args.database:
        raise RuntimeError("Source must be the explicitly named local database")
    source = Database(AppConfig.from_env().DATABASE_URL)
    with source.transaction() as conn:
        applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    pending = [p.name for p in sorted((ROOT / "migrations").glob("*.sql")) if p.name not in applied]
    if pending != list(MIGRATIONS):
        raise RuntimeError("Unexpected pending migration set; source was not modified")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(output, 0o700)
    before = fingerprint(source)
    backup = output / "database.sql"
    with tempfile.TemporaryDirectory(prefix="mira-textbook-upgrade-", dir="/tmp") as temp:
        temp = Path(temp)
        defaults = temp / "client.cnf"
        def quoted(s):
            return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r') + '"'
        with open(defaults, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
            file.write("[client]\n" + "\n".join(f"{k}={quoted(str(v))}" for k, v in {
                "host": parsed.hostname, "port": parsed.port or 3306,
                "user": unquote(parsed.username or ""), "password": unquote(parsed.password or "")}.items()) + "\n")
        try:
            with open(backup, "xb", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
                result = subprocess.run([shutil.which("mysqldump"), f"--defaults-extra-file={defaults}", "--single-transaction",
                    "--skip-lock-tables", "--hex-blob", "--no-tablespaces", "--set-gtid-purged=OFF", "--column-statistics=0", args.database],
                    stdout=file, stderr=subprocess.PIPE, timeout=60)
            if result.returncode:
                raise RuntimeError(f"mysqldump failed with exit code {result.returncode}; no source write occurred")
        finally:
            defaults.unlink(missing_ok=True)
        if fingerprint(source) != before:
            raise RuntimeError("Source changed during backup; retain backup and repeat verification in a quiet window")
        data, socket = temp / "data", str(temp / "mysql.sock")
        mysqld = shutil.which("mysqld")
        with (temp / "server.log").open("wb") as log:
            subprocess.run([mysqld, "--no-defaults", "--initialize-insecure", f"--datadir={data}"], stdout=log, stderr=log, check=True, timeout=60)
            process = subprocess.Popen([mysqld, "--no-defaults", f"--datadir={data}", f"--socket={socket}", "--skip-networking", "--mysqlx=OFF", f"--pid-file={temp / 'mysql.pid'}"], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 30
                while not Path(socket).exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Isolated MySQL failed to start")
                    time.sleep(0.1)
                raw = pymysql.connect(unix_socket=socket, user="root", autocommit=True)
                with raw.cursor() as cursor:
                    cursor.execute("CREATE DATABASE textbook_upgrade_copy CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
                raw.close()
                with backup.open("rb") as file:
                    restored = subprocess.run([shutil.which("mysql"), "--no-defaults", f"--socket={socket}", "--user=root", "textbook_upgrade_copy"], stdin=file, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=90)
                if restored.returncode:
                    raise RuntimeError("Isolated restore failed; source was not modified")
                copy = CopyDatabase(socket)
                if fingerprint(copy) != before:
                    raise RuntimeError("Restored data does not match source snapshot")
                with copy.transaction() as conn:
                    for name in MIGRATIONS:
                        conn.executescript((ROOT / "migrations" / name).read_text())
                        conn.execute("INSERT INTO schema_migrations(version,applied_at) VALUES (?,?)", (name, int(time.time()*1000)))
                        conn.commit()
                service = TextbookLearningService(TextbookRepository(copy))
                manifests = [json.loads(p.read_text()) for p in sorted((ROOT / "content/textbooks").glob("*.json"))]
                service.import_catalog(manifests)
                service.import_manifest(json.loads((ROOT / "content/textbooks/revisions/pep-chinese-g1-upper.preview.v2.json").read_text()))
                after = fingerprint(copy)
                unchanged = all(after[k] == v for k, v in before.items() if k != "schema_migrations")
                if not unchanged:
                    raise RuntimeError("An existing table changed during isolated upgrade")
                with backup.open("rb") as file:
                    backup_hash = hashlib.file_digest(file, "sha256").hexdigest()
                report = {"sourceDatabase": args.database, "sourceModified": False,
                    "backup": str(backup), "backupSha256": backup_hash,
                    "backupBytes": backup.stat().st_size, "restoredTables": len(before),
                    "migrations": list(MIGRATIONS), "migrationSha256": {name: hashlib.sha256((ROOT / "migrations" / name).read_bytes()).hexdigest() for name in MIGRATIONS},
                    "existingTablesUnchanged": unchanged, "sourceFingerprints": before,
                    "textbookEditions": after["learning_textbook_editions"]["rows"], "textbookRevisions": after["learning_textbook_revisions"]["rows"],
                    "existingCourses": before["learning_courses"]["rows"], "existingSessions": before["learning_sessions"]["rows"]}
                (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                print(json.dumps({k: v for k, v in report.items() if k != "sourceFingerprints"}, ensure_ascii=False, indent=2))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Database exceptions can contain identifiers or data; never dump a
        # configuration traceback from this operator helper.
        print(json.dumps({"ok": False, "errorType": type(exc).__name__,
                          "message": str(exc) if isinstance(exc, RuntimeError) else "Verification failed; source was not modified"}), file=sys.stderr)
        raise SystemExit(1)
