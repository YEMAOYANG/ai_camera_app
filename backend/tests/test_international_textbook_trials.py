"""Isolated readiness API checks: no live accounts, providers or course writes."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from werkzeug.datastructures import MultiDict

from core.errors import ApiError
from routes.api.v2.student_international_trials import student_international_trials_bp
from services.international_textbook_trial_service import InternationalTextbookTrialService, SCHEMA


def manifest():
    books = []
    for identity, subject, grade, semester in (
        ("hk-sfa-chinese-p5-lower", "chinese", "primary_5", "lower"),
        ("hk-sfa-english-p6-upper", "english", "primary_6", "upper"),
    ):
        books.append({"id": identity, "subject": subject, "gradeCode": grade, "semester": semester,
            "requestedTitle": "Synthetic requested book", "matchedTitle": None, "publisher": None,
            "editionStatus": "needs_confirmation", "editionNote": "Synthetic evidence only",
            "candidates": [], "evidence": [{"label": "Synthetic source", "url": "https://example.org/catalog",
                "detail": "This test does not establish a textbook match"}],
            "requiredMaterials": ["Exact book identity and lesson source"]})
    return {"schemaVersion": SCHEMA, "checkedAt": "2026-10-12", "school": {
        "requestedName": "香港圣方济各英文小学", "name": "聖方濟各英文小學",
        "website": "https://sfaeps.edu.hk/", "booklistStatus": "unconfirmed"}, "textbooks": books}


class InternationalTextbookTrialTest(unittest.TestCase):
    def setUp(self):
        self.auth = Mock()
        self.auth.authenticate.return_value = {"principal": {"child_id": "isolated-child"}}
        self.manifest = manifest()
        self.service = InternationalTextbookTrialService(student_auth=self.auth, manifest=self.manifest)
        self.app = Flask(__name__)
        self.app.register_blueprint(student_international_trials_bp,
            url_prefix="/api/v2/student/learning/international-trials")
        self.client = self.app.test_client()
        self.url = "/api/v2/student/learning/international-trials"
        self.headers = {"Authorization": "Bearer isolated-student"}

    def request(self, suffix="", method="get"):
        with patch("routes.api.v2.student_international_trials.student_auth_service", return_value=self.auth), \
             patch("routes.api.v2.student_international_trials.InternationalTextbookTrialService", return_value=self.service):
            return getattr(self.client, method)(self.url + suffix, headers=self.headers)

    def test_authenticated_read_preserves_mixed_grades_and_never_dispatches(self):
        with patch("integrations.openmaic_full_runtime_client.OpenMaicFullRuntimeClient.start_generation") as dispatch, \
             patch("core.database.Database.transaction") as transaction:
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.auth.authenticate.assert_called_once_with("isolated-student")
        self.assertEqual([(b["subject"], b["gradeCode"], b["semester"]) for b in response.json["textbooks"]],
            [("chinese", "primary_5", "lower"), ("english", "primary_6", "upper")])
        self.assertEqual(response.json["generation"], {
            "status": "blocked_source", "canGenerate": False, "publishedCourseKey": None})
        dispatch.assert_not_called()
        transaction.assert_not_called()
        self.assertNotIn("principal", response.json)

    def test_expired_student_session_returns_401_without_reading_catalogue(self):
        self.service = InternationalTextbookTrialService(student_auth=self.auth)
        self.auth.authenticate.side_effect = ApiError("student_access_expired", "请重新进入学习空间", 401)
        with patch("pathlib.Path.read_text") as read:
            response = self.request()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        read.assert_not_called()

    def test_any_query_and_mutation_request_are_rejected(self):
        for suffix in ("?childId=other", "?gradeCode=primary_1", "?book=one&book=two", "?generate=true"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.request(suffix).status_code, 400)
        self.assertEqual(self.request(method="post").status_code, 405)
        self.auth.authenticate.assert_not_called()
        with self.assertRaises(ApiError):
            self.service.catalog("isolated-student", MultiDict([("", "")]))

    def test_catalog_verification_is_not_generation_or_school_confirmation(self):
        value = manifest()
        value["textbooks"][0].update(editionStatus="catalog_verified", matchedTitle="Verified catalogue title", publisher="Publisher")
        result = InternationalTextbookTrialService(student_auth=self.auth, manifest=value).catalog("isolated-student")
        self.assertFalse(result["generation"]["canGenerate"])
        self.assertEqual(result["school"]["booklistStatus"], "unconfirmed")
        self.assertTrue(result["textbooks"][0]["requiredMaterials"])

    def test_configuration_cannot_enable_generation_or_swap_exact_identity(self):
        for mutate in (
            lambda value: value.update(generation={"canGenerate": True}),
            lambda value: value["textbooks"][0].update(gradeCode="primary_6"),
            lambda value: value["textbooks"].append(deepcopy(value["textbooks"][0])),
            lambda value: value["textbooks"][1].update(id="hk-sfa-chinese-p5-lower"),
            lambda value: value["textbooks"][0].update(requiredMaterials=[]),
            lambda value: value["school"].update(booklistStatus="confirmed"),
            lambda value: value["textbooks"][0]["evidence"][0].update(url="javascript:alert(1)"),
            lambda value: value["textbooks"][0]["evidence"][0].update(url="https://user:password@example.org/"),
        ):
            value = manifest()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(ApiError) as raised:
                InternationalTextbookTrialService(student_auth=self.auth, manifest=value).catalog("isolated-student")
            self.assertEqual(raised.exception.status_code, 503)

    def test_response_mutation_and_missing_file_do_not_change_source_or_expose_details(self):
        first = self.service.catalog("isolated-student")
        first["textbooks"][0]["requiredMaterials"].clear()
        self.assertTrue(self.service.catalog("isolated-student")["textbooks"][0]["requiredMaterials"])
        self.assertEqual(self.manifest, manifest())
        self.service = InternationalTextbookTrialService(student_auth=self.auth)
        with patch("pathlib.Path.read_text", side_effect=OSError("private-path-detail")):
            response = self.request()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-path-detail", response.text)


if __name__ == "__main__":
    unittest.main()
