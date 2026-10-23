import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
import warnings
from unittest import mock
import zipfile


MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "courseware_backup.py"
SPEC = importlib.util.spec_from_file_location("mira_courseware_backup", MODULE_PATH)
backup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backup
SPEC.loader.exec_module(backup)


class CoursewareBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="backup-fixture-", dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.base = Path(self.temporary.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()
        self.put("output/lesson/original.json", b'{"lesson":"original","audio":"voice.wav"}\n')
        self.put("output/lesson/voice.wav", b"RIFF" + bytes(range(256)) * 40)
        self.put("output/history/voice-copy.wav", (self.project / "output/lesson/voice.wav").read_bytes())
        (self.project / "output/empty").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def put(self, relative, content):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def make_backup(self, name="backup"):
        plan = backup.build_plan(self.project, ["output"])
        destination = self.base / name
        receipt = backup.create_backup(plan, destination)
        return plan, destination, destination / backup.ARCHIVE_NAME, receipt

    def rewritten(self, source, mutate_index=None, corrupt_object=False, extra=None):
        target = self.base / ("rewritten-%s.zip" % len(list(self.base.glob("rewritten*"))))
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
                target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as changed:
            for info in original.infolist():
                data = original.read(info.filename)
                if info.filename == backup.INDEX_NAME and mutate_index:
                    value = json.loads(data)
                    mutate_index(value)
                    data = backup._json_bytes(value)
                if corrupt_object and info.filename.startswith("objects/"):
                    data = bytes([data[0] ^ 1]) + data[1:] if data else b"wrong"
                    corrupt_object = False
                changed.writestr(info.filename, data)
            if extra:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    changed.writestr(extra, b"unexpected")
        return target

    def test_deduplicated_zip_restores_paths_bytes_empty_dirs_and_metadata(self):
        source = self.project / "output/lesson/original.json"
        os.chmod(source, 0o640)
        os.utime(source, ns=(1700000000123456789, 1700000000123456789))
        plan, directory, archive, receipt = self.make_backup()
        self.assertEqual(3, len(plan.index["files"]))
        self.assertEqual(2, len(plan.index["objects"]))
        self.assertLessEqual(archive.stat().st_size, plan.zip_upper_bound)
        self.assertEqual(archive.stat().st_size, receipt["byteSize"])
        backup.verify_backup(archive)
        restored = self.base / "restored"
        result = backup.restore_backup(archive, restored)
        self.assertEqual(3, result["restoredFiles"])
        for record in plan.index["files"]:
            self.assertEqual((self.project / record["path"]).read_bytes(),
                             (restored / record["path"]).read_bytes())
        self.assertTrue((restored / "output/empty").is_dir())
        self.assertEqual(0o640, (restored / "output/lesson/original.json").stat().st_mode & 0o777)
        self.assertEqual(source.stat().st_mtime_ns,
                         (restored / "output/lesson/original.json").stat().st_mtime_ns)
        self.assertTrue(source.is_file())

    def test_embedded_stdlib_recovery_works_without_project_and_selects_roots(self):
        _, directory, archive, _ = self.make_backup()
        independent = self.base / "external-disk"
        shutil.copytree(directory, independent)
        self.project.rename(self.base / "unavailable-original")
        with zipfile.ZipFile(independent / archive.name) as packaged:
            (independent / "restore.py").write_bytes(packaged.read("restore.py"))
        command = [sys.executable, "-B", str(independent / "restore.py")]
        verified = subprocess.run(command + ["verify", "--archive", str(independent / archive.name)],
                                  cwd=str(independent), capture_output=True, text=True)
        self.assertEqual(0, verified.returncode, verified.stderr)
        verify_only = subprocess.run(command + ["restore", "--verify-only", "--archive", str(independent / archive.name)],
                                     cwd=str(independent), capture_output=True, text=True)
        self.assertEqual(0, verify_only.returncode, verify_only.stderr)
        destination = self.base / "selected-recovery"
        restored = subprocess.run(command + ["restore", "--archive", str(independent / archive.name),
                                             "--destination", str(destination), "--root", "output/lesson"],
                                  cwd=str(independent), capture_output=True, text=True)
        self.assertEqual(0, restored.returncode, restored.stderr)
        self.assertTrue((destination / "output/lesson/voice.wav").is_file())
        self.assertFalse((destination / "output/history").exists())

    def test_paid_claims_nonempty_locks_sql_and_licenses_are_preserved(self):
        self.put("output/paid/request.claim", b'{"paidRequestId":"frozen-id"}')
        self.put("output/paid/request.lock", b'{"owner":"authoring-job"}')
        self.put("output/paid/LICENSE", b"original license")
        self.put("output/lesson/source.sql", b"not a database dump; course source")
        self.put("output/paid/worker.lock", b"")
        self.put("output/private/.env.local", b"fixture-secret-do-not-archive")
        for path in backup.EXCLUDED_DATABASE_PATHS:
            self.put(path, b"fixture database")
        plan = backup.build_plan(self.project, ["output"])
        paths = {x["path"] for x in plan.index["files"]}
        self.assertTrue({"output/paid/request.claim", "output/paid/request.lock",
                         "output/paid/LICENSE", "output/lesson/source.sql"}.issubset(paths))
        exclusions = {x["path"] for x in plan.index["excluded"]}
        self.assertTrue(backup.EXCLUDED_DATABASE_PATHS.issubset(exclusions))
        self.assertIn("output/paid/worker.lock", exclusions)
        self.assertIn("output/private/.env.local", exclusions)

    def test_recorded_links_are_not_followed_and_restore_refuses_before_writing(self):
        (self.project / "output/link").symlink_to(self.base / "outside")
        plan, _, archive, _ = self.make_backup()
        self.assertEqual(str(self.base / "outside"), plan.index["symlinks"][0]["target"])
        destination = self.base / "refused"
        with self.assertRaisesRegex(backup.BackupError, "recorded_symlinks_refused"):
            backup.restore_backup(archive, destination)
        self.assertFalse(destination.exists())
        result = backup.restore_backup(archive, destination, skip_links=True)
        self.assertEqual(["output/link"], result["skippedLinks"])
        self.assertFalse((destination / "output/link").exists())

    def test_only_three_exact_runtime_code_links_are_explicitly_excluded(self):
        for relative, target in backup.EXCLUDED_RUNTIME_LINK_TARGETS.items():
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(self.project / target, target_is_directory=True)
        plan = backup.build_plan(self.project, ["output"])
        exclusions = {x["path"]: x for x in plan.index["excluded"]}
        self.assertFalse(plan.index["symlinks"])
        for relative, target in backup.EXCLUDED_RUNTIME_LINK_TARGETS.items():
            self.assertEqual(str(self.project / target), exclusions[relative]["linkTarget"])
            self.assertEqual("verified_operator_staging_runtime_code_link", exclusions[relative]["reason"])
        changed = next(iter(backup.EXCLUDED_RUNTIME_LINK_TARGETS))
        path = self.project / changed
        path.unlink()
        path.symlink_to(self.base / "different-target", target_is_directory=True)
        changed_plan = backup.build_plan(self.project, ["output"])
        self.assertEqual([changed], [x["path"] for x in changed_plan.index["symlinks"]])

    def test_restore_does_not_overwrite_or_follow_destination_links(self):
        _, _, archive, _ = self.make_backup()
        destination = self.base / "existing"
        existing = destination / "output/lesson/original.json"
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"keep me")
        with self.assertRaisesRegex(backup.BackupError, "restore_would_overwrite"):
            backup.restore_backup(archive, destination)
        self.assertEqual(b"keep me", existing.read_bytes())
        linked = self.base / "linked"
        linked.mkdir()
        (linked / "output").symlink_to(self.base / "outside", target_is_directory=True)
        with self.assertRaises(backup.BackupError):
            backup.restore_backup(archive, linked)
        self.assertFalse((self.base / "outside").exists())

    def test_source_change_keeps_partial_and_diagnostic_without_final_archive(self):
        plan = backup.build_plan(self.project, ["output"])
        original_write = backup._write_archive

        def changing_write(current_plan, path, progress=None):
            original_write(current_plan, path, progress)
            (self.project / "output/lesson/original.json").write_bytes(b"changed source")

        destination = self.base / "changed-backup"
        with mock.patch.object(backup, "_write_archive", side_effect=changing_write):
            with self.assertRaisesRegex(backup.BackupError, "source_changed"):
                backup.create_backup(plan, destination)
        self.assertFalse((destination / backup.ARCHIVE_NAME).exists())
        self.assertTrue((destination / (backup.ARCHIVE_NAME + ".part")).is_file())
        self.assertTrue((destination / "backup-failure.json").is_file())
        self.assertEqual(b"changed source", (self.project / "output/lesson/original.json").read_bytes())

    def test_space_preflight_does_not_create_destination(self):
        plan = backup.build_plan(self.project, ["output"])
        destination = self.base / "no-space"
        with mock.patch.object(backup, "available_bytes", return_value=plan.zip_upper_bound + backup.RESERVE_BYTES - 1):
            with self.assertRaisesRegex(backup.BackupError, "insufficient_space"):
                backup.create_backup(plan, destination)
        self.assertFalse(destination.exists())

    def test_corrupt_objects_missing_objects_and_unsafe_paths_are_rejected(self):
        _, _, archive, _ = self.make_backup()
        bad = self.rewritten(archive, corrupt_object=True)
        with self.assertRaises(backup.BackupError):
            backup.verify_backup(bad)
        for unsafe in ("../escape", "/absolute", "output/../escape", "C:/escape"):
            bad = self.rewritten(archive, mutate_index=lambda index: index["files"][0].update(path=unsafe))
            with self.assertRaises(backup.BackupError):
                backup.restore_backup(bad, self.base / "must-not-create")
        bad = self.rewritten(archive, mutate_index=lambda index: index["objects"].pop(next(iter(index["objects"]))))
        with self.assertRaises(backup.BackupError):
            backup.verify_backup(bad)
        bad = self.rewritten(archive, extra="../outside")
        with self.assertRaises(backup.BackupError):
            backup.verify_backup(bad)
        self.assertFalse((self.base / "must-not-create").exists())

    def test_duplicate_zip_members_and_link_members_are_rejected(self):
        _, _, archive, _ = self.make_backup()
        bad = self.rewritten(archive, extra=backup.INDEX_NAME)
        with self.assertRaises(backup.BackupError):
            backup.verify_backup(bad)
        bad = self.base / "linked-member.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(bad, "w") as target:
            for info in source.infolist():
                if info.filename.startswith("objects/"):
                    info.external_attr = 0o120777 << 16
                target.writestr(info, source.read(info.filename))
        with self.assertRaisesRegex(backup.BackupError, "linked_special"):
            backup.verify_backup(bad)

    def test_corrupted_deflate_stream_fails_crc_or_hash_verification(self):
        _, _, archive, _ = self.make_backup()
        with zipfile.ZipFile(archive) as source:
            member = next(info for info in source.infolist() if info.filename.startswith("objects/"))
        data = bytearray(archive.read_bytes())
        name_size, extra_size = struct.unpack("<HH", data[member.header_offset + 26:member.header_offset + 30])
        position = member.header_offset + 30 + name_size + extra_size + member.compress_size // 2
        data[position] ^= 1
        bad = self.base / "corrupt-deflate.zip"
        bad.write_bytes(data)
        with self.assertRaises(backup.BackupError):
            backup.verify_backup(bad)

    @unittest.skipUnless(sys.platform == "darwin", "requires native clonefile; no copy fallback")
    def test_existing_tar_sidecar_clone_is_self_contained_and_tampering_fails(self):
        original = self.put("output/course-data-snapshots/old/course-assets.tar.gz", b"fixture compressed bytes")
        plan, directory, archive, _ = self.make_backup()
        self.assertEqual(1, len(plan.index["sidecars"]))
        record = plan.index["sidecars"][0]
        cloned = directory / record["backupPath"]
        self.assertNotEqual(original.stat().st_ino, cloned.stat().st_ino)
        self.assertEqual(original.read_bytes(), cloned.read_bytes())
        original.write_bytes(b"original changes after completed backup")
        backup.verify_backup(archive)
        restored = self.base / "sidecar-recovery"
        backup.restore_backup(archive, restored)
        self.assertEqual(b"fixture compressed bytes", (restored / record["path"]).read_bytes())
        cloned.write_bytes(b"corrupt sidecar")
        with self.assertRaisesRegex(backup.BackupError, "sidecar_hash_mismatch"):
            backup.verify_backup(archive)

    def test_sidecar_clone_failure_has_no_ordinary_copy_fallback(self):
        self.put("output/course-data-snapshots/old/course-assets.tar.gz", b"fixture compressed bytes")
        plan = backup.build_plan(self.project, ["output"])
        destination = self.base / "clone-fails"
        with mock.patch.object(backup, "_clone_file", side_effect=backup.BackupError("sidecar_clone_failed")):
            with self.assertRaisesRegex(backup.BackupError, "sidecar_clone_failed"):
                backup.create_backup(plan, destination)
        self.assertFalse((destination / backup.ARCHIVE_NAME).exists())
        self.assertTrue((destination / "backup-failure.json").is_file())
        self.assertTrue((self.project / "output/course-data-snapshots/old/course-assets.tar.gz").is_file())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFO support")
    def test_special_source_and_escaping_roots_are_rejected(self):
        with self.assertRaises(backup.BackupError):
            backup.build_plan(self.project, ["../escape"])
        os.mkfifo(str(self.project / "output/not-a-regular-file"))
        with self.assertRaisesRegex(backup.BackupError, "special_file_forbidden"):
            backup.build_plan(self.project, ["output"])


if __name__ == "__main__":
    unittest.main()
