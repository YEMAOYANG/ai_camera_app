from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from pymysql.err import OperationalError

from core.course_storage_config import CourseStorageConfig
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
from services.course_file_writer import CourseFileWriter, CourseFileWriteError, NodeCourseFileUploader, _json_bytes
from tests.test_course_storage_repository import _Database


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class CourseFileWriterTest(unittest.TestCase):
    def setUp(self):
        self.db = _Database()
        self.addCleanup(self.db.raw.close)
        self.db.raw.create_function("JSON_UNQUOTE", 1, lambda v: v)
        self.db.raw.create_function("JSON_CONTAINS", 2, lambda data, query: int(any(
            all(item.get(k) == v for k, v in json.loads(query).items()) for item in json.loads(data))))
        self.db.raw.executescript("""
          CREATE TABLE learning_textbook_course_previews(preview_key TEXT,classroom_id TEXT,status TEXT);
          CREATE TABLE learning_textbook_course_builds(content_key TEXT,status TEXT,input_json TEXT);
        """)
        self.repo = CourseStorageRepository(self.db)
        self.config = CourseStorageConfig(mode="registry", endpoint="http://storage.invalid:9000", bucket="study")
        self.storage = storage_id_for(self.config.endpoint, self.config.bucket)
        self.writer = CourseFileWriter(config=self.config, repository=self.repo)
        self.meta = {"scopeKey": "a" * 64, "previewKey": "b" * 64, "classroomId": "stage-test",
            "sourceKind": "textbook_preview", "courseId": "textbook-preview:" + "b" * 64,
            "courseVersion": "v1", "status": "generated_saved", "storageDirectory": "语文/独立课件/一年级/2026-10-23/练习"}
        self.db.raw.execute("INSERT INTO learning_textbook_course_previews VALUES(?,?,?)", ("b" * 64, "stage-test", "review_required"))
        self.old = raw({"id": "stage-test", "stage": {"id": "stage-test", "name": "练习"}, "scenes": [{"id": "scene-1"}]})
        self.new = raw({"id": "stage-test", "stage": {"id": "stage-test", "name": "修改后"}, "scenes": [{"id": "scene-1"}]})
        self.path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-test.json"
        self.read = Mock(return_value=self.old)
        self.writer._read = self.read
        self.uploader = Mock()
        self.writer.uploader = self.uploader
        self.uploader.upload.side_effect = lambda **kw: {"kind": "object", "objectKey": kw["object_key"], "etag": '"verified-etag"'}

    def register(self, path=None, body=None, meta=None):
        path, body = path or self.path, body or self.old
        metadata = {**(meta or self.meta), "scopeKey": sha(path.encode())}
        self.repo.register_scope(metadata, [{"sourcePath": path, "sha256": sha(body), "byteSize": len(body),
            "mimeType": "application/json", "locator": {"kind": "object", "objectKey": "原有/工作记录.json", "etag": '"old-etag"'}}], self.storage)
        return path

    def write(self, body=None, path=None, expected=None):
        return self.writer.write_bytes(path or self.path, body or self.new, expected_sha256=expected or sha(self.old))

    def test_saved_preview_advances_exact_head_and_retains_old_version(self):
        self.register()
        value = self.write()
        self.assertEqual(value["sha256"], sha(self.new))
        self.assertEqual(value["storage"]["bucket"], "study")
        self.assertEqual(self.repo.resolve(self.path, self.storage, sha(self.old))["sha256"], sha(self.old))
        self.assertEqual(self.repo.resolve(self.path, self.storage)["sha256"], sha(self.new))
        self.read.assert_called_once_with(self.path, sha(self.old))
        call = self.uploader.upload.call_args.kwargs
        self.assertEqual(call["raw"], self.new)
        self.assertRegex(call["object_key"], r"^语文/独立课件/一年级/2026-10-23/练习/练习-工作记录-\d{8}T\d{12}Z-[a-f0-9]{8}\.json$")
        # The existing preview workflow, rather than this file registry, owns
        # its classroom SHA and review transitions.
        self.assertEqual(self.db.raw.execute("SELECT status FROM learning_textbook_course_previews").fetchone()[0], "review_required")

    def test_stale_missing_and_same_bytes_never_upload_or_reset_head(self):
        with self.assertRaisesRegex(CourseFileWriteError, "asset_not_found"):
            self.write()
        self.register()
        with self.assertRaisesRegex(CourseFileWriteError, "head_conflict"):
            self.write(expected="f" * 64)
        value = self.write(body=self.old)
        self.assertEqual(value["sha256"], sha(self.old))
        self.uploader.upload.assert_not_called()
        self.read.assert_not_called()

    def test_published_or_linked_preview_or_unknown_scope_denies_before_upload(self):
        for metadata, published in (({**self.meta, "status": "published"}, False),
                                    ({**self.meta, "status": "unknown"}, False), (self.meta, True)):
            with self.subTest(status=metadata["status"], linked=published):
                self.db.raw.execute("DELETE FROM course_storage_heads")
                self.db.raw.execute("DELETE FROM course_storage_scopes")
                self.db.raw.execute("DELETE FROM learning_textbook_course_builds")
                self.register(meta=metadata)
                if published:
                    self.db.raw.execute("INSERT INTO learning_textbook_course_builds VALUES(?,?,?)",
                        ("c" * 64, "published", json.dumps({"previewKey": "b" * 64})))
                with self.assertRaises(CourseFileWriteError):
                    self.write()
        self.uploader.upload.assert_not_called()

    def test_saved_head_shared_with_published_parent_is_immutable(self):
        self.register(meta={**self.meta, "status": "published"})
        self.repo.register_scope({**self.meta, "scopeKey": "e" * 64}, [{"sourcePath": self.path, "sha256": sha(self.old),
            "byteSize": len(self.old), "mimeType": "application/json", "locator": {"kind": "object", "objectKey": "saved/原稿.json", "etag": '"saved"'}}], self.storage)
        self.assertEqual(self.repo.head_scope(self.path, self.storage)["metadata"]["status"], "generated_saved")
        with self.assertRaisesRegex(CourseFileWriteError, "published_immutable"):
            self.write()
        self.uploader.upload.assert_not_called()

    def test_partial_upload_failure_never_commits_a_version(self):
        self.register()
        self.uploader.upload.side_effect = CourseFileWriteError("course_storage_upload_failed", 502)
        with self.assertRaisesRegex(CourseFileWriteError, "upload_failed"):
            self.write()
        self.assertEqual(self.repo.resolve(self.path, self.storage)["sha256"], sha(self.old))
        self.assertIsNone(self.repo.resolve(self.path, self.storage, sha(self.new)))
        self.assertEqual(self.db.raw.execute("SELECT COUNT(*) FROM course_storage_scopes").fetchone()[0], 1)

    def test_concurrent_writer_wins_without_deleting_either_remote_object_or_old_version(self):
        self.register()
        winning = raw({"new": "other writer"})
        def upload(**kw):
            self.repo.compare_and_activate({**self.meta, "scopeKey": "c" * 64}, [{"sourcePath": self.path,
                "sha256": sha(winning), "byteSize": len(winning), "mimeType": "application/json",
                "locator": {"kind": "object", "objectKey": "其他/新版本.json", "etag": '"winner"'}}],
                self.storage, expected_old_sha=sha(self.old))
            return {"kind": "object", "objectKey": kw["object_key"], "etag": '"loser-upload-retained"'}
        self.uploader.upload.side_effect = upload
        with self.assertRaisesRegex(CourseFileWriteError, "head_conflict"):
            self.write()
        self.assertEqual(self.repo.resolve(self.path, self.storage)["sha256"], sha(winning))
        self.assertIsNotNone(self.repo.resolve(self.path, self.storage, sha(self.old)))
        self.assertIsNone(self.repo.resolve(self.path, self.storage, sha(self.new)))

    def test_publication_during_upload_is_rechecked_inside_cas(self):
        self.register()
        def upload(**kw):
            self.db.raw.execute("INSERT INTO learning_textbook_course_builds VALUES(?,?,?)",
                ("c" * 64, "published", json.dumps({"previewKey": "b" * 64})))
            self.db.raw.commit()
            return {"kind": "object", "objectKey": kw["object_key"], "etag": '"retained-orphan"'}
        self.uploader.upload.side_effect = upload
        with self.assertRaisesRegex(CourseFileWriteError, "published_immutable"):
            self.write()
        self.assertEqual(self.repo.resolve(self.path, self.storage)["sha256"], sha(self.old))
        self.assertIsNone(self.repo.resolve(self.path, self.storage, sha(self.new)))

    def test_only_mysql_deadlock_preflight_retries_in_fresh_transaction(self):
        self.register()
        policy = self.writer._policy
        attempts = []
        def check(*args):
            attempts.append(args[-1])
            if len(attempts) < 3:
                raise OperationalError(1213, 'synthetic test deadlock')
            return policy(*args)
        with patch.object(self.writer, '_policy', check):
            value = self.write()
        self.assertEqual(value['sha256'], sha(self.new))
        self.assertEqual(len(attempts), 4)  # three preflights, final CAS guard
        self.assertIsNot(attempts[0], attempts[1])
        self.assertIsNot(attempts[1], attempts[2])
        self.uploader.upload.assert_called_once()

    def test_cas_deadlock_reuses_one_verified_upload_and_original_expected_head(self):
        self.register()
        activate = self.repo.compare_and_activate
        calls = []
        def cas(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                raise OperationalError(1213, 'synthetic test deadlock')
            return activate(*args, **kwargs)
        with patch.object(self.repo, 'compare_and_activate', cas):
            self.write()
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call['expected_old_sha'] == sha(self.old) for call in calls))
        self.assertEqual(len({call['expected_scope_key'] for call in calls}), 1)
        self.uploader.upload.assert_called_once()
        self.assertIsNotNone(self.repo.resolve(self.path, self.storage, sha(self.old)))

    def test_guard_deadlock_rolls_back_cas_and_repeats_lifecycle_without_reupload(self):
        self.register()
        original = self.writer._policy
        calls = []
        def policy(*args):
            calls.append(args[-1])
            result = original(*args)
            if len(calls) == 2:  # first transaction's CAS guard
                raise OperationalError(1213, 'synthetic test scope scan deadlock')
            return result
        with patch.object(self.writer, '_policy', policy):
            self.write()
        self.assertEqual(len(calls), 3)
        self.assertIsNot(calls[1], calls[2])
        self.uploader.upload.assert_called_once()
        self.assertEqual(self.db.raw.execute('SELECT COUNT(*) FROM course_storage_scopes').fetchone()[0], 2)
        self.assertEqual(self.db.raw.execute('SELECT COUNT(*) FROM course_storage_files').fetchone()[0], 2)

    def test_cas_deadlock_exhaustion_preserves_old_version_and_does_not_reupload(self):
        self.register()
        with patch.object(self.repo, 'compare_and_activate', side_effect=OperationalError(1213, 'synthetic')) as activate:
            with self.assertRaisesRegex(CourseFileWriteError, 'write_conflict') as caught:
                self.write()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(activate.call_count, 3)
        self.uploader.upload.assert_called_once()
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(self.old))
        self.assertIsNone(self.repo.resolve(self.path, self.storage, sha(self.new)))

    def test_deadlock_exhaustion_returns_conflict_and_other_failures_never_retry(self):
        self.register()
        for code, expected in ((1213, 3), (1205, 1)):
            with self.subTest(code=code):
                with patch.object(self.writer, '_policy', side_effect=OperationalError(code, 'synthetic')) as policy:
                    with self.assertRaises(CourseFileWriteError if code == 1213 else OperationalError) as raised:
                        self.write()
                    self.assertEqual(policy.call_count, expected)
                    if code == 1213:
                        self.assertEqual(raised.exception.status_code, 409)
        self.uploader.upload.assert_not_called()
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(self.old))

    def test_cas_deadlock_followed_by_stale_head_is_conflict_without_upload_retry(self):
        self.register()
        activate = self.repo.compare_and_activate
        winning = raw({'winner': True})
        calls = []
        def cas(*args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                activate({**self.meta, 'scopeKey': 'c' * 64}, [{'sourcePath': self.path,
                    'sha256': sha(winning), 'byteSize': len(winning), 'mimeType': 'application/json',
                    'locator': {'kind': 'object', 'objectKey': '胜出/工作记录.json', 'etag': '"winner"'}}],
                    self.storage, expected_old_sha=sha(self.old))
                raise OperationalError(1213, 'synthetic test deadlock')
            return activate(*args, **kwargs)
        with patch.object(self.repo, 'compare_and_activate', cas), self.assertRaisesRegex(CourseFileWriteError, 'head_conflict'):
            self.write()
        self.assertEqual(len(calls), 2)
        self.uploader.upload.assert_called_once()
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(winning))

    def test_json_credentials_duplicates_and_wrong_classroom_are_rejected(self):
        self.register()
        for value in (b'{"secretKey":"actual-private-value"}', b'{"id":1,"id":2}', b'{"x":NaN}',
                      self.new.replace(b"stage-test", b"stage-other")):
            with self.subTest(raw=value[:30]), self.assertRaises(CourseFileWriteError):
                self.write(value)
        self.uploader.upload.assert_not_called()

    def test_raw_media_dispatch_and_terminal_receipt_paths_are_not_mutable(self):
        for path in ("output/lesson/authoring-job/dispatch.json", "output/lesson/snapshot.json",
                     "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/budget-binding.json",
                     "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/transcripts/" + "c" * 64 + ".json"):
            with self.subTest(path=path):
                self.register(path=path)
                with self.assertRaisesRegex(CourseFileWriteError, "write_forbidden"):
                    self.write(path=path)
        self.uploader.upload.assert_not_called()

    def test_running_paid_job_can_complete_but_terminal_claim_cannot_reset(self):
        request = "tts-known-request"
        path = "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/jobs/tts/" + sha(request.encode()) + ".json"
        old = {"schemaVersion": "mira.openmaic.formal-audio-job.v1", "requestId": request,
               "requestSha256": "e" * 64, "kind": "tts", "state": "running", "providerId": "qwen-tts"}
        completed = {**old, "state": "succeeded", "audioSha256": "f" * 64}
        self.old, self.new = raw(old), raw(completed)
        self.read.return_value = self.old
        self.register(path=path)
        self.write(path=path)
        self.read.return_value = self.new
        with self.assertRaises(CourseFileWriteError):
            self.write(path=path, body=raw(old), expected=sha(self.new))
        self.assertEqual(self.uploader.upload.call_count, 1)

    def test_aggregate_and_review_ledger_preserve_terminal_entries(self):
        cases = [("formal-quality-reviews/" + "c" * 64 + "/attempts.json", "snapshotSha256", "passed")]
        for relative, key, status in cases:
            with self.subTest(path=relative):
                path = "openmaic-runtime/.runtime/OpenMAIC/data/" + relative
                self.old = raw([{key: "known", "status": status}])
                self.read.return_value = self.old
                self.register(path=path)
                with self.assertRaises(CourseFileWriteError):
                    self.write(path=path, body=raw([{key: "known", "status": "started"}]))
                value = self.write(path=path, body=raw([{key: "known", "status": status}, {key: "new", "status": "started"}]))
                self.assertEqual(value["byteSize"], len(raw([{key: "known", "status": status}, {key: "new", "status": "started"}])))

    def audio_fixture(self, *, initial=None):
        from content.textbook_catalog import digest
        from content.textbook_preview_audio_contract import new_audio_plan, tts_request_id
        from services.textbook_preview_audio import core_content
        from tests.test_textbook_preview_audio_contract import frozen
        classroom = {"id": "stage-test", "stage": {"id": "stage-test"}, "scenes": [{"id": "scene-1",
                     "actions": [{"id": "action-1", "type": "speech", "text": "请观察图片。"}]}]}
        plan = new_audio_plan(preview_key=self.meta["previewKey"], classroom_sha256=digest(classroom),
            core_sha256=digest(core_content(classroom)), frozen_input=frozen())
        request = tts_request_id(plan, "scene-1", "action-1", "请观察图片。")
        path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-test/textbook-preview-audio/receipts.json"
        self.old = raw(initial or [])
        self.read.side_effect = lambda p, *_a: raw(plan) if p.endswith("/plan.json") else raw(classroom) if p.endswith("/stage-test.json") else self.old
        self.register(path=path)
        return path, plan, request

    def test_real_audio_unknown_claim_success_identity_then_duration_sequence(self):
        from content.textbook_catalog import digest
        path, plan, request = self.audio_fixture()
        actual = {"requestId": request, "status": "succeeded", "audioSha256": "f" * 64, "mimeType": "audio/wav"}
        self.writer._formal_tts = Mock(return_value=actual)
        claim = {"requestId": request, "status": "unknown", "audioSha256": None}
        completed = {**actual, "previewAudioIdentity": {"planSha256": digest(plan), "attempt": 1}}
        for records in ([claim], [completed], [{**completed, "durationSeconds": 1.25}]):
            before = self.old
            after = raw(records)
            self.writer.write_bytes(path, after, expected_sha256=sha(before))
            self.old = after
        self.assertEqual(self.repo.resolve(path, self.storage)["sha256"], sha(self.old))
        for bad in ({**completed, "audioSha256": "e" * 64}, {**completed, "durationSeconds": -1},
                    {**completed, "durationSeconds": 1.25, "previewAudioIdentity": {"planSha256": "0" * 64, "attempt": 1}}):
            with self.assertRaises(CourseFileWriteError):
                self.writer.write_bytes(path, raw([bad]), expected_sha256=sha(self.old))
        self.assertEqual(self.uploader.upload.call_count, 3)

    def test_ambiguous_receipt_requires_existing_same_identity_success_and_failed_cannot_reset(self):
        from content.textbook_catalog import digest
        path, plan, request = self.audio_fixture()
        identity = {"planSha256": digest(plan), "attempt": 1}
        claim = {"requestId": request, "status": "ambiguous", "audioSha256": None, "mimeType": None,
                 "previewAudioIdentity": identity}
        self.old = raw([claim])
        current_scope = {**self.meta, "scopeKey": "d" * 64}
        self.repo.register_scope(current_scope, [{"sourcePath": path, "sha256": sha(self.old), "byteSize": len(self.old),
            "mimeType": "application/json", "locator": {"kind": "object", "objectKey": "原有/ambiguous.json", "etag": '"claim"'}}], self.storage)
        receipt = {**claim, "status": "succeeded", "audioSha256": "f" * 64, "mimeType": "audio/wav"}
        self.writer._formal_tts = Mock(return_value={"requestId": request, "status": "ambiguous", "audioSha256": None, "mimeType": None})
        with self.assertRaises(CourseFileWriteError):
            self.writer.write_bytes(path, raw([receipt]), expected_sha256=sha(self.old))
        self.uploader.upload.assert_not_called()
        self.writer._formal_tts.return_value = {k: receipt[k] for k in ("requestId", "status", "audioSha256", "mimeType")}
        self.writer.write_bytes(path, raw([receipt]), expected_sha256=sha(self.old))

    def test_running_job_can_fill_null_result_but_not_change_existing_result_or_request(self):
        request = "tts-known-request"
        path = "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/jobs/tts/" + sha(request.encode()) + ".json"
        record = {"schemaVersion": "mira.openmaic.formal-audio-job.v1", "kind": "tts", "requestId": request,
                  "state": "running", "requestSha256": "e" * 64, "audioSha256": None, "mimeType": None}
        self.old = raw(record)
        self.read.return_value = self.old
        self.register(path=path)
        filled = {**record, "state": "succeeded", "audioSha256": "f" * 64, "mimeType": "audio/wav"}
        self.writer.write_bytes(path, raw(filled), expected_sha256=sha(self.old))
        self.assertEqual(self.repo.resolve(path, self.storage)["sha256"], sha(raw(filled)))

    def test_narration_revision_receipt_requires_exact_retained_intent_source_and_saved_target(self):
        from content.textbook_catalog import digest
        from content.textbook_preview_audio_contract import revision_audio_plan, tts_request_id
        from services.textbook_preview_audio import core_content
        path, plan, _request = self.audio_fixture()
        source = json.loads(self.read.side_effect(self.path))
        target = deepcopy(source)
        target["scenes"][0]["actions"][0]["text"] = "请点击清楚的图片。"
        patch_data = {"schemaVersion": "mira.textbook.preview-narration-revision.v1", "expectedSourceSha256": digest(source),
            "reviewer": "teacher", "basis": "原审核明确反馈需要更清楚的引导", "changes": [{"sceneId": "scene-1", "actionId": "action-1",
                "beforeTextSha256": sha("请观察图片。".encode()), "text": "请点击清楚的图片。"}]}
        audit = raw({"previewKey": self.meta["previewKey"], "segments": []})
        revision = digest({"previewKey": plan["previewKey"], "patch": patch_data, "failedAuditSha256": sha(audit)})
        child = revision_audio_plan(plan, revision_id=revision, classroom_sha256=digest(target),
            core_sha256=digest(core_content(target)), frozen_input=plan["binding"])
        request = tts_request_id(child, "scene-1", "action-1", "请点击清楚的图片。")
        receipt = {"requestId": request, "status": "succeeded", "audioSha256": "f" * 64, "mimeType": "audio/wav",
                   "narrationRevisionId": revision, "previewAudioIdentity": {"planSha256": digest(child), "attempt": 1}}
        combined = raw([receipt])
        archive = str(Path(path).parent / "narration-revisions" / revision)
        files = {"source.json": raw(source), "source-row.json": raw({"status": "review_required"}),
                 "target-text.json": raw(target), "original-plan.json": raw(plan),
                 "original-receipts.json": self.old, "failed-audit.json": audit, "plan.json": raw(child)}
        intent = {"schemaVersion": "mira.textbook.preview-narration-intent.v1", "revisionId": revision,
                  "previewKey": plan["previewKey"], "classroomId": "stage-test", "patch": patch_data,
                  "files": {name: sha(body) for name, body in files.items()}}
        intent["sha256"] = digest(intent)
        mapping = {**{archive + "/" + name: body for name, body in files.items()},
                   archive + "/intent.json": raw(intent), archive + "/saved.json": raw(target),
                   archive + "/receipts.json": combined, self.path: raw(target), str(Path(path).parent / "plan.json"): raw(plan), path: self.old}
        self.read.side_effect = lambda p, *_a: mapping[p]
        self.writer._formal_tts = Mock(return_value={k: receipt[k] for k in ("requestId", "status", "audioSha256", "mimeType")})
        original = mapping[archive + "/original-receipts.json"]
        mapping[archive + "/original-receipts.json"] = b"[ ]"
        with self.assertRaises(CourseFileWriteError):
            self.writer.write_bytes(path, combined, expected_sha256=sha(self.old))
        self.uploader.upload.assert_not_called()
        mapping[archive + "/original-receipts.json"] = original
        result = self.writer.write_bytes(path, combined, expected_sha256=sha(self.old))
        self.assertEqual(result["sha256"], sha(combined))
        self.assertEqual(self.writer._formal_tts.call_args.args[1], child)

    def test_draft_requires_exact_amendment_and_running_snapshot_requires_running_state(self):
        path = "output/lesson/authoring-job/draft.json"
        self.register(path=path)
        self.writer._amendment = Mock(side_effect=CourseFileWriteError("course_storage_amendment_required"))
        with self.assertRaisesRegex(CourseFileWriteError, "amendment_required"):
            self.write(path=path)
        self.uploader.upload.assert_not_called()
        saved = "output/lesson/authoring-job/saved-stage-test.json"
        self.register(path=saved)
        self.read.side_effect = lambda path, *_a: raw({"status": "session_running"}) if path.endswith("state.json") else self.old
        self.write(path=saved)
        self.read.side_effect = lambda path, *_a: raw({"status": "saved_stage_available"}) if path.endswith("state.json") else self.new
        with self.assertRaises(CourseFileWriteError):
            self.write(path=saved, body=self.old, expected=sha(self.new))

    def test_exact_undispatched_amendment_intent_can_advance_draft_but_not_rebind_scope(self):
        from content.textbook_catalog import digest
        from tests.test_textbook_workbench_authoring import reviewed_draft
        draft = reviewed_draft()
        revised = {**deepcopy(draft), "request": draft["request"] + " 增加真实图示决策反馈。"}
        self.old, self.new = raw(draft), raw(revised)
        path = "output/lesson/authoring-job/draft.json"
        with tempfile.TemporaryDirectory() as temporary:
            self.writer.root = Path(temporary)
            identity = {"jobDirectory": str(self.writer.root / Path(path).parent), "sourceDraftSha256": sha(self.old),
                        "targetDraftSha256": sha(self.new), "reviewer": "teacher", "basis": "原请求保留教材范围并补反馈"}
            revision = digest(identity)
            archive = self.writer.root / Path(path).parent / "amendments" / revision
            archive.mkdir(parents=True)
            source_frozen = {"schemaVersion": "fixture-frozen", "binding": draft["binding"], "draftSha256": sha(self.old)}
            target_frozen = {**source_frozen, "draftSha256": sha(self.new), "draftAmendmentId": revision}
            files = {"source-draft.json": self.old.decode(), "target-draft.json": self.new.decode(),
                     "source-frozen.json": raw(source_frozen).decode(), "target-frozen.json": raw(target_frozen).decode(),
                     "source-state.json": raw({"status": "prepared"}).decode(), "target-state.json": raw({"status": "prepared"}).decode()}
            intent = {"identity": identity, "files": files, "sourceEvidence": []}
            intent["sha256"] = digest(intent)
            (archive / "intent.json").write_bytes(raw(intent))
            self.writer._exists = Mock(return_value=False)
            self.read.side_effect = lambda p, *_a: raw({"status": "prepared"}) if p.endswith("state.json") else self.old
            self.register(path=path)
            with patch("services.course_file_store.course_glob", return_value=[archive]), \
                 patch("services.textbook_workbench_authoring.course_exists", side_effect=lambda p: p.is_file()), \
                 patch("services.textbook_workbench_authoring.course_text", side_effect=lambda p: p.read_text()):
                value = self.write(path=path)
            self.assertEqual(value["sha256"], sha(self.new))
            scope = self.repo.head_scope(path, self.storage)
            self.assertEqual(scope["metadata"]["writePolicy"], "traceable_amendment:" + revision)


