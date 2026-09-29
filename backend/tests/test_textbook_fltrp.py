"""Reviewed FLTRP supplements retain official identity and reach both clients."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest, generation_brief, validate_manifest
from core.errors import ApiError
from scripts.sync_textbook_directories import build_catalog
from tests import test_textbook_learning as fixtures

ROOT = Path(__file__).parents[1] / "content/textbooks"


def supplements():
    records = json.loads((ROOT / "sources/smartedu-sync-fltrp-primary-20260928.json").read_text())["records"]
    ids = {r["editionId"] for r in records}
    return [json.loads(path.read_text()) for folder in ("sync-english-v1", "official-directories-v1")
            for path in (ROOT / folder).glob("*.json") if any(path.name.startswith(eid + ".") for eid in ids)]


class FltrpSourceTest(unittest.TestCase):
    def test_official_directories_win_and_repeated_sync_preserves_them(self):
        books = [validate_manifest(b) for b in supplements()]
        self.assertEqual(len(books), 16)
        directories = [b for b in books if b["units"]]
        self.assertEqual({(b["gradeCode"], b["volume"]) for b in directories},
                         {(f"primary_{g}", v) for g in range(3, 7) for v in ("upper", "lower")})
        self.assertEqual(sum(len(u["lessons"]) for b in directories for u in b["units"]), 204)
        snapshots = []
        for book in directories:
            source = book["directorySource"]
            frozen = json.loads((ROOT / "sources/smartedu-directories-20260928" / (source["resourceId"] + ".json")).read_text())
            snapshots.append(frozen)
            self.assertEqual(source["snapshotSha256"], digest(frozen))
            self.assertEqual(source["catalogId"], book["source"]["resourceId"])
            self.assertEqual(book["source"]["kind"], "smartedu_sync_classroom")
            self.assertEqual([u["unitId"] for u in book["units"]], [u["id"] for u in frozen["tree"]])
            self.assertTrue(all(n["brief"]["status"] == "draft" and n["printedPage"] is None
                                and n["pdfPage"] is None for u in book["units"] for n in u["lessons"]))
            with self.assertRaises(ApiError) as caught:
                generation_brief(book, book["units"][0]["lessons"][0]["nodeId"])
            self.assertEqual(caught.exception.code, "textbook_review_required")
        with tempfile.TemporaryDirectory() as folder:
            report = build_catalog(books, snapshots, Path(folder))
            self.assertTrue(all(r["status"] == "preserved_existing_directory" for r in report))
            self.assertEqual(list(Path(folder).iterdir()), [])
        review = json.loads((ROOT / "sources/fltrp-primary-source-reconciliation-20260928.json").read_text())
        self.assertEqual((review["newBooks"], review["preservedBooks"], review["githubOnlyBooks"]), (8, 4, 0))
        added = [r for r in review["records"] if r["decision"] == "add_official_directory"]
        self.assertEqual({r["officialResourceId"] for r in added}, {b["source"]["resourceId"] for b in directories})
        self.assertTrue(all(r["comparison"]["matchedCoreLessons"] == 20 for r in added))

    def test_no_unreviewed_grade_editor_or_directory_can_reuse_a_record(self):
        book = next(b for b in supplements() if b["gradeCode"] == "primary_3" and b["units"])
        for key, value in (("gradeCode", "primary_4"), ("subject", "math"),
                           ("editionLabel", "外研社版（三年级起点，孙有中主编）")):
            invalid = deepcopy(book)
            invalid[key] = value
            with self.subTest(key=key), self.assertRaises(ApiError):
                validate_manifest(invalid)
        invalid = deepcopy(book)
        invalid["directorySource"]["catalogId"] = "unrelated-official-tree"
        invalid["directorySource"]["url"] = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/unrelated-official-tree.json"
        with self.assertRaises(ApiError):
            validate_manifest(invalid)


class FltrpClientTest(unittest.TestCase):
    setUp = fixtures.TextbookLearningTest.setUp

    def test_grade_three_parent_selection_and_student_contents_match_each_term(self):
        books = supplements()
        first = self.service.import_catalog(books)
        self.assertEqual(sum(b["created"] for b in first["books"]), 16)
        self.assertFalse(first["providerDispatched"])
        self.assertFalse(any(b["created"] for b in self.service.import_catalog(books)["books"]))
        self.db.execute("UPDATE children SET grade_code='primary_3' WHERE id='child-a'")
        self.db.raw.commit()
        # The existing official edition remains a separate selectable book.
        other = json.loads((ROOT / "math-english-v1/fltrp-sunyouzhong-english-g3-upper.index.v1.json").read_text())
        self.service.import_manifest(other)
        for term, first_title in (("upper", "Unit 1 Do you use chopsticks in the UK?"),
                                  ("lower", "Unit 1 She’ s very nice.")):
            with self.subTest(term=term), patch("services.textbook_learning_service.school_term", return_value=(2026, term)):
                parent = self.service.parent_catalog("parent-a", "child-a")
                offered = [b for b in parent["books"] if "陈琳" in b["editionLabel"]]
                self.assertEqual(len(offered), 2)  # One book per term, not index + directory duplicates.
                self.assertTrue(all(b["lessonCount"] == 24 for b in offered))
                self.assertTrue(any(b["editionId"] == other["editionId"] for b in parent["books"]))
                self.assertEqual(self.service.student_catalog("student-a", {})["books"], [])
                book = next(b for b in offered if b["volume"] == term)
                self.service.parent_select("parent-a", "child-a", {
                    "editionId": book["editionId"], "alignmentRevisionId": book["revisionId"],
                    "expectedSelectionRevision": 0, "schoolYearStartYear": 2026, "semester": term})
                parent_selected = [b for b in self.service.parent_catalog("parent-a", "child-a")["books"] if b["selected"]]
                student = self.service.student_catalog("student-a", {})["books"]
                self.assertEqual(student, parent_selected)
                self.assertEqual(student[0]["learningStatus"]["status"], "unpublished")
                before = self.db.raw.total_changes
                contents = self.service.student_contents("student-a", book["editionId"], {"alignmentRevisionId": book["revisionId"]})
                self.assertEqual(contents["units"][0]["lessons"][0]["title"], first_title)
                self.assertTrue(all(n["course"] is None for u in contents["units"] for n in u["lessons"]))
                self.assertEqual(self.db.raw.total_changes, before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)
