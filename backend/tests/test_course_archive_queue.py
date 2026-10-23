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

    def completed_with_incomplete_capture(self, *, unique_old_original=False):
        from services.course_archive_exporter import CourseArchiveExporter

        class RecoverableExporter(CourseArchiveExporter):
            incomplete = True

            def export_snapshot(inner, snapshot, **options):
                if inner.incomplete:
                    snapshot.missing_sources.append({"kind": "media", "sourceIdentity": "needed.wav"})
                    if unique_old_original:
                        snapshot.documents["唯一原稿.json"] = '{"unique":"must survive"}'
                return super().export_snapshot(snapshot, **options)

        exporter = RecoverableExporter(project_root=self.root, media_store=Mock(),
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
