"""Migration safety tests using temporary fixtures and fake dump processes only."""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


DEPLOY_DIR = str(Path(__file__).resolve().parents[1])
if DEPLOY_DIR not in sys.path:
    sys.path.insert(0, DEPLOY_DIR)
import data_bundle as bundle
import server_backup


class DataBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.backend = self.repo / "backend"
        self.runtime = self.repo / "openmaic-runtime"
        self.backend_data = self.backend / "data"
        self.openmaic_data = self.runtime / ".runtime/OpenMAIC/data"
        self.backend_data.mkdir(parents=True)
        self.openmaic_data.mkdir(parents=True)
        (self.backend / "content").mkdir()
        self.policy_bytes = b'{"schemaVersion":"mira.learning.budget-policy.v1", "enabled":false}\n'
        (self.backend / "content/learning_budget_policy.json").write_bytes(self.policy_bytes)
        (self.backend / ".env").write_text(
            "APP_DATABASE_URL=postgresql://mira:PG_PRIVATE@localhost:5432/mira\n"
            "APP_STUDENT_AUTH_PEPPER=PEPPER_PRIVATE\nINTERNAL_API_TOKEN=TOKEN_PRIVATE\n")
        (self.runtime / ".env").write_text("MIRA_OPENMAIC_AGENT_DATABASE_URL=postgresql://mira:PG_PRIVATE@127.0.0.1:5432/mira\n")
        (self.backend_data / ".device-secret.key").write_bytes(b"DEVICE_PRIVATE")
        (self.backend_data / "learning-media").mkdir()
        (self.backend_data / "learning-media/lesson.mp3").write_bytes(b"audio fixture")
        (self.openmaic_data / "formal-audio/jobs/tts").mkdir(parents=True)
        (self.openmaic_data / "formal-audio/jobs/tts/existing.json").write_bytes(b'{"status":"ambiguous","courseId":"keep-me"}')
        self.output = self.root / "bundle"
        self.args = bundle.parser().parse_args(["export-local", "--repo-root", str(self.repo),
                                                "--output", str(self.output), "--services-stopped"])

    def fake_process(self, command, *, stdout, stderr, stdin, env, check):
        self.assertEqual(stdin, subprocess.DEVNULL)
        for secret in ("PG_PRIVATE", "PEPPER_PRIVATE", "DEVICE_PRIVATE"):
            self.assertNotIn(secret, " ".join(command))
            self.assertNotIn(secret, str(env))
        if command[0] == "pg_dump":
            password_file = Path(env["PGPASSFILE"])
            self.assertEqual(password_file.stat().st_mode & 0o777, 0o600)
            self.assertIn("PG_PRIVATE", password_file.read_text())
            self.assertEqual(Path(env["PGSERVICEFILE"]).stat().st_mode & 0o777, 0o600)
            stdout.write(b"PGDMP fixture")
            return subprocess.CompletedProcess(command, 0)
        self.assertEqual(command[0], "pg_restore")
        self.assertEqual(command[1], "--list")
        return subprocess.CompletedProcess(command, 0, stdout=b"; Dumped from database version: 16.9\n")

    def export(self):
        with patch.object(bundle.subprocess, "run", side_effect=self.fake_process):
            return bundle.export_local(self.args)

    def update_checksum(self, filename):
        path = self.output / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["files"][filename] = {"sha256": bundle.sha256(self.output / filename),
                                       "bytes": (self.output / filename).stat().st_size}
        path.write_text(json.dumps(manifest))

    def test_roundtrip_preserves_audio_ambiguous_jobs_device_key_policy_and_db_versions(self):
        self.export()
        manifest = bundle.verify(self.output)
        self.assertEqual(set(manifest["databases"]), {"postgres"})
        self.assertEqual(manifest["databases"]["postgres"]["serverVersion"], "16.9")
        self.assertEqual(manifest["databases"]["postgres"]["database"], "mira")
        self.assertEqual(manifest["databases"]["postgres"]["schemas"], ["app", "public"])
        target = self.root / "restored"
        result = bundle.restore_files(self.output, target)
        self.assertFalse(result["databasesRestored"])
        for root, destination in ((self.backend_data, "backend-data"), (self.openmaic_data, "openmaic-data")):
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.read_bytes(), (target / destination / path.relative_to(root)).read_bytes())
        self.assertEqual((target / "backend-data" / bundle.POLICY_DESTINATION).read_bytes(), self.policy_bytes)
        manifest_text = (self.output / "manifest.json").read_text()
        for secret in ("PG_PRIVATE", "PEPPER_PRIVATE", "TOKEN_PRIVATE", "DEVICE_PRIVATE"):
            self.assertNotIn(secret, manifest_text)
        self.assertEqual((self.output / "postgres.dump").stat().st_mode & 0o777, 0o600)

    def test_export_refuses_a_classroom_runtime_on_another_database(self):
        (self.runtime / ".env").write_text("MIRA_OPENMAIC_AGENT_DATABASE_URL=postgresql://mira:PG_PRIVATE@localhost:5432/openmaic\n")
        with patch.object(bundle.subprocess, "run") as run:
            with self.assertRaisesRegex(bundle.BundleError, "same database") as error:
                bundle.export_local(self.args)
        run.assert_not_called()
        self.assertNotIn("PG_PRIVATE", str(error.exception))
        self.assertFalse((self.output / "manifest.json").exists())

    def test_export_refuses_a_legacy_mysql_backend_url(self):
        with (self.backend / ".env").open("a") as stream:
            stream.write("APP_DATABASE_URL=mysql+pymysql://mira:MYSQL_PRIVATE@localhost:3306/mira\n")
        with patch.object(bundle.subprocess, "run") as run:
            with self.assertRaisesRegex(bundle.BundleError, "postgresql://") as error:
                bundle.export_local(self.args)
        run.assert_not_called()
        self.assertNotIn("MYSQL_PRIVATE", str(error.exception))

    def test_export_requires_writer_stop_acknowledgement_before_touching_output(self):
        self.args.services_stopped = False
        with self.assertRaisesRegex(bundle.BundleError, "Stop all"):
            bundle.export_local(self.args)
        self.assertFalse(self.output.exists())

    def test_failed_database_dump_has_no_completed_manifest_and_no_credentials_in_error(self):
        def failure(command, **kwargs):
            kwargs["stdout"].write(b"partial")
            return subprocess.CompletedProcess(command, 7, stderr=b"password PG_PRIVATE")
        with patch.object(bundle.subprocess, "run", side_effect=failure):
            with self.assertRaisesRegex(bundle.BundleError, "exit 7") as error:
                bundle.export_local(self.args)
        self.assertNotIn("PG_PRIVATE", str(error.exception))
        self.assertFalse((self.output / "manifest.json").exists())
        with self.assertRaisesRegex(bundle.BundleError, "No completed manifest"):
            bundle.verify(self.output)

    def test_tampered_dump_refused_before_creating_restore_directory(self):
        self.export()
        (self.output / "postgres.dump").write_bytes(b"tampered")
        target = self.root / "restore"
        with self.assertRaisesRegex(bundle.BundleError, "Checksum"):
            bundle.restore_files(self.output, target)
        self.assertFalse(target.exists())

    def test_path_traversal_rejected_even_with_matching_checksums(self):
        self.export()
        with tarfile.open(self.output / "backend-data.tar", "w") as archive:
            member = tarfile.TarInfo("../escaped")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        self.update_checksum("backend-data.tar")
        with self.assertRaisesRegex(bundle.BundleError, "Unsafe archive"):
            bundle.verify(self.output)

    def test_symlink_and_hardlink_archives_rejected(self):
        self.export()
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with self.subTest(kind=kind):
                with tarfile.open(self.output / "backend-data.tar", "w") as archive:
                    member = tarfile.TarInfo("evil")
                    member.type = kind
                    member.linkname = "/etc/passwd"
                    archive.addfile(member)
                self.update_checksum("backend-data.tar")
                with self.assertRaisesRegex(bundle.BundleError, "Unsafe archive"):
                    bundle.verify(self.output)

    def test_restore_never_overwrites_an_existing_target(self):
        self.export()
        target = self.root / "restore"
        target.mkdir()
        (target / "precious").write_bytes(b"keep")
        with self.assertRaisesRegex(bundle.BundleError, "refusing to overwrite"):
            bundle.restore_files(self.output, target)
        self.assertEqual((target / "precious").read_bytes(), b"keep")

    def test_source_symlink_rejected_before_any_dump(self):
        (self.backend_data / "linked").symlink_to(self.backend / ".env")
        with patch.object(bundle.subprocess, "run") as run:
            with self.assertRaisesRegex(bundle.BundleError, "symlink"):
                bundle.export_local(self.args)
        run.assert_not_called()

    def test_custom_media_path_fails_instead_of_silent_incomplete_backup(self):
        with (self.backend / ".env").open("a") as stream:
            stream.write("LEARNING_MEDIA_STORAGE_ROOT=/custom/media\n")
        with self.assertRaisesRegex(bundle.BundleError, "Custom LEARNING_MEDIA_STORAGE_ROOT"):
            bundle.export_local(self.args)

    def test_dotenv_is_literal_and_never_executes_substitution(self):
        path = self.root / "literal.env"
        path.write_text("export KEY='$(touch never)'\nOTHER=hello # comment\n")
        self.assertEqual(bundle.read_env(path), {"KEY": "$(touch never)", "OTHER": "hello"})
        with self.assertRaisesRegex(bundle.BundleError, "literal"):
            bundle.literal(bundle.read_env(path)["KEY"], "KEY")
        self.assertFalse((self.root / "never").exists())

    def test_policy_override_preserves_exact_bytes(self):
        policy = self.root / "actual-policy.json"
        body = b'{ "schemaVersion": "mira.learning.budget-policy.v1", "enabled": true }\n'
        policy.write_bytes(body)
        self.args.budget_policy = policy
        self.export()
        self.assertEqual((self.output / "learning-budget-policy.json").read_bytes(), body)

    def test_missing_database_version_prevents_completed_bundle(self):
        def no_version(command, **kwargs):
            if command[0] == "pg_restore":
                return subprocess.CompletedProcess(command, 0, stdout=b"no source version")
            return self.fake_process(command, **kwargs)
        with patch.object(bundle.subprocess, "run", side_effect=no_version):
            with self.assertRaisesRegex(bundle.BundleError, "source database version"):
                bundle.export_local(self.args)
        self.assertFalse((self.output / "manifest.json").exists())

    def server_fixture(self):
        root = self.root / "server-data"
        root.mkdir()
        shutil.copytree(self.backend_data, root / "backend-data")
        shutil.copytree(self.openmaic_data, root / "openmaic-data")
        policy = root / "backend-data" / bundle.POLICY_DESTINATION
        policy.parent.mkdir()
        policy.write_bytes(self.policy_bytes)
        return {"MIRA_DATA_ROOT": str(root), "MIRA_BACKEND_ENV_FILE": str(self.backend / ".env"),
                "MIRA_STUDENT_AUTH_PEPPER": "SERVER_PRIVATE_PEPPER", "MIRA_INTERNAL_API_TOKEN": "SERVER_PRIVATE_TOKEN",
                "MIRA_PERSISTENCE_TOKEN": "SERVER_PRIVATE_PERSISTENCE"}

    def fake_server_process(self, command, *, stdin, stdout, stderr, env, check):
        for secret in ("SERVER_PRIVATE_PEPPER", "SERVER_PRIVATE_TOKEN", "SERVER_PRIVATE_PERSISTENCE"):
            self.assertNotIn(secret, " ".join(command))
        if "ps" in command:
            return subprocess.CompletedProcess(command, 0, stdout=b"postgres\n")
        if "pg_restore" in command:
            self.assertEqual(stdin.read(), b"PGDMP server fixture")
            return subprocess.CompletedProcess(command, 0, stdout=b"; Dumped from database version: 16.9\n")
        self.assertIn('PGPASSWORD="$POSTGRES_PASSWORD"', command[-1])
        self.assertIn("pg_dump", command[-1])
        stdout.write(b"PGDMP server fixture")
        return subprocess.CompletedProcess(command, 0)

    def test_server_backup_roundtrip_uses_containers_and_compatible_manifest(self):
        config = self.server_fixture()
        with patch.object(server_backup.subprocess, "run", side_effect=self.fake_server_process) as calls:
            result = server_backup.export_server(config, ["docker", "compose"], {}, self.output)
        self.assertTrue(result["verified"])
        manifest = bundle.verify(self.output)
        self.assertEqual(set(manifest["databases"]), {"postgres"})
        self.assertEqual(manifest["databases"]["postgres"]["serverMajor"], 16)
        self.assertEqual(manifest["databases"]["postgres"]["database"], "mira")
        self.assertEqual(sum("ps" in call.args[0] for call in calls.call_args_list), 2)
        target = self.root / "restored-server"
        bundle.restore_files(self.output, target)
        self.assertEqual((target / "backend-data" / bundle.POLICY_DESTINATION).read_bytes(), self.policy_bytes)
        for secret in ("SERVER_PRIVATE_PEPPER", "SERVER_PRIVATE_TOKEN", "SERVER_PRIVATE_PERSISTENCE"):
            self.assertNotIn(secret, (self.output / "manifest.json").read_text())
        self.assertTrue(manifest["secretsToMigrateSeparately"]["backend_env"]["APP_STUDENT_AUTH_PEPPER"]["configured"])

    def test_server_backup_refuses_running_writer_before_creating_output(self):
        config = self.server_fixture()
        with patch.object(server_backup.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=b"postgres\nbackend\n")):
            with self.assertRaisesRegex(bundle.BundleError, "every application"):
                server_backup.export_server(config, ["docker", "compose"], {}, self.output)
        self.assertFalse(self.output.exists())

    def test_server_dump_failure_does_not_leave_completed_manifest_or_echo_secret(self):
        config = self.server_fixture()
        def fail_dump(command, **kwargs):
            if "pg_dump" in command[-1]:
                return subprocess.CompletedProcess(command, 1, stderr=b"password SERVER_PRIVATE_TOKEN")
            return self.fake_server_process(command, **kwargs)
        with patch.object(server_backup.subprocess, "run", side_effect=fail_dump):
            with self.assertRaisesRegex(bundle.BundleError, "postgres dump failed") as error:
                server_backup.export_server(config, ["docker", "compose"], {}, self.output)
        self.assertNotIn("SERVER_PRIVATE_TOKEN", str(error.exception))
        self.assertFalse((self.output / "manifest.json").exists())

    def test_server_backup_rechecks_writers_before_completing(self):
        config = self.server_fixture()
        checks = 0
        def writer_started(command, **kwargs):
            nonlocal checks
            if "ps" in command:
                checks += 1
                if checks == 2:
                    return subprocess.CompletedProcess(command, 0, stdout=b"postgres\ncurriculum-worker\n")
            return self.fake_server_process(command, **kwargs)
        with patch.object(server_backup.subprocess, "run", side_effect=writer_started):
            with self.assertRaisesRegex(bundle.BundleError, "every application"):
                server_backup.export_server(config, ["docker", "compose"], {}, self.output)
        self.assertFalse((self.output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
