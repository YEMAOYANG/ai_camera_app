"""One-start and three-start FLTRP editions must never alias each other."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest, validate_manifest
from content.textbook_metadata import reviewed_edition_label, reviewed_editions
from core.errors import ApiError
from tests import test_textbook_learning as fixtures

ROOT = Path(__file__).parents[1] / "content/textbooks"


def additions():
    return [json.loads(p.read_text()) for p in sorted((ROOT / "fltrp-reviewed-v1").glob("*.json"))]


def original(edition, revision):
    for p in ROOT.rglob("*.json"):
        if p.parent.name == "fltrp-reviewed-v1":
            continue
        value = json.loads(p.read_text())
        if isinstance(value, dict) and value.get("editionId") == edition and value.get("revisionId") == revision:
            return value
    raise AssertionError("Reviewed base revision missing")


class FltrpAuditDataTest(unittest.TestCase):
    def test_metadata_changes_only_label_and_never_rewrites_frozen_content(self):
        reviewed = reviewed_editions()
        self.assertEqual(len(reviewed), 32)
        books = additions()
        self.assertEqual(len(books), 48)
        for book in books:
            validate_manifest(book)
            if book["revisionId"] != "20260928-metadata-1":
                continue
            record = reviewed[book["editionId"]]
            base = original(book["editionId"], record["baseRevisionId"])
            self.assertEqual(digest(base), record["baseManifestSha256"])
            expected = {**base, "revisionId": book["revisionId"], "editionLabel": record["editionLabel"]}
            self.assertEqual(book, expected)
            self.assertIn(f'{"一" if record["startingGrade"] == 1 else "三"}年级起点', book["editionLabel"])
            self.assertIn(record["editor"], book["editionLabel"])
            self.assertIn(str(record["curriculumStandard"]), book["editionLabel"])

    def test_display_correction_requires_exact_reviewed_identity_and_label(self):
        record = next(r for r in reviewed_editions().values() if r["editor"] == "孙有中")
        book = original(record["identity"]["editionId"], record["baseRevisionId"])
        self.assertEqual(reviewed_edition_label(book), record["editionLabel"])
        for key, value in (("gradeCode", "primary_1"), ("volume", "full"),
                           ("publisher", "另一出版社"), ("editionLabel", "未经核验的另一个系列")):
            changed = {**book, key: value}
            self.assertEqual(reviewed_edition_label(changed), changed["editionLabel"])
        changed = deepcopy(book)
        changed["source"]["resourceId"] = "another-resource"
        self.assertEqual(reviewed_edition_label(changed), changed["editionLabel"])

    def test_three_start_directory_cannot_be_renamed_as_one_start_or_new_standard(self):
        books = [b for b in additions() if b["units"] and "三年级起点，陈琳" in b["editionLabel"]]
        self.assertEqual(len(books), 8)
        self.assertEqual({(b["gradeCode"], b["volume"]) for b in books},
                         {(f"primary_{g}", v) for g in range(3, 7) for v in ("upper", "lower")})
        for book in books:
            frozen = json.loads((ROOT / "sources/smartedu-directories-20260928" / (book["source"]["resourceId"] + ".json")).read_text())
            self.assertEqual(book["directorySource"]["snapshotSha256"], digest(frozen))
            self.assertIn("三年级起点", frozen["evidence"]["officialTitle"])
            for old, new in (("三年级起点", "一年级起点"), ("2011", "2022"), ("陈琳", "孙有中")):
                bad = {**book, "editionLabel": book["editionLabel"].replace(old, new)}
                with self.assertRaises(ApiError):
                    validate_manifest(bad)


class FltrpAuditServiceTest(unittest.TestCase):
    setUp = fixtures.TextbookLearningTest.setUp

    def test_saved_choice_gets_clear_label_without_revision_or_history_mutation(self):
        record = next(r for r in reviewed_editions().values()
                      if r["editor"] == "孙有中" and r["identity"]["gradeCode"] == "primary_3"
                      and r["identity"]["volume"] == "upper")
        book = original(record["identity"]["editionId"], record["baseRevisionId"])
        self.service.import_manifest(book)
        self.db.execute("UPDATE children SET grade_code='primary_3' WHERE id='child-a'")
        self.db.raw.commit()
        self.service.parent_select("parent-a", "child-a", {
            "editionId": book["editionId"], "alignmentRevisionId": book["revisionId"],
            "expectedSelectionRevision": 0, "schoolYearStartYear": 2026, "semester": "upper"})
        before_choice = self.db.execute("SELECT * FROM learning_textbook_selections").fetchall()
        before_revision = self.repo.get_revision(self.db, book["editionId"], book["revisionId"])
        imported = self.service.import_catalog(additions())
        self.assertEqual(sum(r["created"] for r in imported["books"]), 48)
        self.assertFalse(imported["providerDispatched"])
        self.assertFalse(any(r["created"] for r in self.service.import_catalog(additions())["books"]))
        writes_before_read = self.db.raw.total_changes
        parent = self.service.parent_catalog("parent-a", "child-a")
        selected = next(b for b in parent["books"] if b["selected"])
        self.assertEqual(selected["revisionId"], book["revisionId"])
        self.assertEqual(selected["editionLabel"], record["editionLabel"])
        self.assertEqual(self.service.student_catalog("student-a", {})["books"], [selected])
        self.assertEqual(self.db.raw.total_changes, writes_before_read)
        self.assertEqual(self.db.execute("SELECT * FROM learning_textbook_selections").fetchall(), before_choice)
        self.assertEqual(self.repo.get_revision(self.db, book["editionId"], book["revisionId"]), before_revision)
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)
        self.assertEqual(len({b["editionId"] for b in parent["books"]}), len(parent["books"]))

    def test_one_start_and_three_start_are_distinct_for_both_semesters(self):
        self.service.import_catalog(additions())
        self.db.execute("UPDATE children SET grade_code='primary_3' WHERE id='child-a'")
        self.db.raw.commit()
        for term in ("upper", "lower"):
            with self.subTest(term=term), patch("services.textbook_learning_service.school_term", return_value=(2026, term)):
                books = self.service.parent_catalog("parent-a", "child-a")["books"]
                chen = [b for b in books if "陈琳" in b["editionLabel"] and b["volume"] == term]
                self.assertEqual(len(chen), 2)
                one = next(b for b in chen if "一年级起点" in b["editionLabel"])
                three = next(b for b in chen if "三年级起点" in b["editionLabel"])
                self.assertNotEqual(one["editionId"], three["editionId"])
                self.service.parent_select("parent-a", "child-a", {
                    "editionId": three["editionId"], "alignmentRevisionId": three["revisionId"],
                    "expectedSelectionRevision": 0, "schoolYearStartYear": 2026, "semester": term})
                contents = self.service.student_contents("student-a", three["editionId"], {"alignmentRevisionId": three["revisionId"]})
                titles = [n["title"] for u in contents["units"] for n in u["lessons"]]
                self.assertTrue(all(n["course"] is None for u in contents["units"] for n in u["lessons"]))
                if term == "upper":
                    self.assertTrue(any("Sam" in title for title in titles))
                    self.assertFalse(any("chopsticks" in title for title in titles))
