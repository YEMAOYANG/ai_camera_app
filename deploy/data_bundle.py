#!/usr/bin/env python3
"""Offline, credential-safe migration bundle for the local Mira stack.

Does not stop services, call Providers, rewrite course IDs, publish courses, or
restore databases. Stop every writer before export; restore into empty storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlsplit


# v2: one PostgreSQL database holds the backend (schema app) and the classroom
# runtime (schema public); v1 bundles also carried a MySQL dump.
SCHEMA = "mira.data-bundle.v2"
ARCHIVES = {"backend-data.tar": "backend-data", "openmaic-data.tar": "openmaic-data"}
FILES = {"postgres.dump", "learning-budget-policy.json", *ARCHIVES}
DATABASE_SCHEMAS = ["app", "public"]
POLICY_DESTINATION = "deployment-policies/learning-budget-policy.json"
SECRET_KEYS = (
    "APP_STUDENT_AUTH_PEPPER", "APP_DEVICE_SECRET_KEY", "INTERNAL_API_TOKEN",
    "APP_INTERNAL_API_TOKEN", "MIRA_INTERNAL_API_TOKEN", "MIRA_OPENMAIC_PERSISTENCE_DEV_TOKEN",
)


class BundleError(Exception):
    pass


def read_env(path: Path) -> dict[str, str]:
    """Read literal dotenv values without shell execution or interpolation."""
    result = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)", line)
        if not match:
            raise BundleError(f"Unsupported dotenv syntax at line {number}; no values were printed")
        key, value = match.groups()
        if value.startswith(("'", '"')):
            quote = value[0]
            end = len(value) - 1
            while end > 0 and value[end] != quote:
                end -= 1
            if end == 0 or (value[end + 1:].strip() and not value[end + 1:].strip().startswith("#")):
                raise BundleError(f"Unsupported quoted dotenv value for {key}")
            value = value[1:end]
            if quote == '"':
                value = re.sub(r'\\([\\"])', r'\1', value)
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        result[key] = value
    return result


def literal(value: str, label: str) -> str:
    if "${" in value or "$(" in value or "`" in value or any(c in value for c in "\r\n\x00"):
        raise BundleError(f"{label} requires a literal value without interpolation or control characters")
    return value


def resolve_path(value: str, base: Path, label: str) -> Path:
    path = Path(literal(value, label)).expanduser()
    return (path if path.is_absolute() else base / path).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_files(root: Path):
    if not root.is_dir() or root.is_symlink():
        raise BundleError(f"Missing data directory or symlink: {root}")
    for current, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(current) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise BundleError(f"Unsupported symlink or special file in data directory: {path.relative_to(root)}")
            yield path


def tree_stats(root: Path) -> dict:
    count, size = 0, 0
    for path in tree_files(root):
        if path.is_file():
            count += 1
            size += path.stat().st_size
    return {"path": str(root), "files": count, "bytes": size}


def sources(args) -> dict:
    repo = args.repo_root.resolve()
    backend = repo / "backend"
    runtime = repo / "openmaic-runtime"
    backend_env = read_env(args.backend_env or backend / ".env")
    runtime_env = read_env(args.runtime_env or runtime / ".env")
    source = (args.openmaic_source.resolve() if args.openmaic_source else
              resolve_path(runtime_env.get("OPENMAIC_SOURCE_DIR") or ".runtime/OpenMAIC", runtime, "OPENMAIC_SOURCE_DIR"))
    data = {"backend-data.tar": backend / "data", "openmaic-data.tar": source / "data"}
    # A custom path must not silently disappear from a nominally complete backup.
    expected = [
        (backend_env, "LEARNING_MEDIA_STORAGE_ROOT", backend, data["backend-data.tar"] / "learning-media"),
        (backend_env, "APP_DEVICE_SECRET_STORE_DIR", backend, data["backend-data.tar"] / "device-secrets"),
        (backend_env, "APP_DEVICE_SECRET_KEY_FILE", backend, data["backend-data.tar"] / ".device-secret.key"),
        (runtime_env, "MIRA_FORMAL_AUDIO_DATA_DIR", source, data["openmaic-data.tar"] / "formal-audio"),
        (runtime_env, "MIRA_FORMAL_PROVIDER_READINESS_DATA_DIR", source, data["openmaic-data.tar"] / "formal-provider-readiness"),
    ]
    for values, key, base, canonical in expected:
        if values.get(key) and resolve_path(values[key], base, key) != canonical.resolve():
            raise BundleError(f"Custom {key} is outside the supported canonical layout; include it in a reviewed migration before export")
    policy = (args.budget_policy.resolve() if args.budget_policy else
              resolve_path(backend_env.get("LEARNING_BUDGET_POLICY_PATH") or "content/learning_budget_policy.json", backend,
                           "LEARNING_BUDGET_POLICY_PATH"))
    if not policy.is_file():
        raise BundleError("Budget policy file is missing; pass --budget-policy for the actual running policy")
    try:
        if json.loads(policy.read_text()).get("schemaVersion") != "mira.learning.budget-policy.v1":
            raise ValueError()
    except (ValueError, AttributeError):
        raise BundleError("Budget policy is not a Mira learning budget policy") from None
    return {"repo": repo, "data": data, "policy": policy, "backend_env": backend_env, "runtime_env": runtime_env}


def db_connection(value: str, label: str) -> dict:
    try:
        parsed = urlsplit(literal(value, f"{label} database URL"))
        database = unquote(parsed.path.lstrip("/"))
        if (parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.username
                or not re.fullmatch(r"[A-Za-z0-9_]+", database)):
            raise ValueError()
        query = parse_qs(parsed.query)
        if set(query) - {"sslmode"}:
            raise BundleError(f"Unsupported {label} connection parameters; use a dedicated literal export dotenv file")
        result = {"host": parsed.hostname, "port": str(parsed.port or 5432),
                  "user": unquote(parsed.username), "password": unquote(parsed.password or ""), "database": database}
        if "sslmode" in query:
            result["sslmode"] = query["sslmode"][0]
        for item in result.values():
            if any(c in item for c in "\r\n\x00"):
                raise ValueError()
        return result
    except (ValueError, TypeError):
        raise BundleError(f"Invalid {label} database URL; use postgresql://, URL-encode credentials and select one named database") from None


def private_write(path: Path, content: str | bytes):
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(content.encode() if isinstance(content, str) else content)


def run_dump(command: list[str], target: Path, env: dict):
    with target.open("xb") as output:
        os.chmod(target, 0o600)
        try:
            result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    env=env, check=False)
        except OSError:
            raise BundleError(f"Could not execute {Path(command[0]).name}; install the matching database client") from None
    if result.returncode:
        raise BundleError(f"{Path(command[0]).name} failed (exit {result.returncode}); details suppressed to protect credentials")
    if not target.stat().st_size:
        raise BundleError(f"{Path(command[0]).name} produced an empty dump")


def dump_databases(source: dict, output: Path, pg_dump: str, pg_restore: str) -> dict:
    backend, runtime = source["backend_env"], source["runtime_env"]
    pg = db_connection(backend.get("APP_DATABASE_URL", ""), "backend")
    classroom = db_connection(runtime.get("MIRA_OPENMAIC_AGENT_DATABASE_URL") or runtime.get("DATABASE_URL")
                              or backend.get("MIRA_OPENMAIC_AGENT_DATABASE_URL", ""), "classroom runtime")
    def server(connection):
        local = connection["host"] in {"localhost", "127.0.0.1", "::1"}
        return ("loopback" if local else connection["host"], connection["port"], connection["database"])
    if server(classroom) != server(pg):
        raise BundleError("The backend and the classroom runtime must use the same database; finish the single-database migration first")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    with tempfile.TemporaryDirectory(prefix="mira-dump-credentials-") as directory:
        temp = Path(directory)
        def pg_escape(value):
            return value.replace("\\", "\\\\").replace(":", "\\:")
        passfile = temp / "pgpass"
        private_write(passfile, ":".join(pg_escape(pg[k]) for k in ("host", "port", "database", "user", "password")) + "\n")
        # Service-file values are literal libpq parameters. Connection usernames
        # and passwords therefore never appear in process arguments or output.
        servicefile = temp / "pg_service.conf"
        private_write(servicefile, "[mira_bundle]\n" + "\n".join(f"{key}={pg[value]}" for key, value in
                      (("host", "host"), ("port", "port"), ("dbname", "database"), ("user", "user")))
                      + ("\nsslmode=" + pg["sslmode"] if "sslmode" in pg else "") + "\n")
        run_dump([pg_dump, "--format=custom", "--no-owner", "--no-acl"], output / "postgres.dump",
                 {**env, "PGSERVICEFILE": str(servicefile), "PGSERVICE": "mira_bundle", "PGPASSFILE": str(passfile)})
    try:
        listing = subprocess.run([pg_restore, "--list", str(output / "postgres.dump")],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                 env=env, check=False)
    except OSError:
        raise BundleError("pg_restore is required to record the PostgreSQL source version") from None
    pg_version = re.search(r"Dumped from database version:\s*(\d[^\r\n]*)", listing.stdout.decode("utf-8", errors="replace"))
    if listing.returncode or not pg_version:
        raise BundleError("Could not establish the source database version; no completed bundle was created")
    return {"postgres": {"database": pg["database"], "format": "custom", "schemas": DATABASE_SCHEMAS,
                         "serverVersion": pg_version.group(1).strip(), "serverMajor": int(pg_version.group(1).split(".")[0])}}


def write_archive(root: Path, target: Path):
    with tarfile.open(target, "x", dereference=False) as archive:
        os.chmod(target, 0o600)
        for path in tree_files(root):
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)


def secret_inventory(source: dict) -> dict:
    result = {}
    for origin in ("backend_env", "runtime_env"):
        values = source[origin]
        result[origin] = {key: {"configured": bool(values.get(key)),
                               "sha256": hashlib.sha256(values[key].encode()).hexdigest() if values.get(key) else None}
                          for key in SECRET_KEYS if key in values or (origin == "backend_env" and key == "APP_STUDENT_AUTH_PEPPER")}
    return result


def export_local(args) -> dict:
    if not args.services_stopped:
        raise BundleError("Stop all application/worker/operator writers first, then pass --services-stopped; databases must remain running")
    source = sources(args)
    output = args.output.resolve()
    for root in source["data"].values():
        if output.is_relative_to(root.resolve()):
            raise BundleError("Bundle output must be outside the data directories")
        tree_stats(root)
    if output.exists() or output.is_symlink():
        raise BundleError("Output must be a new directory; refusing to overwrite")
    output.mkdir(mode=0o700, parents=False)
    # A failed export deliberately has no manifest and cannot pass verification.
    databases = dump_databases(source, output, args.pg_dump, args.pg_restore)
    for filename, root in source["data"].items():
        write_archive(root, output / filename)
    private_write(output / "learning-budget-policy.json", source["policy"].read_bytes())
    manifest = {"schemaVersion": SCHEMA, "createdAt": datetime.now(timezone.utc).isoformat(),
                "writersStoppedAcknowledged": True, "databases": databases,
                "files": {name: {"sha256": sha256(output / name), "bytes": (output / name).stat().st_size} for name in sorted(FILES)},
                "policies": [{"env": "LEARNING_BUDGET_POLICY_PATH", "file": "learning-budget-policy.json",
                              "containerPath": "/app/data/" + POLICY_DESTINATION}],
                "secretsToMigrateSeparately": secret_inventory(source),
                "notes": ["Preserve IDs, publication states, ambiguous jobs and audit evidence exactly.",
                          "Database dumps and data archives contain private information; restrict transfer and storage.",
                          "No environment files or Provider keys are exported; preserve student pepper and device key separately.",
                          "If policy was overridden in a process, pass --budget-policy for that exact file."]}
    private_write(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    try:
        verify(output)
    except Exception:
        (output / "manifest.json").unlink(missing_ok=True)
        raise
    return {"bundle": str(output), "verified": True, "files": len(FILES)}


def archive_members(archive: tarfile.TarFile):
    seen = set()
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (not member.name or member.name.startswith("/") or "\\" in member.name or ".." in path.parts
                or ":" in member.name or path.as_posix() != member.name.rstrip("/")
                or member.name in seen or not (member.isfile() or member.isdir())):
            raise BundleError("Unsafe archive member; links, special files and path traversal are forbidden")
        seen.add(member.name)
        yield member


def verify(bundle: Path) -> dict:
    if not bundle.is_dir() or bundle.is_symlink():
        raise BundleError("Bundle must be a regular directory")
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise BundleError("No completed manifest; an interrupted export cannot be restored")
    try:
        manifest = json.loads(manifest_path.read_text())
        if (manifest["schemaVersion"] != SCHEMA or not isinstance(manifest["files"], dict)
                or set(manifest["files"]) != FILES or manifest["writersStoppedAcknowledged"] is not True):
            raise ValueError()
        if manifest["policies"] != [{"env": "LEARNING_BUDGET_POLICY_PATH", "file": "learning-budget-policy.json",
                                     "containerPath": "/app/data/" + POLICY_DESTINATION}]:
            raise ValueError()
        if set(manifest["databases"]) != {"postgres"}:
            raise ValueError()
        for kind in ("postgres",):
            database = manifest["databases"][kind]
            if (not re.fullmatch(r"[A-Za-z0-9_]+", database["database"])
                    or database["format"] != "custom" or database["schemas"] != DATABASE_SCHEMAS
                    or type(database["serverMajor"]) is not int or database["serverMajor"] < 1
                    or not re.fullmatch(r"\d[^\r\n\x00]*", database["serverVersion"])
                    or int(database["serverVersion"].split(".")[0]) != database["serverMajor"]):
                raise ValueError()
        for name, expected in manifest["files"].items():
            path = bundle / name
            if not re.fullmatch(r"[a-f0-9]{64}", expected["sha256"]) or type(expected["bytes"]) is not int or expected["bytes"] < 0:
                raise ValueError()
            if not path.is_file() or path.is_symlink() or path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
                raise BundleError(f"Checksum/size mismatch or missing file: {name}")
        for name in ARCHIVES:
            with tarfile.open(bundle / name, "r:") as archive:
                list(archive_members(archive))
        return manifest
    except (ValueError, KeyError, TypeError, AttributeError, tarfile.TarError):
        raise BundleError("Invalid bundle manifest or archive") from None


def restore_files(bundle: Path, target: Path) -> dict:
    verify(bundle)
    if target.is_symlink() or (target.exists() and (not target.is_dir() or any(target.iterdir()))):
        raise BundleError("Restore target must be missing or an empty regular directory; refusing to overwrite")
    target.mkdir(mode=0o700, parents=False, exist_ok=True)
    for name, directory in ARCHIVES.items():
        destination = target / directory
        destination.mkdir(mode=0o700)
        with tarfile.open(bundle / name, "r:") as archive:
            for member in archive_members(archive):
                path = destination / member.name
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True, mode=0o700)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with archive.extractfile(member) as incoming, path.open("xb") as outgoing:
                        os.chmod(path, 0o600)
                        shutil.copyfileobj(incoming, outgoing)
    policy = target / "backend-data" / POLICY_DESTINATION
    policy.parent.mkdir(mode=0o700, exist_ok=True)
    original = bundle / "learning-budget-policy.json"
    if policy.exists():
        if not policy.is_file() or sha256(policy) != sha256(original):
            raise BundleError("Existing archived deployment policy conflicts; no original file was overwritten")
    else:
        private_write(policy, original.read_bytes())
    return {"target": str(target.resolve()), "filesRestored": True, "databasesRestored": False}


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    for command in ("inventory", "export-local"):
        sub = commands.add_parser(command)
        sub.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
        sub.add_argument("--backend-env", type=Path)
        sub.add_argument("--runtime-env", type=Path)
        sub.add_argument("--openmaic-source", type=Path)
        sub.add_argument("--budget-policy", type=Path)
        if command == "export-local":
            sub.add_argument("--output", type=Path, required=True)
            sub.add_argument("--services-stopped", action="store_true")
            sub.add_argument("--pg-dump", default="pg_dump")
            sub.add_argument("--pg-restore", default="pg_restore")
    sub = commands.add_parser("verify")
    sub.add_argument("bundle", type=Path)
    sub = commands.add_parser("restore-files")
    sub.add_argument("bundle", type=Path)
    sub.add_argument("--target", type=Path, required=True)
    return cli


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inventory":
            source = sources(args)
            result = {"data": {name: tree_stats(root) for name, root in source["data"].items()},
                      "policy": {"path": str(source["policy"]), "sha256": sha256(source["policy"])},
                      "secretsToMigrateSeparately": secret_inventory(source), "databaseContentsRead": False}
        elif args.command == "export-local":
            result = export_local(args)
        elif args.command == "verify":
            verify(args.bundle)
            result = {"bundle": str(args.bundle), "verified": True}
        else:
            result = restore_files(args.bundle, args.target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BundleError, OSError) as error:
        # OSError can include secret-bearing paths, so only our deliberate messages
        # are exposed. Never echo subprocess stderr, dotenv values or connections.
        message = str(error) if isinstance(error, BundleError) else "Filesystem operation failed; check paths, permissions and free space"
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
