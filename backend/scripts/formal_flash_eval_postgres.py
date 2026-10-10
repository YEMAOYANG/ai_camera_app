"""Own one fresh PostgreSQL cluster for isolated formal acceptance only.

Default preflight is read-only. init/start/stop are explicit operator actions;
importing this module starts nothing. Existing clusters cannot be initialized,
adopted by another manifest, cleaned, migrated, or stopped by port number.
Passwords never enter argv, command output, or the public status result.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import stat
import subprocess
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "backend/data/homework/course-evals/20261008-flash-formal-v2"
PG_BIN = Path("/opt/homebrew/opt/postgresql@16/bin")
PORT = 55482
ROLE = "mira_formal_eval"
DATABASE = "mira_formal_flash_eval"
SCHEMA = "mira.eval.formal-flash-isolated-postgres.v1"
PRIVATE_SOCKET = Path("/private/tmp") / ("mira-formal-pg-55482-" + hashlib.sha256(str(BASE).encode()).hexdigest()[:16])


class LifecycleError(RuntimeError):
    """Only fixed, credential-free error codes may be printed by main."""


def _require(condition, code):
    if not condition:
        raise LifecycleError(code)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Paths:
    base: Path = BASE
    bin: Path = PG_BIN
    port: int = PORT
    socket_path: Path = PRIVATE_SOCKET

    @property
    def cluster(self): return self.base / "isolated-pg"
    @property
    def socket(self): return self.socket_path
    @property
    def password(self): return self.base / "isolated-pg-password.private"
    @property
    def manifest(self): return self.base / "isolated-pg-lifecycle.private.json"
    @property
    def launch_env(self): return self.base / "isolated-pg-launchenv.private.json"
    @property
    def log(self): return self.base / "isolated-pg-postmaster.private.log"
    @property
    def lock(self): return self.base / "isolated-pg-lifecycle.private.lock"


def _private_owned(path: Path, *, directory=False):
    _require(path.exists() and not path.is_symlink(), "private_path_missing_or_symlink")
    info = path.stat()
    _require(info.st_uid == os.getuid(), "private_path_not_owned")
    _require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "private_path_type_invalid")
    _require(info.st_mode & 0o077 == 0, "private_path_permissions_invalid")


def _no_symlink_ancestors(path: Path):
    for ancestor in (path, *path.parents):
        _require(not ancestor.is_symlink(), "symlink_path_refused")


def _write_private_new(path, value, *, json_value=True):
    raw = (_canonical(value) + "\n").encode() if json_value else value.encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_private_json(path, value):
    _private_owned(path)
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    _write_private_new(temp, value)
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _subprocess(argv, *, cwd, timeout=30, ok=(0,)):
    # No shell and no inherited PG* override, .env loader or provider secret.
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"}
    result = subprocess.run([str(arg) for arg in argv], cwd=str(cwd), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
    _require(result.returncode in ok, "operator_command_failed")
    return result


def _process_identity(pid):
    _require(type(pid) is int and 1 < pid < 2**31, "process_pid_invalid")
    started = _subprocess(["/bin/ps", "-ww", "-p", pid, "-o", "lstart="], cwd=ROOT, timeout=5).stdout.strip()
    command = _subprocess(["/bin/ps", "-ww", "-p", pid, "-o", "command="], cwd=ROOT, timeout=5).stdout.strip()
    output = _subprocess(["/usr/sbin/lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"], cwd=ROOT, timeout=5).stdout
    directories = [line[1:] for line in output.splitlines() if line.startswith("n")]
    _require(started and command and len(directories) == 1, "process_identity_unavailable")
    return {"pid": pid, "startIdentity": started, "cwd": directories[0],
            "command": command, "commandSha256": hashlib.sha256(command.encode()).hexdigest()}


def _port_listener_pids(port):
    result = _subprocess(["/usr/sbin/lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                         cwd=ROOT, timeout=5, ok=(0, 1))
    _require(not result.stderr.strip() and (result.returncode == 0 or not result.stdout.strip()), "listener_inventory_failed")
    _require(all(line.isdigit() for line in result.stdout.splitlines()), "listener_inventory_failed")
    return {int(line) for line in result.stdout.splitlines()}


def _locked_operation(method):
    @wraps(method)
    def guarded(self):
        with self._operation_lock(allow_fresh=method.__name__ == "initialize"):
            return method(self)
    return guarded


class PostgresOperator:
    def __init__(self, paths=Paths(), *, run=_subprocess, inspect_process=_process_identity,
                 listeners=_port_listener_pids, clock=time.time):
        self.paths, self.run, self.inspect_process, self.listeners, self.clock = paths, run, inspect_process, listeners, clock

    @contextmanager
    def _operation_lock(self, *, allow_fresh=False):
        p = self.paths
        _no_symlink_ancestors(p.base)
        if allow_fresh:
            p.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        _require(p.base.is_dir() and p.base.stat().st_uid == os.getuid(), "operator_directory_not_owned")
        fd = os.open(p.lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            _private_owned(p.lock)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def preflight(self):
        p = self.paths
        _require(p.base.is_absolute() and p.bin.is_absolute() and p.port == PORT, "operator_scope_invalid")
        _no_symlink_ancestors(p.base)
        _no_symlink_ancestors(p.socket)
        # macOS sockaddr_un.sun_path is 104 bytes. The long course-evals path
        # cannot safely hold a Unix socket even though it can hold PG data.
        _require(p.socket.is_absolute() and len(os.fsencode(str(p.socket / f".s.PGSQL.{p.port}"))) < 104,
                 "private_socket_path_too_long")
        for executable in ("initdb", "pg_ctl", "createdb", "postgres"):
            target = p.bin / executable
            _require(target.is_file() and os.access(target, os.X_OK), "postgres_binary_unavailable")
        return {"cluster": str(p.cluster), "host": "127.0.0.1", "port": p.port,
                "freshInitializationAvailable": not any(path.exists() or path.is_symlink() for path in
                    (p.cluster, p.socket, p.password, p.manifest, p.launch_env, p.log)),
                "databaseStarts": 0, "paidCalls": 0}

    def _fingerprint(self):
        p = self.paths
        _private_owned(p.cluster, directory=True)
        _private_owned(p.socket, directory=True)
        for path in (p.password, p.launch_env, p.cluster / "PG_VERSION",
                     p.cluster / "pg_hba.conf", p.cluster / "postgresql.conf"):
            _private_owned(path)
        version = p.cluster / "PG_VERSION"
        _require(version.is_file() and version.read_text().strip() == "16", "cluster_version_invalid")
        info = p.cluster.stat()
        return {"cluster": str(p.cluster), "device": info.st_dev, "inode": info.st_ino, "ownerUid": info.st_uid,
                "socket": str(p.socket), "port": p.port, "role": ROLE, "database": DATABASE,
                "postgresBinary": str((p.bin / "postgres").resolve()),
                "passwordSha256": _file_sha(p.password), "launchEnvSha256": _file_sha(p.launch_env),
                "hbaSha256": _file_sha(p.cluster / "pg_hba.conf"),
                "configSha256": _file_sha(p.cluster / "postgresql.conf")}

    def _manifest(self):
        self.preflight()
        p = self.paths
        _private_owned(p.manifest)
        try: value = json.loads(p.manifest.read_text())
        except (ValueError, OSError): raise LifecycleError("manifest_invalid") from None
        _require(isinstance(value, dict) and value.get("schemaVersion") == SCHEMA
                 and value.get("fingerprint") == self._fingerprint(), "cluster_manifest_identity_mismatch")
        return value

    @_locked_operation
    def initialize(self):
        self.preflight()
        p = self.paths
        _require(not any(path.exists() or path.is_symlink() for path in
            (p.cluster, p.socket, p.password, p.manifest, p.launch_env, p.log)), "existing_initialization_refused")
        p.base.mkdir(parents=True, exist_ok=True, mode=0o700)
        _require(p.base.stat().st_uid == os.getuid(), "operator_directory_not_owned")
        password = secrets.token_urlsafe(48)
        _write_private_new(p.password, password + "\n", json_value=False)
        # initdb itself creates the exact fresh data directory; never call it
        # with a directory inherited from another database/operator.
        self.run([p.bin / "initdb", "-D", p.cluster, "--username", ROLE,
                  "--pwfile", p.password, "--auth-local=trust", "--auth-host=scram-sha-256",
                  "--encoding=UTF8", "--locale=C"], cwd=p.base, timeout=60)
        _private_owned(p.cluster, directory=True)
        p.socket.mkdir(mode=0o700)
        config = p.cluster / "postgresql.conf"
        config.write_text(config.read_text() + "\n# Exact formal acceptance operator scope.\n"
            + "listen_addresses = '127.0.0.1'\n" + f"port = {p.port}\n"
            + "unix_socket_directories = '" + str(p.socket).replace("'", "''") + "'\n"
            + "unix_socket_permissions = 0700\npassword_encryption = 'scram-sha-256'\n")
        os.chmod(config, 0o600)
        # localhost TCP authentication is explicit and password based. Only
        # the protected private Unix socket can use trust authentication.
        hba = p.cluster / "pg_hba.conf"
        hba.write_text(f"local all {ROLE} trust\nhost all {ROLE} 127.0.0.1/32 scram-sha-256\n")
        os.chmod(hba, 0o600)
        url = f"postgresql://{ROLE}:{quote(password, safe='')}@127.0.0.1:{p.port}/{DATABASE}"
        _write_private_new(p.launch_env, {"DATABASE_URL": url, "MIRA_OPENMAIC_AGENT_DATABASE_URL": url})
        _write_private_new(p.log, "", json_value=False)
        manifest = {"schemaVersion": SCHEMA, "fingerprint": self._fingerprint(), "initializedAt": int(self.clock()),
                    "databaseCreated": False, "activeProcess": None,
                    "events": [{"operation": "initialized", "at": int(self.clock()), "databaseStarts": 0}]}
        _write_private_new(p.manifest, manifest)
        return {"ok": True, "state": "initialized", "cluster": str(p.cluster),
                "launchEnvPath": str(p.launch_env), "databaseStarts": 0, "paidCalls": 0}

    def _ready_process(self, *, required=True):
        p = self.paths
        pidfile = p.cluster / "postmaster.pid"
        if not pidfile.exists():
            _require(not required, "owned_postmaster_missing")
            return None
        _private_owned(pidfile)
        lines = pidfile.read_text().splitlines()
        _require(len(lines) >= 8 and lines[0].isdigit() and lines[2].isdigit()
                 and lines[1] == str(p.cluster) and lines[3] == str(p.port)
                 and lines[4] == str(p.socket) and lines[5] == "127.0.0.1"
                 and lines[7].strip() == "ready", "postmaster_scope_mismatch")
        pid = int(lines[0])
        process = self.inspect_process(pid)
        _require(process.get("pid") == pid and process.get("cwd") == str(p.cluster), "postmaster_process_mismatch")
        try: command = shlex.split(process["command"])
        except (ValueError, KeyError): raise LifecycleError("postmaster_process_mismatch") from None
        expected = ["-D", str(p.cluster)]
        allowed_tail = ["-h", "127.0.0.1", "-p", str(p.port), "-k", str(p.socket)]
        _require(command and str(Path(command[0]).resolve()) == str((p.bin / "postgres").resolve())
                 and command[1:] in (expected, expected + allowed_tail)
                 and process.get("commandSha256") == hashlib.sha256(process["command"].encode()).hexdigest(),
                 "postmaster_command_mismatch")
        _require(self.listeners(p.port) == {pid}, "postmaster_listener_mismatch")
        self.run([p.bin / "pg_ctl", "-D", p.cluster, "status"], cwd=p.base, timeout=5)
        return {**process, "postmasterStartedAt": int(lines[2])}

    @_locked_operation
    def status(self):
        manifest = self._manifest()
        process = self._ready_process(required=False)
        if process is not None:
            _require(manifest["activeProcess"] == process, "active_process_manifest_mismatch")
        else:
            _require(not self.listeners(self.paths.port), "foreign_listener_refused")
        return {"ok": True, "state": "running" if process else "stopped",
                "pid": process["pid"] if process else None, "databaseCreated": manifest["databaseCreated"],
                "cluster": str(self.paths.cluster), "paidCalls": 0}

    @_locked_operation
    def start(self):
        manifest = self._manifest()
        p = self.paths
        if (p.cluster / "postmaster.pid").exists():
            process = self._ready_process()
            _require(manifest["activeProcess"] == process and manifest["databaseCreated"], "existing_start_not_confirmed")
            return {"ok": True, "state": "running", "pid": process["pid"], "started": False, "paidCalls": 0}
        _require(not self.listeners(p.port), "foreign_listener_refused")
        options = shlex.join(["-h", "127.0.0.1", "-p", str(p.port), "-k", str(p.socket)])
        self.run([p.bin / "pg_ctl", "-D", p.cluster, "-l", p.log, "-w", "-t", "30", "-o", options, "start"], cwd=p.base, timeout=40)
        process = self._ready_process()
        manifest["activeProcess"] = process
        manifest["events"].append({"operation": "started", "at": int(self.clock()), "process": process})
        _atomic_private_json(p.manifest, manifest)
        if not manifest["databaseCreated"]:
            # Only the freshly owned private socket/cluster is contacted. The
            # generated password is never passed to this local trust command.
            self.run([p.bin / "createdb", "--host", p.socket, "--port", str(p.port),
                      "--username", ROLE, "--owner", ROLE, DATABASE], cwd=p.base, timeout=30)
            manifest["databaseCreated"] = True
            manifest["events"].append({"operation": "database_created", "at": int(self.clock())})
            _atomic_private_json(p.manifest, manifest)
        return {"ok": True, "state": "running", "pid": process["pid"], "started": True,
                "launchEnvPath": str(p.launch_env), "paidCalls": 0}

    @_locked_operation
    def stop(self):
        manifest = self._manifest()
        p = self.paths
        process = self._ready_process(required=False)
        if process is None:
            _require(not self.listeners(p.port), "foreign_listener_refused")
            return {"ok": True, "state": "stopped", "stopped": False, "paidCalls": 0}
        _require(manifest["activeProcess"] == process, "active_process_manifest_mismatch")
        self.run([p.bin / "pg_ctl", "-D", p.cluster, "-w", "-t", "30", "-m", "fast", "stop"], cwd=p.base, timeout=40)
        _require(not (p.cluster / "postmaster.pid").exists() and not self.listeners(p.port), "stop_not_confirmed")
        manifest["activeProcess"] = None
        manifest["events"].append({"operation": "stopped", "at": int(self.clock()), "process": process})
        _atomic_private_json(p.manifest, manifest)
        return {"ok": True, "state": "stopped", "stopped": True, "paidCalls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preflight", "init", "start", "status", "stop"], nargs="?", default="preflight")
    args = parser.parse_args(argv)
    operator = PostgresOperator()
    try:
        result = getattr(operator, "initialize" if args.operation == "init" else args.operation)()
        print(_canonical(result))
        return 0
    except LifecycleError as exc:
        print(_canonical({"ok": False, "error": str(exc), "operation": args.operation}))
        return 1
    except (OSError, subprocess.SubprocessError):
        # Do not print stderr, argv/env or a connection string on failure.
        print(_canonical({"ok": False, "error": "isolated_postgres_operation_refused", "operation": args.operation}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
