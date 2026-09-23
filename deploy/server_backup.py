"""Stopped-writer backup of the deployed Compose stack; invoked by server.py."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

import data_bundle


# These scripts are fixed text, never assembled from a password or other config
# value. The database containers already hold their credentials in environment.
MYSQL_DUMP = ('export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
              'exec mysqldump --no-defaults --no-login-paths --user=root '
              '--single-transaction --skip-lock-tables --quick --routines --events '
              '--triggers --hex-blob --no-tablespaces --set-gtid-purged=OFF '
              '--default-character-set=utf8mb4 --comments "$MYSQL_DATABASE"')
MYSQL_VERSION = ('export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
                 'exec mysql --no-defaults --no-login-paths --user=root --batch '
                 '--skip-column-names --execute="SELECT VERSION()"')
POSTGRES_DUMP = ('export PGPASSWORD="$POSTGRES_PASSWORD"; '
                 'exec pg_dump --host=127.0.0.1 --username="$POSTGRES_USER" '
                 '--dbname="$POSTGRES_DB" --format=custom --no-owner --no-acl')


def run(command, *, env, label, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE):
    try:
        result = subprocess.run(command, env=env, stdin=stdin, stdout=stdout,
                                stderr=subprocess.PIPE, check=False)
    except OSError:
        raise data_bundle.BundleError(f"Could not run {label}; check Docker and Compose availability") from None
    if result.returncode:
        raise data_bundle.BundleError(f"{label} failed (exit {result.returncode}); output suppressed to protect credentials")
    return result


def assert_writers_stopped(prefix, env):
    result = run([*prefix, "ps", "--status", "running", "--services"], env=env, label="Compose writer-state check")
    services = set(result.stdout.decode("utf-8").split())
    if services != {"mysql", "postgres"}:
        raise data_bundle.BundleError("Backup requires mysql and postgres running, with every application, worker and other service stopped")


def source_version(text: str, label: str) -> dict:
    value = text.strip()
    if not re.fullmatch(r"\d+\.\d+[^\r\n\x00]*", value):
        raise data_bundle.BundleError(f"Could not establish {label} source database version")
    return {"serverVersion": value, "serverMajor": int(value.split(".")[0])}


def export_server(config: dict, compose_prefix: list[str], command_env: dict, output: Path) -> dict:
    """Export an already-stopped deployment without changing services or data."""
    assert_writers_stopped(compose_prefix, command_env)
    try:
        root = Path(config["MIRA_DATA_ROOT"])
        if not root.is_absolute():
            raise data_bundle.BundleError("MIRA_DATA_ROOT must be absolute")
        backend_env = data_bundle.read_env(Path(config["MIRA_BACKEND_ENV_FILE"]))
        roots = {"backend-data.tar": root / "backend-data", "openmaic-data.tar": root / "openmaic-data"}
        policy = roots["backend-data.tar"] / data_bundle.POLICY_DESTINATION
        if not policy.is_file() or policy.is_symlink():
            raise data_bundle.BundleError("Deployed budget policy is missing or a symlink")
        if json.loads(policy.read_text()).get("schemaVersion") != "mira.learning.budget-policy.v1":
            raise data_bundle.BundleError("Deployed budget policy has an invalid schema")
        secrets = data_bundle.secret_inventory({
            "backend_env": {"APP_STUDENT_AUTH_PEPPER": config["MIRA_STUDENT_AUTH_PEPPER"],
                            "INTERNAL_API_TOKEN": config["MIRA_INTERNAL_API_TOKEN"],
                            "APP_DEVICE_SECRET_KEY": backend_env.get("APP_DEVICE_SECRET_KEY", "")},
            "runtime_env": {"MIRA_INTERNAL_API_TOKEN": config["MIRA_INTERNAL_API_TOKEN"],
                            "MIRA_OPENMAIC_PERSISTENCE_DEV_TOKEN": config["MIRA_PERSISTENCE_TOKEN"]},
        })
    except (KeyError, ValueError, TypeError, AttributeError):
        raise data_bundle.BundleError("Incomplete deployment configuration or invalid deployed budget policy") from None
    output = output.resolve()
    if output.exists() or output.is_symlink():
        raise data_bundle.BundleError("Backup output must be a new directory; refusing to overwrite")
    if output.is_relative_to(root.resolve()):
        raise data_bundle.BundleError("Backup output must be outside MIRA_DATA_ROOT")
    for directory in roots.values():
        data_bundle.tree_stats(directory)
    output.mkdir(mode=0o700, parents=False)
    mysql_version = run([*compose_prefix, "exec", "-T", "mysql", "sh", "-ec", MYSQL_VERSION],
                        env=command_env, label="MySQL version query").stdout.decode("utf-8")
    databases = {"mysql": {"database": "mira", "format": "sql", **source_version(mysql_version, "MySQL")}}
    for service, command, filename in (("mysql", MYSQL_DUMP, "mysql.sql"),
                                       ("postgres", POSTGRES_DUMP, "postgres.dump")):
        path = output / filename
        with path.open("xb") as destination:
            os.chmod(path, 0o600)
            run([*compose_prefix, "exec", "-T", service, "sh", "-ec", command],
                env=command_env, label=f"{service} dump", stdout=destination)
        if not path.stat().st_size:
            raise data_bundle.BundleError(f"{service} produced an empty dump")
    with (output / "postgres.dump").open("rb") as incoming:
        listing = run([*compose_prefix, "exec", "-T", "postgres", "pg_restore", "--list"],
                      env=command_env, label="PostgreSQL archive version check", stdin=incoming)
    match = re.search(r"Dumped from database version:\s*(\d[^\r\n]*)", listing.stdout.decode("utf-8"))
    if not match:
        raise data_bundle.BundleError("PostgreSQL archive does not identify its source version")
    databases["postgres"] = {"database": "openmaic", "format": "custom", **source_version(match.group(1), "PostgreSQL")}
    for filename, directory in roots.items():
        data_bundle.write_archive(directory, output / filename)
    data_bundle.private_write(output / "learning-budget-policy.json", policy.read_bytes())
    assert_writers_stopped(compose_prefix, command_env)
    manifest = {
        "schemaVersion": data_bundle.SCHEMA,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "writersStoppedAcknowledged": True,
        "databases": databases,
        "files": {name: {"sha256": data_bundle.sha256(output / name), "bytes": (output / name).stat().st_size}
                  for name in sorted(data_bundle.FILES)},
        "policies": [{"env": "LEARNING_BUDGET_POLICY_PATH", "file": "learning-budget-policy.json",
                      "containerPath": "/app/data/" + data_bundle.POLICY_DESTINATION}],
        "secretsToMigrateSeparately": secrets,
        "notes": ["Exported from a deployed Compose stack with only database services running.",
                  "All external database writers must also remain stopped for the entire export.",
                  "Preserve IDs, publication states, ambiguous jobs and audit evidence exactly.",
                  "No dotenv files or Provider keys are exported; preserve identity secrets separately."],
    }
    data_bundle.private_write(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    try:
        data_bundle.verify(output)
    except Exception:
        (output / "manifest.json").unlink(missing_ok=True)
        raise
    return {"bundle": str(output), "verified": True, "files": len(data_bundle.FILES)}
