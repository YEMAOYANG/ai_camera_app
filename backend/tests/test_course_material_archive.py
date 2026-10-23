"""Fixed producer materials join archives without absorbing mutable session data."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from PIL import Image

from services.course_archive_exporter import (
    ArchiveSnapshot, CourseArchiveError, CourseArchiveExporter, validate_material_bytes,
)
from scripts.course_storage_releases import canonical


def inventory(items):
    return {"schemaVersion": "mira.course-material-inventory.v1", "boundSessions": ["producer"],
        "materials": items, "dependencySha256": hashlib.sha256(canonical(items).encode()).hexdigest()}


class CourseMaterialArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.staging = self.root / "private"
        self.staging.mkdir()
        self.environment = patch.dict(os.environ, {"MIRA_TASK_TMPDIR": str(self.staging)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        picture = BytesIO()
        Image.new("RGB", (2, 3), "red").save(picture, "PNG")
        self.picture = picture.getvalue()
        self.source = "openmaic-runtime/.runtime/OpenMAIC/data/materials/owner-one/mat_source"
        self.path = self.root / self.source
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(self.picture)
        self.item = {"sourcePath": self.source, "mimeType": "image/png", "displayName": "课文插图.png",
            "originalName": "课文插图.png", "materialId": "mat_source", "kind": "source", "role": "owner",
            "sha256": hashlib.sha256(self.picture).hexdigest(), "byteSize": len(self.picture)}
        self.loader = Mock(side_effect=lambda request: inventory([self.item]))
        self.exporter = CourseArchiveExporter(project_root=self.root, media_store=Mock(),
            native_document_loader=lambda _: None, material_inventory_loader=self.loader,
            standard_asset_resolver=lambda *args, **kwargs: {"entries": [], "unresolved": []})
        self.snapshot = ArchiveSnapshot(identity={"courseId": "course-one", "courseVersion": "1",
            "classroomId": "stage-one", "contentKey": None, "releaseSha256": None},
            metadata={"title": "观察图片", "subjectName": "语文", "gradeLabel": "一年级"},
            classroom={"stage": {"id": "stage-one"}, "scenes": [{"id": "scene-one", "content": {}}]})

    def add(self, **kwargs):
        self.exporter._add_course_materials(self.snapshot, stage_id="stage-one", **kwargs)

    def export(self):
        return self.exporter.export_snapshot(self.snapshot, staging_root=self.staging / "exports")

    def test_extensionless_owner_original_keeps_exact_restore_path_and_human_name(self):
        self.add(session_id="producer")
        result = self.export()
        self.assertTrue(result["complete"])
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            entry = next(item for item in manifest["files"] if item.get("sourcePath") == self.source)
            self.assertEqual(entry["archivePath"], "原稿/" + self.source)
            self.assertEqual(entry["mimeType"], "image/png")
            self.assertEqual(entry["displayName"], "课文插图.png")
            self.assertEqual(entry["originalName"], "课文插图.png")
            self.assertEqual(archive.read(entry["archivePath"]), self.picture)
        self.assertEqual(self.path.read_bytes(), self.picture)
        self.assertEqual(self.loader.call_count, 2)

    def test_extensionless_files_are_not_globally_whitelisted(self):
        self.snapshot.source_files.append(self.path)
        result = self.export()
        self.assertFalse(result["complete"])
        self.assertIn("original_requires_safe_format_adapter", [item["reason"] for item in result["missingSources"]])

    def test_material_mime_and_database_integrity_must_match_real_bytes(self):
        for field, value in (("mimeType", "application/pdf"), ("sha256", "0" * 64), ("byteSize", len(self.picture) + 1)):
            with self.subTest(field=field):
                item = {**self.item, field: value}
                self.loader.side_effect = lambda request: inventory([item])
                snapshot = deepcopy(self.snapshot)
                self.exporter._add_course_materials(snapshot, stage_id="stage-one")
                with self.assertRaises(CourseArchiveError):
                    self.exporter.export_snapshot(snapshot, staging_root=self.staging / ("exports-" + field))

    def test_dependency_set_is_rechecked_before_archive_is_uploadable(self):
        self.add()
        self.loader.side_effect = lambda request: inventory([])
        with self.assertRaisesRegex(CourseArchiveError, "course_material_dependencies_changed"):
            self.export()

    def test_frozen_authoring_identity_is_forwarded_without_publishing_session_rows(self):
        self.exporter._textbook_sources(self.snapshot,
            {"authoring": {"sessionId": "producer", "stageId": "stage-source"}},
            {"textbookBinding": {"editionId": "book", "nodeId": "lesson"}})
        self.loader.assert_called_once_with({"sessionId": "producer", "stageId": "stage-source", "bindingKind": "frozen_authoring"})
        self.assertEqual(self.snapshot.source_files, [self.path])
        self.assertEqual(self.snapshot.documents, {})

    def test_native_saved_event_collects_materials_even_without_backend_workbench_job(self):
        with patch.object(self.exporter, "_workbench_jobs", return_value=[]):
            self.exporter._native_authoring_sources(self.snapshot, {"sessionId": "producer"}, source_digest="a" * 64)
        self.loader.assert_called_once_with({"sessionId": "producer", "stageId": "stage-one", "sourceDigest": "a" * 64,
                                            "bindingKind": "native_event"})
        self.assertEqual(self.snapshot.source_files, [self.path])

    def test_preflight_checks_material_format_and_does_not_reuse_a_different_mime_result(self):
        self.add()
        cache = {}
        with patch.object(self.exporter, "_published_snapshot", return_value=self.snapshot):
            result = self.exporter.preflight_course(None, course_id="course-one", course_version="1", file_cache=cache)
            self.assertTrue(result["readyForArchive"])
            self.snapshot.material_sources[self.source]["mimeType"] = "application/pdf"
            failed = self.exporter.preflight_course(None, course_id="course-one", course_version="1", file_cache=cache)
        self.assertFalse(failed["readyForArchive"])
        self.assertEqual(failed["failures"][0]["reason"], "course_material_pdf_invalid")

    def test_inventory_cannot_escape_material_root_or_forge_dependency_digest(self):
        for item in ({**self.item, "sourcePath": "output/unrelated-no-extension"},
                     {**self.item, "sourcePath": "openmaic-runtime/.runtime/OpenMAIC/data/materials/../private"}):
            self.loader.side_effect = lambda request: inventory([item])
            with self.assertRaises(CourseArchiveError):
                self.add()
            self.snapshot.material_bindings.clear()
        self.loader.side_effect = lambda request: {**inventory([self.item]), "dependencySha256": "0" * 64}
        with self.assertRaisesRegex(CourseArchiveError, "digest_mismatch"):
            self.add()

    def test_existing_remote_material_can_be_rearchived_with_local_original_absent(self):
        self.add()
        stat = self.path.stat()
        self.path.unlink()
        from services.course_file_store import course_bytes, course_exists, course_stat
        with patch("services.course_archive_exporter.course_bytes", side_effect=lambda p: self.picture if p == self.path else course_bytes(p)), \
             patch("services.course_archive_exporter.course_exists", side_effect=lambda p: True if p == self.path else course_exists(p)), \
             patch("services.course_archive_exporter.course_stat", side_effect=lambda p: stat if p == self.path else course_stat(p)):
            result = self.export()
        self.assertTrue(result["complete"])
        self.assertFalse(self.path.exists())
        with zipfile.ZipFile(result["zip"]["path"]) as archive:
            self.assertEqual(archive.read("原稿/" + self.source), self.picture)

    def test_text_and_unknown_binary_validation_do_not_execute_or_leak_credentials(self):
        self.assertEqual(validate_material_bytes("教材课文".encode(), "text/markdown"), "text/markdown")
        for raw, mime in ((b"\x89PNG\r\n\x1a\ninvalid", "image/png"), (b"arbitrary binary", "application/octet-stream"),
                          (b"\xff\x00", "text/plain"), (b'Bearer ' + b'a' * 24, "text/markdown")):
            with self.subTest(mime=mime), self.assertRaises(CourseArchiveError):
                validate_material_bytes(raw, mime)

    def test_material_text_uses_original_source_assignment_checks_including_csv_columns(self):
        for mime in ("text/plain", "text/markdown", "text/html", "text/csv"):
            for assignment in (b"password='fixture-value'", b"cookie='fixture-cookie'", b"child_id='fixture-child'"):
                with self.subTest(mime=mime, assignment=assignment), self.assertRaisesRegex(
                        CourseArchiveError, "credential_or_student_data_in_artifact"):
                    validate_material_bytes(assignment, mime)
        with self.assertRaisesRegex(CourseArchiveError, "credential_or_student_data_in_artifact"):
            validate_material_bytes(b"child_id,answer\nfixture-child,yes\n", "text/csv")
        self.assertEqual(validate_material_bytes("图片,分类\n苹果,水果\n".encode(), "text/csv"), "text/csv")
        with self.assertRaisesRegex(CourseArchiveError, "course_material_csv_invalid"):
            validate_material_bytes(b'name,value\n"unterminated', "text/csv")

    def test_aac_requires_complete_adts_frames_and_not_an_arbitrary_sync_prefix(self):
        # One AAC-LC silence frame retained from ffmpeg's ADTS encoder output.
        packet = bytes.fromhex("fff15040017ffc01182007")
        self.assertEqual(validate_material_bytes(packet + packet, "audio/aac"), "audio/aac")
        for invalid in (b"ADIF", packet[:-1], packet + packet[:-1], b"\xff\xf1" + b"\x00" * 12,
                        packet[:2] + bytes([packet[2] | 60]) + packet[3:]):
            with self.subTest(raw=invalid), self.assertRaisesRegex(CourseArchiveError, "course_material_audio_invalid"):
                validate_material_bytes(invalid, "audio/aac")

    def test_quicktime_requires_movie_and_media_atoms_with_valid_boundaries(self):
        def atom(kind, body):
            return (len(body) + 8).to_bytes(4, "big") + kind + body
        movie = atom(b"moov", atom(b"mvhd", b"\x00" * 8))
        media = atom(b"mdat", b"sample frame bytes")
        ftyp = atom(b"ftyp", b"qt  \x00\x00\x00\x00qt  ")
        self.assertEqual(validate_material_bytes(ftyp + movie + media, "video/quicktime"), "video/quicktime")
        self.assertEqual(validate_material_bytes(movie + media, "video/quicktime"), "video/quicktime")
        for invalid in (ftyp, ftyp + movie, ftyp + media, ftyp + movie + media[:-1],
                        atom(b"ftyp", b"isom\x00\x00\x00\x00isom") + movie + media,
                        b"arbitrary binary"):
            with self.subTest(raw=invalid), self.assertRaisesRegex(CourseArchiveError, "course_material_video_invalid"):
                validate_material_bytes(invalid, "video/quicktime")

    def test_wav_upload_alias_returns_the_existing_canonical_mime(self):
        import wave
        out = BytesIO()
        with wave.open(out, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 40)
        self.assertEqual(validate_material_bytes(out.getvalue(), "audio/x-wav"), "audio/wav")

    def test_private_authoring_control_is_excluded_before_registry_path_resolution(self):
        from repositories.course_storage_repository import CourseStorageRegistryError
        from services.course_file_store import course_exists
        root = self.root / "output/textbook-operator-lessons/book/lesson/teaching-1"
        private = root / "authoring-job/owner.cookies"
        private.parent.mkdir(parents=True)
        private.write_text("fixture-private-control")
        (root / "plan.json").write_text('{"lesson":"fixed teaching source"}')
        self.snapshot.source_roots.append(root)
        def resolve(path):
            if path == private:
                raise CourseStorageRegistryError("course_storage_path_forbidden")
            return course_exists(path)
        with patch("services.course_archive_exporter.course_exists", side_effect=resolve), \
             patch.object(self.exporter, "_published_snapshot", return_value=self.snapshot):
            result = self.exporter.preflight_course(None, course_id="course-one", course_version="1")
            archive = self.export()
        self.assertTrue(result["readyForArchive"])
        self.assertEqual(result["excludedFileCount"], 1)
        with zipfile.ZipFile(archive["zip"]["path"]) as bundle:
            manifest = json.loads(bundle.read("manifest.json"))
            self.assertNotIn("原稿/" + private.relative_to(self.root).as_posix(), bundle.namelist())
            self.assertIn({"sourceIdentity": private.relative_to(self.root).as_posix(),
                "reason": "credential_or_runtime_file_excluded"}, manifest["excludedFiles"])
        self.assertEqual(private.read_text(), "fixture-private-control")


if __name__ == "__main__":
    unittest.main()
