"""Operator guards use synthetic bytes/clients; no real DB, HTTP or provider."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from scripts.verify_course_storage_runtime import (ExistingDeliveryCopies, ExistingMediaOnly,
    ReadOnlyConnection, ReadOnlyDatabase, ReadOnlyRuntime, TrackedRemoteStore,
    VerificationError, WriteGuard, private_output, runtime_read_url, source_audit, visual_fork)


class RemoteRuntimeVerificationTests(unittest.TestCase):
    def test_database_is_server_read_only_and_rejects_all_nonselect_or_mutating_select(self):
        connection = Mock()
        @contextmanager
        def transaction():
            yield connection
        database = Mock(transaction=transaction)
        with ReadOnlyDatabase(database).transaction() as reader:
            reader.execute("SELECT * FROM courses WHERE id=?", ("one",))
            for sql in ("UPDATE courses SET x=1", "DELETE FROM courses", "SELECT 1; DELETE FROM courses",
                        "SELECT * FROM courses FOR UPDATE", "SELECT x INTO OUTFILE '/tmp/x'", "SELECT GET_LOCK('x',1)"):
                with self.subTest(sql=sql), self.assertRaises(VerificationError):
                    reader.execute(sql)
            with self.assertRaises(VerificationError):
                reader.executescript("SELECT 1")
        self.assertEqual(connection.execute.call_count, 2)
        connection.execute.assert_any_call("SET TRANSACTION READ ONLY")
        connection.execute.assert_any_call("SELECT * FROM courses WHERE id=?", ("one",))

    def test_runtime_only_exposes_exact_get_and_never_provider_save_or_generation(self):
        client = Mock(base_url="http://127.0.0.1:3100")
        runtime = ReadOnlyRuntime(client)
        self.assertEqual(runtime.get_classroom("stage-one"), client.get_classroom.return_value)
        for name in ("save_preview_classroom", "start_formal_audio_tts", "start_formal_audio_asr", "generate"):
            with self.subTest(name=name), self.assertRaises(VerificationError):
                getattr(runtime, name)({})
            getattr(client, name).assert_not_called()

    def test_loopback_replica_changes_transport_without_changing_frozen_origin(self):
        client = Mock(base_url="http://127.0.0.1:3102")
        runtime = ReadOnlyRuntime(client, canonical_origin="http://127.0.0.1:3100")
        self.assertEqual(runtime.base_url, "http://127.0.0.1:3100")
        self.assertEqual(runtime.read_url, "http://127.0.0.1:3102")
        runtime.get_classroom("stage-frozen")
        client.get_classroom.assert_called_once_with("stage-frozen")
        self.assertEqual(runtime_read_url("http://127.0.0.1:3102/"), runtime.read_url)
        for value in ("https://127.0.0.1:3102", "http://storage.invalid:3102", "http://user:password@localhost:3102",
                      "http://127.0.0.1:3102/path", "http://localhost:3102?x=1", "http://127.0.0.1:999999"):
            with self.subTest(value=value), self.assertRaises(VerificationError):
                runtime_read_url(value)

    def test_source_unregistered_does_not_fall_back_but_new_private_candidate_may(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "repo"
            task = Path(temporary) / "task"
            original = project / "output/original.json"
            original.parent.mkdir(parents=True)
            original.write_text("stale local data")
            store = Mock()
            store.read_bytes.return_value = None
            tracked = TrackedRemoteStore(store, project, task)
            with self.assertRaises(VerificationError):
                tracked.read_bytes(original)
            self.assertEqual(tracked.unregistered_sources, {"output/original.json"})
            self.assertIsNone(tracked.read_bytes(task / "new-candidate.json"))
            with self.assertRaises(VerificationError):
                ExistingMediaOnly(Mock(read_bytes=Mock(return_value=None))).read(original)

    def test_signed_delivery_reuses_original_encoded_bytes_with_exact_hash_size_and_identity(self):
        original, delivered = b"approved source wav", b"original encoded mp3"
        checksum = hashlib.sha256(delivered).hexdigest()
        item = {"path": "/api/classroom-media/tbpub_" + "a" * 24 + "/audio/" + checksum + ".mp3",
            "sha256": checksum, "byteSize": len(delivered), "sourceSha256": hashlib.sha256(original).hexdigest()}
        store = Mock()
        store.read_bytes.return_value = delivered
        copy = ExistingDeliveryCopies({"media": [item]}, store)
        self.assertEqual(copy(".wav", original), (".mp3", delivered))
        self.assertEqual(store.read_bytes.call_args.kwargs,
            {"expected_sha256": checksum, "expected_bytes": len(delivered)})
        store.read_bytes.reset_mock()
        with self.assertRaises(VerificationError):
            copy(".wav", b"different source")
        store.read_bytes.assert_not_called()
        other = {**item, "sha256": "b" * 64}
        with self.assertRaises(VerificationError):
            ExistingDeliveryCopies({"media": [item, other]}, store)(".wav", original)
        store.read_bytes.assert_not_called()

    def test_write_guard_allows_only_task_artifacts_and_source_serialization_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            task, classroom = Path(temporary) / "task", Path(temporary) / "classrooms"
            guard = WriteGuard(task, classroom)
            guard.check("open", (str(task / "candidate.json"), "w", os.O_WRONLY | os.O_CREAT))
            guard.check("open", (str(classroom / "stage-one/textbook-preview-audio/operator.lock"), "a", os.O_RDWR | os.O_CREAT))
            guard.check("os.mkdir", (str(classroom / "stage-one/textbook-preview-audio"), 0o700, -1))
            for event, args in (("open", (str(classroom / "stage-one.json"), "w", os.O_WRONLY | os.O_CREAT)),
                                ("os.remove", (str(classroom / "stage-one.json"), -1)),
                                ("os.rename", (str(task / "x"), str(classroom / "stage-one.json"), -1, -1)),
                                ("urllib.Request", ("https://example.invalid", b"data", {}, "POST")),
                                ("subprocess.Popen", ("provider", [], None, None))):
                with self.subTest(event=event), self.assertRaises(VerificationError):
                    guard.check(event, args)

    def test_audit_discovery_uses_only_current_head_and_retains_original_signed_audit(self):
        registry, store = Mock(), Mock()
        registry.find_scopes.return_value = [{"bindings": [
            {"sourcePath": "output/lesson/audit.json", "sha256": "a" * 64},
            {"sourcePath": "output/lesson/audit.json", "sha256": "b" * 64}]}]
        store.resolve.return_value = {"sha256": "b" * 64}
        document = {"sha256": "c" * 64, "passed": True}
        store.read_bytes.return_value = json.dumps(document).encode()
        path, result = source_audit(registry, store, {"course_id": "course", "course_version": "1"},
            {"audioAudit": {"sha256": "c" * 64}}, "d" * 64)
        self.assertEqual(result, document)
        self.assertEqual(path.name, "audit.json")
        store.read_bytes.assert_called_once()
        self.assertEqual(store.read_bytes.call_args.kwargs["expected_sha256"], "b" * 64)
        store.read_bytes.return_value = json.dumps({**document, "sha256": "e" * 64}).encode()
        with self.assertRaises(VerificationError):
            source_audit(registry, store, {"course_id": "course", "course_version": "1"},
                {"audioAudit": {"sha256": "c" * 64}}, "d" * 64)

    def test_output_boundary_and_visual_fork_leave_original_teaching_content_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            task = Path(temporary)
            self.assertEqual(private_output(task / "candidate", task), (task / "candidate").resolve())
            with self.assertRaises(VerificationError):
                private_output(task.parent / "outside", task)
            (task / "linked").symlink_to(task.parent, target_is_directory=True)
            with self.assertRaises(VerificationError):
                private_output(task / "linked/candidate", task)
        parent = {"build": {"content_key": "a" * 64, "teaching_revision": "1"},
            "preview": {"classroom_json": '{"id":"one","scenes":[{"id":"s","type":"interactive","content":{"html":"<p>original</p>"},"actions":[{"type":"speech","text":"original"}]}]}'}}
        before = deepcopy(parent)
        patch, visual = visual_fork(parent, "storage-proof-one")
        self.assertEqual(parent, before)
        self.assertEqual(patch["changes"], [])
        self.assertTrue(visual["changes"][0]["html"].startswith("<p>original</p>\n<!--"))
        with self.assertRaises(VerificationError):
            visual_fork(parent, "1")


if __name__ == "__main__":
    unittest.main()
