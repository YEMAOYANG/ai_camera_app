from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_bundle
import server


class ServerDeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.config_dir = self.root / "config"
        with contextlib.redirect_stdout(io.StringIO()):
            server.initialize(self.config_dir)
        self.env_path = self.config_dir / "compose.env"
        self.values = data_bundle.read_env(self.env_path)
        self.values.update({"MIRA_BASE_DOMAIN": "mira-demo.cn", "MIRA_DEPLOY_MODE": "preview",
                            "MIRA_ACCESS_CIDRS": "8.8.8.8/32", "MIRA_DATA_ROOT": str(self.root / "data"),
                            "MIRA_PARENT_WEB_DIST": str(self.root / "web")})
        for key, prefix in zip(server.ORIGINS, ("parent", "learn", "classroom", "api", "realtime")):
            self.values[key] = f"https://{prefix}.mira-demo.cn"
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.env_path.write_text("\n".join(f"{key}='{value}'" for key, value in self.values.items()) + "\n")

    def test_init_is_private_and_never_overwrites(self):
        for path in self.config_dir.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(set(self.values[key] for key in server.SECRETS)), len(server.SECRETS))
        with self.assertRaises(server.DeployError):
            server.initialize(self.config_dir)

    def test_preview_rejects_public_or_private_network_allowlist(self):
        for cidrs in ("0.0.0.0/0 ::/0", "192.168.1.0/24", "8.0.0.0/8", "bad", "8.8.8.8/24"):
            with self.subTest(cidrs=cidrs), self.assertRaises(server.DeployError):
                server.validate({**self.values, "MIRA_ACCESS_CIDRS": cidrs})
        server.validate(self.values)

    def test_https_sibling_origins_and_nonoverlapping_storage(self):
        for value in ("http://learn.mira-demo.cn", "https://learn.other.cn", "https://learn.mira-demo.cn/path",
                      "https://user@learn.mira-demo.cn", "https://learn.mira-demo.cn:443"):
            with self.subTest(value=value), self.assertRaises(server.DeployError):
                server.validate({**self.values, "MIRA_STUDENT_ORIGIN": value})
        with self.assertRaises(server.DeployError):
            server.validate({**self.values, "MIRA_PARENT_WEB_DIST": self.values["MIRA_DATA_ROOT"] + "/web"})

    def test_rejects_unprotected_or_interpolated_env(self):
        self.env_path.chmod(0o644)
        with self.assertRaises(server.DeployError):
            server.read_private(self.env_path)
        self.env_path.chmod(0o600)
        self.env_path.write_text("EVIL=$(touch /tmp/nope)\n")
        with self.assertRaises(data_bundle.BundleError):
            server.read_private(self.env_path)

    def test_compose_profiles_are_not_inherited(self):
        with patch.dict(os.environ, {"COMPOSE_PROFILES": "generation", "MIRA_INTERNAL_API_TOKEN": "wrong"}):
            env = server.command_env(self.values)
        self.assertNotIn("COMPOSE_PROFILES", env)
        self.assertEqual(env["MIRA_INTERNAL_API_TOKEN"], self.values["MIRA_INTERNAL_API_TOKEN"])

    def test_database_versions_and_secret_continuity(self):
        manifest = {"databases": {"postgres": {"serverMajor": 16, "serverVersion": "16.9"}},
                    "secretsToMigrateSeparately": {"backend_env": {"APP_STUDENT_AUTH_PEPPER": {
                        "configured": True, "sha256": hashlib.sha256(self.values["MIRA_STUDENT_AUTH_PEPPER"].encode()).hexdigest()}},
                        "runtime_env": {}}}
        server.version_compatible(self.values, manifest)
        server.check_secret_continuity(self.values, {}, manifest)
        with self.assertRaises(server.DeployError):
            server.version_compatible({**self.values, "MIRA_POSTGRES_IMAGE": "postgres:17-alpine"}, manifest)
        with self.assertRaises(server.DeployError):
            server.check_secret_continuity({**self.values, "MIRA_STUDENT_AUTH_PEPPER": "different"}, {}, manifest)

    def test_generation_flags_cannot_accidentally_resume(self):
        server.validate_runtime(self.values)
        path = Path(self.values["MIRA_BACKEND_ENV_FILE"])
        path.write_text(path.read_text() + "\nLEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED=1\n")
        with self.assertRaises(server.DeployError):
            server.validate_runtime(self.values)

    def test_production_start_requires_real_sms(self):
        web = Path(self.values["MIRA_PARENT_WEB_DIST"])
        web.mkdir()
        (web / "index.html").write_text("demo")
        with self.assertRaisesRegex(server.DeployError, "SMS"):
            server.validate_runtime({**self.values, "MIRA_DEPLOY_MODE": "production"}, starting=True)

    def test_prepare_failure_never_creates_success_marker(self):
        with patch.object(server, "ensure_stopped"), patch.object(server, "run", side_effect=server.DeployError("dump failed")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(server.main(["--env", str(self.env_path), "prepare"]), 1)
        self.assertFalse((Path(self.values["MIRA_DATA_ROOT"]) / server.MARKER).exists())

    def test_prepare_refuses_existing_data_before_docker_writes(self):
        root = Path(self.values["MIRA_DATA_ROOT"])
        root.mkdir()
        original = root / "existing"
        original.write_text("preserve")
        with patch.object(server, "ensure_stopped"), patch.object(server, "run") as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(server.main(["--env", str(self.env_path), "prepare"]), 1)
            run.assert_not_called()
        self.assertEqual(original.read_text(), "preserve")

    def test_stop_keeps_databases_and_start_requires_preparation(self):
        with patch.object(server, "run") as run, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(server.main(["--env", str(self.env_path), "stop"]), 0)
        args = run.call_args.args
        self.assertIn("backend", args)
        self.assertNotIn("postgres", args)
        web = Path(self.values["MIRA_PARENT_WEB_DIST"])
        web.mkdir()
        (web / "index.html").write_text("demo")
        with patch.object(server, "run") as run, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(server.main(["--env", str(self.env_path), "start"]), 1)
            run.assert_not_called()

    def test_secret_bearing_subprocess_stderr_is_suppressed(self):
        result = type("Result", (), {"returncode": 1, "stderr": b"secret-password"})()
        with patch.object(server.subprocess, "run", return_value=result):
            with self.assertRaises(server.DeployError) as caught:
                server.run(["docker", "compose"], {}, "exec", "postgres")
        self.assertNotIn("secret-password", str(caught.exception))

    def test_start_refuses_marker_with_missing_database_storage(self):
        root = Path(self.values["MIRA_DATA_ROOT"])
        root.mkdir()
        server.record(root, "empty")
        with self.assertRaises(server.DeployError):
            server.validate_prepared(root, self.values)

    def test_restore_import_or_migration_failure_never_marks_success(self):
        manifest = {"createdAt": "fixture", "files": {}, "databases": {}}
        for failed_call in (2, 3, 5):
            root = self.root / f"failed-{failed_call}"
            self.values["MIRA_DATA_ROOT"] = str(root)
            self.save()
            calls = []
            def fake_run(prefix, env, *args, **kwargs):
                calls.append(args)
                if len(calls) == failed_call:
                    raise server.DeployError("fixture failure")
            def restore_files(source, target):
                target.mkdir()
            with patch.object(server.bundle, "verify", return_value=manifest), \
                    patch.object(server, "version_compatible"), patch.object(server, "check_secret_continuity"), \
                    patch.object(server, "ensure_stopped"), patch.object(server.bundle, "restore_files", side_effect=restore_files), \
                    patch.object(server, "run", side_effect=fake_run), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(server.main(["--env", str(self.env_path), "restore", str(self.root / "bundle")]), 1)
            self.assertFalse((root / server.MARKER).exists())
            self.assertFalse(any("backend" in args or "openmaic" in args for args in calls))

    def test_restore_replaces_the_empty_app_schema_and_restores_as_the_application_login(self):
        manifest = {"createdAt": "fixture", "files": {}, "databases": {}}
        calls = []
        def fake_run(prefix, env, *args, **kwargs):
            calls.append((args, kwargs))
        def restore_files(source, target):
            target.mkdir()
        with patch.object(server.bundle, "verify", return_value=manifest), \
                patch.object(server, "version_compatible"), patch.object(server, "check_secret_continuity"), \
                patch.object(server, "ensure_stopped"), patch.object(server.bundle, "restore_files", side_effect=restore_files), \
                patch.object(server, "run", side_effect=fake_run), patch.object(server.bundle, "private_write"), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(server.main(["--env", str(self.env_path), "restore", str(self.root / "bundle")]), 0)
        scripts = [args[-1] for args, _ in calls if args[:2] == ("exec", "-T")]
        self.assertIn('--command="DROP SCHEMA app"', scripts[0])
        self.assertIn("pg_restore", scripts[1])
        self.assertIn("--role=mira", scripts[1])
        self.assertEqual(calls[2][1]["input_file"], self.root / "bundle" / "postgres.dump")
        self.assertEqual(calls[0][0], ("up", "-d", "--wait", "postgres"))


if __name__ == "__main__":
    unittest.main()
