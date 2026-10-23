"""Archive recovery bytes, ownership boundaries and public upload contracts."""
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

from services.course_archive_exporter import (
    ArchiveSnapshot, CourseArchiveError, CourseArchiveExporter, _check_public,
)
from services.course_media_object_store import CourseMediaStorageError
from core.course_storage_config import CourseStorageConfig


class CourseArchiveExporterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.staging = self.root / "private-task"
        self.staging.mkdir()
        self.environment = patch.dict(os.environ, {"MIRA_TASK_TMPDIR": str(self.staging)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.store = Mock()
        self.exporter = CourseArchiveExporter(project_root=self.root, media_store=self.store,
            native_document_loader=lambda stage: None,
            standard_asset_resolver=lambda document, **kwargs: {"entries": [], "unresolved": []})
        self.media = b"already migrated recording\x00\x01"
        self.media_path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/tbpub_test/audio/teacher.mp3"
        self.identity = {"courseId": "course", "courseVersion": "1", "classroomId": "tbpub_test",
                         "contentKey": "a" * 64, "releaseSha256": "b" * 64}
        self.snapshot = ArchiveSnapshot(identity=self.identity, metadata={"title": "怎样学科学",
            "subjectName": "科学", "gradeLabel": "一年级上册"},
            classroom={"stage": {"id": "tbpub_test"}, "scenes": [{"id": "page1",
                "type": "interactive", "content": {"html": "<button>开始</button>"}}]},
            documents={"原始课堂.json": '{ "stage": {"id":"source"}, "scenes": [] }\n',
                       "数据库/课程记录.json": {"content_json": '{"title": "科学"}'}},
            media=[{"path": "/api/classroom-media/tbpub_test/audio/teacher.mp3",
                "sha256": hashlib.sha256(self.media).hexdigest(), "byteSize": len(self.media),
                "mimeType": "audio/mpeg"}])
        self.store.read.return_value = self.media
        self.release = {**self.identity, "storageDirectory": "科学/审定教材-上册/一年级/2026-10-23/怎样学科学-v2"}

    def export(self, snapshot=None, **kwargs):
        return self.exporter.export_snapshot(snapshot or self.snapshot,
            staging_root=self.staging / "exports", release=self.release, **kwargs)

    def test_remote_only_archive_contains_actual_bytes_exact_original_json_and_extracted_html(self):
        self.assertFalse((self.root / self.media_path).exists())
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("媒体/" + self.media_path), self.media)
            self.assertEqual(archive.read("原始课堂.json"), self.snapshot.documents["原始课堂.json"].encode())
            self.assertEqual(archive.read("数据库原字段/课程记录/000-content_json.json"), b'{"title": "\xe7\xa7\x91\xe5\xad\xa6"}')
            self.assertEqual(archive.read("互动页面/001-page1.html"), "<button>开始</button>".encode())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertFalse(next(x for x in manifest["files"] if x["archivePath"].endswith(".html"))["original"])
            self.assertEqual(set(archive.namelist()), {x["archivePath"] for x in manifest["files"]} | {"manifest.json"})
        self.store.read.assert_called_once_with(self.root / self.media_path,
            expected_sha256=hashlib.sha256(self.media).hexdigest(), expected_bytes=len(self.media))

    def test_generated_upload_contract_is_readable_and_preserves_existing_directory(self):
        result = self.export(meta={"exportedAt": "2026-10-23T09:10:11.123456Z"})
        self.assertEqual(result["objectDirectory"], self.release["storageDirectory"])
        files = result["generatedPublicFiles"]
        self.assertEqual(len(files), 4)
        for item in files:
            self.assertTrue(item["relativePath"].startswith(self.release["storageDirectory"] + "/怎样学科学-"))
            self.assertIn("2026-10-23 09-10-11.123456", item["relativePath"])
            self.assertEqual(len(item["relativePath"].split("/")), 6)
            path = Path(item["localPath"])
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(item["byteSize"], path.stat().st_size)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        public_json = "".join(Path(x["localPath"]).read_text() for x in files if x["mimeType"] == "application/json")
        self.assertNotIn(str(self.staging), public_json)
        self.assertNotIn("localPath", public_json)
        self.assertEqual(stat.S_IMODE(Path(result["stagingDirectory"]).stat().st_mode), 0o700)

    def test_owned_source_excludes_credentials_without_following_unrelated_json_links(self):
        source = self.root / "output/one-bound-job"
        source.mkdir(parents=True)
        (source / "owner.cookies").write_text("private-cookie")
        (source / ".env").write_text("PRIVATE=secret")
        original = b'{"request":"teach science","untrustedLink":"../../unrelated.json"}'
        (source / "draft.json").write_bytes(original)
        (self.root / "unrelated.json").write_text('{"private":"never copy"}')
        self.snapshot.source_roots = [source]
        result = self.export()
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            names = archive.namelist()
            self.assertEqual(archive.read("原稿/output/one-bound-job/draft.json"), original)
            self.assertFalse(any("owner.cookies" in x or ".env" in x or "unrelated.json" in x for x in names))
            self.assertEqual(len(json.loads(archive.read("manifest.json"))["excludedFiles"]), 2)
        self.assertTrue(result["complete"])

    def test_missing_required_original_blocks_all_upload_files(self):
        self.snapshot.missing_sources = [{"kind": "authoring", "reason": "bound_original_missing"}]
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertTrue(Path(result["indexPath"]).is_file())

    def test_secret_in_original_is_not_redacted_or_uploaded_as_an_original(self):
        path = self.root / "output/one/draft.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"apiKey":"private-credential"}')
        self.snapshot.source_files = [path]
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertEqual(result["missingSources"][0]["kind"], "unsafe_original")
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertNotIn("原稿/output/one/draft.json", archive.namelist())

    def test_raw_logs_and_partial_json_preserve_bytes_but_scan_payloads(self):
        source = self.root / "output/one"
        source.mkdir(parents=True)
        originals = {"events.sse": b'event: status\ndata: {"status":"saved"}\n\n',
            "progress.jsonl": b'{"phase":"audio"}\n{"phase":"done"}\n',
            "scene.body": b'<html><p>Course original</p></html>\n',
            "run.stdout.json": b'{"phase":"saved"}\n{unfinished\n'}
        for name, raw in originals.items():
            (source / name).write_bytes(raw)
        self.snapshot.source_roots = [source]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            for name, raw in originals.items():
                self.assertEqual(archive.read("原稿/output/one/" + name), raw)
            manifest = json.loads(archive.read("manifest.json"))
            partial = next(item for item in manifest["files"] if item["archivePath"].endswith("run.stdout.json"))
            self.assertEqual(partial["originalFormat"], "raw-text-log")
        for name, raw in (("events.sse", b'data: {"childId":"actual-private-id"}\n'),
                          ("progress.jsonl", b'{"phase":"done"}\n{"apiKey":"short"}\n'),
                          ("run.stdout.json", b'{"childId":"private-id",\n')):
            with self.subTest(name=name):
                self.snapshot.source_roots = []
                path = source / name
                path.write_bytes(raw)
                self.snapshot.source_files = [path]
                unsafe = self.export()
                self.assertFalse(unsafe["complete"])
                self.assertEqual(unsafe["generatedPublicFiles"], [])

    def test_only_proven_runtime_backup_is_excluded_before_symlink_gate(self):
        source = self.root / "output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard/u4-l1/teaching-1"
        backup = source / "quality-repairs/formal-audio-predispatch-recovery-v1/old-build"
        backup.parent.mkdir(parents=True)
        backup.symlink_to(self.root, target_is_directory=True)
        (source / "draft.json").write_text('{"lesson":"秋天"}')
        self.snapshot.source_roots = [source]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["excludedFiles"][0]["reason"], "retained_private_runtime_recovery_backup")
            self.assertFalse(any("old-build" in name for name in archive.namelist()))
        material = source / "actual-material"
        material.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(CourseArchiveError, "source_symlink_rejected"):
            self.export()

    def test_exact_operator_compile_staging_excludes_runtime_links_but_not_neighbor_material(self):
        source = self.root / "output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard/u4-l3/teaching-1"
        staging = source / "planning/native-operator-staging-0242"
        staging.mkdir(parents=True)
        runtime = self.root / "openmaic-runtime/.runtime/OpenMAIC"
        for name in ("types", "node_modules", "public", "packages"):
            (runtime / name).mkdir(parents=True)
            (staging / name).symlink_to(runtime / name, target_is_directory=True)
        (staging / "operator-baseline.json").write_text('{"nativeRoot":"runtime"}')
        (source / "draft.json").write_bytes(b'{"lesson":"retained actual original"}')
        self.snapshot.source_roots = [source]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["excludedFiles"][0]["reason"], "retained_private_runtime_compile_staging")
            self.assertFalse(any("native-operator-staging-0242" in name for name in archive.namelist()))
            self.assertTrue(any(name.endswith("teaching-1/draft.json") for name in archive.namelist()))
        self.assertTrue((staging / "node_modules").is_symlink())
        neighbor = source / "planning/native-operator-staging-0242-lesson"
        neighbor.mkdir()
        (neighbor / "actual-material").symlink_to(runtime / "public", target_is_directory=True)
        with self.assertRaisesRegex(CourseArchiveError, "source_symlink_rejected"):
            self.export()

    def test_exact_retained_vendor_license_is_supported_without_general_no_extension_allowlist(self):
        license = self.root / "output/one/provenance/vendor/three-0.160.0/LICENSE"
        license.parent.mkdir(parents=True)
        license.write_bytes(b'MIT License\nCopyright retained dependency\n')
        self.snapshot.source_files = [license]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原稿/" + license.relative_to(self.root).as_posix()), license.read_bytes())
        unknown = license.parent.parent / "LICENSE"
        unknown.write_bytes(license.read_bytes())
        self.snapshot.source_files = [unknown]
        self.assertFalse(self.export()["complete"])

    def test_named_repair_before_copies_keep_bytes_and_underlying_safety_checks(self):
        source = self.root / "output/repair"
        source.mkdir(parents=True)
        originals = {"compiler.py.before": b'raise RuntimeError("never execute")\n',
                     "revised.scene.json.before-finite": b'{ "html":"<p>original</p>" }\n'}
        for name, raw in originals.items():
            (source / name).write_bytes(raw)
        self.snapshot.source_roots = [source]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            for name, raw in originals.items():
                self.assertEqual(archive.read("原稿/output/repair/" + name), raw)
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(next(item["mimeType"] for item in manifest["files"]
                if item["archivePath"].endswith(".json.before-finite")), "application/json")
        (source / "revised.scene.json.before-finite").write_bytes(b'{"childId":"private"}')
        self.assertFalse(self.export()["complete"])
        (source / "revised.scene.json.before-finite").write_bytes(originals["revised.scene.json.before-finite"])
        (source / "compiler.py.before").write_bytes(b'API_KEY="short"\n')
        self.assertFalse(self.export()["complete"])

    def test_raw_http_pdf_response_needs_exact_sidecar_hash_size_and_signature(self):
        source = self.root / "output/job/http-original-response.bin"
        source.parent.mkdir(parents=True)
        raw = b'%PDF-1.6\nOriginal retained public source\n%%EOF\n'
        source.write_bytes(raw)
        record = {"scheme": "http", "contentType": "application/pdf", "startsPDF": True,
                  "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        metadata = source.parent / "metadata.json"
        metadata.write_text(json.dumps([record]))
        self.snapshot.source_files = [source, metadata]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原稿/output/job/http-original-response.bin"), raw)
            manifest = json.loads(archive.read("manifest.json"))
            entry = next(item for item in manifest["files"] if item["archivePath"].endswith(".bin"))
            self.assertEqual(entry["mimeType"], "application/pdf")
        source.write_bytes(raw.replace(b'Original', b'Modified'))
        with self.assertRaisesRegex(CourseArchiveError, "original_response_integrity"):
            self.export()

    def test_sensitive_database_fields_fail_closed_and_token_counts_are_allowed(self):
        _check_public({"maxTokens": 100, "usage": {"input_tokens": 20}, "apiKey": ""})
        _check_public({"authorization": "用户已明确授权保存原稿并复用本轮已通过的教学审核，不得重新发起付费生成。"})
        _check_public({"authorization": "The user explicitly authorized this retained course draft for reviewed publication."})
        for record in ({"access_token": "private"}, {"content_json": '{"childId":"child"}'},
                       {"runtimeToken": "secret"}, {"privateKey": "secret"},
                       {"authorization": "Bearer private-token 用户中文授权"},
                       {"authorization": "Basic private-token 用户中文授权"},
                       {"authorization": "Token private-token 用户中文授权"},
                       {"authorization": "a" * 48}):
            with self.subTest(record=record), self.assertRaisesRegex(CourseArchiveError, "credential_or_student"):
                _check_public(record)

    def test_public_image_reference_and_inert_source_fixture_do_not_exempt_real_credentials(self):
        public = "https://pics0.baidu.com/feed/" + "a" * 40 + ".jpeg@f_auto?token=" + "b" * 32
        _check_public({"research": "![reference](" + public + ")"})
        for unsafe in (public + "&access_token=private", public.replace("pics0.baidu.com", "private.example"),
                       public.replace(".jpeg@f_auto", ".png"), public.replace("b" * 32, "b" * 33)):
            with self.subTest(unsafe=unsafe), self.assertRaises(CourseArchiveError):
                _check_public(unsafe)
        source = self.root / "output/check.test.ts"
        source.parent.mkdir(parents=True)
        raw = b'const cookie="11111111-1111-4111-8111-111111111111"; const map={accesskey:"accessKey"};'
        source.write_bytes(raw)
        self.snapshot.source_files = [source]
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原稿/output/check.test.ts"), raw)
        source.write_bytes(raw.replace(b'11111111-1111-4111-8111-111111111111', b'22222222-2222-4222-8222-222222222222'))
        self.assertFalse(self.export()["complete"])

    def test_large_embedded_asset_does_not_hide_following_short_credential(self):
        from services.course_archive_exporter import _check_source_text
        prefix = b'const image="data:image/png;base64,' + b'A' * (1024 * 1024) + b'";\n'
        _check_source_text(prefix + b'const key=process.env.PROVIDER_API_KEY;', ".js")
        for assignment in (b'const PROVIDER_API_KEY="short";', b'const providerKey="short";'):
            with self.subTest(assignment=assignment), self.assertRaises(CourseArchiveError):
                _check_source_text(prefix + assignment, ".js")
        _check_source_text(b"const view=`${occupied ? chair.childId : 'empty'}`;", ".html")
        with self.assertRaises(CourseArchiveError):
            _check_source_text(b'actual.childId = "private-student";', ".html")

    def test_future_authoring_binding_refreshes_exact_job_and_keeps_control_private(self):
        room = {"stage": {"id": "stage_new"}, "scenes": [{"id": "scene1", "type": "slide"}]}
        meta = {"courseId": "native-new", "courseVersion": "saved-1", "title": "新课", "subject": "science",
                "generatedAt": "2026-10-23T09:10:11Z"}
        # The daemon has already scanned before this job was created.
        self.assertEqual(self.exporter._workbench_jobs(), [])
        teaching = self.root / "output/book/node/teaching-1"
        job = teaching / "authoring-job"
        job.mkdir(parents=True)
        draft = b'{"request":"Teach one observation","pagePlan":[{"goal":"compare"}]}'
        frozen = {"teachingRevision": 1, "draftSha256": hashlib.sha256(draft).hexdigest(),
                  "requestSha256": hashlib.sha256(b'Teach one observation').hexdigest()}
        (job / "draft.json").write_bytes(draft)
        (job / "frozen.json").write_text(json.dumps(frozen))
        (job / "state.json").write_text(json.dumps({"sessionId": "private-author-session", "savedStages": []}))
        (job / "policy.json").write_bytes(b'{"interactionPolicy":"frozen"}')
        digest = self.exporter._native_digest(room)
        result = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage", source_digest=digest,
            staging_root=self.staging / "native", meta=meta, authoring_binding={"sessionId": "private-author-session"})
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原稿/output/book/node/teaching-1/authoring-job/draft.json"), draft)
            self.assertFalse(any(name.endswith("state.json") for name in archive.namelist()))
            self.assertFalse(any(b'private-author-session' in archive.read(name) for name in archive.namelist()))
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["excludedFiles"][0]["reason"], "private_authoring_runtime_control")
        (job / "draft.json").write_bytes(draft + b' ')
        with self.assertRaisesRegex(CourseArchiveError, "authoring_original_integrity"):
            self.exporter.export_native_snapshot(room, source_kind="native_pg_stage", source_digest=digest,
                staging_root=self.staging / "native", meta=meta, authoring_binding={"sessionId": "private-author-session"})
        (job / "draft.json").write_bytes(draft)
        (job / "state.json").write_text(json.dumps({"sessionId": "private-author-session",
            "savedStages": [{"stageId": "stage_new"}]}))
        historical = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage", source_digest=digest,
            staging_root=self.staging / "native", meta=meta)
        with zipfile.ZipFile(historical["zip"]["path"]) as archive:
            self.assertIn("原稿/output/book/node/teaching-1/authoring-job/draft.json", archive.namelist())
        direct = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage", source_digest=digest,
            staging_root=self.staging / "native", meta=meta, authoring_binding={"sessionId": "direct-native-session"})
        self.assertTrue(direct["complete"])
        with zipfile.ZipFile(direct["zip"]["path"]) as archive:
            self.assertFalse(any("authoring-job" in name for name in archive.namelist()))

    def test_migrated_remote_failure_never_reads_local_fallback(self):
        path = self.root / self.media_path
        path.parent.mkdir(parents=True)
        path.write_bytes(self.media)
        self.store.read.side_effect = CourseMediaStorageError("Course media integrity failed")
        with self.assertRaises(CourseMediaStorageError):
            self.export()
        self.assertFalse(list(self.staging.rglob("index.json")))

    def test_remote_wrong_sha_is_rejected_and_local_unlisted_bytes_are_verified(self):
        self.store.read.return_value = b"corrupt"
        with self.assertRaisesRegex(CourseArchiveError, "published_media_hash_mismatch"):
            self.export()
        self.store.read.return_value = None
        path = self.root / self.media_path
        path.parent.mkdir(parents=True)
        path.write_bytes(self.media)
        self.assertTrue(self.export()["complete"])

    def test_symlinks_traversal_and_unapproved_staging_are_rejected(self):
        link = self.root / "output/linked.json"
        link.parent.mkdir()
        target = self.root / "secret.json"
        target.write_text('{}')
        link.symlink_to(target)
        self.snapshot.source_files = [link]
        with self.assertRaisesRegex(CourseArchiveError, "linked"):
            self.export()
        self.snapshot.source_files = []
        self.snapshot.documents["../escape.json"] = {}
        with self.assertRaisesRegex(CourseArchiveError, "archive_path_invalid"):
            self.export()
        with self.assertRaisesRegex(CourseArchiveError, "staging_root_must"):
            self.exporter.export_snapshot(self.snapshot, staging_root=self.root / "unapproved")

    def test_release_identity_mismatch_and_unsafe_object_directory_rejected(self):
        self.release["releaseSha256"] = "c" * 64
        with self.assertRaisesRegex(CourseArchiveError, "identity_mismatch"):
            self.export()
        self.release["releaseSha256"] = "b" * 64
        self.release["storageDirectory"] = "2026-10-23/科学/../escape"
        with self.assertRaisesRegex(CourseArchiveError, "archive_path_invalid"):
            self.export()

    def test_future_saved_snapshot_is_explicit_and_requires_source_digest(self):
        self.snapshot.status = "generated_saved"
        result = self.export(source_kind="native_terminal", source_digest="d" * 64)
        self.assertEqual(result["status"], "generated_saved")
        with self.assertRaisesRegex(CourseArchiveError, "source_digest_invalid"):
            self.export(source_kind="native_terminal", source_digest="invalid")

    def test_native_public_entry_preserves_original_capture_and_never_claims_publication(self):
        snapshot = {"id": "stage_new", "stage": {"id": "stage_new", "name": "新课"},
                    "scenes": [{"id": "scene1", "stageId": "stage_new", "type": "slide"}]}
        raw = json.dumps(snapshot, ensure_ascii=False, indent=2)
        meta = {"courseId": "native-saved:stage_new", "courseVersion": "saved-1",
                "title": "新课", "subject": "course", "generatedAt": "2026-10-23T09:10:11Z", "sourceRaw": raw}
        result = self.exporter.export_native_snapshot(snapshot, source_kind="native_pg_stage",
            source_digest=hashlib.sha256(raw.encode()).hexdigest(), staging_root=self.staging / "saved", meta=meta)
        self.assertEqual(result["status"], "generated_saved")
        self.assertIsNone(result["releaseSha256"])
        self.assertEqual(result["sourceDigest"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertTrue(result["objectDirectory"].startswith("课程/未绑定教材/未标注年级/"))
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("Native终态快照.json"), raw.encode())
        with self.assertRaisesRegex(CourseArchiveError, "source_digest_mismatch"):
            self.exporter.export_native_snapshot(snapshot, source_kind="native_pg_stage", source_digest="a" * 64,
                staging_root=self.staging / "saved", meta=meta)

    def test_native_js_digest_covers_javascript_number_and_unicode_serialization(self):
        snapshot = {"stage": {"id": "stage_new", "x": 1.0, "y": 0.0000001},
                    "scenes": [{"id": "scene1", "type": "slide"}]}
        canonical = '{"scenes":[{"id":"scene1","type":"slide"}],"stage":{"id":"stage_new","x":1,"y":1e-7}}'
        self.assertEqual(self.exporter._native_digest(snapshot), hashlib.sha256(canonical.encode()).hexdigest())

    def test_revised_publication_keeps_original_frozen_authoring_version(self):
        teaching = self.root / "output/book/node/teaching-1"
        job = teaching / "authoring-job"
        job.mkdir(parents=True)
        (teaching / "sources").mkdir()
        review = teaching / "sources/source-review.json"
        review.write_text('{}')
        (job / "frozen.json").write_text(json.dumps({"binding": {"editionId": "book", "nodeId": "node"}, "teachingRevision": "1"}))
        self.exporter._textbook_sources(self.snapshot,
            {"sourceScope": {"localReviewPath": str(review.relative_to(self.root))}},
            {"textbookBinding": {"editionId": "book", "nodeId": "node", "teachingRevision": "5"}})
        self.assertIn(teaching, self.snapshot.source_roots)
        changed = deepcopy(self.snapshot)
        with self.assertRaisesRegex(CourseArchiveError, "binding_mismatch"):
            self.exporter._textbook_sources(changed,
                {"sourceScope": {"localReviewPath": str(review.relative_to(self.root))}},
                {"textbookBinding": {"editionId": "other-book", "nodeId": "node", "teachingRevision": "5"}})

    def test_saved_preview_preserves_plan_review_and_raw_database_fields(self):
        from content.textbook_catalog import digest
        room_raw = json.dumps(self.snapshot.classroom, ensure_ascii=False, indent=2)
        plan = {"subject": "science", "gradeCode": "primary_1", "lessonTitle": "怎样学科学",
                "pagePlan": [{"goal": "观察并比较"}], "editionId": "book", "nodeId": "node"}
        row = {"preview_key": "d" * 64, "status": "review_required", "classroom_json": room_raw,
               "classroom_sha256": digest(self.snapshot.classroom), "classroom_id": "tbpub_test",
               "input_json": json.dumps(plan, ensure_ascii=False), "result_json": '{"review":"needs audio"}',
               "edition_id": "book", "revision_id": "directory", "node_id": "node"}
        manifest = {"subject": "science", "gradeCode": "primary_1", "editionId": "book", "title": "科学"}
        revision = {"manifest_json": json.dumps(manifest, ensure_ascii=False), "manifest_sha256": digest(manifest)}
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [row, revision]
        result = self.exporter.export_saved_preview(conn, preview_key="d" * 64, staging_root=self.staging / "review")
        self.assertTrue(result["complete"])
        self.assertEqual(result["status"], "generated_saved")
        self.assertIsNone(result["releaseSha256"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原始课堂.json"), room_raw.encode())
            self.assertEqual(archive.read("冻结创作请求.json"), row["input_json"].encode())
            self.assertEqual(archive.read("数据库原字段/原始预览记录/000-result_json.json"), row["result_json"].encode())
        self.assertTrue(all(c.args[0].lstrip().startswith("SELECT") for c in conn.execute.call_args_list))

    def test_unknown_original_format_blocks_complete_instead_of_silently_omitting(self):
        path = self.root / "output/lesson-source.custom"
        path.parent.mkdir()
        path.write_bytes(b"unique original")
        self.snapshot.source_files = [path]
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["missingSources"][0]["kind"], "unclassified_original")
        self.assertEqual(result["generatedPublicFiles"], [])

    def test_frozen_compiler_source_is_archived_verbatim_without_execution(self):
        capsule = self.root / "output/one/compiler-source-capsule"
        capsule.mkdir(parents=True)
        marker = self.root / "must-not-run"
        raw = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n").encode()
        (capsule / "compiler.py").write_bytes(raw)
        (capsule / "activity.ts").write_text("throw new Error('must not execute');\n")
        (capsule / "layout.css").write_text("button { min-height: 48px; }\n")
        (capsule / "config.yaml").write_text("schemaVersion: source-capsule-v1\n")
        self.snapshot.source_roots = [capsule]
        result = self.export()
        self.assertTrue(result["complete"])
        self.assertFalse(marker.exists())
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原稿/output/one/compiler-source-capsule/compiler.py"), raw)

    def test_source_and_config_credentials_still_block_complete(self):
        source = self.root / "output/compiler-source-capsule/config.yaml"
        source.parent.mkdir(parents=True)
        self.snapshot.source_files = [source]
        for raw in (b"secret_key: small-secret\n", b"password: 'short'\n"):
            source.write_bytes(raw)
            result = self.export()
            self.assertFalse(result["complete"])
            self.assertEqual(result["generatedPublicFiles"], [])
            self.assertEqual(result["missingSources"][0]["kind"], "unsafe_original")
        python = source.with_suffix(".py")
        python.write_text("api_key = 'short'\n")
        self.snapshot.source_files = [python]
        self.assertFalse(self.export()["complete"])

    def test_retired_legacy_adapter_retains_original_and_lifecycle_without_publication(self):
        stage = "stage-retired"
        room = {"id": stage, "stage": {"id": stage, "name": "退休课程"},
                "scenes": [{"id": "s1", "type": "slide"}]}
        raw = json.dumps(room, ensure_ascii=False, indent=2).encode()
        path = self.root / "openmaic-runtime/.runtime/OpenMAIC/data/classrooms" / (stage + ".json")
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
        result = self.exporter.export_legacy_classroom(stage, staging_root=self.staging / "retired",
                                                      meta={"lifecycleStatus": "retired", "retired": True})
        self.assertTrue(result["complete"])
        self.assertEqual(result["status"], "generated_saved")
        self.assertIsNone(result["releaseSha256"])
        self.assertEqual(result["sourceDigest"], hashlib.sha256(raw).hexdigest())
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原始课堂.json"), raw)
            self.assertEqual(json.loads(archive.read("metadata.json"))["lifecycleStatus"], "retired")

    def test_saved_audio_alias_recovers_only_exact_successful_paid_original(self):
        request = "tbprev_" + "a" * 64
        classroom = "tbwork_saved"
        audio_root = self.exporter.native_root / "data/formal-audio"
        asset = audio_root / "assets/mirawav_original.wav"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(self.media)
        checksum = hashlib.sha256(self.media).hexdigest()
        job = {"kind": "tts", "state": "succeeded", "requestId": request,
               "classroomId": classroom, "audioSha256": checksum, "sizeBytes": len(self.media),
               "mimeType": "audio/wav", "assetFileName": asset.name}
        job_path = audio_root / "jobs/tts" / (hashlib.sha256(request.encode()).hexdigest() + ".json")
        job_path.parent.mkdir(parents=True)
        job_path.write_text(json.dumps(job))
        alias = f"/api/classroom-media/{classroom}/audio/{request}.wav"
        self.snapshot.classroom["scenes"][0]["actions"] = [{"type": "speech", "audioId": request, "audioUrl": alias}]
        self.snapshot.media = []
        self.store.config = CourseStorageConfig(mode="local")
        self.store.read.return_value = None
        receipts = [{"requestId": request, "status": "succeeded", "mimeType": "audio/wav", "audioSha256": checksum}]
        self.exporter._collect_snapshot_media(self.snapshot, audio_receipts=receipts)
        self.assertFalse(self.snapshot.missing_sources)
        self.assertIn(job_path, self.snapshot.source_files)
        result = self.export()
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            logical = "媒体/openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + classroom + "/audio/" + request + ".wav"
            self.assertEqual(archive.read(logical), self.media)
        # A changed receipt or a job belonging to another classroom cannot
        # authorize the retained bytes even if a same-named file is present.
        self.snapshot.media, self.snapshot.missing_sources = [], []
        receipts[0]["audioSha256"] = "d" * 64
        self.exporter._collect_snapshot_media(self.snapshot, audio_receipts=receipts)
        self.assertEqual(len(self.snapshot.missing_sources), 1)
        self.assertFalse(self.snapshot.media)

    def test_catalog_review_revision_changes_without_forging_release_digest(self):
        from services import course_archive_exporter as exporter_module
        row = {"content_key": "a" * 64, "course_id": "course", "course_version": "1",
               "input_json": '{"previewKey":"preview"}', "release_sha256": "b" * 64,
               "build_updated_at": 10, "course_updated_at": 20, "title": "课件",
               "subject": "science", "grade_code": "primary_1"}
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [row, {"updated_at": 30, "result_json": '{"review":1}'},
                                                        row, {"updated_at": 31, "result_json": '{"review":2}'}]
        with patch.object(exporter_module.releases, "_current_keys", return_value=["a" * 64]), \
             patch.object(exporter_module.releases, "_other_published_courses", return_value=[]):
            a = self.exporter.list_courses(conn)[0]
            b = self.exporter.list_courses(conn)[0]
        self.assertEqual(a["sourceDigest"], b["sourceDigest"])
        self.assertEqual(a["sourceDigest"], "b" * 64)
        self.assertNotEqual(a["archiveSourceRevision"], b["archiveSourceRevision"])

    def test_unresolved_standard_asset_blocks_complete_and_public_upload(self):
        self.snapshot.classroom["scenes"][0]["content"] = {"type": "slide", "canvas": {
            "elements": [{"type": "image", "id": "image1", "src": "ast_owned_image"}]}}
        self.exporter.standard_asset_resolver = lambda doc, **kwargs: {
            "entries": [{"ref": "ast_owned_image", "kind": "image", "status": "unresolved"}],
            "unresolved": [{"ref": "ast_owned_image", "reason": "asset_bytes_missing"}]}
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertEqual(result["missingSources"][0]["sourceIdentity"], "ast_owned_image")

    def test_resolved_standard_asset_is_verified_and_original_reference_is_preserved(self):
        ref, data = "ast_owned_image", b"the exact registered image bytes"
        self.snapshot.classroom["scenes"][0]["content"] = {"type": "slide", "canvas": {
            "elements": [{"type": "image", "id": "image1", "src": ref}]}}
        def resolve(document, *, staging_root):
            staging_root.mkdir(parents=True, exist_ok=True)
            source = staging_root / "image.webp"
            source.write_bytes(data)
            return {"entries": [{"ref": ref, "kind": "image", "status": "resolved", "sourcePath": str(source),
                "sha256": hashlib.sha256(data).hexdigest(), "byteSize": len(data), "mimeType": "image/webp"}], "unresolved": []}
        self.exporter.standard_asset_resolver = resolve
        original = deepcopy(self.snapshot.classroom)
        result = self.export()
        self.assertTrue(result["complete"])
        self.assertEqual(self.snapshot.classroom, original)
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("Native素材/图片-001.webp"), data)
            self.assertIn(ref, archive.read("classroom.json").decode())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(next(x for x in manifest["files"] if x["sourceKind"] == "native_standard_asset")["sourceIdentity"], ref)

    def test_standard_asset_resolver_cannot_supply_unrelated_files(self):
        data = b"unrelated"
        source = self.root / "unrelated.webp"
        source.write_bytes(data)
        self.exporter.standard_asset_resolver = lambda document, **kwargs: {
            "entries": [{"ref": "ast_owned_image", "kind": "image", "status": "resolved", "sourcePath": str(source),
                "sha256": hashlib.sha256(data).hexdigest(), "byteSize": len(data), "mimeType": "image/webp"}], "unresolved": []}
        with self.assertRaisesRegex(CourseArchiveError, "standard_asset_bytes_mismatch"):
            self.export()

    def test_export_course_checks_injected_adapter_identity_without_mutating_connection(self):
        conn = Mock()
        adapter = Mock(return_value=self.snapshot)
        result = self.exporter.export_course(conn, course_id="course", course_version="1",
            staging_root=self.staging / "exports", source_adapter=adapter, release=self.release)
        self.assertTrue(result["complete"])
        conn.assert_not_called()
        self.assertEqual(conn.method_calls, [])
        wrong = deepcopy(self.snapshot)
        wrong.identity["courseId"] = "other"
        with self.assertRaisesRegex(CourseArchiveError, "source_adapter_identity_mismatch"):
            self.exporter.export_course(conn, course_id="course", course_version="1",
                staging_root=self.staging / "exports", source_adapter=lambda *a, **k: wrong)


if __name__ == "__main__":
    unittest.main()
