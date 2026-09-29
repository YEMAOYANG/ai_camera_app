"""Official source identity, non-generating sync, and existing-course preservation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from content.textbook_catalog import generation_brief, validate_manifest
from content.textbook_sync import directory_revision, normalized_tree
from core.errors import ApiError
from scripts.sync_textbook_directories import build_catalog
from tests import test_textbook_learning as fixtures

ROOT = Path(__file__).parents[1] / "content/textbooks"


def index():
    value = fixtures.sample()
    value.update(editionId="synthetic-sync-book", revisionId="index-1", units=[],
                 coverage={"status": "index_only", "note": "Synthetic index"})
    return value


def snapshot(base):
    return {"schemaVersion": "mira.smartedu-directory-snapshot.v1", "resourceId": base["source"]["resourceId"],
            "kind": "smartedu_ebook_mapping", "catalogId": "official-directory", "verifiedAt": "2026-09-28",
            "frontPageCount": 5, "pages": {"lesson-1": 6, "lesson-2": 5}, "tree": [
                {"id": "unit-1", "title": "Unit 1", "children": [
                    {"id": "section-a", "title": "Section A", "children": [
                        {"id": "lesson-1", "title": "Hello!", "children": []},
                        {"id": "lesson-2", "title": "Listen and say", "children": []}]}]}]}


class DirectorySyncTest(unittest.TestCase):
    def test_incomplete_official_preview_keeps_partial_coverage(self):
        base = index()
        source = snapshot(base)
        source["kind"] = "smartedu_preview_directory"
        source["catalogId"] = source["resourceId"]
        source["coverage"] = {"status": "partial", "note": "官方预览首张目录页缺字，仅收录可核实部分。"}
        value = directory_revision(base, source)
        self.assertEqual(value["coverage"], source["coverage"])
        self.assertTrue(value["units"])
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(build_catalog([base, value], [source], Path(directory))[0]["status"],
                             "preserved_existing_directory")
        source["coverage"] = {"status": "partial", "note": ""}
        with self.assertRaises(ValueError):
            directory_revision(base, source)

    def test_idempotent_and_no_authoring_or_course_preparation(self):
        base = index()
        source = snapshot(base)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            first = build_catalog([base], [source], out)
            second = build_catalog([base], [source], out)
            self.assertEqual(first[0]["status"], "created")
            self.assertEqual(second[0]["status"], "unchanged")
            self.assertEqual(first[0]["sha256"], second[0]["sha256"])
            value = json.loads(next(out.glob("*.json")).read_text())
            self.assertEqual(value["units"][0]["lessons"][0]["sectionTitle"], "Section A")
            self.assertEqual([n["printedPage"] for n in value["units"][0]["lessons"]], [1, None])
            self.assertEqual(value["units"][0]["lessons"][0]["brief"]["objectives"], [])
            with self.assertRaises(ApiError) as caught:
                generation_brief(value, "lesson-1")
            self.assertEqual(caught.exception.code, "textbook_review_required")
            # Existing full OR partial directories take precedence over a sync.
            preserved = build_catalog([base, value], [source], out)
            self.assertEqual(preserved[0]["status"], "preserved_existing_directory")

    def test_wrong_resource_duplicate_nodes_and_empty_approved_brief_rejected(self):
        base = index()
        source = snapshot(base)
        source["resourceId"] = "another-resource"
        with self.assertRaises(ValueError):
            directory_revision(base, source)
        source = snapshot(base)
        source["tree"].append(deepcopy(source["tree"][0]))
        with self.assertRaises(ValueError):
            directory_revision(base, source)
        value = directory_revision(base, snapshot(base))
        value["units"][0]["lessons"][0]["brief"]["status"] = "approved"
        with self.assertRaises(ApiError):
            validate_manifest(value)

    def test_hidden_source_nodes_are_not_promoted_to_lessons(self):
        self.assertEqual(normalized_tree([{"id": "hidden", "title": "Hidden", "custom_properties": {"hidden": True}}]), [])

    def test_real_manifests_follow_source_scope_and_include_low_grade_fltrp(self):
        from content.textbook_catalog import digest
        books = [validate_manifest(json.loads(p.read_text())) for p in (ROOT / "official-directories-v1").glob("*.json")]
        self.assertGreater(len(books), 80)
        for book in books:
            source = book["directorySource"]
            frozen = json.loads((ROOT / "sources/smartedu-directories-20260928" / (source["resourceId"] + ".json")).read_text())
            self.assertEqual(source["snapshotSha256"], digest(frozen))
            self.assertTrue(all(n["brief"]["status"] == "draft" for u in book["units"] for n in u["lessons"]))
        supplemental = [book for book in books if book["source"].get("kind") == "smartedu_sync_classroom"]
        self.assertTrue(all(b["subject"] == "english" for b in supplemental))
        fltrp = [book for book in supplemental if "陈琳" in book["editionLabel"]]
        self.assertEqual({(b["gradeCode"], b["volume"]) for b in fltrp},
                         {(f"primary_{grade}", term) for grade in range(1, 7) for term in ("upper", "lower")})
        first = next(b for b in fltrp if b["gradeCode"] == "primary_1" and b["volume"] == "upper")
        self.assertEqual([n["title"] for n in first["units"][0]["lessons"]], ["Unit 1 Hello!", "Unit 2 How are you?"])


class SelectedDirectoryTest(unittest.TestCase):
    setUp = fixtures.TextbookLearningTest.setUp
    choose = fixtures.TextbookLearningTest.choose
    assert_error = fixtures.TextbookLearningTest.assert_error
    prepare = fixtures.TextbookLearningTest.prepare
    bind = fixtures.TextbookLearningTest.bind

    def test_enriches_empty_selection_read_only_on_both_clients(self):
        base = index()
        self.service.import_manifest(base)
        self.choose(manifest=base)
        before = self.db.execute("SELECT * FROM learning_textbook_selections").fetchall()
        events = self.db.execute("SELECT * FROM learning_textbook_selection_events").fetchall()
        revision = directory_revision(base, snapshot(base))
        self.service.import_manifest(revision)
        self.assertFalse(self.service.import_manifest(revision)["created"])
        for result in (self.service.catalog(self.child), self.service.student_catalog("student-a", {})):
            book = next(b for b in result["books"] if b["selected"])
            self.assertEqual(book["revisionId"], revision["revisionId"])
            self.assertEqual(book["selectionRevision"], 1)
            self.assertEqual(book["lessonCount"], 2)
            self.assertEqual(book["learningStatus"]["availableLessonCount"], 0)
        contents = self.service.student_contents("student-a", base["editionId"], {"alignmentRevisionId": revision["revisionId"]})
        self.assertIsNone(contents["units"][0]["lessons"][0]["course"])
        self.assertEqual(contents["units"][0]["lessons"][0]["sectionTitle"], "Section A")
        self.assertEqual(before, self.db.execute("SELECT * FROM learning_textbook_selections").fetchall())
        self.assertEqual(events, self.db.execute("SELECT * FROM learning_textbook_selection_events").fetchall())
        self.assertEqual(self.service.student_catalog("student-b", {})["books"], [])
        self.assert_error("textbook_selection_required", lambda: self.service.student_contents("student-b", base["editionId"], {"alignmentRevisionId": revision["revisionId"]}))
        # CAS still uses the parent's original selection revision.
        self.assert_error("textbook_selection_changed", lambda: self.choose(manifest=revision, expected=0))
        self.choose(manifest=revision, expected=1)

    def test_existing_directory_and_published_course_remain_pinned(self):
        self.choose()
        course, _ = self.bind()
        self.visible.return_value = course
        before = self.db.execute("SELECT * FROM learning_textbook_course_builds").fetchall()
        self.assertIsNone(directory_revision(self.manifest, snapshot(self.manifest)))
        new = deepcopy(self.manifest)
        new["revisionId"] = "newer-directory"
        self.service.import_manifest(new)
        selected = next(b for b in self.service.catalog(self.child)["books"] if b["selected"])
        self.assertEqual(selected["revisionId"], self.manifest["revisionId"])
        self.assertEqual(selected["learningStatus"]["availableLessonCount"], 1)
        self.assertEqual(before, self.db.execute("SELECT * FROM learning_textbook_course_builds").fetchall())
