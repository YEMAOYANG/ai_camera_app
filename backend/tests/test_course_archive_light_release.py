"""Light provenance validation and offline textbook snapshot regression coverage."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import digest
from services.course_archive_exporter import CourseArchiveError, CourseArchiveExporter


def light_request():
    return {"coursewareLight": {
        "schemaVersion": "mira.courseware.light-release.v1",
        "source": {"stageId": "omclass_test-1.v2:source", "bodySha256": "a" * 64},
        "gates": {"G0": {"passed": True}},
        "confirmation": {"userQuote": "Publish this lesson", "confirmedAt": "2026-11-03",
                         "confirmedBy": "owner"},
        "evidence": {key: "b" * 64 for key in
                     ("notesSha256", "briefSha256", "receiptSha256", "verificationSha256")}}}


class LightReleaseValidationTest(unittest.TestCase):
    def test_valid_shape(self):
        frozen = light_request()
        original = deepcopy(frozen)
        CourseArchiveExporter._validate_light_release(frozen)
        self.assertEqual(frozen, original)

    def test_invalid_shapes(self):
        cases = []
        for value in (None, False, [], "light", {}):
            cases.append((("coursewareLight",), value, "schema"))
        cases.extend([
            (("coursewareLight", "schemaVersion"), "other", "schema"),
            (("coursewareLight", "extra"), True, "schema"),
            (("coursewareLight", "source"), [], "source"),
            (("coursewareLight", "source"), {}, "source"),
            (("coursewareLight", "source", "extra"), True, "source"),
            (("coursewareLight", "gates"), [], "gates"),
            (("coursewareLight", "gates"), None, "gates"),
            (("coursewareLight", "confirmation"), [], "confirmation"),
            (("coursewareLight", "confirmation"), {}, "confirmation"),
            (("coursewareLight", "confirmation", "confirmedBy"), "worker", "confirmation"),
            (("coursewareLight", "confirmation", "userQuote"), None, "confirmation"),
            (("coursewareLight", "confirmation", "confirmedAt"), 123, "confirmation"),
            (("coursewareLight", "confirmation", "extra"), True, "confirmation"),
            (("coursewareLight", "evidence"), [], "evidence"),
            (("coursewareLight", "evidence"), {}, "evidence"),
            (("coursewareLight", "evidence", "extra"), "a" * 64, "evidence"),
        ])
        for value in (None, 123, "", "../stage", "stage/name", "stage name", "stage\n"):
            cases.append((("coursewareLight", "source", "stageId"), value, "source"))
        for path, code in [(("coursewareLight", "source", "bodySha256"), "source")] + [
                (("coursewareLight", "evidence", key), "evidence") for key in
                light_request()["coursewareLight"]["evidence"]]:
            for value in (None, 123, "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 64 + "\n"):
                cases.append((path, value, code))
        for path, value, code in cases:
            with self.subTest(path=path, value=value):
                frozen = light_request()
                target = frozen
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaisesRegex(CourseArchiveError, "^light_release_" + code + "_invalid$"):
                    CourseArchiveExporter._validate_light_release(frozen)

    def test_preview_conflict(self):
        for preview in ("preview_test", "", None):
            with self.subTest(preview=preview):
                frozen = {**light_request(), "previewKey": preview}
                with self.assertRaisesRegex(CourseArchiveError, "^light_release_preview_conflict$"):
                    CourseArchiveExporter._validate_light_release(frozen)


class LightReleaseSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.exporter = CourseArchiveExporter(media_store=Mock())
        self.conn = Mock()
        self.key = "a" * 64
        self.classroom_id = "tbpub_" + self.key[:24]
        self.classroom = {"stage": {"id": self.classroom_id}, "scenes": [
            {"id": "page1", "type": "interactive", "content": {"html": "<button>Start</button>"}}]}
        self.course = {"id": "course", "version": "1", "title": "Test lesson"}
        self.manifest = {"editionId": "book"}
        self.media = [{"path": "/api/classroom-media/" + self.classroom_id + "/audio/teacher.mp3",
                       "sha256": "c" * 64, "byteSize": 10, "mimeType": "audio/mpeg"}]
        self.release = {"classroomId": self.classroom_id, "sha256": "b" * 64,
                        "classroom": self.classroom, "media": self.media}

    def snapshot(self, frozen):
        self.build = {"input_json": json.dumps(frozen), "review_json": json.dumps({"release": self.release})}
        with patch("services.course_archive_exporter.releases._validated_release",
                   return_value=(self.build, self.course, self.release, self.manifest)), \
                patch("services.course_archive_exporter.releases.release_metadata", return_value={}):
            return self.exporter._textbook_snapshot(self.conn, self.key)

    def test_light_snapshot_retains_identity_documents_and_media_without_sources(self):
        frozen = light_request()
        with patch("services.course_archive_exporter.course_glob") as glob, \
                patch.object(self.exporter, "_textbook_sources") as sources, \
                patch.object(self.exporter, "_add_native_sources") as native:
            snapshot = self.snapshot(frozen)
        self.assertEqual(snapshot.identity, {"courseId": "course", "courseVersion": "1",
            "contentKey": self.key, "classroomId": self.classroom_id, "releaseSha256": "b" * 64})
        self.assertEqual(snapshot.documents, {"数据库/课程记录.json": self.course,
            "数据库/教材构建记录.json": self.build, "教材目录.json": self.manifest,
            "冻结发布请求.json": self.build["input_json"], "审核与发布记录.json": self.build["review_json"],
            "发布记录.json": self.release})
        self.assertEqual(snapshot.classroom, self.classroom)
        self.assertEqual(snapshot.media, self.media)
        self.assertEqual(snapshot.source_roots, [])
        self.assertEqual(snapshot.missing_sources, [])
        self.conn.execute.assert_not_called()
        glob.assert_not_called()
        sources.assert_not_called()
        native.assert_not_called()

    def test_snapshot_rejects_invalid_light_and_preview_conflict(self):
        for frozen, code in (({"coursewareLight": None}, "schema_invalid"),
                             ({**light_request(), "previewKey": "preview_test"}, "preview_conflict")):
            with self.subTest(code=code), self.assertRaisesRegex(
                    CourseArchiveError, "^light_release_" + code + "$"):
                self.snapshot(frozen)
        self.conn.execute.assert_not_called()

    def test_preview_snapshot_keeps_original_and_collects_sources(self):
        original = {"stage": {"id": "omclass_source"}, "scenes": []}
        original_input = {"authoring": {"stageId": "omclass_source"}}
        preview = {"classroom_json": json.dumps(original), "classroom_sha256": digest(original),
                   "input_json": json.dumps(original_input), "classroom_id": "omclass_source"}
        self.conn.execute.return_value.fetchone.return_value = preview
        frozen = {"previewKey": "preview_test", "sourceSha256": digest(original)}
        with patch.object(self.exporter, "_textbook_sources") as sources, \
                patch.object(self.exporter, "_add_native_sources") as native:
            snapshot = self.snapshot(frozen)
        self.assertEqual(snapshot.missing_sources, [])
        self.assertEqual(snapshot.documents["原始课堂.json"], preview["classroom_json"])
        self.assertEqual(snapshot.documents["数据库/原始预览记录.json"], preview)
        sources.assert_called_once_with(snapshot, original_input, frozen)
        native.assert_called_once_with(snapshot, "omclass_source")
        self.conn.execute.assert_called_once_with(
            "SELECT * FROM learning_textbook_course_previews WHERE preview_key=?", ("preview_test",))

    def test_missing_preview_keeps_missing_source(self):
        self.conn.execute.return_value.fetchone.return_value = None
        snapshot = self.snapshot({"previewKey": "preview_test"})
        self.assertEqual(snapshot.missing_sources, [{"kind": "preview", "reason": "bound_preview_missing"}])

    def test_batch_snapshot_collects_only_matching_frozen_sources(self):
        task_id = "d" * 64
        frozen = {"taskId": task_id, "sourceInputSha256": "e" * 64}
        paths = [Path("/fixture/prepared/input.json"), Path("/fixture/compiled/input.json"),
                 Path("/fixture/unrelated/input.json"), Path("/fixture/symlink/input.json")]
        inputs = {path: json.dumps({"taskId": task_id, "inputSha256":
                  "f" * 64 if "unrelated" in str(path) else "e" * 64}).encode() for path in paths}
        with patch("services.course_archive_exporter.course_glob", return_value=paths) as glob, \
                patch("services.course_archive_exporter.course_bytes", side_effect=inputs.__getitem__) as read, \
                patch.object(Path, "is_symlink", autospec=True,
                             side_effect=lambda path: path == paths[-1]):
            snapshot = self.snapshot(frozen)
        glob.assert_called_once_with(self.exporter.root / "output", "**/" + task_id + "/input.json")
        self.assertEqual(read.call_count, 3)
        self.assertEqual(snapshot.source_roots, [path.parent for path in paths[:2]])
        self.assertEqual(snapshot.missing_sources, [])

    def test_batch_without_exact_source_keeps_missing_source(self):
        for frozen in ({}, {"taskId": "invalid"}, {"taskId": "d" * 64}):
            with self.subTest(frozen=frozen), patch(
                    "services.course_archive_exporter.course_glob", return_value=[]):
                snapshot = self.snapshot(frozen)
            self.assertEqual(snapshot.source_roots, [])
            self.assertEqual(snapshot.missing_sources, [{"kind": "authoring",
                "reason": "exact_batch_source_missing_or_ambiguous"}])


if __name__ == "__main__":
    unittest.main()
