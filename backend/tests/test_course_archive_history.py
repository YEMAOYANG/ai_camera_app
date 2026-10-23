"""Historical source identity and exact byte versions must remain distinct."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from services.course_archive_exporter import CourseArchiveError, CourseArchiveExporter
from services.course_archive_history import (
    AUTHORING_ROOT, discover_authoring_history, export_authoring_history, seed_authoring_history,
)
from services.course_archive_queue import CourseArchiveQueue, storage_identity


class CourseArchiveHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.owner = self.root / AUTHORING_ROOT / "compiled-v1/candidates" / ("a" * 64)
        self.owner.mkdir(parents=True)
        self.source = self.owner / "classroom.json"
        self.room = {"id": "stage-historical", "stage": {"id": "stage-historical", "name": "旧原稿"},
            "scenes": [{"id": "scene-one", "stageId": "stage-historical", "type": "slide",
                        "content": {"elements": []}}]}
        self.raw = (json.dumps(self.room, ensure_ascii=False, indent=2) + "\n").encode()
        self.source.write_bytes(self.raw)
        self.plan = self.owner / "plan.json"
        self.plan.write_bytes(b'{"goal":"retained first teaching plan"}\n')
        self.exporter = CourseArchiveExporter(project_root=self.root,
            standard_asset_resolver=lambda document, **kwargs: {"entries": [], "unresolved": []},
            material_inventory_loader=lambda request: {"schemaVersion": "mira.course-material-inventory.v1",
                "materials": [], "dependencySha256": hashlib.sha256(b"[]").hexdigest()})

    def discover(self, **kwargs):
        return discover_authoring_history(self.root, paths=[self.source], **kwargs)

    def test_same_stage_different_original_bytes_are_separate_queued_versions(self):
        first = self.discover()["events"][0]
        compact = json.dumps(self.room, ensure_ascii=False, separators=(",", ":")).encode()
        self.source.write_bytes(compact)
        second = self.discover()["events"][0]
        self.assertEqual(first["stageId"], second["stageId"])
        self.assertEqual(first["snapshot"], second["snapshot"])
        self.assertNotEqual(first["sourceDigest"], second["sourceDigest"])
        queue = CourseArchiveQueue(self.root / "private-state", storage_identity("https://media.example.test", "study"))
        jobs = seed_authoring_history(queue, [first, second, first])
        self.assertNotEqual(jobs[0]["key"], jobs[1]["key"])
        self.assertEqual(jobs[0]["key"], jobs[2]["key"])
        self.assertEqual(jobs[0]["event"]["sourceRaw"].encode(), self.raw)
        self.assertEqual(len(list(queue.items.glob("*.json"))), 2)

    def test_unchanged_bytes_do_not_repeat_and_sidecar_changes_have_a_new_revision(self):
        first = self.discover()
        cache = deepcopy(first["cache"])
        cache["after"] = ""
        with patch("services.course_archive_history._read", side_effect=AssertionError("unchanged bytes reopened")):
            self.assertEqual(self.discover(cache=cache)["events"], [])
        self.plan.write_bytes(b'{"goal":"updated retained teaching plan"}\n')
        second = self.discover(cache=cache)
        self.assertEqual(len(second["events"]), 1)
        self.assertEqual(first["events"][0]["sourceDigest"], second["events"][0]["sourceDigest"])
        self.assertNotEqual(first["events"][0]["archiveSourceRevision"], second["events"][0]["archiveSourceRevision"])

    def test_real_export_preserves_raw_original_and_plan_without_inventing_textbook_metadata(self):
        event = self.discover()["events"][0]
        result = export_authoring_history(self.exporter, event, staging_root=self.root / "archives")
        self.assertTrue(result["complete"], result["missingSources"])
        self.assertEqual(result["sourceKind"], "native_authoring_file")
        self.assertIn("/未绑定教材(历史课件)/未标注年级/", result["objectDirectory"])
        manifest = json.loads(Path(result["manifestPath"]).read_bytes())
        record = next(f for f in manifest["files"] if f["sourceIdentity"] == self.source.relative_to(self.root).as_posix())
        self.assertEqual(record["sha256"], hashlib.sha256(self.raw).hexdigest())
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read(record["archivePath"]), self.raw)
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_changed_source_is_rejected_before_any_export_or_staging(self):
        event = self.discover()["events"][0]
        self.plan.write_bytes(b'{"goal":"a later authoring version"}')
        with patch.object(self.exporter, "export_snapshot") as export:
            with self.assertRaisesRegex(CourseArchiveError, "owner_version_changed"):
                export_authoring_history(self.exporter, event, staging_root=self.root / "archives")
        export.assert_not_called()
        self.assertFalse((self.root / "archives").exists())

    def test_credentials_are_not_opened_and_are_excluded_by_the_existing_exporter(self):
        credentials = self.owner / ".env"
        credentials.write_bytes(b"PRIVATE_TEST_VALUE=do-not-read-fixture\n")
        from services import course_archive_history as history
        original_read = history._read

        def guarded(path, **kwargs):
            self.assertNotEqual(path.name, ".env")
            return original_read(path, **kwargs)

        with patch.object(history, "_read", side_effect=guarded):
            event = self.discover()["events"][0]
            result = export_authoring_history(self.exporter, event, staging_root=self.root / "archives")
        self.assertTrue(result["complete"])
        self.assertNotIn("do-not-read-fixture", json.dumps(event))
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertTrue(all("do-not-read-fixture" not in archive.read(name).decode("utf8")
                                for name in archive.namelist()))
        self.assertEqual(credentials.read_bytes(), b"PRIVATE_TEST_VALUE=do-not-read-fixture\n")

    def test_linked_unbound_and_empty_sources_are_not_seeded(self):
        outside = self.root / "outside"
        outside.mkdir()
        linked = self.owner / "linked"
        linked.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.discover()["events"], [])
        linked.unlink()
        unbound = self.root / AUTHORING_ROOT / "unbound/classroom.json"
        unbound.parent.mkdir()
        unbound.write_bytes(self.raw)
        result = discover_authoring_history(self.root, paths=[unbound])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["errors"][0]["error"], "authoring_history_owner_not_bound")
        self.source.write_bytes(b'{"stage":{"id":"stage-historical"},"scenes":[{}]}')
        self.assertEqual(self.discover()["events"], [])
        with self.assertRaisesRegex(CourseArchiveError, "outside_or_linked"):
            discover_authoring_history(self.root, paths=[self.root.parent / "outside.json"])

    def test_change_during_export_keeps_diagnostic_capture_incomplete_and_never_changes_originals(self):
        event = self.discover()["events"][0]
        original_export = self.exporter.export_snapshot

        def changed_export(*args, **kwargs):
            self.plan.write_bytes(b'{"goal":"changed after binding"}')
            return original_export(*args, **kwargs)

        with patch.object(self.exporter, "export_snapshot", side_effect=changed_export):
            result = export_authoring_history(self.exporter, event, staging_root=self.root / "archives")
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertFalse(json.loads(Path(result["indexPath"]).read_bytes())["complete"])
        self.assertEqual(result["missingSources"][-1]["reason"], "captured_original_version_mismatch")
        self.assertTrue(Path(result["zip"]["path"]).is_file())
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(self.plan.read_bytes(), b'{"goal":"changed after binding"}')

    def test_default_scan_is_bounded_and_only_classroom_filenames_are_automatic(self):
        narrated = self.owner / "narrated-classroom.json"
        narrated.write_bytes(self.raw)
        discovered = discover_authoring_history(self.root, limit=1)
        self.assertEqual(discovered["visited"], 1)
        self.assertEqual([e["authoringPath"] for e in discovered["events"]],
                         [self.source.relative_to(self.root).as_posix()])
        end = discover_authoring_history(self.root, cache=discovered["cache"], limit=1)
        self.assertEqual(end["visited"], 0)
        self.assertEqual(end["cache"]["after"], "")
        explicit = discover_authoring_history(self.root, paths=[narrated])
        self.assertEqual(len(explicit["events"]), 1)


if __name__ == "__main__":
    unittest.main()
