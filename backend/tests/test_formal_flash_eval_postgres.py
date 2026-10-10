"""Essential lifecycle guards, with no PostgreSQL process or socket started."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shlex
from tempfile import TemporaryDirectory
import unittest

from scripts.formal_flash_eval_postgres import (
    BASE, PORT, LifecycleError, Paths, PostgresOperator,
)


class FakePostgres:
    def __init__(self, paths):
        self.paths = paths
        self.calls = []
        self.listening = set()
        self.process = None

    def run(self, argv, **options):
        argv = [str(arg) for arg in argv]
        self.calls.append(argv)
        p = self.paths
        name = Path(argv[0]).name
        if name == "initdb":
            p.cluster.mkdir(mode=0o700)
            for file, text in (("PG_VERSION", "16\n"), ("postgresql.conf", "# isolated test\n"), ("pg_hba.conf", "")):
                target = p.cluster / file
                target.write_text(text)
                target.chmod(0o600)
        elif name == "pg_ctl" and argv[-1] == "start":
            command = shlex.join([str(p.bin / "postgres"), "-D", str(p.cluster), "-h", "127.0.0.1", "-p", str(p.port), "-k", str(p.socket)])
            self.process = {"pid": 12345, "startIdentity": "Thu Oct  8 12:00:00 2026", "cwd": str(p.cluster),
                            "command": command, "commandSha256": hashlib.sha256(command.encode()).hexdigest()}
            self.listening = {12345}
            pidfile = p.cluster / "postmaster.pid"
            pidfile.write_text(f"12345\n{p.cluster}\n1791432000\n{p.port}\n{p.socket}\n127.0.0.1\n0 0\nready\n")
            pidfile.chmod(0o600)
        elif name == "pg_ctl" and argv[-1] == "stop":
            (p.cluster / "postmaster.pid").unlink()
            self.listening.clear()
            self.process = None
        return None

    def inspect(self, pid):
        if not self.process:
            raise LifecycleError("process_identity_unavailable")
        return deepcopy(self.process)


class FormalPostgresGuardTests(unittest.TestCase):
    def setUp(self):
        # macOS /tmp and /var are symlinks; keep the production no-symlink
        # ancestor guard intact instead of disabling it for isolated tests.
        self.directory = TemporaryDirectory(prefix="formal-pg-guard-", dir="/private/tmp")
        self.addCleanup(self.directory.cleanup)
        base = Path(self.directory.name)
        binary = base / "bin"
        binary.mkdir()
        for name in ("initdb", "pg_ctl", "createdb", "postgres"):
            path = binary / name
            path.write_text("unused offline placeholder")
            path.chmod(0o700)
        self.paths = Paths(base / "eval", binary, socket_path=base / "socket")
        self.fake = FakePostgres(self.paths)
        self.operator = PostgresOperator(self.paths, run=self.fake.run, inspect_process=self.fake.inspect,
            listeners=lambda port: set(self.fake.listening), clock=lambda: 1791432000)

    def test_default_scope_v2_and_preflight_starts_nothing(self):
        self.assertIn("20261008-flash-formal-v2", str(BASE))
        self.assertEqual(PORT, 55482)
        self.assertLess(len(str(Paths().socket / ".s.PGSQL.55482").encode()), 104)
        before = self.operator.preflight()
        self.assertTrue(before["freshInitializationAvailable"])
        self.assertEqual(self.fake.calls, [])
        self.assertFalse(self.paths.base.exists())

    def test_fresh_initialization_private_secrets_and_no_reinitialization(self):
        result = self.operator.initialize()
        password = self.paths.password.read_text().strip()
        public = json.dumps(result)
        self.assertNotIn(password, public)
        self.assertNotIn(password, json.dumps(self.fake.calls))
        self.assertNotIn(password, self.paths.manifest.read_text())
        env = json.loads(self.paths.launch_env.read_text())
        self.assertEqual(env["DATABASE_URL"], env["MIRA_OPENMAIC_AGENT_DATABASE_URL"])
        self.assertIn("127.0.0.1:55482/mira_formal_flash_eval", env["DATABASE_URL"])
        for path in (self.paths.password, self.paths.launch_env, self.paths.manifest, self.paths.log):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.paths.socket.stat().st_mode & 0o777, 0o700)
        self.assertIn("--auth-host=scram-sha-256", self.fake.calls[0])
        self.assertIn("--auth-local=trust", self.fake.calls[0])
        snapshot = self.paths.password.read_bytes()
        with self.assertRaises(LifecycleError): self.operator.initialize()
        self.assertEqual(self.paths.password.read_bytes(), snapshot)
        self.assertEqual(len(self.fake.calls), 1)

    def test_existing_cluster_or_symlink_cannot_be_initialized(self):
        self.paths.base.mkdir()
        self.paths.cluster.mkdir()
        (self.paths.cluster / "existing.txt").write_text("preserve")
        with self.assertRaises(LifecycleError): self.operator.initialize()
        self.assertEqual(self.fake.calls, [])
        self.assertEqual((self.paths.cluster / "existing.txt").read_text(), "preserve")

    def test_owned_start_stop_restart_only_creates_database_once(self):
        self.operator.initialize()
        first = self.operator.start()
        self.assertEqual(first["pid"], 12345)
        self.assertEqual(self.operator.status()["state"], "running")
        self.assertFalse(self.operator.start()["started"])
        self.assertEqual(len([c for c in self.fake.calls if Path(c[0]).name == "createdb"]), 1)
        self.assertTrue(self.operator.stop()["stopped"])
        self.assertFalse(self.operator.stop()["stopped"])
        self.assertTrue(self.operator.start()["started"])
        self.assertEqual(len([c for c in self.fake.calls if Path(c[0]).name == "createdb"]), 1)

    def test_foreign_listener_refuses_start_and_never_kills_by_port(self):
        self.operator.initialize()
        before = len(self.fake.calls)
        self.fake.listening = {9876}
        with self.assertRaises(LifecycleError): self.operator.start()
        with self.assertRaises(LifecycleError): self.operator.stop()
        self.assertEqual(len(self.fake.calls), before)

    def test_changed_pid_cwd_command_or_start_identity_refuses_stop(self):
        self.operator.initialize()
        self.operator.start()
        original = deepcopy(self.fake.process)
        for mutation in (
            lambda p: p.update(pid=54321),
            lambda p: p.update(cwd="/private/tmp/foreign"),
            lambda p: p.update(command=p["command"] + " -h 0.0.0.0"),
            lambda p: p.update(startIdentity="different process after PID reuse"),
        ):
            self.fake.process = deepcopy(original)
            mutation(self.fake.process)
            before = len([c for c in self.fake.calls if c[-1] == "stop"])
            with self.assertRaises(LifecycleError): self.operator.stop()
            self.assertEqual(len([c for c in self.fake.calls if c[-1] == "stop"]), before)
        self.fake.process = original

    def test_manifest_config_and_password_drift_refuse_all_mutations(self):
        self.operator.initialize()
        self.operator.start()
        for path in (self.paths.password, self.paths.cluster / "pg_hba.conf", self.paths.cluster / "postgresql.conf"):
            old = path.read_bytes()
            path.write_bytes(old + b"drift\n")
            before = len(self.fake.calls)
            with self.assertRaises(LifecycleError): self.operator.start()
            with self.assertRaises(LifecycleError): self.operator.stop()
            self.assertEqual(len(self.fake.calls), before)
            path.write_bytes(old)


if __name__ == "__main__":
    unittest.main()
