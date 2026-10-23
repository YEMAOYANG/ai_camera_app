"""Archive retries must never regenerate, lose events or acknowledge partial uploads."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from services.course_archive_queue import (
    ArchiveQueueError, CourseArchiveProcessor, CourseArchiveQueue, CourseArchiveWorker,
    filesystem_event, postgres_event, storage_identity,
)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Exporter:
    def __init__(self):
        self.calls = 0
        self.incomplete = False
        self.catalog = []

    def list_courses(self, conn, *, include_saved):
        assert include_saved is True
        return self.catalog

    def export_course(self, conn, *, course_id, course_version, staging_root, **_):
        course = next(c for c in self.catalog if (c["courseId"], c["courseVersion"]) == (course_id, course_version))
        return self._export(staging_root, course["sourceKind"], course["sourceDigest"], course_id, course_version)

    def export_native_snapshot(self, snapshot, *, source_kind, source_digest, staging_root, meta):
        return self._export(staging_root, source_kind, source_digest, meta["courseId"], meta["courseVersion"])

    def export_legacy_classroom(self, classroom_id, *, staging_root):
        path = self.native_root / "data/classrooms" / (classroom_id + ".json")
        return self._export(staging_root, "native_legacy_file", digest(path.read_bytes()),
                            "native-legacy:" + classroom_id, "saved-original")

    def _export(self, staging, kind, sha, course, version):
        self.calls += 1
        archive_id = digest((kind + sha).encode())[:24]
        root = staging / (archive_id + "-" + format(self.calls, "08x"))
        root.mkdir(parents=True)
        payload = root / "课程资料"
        payload.mkdir()
        public = []
        for name, mime in [("完整课件.zip", "application/zip"), ("课堂结构.json", "application/json"),
                           ("manifest.json", "application/json")]:
            path = (root if mime == "application/zip" else payload) / name
            path.write_bytes(b"fixture-archive-bytes:" + name.encode())
            public.append({"localPath": str(path),
                "relativePath": "科学/教材/一年级/2026-10-23/观察/" + name,
                "sha256": digest(path.read_bytes()), "byteSize": path.stat().st_size, "mimeType": mime})
        value = {"schemaVersion": "mira.course-archive.export.v1", "archiveId": archive_id,
            "courseId": course, "courseVersion": version, "sourceKind": kind, "sourceDigest": sha,
            "complete": not self.incomplete,
            "missingSources": [{"kind": "native_media", "sourceIdentity": "needed.wav"}] if self.incomplete else [],
            "stagingDirectory": str(root), "manifestPath": str(payload / "manifest.json"),
            "objectDirectory": "科学/教材/一年级/2026-10-23/观察",
            "zip": {"path": str(root / "完整课件.zip")},
            "generatedPublicFiles": [] if self.incomplete else public, "indexPath": str(root / "index.json")}
        Path(value["indexPath"]).write_bytes(encoded(value))
        return value


class Client:
    def __init__(self, queue):
        self.queue = queue
        self.uploads = 0
        self.acks = []
        self.rows = []
        self.cursors = []
        self.stages = []
        self.stage_cursors = []
        self.upload_failure = False
        self.ack_failure = False
        self.mutate = lambda value: value

    def events(self, *, after_id, limit):
        self.cursors.append(after_id)
        return [row for row in self.rows if int(row["id"]) > int(after_id)
                and str(row["id"]) not in self.acks][:limit]

    def upload(self, index):
        self.uploads += 1
        if self.upload_failure:
            raise RuntimeError("untrusted provider failure containing a secret")
        raw = Path(index).read_bytes()
        value = json.loads(raw)
        receipt = {"schemaVersion": "mira.course-archive.verification.v1",
            "complete": True, "archiveId": value["archiveId"],
            "courseId": value["courseId"], "courseVersion": value["courseVersion"],
            "sourceDigest": value["sourceDigest"], "indexSha256": digest(raw), "storage": self.queue.storage,
            "byteSize": sum(f["byteSize"] for f in value["generatedPublicFiles"]),
            "objects": [{"objectKey": f["relativePath"], "sha256": f["sha256"],
                "byteSize": f["byteSize"], "etag": '"verified"'} for f in value["generatedPublicFiles"]]}
        receipt = self.mutate(deepcopy(receipt))
        path = self.queue.root / "archive-transfers" / value["archiveId"] / "verified-complete.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded(receipt))
        versioned = path.parent / "verifications" / digest(encoded(self.queue.storage)) / (digest(raw) + ".json")
        versioned.parent.mkdir(parents=True, exist_ok=True)
        versioned.write_bytes(encoded(receipt))
        return receipt

    def saved_stages(self, *, after_stage_id, limit):
        self.stage_cursors.append(after_stage_id)
        return [row for row in self.stages if row["stage_id"] > after_stage_id][:limit]

    def acknowledge(self, event_id, source_digest):
        if self.ack_failure:
            raise RuntimeError("ack failure")
        self.acks.append(str(event_id))


class CourseArchiveQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.now = 1000
        self.storage = storage_identity("https://media.example.test/", "study")
        self.queue = CourseArchiveQueue(self.root / "state", self.storage, clock=lambda: self.now)
        self.exporter = Exporter()
        self.exporter.root = self.root
        self.client = Client(self.queue)
        self.processor = CourseArchiveProcessor(self.queue, self.exporter, self.client)
        self.snapshot = {"id": "stage-one", "stage": {"id": "stage-one", "name": "观察", "subject": "science"},
                         "scenes": [{"stageId": "stage-one", "id": "page-one", "type": "slide"}]}

    def pg(self, event_id="1"):
        return postgres_event({"id": event_id, "source_kind": "native_pg_stage", "stage_id": "stage-one",
            "stage_revision": "7", "source_digest": digest(encoded(self.snapshot)),
            "snapshot_json": self.snapshot, "created_at": "2026-10-23T01:00:00.000Z"})

    def fs(self, snapshot_raw=None):
        raw = snapshot_raw or encoded(self.snapshot)
        sha = digest(raw)
        path = self.queue.root / "archive-events" / ("legacy-" + digest(("stage-one:" + sha).encode()) + ".json")
        path.parent.mkdir(exist_ok=True)
        # The producer emits its own canonical number serialization.
        data = b'{"schemaVersion":"mira.course-archive.event.v1","sourceKind":"legacy_classroom","stageId":"stage-one","sourceDigest":"' + sha.encode() + b'","createdAt":"2026-10-23T01:00:00.000Z","snapshot":' + raw + b'}'
        path.write_bytes(data)
        return path

    def test_single_process_lock_and_private_queue_modes(self):
        with self.queue.lock(), self.assertRaisesRegex(ArchiveQueueError, "already_running"):
            with self.queue.lock():
                self.fail("second worker entered")
        job = self.queue.enqueue(self.pg())
        self.assertEqual(stat.S_IMODE((self.queue.items / (job["key"] + ".json")).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.queue.directory.stat().st_mode), 0o700)

    def test_pg_authoring_control_is_private_and_passed_separately_from_course_metadata(self):
        row = {"id": "44", "source_kind": "native_pg_stage", "session_id": "authoring-session-44",
            "stage_id": "stage-one", "stage_revision": "7", "source_digest": digest(encoded(self.snapshot)),
            "snapshot_json": self.snapshot, "created_at": "2026-10-23T01:00:00.000Z"}
        event = postgres_event(row)
        self.assertEqual(event["authoringBinding"], {"sessionId": "authoring-session-44"})
        self.assertNotIn("sessionId", json.dumps(event["snapshot"]))
        self.exporter.export_native_snapshot = Mock(side_effect=RuntimeError("stop before upload"))
        self.assertFalse(self.processor.process(self.queue.enqueue(event)))
        call = self.exporter.export_native_snapshot.call_args.kwargs
        self.assertEqual(call["authoring_binding"], event["authoringBinding"])
        self.assertNotIn("session", json.dumps(call["meta"]))
        with self.assertRaisesRegex(ArchiveQueueError, "binding_invalid"):
            postgres_event({**row, "session_id": "../foreign-job"})

    def test_authoring_history_uses_its_frozen_original_adapter_before_transport(self):
        event = {**self.pg(), "origin": "authoring-history", "sourceKind": "native_authoring_file"}
        self.exporter.export_native_snapshot = Mock(side_effect=AssertionError("wrong adapter"))
        with patch("services.course_archive_history.export_authoring_history",
                   side_effect=RuntimeError("original binding failed")) as export:
            self.assertFalse(self.processor.process(self.queue.enqueue(event)))
        export.assert_called_once_with(self.exporter, event, staging_root=self.queue.root / "archives")
        self.exporter.export_native_snapshot.assert_not_called()
        self.assertEqual(self.client.uploads, 0)
        self.assertEqual(self.client.acks, [])

    def test_failed_upload_keeps_event_and_reuses_the_frozen_export_after_backoff(self):
        job = self.queue.enqueue(self.pg())
        self.client.upload_failure = True
        self.assertFalse(self.processor.process(job))
        self.assertEqual(self.client.acks, [])
        self.assertEqual(self.queue.due(10), [])
        self.assertNotIn("secret", json.dumps(job))
        frozen = job["export"].copy()
        self.now += 15
        self.client.upload_failure = False
        self.assertTrue(self.processor.process(self.queue.due(1)[0]))
        self.assertEqual(self.exporter.calls, 1)
        self.assertEqual(frozen, job["export"])
        self.assertEqual(self.client.acks, ["1"])

    def test_only_known_stable_error_codes_are_persisted_without_raw_exception_data(self):
        from services.course_archive_exporter import CourseArchiveError
        from scripts.course_storage_releases import InventoryError

        spoof = type("CourseArchiveError", (ValueError,), {"__module__": "untrusted_exporter"})
        cases = [
            (CourseArchiveError("archive_native_source_missing"), "archive_native_source_missing"),
            (InventoryError("release_binding_invalid"), "release_binding_invalid"),
            (ArchiveQueueError("archive_export_incomplete"), "archive_export_incomplete"),
            (CourseArchiveError('{"private": "fixture-secret"}'), None),
            (ArchiveQueueError("fixture-secret/path.json"), None),
            (CourseArchiveError("archive_native_source_missing\n"), None),
            (spoof("looks_safe"), None),
            (RuntimeError("looks_safe"), None),
        ]
        for error, expected in cases:
            with self.subTest(error_type=type(error).__name__, expected=expected):
                job = self.queue.enqueue(self.pg())
                with patch.object(self.exporter, "export_native_snapshot", side_effect=error):
                    self.assertFalse(self.processor.process(job))
                persisted = json.loads((self.queue.items / (job["key"] + ".json")).read_bytes())
                self.assertEqual(persisted["lastErrorCode"], expected)
                self.assertEqual(persisted["lastError"], type(error).__name__)
                self.assertNotIn("fixture-secret", json.dumps(persisted))
                self.assertEqual(persisted["event"]["snapshot"], self.snapshot)
        self.assertEqual((self.client.uploads, self.client.acks), (0, []))

    def test_ack_retry_reuses_durable_verified_receipt_without_uploading_again(self):
        job = self.queue.enqueue(self.pg())
        self.client.ack_failure = True
        self.assertFalse(self.processor.process(job))
        self.assertIn("receiptSha256", job)
        self.client.ack_failure = False
        self.assertTrue(self.processor.process(job))
        self.assertEqual((self.exporter.calls, self.client.uploads), (1, 1))

    def test_storage_destination_and_source_kind_are_separate_identities(self):
        event = self.pg()
        original = self.queue.enqueue(event)
        other = CourseArchiveQueue(self.queue.root, {**self.storage, "bucket": "another"})
        self.assertNotEqual(other.enqueue(event)["key"], original["key"])
        self.assertNotEqual(self.queue.enqueue({**event, "sourceKind": "legacy_classroom"})["key"], original["key"])
        changed = deepcopy(event)
        changed["snapshot"]["stage"]["name"] = "different content under old digest"
        with self.assertRaisesRegex(ArchiveQueueError, "snapshot_conflict"):
            self.queue.enqueue(changed)

    def test_incomplete_capture_is_not_uploaded_and_can_retry_when_media_arrives(self):
        self.exporter.incomplete = True
        job = self.queue.enqueue(self.pg())
        self.assertFalse(self.processor.process(job))
        self.assertNotIn("export", job)
        self.assertEqual(len(job["incompleteExports"]), 1)
        self.assertFalse(self.processor.process(job))
        self.assertEqual(self.exporter.calls, 1)
        (self.root / "needed.wav").write_bytes(b"source is now present")
        self.exporter.incomplete = False
        self.assertTrue(self.processor.process(job))
        self.assertEqual((self.exporter.calls, self.client.uploads), (2, 1))
        self.assertEqual(self.client.acks, ["1"])

    def test_repaired_exporter_retries_unchanged_original_without_repeating_unfixed_zip(self):
        adapter = self.root / "backend/services/course_archive_exporter.py"
        adapter.parent.mkdir(parents=True)
        adapter.write_bytes(b"old safe format allowlist")
        self.exporter.incomplete = True
        job = self.queue.enqueue(self.pg())
        self.assertFalse(self.processor.process(job))
        self.assertFalse(self.processor.process(job))
        self.assertEqual(self.exporter.calls, 1)
        adapter.write_bytes(b"safe compiler capsule source format added")
        self.exporter.incomplete = False
        self.assertTrue(self.processor.process(job))
        self.assertEqual((self.exporter.calls, self.client.uploads), (2, 1))

    def test_repaired_native_asset_helper_changes_dependency_signature(self):
        helper = self.root / "openmaic-runtime/scripts/course-archive-assets.mjs"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b"old asset adapter")
        before = self.processor._missing_dependencies([{"kind": "native_asset", "sourceIdentity": "ast_missing"}])
        self.assertEqual(before, self.processor._missing_dependencies(
            [{"kind": "native_asset", "sourceIdentity": "ast_missing"}]))
        helper.write_bytes(b"fixed official asset adapter")
        self.assertNotEqual(before, self.processor._missing_dependencies(
            [{"kind": "native_asset", "sourceIdentity": "ast_missing"}]))

    def test_receipt_must_cover_exact_objects_and_storage_before_ack(self):
        mutations = [lambda r: {**r, "storage": {**r["storage"], "bucket": "wrong"}},
            lambda r: {**r, "objects": r["objects"][:-1]},
            lambda r: {**r, "objects": [r["objects"][0], r["objects"][0]]},
            lambda r: {**r, "indexSha256": "0" * 64},
            lambda r: {**r, "sourceDigest": "0" * 64}, lambda r: {**r, "complete": False}]
        for i, mutation in enumerate(mutations):
            with self.subTest(i=i):
                event = self.pg(str(i + 1))
                event["sourceDigest"] = digest(str(i).encode())
                job = self.queue.enqueue(event)
                self.client.mutate = mutation
                self.assertFalse(self.processor.process(job))
        self.assertEqual(self.client.acks, [])

    def test_missing_durable_receipt_cannot_be_replaced_by_success_stdout(self):
        real_upload = self.client.upload
        def stdout_only(index):
            result = real_upload(index)
            (self.queue.root / "archive-transfers" / result["archiveId"] / "verified-complete.json").unlink()
            (self.queue.root / "archive-transfers" / result["archiveId"] / "verifications" /
                digest(encoded(self.queue.storage)) / (result["indexSha256"] + ".json")).unlink()
            return result
        self.client.upload = stdout_only
        self.assertFalse(self.processor.process(self.queue.enqueue(self.pg())))
        self.assertEqual(self.client.acks, [])

    def test_filesystem_event_moves_only_after_verified_delivery_and_preserves_source(self):
        source = self.root / "saved-original.json"
        source.write_bytes(encoded(self.snapshot))
        path = self.fs()
        event = filesystem_event(path)
        job = self.queue.enqueue(event)
        self.client.upload_failure = True
        self.assertFalse(self.processor.process(job))
        self.assertTrue(path.is_file())
        self.client.upload_failure = False
        self.assertTrue(self.processor.process(job))
        self.assertFalse(path.exists())
        self.assertEqual(len(list((path.parent / "processed").glob("*.json"))), 1)
        self.assertEqual(source.read_bytes(), encoded(self.snapshot))

    def test_filesystem_raw_js_numbers_are_preserved_and_digest_checked(self):
        raw = encoded(self.snapshot).replace(b'"name":"', b'"small":1e-7,"name":"')
        path = self.fs(raw)
        event = filesystem_event(path)
        self.assertEqual(event["sourceRaw"].encode(), raw)
        value = json.loads(path.read_bytes())
        value["snapshot"]["stage"]["name"] = "changed"
        path.write_bytes(encoded(value))
        with self.assertRaisesRegex(ArchiveQueueError, "digest_mismatch"):
            filesystem_event(path)

    def test_changed_event_or_index_is_not_acknowledged_or_overwritten(self):
        path = self.fs()
        event = filesystem_event(path)
        job = self.queue.enqueue(event)
        self.processor._export(job)
        index = Path(job["export"]["indexPath"])
        index.write_bytes(index.read_bytes() + b" ")
        self.assertFalse(self.processor.process(job))
        self.assertTrue(path.exists())
        self.assertEqual(self.client.uploads, 0)

    def test_symlink_events_and_state_are_rejected(self):
        path = self.fs()
        actual = path.with_suffix(".actual")
        path.rename(actual)
        path.symlink_to(actual)
        with self.assertRaises(OSError):
            filesystem_event(path)
        alias = self.root / "alias"
        alias.symlink_to(self.queue.root, target_is_directory=True)
        with self.assertRaisesRegex(ArchiveQueueError, "symlink"):
            CourseArchiveQueue(alias, self.storage)

    def test_worker_paginates_pg_and_acks_duplicate_events_without_reexport(self):
        row = {"id": "1", "source_kind": "native_pg_stage", "stage_id": "stage-one", "stage_revision": "7",
            "source_digest": digest(encoded(self.snapshot)), "snapshot_json": self.snapshot,
            "created_at": "2026-10-23T01:00:00.000Z"}
        self.client.rows = [row]
        worker = CourseArchiveWorker(self.queue, self.processor, scan_catalog=False)
        self.assertEqual(worker.run_once(limit=1)["completed"], 1)
        self.client.rows.append({**row, "id": "2"})
        self.assertEqual(worker.run_once(limit=1)["completed"], 1)
        self.assertEqual((self.exporter.calls, self.client.uploads), (1, 1))
        self.assertIn("2", self.client.acks)
        self.assertEqual(self.client.cursors, [0, 1])

    def test_live_only_worker_preserves_private_history_and_delivers_real_pg_and_fs_outboxes(self):
        historical = deepcopy(self.pg())
        historical.update(origin="reconcile", priority=2)
        historical["snapshot"]["stage"]["name"] = "previous historical bytes"
        historical["sourceDigest"] = digest(encoded(historical["snapshot"]))
        job = self.queue.enqueue(historical)
        path = self.queue.items / (job["key"] + ".json")
        before = path.read_bytes()
        # An exact old capture newly emitted by the real outbox is live work;
        # its delivery must be promoted while unrelated private history stays.
        promoted = self.queue.enqueue({**self.pg(), "origin": "reconcile", "priority": 2})
        self.client.rows = [{"id": "99", "source_kind": "native_pg_stage", "stage_id": "stage-one",
            "stage_revision": "8", "source_digest": digest(encoded(self.snapshot)),
            "snapshot_json": self.snapshot, "created_at": "2026-10-23T01:00:00.000Z"}]
        event_path = self.fs()
        worker = CourseArchiveWorker(self.queue, self.processor, scan_catalog=False, scan_history=False)
        with patch.object(worker, "_reconcile_legacy") as legacy, \
                patch.object(worker, "_reconcile_postgres") as postgres:
            result = worker.run_once(limit=10)
        legacy.assert_not_called()
        postgres.assert_not_called()
        self.assertEqual((result["completed"], result["failed"], result["discoveryErrors"]), (2, 0, 0))
        self.assertEqual(self.client.acks, ["99"])
        self.assertFalse(event_path.exists())
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads((self.queue.items / (promoted["key"] + ".json")).read_bytes())["status"], "complete")
        self.assertEqual(self.queue.due(10, max_priority=1), [])
        self.assertEqual([j["key"] for j in self.queue.due(10)], [job["key"]])

    def test_cli_requires_include_history_for_discovery_and_existing_priority_two_delivery(self):
        from workers import course_archive_worker as cli

        event = self.pg()
        event.update(origin="reconcile", priority=2)
        job = self.queue.enqueue(event)
        path = self.queue.items / (job["key"] + ".json")
        before = path.read_bytes()
        self.client.stages = [{"stage_id": "stage-one", "stage_revision": "7",
            "source_digest": event["sourceDigest"], "snapshot_json": self.snapshot,
            "created_at": "2026-10-23T01:00:00.000Z"}]
        instances = []

        def worker_factory(*args, **kwargs):
            worker = CourseArchiveWorker(*args, **kwargs)
            worker._reconcile_legacy = Mock(wraps=worker._reconcile_legacy)
            worker._reconcile_postgres = Mock(wraps=worker._reconcile_postgres)
            instances.append(worker)
            return worker

        with patch.dict(os.environ, {"COURSE_STORAGE_ARCHIVE_ENABLED": "true",
                "COURSE_STORAGE_ENDPOINT": self.storage["endpoint"], "COURSE_STORAGE_BUCKET": "study"}), \
                patch("core.config.AppConfig.from_env", return_value=Mock(DATABASE_URL="unused-test-database")), \
                patch("core.database.Database", return_value=Mock()), \
                patch("services.course_archive_exporter.CourseArchiveExporter", return_value=self.exporter), \
                patch.object(cli, "CourseArchiveQueue", return_value=self.queue), \
                patch.object(cli, "CourseArchiveProcessor", return_value=self.processor), \
                patch.object(cli, "NodeArchiveClient", return_value=self.client), \
                patch.object(cli, "CourseArchiveWorker", side_effect=worker_factory), \
                patch.object(cli.shutil, "which", return_value="/fixture/node24"), \
                patch.object(cli.subprocess, "run", return_value=Mock(returncode=0, stdout="v24.21.0\n")), \
                patch.object(cli.signal, "signal"):
            self.assertEqual(cli.main(["--once"]), 0)
            self.assertFalse(instances[0].scan_history)
            instances[0]._reconcile_legacy.assert_not_called()
            instances[0]._reconcile_postgres.assert_not_called()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual((self.exporter.calls, self.client.uploads), (0, 0))
            self.assertEqual(cli.main(["--once", "--include-history"]), 0)
        self.assertTrue(instances[1].scan_history)
        instances[1]._reconcile_legacy.assert_called_once()
        instances[1]._reconcile_postgres.assert_called_once()
        self.assertEqual(self.client.stage_cursors, [""])
        self.assertEqual((self.exporter.calls, self.client.uploads), (1, 1))
        self.assertEqual(json.loads(path.read_bytes())["status"], "complete")

    def test_catalog_scans_saved_and_published_but_unchanged_courses_are_not_exported(self):
        self.exporter.catalog = [{"courseId": "published", "courseVersion": "1", "sourceKind": "textbook_release",
                "sourceDigest": "a" * 64, "status": "published"},
            {"courseId": "textbook-preview:saved", "courseVersion": "saved-1", "sourceKind": "textbook_preview",
                "sourceDigest": "b" * 64, "status": "generated_saved"}]
        database = Mock()
        self.processor.database = database
        worker = CourseArchiveWorker(self.queue, self.processor, database=database)
        first = worker.run_once(limit=2)
        self.assertEqual((first["completed"], first["failed"], first["discoveryErrors"]), (2, 0, 0))
        self.assertEqual(worker.run_once(limit=2)["completed"], 0)
        self.assertEqual((self.exporter.calls, self.client.uploads), (2, 2))

    def test_disabled_worker_never_connects_or_imports_application(self):
        from workers.course_archive_worker import main
        with patch.dict(os.environ, {"COURSE_STORAGE_ARCHIVE_ENABLED": "false"}), \
                patch("core.database.Database.connect", side_effect=AssertionError("no DB")):
            self.assertEqual(main(["--once"]), 0)

    def test_verified_acknowledged_cleanup_preserves_originals_index_and_manifest(self):
        original = self.root / "original-teaching-plan.json"
        original.write_bytes(b"unique original must survive")
        job = self.queue.enqueue(self.pg())
        self.assertTrue(self.processor.process(job))
        stage = Path(job["export"]["indexPath"]).parent
        self.assertTrue(job["stagingPruned"])
        self.assertEqual({p.name for p in stage.iterdir()}, {"index.json", "manifest.json"})
        self.assertEqual(original.read_bytes(), b"unique original must survive")
        self.assertTrue(self.processor.process(job))
        self.assertEqual((self.exporter.calls, self.client.uploads), (1, 1))

    def test_cleanup_waits_for_ack_and_rejects_links_to_originals(self):
        job = self.queue.enqueue(self.pg())
        self.client.ack_failure = True
        self.assertFalse(self.processor.process(job))
        stage = Path(job["export"]["indexPath"]).parent
        self.assertTrue((stage / "完整课件.zip").is_file())
        original = self.root / "original"
        original.mkdir()
        (original / "media.wav").write_bytes(b"keep")
        (stage / "课程资料" / "original-link").symlink_to(original, target_is_directory=True)
        self.client.ack_failure = False
        self.assertFalse(self.processor.process(job))
        self.assertEqual((original / "media.wav").read_bytes(), b"keep")
        self.assertTrue((stage / "完整课件.zip").exists())

    def test_versioned_storage_receipt_survives_latest_being_overwritten(self):
        job = self.queue.enqueue(self.pg())
        self.client.ack_failure = True
        self.assertFalse(self.processor.process(job))
        self.assertIn("verifications", job["receiptPath"])
        latest = self.queue.root / "archive-transfers" / job["export"]["archiveId"] / "verified-complete.json"
        latest.write_bytes(encoded({"complete": True, "storage": {"bucket": "other"}}))
        self.client.ack_failure = False
        self.assertTrue(self.processor.process(job))
        self.assertEqual(self.client.uploads, 1)

    def test_catalog_revision_changes_identity_without_falsifying_release_digest(self):
        course = {"courseId": "one", "courseVersion": "1", "sourceKind": "textbook_release",
                  "sourceDigest": "a" * 64, "archiveSourceRevision": "b" * 64}
        event = {"sourceKind": "textbook_release", "sourceDigest": "a" * 64, "course": course, "origin": "catalog"}
        old = self.queue.enqueue(event)
        changed = deepcopy(event)
        changed["course"]["archiveSourceRevision"] = "c" * 64
        new = self.queue.enqueue(changed)
        self.assertNotEqual(old["key"], new["key"])
        self.assertEqual(old["identity"]["sourceDigest"], new["identity"]["sourceDigest"])

    def test_legacy_reconciliation_recovers_missing_outbox_and_does_not_reread_unchanged_source(self):
        self.exporter.native_root = self.root / "native"
        source = self.exporter.native_root / "data/classrooms/stage-one.json"
        source.parent.mkdir(parents=True)
        source.write_bytes(encoded(self.snapshot))
        worker = CourseArchiveWorker(self.queue, self.processor, scan_catalog=False)
        first = worker.run_once(limit=1)
        self.assertEqual((first["completed"], first["failed"], first["discoveryErrors"]), (1, 0, 0))
        self.assertTrue(source.is_file())
        worker.run_once(limit=1)  # Cursor reaches the end, then wraps.
        from services import course_archive_queue as module
        original_read = module._read
        def no_source_read(path):
            self.assertNotEqual(Path(path), source, "unchanged source was re-read")
            return original_read(path)
        with patch.object(module, "_read", side_effect=no_source_read):
            self.assertEqual(worker.run_once(limit=1)["completed"], 0)
        self.assertEqual(self.exporter.calls, 1)

    def test_catalog_has_priority_over_historical_reconciliation(self):
        self.exporter.native_root = self.root / "native"
        source = self.exporter.native_root / "data/classrooms/stage-one.json"
        source.parent.mkdir(parents=True)
        source.write_bytes(encoded(self.snapshot))
        self.exporter.catalog = [{"courseId": "published", "courseVersion": "1", "sourceKind": "textbook_release",
                                  "sourceDigest": "a" * 64, "status": "published"}]
        database = Mock()
        self.processor.database = database
        worker = CourseArchiveWorker(self.queue, self.processor, database=database)
        self.assertEqual(worker.run_once(limit=1)["completed"], 1)
        pending = self.queue.due(10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event"]["sourceKind"], "native_legacy_file")
        self.assertEqual(pending[0]["priority"], 2)

    def test_pg_reconciliation_preserves_snapshot_without_ack_and_deduplicates_real_outbox(self):
        row = {"stage_id": "stage-one", "stage_revision": "7", "source_digest": digest(encoded(self.snapshot)),
               "snapshot_json": self.snapshot, "created_at": "2026-10-23T01:00:00.000Z"}
        self.client.stages = [row]
        worker = CourseArchiveWorker(self.queue, self.processor, scan_catalog=False)
        self.assertEqual(worker.run_once(limit=1)["completed"], 1)
        self.assertEqual(self.client.acks, [])
        self.client.rows = [{**row, "id": "99", "source_kind": "native_pg_stage"}]
        self.assertEqual(worker.run_once(limit=1)["completed"], 1)
        self.assertEqual(self.client.acks, ["99"])
        self.assertEqual((self.exporter.calls, self.client.uploads), (1, 1))

    def test_operator_can_adopt_an_existing_verified_index_without_reupload(self):
        event = self.pg()
        job = self.queue.enqueue(event)
        self.processor._export(job)
        self.client.upload(job["export"]["indexPath"])
        self.assertTrue(self.processor.adopt_verified(event, job["export"]["indexPath"]))
        self.assertEqual((self.exporter.calls, self.client.uploads), (1, 1))

    def layout_replacement(self, job):
        value = json.loads(Path(job["export"]["indexPath"]).read_bytes())
        stage = self.queue.root / "archives" / (value["archiveId"] + "-123abc00")
        stage.mkdir()
        value.update(objectDirectory="科学/教材/一年级上册/2026-10-23/观察", stagingDirectory=str(stage),
                     manifestPath=str(stage / "课程资料/manifest.json"), indexPath=str(stage / "index.json"))
        value["zip"]["path"] = str(stage / "完整课件.zip")
        for entry in value["generatedPublicFiles"]:
            filename = entry["relativePath"].rsplit("/", 1)[-1]
            entry["relativePath"] = value["objectDirectory"] + "/" + filename
            entry["localPath"] = str((stage if entry["mimeType"] == "application/zip" else stage / "课程资料") / filename)
        (stage / "manifest.json").write_bytes(Path(job["retainedManifestPath"]).read_bytes())
        Path(value["indexPath"]).write_bytes(encoded(value))
        self.client.upload(value["indexPath"])
        return value

    def test_verified_layout_rebinding_is_explicit_idempotent_and_keeps_previous_delivery_proof(self):
        job = self.queue.enqueue(self.pg())
        self.assertTrue(self.processor.process(job))
        old = deepcopy(job)
        new = self.layout_replacement(job)
        calls = (self.exporter.calls, self.client.uploads, list(self.client.acks))
        self.assertTrue(self.processor.relocate_verified(job["key"], new["indexPath"])["dryRun"])
        self.assertEqual(json.loads((self.queue.items / (job["key"] + ".json")).read_bytes())["export"], old["export"])
        self.processor.relocate_verified(job["key"], new["indexPath"], dry_run=False)
        saved = json.loads((self.queue.items / (job["key"] + ".json")).read_bytes())
        self.assertEqual(saved["export"]["indexPath"], new["indexPath"])
        self.assertEqual(saved["archiveLayoutHistory"][0]["export"], old["export"])
        self.assertEqual((self.exporter.calls, self.client.uploads, self.client.acks), calls)
        self.assertTrue(self.processor.relocate_verified(job["key"], new["indexPath"], dry_run=False)["alreadyCurrent"])

    def test_layout_rebinding_rejects_content_changes_and_wrong_remote_receipts_without_mutating_job(self):
        job = self.queue.enqueue(self.pg())
        self.assertTrue(self.processor.process(job))
        old = deepcopy(job["export"])
        new = self.layout_replacement(job)
        changed = deepcopy(new)
        changed["generatedPublicFiles"][0]["sha256"] = "c" * 64
        Path(new["indexPath"]).write_bytes(encoded(changed))
        with self.assertRaisesRegex(ArchiveQueueError, "content_changed"):
            self.processor.relocate_verified(job["key"], new["indexPath"], dry_run=False)
        Path(new["indexPath"]).write_bytes(encoded(new))
        self.client.mutate = lambda value: {**value, "storage": {**value["storage"], "bucket": "other"}}
        self.client.upload(new["indexPath"])
        with self.assertRaisesRegex(ArchiveQueueError, "verification_not_bound"):
            self.processor.relocate_verified(job["key"], new["indexPath"], dry_run=False)
        saved = json.loads((self.queue.items / (job["key"] + ".json")).read_bytes())
        self.assertEqual(saved["export"], old)

    def test_real_native_exporter_contract_delivers_and_cleans_only_derived_staging(self):
        from services.course_archive_exporter import CourseArchiveExporter
        self.processor.exporter = CourseArchiveExporter(project_root=self.root,
            media_store=Mock(), native_document_loader=lambda _: None,
            standard_asset_resolver=lambda *args, **kwargs: {"entries": [], "unresolved": []})
        path = self.fs()
        event = filesystem_event(path)
        job = self.queue.enqueue(event)
        self.assertTrue(self.processor.process(job), job.get("lastErrorCode"))
        self.assertTrue(job["stagingPruned"])
        self.assertTrue(Path(job["retainedManifestPath"]).is_file())
        self.assertFalse(path.exists())

    def completed_with_incomplete_capture(self, *, unique_old_original=False, private_old_originals=False,
                                          inherited_audio_alias=False):
        from services.course_archive_exporter import CourseArchiveExporter

        private_sources = []
        if private_old_originals:
            base = self.root / "output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard"
            for name in ("u4-l1/teaching-1/quality-repairs/formal-audio-predispatch-recovery-v1/old-build/4839.js",
                         "u4-l3/teaching-1/planning/native-operator-staging-0242/9196.js"):
                source = base / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(("/* retained private runtime " + source.name + " */").encode())
                private_sources.append(source)
        audio_sources, media, alias = [], None, None
        if inherited_audio_alias:
            prefix = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/"
            stage, request = "tbrev_" + "8" * 24, "tbprev_" + "a" * 64
            physical = prefix + stage + "/audio/" + request + ".wav"
            base = prefix + stage + "/textbook-preview-audio/operator-parent/"
            paid = "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/jobs/tts/" + digest(request.encode()) + ".json"
            evidence = [base + "source-receipts.json", base + "audio/" + request + ".wav", paid]
            raw = b"RIFF\x24\x00\x00\x00WAVEfmt retained fixture audio"
            for relative in [physical, *evidence]:
                path = self.root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw if path.suffix == ".wav" else encoded({"requestId": request, "status": "succeeded"}))
                audio_sources.append(path)
            media = {"path": "/api/classroom-media/" + stage + "/audio/" + request + ".wav",
                "sourcePath": physical, "archiveSourcePath": physical, "sha256": digest(raw),
                "byteSize": len(raw), "mimeType": "audio/wav"}
            alias = {"originalReference": "/api/classroom-media/" + stage + "/audio/cue-you.wav",
                "archivePath": "媒体/" + physical, "sha256": digest(raw), "byteSize": len(raw),
                "mimeType": "audio/wav", "sceneId": "page-one", "actionId": "review_cue-you",
                "ttsRequestId": request, "recoveryReason": "historical_audio_alias_from_verified_inherited_receipt",
                "evidence": evidence, "evidenceSha256": {p: digest((self.root / p).read_bytes()) for p in evidence}}
            self.audio_alias_fixture = {"physicalPath": self.root / physical, "originalBytes": raw,
                                        "oldIdentity": media["path"], "alias": alias}

        class RecoverableExporter(CourseArchiveExporter):
            incomplete = True

            def export_snapshot(inner, snapshot, **options):
                snapshot.source_roots.extend(source.parent.parent for source in private_sources)
                snapshot.source_files.extend(audio_sources)
                if media:
                    snapshot.media.append({**media, "path": media["path"] if inner.incomplete else alias["originalReference"]})
                    if not inner.incomplete:
                        snapshot.recovered_aliases.append(alias)
                if inner.incomplete:
                    snapshot.missing_sources.append({"kind": "media", "sourceIdentity": "needed.wav"})
                    if unique_old_original:
                        snapshot.documents["唯一原稿.json"] = '{"unique":"must survive"}'
                    if private_old_originals:
                        # The older capture predates the explicit private-runtime exclusions.
                        with patch("services.course_archive_exporter._private_runtime_exclusion", return_value=None):
                            return super().export_snapshot(snapshot, **options)
                return super().export_snapshot(snapshot, **options)

        exporter = RecoverableExporter(project_root=self.root, media_store=Mock(read=Mock(return_value=None)),
            native_document_loader=lambda _: None,
            standard_asset_resolver=lambda *args, **kwargs: {"entries": [], "unresolved": []})
        self.processor.exporter = exporter
        job = self.queue.enqueue(self.pg())
        with self.assertRaisesRegex(ArchiveQueueError, "archive_export_incomplete"):
            self.processor._export(job)
        original = self.root / "needed.wav"
        original.write_bytes(b"retained paid source")
        exporter.incomplete = False
        self.assertTrue(self.processor.process(job), job.get("lastErrorCode"))
        return job, Path(job["incompleteExports"][0]["indexPath"]).parent, original

    def test_incomplete_capture_cleanup_defaults_to_dry_run_then_preserves_recovery_evidence(self):
        job, stage, original = self.completed_with_incomplete_capture()
        before = {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
        plan = self.processor.prune_incomplete_captures(job["key"])
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["eligibleCaptures"], 1, plan)
        self.assertGreater(plan["eligibleBytes"], 0)
        self.assertEqual(plan["removedBytes"], 0)
        self.assertEqual(before, {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()})
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["removedBytes"], plan["eligibleBytes"], result)
        self.assertEqual({p.name for p in stage.iterdir()}, {"index.json", "manifest.json", "incomplete-prune.json"})
        self.assertEqual(original.read_bytes(), b"retained paid source")
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"], dry_run=False)["removedBytes"], 0)

    def record_zip_only_cleanup(self, job, stage):
        """Model the operator's byte-verified ZIP-only journal, without a prune marker."""
        index_path = stage / "index.json"
        raw = index_path.read_bytes()
        index = json.loads(raw)
        manifest_path = Path(index["manifestPath"])
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        originals = {entry["archivePath"]: entry["original"] for entry in manifest["files"]}
        zip_path = Path(index["zip"]["path"])
        entries = []
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                payload = manifest_path.parent / info.filename
                evidence = self.processor._cleanup_file(payload)
                self.assertEqual(archive.read(info), payload.read_bytes())
                entries.append({"archivePath": info.filename, "payloadPath": str(payload),
                    "sha256": evidence["sha256"], "byteSize": evidence["byteSize"],
                    "original": originals.get(info.filename, False), "payloadIdentity": evidence["identity"],
                    "zipCRC": info.CRC, "compression": info.compress_type, "dateTime": list(info.date_time),
                    "extraHex": info.extra.hex(), "commentHex": info.comment.hex(), "externalAttr": info.external_attr})
        directory = self.queue.root / "archive-retirements" / job["key"] / "zip-only-captures" / stage.name
        directory.mkdir(parents=True, mode=0o700)
        for name, data in (("index.json", raw), ("manifest.json", manifest_raw)):
            (directory / name).write_bytes(data)
            (directory / name).chmod(0o600)
        proof = {"schemaVersion": "mira.course-archive.zip-only-cleanup.v1",
            "status": "zip-removed-payload-retained", "mode": "zip-only", "jobKey": job["key"],
            "indexPath": str(index_path), "indexSha256": digest(raw), "manifestPath": str(manifest_path),
            "manifestSha256": digest(manifest_raw), "retainedIndexPath": str(directory / "index.json"),
            "retainedManifestPath": str(directory / "manifest.json"),
            "removedZip": {"path": str(zip_path), **self.processor._cleanup_file(zip_path)},
            "verifiedEntries": entries, "payloadPruned": False, "establishesComplete": False,
            "queueRecordChanged": False}
        journal = directory / "zip-only-cleanup.json"
        journal.write_bytes(encoded(proof))
        journal.chmod(0o600)
        zip_path.unlink()
        return journal, proof

    def test_zip_only_journal_allows_missing_zip_after_complete_replacement_without_faking_intent(self):
        job, stage, original = self.completed_with_incomplete_capture()
        journal, proof = self.record_zip_only_cleanup(job, stage)
        journal_raw = journal.read_bytes()
        before = {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
        plan = self.processor.prune_incomplete_captures(job["key"])
        self.assertEqual(plan["eligibleCaptures"], 1, plan)
        self.assertFalse((stage / "incomplete-prune.json").exists())
        self.assertEqual(before, {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()})
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 1, result)
        marker = json.loads((stage / "incomplete-prune.json").read_bytes())
        self.assertEqual(marker["zipOnlyProof"], {"path": str(journal), "sha256": digest(journal_raw)})
        self.assertEqual(journal.read_bytes(), journal_raw)
        self.assertEqual(original.read_bytes(), b"retained paid source")
        self.assertEqual({p.name for p in stage.iterdir()}, {"index.json", "manifest.json", "incomplete-prune.json"})
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"], dry_run=False)["removedBytes"], 0)

    def test_zip_only_journal_rejects_missing_mismatched_or_incomplete_evidence_without_payload_deletion(self):
        job, stage, _ = self.completed_with_incomplete_capture()
        journal, proof = self.record_zip_only_cleanup(job, stage)
        before = {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
        mutations = [
            ("job", lambda value: value.update(jobKey="f" * 64)),
            ("index", lambda value: value.update(indexSha256="f" * 64)),
            ("manifest", lambda value: value.update(manifestSha256="f" * 64)),
            ("zip digest", lambda value: value["removedZip"].update(sha256="f" * 64)),
            ("zip size", lambda value: value["removedZip"].update(byteSize=value["removedZip"]["byteSize"] + 1)),
            ("zip member missing", lambda value: value["verifiedEntries"].pop()),
            ("zip member duplicate", lambda value: value["verifiedEntries"].__setitem__(0, value["verifiedEntries"][-1])),
            ("member digest", lambda value: value["verifiedEntries"][0].update(sha256="f" * 64)),
            ("foreign payload", lambda value: value["verifiedEntries"][0].update(payloadPath=str(self.root / "original.json"))),
            ("unbound backup", lambda value: value.update(retainedManifestPath=str(stage / "manifest.json"))),
            ("not completed", lambda value: value.update(status="zip-removal-planned")),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                changed = deepcopy(proof)
                mutate(changed)
                journal.write_bytes(encoded(changed))
                result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
                self.assertEqual(result["eligibleCaptures"], 0, result)
                self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_zip_only_proof_invalid")
                self.assertFalse((stage / "incomplete-prune.json").exists())
                self.assertEqual(before, {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()})
        journal.unlink()
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 0, result)
        self.assertFalse((stage / "incomplete-prune.json").exists())

    def test_zip_only_journal_rejects_linked_proof_changed_backups_and_changed_or_missing_payload(self):
        job, stage, _ = self.completed_with_incomplete_capture()
        journal, proof = self.record_zip_only_cleanup(job, stage)
        raw = journal.read_bytes()
        backup = journal.parent / "manifest.json"
        saved = backup.read_bytes()
        backup.write_bytes(saved + b" ")
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        backup.write_bytes(saved)
        journal.chmod(0o644)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        journal.unlink()
        alias = self.root / "journal.json"
        alias.write_bytes(raw)
        alias.chmod(0o600)
        journal.symlink_to(alias)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        journal.unlink()
        journal.write_bytes(raw)
        journal.chmod(0o600)
        filename = Path(proof["verifiedEntries"][0]["payloadPath"])
        saved = filename.read_bytes()
        filename.write_bytes(bytes([saved[0] ^ 1]) + saved[1:])
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        # A forged current identity cannot replace the existing full payload SHA check.
        proof["verifiedEntries"][0]["payloadIdentity"] = self.processor._cleanup_file(filename)["identity"]
        journal.write_bytes(encoded(proof))
        result = self.processor.prune_incomplete_captures(job["key"])
        self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_derivative_changed")
        filename.unlink()
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        self.assertFalse((stage / "incomplete-prune.json").exists())

    def test_zip_only_proof_does_not_replace_original_coverage(self):
        job, stage, _ = self.completed_with_incomplete_capture(unique_old_original=True)
        self.record_zip_only_cleanup(job, stage)
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_original_not_covered")
        self.assertTrue((stage / "课程资料" / "唯一原稿.json").exists())

    def test_zip_only_proof_does_not_replace_existing_zip_validation(self):
        job, stage, _ = self.completed_with_incomplete_capture()
        self.record_zip_only_cleanup(job, stage)
        index = json.loads((stage / "index.json").read_bytes())
        Path(index["zip"]["path"]).write_bytes(b"recreated changed ZIP must not use journal")
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_zip_changed")
        self.assertFalse((stage / "incomplete-prune.json").exists())

    def test_zip_only_cleanup_resume_binds_journal_and_allows_only_planned_missing_payload(self):
        job, stage, _ = self.completed_with_incomplete_capture()
        journal, proof = self.record_zip_only_cleanup(job, stage)
        unlink = Path.unlink
        interrupted = False

        def interrupted_unlink(path, *args, **kwargs):
            nonlocal interrupted
            result = unlink(path, *args, **kwargs)
            if path.is_relative_to(stage / "课程资料") and not interrupted:
                interrupted = True
                raise OSError("interrupted after persisted cleanup intent")
            return result

        with patch.object(Path, "unlink", interrupted_unlink):
            first = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertFalse(first["captures"][0]["eligible"])
        raw = journal.read_bytes()
        proof["auditChanged"] = True
        journal.write_bytes(encoded(proof))
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        journal.write_bytes(raw)
        second = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(second["eligibleCaptures"], 1, second)
        self.assertEqual({p.name for p in stage.iterdir()}, {"index.json", "manifest.json", "incomplete-prune.json"})

    def bind_private_recovery(self, job, stage):
        index_raw = (stage / "index.json").read_bytes()
        index = json.loads(index_raw)
        manifest_raw = Path(index["manifestPath"]).read_bytes()
        old = json.loads(manifest_raw)
        replacement = json.loads(Path(job["retainedManifestPath"]).read_bytes())
        identity = lambda entry: (entry["sourceIdentity"], entry["sha256"], entry["byteSize"])
        covered = {identity(entry) for entry in replacement["files"] if entry["original"]}
        uncovered = [entry for entry in old["files"] if entry["original"] and identity(entry) not in covered]
        self.assertEqual(len(uncovered), 2)
        directory = self.queue.root / "archive-retirements" / job["key"] / "private-recovery" / stage.name
        (directory / "files").mkdir(parents=True, mode=0o700)
        for name, raw in (("index.json", index_raw), ("manifest.json", manifest_raw)):
            (directory / name).write_bytes(raw)
            (directory / name).chmod(0o600)
        entries = []
        for entry in uncovered:
            target = directory / "files" / (entry["sha256"] + ".js")
            target.write_bytes((stage / "课程资料" / entry["archivePath"]).read_bytes())
            target.chmod(0o600)
            entries.append({**entry, "recoveryPath": str(target)})
        provisional = {"schemaVersion": "mira.course-archive.private-recovery.v1",
            "status": "verified-private-recovery", "jobKey": job["key"], "captureStage": str(stage),
            "indexPath": str(stage / "index.json"), "indexSha256": digest(index_raw),
            "manifestPath": index["manifestPath"], "manifestSha256": digest(manifest_raw),
            "retainedIndexPath": str(directory / "index.json"), "retainedManifestPath": str(directory / "manifest.json"),
            "files": entries, "fileCount": len(entries), "byteSize": sum(entry["byteSize"] for entry in entries),
            "publicUploadAllowed": False, "payloadPruned": False, "queueRecordChanged": False}
        raw = encoded(provisional)
        provisional_path = directory / "private-recovery.provisional.json"
        provisional_path.write_bytes(raw)
        provisional_path.chmod(0o600)
        bound_entries = []
        for entry in entries:
            omission = next(item for item in replacement["excludedFiles"]
                if Path(entry["sourceIdentity"]).is_relative_to(item["sourceIdentity"]))
            bound_entries.append({**entry, "matchedOmission": omission})
        proof = {**provisional, "files": bound_entries, "schemaVersion": "mira.course-archive.private-recovery.v2",
            "status": "bound-complete-replacement", "replacementIndexSha256": job["export"]["indexSha256"],
            "receiptSha256": job["receiptSha256"], "provisionalProofPath": str(provisional_path),
            "provisionalProofSha256": digest(raw)}
        journal = directory / "private-recovery.json"
        journal.write_bytes(encoded(proof))
        journal.chmod(0o600)
        return journal, proof

    def test_explicit_private_omissions_can_use_bound_independent_recovery_without_public_upload(self):
        job, stage, original = self.completed_with_incomplete_capture(private_old_originals=True)
        journal, proof = self.bind_private_recovery(job, stage)
        self.record_zip_only_cleanup(job, stage)
        before = {path: path.read_bytes() for path in journal.parent.rglob("*") if path.is_file()}
        calls = (self.client.uploads, self.exporter.calls)
        plan = self.processor.prune_incomplete_captures(job["key"])
        self.assertEqual(plan["eligibleCaptures"], 1, plan)
        self.assertFalse((stage / "incomplete-prune.json").exists())
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 1, result)
        marker = json.loads((stage / "incomplete-prune.json").read_bytes())
        self.assertEqual(marker["privateRecoveryProof"], {"path": str(journal), "sha256": digest(journal.read_bytes())})
        self.assertEqual(before, {path: path.read_bytes() for path in journal.parent.rglob("*") if path.is_file()})
        self.assertEqual(calls, (self.client.uploads, self.exporter.calls))
        self.assertEqual(original.read_bytes(), b"retained paid source")
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"], dry_run=False)["removedBytes"], 0)

    def test_private_recovery_rejects_unbound_or_nonexact_proof_without_deleting_capture(self):
        job, stage, _ = self.completed_with_incomplete_capture(private_old_originals=True)
        journal, proof = self.bind_private_recovery(job, stage)
        before = {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
        mutations = [
            ("unfinalized", lambda p: p.update(schemaVersion="mira.course-archive.private-recovery.v1")),
            ("job", lambda p: p.update(jobKey="a" * 64)),
            ("old index", lambda p: p.update(indexSha256="a" * 64)),
            ("old manifest", lambda p: p.update(manifestSha256="a" * 64)),
            ("replacement", lambda p: p.update(replacementIndexSha256="a" * 64)),
            ("receipt", lambda p: p.update(receiptSha256="a" * 64)),
            ("provisional", lambda p: p.update(provisionalProofSha256="a" * 64)),
            ("missing original", lambda p: p["files"].pop()),
            ("duplicate", lambda p: p["files"].__setitem__(0, p["files"][1])),
            ("extra", lambda p: p["files"].append(deepcopy(p["files"][0]))),
            ("outside", lambda p: p["files"][0].update(recoveryPath=str(self.root / "needed.wav"))),
            ("wrong omission", lambda p: p["files"][0].update(matchedOmission={"sourceIdentity": "unrelated", "reason": "retained_private_runtime_recovery_backup"})),
            ("wrong omission reason", lambda p: p["files"][0]["matchedOmission"].update(reason="runtime_file_excluded")),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                changed = deepcopy(proof)
                mutate(changed)
                journal.write_bytes(encoded(changed))
                result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
                self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_private_recovery_invalid")
                self.assertEqual(before, {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()})
                self.assertFalse((stage / "incomplete-prune.json").exists())
        journal.unlink()
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)

    def test_private_recovery_cannot_replace_explicit_omission_or_verified_replacement_guards(self):
        job, stage, _ = self.completed_with_incomplete_capture(private_old_originals=True)
        self.bind_private_recovery(job, stage)
        replacement = self.processor._index(job)
        manifest = json.loads(Path(job["retainedManifestPath"]).read_bytes())
        variants = [[], [{"sourceIdentity": "different-original.js", "reason": "retained_private_runtime_recovery_backup"}],
                    [{**entry, "reason": "credential_or_runtime_file_excluded"} for entry in manifest["excludedFiles"]]]
        for omissions in variants:
            with self.subTest(omissions=omissions), self.assertRaisesRegex(ArchiveQueueError, "original_not_covered"):
                self.processor._incomplete_cleanup_plan(job, job["incompleteExports"][0], replacement,
                    {**manifest, "excludedFiles": omissions})
        saved = deepcopy(job)
        job["status"] = "uploaded"
        self.queue.save(job)
        with self.assertRaisesRegex(ArchiveQueueError, "replacement_not_complete"):
            self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.queue.save(saved)
        receipt = Path(saved["receiptPath"])
        receipt.write_bytes(receipt.read_bytes() + b" ")
        with self.assertRaisesRegex(ArchiveQueueError, "archive_receipt_changed"):
            self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertFalse((stage / "incomplete-prune.json").exists())

    def test_private_omission_paths_match_only_normalized_exact_files_or_segment_descendants(self):
        entry = {"sourceIdentity": "output/old-build/server/chunks/4839.js", "sha256": "a" * 64, "byteSize": 5}
        reason = "retained_private_runtime_recovery_backup"
        for root in ("output/old-build", entry["sourceIdentity"]):
            omission = {"sourceIdentity": root, "reason": reason}
            result = self.processor._private_recovery_omissions([entry], {"excludedFiles": [omission]})
            self.assertEqual(list(result.values()), [omission])
        for bad in ("output/old-build-evil/server/4839.js", "output/old-build/../4839.js",
                    "/output/old-build/4839.js", "output//old-build/4839.js", "output/./old-build/4839.js",
                    "output/old-build\\4839.js", "output/old-build/\n4839.js", "output/old-build/\u202e4839.js"):
            with self.subTest(source=bad), self.assertRaisesRegex(ArchiveQueueError, "original_not_covered"):
                self.processor._private_recovery_omissions([{**entry, "sourceIdentity": bad}], {
                    "excludedFiles": [{"sourceIdentity": "output/old-build", "reason": reason}]})
        for bad in ("output/old-build-evil", "output/old-build/..", "/output/old-build", "output//old-build",
                    "output\\old-build", "output/old-build\x00", "output/old-build/."):
            with self.subTest(omission=bad), self.assertRaisesRegex(ArchiveQueueError, "original_not_covered"):
                self.processor._private_recovery_omissions([entry], {
                    "excludedFiles": [{"sourceIdentity": bad, "reason": reason}]})
        with self.assertRaisesRegex(ArchiveQueueError, "original_not_covered"):
            self.processor._private_recovery_omissions([entry], {"excludedFiles": [
                {"sourceIdentity": "output/old-build", "reason": reason},
                {"sourceIdentity": "output/old-build", "reason": "retained_private_runtime_compile_staging"}]})

    def test_private_recovery_requires_independent_private_unchanged_bytes_not_original_presence(self):
        job, stage, _ = self.completed_with_incomplete_capture(private_old_originals=True)
        journal, proof = self.bind_private_recovery(job, stage)
        journal_raw = journal.read_bytes()
        journal.chmod(0o644)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        journal.chmod(0o600)
        provisional = Path(proof["provisionalProofPath"])
        provisional_raw = provisional.read_bytes()
        provisional.write_bytes(provisional_raw + b" ")
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        provisional.write_bytes(provisional_raw)
        journal.unlink()
        alias = self.root / "private-proof.json"
        alias.write_bytes(journal_raw)
        alias.chmod(0o600)
        journal.symlink_to(alias)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        journal.unlink()
        journal.write_bytes(journal_raw)
        journal.chmod(0o600)
        filename = Path(proof["files"][0]["recoveryPath"])
        saved = filename.read_bytes()
        source = self.root / proof["files"][0]["sourceIdentity"]
        self.assertEqual(source.read_bytes(), saved)
        filename.write_bytes(bytes([saved[0] ^ 1]) + saved[1:])
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        filename.unlink()
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        filename.symlink_to(source)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        filename.unlink()
        os.link(source, filename)
        filename.chmod(0o600)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        filename.unlink()
        filename.write_bytes(saved)
        filename.chmod(0o644)
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        filename.chmod(0o600)
        source.unlink()  # The verified independent backup is sufficient without a live source.
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 1)
        self.assertFalse((stage / "incomplete-prune.json").exists())

    def test_private_recovery_cleanup_resume_revalidates_bound_proof_and_retained_bytes(self):
        job, stage, _ = self.completed_with_incomplete_capture(private_old_originals=True)
        journal, proof = self.bind_private_recovery(job, stage)
        unlink = Path.unlink
        interrupted = False

        def interrupted_unlink(path, *args, **kwargs):
            nonlocal interrupted
            result = unlink(path, *args, **kwargs)
            if path.is_relative_to(stage / "课程资料") and not interrupted:
                interrupted = True
                raise OSError("interrupted after persisted private recovery cleanup intent")
            return result

        with patch.object(Path, "unlink", interrupted_unlink):
            first = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(first["eligibleCaptures"], 0)
        original_raw = journal.read_bytes()
        journal.write_bytes(original_raw + b" ")
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        journal.write_bytes(original_raw)
        filename = Path(proof["files"][0]["recoveryPath"])
        saved = filename.read_bytes()
        filename.write_bytes(bytes([saved[0] ^ 1]) + saved[1:])
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"])["eligibleCaptures"], 0)
        filename.write_bytes(saved)
        second = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(second["eligibleCaptures"], 1, second)
        self.assertEqual({p.name for p in stage.iterdir()}, {"index.json", "manifest.json", "incomplete-prune.json"})

    def test_inherited_audio_alias_covers_same_member_and_records_proof_without_touching_native_source(self):
        job, stage, _ = self.completed_with_incomplete_capture(inherited_audio_alias=True)
        before = self.audio_alias_fixture["physicalPath"].read_bytes()
        calls = (self.exporter.calls, self.client.uploads)
        dry = self.processor.prune_incomplete_captures(job["key"])
        self.assertEqual(dry["eligibleCaptures"], 1, dry)
        self.assertFalse((stage / "incomplete-prune.json").exists())
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 1, result)
        marker = json.loads((stage / "incomplete-prune.json").read_bytes())
        coverage = marker["audioAliasCoverage"]
        self.assertEqual(len(coverage), 1)
        self.assertEqual(coverage[0]["oldIdentity"], self.audio_alias_fixture["oldIdentity"])
        self.assertEqual(coverage[0]["newIdentity"], self.audio_alias_fixture["alias"]["originalReference"])
        self.assertEqual(coverage[0]["alias"], self.audio_alias_fixture["alias"])
        self.assertNotIn("privateRecoveryProof", marker)
        self.assertEqual(self.audio_alias_fixture["physicalPath"].read_bytes(), before)
        self.assertEqual(calls, (self.exporter.calls, self.client.uploads))
        self.assertEqual(self.processor.prune_incomplete_captures(job["key"], dry_run=False)["removedBytes"], 0)

    def test_inherited_audio_alias_rejects_missing_ambiguous_foreign_or_changed_mapping_and_evidence(self):
        job, stage, _ = self.completed_with_incomplete_capture(inherited_audio_alias=True)
        replacement = self.processor._index(job)
        manifest = json.loads(Path(job["retainedManifestPath"]).read_bytes())
        target = self.audio_alias_fixture["alias"]["archivePath"]

        def media(value):
            return next(entry for entry in value["files"] if entry["archivePath"] == target)

        def foreign(value):
            value["recoveredAliases"][0]["originalReference"] = value["recoveredAliases"][0]["originalReference"].replace("tbrev_", "foreign_")
            media(value)["sourceIdentity"] = value["recoveredAliases"][0]["originalReference"]

        def remove_paid_proof(value):
            alias = value["recoveredAliases"][0]
            paid = next(source for source in alias["evidence"] if "/formal-audio/jobs/tts/" in source)
            alias["evidence"].remove(paid)
            alias["evidenceSha256"].pop(paid)

        evidence = self.audio_alias_fixture["alias"]["evidence"][0]
        audio_evidence = next(source for source in self.audio_alias_fixture["alias"]["evidence"] if source.endswith(".wav"))
        mutations = [
            ("missing alias", lambda m: m.update(recoveredAliases=[])),
            ("duplicate alias", lambda m: m["recoveredAliases"].append(deepcopy(m["recoveredAliases"][0]))),
            ("different archive member", lambda m: m["recoveredAliases"][0].update(archivePath=target.replace("tbrev_", "foreign_"))),
            ("different stage URI", foreign),
            ("different SHA", lambda m: m["recoveredAliases"][0].update(sha256="f" * 64)),
            ("different size", lambda m: m["recoveredAliases"][0].update(byteSize=1)),
            ("different MIME", lambda m: m["recoveredAliases"][0].update(mimeType="audio/ogg")),
            ("wrong reason", lambda m: m["recoveredAliases"][0].update(recoveryReason="same_hash_nearby_stage")),
            ("wrong request", lambda m: m["recoveredAliases"][0].update(ttsRequestId="tbprev_" + "f" * 64)),
            ("new media is derived", lambda m: media(m).update(original=False)),
            ("new media changed", lambda m: media(m).update(sha256="f" * 64)),
            ("missing evidence hash", lambda m: m["recoveredAliases"][0]["evidenceSha256"].pop(evidence)),
            ("missing evidence member", lambda m: m.update(files=[e for e in m["files"] if e["archivePath"] != "原稿/" + evidence])),
            ("paid proof omitted", remove_paid_proof),
            ("evidence not original", lambda m: next(e for e in m["files"] if e["archivePath"] == "原稿/" + evidence).update(original=False)),
            ("evidence wrong source", lambda m: next(e for e in m["files"] if e["archivePath"] == "原稿/" + evidence).update(sourceIdentity="unrelated.json")),
            ("evidence invalid MIME", lambda m: next(e for e in m["files"] if e["archivePath"] == "原稿/" + audio_evidence).update(mimeType={"invalid": True})),
        ]
        before = {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()}
        for name, mutate in mutations:
            with self.subTest(name=name):
                changed = deepcopy(manifest)
                mutate(changed)
                with self.assertRaisesRegex(ArchiveQueueError, "original_not_covered"):
                    self.processor._incomplete_cleanup_plan(job, job["incompleteExports"][0], replacement, changed)
                self.assertFalse((stage / "incomplete-prune.json").exists())
                self.assertEqual(before, {p.relative_to(stage): p.read_bytes() for p in stage.rglob("*") if p.is_file()})

    def test_inherited_audio_alias_requires_exact_old_native_identity_and_original_member(self):
        job, stage, _ = self.completed_with_incomplete_capture(inherited_audio_alias=True)
        manifest = json.loads(Path(job["retainedManifestPath"]).read_bytes())
        files = self.processor._cleanup_manifest_files(manifest)
        old_manifest = json.loads((stage / "课程资料/manifest.json").read_bytes())
        old = next(entry for entry in old_manifest["files"] if entry["sourceIdentity"] == self.audio_alias_fixture["oldIdentity"])
        physical = old["archivePath"].removeprefix("媒体/")
        self.assertEqual(len(self.processor._inherited_audio_alias_coverage([{**old, "sourceIdentity": physical}], files, manifest)), 1)
        for change in ({"sourceIdentity": old["sourceIdentity"].replace("tbrev_", "foreign_")},
                       {"sourceIdentity": physical.replace("/audio/", "/audio/../audio/")},
                       {"archivePath": old["archivePath"].replace("tbrev_", "foreign_")},
                       {"sourceIdentity": "https://example.test" + old["sourceIdentity"]},
                       {"original": False}, {"mimeType": "audio/ogg"}):
            with self.subTest(change=change):
                self.assertEqual(self.processor._inherited_audio_alias_coverage([{**old, **change}], files, manifest), [])

    def test_inherited_audio_alias_cleanup_resumes_only_with_same_persisted_mapping(self):
        job, stage, _ = self.completed_with_incomplete_capture(inherited_audio_alias=True)
        unlink = Path.unlink
        interrupted = False

        def interrupted_unlink(path, *args, **kwargs):
            nonlocal interrupted
            result = unlink(path, *args, **kwargs)
            if path.is_relative_to(stage / "课程资料") and not interrupted:
                interrupted = True
                raise OSError("interrupted after persisted alias coverage intent")
            return result

        with patch.object(Path, "unlink", interrupted_unlink):
            first = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(first["eligibleCaptures"], 0)
        marker = stage / "incomplete-prune.json"
        raw = marker.read_bytes()
        changed = json.loads(raw)
        changed["audioAliasCoverage"][0]["oldIdentity"] = "wrong-old-identity"
        marker.write_bytes(encoded(changed))
        result = self.processor.prune_incomplete_captures(job["key"])
        self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_plan_changed")
        marker.write_bytes(raw)
        second = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(second["eligibleCaptures"], 1, second)
        self.assertEqual(self.audio_alias_fixture["physicalPath"].read_bytes(), self.audio_alias_fixture["originalBytes"])

    def test_incomplete_capture_unique_original_is_retained_without_touching_any_derivative(self):
        job, stage, _ = self.completed_with_incomplete_capture(unique_old_original=True)
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 0)
        self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_original_not_covered")
        self.assertTrue((stage / "课程资料" / "唯一原稿.json").is_file())
        self.assertTrue(any(stage.glob("*.zip")))

    def test_incomplete_cleanup_requires_acknowledged_receipt_and_exclusive_queue_lock(self):
        job, stage, _ = self.completed_with_incomplete_capture()
        with self.queue.lock(), self.assertRaisesRegex(ArchiveQueueError, "already_running"):
            self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        stored = json.loads((self.queue.items / (job["key"] + ".json")).read_bytes())
        stored["status"] = "uploaded"
        self.queue.save(stored)
        with self.assertRaisesRegex(ArchiveQueueError, "replacement_not_complete"):
            self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertTrue(any(stage.glob("*.zip")))

    def test_incomplete_cleanup_rejects_changed_payload_links_and_another_job_consumer(self):
        job, stage, original = self.completed_with_incomplete_capture()
        payload = stage / "课程资料" / "Native终态快照.json"
        saved = payload.read_bytes()
        payload.write_bytes(saved + b" ")
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 0)
        payload.write_bytes(saved)
        (stage / "asset-sources").symlink_to(original.parent, target_is_directory=True)
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["eligibleCaptures"], 0)
        (stage / "asset-sources").unlink()
        other = self.queue.enqueue({**self.pg(), "sourceDigest": "f" * 64})
        other["export"] = job["incompleteExports"][0]
        self.queue.save(other)
        result = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertEqual(result["captures"][0]["reason"], "archive_incomplete_cleanup_other_consumer")
        self.assertTrue(any(stage.glob("*.zip")))

    def test_incomplete_cleanup_resumes_after_an_interrupted_unlink(self):
        job, stage, _ = self.completed_with_incomplete_capture()
        unlink = Path.unlink
        interrupted = False

        def interrupted_unlink(path, *args, **kwargs):
            nonlocal interrupted
            result = unlink(path, *args, **kwargs)
            if path.is_relative_to(stage) and path.suffix == ".zip" and not interrupted:
                interrupted = True
                raise OSError("interrupted after persisted cleanup intent")
            return result

        with patch.object(Path, "unlink", interrupted_unlink):
            first = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertFalse(first["captures"][0]["eligible"])
        second = self.processor.prune_incomplete_captures(job["key"], dry_run=False)
        self.assertTrue(second["captures"][0]["eligible"], second)
        self.assertEqual({p.name for p in stage.iterdir()}, {"index.json", "manifest.json", "incomplete-prune.json"})
