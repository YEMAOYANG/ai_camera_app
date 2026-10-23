"""Real operator entry points with isolated originals and a fake object store."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import unquote, urlsplit

from core.course_storage_config import CourseStorageConfig
from content.textbook_catalog import digest
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.course_file_store import CourseFileStore, CourseFileStorageError
from services.textbook_batch_audio import _external_once
from tests import test_textbook_operator_revision_service as operator_tests
from tests import test_textbook_workbench_authoring as workbench_tests
from tests import test_textbook_preview_pronunciation_revision as pronunciation_revision_tests
from tests import test_textbook_preview_pronunciation_initialization as pronunciation_initialization_tests
from tests import test_textbook_pinyin_narrator as pinyin_tests


class _Response(BytesIO):
    status = 200

    def __init__(self, raw):
        super().__init__(raw)
        self.headers = {"ETag": '"' + "a" * 32 + '"', "Content-Length": str(len(raw))}


class _RemoteSources:
    """Keep registry identity and bytes separate, as a failed remote read must."""
    def __init__(self, root, directories):
        self.entries, self.objects, self.requests = {}, {}, []
        for directory in directories:
            for path in directory.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(root).as_posix()
                    raw = path.read_bytes()
                    checksum = hashlib.sha256(raw).hexdigest()
                    key = "originals/" + relative
                    self.objects[key] = raw
                    self.entries[relative] = {"sourcePath": relative, "sha256": checksum,
                        "byteSize": len(raw), "mimeType": "application/octet-stream",
                        "locator": {"kind": "object", "objectKey": key, "etag": "a" * 32}}
        repository = Mock()
        repository.resolve.side_effect = lambda path, storage_id, expected_sha=None: (
            self.entries.get(path) if expected_sha is None or self.entries.get(path, {}).get("sha256") == expected_sha else None)
        repository.paths_under.side_effect = lambda directory, storage_id: [
            path for path in self.entries if path.startswith(directory + "/")]
        self.store = CourseFileStore(config=CourseStorageConfig(mode="registry",
            endpoint="http://storage.invalid:9000", bucket="study"), project_root=root, repository=repository)
        self.opener = Mock()
        self.opener.open.side_effect = self.response

    def response(self, request, timeout):
        self.requests.append(request)
        if request.get_header("If-match") != '"' + "a" * 32 + '"':
            raise AssertionError("Remote read must use the registered object identity")
        key = unquote(urlsplit(request.full_url).path).removeprefix("/study/")
        if key not in self.objects:
            raise URLError("object missing")
        return _Response(self.objects[key])

    def patches(self, test):
        for patcher in (patch("services.course_file_store.CourseFileStore", return_value=self.store),
                        patch("services.course_file_store.build_opener", return_value=self.opener)):
            patcher.start()
            test.addCleanup(patcher.stop)


class TextbookRemoteSourceTests(unittest.TestCase):
    def operator(self):
        case = operator_tests.OperatorRevisionServiceTests("test_prepare_register_narrate_audit_publish_reuses_exact_parent_and_only_changes_one_line")
        case.setUp()
        self.addCleanup(case.doCleanups)
        original_root, original_audit = case.root, case.audit_dir
        case.root = case.base / "openmaic-runtime/.runtime/OpenMAIC/data/classrooms"
        case.root.parent.mkdir(parents=True)
        original_root.rename(case.root)
        case.audit_dir = case.base / "output/current-audit"
        case.audit_dir.parent.mkdir()
        original_audit.rename(case.audit_dir)
        case.source_folder = case.root / case.source_cid / "textbook-preview-audio"
        case.source_audit = case.audit_dir / "audit.json"
        remote = _RemoteSources(case.base, (case.root, case.audit_dir))
        remote.patches(self)
        shutil.rmtree(case.root)
        shutil.rmtree(case.audit_dir)
        return case, remote

    def assert_no_paid_or_save(self, case):
        for name in ("start_formal_audio_tts", "start_formal_audio_asr", "save_preview_classroom"):
            getattr(case.runtime, name).assert_not_called()

    def test_published_parent_prepares_new_revision_with_every_original_remote(self):
        case, remote = self.operator()
        before = case.parent_rows()
        prepared = case.prepare()
        self.assertEqual((prepared["changedSpeechCount"], prepared["inheritedSpeechCount"]), (1, 2))
        self.assertTrue(remote.requests)
        self.assertEqual(case.parent_rows(), before)
        self.assertFalse((case.root / (case.source_cid + ".json")).exists())
        self.assertEqual(list(case.source_folder.iterdir()), [case.source_folder / "operator.lock"])
        self.assertTrue((case.output / "prepared.json").is_file())
        self.assert_no_paid_or_save(case)

    def test_registered_missing_parent_never_uses_stale_local_or_calls_provider(self):
        case, remote = self.operator()
        path = case.source_folder / "plan.json"
        relative = path.relative_to(case.base).as_posix()
        path.parent.mkdir(parents=True)
        path.write_bytes(remote.objects.pop("originals/" + relative))
        with self.assertRaises(CourseFileStorageError):
            case.prepare()
        self.assertFalse(case.output.exists())
        self.assert_no_paid_or_save(case)

    def test_changed_remote_original_fails_existing_parent_digest_guard(self):
        case, remote = self.operator()
        relative = case.source_audit.relative_to(case.base).as_posix()
        remote.objects["originals/" + relative] += b" "
        with self.assertRaises(CourseFileStorageError):
            case.prepare()
        self.assertFalse(case.output.exists())
        self.assert_no_paid_or_save(case)

    def test_existing_remote_workbench_freeze_is_reused_without_dispatch_or_overwrite(self):
        case = workbench_tests.WorkbenchAuthoringTest("test_prepare_preserves_exact_bytes_all_fields_teacher_and_makes_no_http")
        case.setUp()
        self.addCleanup(case.doCleanups)
        remote = _RemoteSources(case.root, (case.root / "output",))
        remote.patches(self)
        shutil.rmtree(case.root / "output")
        result = case.service.prepare(case.draft_path)
        self.assertEqual(result, case.prepared)
        self.assertFalse(case.job.exists())
        case.factory.assert_not_called()
        case.guard.inspect.assert_called_once()

    def test_remote_unknown_paid_checkpoint_still_fences_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "output/audio-audit/request.json"
            checkpoint.parent.mkdir(parents=True)
            payload = {"text": "synthetic narration"}
            checkpoint.write_text(json.dumps({"requestId": "request",
                "requestPayloadSha256": digest(payload), "state": "dispatching"}))
            remote = _RemoteSources(root, (root / "output",))
            remote.patches(self)
            shutil.rmtree(root / "output")
            runtime = Mock()
            runtime.get_formal_audio_tts.side_effect = OpenMaicFullRuntimeError("not_found", "missing", status_code=404)
            with self.assertRaisesRegex(RuntimeError, "audio_prior_dispatch_unresolved_no_retry"):
                _external_once(runtime, checkpoint, "request", "tts", payload)
            runtime.start_formal_audio_tts.assert_not_called()
            self.assertFalse(checkpoint.exists())

    def test_unavailable_registered_paid_checkpoint_fails_before_any_provider_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "output/audio-audit/request.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_text("{}")
            remote = _RemoteSources(root, (root / "output",))
            remote.patches(self)
            remote.objects.clear()
            runtime = Mock()
            with self.assertRaises(CourseFileStorageError):
                _external_once(runtime, checkpoint, "request", "tts", {})
            runtime.get_formal_audio_tts.assert_not_called()
            runtime.start_formal_audio_tts.assert_not_called()

    def test_lost_narration_save_recovers_with_all_local_originals_removed(self):
        from services.textbook_preview_audio import narrate_preview
        harness = pinyin_tests.PinyinNarratorTests()
        self.addCleanup(harness.doCleanups)
        f = harness.fixture()
        narrate_preview(f.service, f.key, f.root, speech_selection=f.selection(0))
        def saved_without_response(value):
            f.save(value)
            raise OpenMaicFullRuntimeError('response_lost', 'synthetic lost response')
        f.runtime.save_preview_classroom.side_effect = saved_without_response
        with self.assertRaises(OpenMaicFullRuntimeError):
            narrate_preview(f.service, f.key, f.root)
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            old_root = f.root
            f.root = project / 'output/current-narration'
            f.root.parent.mkdir()
            old_root.rename(f.root)
            f.folder = f.root / f.cid / 'textbook-preview-audio'
            remote = _RemoteSources(project, (f.root,))
            remote.patches(self)
            shutil.rmtree(f.root)
            calls = (f.runtime.save_preview_classroom.call_count,
                f.runtime.start_formal_audio_tts.call_count,
                f.runtime.download_formal_audio_tts.call_count)
            result = narrate_preview(f.service, f.key, f.root)
            self.assertEqual((result['status'], result['result']['audioCompleted']), ('preview_ready', 8))
            self.assertEqual(calls, (f.runtime.save_preview_classroom.call_count,
                f.runtime.start_formal_audio_tts.call_count,
                f.runtime.download_formal_audio_tts.call_count))
            self.assertFalse((f.root / (f.cid + '.json')).exists())
            self.assertTrue(remote.requests)

    def test_pronunciation_review_prepares_from_remote_classroom_wavs_and_probe_evidence(self):
        for kind in ("initialization", "revision"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                if kind == "initialization":
                    case = pronunciation_initialization_tests.PronunciationInitializationTests()
                    prepare = lambda: case.run_initialization(execute=False)
                else:
                    case = pronunciation_revision_tests.PronunciationRevisionTests()
                    prepare = lambda: case.run_revision(execute=False)
                case.setUp()
                self.addCleanup(case.doCleanups)
                f = case.f
                old_root, project = f.root, Path(temporary)
                f.root = project / "output/pronunciation-originals"
                f.root.parent.mkdir()
                old_root.rename(f.root)
                f.folder = f.root / f.cid / "textbook-preview-audio"
                for key in ("humanFeedback", "approvedProbeEvidence"):
                    if key in case.patch:
                        old_path = Path(case.patch[key]["path"])
                        case.patch[key]["path"] = str(f.root / old_path.relative_to(old_root))
                remote = _RemoteSources(project, (f.root,))
                # Explicit contexts isolate the two registry snapshots.
                with patch("services.course_file_store.CourseFileStore", return_value=remote.store), \
                        patch("services.course_file_store.build_opener", return_value=remote.opener):
                    shutil.rmtree(f.root)
                    result = prepare()
                self.assertTrue(result["prepared"])
                self.assertTrue(remote.requests)
                self.assertFalse((f.root / (f.cid + ".json")).exists())
                f.runtime.save_preview_classroom.assert_not_called()
                f.runtime.start_formal_audio_tts.assert_not_called()
                f.runtime.start_formal_audio_asr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
