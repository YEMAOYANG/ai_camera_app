"""Four-subject budget admission on isolated SQL; no provider or runtime calls.

The synthetic release reuses the existing 天地人 fixture only to exercise signed
authority and accounting. It does not validate science content or publish it.
"""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from content.learning_budget_policy import (COURSE_BUDGET_SUBJECTS, LearningBudgetPolicy,
                                           PURPOSES, UNITS, canonical, digest)
from core.errors import ApiError
from core.security import now_ms
from repositories.textbook_repository import TextbookRepository
from services.learning_budget_service import LearningBudgetService
from services.learning_paid_authority import scope_digest
from services.textbook_classroom_service import TextbookClassroomService
from tests.test_learning_budget import IsolatedDatabase, test_policy
from tests.test_homework_paid_budget import HomeworkBudgetDatabase
from tests.test_textbook_publication import fixture as release_fixture


class ScienceLearningBudgetTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = IsolatedDatabase(Path(directory.name) / "budget.db")
        self.now = now_ms()
        self.raw = test_policy()
        self.raw["authorizationTemplates"] = {
            purpose: {"maxUnits": dict.fromkeys(UNITS, 10000),
                      "priceKeys": ["fake-text-v1"], "ttlMs": 60000}
            for purpose in PURPOSES
        }
        self.budget = self.service()

    def service(self, raw=None):
        return LearningBudgetService(self.db, policy=LearningBudgetPolicy(raw or self.raw),
                                     clock=lambda: self.now)

    @staticmethod
    def scope(purpose="required_teaching", subject="science"):
        production = purpose == "production"
        return {"purpose": purpose, "gradeCode": "primary_1", "subject": subject,
                "courseId": "course", "courseVersion": "1", "approvalReference": "reviewed-release",
                "userId": None if production else "child",
                "sessionId": None if production else "session",
                "productionJobId": "job" if production else None}

    def rows(self):
        with self.db.transaction() as conn:
            return {table: conn.execute("SELECT * FROM " + table + " ORDER BY id").fetchall()
                    for table in ("learning_budget_authorizations", "learning_budget_reservations",
                                  "learning_budget_events")}

    def assert_code(self, code, call):
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.code, "learning_budget_" + code)

    def reserve(self, identity, dispatch="science-turn", price="fake-text-v1"):
        return self.budget.reserve(authorization_id=identity, dispatch_id=dispatch,
            request_sha256=digest(dispatch), price_key=price,
            max_units={"calls": 1, "input_tokens": 10, "output_tokens": 10})

    def test_all_four_subjects_validate_for_all_three_course_purposes(self):
        self.assertIsInstance(COURSE_BUDGET_SUBJECTS, frozenset)
        self.assertEqual(COURSE_BUDGET_SUBJECTS, {"chinese", "math", "english", "science"})
        for purpose in PURPOSES:
            for subject in COURSE_BUDGET_SUBJECTS:
                with self.subTest(purpose=purpose, subject=subject):
                    scope = self.scope(purpose, subject)
                    self.assertEqual(self.budget.validate_scope(scope), scope)
        self.assertTrue(all(not rows for rows in self.rows().values()))

    def test_other_unknown_and_mixed_student_job_scopes_never_write(self):
        for purpose in PURPOSES:
            for subject in ("other", "physics", "", "science "):
                with self.subTest(purpose=purpose, subject=subject):
                    self.assert_code("invalid_scope", lambda: self.budget.issue_course_authorization(
                        authorization_id=digest([purpose, subject]), scope=self.scope(purpose, subject)))
        for scope, code in (({**self.scope("production"), "userId": "child"}, "production_scope_has_student"),
                            ({**self.scope(), "productionJobId": "job"}, "teaching_scope_has_production"),
                            ({**self.scope(), "gradeCode": "primary_7"}, "invalid_scope"),
                            ({**self.scope(), "clientPrice": "fake-text-v1"}, "invalid_scope")):
            self.assert_code(code, lambda: self.budget.issue_course_authorization(
                authorization_id=digest(scope), scope=scope))
        self.assertTrue(all(not rows for rows in self.rows().values()))

    def test_homework_keeps_science_and_other_without_course_or_session(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = HomeworkBudgetDatabase(Path(directory.name) / "homework.db")
        raw = deepcopy(self.raw)
        maximum = dict.fromkeys(UNITS, 1000000)
        raw["limits"]["purposes"]["homework"] = {"day": maximum, "month": maximum}
        raw["authorizationTemplates"]["homework"] = {
            "maxUnits": dict.fromkeys(UNITS, 10000), "priceKeys": ["fake-text-v1"], "ttlMs": 60000}
        service = LearningBudgetService(database, policy=LearningBudgetPolicy(raw), clock=lambda: self.now)
        for subject in ("science", "other"):
            scope = {"purpose": "homework", "gradeCode": "primary_1", "subject": subject,
                     "familyId": "family", "childId": "child", "submissionId": "submission",
                     "itemId": "item", "itemRevision": 1, "approvalReference": "consent"}
            self.assertEqual(self.budget.validate_scope(scope), scope)
            self.assert_code("invalid_scope", lambda: self.budget.validate_scope(
                {**scope, "courseId": "forged"}))
            with database.transaction() as conn:
                conn.execute("UPDATE homework_submissions SET subject=?", (subject,))
            identity = service.issue_homework_authorization(
                submission_id="hw_test", item_id="hwi_test", revision=1)["authorizationId"]
            row = service.reserve(authorization_id=identity, dispatch_id=subject,
                request_sha256=digest(subject), price_key="fake-text-v1",
                max_units={"calls": 1, "input_tokens": 10, "output_tokens": 10})
            self.assertTrue(service.dispatch(authorization_id=identity, reservation_id=row["reservationId"],
                request_sha256=row["requestSha256"])["dispatchAllowed"])

    def test_production_window_accepts_science_but_keeps_exact_identity_guards(self):
        scope = self.scope("production")
        raw = deepcopy(self.raw)
        raw["productionAuthorizationWindow"] = {"startsAt": self.now, "expiresAt": self.now + 1000,
                                                 "scopes": [scope]}
        self.assertEqual(LearningBudgetPolicy(raw).raw, raw)
        self.assertEqual(LearningBudgetPolicy(self.raw).sha256, digest(self.raw))
        for changes in ({"subject": "other"}, {"subject": "physics"}, {"gradeCode": "primary_7"},
                        {"purpose": "required_teaching"}, {"userId": "child"}, {"sessionId": "session"},
                        {"productionJobId": ""}):
            invalid = deepcopy(raw)
            invalid["productionAuthorizationWindow"]["scopes"] = [{**scope, **changes}]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                LearningBudgetPolicy(invalid)

    def test_science_real_sql_authorizes_reserves_and_dispatches_each_course_purpose(self):
        for purpose in PURPOSES:
            scope = self.scope(purpose)
            identity = scope_digest(scope)
            binding = self.budget.issue_course_authorization(authorization_id=identity, scope=scope)
            self.assertEqual(binding["authorizationId"], identity)
            row = self.reserve(identity, purpose)
            self.assertFalse(row["dispatchAllowed"])
            self.assertTrue(self.budget.dispatch(authorization_id=identity,
                reservation_id=row["reservationId"], request_sha256=row["requestSha256"])["dispatchAllowed"])
        rows = self.rows()
        self.assertEqual(len(rows["learning_budget_authorizations"]), 3)
        self.assertEqual([row["state"] for row in rows["learning_budget_reservations"]], ["dispatched"] * 3)

    def test_science_does_not_bypass_templates_windows_frozen_scope_or_prices(self):
        scope = self.scope()
        identity = scope_digest(scope)
        for field, value in (("enabled", False), ("authorizationTemplates", {**self.raw["authorizationTemplates"],
                                                                         "required_teaching": None})):
            raw = {**self.raw, field: value}
            self.assertIsNone(self.service(raw).issue_course_authorization(authorization_id=identity, scope=scope))
        self.assertTrue(all(not rows for rows in self.rows().values()))
        self.budget.issue_course_authorization(authorization_id=identity, scope=scope)
        original = self.rows()
        for field, value in (("subject", "math"), ("courseId", "forged"), ("courseVersion", "2"),
                             ("userId", "other-child"), ("sessionId", "other-session"),
                             ("approvalReference", "other-release")):
            self.assert_code("authorization_conflict", lambda: self.budget.issue_course_authorization(
                authorization_id=identity, scope={**scope, field: value}))
        self.assert_code("authorization_required", lambda: self.reserve(digest("absent")))
        self.assert_code("price_not_authorized", lambda: self.reserve(identity, price="forged-price"))
        raw = deepcopy(self.raw)
        raw["authorizationWindow"] = {"startsAt": self.now, "expiresAt": self.now + 1000,
                                      "scopes": [{**scope, "courseVersion": "different"}]}
        self.assert_code("scope_not_approved", lambda: self.service(raw).issue_course_authorization(
            authorization_id=identity, scope=scope))
        raw["authorizationWindow"]["scopes"] = [scope]
        self.now += 1001
        self.assert_code("authorization_window_closed", lambda: self.service(raw).issue_course_authorization(
            authorization_id=identity, scope=scope))
        self.assertEqual(self.rows(), original)

    def textbook_service(self):
        """Use real release validation/repositories/signature and the real budget ledger.

        The fixture authentication adapter supplies a stored synthetic login; this
        does not exercise SMS/device login or production MySQL locking.
        """
        manifest, build, release = release_fixture()
        manifest["subject"] = "science"
        frozen = json.loads(build["input_json"])
        frozen.pop("contentKey")
        frozen["subject"] = "science"
        frozen["textbookBinding"]["alignmentManifestSha256"] = digest(manifest)
        key = digest(frozen)
        frozen["contentKey"] = key
        release.update(contentKey=key, classroomId="tbpub_" + key[:24])
        release["classroom"]["id"] = release["classroomId"]
        release["classroom"]["stage"]["id"] = release["classroomId"]
        release["classroomSha256"] = digest(release["classroom"])
        release.pop("sha256")
        release["sha256"] = digest(release)
        review = json.loads(build["review_json"])
        review["release"] = release
        build.update(content_key=key, input_json=canonical(frozen), review_json=canonical(review),
                     edition_id="book", revision_id="directory")
        with self.db.transaction() as conn:
            conn.execute("CREATE TABLE children (id TEXT, family_id TEXT, grade_code TEXT, grade_selection_revision INTEGER)")
            conn.execute("INSERT INTO children VALUES ('child','family','primary_1',1)")
            conn.execute("CREATE TABLE app_settings (family_id TEXT, setting_key TEXT, value TEXT)")
            conn.execute("CREATE TABLE learning_textbook_revisions (edition_id TEXT, revision_id TEXT, retired_at INTEGER, manifest_json TEXT, manifest_sha256 TEXT)")
            conn.execute("INSERT INTO learning_textbook_revisions VALUES ('book','directory',NULL,?,?)", (canonical(manifest), digest(manifest)))
            conn.execute("CREATE TABLE learning_textbook_selections (family_id TEXT, child_id TEXT, school_year_start INTEGER, semester TEXT, grade_revision INTEGER, subject TEXT, edition_id TEXT, revision_id TEXT, current_node_id TEXT)")
            from services.textbook_learning_service import school_term
            year, semester = school_term()
            conn.execute("INSERT INTO learning_textbook_selections VALUES ('family','child',?,?,1,'science','book','directory',NULL)", (year, semester))
            conn.execute("CREATE TABLE learning_textbook_course_builds (" + ",".join(name + " TEXT" for name in build) + ")")
            conn.execute("INSERT INTO learning_textbook_course_builds VALUES (" + ",".join("?" for _ in build) + ")", tuple(build.values()))
            conn.execute("CREATE TABLE learning_courses (id TEXT, version TEXT, status TEXT, quality_status TEXT, retired_at INTEGER, content_json TEXT)")
            conn.execute("INSERT INTO learning_courses VALUES ('course','1','published','released',NULL,?)", (canonical({"title": "天地人"}),))
            conn.execute("CREATE TABLE learning_sessions (id TEXT, family_id TEXT, child_id TEXT, course_id TEXT, course_version TEXT)")
            conn.execute("INSERT INTO learning_sessions VALUES ('session','family','child','course','1')")
            conn.execute("CREATE TABLE fixture_student_logins (id TEXT, family_id TEXT, child_id TEXT, revoked_at INTEGER, refresh_expires_at INTEGER)")
            conn.execute("INSERT INTO fixture_student_logins VALUES ('login','family','child',NULL,?)", (self.now + 14400000,))

        class FixtureAuth:
            def __init__(self):
                self.repository = self

            def get_session(self, conn, *, session_id):
                return conn.execute("SELECT * FROM fixture_student_logins WHERE id=?", (session_id,)).fetchone()

            def _active_principal_and_device(self, conn, *, session, now):
                return {"family_id": session["family_id"], "child_id": session["child_id"]}, None

        service = TextbookClassroomService(TextbookRepository(self.db), student_auth=FixtureAuth(),
            signing_key="synthetic-science-test-only", public_url="https://runtime.invalid", budget_service=self.budget)
        token = "tbpr_" + service.signer.dumps({"purpose": "runtime", "key": key, "release": release["sha256"],
            "studentSession": "login", "learningSession": "session", "gradeRevision": 1})
        return service, token, release

    def test_signed_published_science_release_reaches_real_budget_without_authority_mocks(self):
        service, token, release = self.textbook_service()
        result = service.admit_interaction(token, {"path": "/api/transcription", "request": {
            "subject": "other", "courseId": "forged", "userId": "foreign", "sessionId": "foreign"}})
        identity = result["paidBudget"]["authorizationId"]
        rows = self.rows()
        scope = json.loads(rows["learning_budget_authorizations"][0]["scope_json"])
        self.assertEqual(scope, {**self.scope(), "approvalReference": release["sha256"]})
        self.assertEqual(identity, scope_digest(scope))
        row = self.reserve(identity)
        self.assertTrue(self.budget.dispatch(authorization_id=identity, reservation_id=row["reservationId"],
                                            request_sha256=row["requestSha256"])["dispatchAllowed"])

    def test_unpublished_foreign_changed_or_revoked_release_never_mints_budget(self):
        service, token, _ = self.textbook_service()
        mutations = [
            ("UPDATE learning_textbook_course_builds SET status='draft'", "UPDATE learning_textbook_course_builds SET status='published'"),
            ("UPDATE learning_courses SET status='draft'", "UPDATE learning_courses SET status='published'"),
            ("UPDATE learning_sessions SET child_id='foreign'", "UPDATE learning_sessions SET child_id='child'"),
            ("UPDATE learning_sessions SET course_version='2'", "UPDATE learning_sessions SET course_version='1'"),
            ("UPDATE learning_textbook_selections SET revision_id='unselected'", "UPDATE learning_textbook_selections SET revision_id='directory'"),
            ("UPDATE fixture_student_logins SET revoked_at=1", "UPDATE fixture_student_logins SET revoked_at=NULL"),
        ]
        for mutate, restore in mutations:
            with self.subTest(mutate=mutate):
                with self.db.transaction() as conn:
                    conn.execute(mutate)
                with self.assertRaises(ApiError):
                    service.admit_interaction(token, {"path": "/api/transcription", "request": {}})
                self.assertTrue(all(not rows for rows in self.rows().values()))
                with self.db.transaction() as conn:
                    conn.execute(restore)
        with self.assertRaises(ApiError):
            service.admit_interaction(token + "tampered", {"path": "/api/transcription", "request": {}})
        self.assertTrue(all(not rows for rows in self.rows().values()))


if __name__ == "__main__":
    unittest.main()
