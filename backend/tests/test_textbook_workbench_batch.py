"""Provider-free tests for the v4 reviewed-draft batch coordinator."""
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from services.textbook_workbench_batch import (
    REQUEST_SCHEMA, TextbookWorkbenchBatch, _ReadOnlyWorkbenchClient, sha,
)
from integrations.openmaic_workbench_client import WorkbenchError
from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring


def binding(node: str, *, subject="chinese") -> dict:
    return {"editionId": "edition-one", "revisionId": "revision-one", "nodeId": node,
            "unitId": "unit-one", "unitTitle": "第一单元", "lessonTitle": node,
            "gradeCode": "primary_1", "subject": subject, "volume": "upper",
            "schoolSystem": "six_year"}


class FakeAuthoring:
    def __init__(self, output_root: Path):
        self.output_root = output_root
        self.fail_prepare_nodes = set()
        self.crash_after_marker_nodes = set()
        self.prepare_calls = []
        self.run_calls = []
        self.start_calls = []

    def prepare(self, draft_path, *, teaching_revision="1"):
        draft = json.loads(Path(draft_path).read_text())
        node = draft["binding"]["nodeId"]
        self.prepare_calls.append((node, str(Path(draft_path)), teaching_revision))
        if node in self.fail_prepare_nodes:
            raise ValueError("synthetic unsafe detail must not escape")
        job = (self.output_root / draft["binding"]["editionId"] / node
               / ("teaching-" + teaching_revision) / "authoring-job")
        job.mkdir(parents=True, exist_ok=True)
        (job / "state.json").write_text(json.dumps({"status": "prepared"}))
        return {"jobDirectory": str(job), "status": "prepared", "binding": draft["binding"],
                "teachingRevision": teaching_revision,
                "requestSha256": "a" * 64, "draftSha256": sha(Path(draft_path).read_bytes())}

    def run(self, job, *, start=False):
        job = Path(job)
        node = job.parent.parent.name
        self.run_calls.append((node, start))
        state = json.loads((job / "state.json").read_text())
        if start:
            self.start_calls.append(node)
            (job / "dispatch.json").write_text(json.dumps({"action": "single_post_intent"}))
            if node in self.crash_after_marker_nodes:
                raise RuntimeError("raw simulated transport secret")
            state.update(status="session_queued", sessionId="session-" + node,
                         sessionStatus="queued")
            (job / "state.json").write_text(json.dumps(state))
        return {"jobDirectory": str(job), "binding": binding(node),
                "teachingRevision": "1", **state}


def watch_summary(states, *, blockers=(), external=0, external_statuses=None):
    entries = []
    for index, status in enumerate(states):
        row = {"entryId": (str(index) * 64)[:64], "status": status}
        if status == "saved_stage_available":
            row["savedStages"] = [{"stageId": "stage-" + str(index), "sha256": "a" * 64}]
        entries.append(row)
    active = sum(status in {"session_queued", "session_running"} for status in states)
    counts = {}
    for status in states:
        counts[status] = counts.get(status, 0) + 1
    return {"batchId": "wave", "batchSha256": "b" * 64, "entries": entries,
            "entryCount": len(entries), "statusCounts": counts,
            "occupiedAuthorSessions": active + external,
            "externalOccupiedAuthorSessions": external,
            "externalOccupiedAuthorSessionStatusCounts": external_statuses or {},
            "maximumConcurrentAuthorSessions": 2,
            "dispatchBlockers": list(blockers), "dispatchBlockerCount": len(blockers),
            "generatedDraftsAreReviewed": False, "audioCompleted": False,
            "publicationAllowed": False, "studentDeliveryAllowed": False}


class ScriptedWatchBatch:
    def __init__(self, statuses, starts):
        self.statuses = list(statuses)
        self.starts = list(starts)
        self.status_calls = 0
        self.start_calls = []

    def status(self):
        self.status_calls += 1
        return self.statuses.pop(0)

    def start_bounded(self, **kwargs):
        self.start_calls.append(kwargs)
        return self.starts.pop(0)


@contextmanager
def registry_originals(originals):
    """Serve absent original files through the same registry-aware boundary."""
    from services import textbook_workbench_batch as module

    originals = {path.resolve(): value for path, value in originals.items()}
    real_glob, real_exists, real_text = module.course_glob, module.course_exists, module.course_text

    def discover(directory, pattern, *, recursive=False):
        local = set(real_glob(directory, pattern, recursive=recursive))
        return iter(sorted(local | {path for path in originals
            if path.is_relative_to(Path(directory).resolve()) and path.name == pattern}))

    def read(path):
        key = Path(path).resolve()
        if key not in originals:
            return real_text(path)
        value = originals[key]
        if isinstance(value, Exception):
            raise value
        return value

    with ExitStack() as stack:
        stack.enter_context(patch.object(module, "course_glob", side_effect=discover))
        stack.enter_context(patch.object(module, "course_exists",
            side_effect=lambda path: Path(path).resolve() in originals or real_exists(path)))
        stack.enter_context(patch.object(module, "course_text", side_effect=read))
        yield


class WorkbenchBatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.queue = self.root / "queue"
        self.output = self.root / "operator"
        self.authoring = FakeAuthoring(self.output)
        self.service = TextbookWorkbenchBatch(self.queue, self.authoring)
        self.validate = patch(
            "services.textbook_workbench_batch.validate_draft",
            side_effect=lambda draft, check_current_teacher=True: draft["binding"],
        )
        self.validate.start()
        self.addCleanup(self.validate.stop)

    def make_request(self, nodes=("node-a", "node-b", "node-c"), *, duplicate_job=False):
        entries = []
        for index, node in enumerate(nodes):
            draft = {"binding": binding(node, subject="math" if duplicate_job and index else "chinese"),
                     "request": "reviewed " + node}
            path = self.root / (node + "-" + str(index) + ".json")
            path.write_text(json.dumps(draft, ensure_ascii=False))
            entries.append({"draftPath": path.name, "teachingRevision": "1"})
        request = self.root / "batch-request.json"
        request.write_text(json.dumps({"schemaVersion": REQUEST_SCHEMA, "batchId": "grade1-pilot",
            "scope": {"gradeCode": "primary_1"}, "maximumConcurrentAuthorSessions": 2,
            "entries": entries}, ensure_ascii=False))
        return request

    def init(self, nodes=("node-a", "node-b", "node-c")):
        result = self.service.initialize(self.make_request(nodes))
        manifest = json.loads((self.queue / "batch.json").read_text())
        return result, manifest

    def terminal_fixture(self):
        job = self.output / "old-edition" / "old-node" / "teaching-1" / "authoring-job"
        job.mkdir(parents=True)
        state = {"status": "session_running", "sessionId": "old-session"}
        prompt = "the complete original request"
        frozen = {"requestSha256": sha(prompt.encode()), "payloadSha256": "b" * 64,
                  "skillIds": ["original-skill"]}
        marker = {"action": "single_post_intent", "requestSha256": frozen["requestSha256"],
                  "payloadSha256": frozen["payloadSha256"], "ownerFingerprint": "a" * 64}
        for name, value in (("state.json", state), ("dispatch.json", marker),
                            ("draft.json", {"request": prompt}), ("frozen.json", frozen)):
            (job / name).write_text(json.dumps(value))
        (job / "owner.cookies").write_text("private test identity")
        self.authoring.origin = "http://127.0.0.1:3100"
        self.authoring._load = Mock(return_value=(frozen, {"request": prompt}, state))
        self.authoring._material_payload = Mock(return_value=({}, frozen))
        self.authoring._match = TextbookWorkbenchAuthoring._match
        self.authoring._verify_session_materials = TextbookWorkbenchAuthoring._verify_session_materials
        self.authoring._recover = TextbookWorkbenchAuthoring._recover.__get__(self.authoring)
        client = Mock()
        client.owner_fingerprint.return_value = "a" * 64
        client.session.return_value = {"id": "old-session", "prompt": prompt,
                                       "skillId": "original-skill", "status": "succeeded"}
        return job, state, frozen, marker, client

    def test_verified_old_terminal_frees_slot_without_modifying_job(self):
        job, _, _, _, client = self.terminal_fixture()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in job.iterdir()}
        with patch("services.textbook_workbench_batch._ReadOnlyWorkbenchClient", return_value=client):
            with self.service._dispatch_locked():
                for status in ("succeeded", "failed", "cancelled"):
                    client.session.return_value["status"] = status
                    self.assertEqual(self.service._global_occupied_jobs([]), [])
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in job.iterdir()})
        self.assertEqual(client.session.call_count, 3)
        client.session.assert_called_with("old-session")
        client.create_session.assert_not_called()
        client.upload_material.assert_not_called()

    def test_external_running_or_unverifiable_stays_occupied(self):
        job, _, frozen, marker, client = self.terminal_fixture()
        with patch("services.textbook_workbench_batch._ReadOnlyWorkbenchClient", return_value=client):
            for mode in ("running", "identity", "session_id", "prompt", "request", "payload",
                         "owner", "materials_owner", "materials_binding", "get_error", "load_error"):
                with self.subTest(mode=mode):
                    client.session.return_value.update(status="running", skillId="original-skill",
                        id="old-session", prompt="the complete original request")
                    client.session.side_effect = None
                    self.authoring._load.side_effect = None
                    marker["ownerFingerprint"] = "a" * 64
                    marker["requestSha256"] = frozen["requestSha256"]
                    marker["payloadSha256"] = frozen["payloadSha256"]
                    marker.pop("materialsSha256", None)
                    for key in ("materialsOwnerFingerprint", "materialsSha256", "materialTitles", "materialBindings"):
                        frozen.pop(key, None)
                    if mode != "running":
                        client.session.return_value["status"] = "succeeded"
                    if mode == "identity":
                        client.session.return_value["skillId"] = "wrong-skill"
                    elif mode == "session_id":
                        client.session.return_value["id"] = "other-session"
                    elif mode == "prompt":
                        client.session.return_value["prompt"] = "different request"
                    elif mode == "request":
                        marker["requestSha256"] = "c" * 64
                    elif mode == "payload":
                        marker["payloadSha256"] = "c" * 64
                    elif mode == "owner":
                        marker["ownerFingerprint"] = "c" * 64
                    elif mode == "materials_owner":
                        frozen["materialsOwnerFingerprint"] = "c" * 64
                    elif mode == "materials_binding":
                        frozen.update(materialsOwnerFingerprint="a" * 64, materialsSha256="d" * 64,
                                      materialTitles={"asset": "title"}, materialBindings=[{"materialId": "asset"}])
                        marker["materialsSha256"] = "d" * 64
                        client.stage_events.return_value = [{"type": "user_message", "data": {
                            "text": "the complete original request", "materials": []}}]
                    elif mode == "get_error":
                        client.session.side_effect = WorkbenchError("unavailable", "offline")
                    elif mode == "load_error":
                        self.authoring._load.side_effect = ValueError("bad frozen data")
                    (job / "dispatch.json").write_text(json.dumps(marker))
                    occupied = self.service._global_occupied_jobs([])
                    self.assertEqual(len(occupied), 1)
                    self.assertEqual(occupied[0]["jobDirectory"], str(job.resolve()))
        client.create_session.assert_not_called()
        client.upload_material.assert_not_called()

    def test_read_only_client_get_does_not_rewrite_cookie_and_refuses_post(self):
        cookie = self.root / "owner.cookies"
        cookie.write_text("# Netscape HTTP Cookie File\nlocalhost\tFALSE\t/\tFALSE\t0\t"
                          "anonymous_id\t123e4567-e89b-42d3-a456-426614174000\n")
        os.chmod(cookie, 0o600)
        before = (cookie.read_bytes(), cookie.stat().st_mtime_ns, cookie.stat().st_mode)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"id":"session","status":"succeeded"}'
        opener = Mock()
        opener.open.return_value = response
        with patch("services.textbook_workbench_batch.build_opener", return_value=opener):
            client = _ReadOnlyWorkbenchClient("http://localhost:3100", cookie)
            self.assertEqual(client.session("session")["status"], "succeeded")
            with self.assertRaises(WorkbenchError):
                client.create_session({"prompt": "must not post"})
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(opener.open.call_args.args[0].get_method(), "GET")
        self.assertEqual(before, (cookie.read_bytes(), cookie.stat().st_mtime_ns, cookie.stat().st_mode))

    def test_init_freezes_exact_private_snapshots_and_rejects_same_job_twice(self):
        result, manifest = self.init(("node-a", "node-b"))
        self.assertEqual(result["entryCount"], 2)
        self.assertEqual(result["maximumConcurrentAuthorSessions"], 2)
        self.assertFalse(result["publicationAllowed"])
        for row in manifest["entries"]:
            draft = self.queue / "entries" / row["entryId"] / "draft.json"
            self.assertEqual(stat.S_IMODE(draft.stat().st_mode), 0o600)
            self.assertEqual(sha(draft.read_bytes()), row["draftSha256"])
        self.authoring.prepare_calls.clear()
        # Changing the source after init cannot change what prepare consumes.
        (self.root / "node-a-0.json").write_text(json.dumps({"binding": binding("changed")}))
        self.service.prepare(limit=1)
        self.assertEqual(self.authoring.prepare_calls[0][0], "node-a")
        self.assertIn(str(self.queue / "entries"), self.authoring.prepare_calls[0][1])

        duplicate = self.make_request(("same", "same"), duplicate_job=True)
        other = TextbookWorkbenchBatch(self.root / "duplicate", self.authoring)
        with self.assertRaisesRegex(ValueError, "duplicate_job_path"):
            other.initialize(duplicate)

    def test_snapshot_change_fails_before_single_course_service(self):
        _, manifest = self.init(("node-a",))
        row = manifest["entries"][0]
        snapshot = self.queue / "entries" / row["entryId"] / "draft.json"
        snapshot.write_text(json.dumps({"binding": binding("node-a"), "request": "changed"}))
        with self.assertRaisesRegex(ValueError, "snapshot_changed"):
            self.service.prepare(limit=1)
        self.assertEqual(self.authoring.prepare_calls, [])

    def test_scope_typo_and_queue_directory_symlink_are_rejected(self):
        request = self.make_request(("node-a",))
        value = json.loads(request.read_text())
        value["scope"]["gradeCod"] = value["scope"].pop("gradeCode")
        request.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "scope_key_invalid"):
            TextbookWorkbenchBatch(self.root / "bad-scope", self.authoring).initialize(request)

        request = self.make_request(("node-b",))
        real = self.root / "real-queue"
        real.mkdir(mode=0o700)
        link = self.root / "queue-link"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "directory_symlink_forbidden"):
            TextbookWorkbenchBatch(link, self.authoring).initialize(request)

        poisoned = self.root / "poisoned-queue"
        poisoned.mkdir(mode=0o700)
        outside = self.root / "outside-entries"
        outside.mkdir(mode=0o700)
        (poisoned / "entries").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "entries_directory_invalid"):
            TextbookWorkbenchBatch(poisoned, self.authoring).initialize(request)

        request_link = self.root / "request-link.json"
        request_link.symlink_to(request)
        with self.assertRaisesRegex(ValueError, "request_invalid"):
            TextbookWorkbenchBatch(self.root / "linked-request", self.authoring).initialize(request_link)

    def test_prepare_is_provider_free_and_isolates_one_entry_failure(self):
        self.init()
        self.authoring.fail_prepare_nodes.add("node-b")
        result = self.service.prepare(limit=3)
        self.assertEqual(len(result["attempts"]), 3)
        self.assertEqual(result["providerCalls"], 0)
        self.assertEqual(self.authoring.start_calls, [])
        self.assertEqual(self.authoring.run_calls, [])
        self.assertEqual([row["status"] for row in result["attempts"]],
                         ["prepared", "preparation_blocked", "prepared"])
        blocked = result["attempts"][1]
        self.assertEqual(blocked["error"], "workbench_batch_entry_failed")
        self.assertNotIn("unsafe detail", json.dumps(blocked))

    def test_unknown_dispatch_and_queued_session_each_occupy_a_global_slot(self):
        _, manifest = self.init()
        self.service.prepare(limit=3)
        first = manifest["entries"][0]
        prepared = json.loads((self.queue / "entries" / first["entryId"] / "prepared.json").read_text())
        job = Path(prepared["jobDirectory"])
        (job / "state.json").write_text(json.dumps({"status": "dispatch_unknown"}))
        (job / "dispatch.json").write_text("{}")

        result = self.service.start_bounded(max_starts=2,
                                            confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(self.authoring.start_calls, ["node-b"])
        self.assertEqual(result["summary"]["occupiedAuthorSessions"], 2)
        again = self.service.start_bounded(max_starts=2,
                                           confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(again["startAttempts"], [])
        self.assertEqual(self.authoring.start_calls, ["node-b"])
        self.assertNotIn("node-a", self.authoring.start_calls)

    def test_marker_only_job_outside_batch_consumes_capacity(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        external = self.output / "other-edition" / "other-node" / "teaching-1" / "authoring-job"
        external.mkdir(parents=True)
        # A crash after the permanent dispatch marker but before state.json is
        # still an unresolved external session and must consume one slot.
        (external / "dispatch.json").write_text("{}")
        result = self.service.start_bounded(max_starts=2,
                                            confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(len(result["startAttempts"]), 1)
        self.assertEqual(result["summary"]["externalOccupiedAuthorSessions"], 1)
        self.assertEqual(result["summary"]["occupiedAuthorSessions"], 2)
        self.assertEqual(result["summary"]["externalOccupiedAuthorSessionStatusCounts"],
                         {"unreadable_unknown": 1})
        self.assertIn({"scope": "external_authoring", "status": "unreadable_unknown",
                       "reason": "external_dispatch_reconciliation_required"},
                      result["summary"]["dispatchBlockers"])

    def test_strict_start_blocks_external_running_state_with_saved_error(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        external = self.output / "other-edition" / "other-node" / "teaching-1" / "authoring-job"
        external.mkdir(parents=True)
        (external / "state.json").write_text(json.dumps(
            {"status": "session_running", "error": "provider_transport_failed"}))
        result = self.service.start_bounded(max_starts=2,
            confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
        self.assertEqual(result["startAttempts"], [])
        self.assertEqual(self.authoring.start_calls, [])
        self.assertIn({"scope": "external_authoring", "status": "session_running",
                       "reason": "external_dispatch_reconciliation_required"},
                      result["summary"]["dispatchBlockers"])

    def test_registry_only_running_job_consumes_a_slot_before_start(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        external = self.output / "other-edition" / "archived-node" / "teaching-1" / "authoring-job"
        external.mkdir(parents=True)
        (external / "owner.cookies").write_text("private identity remains local")
        originals = {external / "state.json": json.dumps({"status": "session_running"}),
                     external / "dispatch.json": "{}"}
        with registry_originals(originals):
            result = self.service.start_bounded(max_starts=2,
                confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
        self.assertEqual(len(result["startAttempts"]), 1)
        self.assertEqual(result["summary"]["occupiedAuthorSessions"], 2)
        self.assertEqual(result["summary"]["externalOccupiedAuthorSessions"], 1)
        self.assertEqual(result["summary"]["externalOccupiedAuthorSessionStatusCounts"],
                         {"session_running": 1})
        self.assertFalse((external / "state.json").exists())
        self.assertFalse((external / "dispatch.json").exists())

    def test_registry_only_marker_unreadable_or_nondict_state_stays_occupied(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        external = self.output / "other-edition" / "archived-node" / "teaching-1" / "authoring-job"
        for state in (None, "not-json", "[]", RuntimeError("private remote credential detail")):
            with self.subTest(state=type(state).__name__):
                originals = {external / "dispatch.json": "{}"}
                if state is not None:
                    originals[external / "state.json"] = state
                with registry_originals(originals):
                    result = self.service.start_bounded(max_starts=2,
                        confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
                self.assertEqual(result["startAttempts"], [])
                self.assertEqual(result["summary"]["externalOccupiedAuthorSessions"], 1)
                self.assertEqual(result["summary"]["externalOccupiedAuthorSessionStatusCounts"],
                                 {"unreadable_unknown": 1})
                self.assertNotIn("credential", json.dumps(result))
                self.assertEqual(self.authoring.start_calls, [])

    def test_registry_inventory_failure_stops_before_post_with_safe_error(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        with patch("services.textbook_workbench_batch.course_glob",
                   side_effect=RuntimeError("private database endpoint detail")):
            with self.assertRaisesRegex(ValueError, "^workbench_batch_authoring_inventory_unavailable$"):
                self.service.start_bounded(max_starts=2,
                    confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
        self.assertEqual(self.authoring.start_calls, [])

    def test_two_batches_cannot_admit_more_than_two_sessions_concurrently(self):
        _, first_manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        second = TextbookWorkbenchBatch(self.root / "second-queue", self.authoring)
        second.initialize(self.make_request(("node-c", "node-d")))
        second.prepare(limit=2)
        second_manifest = second._manifest()
        scan_complete, release_scan = threading.Event(), threading.Event()
        original_scan = self.service._global_occupied_jobs

        def pause_after_scan(results):
            occupied = original_scan(results)
            if not scan_complete.is_set():
                scan_complete.set()
                if not release_scan.wait(timeout=5):
                    raise RuntimeError("test admission barrier timed out")
            return occupied

        with patch.object(self.service, "_global_occupied_jobs", side_effect=pause_after_scan), \
                ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.service.start_bounded, max_starts=2,
                confirm_batch_sha256=first_manifest["batchSha256"])
            try:
                self.assertTrue(scan_complete.wait(timeout=5))
                with self.assertRaisesRegex(ValueError, "dispatch_operator_already_running"):
                    second.start_bounded(max_starts=2,
                        confirm_batch_sha256=second_manifest["batchSha256"])
                self.assertEqual(self.authoring.start_calls, [])
            finally:
                release_scan.set()
            self.assertEqual(len(first.result(timeout=5)["startAttempts"]), 2)

        # Once the shared lock is released, the second batch can safely retry;
        # the two admitted sessions are now visible and consume both slots.
        resumed = second.start_bounded(max_starts=2,
            confirm_batch_sha256=second_manifest["batchSha256"])
        self.assertEqual(resumed["startAttempts"], [])
        self.assertEqual(resumed["summary"]["occupiedAuthorSessions"], 2)
        self.assertEqual(self.authoring.start_calls, ["node-a", "node-b"])

    def test_dispatch_lock_contention_makes_zero_posts_and_release_allows_retry(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        with self.service._dispatch_locked():
            with self.assertRaisesRegex(ValueError, "dispatch_operator_already_running"):
                self.service.start_bounded(max_starts=2,
                    confirm_batch_sha256=manifest["batchSha256"])
            self.assertEqual(self.authoring.run_calls, [])
            self.assertEqual(self.authoring.start_calls, [])
        result = self.service.start_bounded(max_starts=2,
            confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(len(result["startAttempts"]), 2)
        self.assertEqual(self.authoring.start_calls, ["node-a", "node-b"])

    def test_dispatch_lock_rejects_symlink_nonregular_and_public_files_before_post(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        lock = self.output / ".workbench-dispatch.lock"
        outside = self.root / "outside-lock"
        outside.write_text("preserve unrelated bytes")
        lock.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "dispatch_lock_invalid"):
            self.service.start_bounded(max_starts=2,
                confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(outside.read_text(), "preserve unrelated bytes")
        lock.unlink()
        lock.mkdir()
        with self.assertRaisesRegex(ValueError, "dispatch_lock_invalid"):
            self.service.start_bounded(max_starts=2,
                confirm_batch_sha256=manifest["batchSha256"])
        lock.rmdir()
        lock.write_text("")
        lock.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "dispatch_lock_invalid"):
            self.service.start_bounded(max_starts=2,
                confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(self.authoring.run_calls, [])
        self.assertEqual(self.authoring.start_calls, [])

    def test_strict_start_requires_ready_materials_and_consistent_prepared_identity(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        prepared = json.loads((self.queue / "entries" / manifest["entries"][0]["entryId"]
                               / "prepared.json").read_text())
        state_path = Path(prepared["jobDirectory"]) / "state.json"
        for state, reason in (({"status": "prepared", "materialsStatus": "upload_unknown"},
                               "material_preparation_required"),
                              ({"status": "prepared", "sessionId": "existing-session"},
                               "prepared_session_identity_conflict")):
            with self.subTest(state=state):
                state_path.write_text(json.dumps(state))
                result = self.service.start_bounded(max_starts=2,
                    confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
                self.assertEqual(result["startAttempts"], [])
                self.assertEqual(self.authoring.start_calls, [])
                self.assertIn(reason, [row["reason"] for row in result["summary"]["dispatchBlockers"]])

    def test_exception_after_marker_stays_unknown_and_is_never_reposted(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        self.authoring.crash_after_marker_nodes.add("node-a")
        result = self.service.start_bounded(max_starts=1,
                                            confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(result["startAttempts"][0]["status"], "dispatch_unknown")
        self.assertEqual(result["startAttempts"][0]["error"], "workbench_batch_entry_failed")
        self.assertNotIn("transport secret", json.dumps(result))
        self.service.start_bounded(max_starts=2,
                                   confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(self.authoring.start_calls.count("node-a"), 1)

    def test_strict_start_stops_before_or_immediately_after_a_blocker(self):
        _, manifest = self.init(("node-a", "node-b", "node-c"))
        self.service.prepare(limit=3)
        first = manifest["entries"][0]
        prepared = json.loads((self.queue / "entries" / first["entryId"] / "prepared.json").read_text())
        (Path(prepared["jobDirectory"]) / "state.json").write_text(
            json.dumps({"status": "session_failed"}))
        blocked = self.service.start_bounded(max_starts=2,
            confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
        self.assertEqual(blocked["startAttempts"], [])
        self.assertEqual(self.authoring.start_calls, [])
        self.assertEqual(blocked["summary"]["dispatchBlockers"][0]["reason"], "generation_failed")

        # A clean retry wave may start one item, but an unknown first dispatch
        # must prevent a second POST in that same strict action.
        (Path(prepared["jobDirectory"]) / "state.json").write_text(json.dumps({"status": "prepared"}))
        self.authoring.crash_after_marker_nodes.add("node-a")
        failed = self.service.start_bounded(max_starts=2,
            confirm_batch_sha256=manifest["batchSha256"], stop_on_blockers=True)
        self.assertEqual(self.authoring.start_calls, ["node-a"])
        self.assertEqual(len(failed["startAttempts"]), 1)
        self.assertEqual(failed["summary"]["dispatchBlockers"][0]["reason"],
                         "dispatch_reconciliation_required")

    def test_confirmation_hold_and_prepared_state_are_hard_start_gates(self):
        _, manifest = self.init(("node-a", "node-b"))
        self.service.prepare(limit=2)
        first, second = [row["entryId"] for row in manifest["entries"]]
        with self.assertRaisesRegex(ValueError, "confirmation_mismatch"):
            self.service.start_bounded(max_starts=1, confirm_batch_sha256="0" * 64)
        receipt = TextbookWorkbenchBatch(self.queue).hold([first], reason="operator review")
        self.assertEqual(receipt["providerCalls"], 0)
        result = self.service.start_bounded(max_starts=2,
                                            confirm_batch_sha256=manifest["batchSha256"])
        self.assertEqual(self.authoring.start_calls, ["node-b"])
        with self.assertRaisesRegex(ValueError, "already_exists_differently"):
            TextbookWorkbenchBatch(self.queue).hold([first], reason="changed")
        with self.assertRaisesRegex(ValueError, "cannot_cancel_dispatched"):
            TextbookWorkbenchBatch(self.queue).hold([second], reason="too late")
        self.assertEqual(result["summary"]["maximumConcurrentAuthorSessions"], 2)

    def test_hold_rejects_nonprepared_state_even_without_marker_or_session_id(self):
        _, manifest = self.init(("node-a",))
        self.service.prepare(limit=1)
        row = manifest["entries"][0]
        prepared = json.loads((self.queue / "entries" / row["entryId"] / "prepared.json").read_text())
        (Path(prepared["jobDirectory"]) / "state.json").write_text(
            json.dumps({"status": "session_running"}))
        with self.assertRaisesRegex(ValueError, "cannot_cancel_dispatched"):
            TextbookWorkbenchBatch(self.queue).hold([row["entryId"]], reason="late")


class WorkbenchBatchCliTest(unittest.TestCase):
    def test_init_and_hold_do_not_load_runtime_or_database(self):
        from scripts import run_textbook_workbench_batch as cli
        batch = Mock()
        batch.initialize.return_value = {"entryCount": 1}
        batch.hold.return_value = {"holds": []}
        with patch.object(cli, "TextbookWorkbenchBatch", return_value=batch), \
                patch.object(cli, "_authoring") as authoring, redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["init", "--queue-directory", "/queue",
                                      "--manifest", "/manifest"]), 0)
            self.assertEqual(cli.main(["hold", "--queue-directory", "/queue",
                                      "--entry-id", "a" * 64, "--reason", "review"]), 0)
            authoring.assert_not_called()

    def test_start_requires_explicit_bound_and_batch_hash_before_config(self):
        from scripts import run_textbook_workbench_batch as cli
        with patch.object(cli, "_authoring") as authoring, redirect_stderr(io.StringIO()):
            for args in (["start-bounded", "--queue-directory", "/queue"],
                         ["start-bounded", "--queue-directory", "/queue", "--max-starts", "3",
                          "--confirm-batch-sha256", "a" * 64],
                         ["status", "--queue-directory", "/queue", "--max-starts", "1"]):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    cli.main(args)
            authoring.assert_not_called()

    def test_valid_start_passes_exact_explicit_confirmation(self):
        from scripts import run_textbook_workbench_batch as cli
        batch = Mock()
        batch.start_bounded.return_value = {"startAttempts": []}
        authoring = Mock()
        with patch.object(cli, "_authoring", return_value=authoring), \
                patch.object(cli, "TextbookWorkbenchBatch", return_value=batch), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["start-bounded", "--queue-directory", "/queue",
                                      "--max-starts", "2", "--confirm-batch-sha256", "b" * 64]), 0)
        batch.start_bounded.assert_called_once_with(max_starts=2, confirm_batch_sha256="b" * 64)

    def test_watch_refills_two_slots_one_at_a_time_and_completes(self):
        from scripts.run_textbook_workbench_batch import _watch_bounded
        batch = ScriptedWatchBatch(
            statuses=[
                watch_summary(["prepared", "prepared", "prepared"]),
                watch_summary(["saved_stage_available", "session_running", "prepared"]),
                watch_summary(["saved_stage_available", "saved_stage_available",
                               "saved_stage_available"]),
            ],
            starts=[
                {"startAttempts": [{"entryId": "0"}],
                 "summary": watch_summary(["session_running", "prepared", "prepared"])},
                {"startAttempts": [{"entryId": "1"}],
                 "summary": watch_summary(["session_running", "session_running", "prepared"])},
                {"startAttempts": [{"entryId": "2"}],
                 "summary": watch_summary(["saved_stage_available", "session_running",
                                           "session_running"])},
            ],
        )
        waits, heartbeats = [], []
        result = _watch_bounded(batch, max_starts=2, max_total_starts=3,
            confirm_batch_sha256="b" * 64, poll_seconds=15,
            wait=lambda seconds, _stop: waits.append(seconds), emit=heartbeats.append)
        self.assertTrue(result["ok"])
        self.assertEqual(result["watchStatus"], "completed")
        self.assertEqual(result["startsThisInvocation"], 3)
        self.assertEqual(waits, [15, 15])
        self.assertEqual(len(heartbeats), 2)
        self.assertEqual([call["max_starts"] for call in batch.start_calls], [1, 1, 1])
        self.assertTrue(all(call["stop_on_blockers"] for call in batch.start_calls))

    def test_watch_budget_exhaustion_polls_paid_work_to_terminal_without_extra_post(self):
        from scripts.run_textbook_workbench_batch import _watch_bounded
        batch = ScriptedWatchBatch(
            statuses=[watch_summary(["prepared", "prepared"]),
                      watch_summary(["saved_stage_available", "prepared"])],
            starts=[{"startAttempts": [{"entryId": "0"}],
                     "summary": watch_summary(["session_running", "prepared"])}],
        )
        waits = []
        result = _watch_bounded(batch, max_starts=2, max_total_starts=1,
            confirm_batch_sha256="b" * 64, poll_seconds=15,
            wait=lambda seconds, _stop: waits.append(seconds))
        self.assertFalse(result["ok"])
        self.assertEqual(result["watchStatus"], "start_budget_exhausted")
        self.assertEqual(batch.status_calls, 2)
        self.assertEqual(len(batch.start_calls), 1)
        self.assertEqual(waits, [15])

    def test_watch_stops_on_existing_or_first_new_blocker(self):
        from scripts.run_textbook_workbench_batch import _watch_bounded
        payment = {"scope": "batch_entry", "entryId": "0" * 64,
                   "status": "operator_error", "reason": "provider_payment_required"}
        existing = ScriptedWatchBatch(
            statuses=[watch_summary(["operator_error", "prepared"], blockers=[payment])], starts=[])
        result = _watch_bounded(existing, max_starts=2, max_total_starts=2,
            confirm_batch_sha256="b" * 64, poll_seconds=15, wait=lambda *_args: None)
        self.assertEqual(result["watchStatus"], "blocked")
        self.assertEqual(existing.start_calls, [])

        unknown = {"scope": "batch_entry", "entryId": "0" * 64,
                   "status": "dispatch_unknown", "reason": "dispatch_reconciliation_required"}
        first = ScriptedWatchBatch(
            statuses=[watch_summary(["prepared", "prepared"])],
            starts=[{"startAttempts": [{"entryId": "0"}],
                     "summary": watch_summary(["dispatch_unknown", "prepared"], blockers=[unknown])}],
        )
        result = _watch_bounded(first, max_starts=2, max_total_starts=2,
            confirm_batch_sha256="b" * 64, poll_seconds=15, wait=lambda *_args: None)
        self.assertEqual(result["watchStatus"], "blocked")
        self.assertEqual(len(first.start_calls), 1)

        external_blocker = {"scope": "external_authoring", "status": "unreadable_unknown",
                            "reason": "external_dispatch_reconciliation_required"}
        external = ScriptedWatchBatch(
            statuses=[watch_summary(["prepared"], blockers=[external_blocker], external=1,
                                    external_statuses={"unreadable_unknown": 1})], starts=[])
        result = _watch_bounded(external, max_starts=2, max_total_starts=1,
            confirm_batch_sha256="b" * 64, poll_seconds=15, wait=lambda *_args: None)
        self.assertEqual(result["watchStatus"], "blocked")
        self.assertEqual(external.start_calls, [])

    def test_watch_treats_held_entries_as_skipped_not_quality_passed(self):
        from scripts.run_textbook_workbench_batch import _watch_bounded
        batch = ScriptedWatchBatch(
            statuses=[watch_summary(["held", "saved_stage_available"])], starts=[])
        result = _watch_bounded(batch, max_starts=2, max_total_starts=1,
            confirm_batch_sha256="b" * 64, poll_seconds=15, wait=lambda *_args: None)
        self.assertTrue(result["ok"])
        self.assertEqual(result["watchStatus"], "completed_with_holds")
        self.assertFalse(result["generatedDraftsAreReviewed"])
        self.assertFalse(result["publicationAllowed"])

        after_start = ScriptedWatchBatch(
            statuses=[watch_summary(["held", "prepared"])],
            starts=[{"startAttempts": [{"entryId": "1"}],
                     "summary": watch_summary(["held", "saved_stage_available"])}],
        )
        result = _watch_bounded(after_start, max_starts=2, max_total_starts=1,
            confirm_batch_sha256="b" * 64, poll_seconds=15, wait=lambda *_args: None)
        self.assertEqual(result["watchStatus"], "completed_with_holds")

    def test_watch_checks_confirmation_before_reporting_completed(self):
        from scripts.run_textbook_workbench_batch import _watch_bounded
        batch = ScriptedWatchBatch(
            statuses=[watch_summary(["saved_stage_available"])], starts=[])
        with self.assertRaisesRegex(ValueError, "confirmation_mismatch"):
            _watch_bounded(batch, max_starts=2, max_total_starts=1,
                confirm_batch_sha256="c" * 64, poll_seconds=15, wait=lambda *_args: None)
        self.assertEqual(batch.start_calls, [])

    def test_watch_signal_stops_before_another_poll_or_start(self):
        from scripts.run_textbook_workbench_batch import _watch_bounded
        stopping = {"value": False}
        batch = ScriptedWatchBatch(
            statuses=[watch_summary(["prepared", "prepared"])],
            starts=[{"startAttempts": [{"entryId": "0"}],
                     "summary": watch_summary(["session_running", "prepared"])}],
        )
        result = _watch_bounded(batch, max_starts=1, max_total_starts=2,
            confirm_batch_sha256="b" * 64, poll_seconds=15,
            stop_requested=lambda: stopping["value"],
            wait=lambda _seconds, _stop: stopping.update(value=True))
        self.assertEqual(result["watchStatus"], "stopped_by_signal")
        self.assertEqual(batch.status_calls, 1)
        self.assertEqual(len(batch.start_calls), 1)

    def test_watch_cli_requires_finite_budget_and_passes_exact_contract(self):
        from scripts import run_textbook_workbench_batch as cli
        with patch.object(cli, "_authoring") as authoring, redirect_stderr(io.StringIO()):
            for args in (["watch-bounded", "--queue-directory", "/queue", "--max-starts", "2",
                          "--confirm-batch-sha256", "b" * 64],
                         ["watch-bounded", "--queue-directory", "/queue", "--max-starts", "2",
                          "--max-total-starts", "3", "--poll-seconds", "14",
                          "--confirm-batch-sha256", "b" * 64],
                         ["watch-bounded", "--queue-directory", "/queue", "--max-starts", "2",
                          "--max-total-starts", "9", "--poll-seconds", "15",
                          "--confirm-batch-sha256", "b" * 64]):
                with self.subTest(args=args), self.assertRaises(SystemExit):
                    cli.main(args)
            authoring.assert_not_called()

        batch = Mock()
        result = {"ok": True, "watchStatus": "completed"}
        with patch.object(cli, "_authoring", return_value=Mock()), \
                patch.object(cli, "TextbookWorkbenchBatch", return_value=batch), \
                patch.object(cli, "_watch_bounded", return_value=result) as watch, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["watch-bounded", "--queue-directory", "/queue",
                "--max-starts", "2", "--max-total-starts", "3", "--poll-seconds", "15",
                "--confirm-batch-sha256", "b" * 64]), 0)
        self.assertEqual(watch.call_args.kwargs["max_starts"], 2)
        self.assertEqual(watch.call_args.kwargs["max_total_starts"], 3)
        self.assertEqual(watch.call_args.kwargs["confirm_batch_sha256"], "b" * 64)


if __name__ == "__main__":
    unittest.main()
