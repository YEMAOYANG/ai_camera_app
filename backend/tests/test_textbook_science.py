"""Four-subject selection, isolation and real science directory provenance."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from content.textbook_catalog import SUBJECTS, digest, validate_manifest
from tests import test_textbook_learning as fixtures


class ScienceSelectionTest(unittest.TestCase):
    setUp = fixtures.TextbookLearningTest.setUp
    assert_error = fixtures.TextbookLearningTest.assert_error

    def four_books(self):
        books = [self.manifest]
        for subject in SUBJECTS[1:]:
            value = deepcopy(self.manifest)
            value.update(editionId=f"synthetic-{subject}", subject=subject)
            value["rightsReview"]["status"] = "pending"
            value["units"][0]["lessons"][0]["brief"]["status"] = "draft"
            self.service.import_manifest(value)
            books.append(value)
        return books

    def selection(self, books):
        return {"schoolYearStartYear": 2026, "semester": "upper", "selections": [
            {"editionId": b["editionId"], "alignmentRevisionId": b["revisionId"],
             "expectedSelectionRevision": 0} for b in books]}

    def test_parent_confirms_four_subjects_student_opens_science_without_generation(self):
        books = self.four_books()
        result = self.service.parent_select_many("parent-a", "child-a", self.selection(books))
        self.assertEqual([s["subject"] for s in result["selections"]], list(SUBJECTS))
        for catalog in (self.service.parent_catalog("parent-a", "child-a"),
                        self.service.student_catalog("student-a", {})):
            self.assertEqual({b["subject"] for b in catalog["books"] if b["selected"]}, set(SUBJECTS))
            self.assertTrue(all(s["status"] == "confirmed" for s in catalog["subjects"]))
        science = books[-1]
        contents = self.service.student_contents("student-a", science["editionId"],
            {"alignmentRevisionId": science["revisionId"]})
        self.assertTrue(contents["units"])
        self.assertTrue(all(n["course"] is None for u in contents["units"] for n in u["lessons"]))
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)
        self.assert_error("textbook_selection_required", lambda: self.service.student_contents("student-b", science["editionId"],
            {"alignmentRevisionId": science["revisionId"]}))

    def test_stale_science_selection_rolls_back_all_four_choices(self):
        body = self.selection(self.four_books())
        body["selections"][-1]["expectedSelectionRevision"] = 1
        self.assert_error("textbook_selection_changed", lambda: self.service.parent_select_many("parent-a", "child-a", body))
        self.assertEqual(self.db.execute("SELECT * FROM learning_textbook_selections").fetchall(), [])
        self.assertEqual(self.db.execute("SELECT * FROM learning_textbook_selection_events").fetchall(), [])

    def test_duplicate_subject_is_rejected_before_any_choice_is_written(self):
        books = self.four_books()
        body = self.selection([books[0], books[1], books[3], books[3]])
        self.assert_error("textbook_selection_invalid", lambda: self.service.parent_select_many("parent-a", "child-a", body))
        self.assertEqual(self.db.execute("SELECT * FROM learning_textbook_selections").fetchall(), [])


class ScienceSourcesTest(unittest.TestCase):
    def test_official_science_directories_keep_frozen_evidence_and_block_generation(self):
        root = Path(__file__).parents[1] / "content/textbooks"
        books = [validate_manifest(json.loads(p.read_text())) for p in (root / "science-v1").glob("*.json")]
        self.assertTrue(books)
        self.assertEqual({b["gradeCode"] for b in books}, {f"primary_{i}" for i in range(1, 7)})
        for book in books:
            self.assertEqual(book["subject"], "science")
            self.assertEqual(book["rightsReview"]["status"], "pending")
            if not book["units"]:
                continue
            source = book["directorySource"]
            snapshot = json.loads((root / "sources/smartedu-science-directories-20260928" / (source["resourceId"] + ".json")).read_text())
            self.assertEqual(source["snapshotSha256"], digest(snapshot))
            self.assertTrue(all(n["brief"]["status"] == "draft" for u in book["units"] for n in u["lessons"]))