class NodeUploaderTest(unittest.TestCase):
    def test_descriptor_is_bound_to_actual_body_destination_and_storage_without_secret_arguments(self):
        storage = {"endpoint": "http://storage.invalid", "bucket": "study", "region": "us-east-1"}
        data = b'{"x":1}'
        base = {"objectKey": "课程/工作.json", "sha256": sha(data), "byteSize": len(data), "etag": '"etag"', "storage": storage}
        with patch("services.course_file_writer.shutil.which", return_value="/fixture/node24"), patch("services.course_file_writer.subprocess.run") as run:
            for changed in ({"byteSize": 1}, {"sha256": "a" * 64}, {"storage": {**storage, "bucket": "other"}}, {"objectKey": "other"}):
                run.return_value = Mock(returncode=0, stdout=json.dumps({**base, **changed}))
                with self.assertRaisesRegex(CourseFileWriteError, "upload_not_verified"):
                    NodeCourseFileUploader().upload(object_key=base["objectKey"], raw=data, storage=storage)
            run.return_value = Mock(returncode=0, stdout=json.dumps(base))
            result = NodeCourseFileUploader().upload(object_key=base["objectKey"], raw=data, storage=storage)
            self.assertEqual(result["etag"], base["etag"])
            args, kwargs = run.call_args
            self.assertEqual(len(args[0]), 2)
            self.assertNotIn("env", kwargs)
            self.assertEqual(json.loads(kwargs["input"])["storage"], storage)


if __name__ == "__main__":
    unittest.main()
