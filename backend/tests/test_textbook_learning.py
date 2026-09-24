"""Isolated service, HTTP and persistence tests. No production database/provider."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from content.textbook_catalog import digest, generation_brief, validate_frozen_brief, validate_manifest
from core.errors import ApiError
from core.security import now_ms
from repositories.textbook_repository import TextbookRepository
from services.textbook_learning_service import TextbookLearningService
from services.textbook_course_policy import assert_textbook_course

ROOT = Path(__file__).parents[1]


def sample(*, reviewed=False):
    manifest = json.loads((ROOT / "content/textbooks/pep-chinese-g1-upper.preview.v1.json").read_text())
    if reviewed:
        manifest["rightsReview"] = {"status": "cleared", "basis": "Synthetic review for tests only"}
        manifest["units"][0]["lessons"][0]["brief"]["status"] = "approved"
    return manifest


class IsolatedDatabase:
    def __init__(self, migrations=("082_fixed_textbook_learning.sql",)):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys=ON")
        source = "\n".join((ROOT / "migrations" / name).read_text() for name in migrations)
        for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\)\s*ENGINE=[^;]+;", source, re.S):
            items, start, depth = [], 0, 0
            for i, char in enumerate(body):
                depth += (char == "(") - (char == ")")
                if char == "," and depth == 0:
                    items.append(body[start:i].strip()); start = i + 1
            items.append(body[start:].strip())
            # Preserve CHECK/FK/UNIQUE constraints; MySQL syntax is also checked
            # separately on a fresh, disposable MySQL instance.
            sql = ",".join(re.sub(r"UNIQUE KEY \w+", "UNIQUE", item) for item in items if not item.startswith("INDEX "))
            self.raw.execute(f"CREATE TABLE {name} ({sql})")
        self.raw.execute("CREATE TABLE children (id TEXT PRIMARY KEY, family_id TEXT, grade_code TEXT, grade_selection_revision INT)")
        self.raw.execute("CREATE TABLE learning_courses (id TEXT,version TEXT,grade_code TEXT,subject TEXT,content_json TEXT,status TEXT,quality_status TEXT,content_origin TEXT,retired_at INT,PRIMARY KEY(id,version))")

    def execute(self, sql, params=()):
        sql = re.sub(r"\s+FOR UPDATE\b", "", sql)
        sql = re.sub(r"ON DUPLICATE KEY UPDATE \w+=\w+", "ON CONFLICT DO NOTHING", sql)
        cursor = self.raw.execute(sql, tuple(params))
        return SimpleNamespace(fetchone=lambda: self.row(cursor.fetchone()), fetchall=lambda: [dict(r) for r in cursor.fetchall()], rowcount=cursor.rowcount)

    @staticmethod
    def row(value):
        return dict(value) if value is not None else None

    @contextmanager
    def transaction(self):
        try:
            yield self
            self.raw.commit()
        except Exception:
            self.raw.rollback()
            raise


class TextbookLearningTest(unittest.TestCase):
    def setUp(self):
        self.db = IsolatedDatabase()
        self.addCleanup(self.db.raw.close)
        self.repo = TextbookRepository(self.db)
        self.child = {"id": "child-a", "family_id": "family-a", "grade_code": "primary_1", "grade_selection_revision": 1}
        self.db.execute("INSERT INTO children VALUES (?,?,?,?)", tuple(self.child.values()))
        self.db.execute("INSERT INTO children VALUES (?,?,?,?)", ("child-b", "family-b", "primary_1", 1))
        self.db.raw.commit()
        self.term = patch("services.textbook_learning_service.school_term", return_value=(2026, "upper"))
        self.term.start(); self.addCleanup(self.term.stop)

        def student_auth(token):
            if token not in {"student-a", "student-b"}:
                raise ApiError("student_session_required", "请登录", 401)
            suffix = token[-1]
            return {"principal": {"family_id": f"family-{suffix}", "child_id": f"child-{suffix}"}}

        def parent_auth(token):
            if token not in {"parent-a", "parent-b", "viewer"}:
                raise ApiError("parent_session_required", "请登录", 401)
            return {"family": {"id": "family-b" if token == "parent-b" else "family-a"}, "user": {"id": token}}

        def capability(conn, context, action):
            self.assertEqual(action, "manage_child_profile")
            if context["user"]["id"] == "viewer":
                raise ApiError("forbidden", "无权限", 403)

        profile = SimpleNamespace(_auth_context=parent_auth, _assert_capability=capability, repository=SimpleNamespace(lock_family=Mock()))
        self.visible = Mock(return_value=None)
        student_learning = SimpleNamespace(repository=SimpleNamespace(get_student_visible_course=self.visible),
                                          learning_service=SimpleNamespace(assert_course_progression=assert_textbook_course))
        self.service = TextbookLearningService(self.repo, student_auth_service=SimpleNamespace(authenticate=student_auth), profile_service=profile, student_learning_service=student_learning)
        self.manifest = sample(reviewed=True)
        self.service.import_manifest(self.manifest)

    def assert_error(self, code, fn):
        with self.assertRaises(ApiError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def choose(self, *, manifest=None, expected=0, child_id="child-a", token="parent-a"):
        m = manifest or self.manifest
        return self.service.parent_select(token, child_id, {"editionId": m["editionId"], "alignmentRevisionId": m["revisionId"],
            "expectedSelectionRevision": expected, "schoolYearStartYear": 2026, "semester": "upper"})

    def prepare(self):
        return self.service.prepare({"editionId": self.manifest["editionId"], "alignmentRevisionId": self.manifest["revisionId"], "nodeId": "u1-l1"})

    def detail(self, token="student-a"):
        return self.service.student_contents(token, self.manifest["editionId"], {"alignmentRevisionId": self.manifest["revisionId"]})

    def bind(self):
        result = self.prepare()
        content = {"textbookBinding": result["generationInput"]["textbookBinding"], "title": "测试原创课"}
        self.db.execute("INSERT INTO learning_courses VALUES (?,?,?,?,?,?,?,?,?)", ("course-a", "1", "primary_1", "chinese", json.dumps(content), "published", "released", "openmaic_generated", None))
        self.db.raw.commit()
        request = {"contentKey": result["contentKey"], "courseId": "course-a", "courseVersion": "1", "courseContentSha256": digest(content),
                   "review": {"reviewer": "test-reviewer", "reviewedAt": now_ms(), "alignmentConfirmed": True, "originalExpressionConfirmed": True, "sourceUsageConfirmed": True, "basis": "Synthetic fixture, not a production review"}}
        with patch.object(self.service, "_assert_published_supply") as gate:
            self.assertTrue(self.service.bind_published(request)["created"])
            self.assertFalse(self.service.bind_published(request)["created"])
            self.assertEqual(gate.call_count, 2)
        course = self.db.execute("SELECT * FROM learning_courses").fetchone()
        return course, request

    def test_manifest_immutable_and_import_is_idempotent(self):
        self.assertFalse(self.service.import_manifest(self.manifest)["created"])
        changed = deepcopy(self.manifest); changed["title"] = "另一册"
        self.assert_error("textbook_revision_conflict", lambda: self.service.import_manifest(changed))
        row = self.repo.get_revision(self.db, self.manifest["editionId"], self.manifest["revisionId"])
        self.assertEqual(self.repo.manifest(row), self.manifest)
        changed["revisionId"] = "next-revision"; changed["gradeCode"] = "primary_2"
        self.assert_error("textbook_edition_conflict", lambda: self.service.import_manifest(changed))

    def test_catalog_collapses_revisions_but_preserves_parent_selection(self):
        newer = deepcopy(self.manifest)
        newer["revisionId"] = "next-revision"
        self.service.import_manifest(newer)
        books = self.service.student_catalog("student-a", {})["books"]
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["revisionId"], "next-revision")
        self.choose()
        pinned = self.service.student_catalog("student-a", {})["books"]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]["revisionId"], self.manifest["revisionId"])
        self.assertTrue(pinned[0]["selected"])

    def test_manifest_rejects_body_bad_source_dates_and_duplicate_sequence(self):
        variants = []
        for key, value in (("pdfContent", "原文"), ("subject", []), ("gradeCode", {})):
            m = deepcopy(self.manifest); m[key] = value; variants.append(m)
        for url in ("https://user:secret@basic.smartedu.cn/tchMaterial/detail", "https://basic.smartedu.cn:bad/tchMaterial/detail", "https://other.invalid/tchMaterial/detail"):
            m = deepcopy(self.manifest); m["source"]["url"] = url; variants.append(m)
        m = deepcopy(self.manifest); m["source"]["verifiedAt"] = "2026-02-30"; variants.append(m)
        m = deepcopy(self.manifest); m["units"][0]["lessons"][1]["sequence"] = 1; variants.append(m)
        for m in variants:
            self.assert_error("textbook_manifest_invalid", lambda: validate_manifest(m))

    def test_unreviewed_sample_cannot_generate(self):
        self.assert_error("textbook_review_required", lambda: generation_brief(sample(), "u1-l1"))
        self.assert_error("textbook_review_required", lambda: self.service.prepare({"editionId": self.manifest["editionId"], "alignmentRevisionId": self.manifest["revisionId"], "nodeId": "u1-l2"}))
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)

    def test_national_chinese_index_has_both_school_systems_without_fabricated_units(self):
        manifests = [validate_manifest(json.loads(p.read_text())) for p in sorted((ROOT / "content/textbooks").glob("*.json"))]
        self.assertEqual(len(manifests), 22)
        self.assertEqual({m["subject"] for m in manifests}, {"chinese"})
        for system, grades in (("six_year", range(1, 7)), ("five_four", range(1, 6))):
            self.assertEqual({(m["gradeCode"], m["volume"]) for m in manifests if m["schoolSystem"] == system},
                             {(f"primary_{i}", v) for i in grades for v in ("upper", "lower")})
        self.assertEqual(len({m["source"]["resourceId"] for m in manifests}), 22)
        indexes = [m for m in manifests if m["coverage"]["status"] == "index_only"]
        self.assertEqual(len(indexes), 21)
        self.assertTrue(all(m["units"] == [] and m["rightsReview"]["status"] == "pending" for m in indexes))
        self.service.import_catalog(indexes)
        self.assertTrue(all(not b["created"] for b in self.service.import_catalog(indexes)["books"]))
        books = self.service.student_catalog("student-a", {})["books"]
        self.assertEqual(len(books), 4)
        self.assertEqual((books[0]["schoolSystem"], books[0]["volume"]), ("six_year", "upper"))
        five_four = next(m for m in indexes if m["schoolSystem"] == "five_four" and m["gradeCode"] == "primary_1" and m["volume"] == "upper")
        self.choose(manifest=five_four)
        detail = self.service.student_contents("student-a", five_four["editionId"], {"alignmentRevisionId": five_four["revisionId"]})
        self.assertEqual(detail["units"], [])
        self.assertEqual(detail["book"]["lessonCount"], 0)
        self.assertTrue(detail["selected"])
        bad = deepcopy(five_four); bad["coverage"]["status"] = "complete"
        self.assert_error("textbook_manifest_invalid", lambda: validate_manifest(bad))
        bad["coverage"]["status"] = "index_only"; bad["gradeCode"] = "primary_6"
        self.assert_error("textbook_manifest_invalid", lambda: validate_manifest(bad))

    def test_catalog_import_rolls_back_all_books_when_one_revision_conflicts(self):
        new = deepcopy(self.manifest); new["editionId"] = "aaa-new-edition"
        conflict = deepcopy(self.manifest); conflict["title"] = "conflicting title"
        self.assert_error("textbook_revision_conflict", lambda: self.service.import_catalog([new, conflict]))
        self.assertIsNone(self.repo.get_revision(self.db, new["editionId"], new["revisionId"]))

    def test_prepare_reuses_fixed_identity_and_never_dispatches(self):
        first, second = self.prepare(), self.prepare()
        self.assertTrue(first["created"]); self.assertFalse(second["created"])
        self.assertEqual(first["contentKey"], second["contentKey"])
        self.assertFalse(first["providerDispatched"])
        self.assertFalse(first["generationInput"]["sourcePolicy"]["allowWebSearch"])
        with patch("content.textbook_catalog.authoring_prompt", return_value={"future": "prompt"}):
            self.assertEqual(validate_frozen_brief(self.manifest, first["generationInput"]), first["generationInput"])
            self.assert_error("textbook_build_conflict", self.prepare)

    def test_selection_permissions_scope_and_cas_history(self):
        self.assert_error("forbidden", lambda: self.choose(token="viewer"))
        self.assert_error("child_not_found", lambda: self.choose(child_id="child-b"))
        self.choose()
        self.assert_error("textbook_selection_changed", self.choose)
        newer = deepcopy(self.manifest); newer["revisionId"] = "review-2"
        self.service.import_manifest(newer)
        catalog = self.service.parent_catalog("parent-a", "child-a")
        self.assertEqual([b["selectionRevision"] for b in catalog["books"]], [1])
        self.choose(manifest=newer, expected=1)
        self.assertFalse(self.detail()["selected"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_selection_events").fetchone()["n"], 2)
        self.assertFalse(any(b["selected"] for b in self.service.student_catalog("student-b", {})["books"]))

    def test_grade_revision_resets_visible_selection_without_deleting_history(self):
        self.choose()
        self.db.execute("UPDATE children SET grade_selection_revision=2 WHERE id='child-a'")
        self.db.raw.commit()
        self.assertEqual(self.service.parent_catalog("parent-a", "child-a")["books"][0]["selectionRevision"], 0)
        self.assertEqual(self.choose()["selectionRevision"], 2)

    def test_reads_never_prepare_and_client_cannot_choose_child(self):
        self.choose()
        self.assert_error("textbook_query_invalid", lambda: self.service.student_catalog("student-a", {"childId": "child-b"}))
        for _ in range(3):
            self.service.student_catalog("student-a", {})
            detail = self.detail()
            self.assertEqual(detail["units"][0]["lessons"][0]["status"], "preparing")
            self.assertNotIn("reviewNote", json.dumps(detail))
            self.assertNotIn("confirmedBy", json.dumps(detail))
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)

    def test_published_binding_selection_and_media_are_all_required(self):
        course, request = self.bind()
        self.visible.return_value = course
        self.assertIsNone(self.detail()["units"][0]["lessons"][0]["course"])
        self.assert_error("textbook_selection_changed", lambda: assert_textbook_course(self.db, child=self.child, course=course))
        self.choose()
        self.assertEqual(self.detail()["units"][0]["lessons"][0]["course"]["courseId"], "course-a")
        gate = self.service.student_learning_service.learning_service
        with patch.object(gate, "assert_course_progression", side_effect=ApiError("learning_prerequisite_not_mastered", "先完成上一课", 409)):
            node = self.detail()["units"][0]["lessons"][0]
            self.assertEqual((node["status"], node["message"], node["course"]), ("locked", "先完成上一课", None))
        self.visible.return_value = None  # withdrawn asset/runtime publication
        self.assertIsNone(self.detail()["units"][0]["lessons"][0]["course"])
        with patch.object(self.service, "_assert_published_supply", side_effect=ApiError("textbook_course_unavailable", "media missing", 409)):
            self.assert_error("textbook_course_unavailable", lambda: self.service.bind_published(request))

    def test_changed_content_and_missing_review_cannot_bind(self):
        course, request = self.bind()
        bad = deepcopy(request); bad["review"]["originalExpressionConfirmed"] = False
        self.assert_error("textbook_review_required", lambda: self.service.bind_published(bad))
        course["content_json"] = json.dumps({"textbookBinding": {"editionId": "other"}})
        self.choose()
        self.assert_error("textbook_course_unavailable", lambda: assert_textbook_course(self.db, child=self.child, course=course))

    def test_http_read_routes_use_student_identity_and_parent_write_is_protected(self):
        from routes.api.v2.student_textbooks import student_textbooks_bp, parent_textbooks_bp
        app = Flask(__name__)
        app.register_blueprint(student_textbooks_bp, url_prefix="/api/v2/student/learning/textbooks")
        app.register_blueprint(parent_textbooks_bp, url_prefix="/api/children")
        app.extensions["mira_textbook_learning_service"] = self.service
        client = app.test_client()
        self.assertEqual(client.get("/api/v2/student/learning/textbooks").status_code, 401)
        response = client.get("/api/v2/student/learning/textbooks", headers={"Authorization": "Bearer student-a"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["books"][0]["publisher"], "人民教育出版社")
        self.assertEqual(client.get("/api/children/child-b/textbooks", headers={"Authorization": "Bearer parent-a"}).status_code, 404)
        self.assertEqual(client.get("/api/children/child-a/textbooks", headers={"Authorization": "Bearer student-a"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
