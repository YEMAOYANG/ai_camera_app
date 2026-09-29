"""Semester authority, published status and official low-grade source evidence.

All mutations use the isolated database fixture; no learner or provider is used.
"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask
from content.textbook_catalog import validate_manifest
from core.errors import ApiError
from services.textbook_course_policy import assert_textbook_course
from services.textbook_learning_service import school_term
from tests import test_textbook_learning as fixtures


class CalendarTest(unittest.TestCase):
    def test_academic_year_and_semester_boundaries(self):
        for day, expected in (("2026-01-31", (2025, "upper")),
                              ("2026-02-01", (2025, "lower")),
                              ("2026-08-31", (2025, "lower")),
                              ("2026-09-01", (2026, "upper"))):
            with self.subTest(day=day):
                self.assertEqual(school_term(datetime.fromisoformat(day)), expected)


class TextbookContextTest(unittest.TestCase):
    setUp = fixtures.TextbookLearningTest.setUp
    assert_error = fixtures.TextbookLearningTest.assert_error
    choose = fixtures.TextbookLearningTest.choose
    prepare = fixtures.TextbookLearningTest.prepare
    bind = fixtures.TextbookLearningTest.bind

    def body(self, semester="lower", revision=0):
        return {"schoolYearStartYear": 2026, "semester": semester,
                "expectedContextRevision": revision, "expectedGradeRevision": 1}

    def update(self, body=None, token="parent-a", child="child-a"):
        return self.service.parent_update_context(token, child, self.body() if body is None else body)

    def catalog(self):
        return self.service.student_catalog("student-a", {})

    def test_manual_term_is_shared_by_parent_student_and_direct_classroom_gate(self):
        self.choose()
        course, _ = self.bind()
        self.visible.return_value = course
        self.assertTrue(assert_textbook_course(self.db, child=self.child, course=course))
        self.update()
        parent = self.service.parent_catalog("parent-a", "child-a")
        student = self.catalog()
        for result in (parent, student):
            self.assertEqual((result["semester"], result["termSource"], result["suggestedSemester"]),
                             ("lower", "parent", "upper"))
        self.assertEqual(student["books"], [])
        self.assert_error("textbook_selection_changed", lambda: assert_textbook_course(self.db, child=self.child, course=course))
        self.assertEqual(len(self.repo.selections(self.db, self.child, 2026, "upper")), 1)
        self.update(self.body(None, revision=1))
        self.assertEqual(self.catalog()["semester"], "upper")
        self.assertEqual(len(self.catalog()["books"]), 1)
        self.assertTrue(assert_textbook_course(self.db, child=self.child, course=course))

    def test_lower_selection_is_preserved_when_returning_to_upper(self):
        lower = deepcopy(self.manifest)
        lower.update(editionId="synthetic-lower", volume="lower", units=[],
                     coverage={"status": "index_only", "note": "Synthetic fixture"})
        self.service.import_manifest(lower)
        self.choose()
        self.update()
        self.service.parent_select_many("parent-a", "child-a", {
            "schoolYearStartYear": 2026, "semester": "lower", "expectedContextRevision": 1,
            "selections": [{"editionId": lower["editionId"], "alignmentRevisionId": lower["revisionId"],
                            "expectedSelectionRevision": 0}]})
        self.assertEqual(self.catalog()["books"][0]["editionId"], lower["editionId"])
        self.update(self.body("upper", revision=1))
        self.assertEqual(self.catalog()["books"][0]["editionId"], self.manifest["editionId"])
        self.update(self.body("lower", revision=2))
        self.assertEqual(self.catalog()["books"][0]["editionId"], lower["editionId"])

    def test_grade_or_academic_year_change_expires_override_without_deleting_history(self):
        self.update()
        with patch("services.textbook_learning_service.school_term", return_value=(2027, "upper")):
            self.assertEqual((self.catalog()["semester"], self.catalog()["termSource"]), ("upper", "calendar"))
        self.db.execute("UPDATE children SET grade_selection_revision=2 WHERE id='child-a'")
        self.db.raw.commit()
        self.assertEqual((self.catalog()["semester"], self.catalog()["termSource"]), ("upper", "calendar"))
        self.assertEqual(self.repo.learning_context(self.db, self.child)["semester"], "lower")
        self.assert_error("textbook_context_changed", self.update)

    def test_context_write_rejects_viewer_foreign_child_stale_year_grade_and_boolean_revision(self):
        self.assert_error("forbidden", lambda: self.update(token="viewer"))
        self.assert_error("child_not_found", lambda: self.update(child="child-b"))
        for field, value, code in (("schoolYearStartYear", 2025, "textbook_context_changed"),
                                   ("expectedGradeRevision", 2, "textbook_context_changed"),
                                   ("expectedContextRevision", True, "textbook_context_invalid"),
                                   ("semester", "spring", "textbook_context_invalid")):
            body = self.body(); body[field] = value
            self.assert_error(code, lambda: self.update(body))
        self.assertEqual(self.repo.learning_context(self.db, self.child), {})
        self.update()
        self.assert_error("textbook_context_changed", self.update)
        self.assertEqual(self.repo.learning_context(self.db, self.child)["revision"], 1)

    def test_stale_picker_cannot_commit_after_term_changes_and_changes_back(self):
        self.update()
        self.update(self.body("upper", revision=1))
        self.assert_error("textbook_term_changed", lambda: self.service.parent_select_many("parent-a", "child-a", {
            "schoolYearStartYear": 2026, "semester": "upper", "expectedContextRevision": 0,
            "selections": [{"editionId": self.manifest["editionId"], "alignmentRevisionId": self.manifest["revisionId"],
                            "expectedSelectionRevision": 0}]}))
        self.assertEqual(self.repo.selections(self.db, self.child, 2026, "upper"), [])

    def test_context_http_auth_and_conflict(self):
        from routes.api.v2.student_textbooks import parent_textbooks_bp
        app = Flask(__name__)
        app.register_blueprint(parent_textbooks_bp, url_prefix="/api/children")
        app.extensions["mira_textbook_learning_service"] = self.service
        client = app.test_client()
        path = "/api/children/child-a/textbooks/context"
        self.assertEqual(client.put(path, json=self.body()).status_code, 401)
        headers = {"Authorization": "Bearer parent-a"}
        self.assertEqual(client.put(path, json=self.body(), headers=headers).status_code, 200)
        self.assertEqual(client.put(path, json=self.body(), headers=headers).status_code, 409)

    def test_status_counts_only_current_accessible_published_course_and_own_completion(self):
        self.choose()
        self.assertEqual(self.catalog()["books"][0]["learningStatus"], {
            "status": "unpublished", "availableLessonCount": 0, "completedLessonCount": 0})
        course, _ = self.bind()
        self.visible.return_value = course
        for row in (("other-family", "family-b", "child-a", "course-a", "1", "completed"),
                    ("other-child", "family-a", "child-b", "course-a", "1", "completed"),
                    ("old-version", "family-a", "child-a", "course-a", "0", "completed"),
                    ("unfinished", "family-a", "child-a", "course-a", "1", "active")):
            self.db.execute("INSERT INTO learning_sessions VALUES (?,?,?,?,?,?)", row)
        self.db.raw.commit()
        self.assertEqual(self.catalog()["books"][0]["learningStatus"], {
            "status": "ready", "availableLessonCount": 1, "completedLessonCount": 0})
        for key in ("own-1", "own-2"):
            self.db.execute("INSERT INTO learning_sessions VALUES (?,?,?,?,?,?)",
                            (key, "family-a", "child-a", "course-a", "1", "completed"))
        self.db.raw.commit()
        self.assertEqual(self.catalog()["books"][0]["learningStatus"]["completedLessonCount"], 1)
        self.visible.return_value = None
        self.assertEqual(self.catalog()["books"][0]["learningStatus"], {
            "status": "unpublished", "availableLessonCount": 0, "completedLessonCount": 0})

    def test_english_is_available_in_first_grade_but_never_auto_selected_or_published(self):
        paths = (Path(__file__).parents[1] / "content/textbooks/low-grade-english-v1").glob("*.json")
        self.service.import_catalog([json.loads(p.read_text()) for p in paths])
        parent = self.service.parent_catalog("parent-a", "child-a")
        self.assertIn({"subject": "english", "status": "selection_required"}, parent["subjects"])
        english = [book for book in parent["books"] if book["subject"] == "english"]
        self.assertTrue(english)
        self.assertTrue(all(not book["selected"] and book["lessonCount"] == 0 for book in english))
        self.assertEqual(self.catalog()["books"], [])


class OfficialLowGradeSourceTest(unittest.TestCase):
    def test_exact_official_records_do_not_accept_invented_labels_or_arbitrary_urls(self):
        root = Path(__file__).parents[1] / "content/textbooks/low-grade-english-v1"
        manifests = [validate_manifest(json.loads(p.read_text())) for p in root.glob("*.json")]
        self.assertEqual(len(manifests), 6)
        for manifest in manifests:
            self.assertEqual(manifest["coverage"]["status"], "index_only")
            self.assertEqual(manifest["rightsReview"]["status"], "pending")
            self.assertEqual(manifest["units"], [])
            for field, value in (("editionLabel", "未经核实的版本"), ("gradeCode", "primary_3")):
                forged = deepcopy(manifest); forged[field] = value
                with self.assertRaises(ApiError):
                    validate_manifest(forged)
            forged = deepcopy(manifest); forged["source"]["url"] = "https://www.moe.gov.cn/"
            with self.assertRaises(ApiError):
                validate_manifest(forged)
