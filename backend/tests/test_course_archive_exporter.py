"""Archive recovery bytes, ownership boundaries and public upload contracts."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from services.course_archive_exporter import (
    ArchiveSnapshot, CourseArchiveError, CourseArchiveExporter, _check_public, _safe_name, _storage_name,
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
            standard_asset_resolver=lambda document, **kwargs: {"entries": [], "unresolved": []},
            material_inventory_loader=lambda request: {"schemaVersion": "mira.course-material-inventory.v1",
                "materials": [], "dependencySha256": hashlib.sha256(b"[]").hexdigest()})
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

    def test_registry_directory_scan_captures_new_owned_media_before_its_first_archive(self):
        helper = self.root / 'openmaic-runtime/scripts/course-archive-assets.mjs'
        helper.parent.mkdir(parents=True)
        helper.write_text('// fixture transport')
        prefix = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/omclass_new/artifact/media'
        image = self.root / prefix / 'lesson-picture.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'new lesson image')
        self.store.config = CourseStorageConfig(mode='registry', endpoint='http://storage.invalid', bucket='study')
        registry_store = Mock()
        registry_store.repository.paths_under.return_value = []
        registry_store.repository.resolve.return_value = None
        registry_store.read_bytes.return_value = None
        result = Mock(returncode=0, stdout=json.dumps({'schemaVersion':'mira.course-archive.assets.v1',
            'entries': [], 'unresolved': []}))
        document = {'stage':{'id':'omclass_new'}, 'scenes':[{'content':{
            'html':'<img src="/api/classroom-media/omclass_new/media/">'}}]}
        with patch('services.course_archive_exporter.CourseFileStore', return_value=registry_store), \
                patch('services.course_archive_exporter.subprocess.run', return_value=result) as run:
            self.exporter._standard_assets(document, staging_root=self.staging)
        sent = json.loads(run.call_args.kwargs['input'])
        self.assertEqual(sent['registryFiles'], [{'path': prefix+'/lesson-picture.png',
            'sha256': hashlib.sha256(image.read_bytes()).hexdigest(), 'byteSize': image.stat().st_size,
            'mimeType':'image/png'}])
        registry_store.repository.paths_under.assert_called_once()
        self.assertEqual(registry_store.repository.paths_under.call_args.args[0], prefix)

    def retained_review_fixture(self):
        from PIL import Image
        edition = self.root / "output/textbook-operator-lessons/book"
        teaching = edition / "lesson/teaching-1"
        job = teaching / "authoring-job"
        receipts = job / "followup/asset-receipts"
        receipts.mkdir(parents=True)
        draft = b'{"lesson":"picture actions"}'
        (job / "draft.json").write_bytes(draft)
        frozen = {"binding": {"editionId": "book", "nodeId": "lesson"},
                  "teachingRevision": 1, "draftSha256": hashlib.sha256(draft).hexdigest()}
        (job / "frozen.json").write_text(json.dumps(frozen))
        source = edition / "review-assets/actions/teacher.png"
        source.parent.mkdir(parents=True)
        image = BytesIO()
        Image.new("RGB", (2, 2), "red").save(image, format="PNG")
        raw = image.getvalue()
        source.write_bytes(raw)
        ref = "/review-assets/actions/teacher.png"
        receipt = receipts / "teacher.json"
        value = {"schemaVersion": "mira.textbook.review-asset-source-receipt.v1",
                 "sourceFilePath": str(source), "sourceFileSha256": hashlib.sha256(raw).hexdigest(),
                 "reviewUrl": ref}
        receipt.write_text(json.dumps(value))
        self.snapshot.metadata["editionId"] = "book"
        self.snapshot.source_roots = [teaching]
        self.snapshot.classroom["scenes"][0]["content"]["html"] = '<img src="' + ref + '">'
        entry = {"ref": ref, "kind": "image", "status": "unresolved",
                 "reason": "controlled_public_asset_missing_or_invalid"}
        result = {"entries": [entry], "unresolved": [entry.copy()]}
        return source, receipt, value, raw, result

    def test_owned_review_receipt_recovers_exact_png_and_is_itself_archived(self):
        source, receipt, _, raw, unresolved = self.retained_review_fixture()
        self.exporter.standard_asset_resolver = lambda *args, **kwargs: deepcopy(unresolved)
        result = self.export()
        self.assertTrue(result["complete"], result["missingSources"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            asset = next(x for x in manifest["files"] if x["sourceKind"] == "native_standard_asset")
            self.assertEqual(archive.read(asset["archivePath"]), raw)
            proof = asset["sourceReceipt"]
            proof_file = next(x for x in manifest["files"] if x["archivePath"] == proof["archivePath"])
            self.assertEqual(proof_file["sha256"], hashlib.sha256(receipt.read_bytes()).hexdigest())
            self.assertEqual(proof["sha256"], proof_file["sha256"])
            self.assertIn(unresolved["entries"][0]["ref"], archive.read("classroom.json").decode())
        self.assertEqual(source.read_bytes(), raw)
        self.assertFalse((self.root / "openmaic-runtime/.runtime/OpenMAIC/public/review-assets").exists())

    def test_review_recovery_rejects_unbound_or_changed_sources(self):
        source, receipt, value, raw, unresolved = self.retained_review_fixture()
        frozen_path = self.snapshot.source_roots[0] / "authoring-job/frozen.json"
        frozen = frozen_path.read_bytes()
        outside = self.root / "output/textbook-operator-lessons/other/review-assets/actions/teacher.png"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(raw)
        cases = ("hash", "outside_edition", "wrong_ref", "symlink", "no_receipt",
                 "no_owned_root", "wrong_frozen_edition", "changed_draft", "not_png")
        for case in cases:
            with self.subTest(case=case):
                if source.is_symlink():
                    source.unlink()
                source.write_bytes(raw)
                receipt.write_text(json.dumps(value))
                frozen_path.write_bytes(frozen)
                (frozen_path.parent / "draft.json").write_bytes(b'{"lesson":"picture actions"}')
                roots = self.snapshot.source_roots[:]
                current = dict(value)
                if case == "hash": current["sourceFileSha256"] = "0" * 64
                elif case == "outside_edition": current["sourceFilePath"] = str(outside)
                elif case == "wrong_ref": current["reviewUrl"] = "/review-assets/actions/another.png"
                elif case == "symlink":
                    source.unlink(); source.symlink_to(outside)
                elif case == "no_receipt": receipt.unlink()
                elif case == "no_owned_root": self.snapshot.source_roots = []
                elif case == "wrong_frozen_edition":
                    altered = json.loads(frozen); altered["binding"]["editionId"] = "other"
                    frozen_path.write_text(json.dumps(altered))
                elif case == "changed_draft": (frozen_path.parent / "draft.json").write_text("{}")
                elif case == "not_png":
                    source.write_bytes(b"not a picture")
                    current["sourceFileSha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
                if case != "no_receipt": receipt.write_text(json.dumps(current))
                self.assertEqual(self.exporter._retained_review_assets(self.snapshot), {})
                self.snapshot.source_roots = roots
        receipt.write_text(json.dumps(value))
        source.write_bytes(raw)
        frozen_path.write_bytes(frozen)
        (frozen_path.parent / "draft.json").write_bytes(b'{"lesson":"picture actions"}')
        sources = self.exporter._retained_review_assets(self.snapshot)
        unknown = deepcopy(unresolved)
        unknown["unresolved"][0]["reason"] = "asset_bytes_unresolved"
        recovered = self.exporter._recover_review_assets(unknown, sources, staging_root=self.staging / "assets")
        self.assertEqual(recovered, unknown)

    def test_recovered_asset_without_archived_receipt_cannot_be_complete(self):
        _, _, _, _, unresolved = self.retained_review_fixture()
        self.exporter.standard_asset_resolver = lambda *args, **kwargs: deepcopy(unresolved)
        with patch.object(self.exporter, "_owned_source_files", return_value=[]):
            result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertIn("review_asset_receipt_not_archived", [x["reason"] for x in result["missingSources"]])

    def test_two_valid_receipts_observing_changed_bytes_are_ambiguous(self):
        from PIL import Image
        source, receipt, value, raw, _ = self.retained_review_fixture()
        image = BytesIO()
        Image.new("RGB", (2, 2), "blue").save(image, format="PNG")
        other_raw = image.getvalue()
        other = {**value, "sourceFileSha256": hashlib.sha256(other_raw).hexdigest()}
        (receipt.parent / "teacher-later.json").write_text(json.dumps(other))
        read_bytes = Path.read_bytes
        observed = iter((raw, other_raw))
        def changing_bytes(path):
            return next(observed) if path == source else read_bytes(path)
        with patch.object(Path, "read_bytes", changing_bytes):
            self.assertEqual(self.exporter._retained_review_assets(self.snapshot), {})

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

    def test_storage_labels_are_separate_from_exact_metadata_and_never_override_frozen_directory(self):
        self.snapshot.metadata.update(editionLabel="人教版 · 根据2022年版课程标准修订", volumeLabel="上册",
            gradeLabel="一年级", editionId="pep-chinese", schoolSystem="six_year",
            storageEditionLabel="统编版", storageGradeLabel="一年级上册")
        self.release = {**self.identity, "uploadDate": "2026-10-23"}
        result = self.export()
        self.assertEqual(result["objectDirectory"], "科学/统编版/一年级上册/2026-10-23/怎样学科学")
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            metadata = json.loads(archive.read("metadata.json"))
            self.assertEqual(metadata["editionLabel"], self.snapshot.metadata["editionLabel"])
            self.assertEqual(metadata["editionId"], "pep-chinese")
            self.assertEqual(metadata["schoolSystem"], "six_year")
        self.release["storageDirectory"] = "科学/已冻结版本/已冻结年级/2026-10-23/原目录"
        self.assertEqual(self.export()["objectDirectory"], self.release["storageDirectory"])

    def test_storage_name_matches_the_actual_node_display_name_contract(self):
        values = [
            "外研社版（一年级起点，陈琳主编） · 2011课标版",
            "Unit 1 What's your name?", "快乐读书吧：读书真快乐",
            "一年级上册（五四制）", " .-  spaced\u00a0\u2003name -.. ",
            "\ufeffname\ufeff", "a\u0085b", 'a\\/:*?"<>|#%\x00\x1fb',
            "世" * 41, "a" * 119 + "🌏tail", "a" * 119 + "-tail",
            "", "... --", "？：#", "语文", "ordinary file",
        ]
        script = """import {displayName} from './openmaic-runtime/scripts/course-storage.mjs';
            let data='';for await(const chunk of process.stdin)data+=chunk;
            console.log(JSON.stringify(JSON.parse(data).map(value=>{
              try{return displayName(value);}catch{return null;}
            })));"""
        expected = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", script],
            cwd=Path(__file__).resolve().parents[2], input=json.dumps(values), text=True))
        for value, node_name in zip(values, expected):
            with self.subTest(value=value):
                if node_name is None:
                    with self.assertRaisesRegex(CourseArchiveError, "storage_name_invalid"):
                        _storage_name(value)
                else:
                    self.assertEqual(_storage_name(value), node_name)
        # Original source paths and generated public basenames keep their contract.
        self.assertEqual(_safe_name("快乐读书吧：读书真快乐"), "快乐读书吧：读书真快乐")
        self.assertEqual(len(_safe_name("a" * 161).encode()), 160)

    def test_saved_and_future_fallback_normalize_only_the_four_storage_fields(self):
        raw = {"subjectName": " 英语\u00a0 ",
            "storageEditionLabel": "外研社版（一年级起点，陈琳主编） · 2011课标版",
            "storageGradeLabel": "一年级上册（五四制）", "title": "Unit 1 What's your name?"}
        self.snapshot.metadata.update(raw)
        self.release = {**self.identity, "uploadDate": "2026-10-23"}
        for status in ("published", "generated_saved"):
            with self.subTest(status=status):
                self.snapshot.status = status
                result = self.export()
                self.assertEqual(result["objectDirectory"],
                    "英语/外研社版(一年级起点,陈琳主编) · 2011课标版/一年级上册(五四制)/2026-10-23/Unit 1 What's your name")
                for item in result["generatedPublicFiles"]:
                    self.assertTrue(item["relativePath"].split("/")[-1].startswith("Unit 1 What's your name--"))
                with zipfile.ZipFile(result["zip"]["path"]) as archive:
                    metadata = json.loads(archive.read("metadata.json"))
                    for key, value in raw.items():
                        self.assertEqual(metadata[key], value)

    def test_frozen_published_directory_preserves_non_normalized_collision_suffix(self):
        frozen = "英语/外研社版（一年级起点，陈琳主编）/一年级上册（五四制）/2026-10-23/How are you（版本2）"
        self.release["storageDirectory"] = frozen
        result = self.export()
        self.assertEqual(result["objectDirectory"], frozen)
        self.assertTrue(all(item["relativePath"].startswith(frozen + "/")
                            for item in result["generatedPublicFiles"]))

    def active_release_manifest(self, entries):
        path = self.root / "backend/data/course-storage/active-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schemaVersion": "mira.course-storage.manifest.v2", "snapshotId": "verified-active",
            "files": [], "releases": entries}))
        self.store.config = CourseStorageConfig(mode="manifest", manifest_path=str(path))
        return path

    def test_verified_future_publication_missing_from_media_index_uses_central_labels(self):
        self.active_release_manifest([{**self.release, "courseId": "previous-course"}])
        self.snapshot.metadata.update(subjectName="语文", storageEditionLabel="统编版", storageGradeLabel="一年级上册")
        conn = Mock()
        with patch.object(self.exporter, "_published_snapshot", return_value=self.snapshot) as authority:
            result = self.exporter.export_course(conn, course_id="course", course_version="1", staging_root=self.staging / "future")
        authority.assert_called_once_with(conn, "course", "1", None)
        self.assertTrue(result["complete"])
        self.assertTrue(result["objectDirectory"].startswith("语文/统编版/一年级上册/"))
        self.assertTrue(result["objectDirectory"].endswith("/怎样学科学"))
        with patch.object(self.exporter, "_published_snapshot", side_effect=CourseArchiveError("published_release_invalid")), \
                patch.object(self.exporter, "_dated_release") as directory_lookup:
            with self.assertRaisesRegex(CourseArchiveError, "published_release_invalid"):
                self.exporter.export_course(conn, course_id="course", course_version="1", staging_root=self.staging / "future")
            directory_lookup.assert_not_called()

    def test_dated_release_retains_one_frozen_path_and_rejects_duplicates_or_identity_conflicts(self):
        self.active_release_manifest([self.release])
        self.assertEqual(self.exporter._dated_release(self.identity)["storageDirectory"], self.release["storageDirectory"])
        cases = ([self.release, self.release],
                 [{**self.release, "releaseSha256": "c" * 64}],
                 [{**self.release, "classroomId": "another-classroom"}],
                 [{**self.release, "storageDirectory": ""}])
        for entries in cases:
            with self.subTest(entries=entries):
                self.active_release_manifest(entries)
                with self.assertRaisesRegex(CourseArchiveError, "published_storage_directory_not_bound"):
                    self.exporter._dated_release(self.identity)

    def test_future_release_cannot_treat_invalid_active_manifest_as_an_empty_index(self):
        path = self.active_release_manifest([])
        self.assertIsNone(self.exporter._dated_release(self.identity))
        media_only = json.loads(path.read_text());media_only.pop("releases")
        path.write_text(json.dumps(media_only))
        self.assertIsNone(self.exporter._dated_release(self.identity))
        for invalid in ({"releases": []}, {"schemaVersion": "mira.course-storage.manifest.v2", "snapshotId": "bad", "files": [], "releases": ["bad"]}):
            with self.subTest(invalid=invalid):
                path.write_text(json.dumps(invalid))
                with self.assertRaisesRegex(CourseArchiveError, "published_storage_directory_manifest_invalid"):
                    self.exporter._dated_release(self.identity)

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

    def test_exact_build_id_adapter_preserves_bounded_ascii_text_with_plain_mime(self):
        source = self.root / "output/one/BUILD_ID"
        source.parent.mkdir(parents=True)
        self.snapshot.source_files = [source]
        for raw in (b"Next_build-2026_10", b"Next_build-2026_10\n", b"a" * 128):
            with self.subTest(raw=raw):
                source.write_bytes(raw)
                result = self.export()
                self.assertTrue(result["complete"])
                with zipfile.ZipFile(result["zip"]["path"]) as archive:
                    name = "原稿/output/one/BUILD_ID"
                    self.assertEqual(archive.read(name), raw)
                    manifest = json.loads(archive.read("manifest.json"))
                    entry = next(e for e in manifest["files"] if e["archivePath"] == name)
                    self.assertEqual(entry["mimeType"], "text/plain")
                    self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())

    def test_build_id_rejects_binary_oversize_multiple_lines_and_credential_payloads(self):
        source = self.root / "output/one/BUILD_ID"
        source.parent.mkdir(parents=True)
        self.snapshot.source_files = [source]
        invalid = (b"", b"a" * 129, b"a" * 128 + b"\n", b"one\ntwo", b"one\n\n",
                   b"one\r\n", b"with space", b"\x00build", b"\xff", "版本".encode(),
                   b"password='private'", b"../other", b"Bearer credential-value")
        for raw in invalid:
            with self.subTest(raw=raw):
                source.write_bytes(raw)
                with self.assertRaisesRegex(CourseArchiveError, "original_build_id_invalid"):
                    self.export()
        # Even a syntactically valid identifier still crosses the normal
        # credential/student-token scanner rather than bypassing it.
        source.write_bytes(b"tbpt_" + b"a" * 20)
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertEqual(result["missingSources"][0]["kind"], "unsafe_original")

    def test_build_id_adapter_does_not_admit_unknown_neighbor_or_similarly_named_files(self):
        source = self.root / "output/one"
        source.mkdir(parents=True)
        (source / "BUILD_ID").write_bytes(b"Next_build")
        for name in ("OTHER_ID", "lowercase/build_id", "BUILD_ID.before"):
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"unreviewed original")
        self.snapshot.source_roots = [source]
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertEqual({Path(e["sourceIdentity"]).name for e in result["missingSources"]},
                         {"OTHER_ID", "build_id", "BUILD_ID.before"})
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertIn("原稿/output/one/BUILD_ID", archive.namelist())
            self.assertFalse(any(name.endswith(("/OTHER_ID", "/build_id", "/BUILD_ID.before"))
                                 for name in archive.namelist()))

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
        self.assertTrue(result["objectDirectory"].startswith("课程/未绑定教材(历史课件)/未标注年级/"))
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("Native终态快照.json"), raw.encode())
        with self.assertRaisesRegex(CourseArchiveError, "source_digest_mismatch"):
            self.exporter.export_native_snapshot(snapshot, source_kind="native_pg_stage", source_digest="a" * 64,
                staging_root=self.staging / "saved", meta=meta)

    def test_native_unknown_binding_does_not_infer_unified_textbook_edition(self):
        room = {"stage": {"id": "stage_new"}, "scenes": [{"id": "scene1", "type": "slide"}]}
        meta = {"courseId": "native-new", "courseVersion": "saved-1", "title": "历史课件", "subject": "chinese",
            "generatedAt": "2026-10-23T09:10:11Z", "editionLabel": "统编版", "storageEditionLabel": "统编版",
            "gradeLabel": "一年级", "storageGradeLabel": "一年级上册", "schoolSystem": "six_year"}
        result = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage",
            source_digest=self.exporter._native_digest(room), staging_root=self.staging / "native", meta=meta)
        self.assertIn("/未绑定教材(历史课件)/", result["objectDirectory"])
        meta["editionId"] = "pep-chinese-g1-upper-2022-standard"
        bound = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage",
            source_digest=self.exporter._native_digest(room), staging_root=self.staging / "native", meta=meta)
        self.assertIn("/未绑定教材(历史课件)/", bound["objectDirectory"])
        with zipfile.ZipFile(bound["zip"]["path"]) as archive:
            self.assertEqual(json.loads(archive.read("metadata.json"))["editionId"], meta["editionId"])

    def native_catalog_fixture(self):
        room = {"stage": {"id": "stage_new"}, "scenes": [{"id": "scene1", "type": "slide"}]}
        teaching = self.root / "output/book/node/teaching-1"
        job = teaching / "authoring-job"
        job.mkdir(parents=True)
        draft = b'{"request":"Retained lesson"}'
        (job / "draft.json").write_bytes(draft)
        (job / "state.json").write_text(json.dumps({"sessionId": "private-author", "savedStages": []}))
        manifest = {"schemaVersion": "mira.learning.textbook-manifest.v1", "editionId": "pep-chinese-g1-upper-2022-standard",
            "revisionId": "directory-original", "gradeCode": "primary_1", "subject": "chinese", "volume": "upper",
            "schoolSystem": "six_year", "title": "语文", "publisher": "人民教育出版社",
            "editionLabel": "根据2022年版课程标准修订；出版版次待核验",
            "source": {"resourceId": "1c73b348-e8b6-47d6-84b0-6dbacbe28268"}}
        path = self.root / "backend/content/textbooks/revisions/original.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        checksum = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        frozen = {"teachingRevision": 1, "draftSha256": hashlib.sha256(draft).hexdigest(),
            "binding": {k:manifest[k] for k in ("editionId", "revisionId", "gradeCode", "subject", "volume", "schoolSystem")},
            "catalogCheck": {"manifestSha256": checksum}}
        frozen_path = job / "frozen.json"
        frozen_path.write_text(json.dumps(frozen))
        meta = {"courseId": "native-saved:stage_new", "courseVersion": "saved-original", "title": "新课",
            "subject": "course", "generatedAt": "2026-10-23T09:10:11Z"}
        return room, manifest, path, frozen, frozen_path, meta

    def test_native_frozen_catalog_proof_sets_labels_without_changing_saved_capture(self):
        room, manifest, path, frozen, _, meta = self.native_catalog_fixture()
        original = deepcopy(room)
        digest = self.exporter._native_digest(room)
        result = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage", source_digest=digest,
            staging_root=self.staging / "native", meta=meta, authoring_binding={"sessionId": "private-author"})
        self.assertTrue(result["complete"])
        self.assertEqual(room, original)
        self.assertEqual(result["sourceDigest"], digest)
        self.assertEqual(result["status"], "generated_saved")
        self.assertIsNone(result["contentKey"])
        self.assertIn("语文/统编版/一年级上册/", result["objectDirectory"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            metadata = json.loads(archive.read("metadata.json"))
            for key in ("editionId", "schoolSystem", "revisionId", "gradeCode", "subjectCode", "volumeCode"):
                expected = manifest.get({"subjectCode":"subject", "volumeCode":"volume"}.get(key,key))
                self.assertEqual(metadata[key], expected)
            self.assertEqual(metadata["textbookManifestSha256"], frozen["catalogCheck"]["manifestSha256"])
            self.assertEqual(archive.read("原稿/backend/content/textbooks/revisions/original.json"), path.read_bytes())

    def test_native_catalog_proof_rejects_wrong_digest_identity_and_missing_proof(self):
        room, manifest, path, frozen, frozen_path, meta = self.native_catalog_fixture()
        for case in ("sha", "editionId", "revisionId", "gradeCode", "subject", "volume", "schoolSystem", "no-proof"):
            with self.subTest(case=case):
                changed, capture = deepcopy(manifest), deepcopy(frozen)
                if case == "sha":
                    capture["catalogCheck"]["manifestSha256"] = "f" * 64
                elif case == "no-proof":
                    capture.pop("catalogCheck")
                else:
                    changed[case] = "other-identity"
                    capture["catalogCheck"]["manifestSha256"] = hashlib.sha256(json.dumps(changed,
                        ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                path.write_text(json.dumps(changed))
                frozen_path.write_text(json.dumps(capture))
                result = self.exporter.export_native_snapshot(room, source_kind="native_pg_stage",
                    source_digest=self.exporter._native_digest(room), staging_root=self.staging / "native", meta=meta,
                    authoring_binding={"sessionId": "private-author"})
                self.assertTrue(result["complete"])
                self.assertIn("/未绑定教材(历史课件)/", result["objectDirectory"])
                with zipfile.ZipFile(result["zip"]["path"]) as archive:
                    self.assertNotIn("原稿/backend/content/textbooks/revisions/original.json", archive.namelist())

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

    def saved_preview_fixture(self):
        from content.textbook_catalog import digest
        room_raw = json.dumps(self.snapshot.classroom, ensure_ascii=False, indent=2)
        plan = {"subject": "science", "gradeCode": "primary_1", "lessonTitle": "怎样学科学",
                "pagePlan": [{"goal": "观察并比较"}], "editionId": "book", "nodeId": "node"}
        row = {"preview_key": "d" * 64, "status": "review_required", "classroom_json": room_raw,
               "classroom_sha256": digest(self.snapshot.classroom), "classroom_id": "tbpub_test",
               "input_json": json.dumps(plan, ensure_ascii=False), "result_json": '{"review":"needs audio"}',
               "edition_id": "book", "revision_id": "directory", "node_id": "node"}
        manifest = {"subject": "science", "gradeCode": "primary_1", "editionId": "book", "title": "科学",
                    "editionLabel": "审定教材", "schoolSystem": "six_year", "volume": "upper"}
        revision = {"manifest_json": json.dumps(manifest, ensure_ascii=False), "manifest_sha256": digest(manifest)}
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [row, revision]
        return conn, row, room_raw

    def test_saved_preview_preserves_plan_review_and_raw_database_fields(self):
        conn, row, room_raw = self.saved_preview_fixture()
        result = self.exporter.export_saved_preview(conn, preview_key="d" * 64, staging_root=self.staging / "review")
        self.assertTrue(result["complete"])
        self.assertEqual(result["status"], "generated_saved")
        self.assertIsNone(result["releaseSha256"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原始课堂.json"), room_raw.encode())
            self.assertEqual(archive.read("冻结创作请求.json"), row["input_json"].encode())
            self.assertEqual(archive.read("数据库原字段/原始预览记录/000-result_json.json"), row["result_json"].encode())
        self.assertTrue(all(c.args[0].lstrip().startswith("SELECT") for c in conn.execute.call_args_list))

    def test_old_saved_preview_version_is_rejected_before_export_or_staging(self):
        conn, row, _ = self.saved_preview_fixture()
        staging = self.staging / "old-version"
        with patch.object(self.exporter, "_saved_preview_snapshot", wraps=self.exporter._saved_preview_snapshot) as load, \
                patch.object(self.exporter, "export_snapshot", wraps=self.exporter.export_snapshot) as export, \
                patch.object(self.exporter, "_staging_root", wraps=self.exporter._staging_root) as allocate:
            with self.assertRaisesRegex(CourseArchiveError, "saved_preview_version_mismatch"):
                self.exporter.export_course(conn, course_id="textbook-preview:" + row["preview_key"],
                    course_version="saved-" + "0" * 16, staging_root=staging)
        load.assert_called_once_with(conn, row["preview_key"])
        export.assert_not_called()
        allocate.assert_not_called()
        self.assertFalse(staging.exists())
        self.assertFalse(list(self.staging.rglob("*.zip")))

    def test_current_saved_preview_version_exports_the_single_validated_snapshot(self):
        conn, row, room_raw = self.saved_preview_fixture()
        staging = self.staging / "current-version"
        version = "saved-" + row["classroom_sha256"][:16]
        with patch.object(self.exporter, "_saved_preview_snapshot", wraps=self.exporter._saved_preview_snapshot) as load, \
                patch.object(self.exporter, "export_snapshot", wraps=self.exporter.export_snapshot) as export:
            result = self.exporter.export_course(conn, course_id="textbook-preview:" + row["preview_key"],
                course_version=version, staging_root=staging)
        load.assert_called_once_with(conn, row["preview_key"])
        export.assert_called_once()
        self.assertEqual(export.call_args.kwargs, {"staging_root": staging, "release": None,
            "source_kind": "textbook_preview", "source_digest": row["classroom_sha256"]})
        self.assertTrue(result["complete"])
        self.assertEqual(result["courseVersion"], version)
        self.assertEqual(result["status"], "generated_saved")
        self.assertEqual(result["sourceKind"], "textbook_preview")
        self.assertEqual(result["sourceDigest"], row["classroom_sha256"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原始课堂.json"), room_raw.encode())
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

    def material_alias_fixture(self):
        stage, material = "stage_history", "mat_original"
        teaching = self.root / "output/book/node/teaching-1"
        job, attachments = teaching / "authoring-job", teaching / "authoring-job/page-assets-v1"
        attachments.mkdir(parents=True, exist_ok=True)
        image = teaching / "derived/image.png"
        image.parent.mkdir(exist_ok=True)
        data = b'\x89PNG\r\n\x1a\nexact retained material bytes'
        image.write_bytes(data)
        checksum = hashlib.sha256(data).hexdigest()
        good = f"/api/classroom-media/{stage}/media/material-{material}-{checksum}.png"
        bad = f"/api/classroom-media/{stage}/media/material-{material}-{'b' * 64}.png"
        live = self.root / ("openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + good.removeprefix("/api/classroom-media/"))
        live.parent.mkdir(parents=True, exist_ok=True)
        live.write_bytes(data)
        draft = b'{"request":"Retained lesson"}'
        (job / "draft.json").write_bytes(draft)
        frozen = {"binding": {"editionId": "book", "nodeId": "node"}, "teachingRevision": 1,
            "draftSha256": hashlib.sha256(draft).hexdigest(), "payloadSha256": "a" * 64}
        state = {"sessionId": "private-author", "savedStages": [{"stageId": stage}]}
        intent = {"assetKey": "portrait", "sessionId": "private-author", "sourceSha256": checksum, "byteSize": len(data)}
        intent_raw = json.dumps(intent).encode()
        receipt = {"intentSha256": hashlib.sha256(intent_raw).hexdigest(), "response": {"material": {
            "materialId": material, "bytes": len(data), "mime": "image/png"}}}
        manifest = {"schemaVersion": "mira.operator.frozen-material-attachments.v1",
            "baseDraftSha256": frozen["draftSha256"], "basePayloadSha256": frozen["payloadSha256"],
            "assets": [{"assetKey": "portrait", "sourcePath": str(image), "mimeType": "image/png", "sha256": checksum, "bytes": len(data)}]}
        manifest["sha256"] = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        files = {job / "frozen.json": frozen, job / "state.json": state,
            attachments / "portrait-intent.json": intent, attachments / "portrait-receipt.json": receipt,
            attachments / "manifest.json": manifest}
        for path, value in files.items():
            path.write_text(json.dumps(value))
        room = {"stage": {"id": stage}, "scenes": [{"id": "old", "content": {"html": f'<img src="{good}"><img src="{bad}">'}}]}
        self.snapshot.documents["历史原稿.json"] = json.dumps(room)
        self.snapshot.source_roots = [teaching]
        self.store.config = CourseStorageConfig(mode="local")
        self.store.read.side_effect = lambda path, **kwargs: None if path.suffix == ".png" else self.media
        return {"files": files, "image": image, "data": data, "good": good, "bad": bad, "teaching": teaching,
            "frozen": job / "frozen.json", "state": job / "state.json", "intent": attachments / "portrait-intent.json",
            "receipt": attachments / "portrait-receipt.json", "manifest": attachments / "manifest.json"}

    def test_retained_material_alias_keeps_wrong_original_ref_and_verifies_bytes_without_live_repair(self):
        fixture = self.material_alias_fixture()
        original = deepcopy(self.snapshot.documents)
        result = self.export()
        self.assertTrue(result["complete"])
        self.assertEqual(self.snapshot.documents, original)
        bad_path = self.root / ("openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + fixture["bad"].removeprefix("/api/classroom-media/"))
        self.assertFalse(bad_path.exists())
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            alias = manifest["recoveredAliases"][0]
            self.assertEqual(alias["originalReference"], fixture["bad"])
            self.assertEqual(alias["sha256"], hashlib.sha256(fixture["data"]).hexdigest())
            self.assertEqual(alias["recoveryReason"], "historical_material_alias_from_verified_upload_receipt")
            self.assertEqual(archive.read(alias["archivePath"]), fixture["data"])
            self.assertEqual(archive.namelist().count(alias["archivePath"]), 1)
            self.assertIn(fixture["bad"], archive.read("历史原稿.json").decode())
            self.assertEqual(len(alias["evidence"]), 4)

    def test_material_alias_rejects_unbound_stage_owner_material_and_changed_proofs(self):
        fixture = self.material_alias_fixture()
        cases = ("material", "intent_hash", "manifest_hash", "bytes", "stage", "owner", "frozen", "unowned_source")
        for case in cases:
            with self.subTest(case=case):
                for path, value in fixture["files"].items():
                    path.write_text(json.dumps(value))
                self.snapshot.source_roots = [fixture["teaching"]]
                fixture["image"].write_bytes(fixture["data"])
                if case == "material":
                    value = deepcopy(fixture["files"][fixture["receipt"]]);value["response"]["material"]["materialId"] = "mat_other"
                    fixture["receipt"].write_text(json.dumps(value))
                elif case == "intent_hash":
                    fixture["intent"].write_text(json.dumps(fixture["files"][fixture["intent"]]) + ' ')
                elif case == "manifest_hash":
                    value = deepcopy(fixture["files"][fixture["manifest"]]);value["assets"][0]["bytes"] += 1
                    fixture["manifest"].write_text(json.dumps(value))
                elif case == "bytes":
                    fixture["image"].write_bytes(fixture["data"] + b'changed')
                elif case in {"stage", "owner"}:
                    value = deepcopy(fixture["files"][fixture["state"]])
                    if case == "stage":value["savedStages"] = [{"stageId": "stage_other"}]
                    else:value["sessionId"] = "other-owner-session"
                    fixture["state"].write_text(json.dumps(value))
                elif case == "frozen":
                    value = deepcopy(fixture["files"][fixture["frozen"]]);value.pop("binding")
                    fixture["frozen"].write_text(json.dumps(value))
                else:self.snapshot.source_roots = []
                result = self.export()
                self.assertFalse(result["complete"])
                with zipfile.ZipFile(result["zip"]["path"]) as archive:
                    self.assertEqual(json.loads(archive.read("manifest.json"))["recoveredAliases"], [])

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

    def inherited_audio_alias_fixture(self):
        """The producer validator is separately exercised by its own suite."""
        from content.textbook_catalog import canonical, digest
        stage, parent_stage, scene_id = "tbrev_role", "original_role", "role_scene"
        request, preview = "tbprev_" + "a" * 64, "d" * 64
        name, text = "cue-me", "请你指一指，谁用我称呼自己？"
        checksum = hashlib.sha256(self.media).hexdigest()
        action = {"id": "review_" + name, "type": "speech", "text": text, "audioId": request}
        html = "<script>player.src='/api/classroom-media/" + stage + "/audio/'+file+'.wav'</script>"
        room = {"stage": {"id": stage}, "scenes": [{"id": scene_id, "content": {"html": html}, "actions": [action]}]}
        frozen = {"operatorRevision": {"revisionId": "frozen-parent"}}
        receipt = {"requestId": request, "status": "succeeded", "audioSha256": checksum, "mimeType": "audio/wav"}
        entry = {"sceneId": scene_id, "actionId": action["id"], "text": text,
            "textSha256": hashlib.sha256(text.encode()).hexdigest(), "ttsRequestId": request,
            "audioSha256": checksum}
        segment = {"sceneId": scene_id, "actionId": action["id"], "ttsRequestId": request,
            "audioSha256": checksum, "textSha256": entry["textSha256"], "asrEntrySha256": digest(entry),
            "ttsReceiptSha256": digest(receipt), "asrRequestId": "saved-asr"}
        row = {"classroom_id": stage, "status": "preview_ready", "preview_key": preview,
            "input_json": canonical(frozen), "classroom_json": canonical(room), "classroom_sha256": digest(room),
            "result_json": canonical({"audioReceipts": [receipt]})}
        root = self.exporter.native_root / "data/classrooms" / stage
        folder, archive = root / "textbook-preview-audio", root / "textbook-preview-audio/operator-parent"
        archive.mkdir(parents=True)
        parent = {"preview": {"classroom_id": parent_stage}, "audit": {"segments": [entry]}, "receipts": [receipt]}
        candidate = {"classroom": room, "inheritedSegments": [segment]}
        context = {"archive": archive, "parent": parent, "candidate": candidate,
            "provenance": {"targetClassroomId": stage, "targetPreviewKey": preview}}
        plan = {"previewKey": preview}
        documents = {"parent.json": parent, "candidate.json": candidate, "input.json": frozen,
            "source.json": room, "source-plan.json": {}, "source-receipts.json": [receipt],
            "source-audit.json": parent["audit"], "asr/saved-asr.json": entry}
        for relative, value in documents.items():
            path = archive / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(canonical(value))
        audio = archive / "audio" / (request + ".wav")
        audio.parent.mkdir()
        audio.write_bytes(self.media)
        prepared = {"files": {p.relative_to(archive).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in archive.rglob("*") if p.is_file()}}
        (archive / "prepared.json").write_text(canonical(prepared))
        (archive / "provenance.json").write_text(canonical(context["provenance"]))
        (folder / "plan.json").write_text(canonical(plan))
        job_path = self.exporter.native_root / "data/formal-audio/jobs/tts" / (hashlib.sha256(request.encode()).hexdigest() + ".json")
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job = {"requestId": request, "classroomId": parent_stage, "state": "succeeded", "kind": "tts",
            "mimeType": "audio/wav", "audioSha256": checksum, "sizeBytes": len(self.media)}
        job_path.write_text(canonical(job))
        self.snapshot.source_roots = [root]
        self.snapshot.classroom = deepcopy(room)
        self.snapshot.documents["数据库/原始预览记录.json"] = row
        self.snapshot.documents["原始课堂.json"] = row["classroom_json"]
        self.store.config = CourseStorageConfig(mode="local")
        self.store.read.side_effect = lambda path, **kwargs: self.media if path.name == "teacher.mp3" else None
        ref = f"/api/classroom-media/{stage}/audio/{name}.wav"
        self.exporter.standard_asset_resolver = lambda *args, **kwargs: {
            "entries": [{"ref": ref, "kind": "audio", "status": "already_collected"}], "unresolved": []}
        match = re.fullmatch(r"/api/classroom-media/([A-Za-z0-9_-]+)/(audio|media)/([A-Za-z0-9_.-]+)", ref)
        return {"root": root, "archive": archive, "context": context, "row": row, "audio": audio,
            "ref": ref, "match": match, "job": job, "job_path": job_path}

    def test_inherited_audio_alias_is_private_and_preserves_original_document(self):
        fixture = self.inherited_audio_alias_fixture()
        original = deepcopy(self.snapshot.classroom)
        # The pure loader owns the complete producer contract; this fixture
        # isolates the archive adapter's independent scene/receipt/byte checks.
        with patch("services.textbook_operator_revision_service.load_inheritance", return_value=fixture["context"]):
            result = self.export()
        self.assertTrue(result["complete"], result["missingSources"])
        self.assertEqual(self.snapshot.classroom, original)
        self.assertFalse((fixture["root"] / "audio/cue-me.wav").exists())
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            alias = manifest["recoveredAliases"][0]
            self.assertEqual(alias["originalReference"], fixture["ref"])
            self.assertEqual(archive.read(alias["archivePath"]), self.media)
            by_path = {f["archivePath"]: f for f in manifest["files"]}
            for relative, checksum in alias["evidenceSha256"].items():
                self.assertEqual(by_path["原稿/" + relative]["sha256"], checksum)
            self.assertIn("/audio/'+file+'.wav", archive.read("classroom.json").decode())

    def test_inherited_audio_alias_rejects_changed_ambiguous_and_unowned_evidence(self):
        from content.textbook_catalog import canonical
        cases = ("wrong_stage", "wrong_scene", "draft", "duplicate_receipt", "duplicate_segment",
            "changed_frozen", "symlink", "hash", "size", "job_stage", "unknown_name", "invalid_lineage")
        for case in cases:
            with self.subTest(case=case):
                fixture = self.inherited_audio_alias_fixture()
                try:
                    if case == "wrong_stage":
                        self.snapshot.source_roots = []
                    elif case == "wrong_scene":
                        self.snapshot.classroom["scenes"][0]["id"] = "unrelated"
                    elif case == "draft":
                        fixture["row"]["status"] = "draft"
                    elif case == "duplicate_receipt":
                        fixture["context"]["parent"]["receipts"] *= 2
                    elif case == "duplicate_segment":
                        fixture["context"]["candidate"]["inheritedSegments"] *= 2
                    elif case == "changed_frozen":
                        (fixture["archive"] / "input.json").write_text('{"changed":true}')
                    elif case == "symlink":
                        fixture["audio"].unlink()
                        fixture["audio"].symlink_to(self.root / "unowned.wav")
                    elif case == "hash":
                        fixture["audio"].write_bytes(self.media + b"changed")
                    elif case in {"size", "job_stage"}:
                        job = dict(fixture["job"])
                        job["sizeBytes" if case == "size" else "classroomId"] = len(self.media) + 1 if case == "size" else "other"
                        fixture["job_path"].write_text(canonical(job))
                    match = fixture["match"]
                    if case == "unknown_name":
                        match = re.fullmatch(r"/api/classroom-media/([A-Za-z0-9_-]+)/(audio|media)/([A-Za-z0-9_.-]+)",
                            fixture["ref"].replace("cue-me.wav", "unknown.wav"))
                    with patch("services.textbook_operator_revision_service.load_inheritance",
                            side_effect=ValueError("invalid frozen lineage") if case == "invalid_lineage" else None,
                            return_value=fixture["context"]):
                        self.assertIsNone(self.exporter._retained_audio_alias(self.snapshot, match))
                finally:
                    import shutil
                    shutil.rmtree(fixture["root"])

    def test_inherited_audio_alias_requires_every_evidence_file_in_final_manifest(self):
        fixture = self.inherited_audio_alias_fixture()
        self.snapshot.private_source_files.append(fixture["job_path"])
        with patch("services.textbook_operator_revision_service.load_inheritance", return_value=fixture["context"]):
            result = self.export()
        self.assertFalse(result["complete"])
        self.assertEqual(result["generatedPublicFiles"], [])
        self.assertTrue(any(m["reason"] == "media_alias_evidence_not_archived" for m in result["missingSources"]))

    def test_payload_disk_reserve_rejects_before_writing_payload(self):
        from services import course_archive_exporter as module
        with patch.object(module.os, "statvfs", return_value=Mock(f_bavail=1024**3, f_frsize=1)):
            with self.assertRaisesRegex(CourseArchiveError, "archive_payload_space_insufficient"):
                self.export()
        self.assertFalse(list(self.staging.rglob("classroom.json")))
        self.assertFalse(list(self.staging.rglob("*.zip")))

    def test_zip_disk_reserve_rejects_before_creating_zip(self):
        from services import course_archive_exporter as module
        self.snapshot.documents.update({f"small-original-{i}.json": {"content": "x" * 2000} for i in range(40)})
        with patch.object(module.os, "statvfs", return_value=Mock(f_bavail=1024**3 + 32768, f_frsize=1)):
            with self.assertRaisesRegex(CourseArchiveError, "archive_zip_space_insufficient"):
                self.export()
        self.assertTrue(list(self.staging.rglob("manifest.json")))
        self.assertFalse(list(self.staging.rglob("*.zip")))

    def test_disk_reserve_allows_verified_complete_archive_with_sufficient_space(self):
        from services import course_archive_exporter as module
        with patch.object(module.os, "statvfs", return_value=Mock(f_bavail=4 * 1024**3, f_frsize=1)):
            result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertIsNone(archive.testzip())

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
