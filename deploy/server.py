#!/usr/bin/env python3
"""Validated single-host Mira deployment. Requires Python 3.10+ and Docker Compose v2.

No command deletes existing data, starts generation workers, or prints secrets.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlsplit

import data_bundle as bundle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ORIGINS = tuple(f"MIRA_{name}_ORIGIN" for name in ("PARENT", "STUDENT", "CLASSROOM", "API", "REALTIME"))
SECRETS = ("MIRA_DB_PASSWORD", "MIRA_POSTGRES_SUPERUSER_PASSWORD",
           "MIRA_INTERNAL_API_TOKEN", "MIRA_PERSISTENCE_TOKEN", "MIRA_STUDENT_AUTH_PEPPER")
WRITERS = ("edge", "student-web", "gateway", "curriculum-worker", "backend", "openmaic")
START_SERVICES = ("postgres", "storage-init", "openmaic", "backend", "gateway", "student-web", "edge")
MARKER = ".mira-deployment.json"
GENERATION_FLAGS = ("LEARNING_DAILY_PREPARATION_ENABLED", "LEARNING_DYNAMIC_GENERATION_ENABLED",
                    "LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED",
                    "LEARNING_CLASSROOM_GENERATION_ENABLED", "LEARNING_MEDIA_WORKER_ENABLED",
                    "LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED",
                    "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED",
                    "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED",
                    "LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED")


class DeployError(Exception):
    pass


def read_private(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise DeployError("Configuration must be an existing regular file")
    if path.stat().st_mode & 0o077:
        raise DeployError(f"Configuration permissions are too broad: chmod 600 {path.name}")
    values = bundle.read_env(path)
    for key, value in values.items():
        bundle.literal(value, key)
        # Docker's dotenv interpolation must not reinterpret literal values.
        if "$" in value:
            raise DeployError(f"{key}: dollar signs are not supported in deployment dotenv files")
    return values


def absolute_path(value: str, key: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or len(path.parts) < 4 or path.resolve() != path or any(c.isspace() for c in value):
        raise DeployError(f"{key} must be a dedicated absolute path with no symlinks or whitespace")
    if any(path == protected or path in protected.parents for protected in (ROOT, HERE)):
        raise DeployError(f"{key} must not contain the source checkout")
    return path


def validate(values: dict) -> dict:
    required = (*ORIGINS, *SECRETS, "MIRA_DEPLOY_MODE", "MIRA_PROJECT_NAME", "MIRA_RELEASE_TAG",
                "MIRA_BASE_DOMAIN", "MIRA_ACCESS_CIDRS", "MIRA_DATA_ROOT", "MIRA_PARENT_WEB_DIST",
                "MIRA_BACKEND_ENV_FILE", "MIRA_RUNTIME_ENV_FILE", "MIRA_POSTGRES_IMAGE")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise DeployError("Missing configuration keys: " + ", ".join(missing))
    if values["MIRA_DEPLOY_MODE"] not in ("production", "preview"):
        raise DeployError("MIRA_DEPLOY_MODE must be production or preview")
    domain = values["MIRA_BASE_DOMAIN"]
    if (not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", domain)
            or domain in ("example.com", "example.org", "example.net") or ".." in domain):
        raise DeployError("Set MIRA_BASE_DOMAIN to your actual registered domain")
    hosts = []
    for key in ORIGINS:
        url = urlsplit(values[key])
        if (url.scheme != "https" or not url.hostname or url.netloc != url.hostname or url.path
                or url.query or url.fragment or not url.hostname.endswith("." + domain)
                or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*", url.hostname)):
            raise DeployError(f"{key} must be an HTTPS subdomain of MIRA_BASE_DOMAIN, without a port or path")
        hosts.append(url.hostname)
    if len(set(hosts)) != len(hosts):
        raise DeployError("The five public origins must be distinct")
    for key in SECRETS:
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", values[key]) or values[key].startswith("CHANGE_ME"):
            raise DeployError(f"{key} must contain 32-256 private URL-safe characters")
    for key in ("MIRA_PROJECT_NAME", "MIRA_RELEASE_TAG"):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,62}", values[key]):
            raise DeployError(f"{key} has an invalid project name or image tag")
    pg_image = re.fullmatch(r"postgres:(\d+)(?:\.\d+)?-alpine", values["MIRA_POSTGRES_IMAGE"])
    if not pg_image or not 14 <= int(pg_image[1]) <= 17:
        raise DeployError("Use postgres:14-17-alpine with this data mount; newer versions need a reviewed volume-layout update")
    paths = {key: absolute_path(values[key], key) for key in
             ("MIRA_DATA_ROOT", "MIRA_PARENT_WEB_DIST", "MIRA_BACKEND_ENV_FILE", "MIRA_RUNTIME_ENV_FILE")}
    for key, path in paths.items():
        for other, candidate in paths.items():
            if key != other and (path == candidate or path in candidate.parents):
                raise DeployError("Data, frontend and secret paths must not overlap")
    try:
        networks = [ipaddress.ip_network(item, strict=True) for item in values["MIRA_ACCESS_CIDRS"].split()]
    except ValueError:
        raise DeployError("MIRA_ACCESS_CIDRS must contain valid space-separated CIDRs") from None
    if not networks:
        raise DeployError("At least one access CIDR is required")
    if values["MIRA_DEPLOY_MODE"] == "preview":
        # Limit preview to individual testers or small known public egress ranges.
        if any(not net.network_address.is_global or net.prefixlen < (24 if net.version == 4 else 64) for net in networks):
            raise DeployError("Preview requires narrow public tester CIDRs (IPv4 /24 or narrower; IPv6 /64 or narrower)")
    return values


def validate_runtime(values: dict, *, starting: bool = False):
    backend = read_private(Path(values["MIRA_BACKEND_ENV_FILE"]))
    runtime = read_private(Path(values["MIRA_RUNTIME_ENV_FILE"]))
    active = [key for key in GENERATION_FLAGS if backend.get(key, "0").lower() not in ("0", "false", "no")]
    if active:
        raise DeployError("This deployment defaults to existing courses only; generation flags must remain off: " + ", ".join(active))
    if starting:
        if not (Path(values["MIRA_PARENT_WEB_DIST"]) / "index.html").is_file():
            raise DeployError("Build and upload the complete parent Web output before start")
        if values["MIRA_DEPLOY_MODE"] == "production":
            # Current provider registry returns UnavailableSmsProvider for every
            # non-development provider. Do not silently expose development OTPs.
            raise DeployError("Production SMS providers are not implemented in this revision. Complete SMS integration, or use IP-restricted preview mode for the boss demo")
    return backend, runtime


def command_env(values: dict) -> dict:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("COMPOSE_", "MIRA_")) and key not in values}
    env.update(values)
    return env


def compose_prefix(path: Path, values: dict) -> list[str]:
    command = ["docker", "compose", "--project-directory", str(HERE), "--env-file", str(path),
               "-f", str(HERE / "compose.production.yml")]
    if values["MIRA_DEPLOY_MODE"] == "preview":
        command += ["-f", str(HERE / "compose.preview.yml")]
    return command


def run(prefix: list, env: dict, *args: str, input_file: Path | None = None, capture: bool = False) -> str:
    try:
        with (input_file.open("rb") if input_file else open(os.devnull, "rb")) as stream:
            result = subprocess.run([*prefix, *args], env=env, stdin=stream, stdout=subprocess.PIPE if capture else None,
                                    stderr=subprocess.PIPE, check=False)
    except OSError:
        raise DeployError("Cannot execute Docker Compose; install Docker Engine and the Compose v2 plugin") from None
    if result.returncode:
        # Database tooling can echo SQL/data/secrets; do not forward its stderr.
        raise DeployError(f"Docker Compose operation failed (exit {result.returncode}); inspect restricted server logs")
    return result.stdout.decode() if capture else ""


def ensure_stopped(prefix: list, env: dict):
    running = set(run(prefix, env, "ps", "--status", "running", "--services", capture=True).split())
    if running - {"postgres"}:
        raise DeployError("Stop application writers before preparing/restoring data")


def ensure_empty(root: Path):
    if root.is_symlink() or (root.exists() and (not root.is_dir() or any(root.iterdir()))):
        raise DeployError("Data root must be new or empty. Existing data is never overwritten; inspect it and choose a new directory")


def record(root: Path, kind: str, manifest: dict | None = None):
    data = {"schema": "mira.deployment.v1", "preparedAt": datetime.now(timezone.utc).isoformat(), "kind": kind}
    if manifest:
        data["bundleCreatedAt"] = manifest.get("createdAt")
        data["databases"] = manifest["databases"]
        data["files"] = manifest["files"]
    bundle.private_write(root / MARKER, json.dumps(data, indent=2) + "\n")


def migrate(prefix: list, env: dict):
    run(prefix, env, "run", "--rm", "--no-deps", "database-migrate")


def validate_prepared(root: Path, values: dict):
    try:
        marker = root / MARKER
        state = json.loads(marker.read_text())
        if marker.is_symlink() or state.get("schema") != "mira.deployment.v1" or state.get("kind") not in ("empty", "restored"):
            raise ValueError()
        for name in ("postgres", "backend-data", "openmaic-data"):
            directory = root / name
            if not directory.is_dir() or directory.is_symlink():
                raise ValueError()
        pg_major = (root / "postgres/PG_VERSION").read_text().strip()
        if values["MIRA_POSTGRES_IMAGE"].split(":")[1].split("-")[0].split(".")[0] != pg_major:
            raise DeployError("PostgreSQL image major differs from the existing data directory; use a reviewed migration")
        policy = json.loads((root / "backend-data" / bundle.POLICY_DESTINATION).read_text())
        if policy.get("schemaVersion") != "mira.learning.budget-policy.v1":
            raise ValueError()
    except (OSError, ValueError, TypeError, AttributeError):
        raise DeployError("Prepared storage is missing or incomplete. Inspect the data mount; do not initialize empty databases over an existing deployment") from None


def version_compatible(values: dict, manifest: dict):
    target = re.search(r":(\d+)", values["MIRA_POSTGRES_IMAGE"])
    if int(target[1]) != manifest["databases"]["postgres"]["serverMajor"]:
        raise DeployError("MIRA_POSTGRES_IMAGE must match the bundle's PostgreSQL server major version")


def check_secret_continuity(values: dict, backend: dict, manifest: dict):
    mapping = {"APP_STUDENT_AUTH_PEPPER": values["MIRA_STUDENT_AUTH_PEPPER"],
               "APP_DEVICE_SECRET_KEY": backend.get("APP_DEVICE_SECRET_KEY", ""),
               "INTERNAL_API_TOKEN": values["MIRA_INTERNAL_API_TOKEN"],
               "APP_INTERNAL_API_TOKEN": values["MIRA_INTERNAL_API_TOKEN"],
               "MIRA_INTERNAL_API_TOKEN": values["MIRA_INTERNAL_API_TOKEN"],
               "MIRA_OPENMAIC_PERSISTENCE_DEV_TOKEN": values["MIRA_PERSISTENCE_TOKEN"]}
    inventory = manifest.get("secretsToMigrateSeparately")
    if not isinstance(inventory, dict):
        raise DeployError("Migration bundle is missing the secret continuity manifest")
    for section in ("backend_env", "runtime_env"):
        entries = inventory.get(section, {})
        for key, expected in entries.items():
            if expected.get("configured") and key in mapping:
                if hashlib.sha256(mapping[key].encode()).hexdigest() != expected.get("sha256"):
                    raise DeployError(f"Preserve the source value of {key} before restoring; its fingerprint differs")
    if not inventory.get("backend_env", {}).get("APP_STUDENT_AUTH_PEPPER", {}).get("configured"):
        print("NOTICE: Source used the development student pepper; reset student PINs and pair again with the new private pepper.")


def initialize(directory: Path):
    directory = directory.absolute()
    targets = {"compose.env": "compose.env.example", "backend.env": "backend.env.example", "openmaic.env": "openmaic.env.example"}
    if any((directory / name).exists() for name in targets):
        raise DeployError("init never overwrites existing configuration")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, template in targets.items():
        text = (HERE / "env" / template).read_text()
        if name == "compose.env":
            for key in SECRETS:
                text = text.replace(f"{key}=CHANGE_ME", f"{key}={secrets.token_hex(32)}")
            text = text.replace("/etc/mira/backend.env", str(directory / "backend.env"))
            text = text.replace("/etc/mira/openmaic.env", str(directory / "openmaic.env"))
        bundle.private_write(directory / name, text)
    print("Created private templates. Set your domain, mode, tester CIDRs and Provider configuration; preserve source secrets before migration.")


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--env", type=Path, default=Path("/etc/mira/compose.env"))
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("--config-dir", type=Path, default=Path("/etc/mira"))
    for name in ("check", "build", "prepare", "migrate", "start", "stop", "status", "logs"):
        commands.add_parser(name)
    commands.add_parser("restore").add_argument("bundle", type=Path)
    commands.add_parser("backup").add_argument("output", type=Path)
    args = cli.parse_args(argv)
    try:
        if args.command == "init":
            initialize(args.config_dir)
            return 0
        values = validate(read_private(args.env))
        backend, runtime = validate_runtime(values, starting=args.command == "start")
        prefix, env = compose_prefix(args.env.absolute(), values), command_env(values)
        root = Path(values["MIRA_DATA_ROOT"])
        if args.command == "check":
            # Quiet validation does not expose the resolved secrets.
            run(prefix, env, "config", "--quiet")
            print("Configuration syntax passed. No containers started; DNS, browser flows and Provider credentials remain to be verified.")
            if values["MIRA_DEPLOY_MODE"] == "production":
                print("NOTICE: Production startup is blocked until the real SMS provider integration is completed.")
        elif args.command == "build":
            source = ROOT / "openmaic-runtime/.runtime/OpenMAIC"
            if not (source / "lib/server/mira-internal-loopback-auth.ts").is_file():
                raise DeployError("Prepare the pinned, patched OpenMAIC source with scripts/bootstrap-upstream.sh first")
            run(prefix, env, "build", "backend", "openmaic", "gateway", "student-web")
        elif args.command == "prepare":
            ensure_stopped(prefix, env)
            ensure_empty(root)
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            for directory in ("backend-data", "openmaic-data"):
                (root / directory).mkdir(mode=0o700)
            policy = root / "backend-data" / bundle.POLICY_DESTINATION
            policy.parent.mkdir(mode=0o700)
            bundle.private_write(policy, (ROOT / "backend/content/learning_classroom_policy.json").read_bytes())
            run(prefix, env, "up", "-d", "--wait", "postgres")
            run(prefix, env, "run", "--rm", "storage-init")
            migrate(prefix, env)
            record(root, "empty")
            print("Empty database prepared. Existing courses have not been imported.")
        elif args.command == "restore":
            manifest = bundle.verify(args.bundle)
            version_compatible(values, manifest)
            check_secret_continuity(values, backend, manifest)
            ensure_stopped(prefix, env)
            ensure_empty(root)
            root.parent.mkdir(parents=True, exist_ok=True)
            bundle.restore_files(args.bundle, root)
            run(prefix, env, "up", "-d", "--wait", "postgres")
            # The dump recreates schema app; the fresh one from initialization
            # is empty, and DROP refuses if anything was written to it.
            run(prefix, env, "exec", "-T", "postgres", "sh", "-ec",
                'PGPASSWORD="$POSTGRES_PASSWORD" exec psql --no-psqlrc --set=ON_ERROR_STOP=1 --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="DROP SCHEMA app"',
                capture=True)
            # Restored objects belong to the application login, as in the source.
            run(prefix, env, "exec", "-T", "postgres", "sh", "-ec",
                'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_restore --exit-on-error --no-owner --no-privileges --role=mira --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"',
                input_file=args.bundle / "postgres.dump", capture=True)
            run(prefix, env, "run", "--rm", "storage-init")
            migrate(prefix, env)
            record(root, "restored", manifest)
            print("Database and data directories restored. Applications remain stopped; review migration notes before start.")
        elif args.command == "start":
            validate_prepared(root, values)
            # Namespace sharing requires the four runtime services to be recreated
            # together on deployment; never leave a consumer on an old namespace.
            run(prefix, env, "stop", *WRITERS)
            run(prefix, env, "up", "-d", "--wait", "--force-recreate", *START_SERVICES)
            print("Services started. Complete the browser acceptance steps in deploy/README.md.")
        elif args.command == "migrate":
            validate_prepared(root, values)
            ensure_stopped(prefix, env)
            run(prefix, env, "up", "-d", "--wait", "postgres")
            migrate(prefix, env)
            print("Schema migrations completed. Application services remain stopped.")
        elif args.command == "stop":
            run(prefix, env, "stop", *WRITERS)
            print("Application writers stopped. The database remains running for backup; data was not deleted.")
        elif args.command == "status":
            run(prefix, env, "ps", "--all")
        elif args.command == "logs":
            run(prefix, env, "logs", "--tail", "100", "backend", "gateway", "openmaic", "student-web", "edge")
        else:
            from server_backup import export_server
            result = export_server(values, prefix, env, args.output)
            print(json.dumps(result, indent=2))
        return 0
    except (DeployError, bundle.BundleError, OSError) as error:
        message = str(error) if isinstance(error, (DeployError, bundle.BundleError)) else "Filesystem operation failed; check permissions, paths and free space"
        print("ERROR: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
