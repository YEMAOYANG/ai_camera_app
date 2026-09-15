"""Required-3D catalog scopes coexist with v1 on an isolated local SQL fixture."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from content.learning_budget_policy import LearningBudgetPolicy, UNITS, digest
from core.errors import ApiError
from integrations.openmaic_formal_media import MULTISTATE_PROFESSIONAL_POLICY
from services.learning_budget_service import LearningBudgetService
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint
from tests.test_learning_budget import IsolatedDatabase, test_policy


class Required3dCatalogBudgetTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.current = build_preparation_target("primary_6")
        with patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": "1"}):
            self.target = build_preparation_target("primary_6")
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = IsolatedDatabase(Path(self.directory.name) / "budget.db")
        raw = test_policy()
        raw["authorizationTemplates"]["production"] = {
            "maxUnits": dict.fromkeys(UNITS, 1000000), "priceKeys": ["fake-text-v1"], "ttlMs": 60000}
        self.service = LearningBudgetService(self.database, policy=LearningBudgetPolicy(raw), clock=lambda: 1000)
        with self.database.transaction() as conn:
            conn.execute("CREATE TABLE learning_catalog_build_jobs (id TEXT, target_spec_json TEXT, request_id TEXT)")
            conn.execute("CREATE TABLE learning_catalog_build_items (id TEXT, build_job_id TEXT, grade_code TEXT, subject TEXT, skill_id TEXT, curriculum_version TEXT, boundary_version TEXT, variant_ordinal INTEGER, course_id TEXT, course_version TEXT)")
            conn.execute("CREATE TABLE learning_curriculum_preparation_plans (id TEXT, catalog_build_id TEXT, library_target_fingerprint TEXT, grade_code TEXT)")
            conn.execute("CREATE TABLE learning_course_supply_requests (target_fingerprint TEXT, subject TEXT, skill_id TEXT, variant_ordinal INTEGER, enabled INTEGER)")
            slot = next(s for s in self.target["courseTargets"] if (s["subject"], s["skillId"], s["variantOrdinal"]) == ("english", "past_future", 1))
            conn.execute("INSERT INTO learning_catalog_build_jobs VALUES ('new-build', ?, 'explicit-new-build')", (json.dumps(self.target),))
            conn.execute("INSERT INTO learning_catalog_build_items VALUES ('new-item','new-build','primary_6','english','past_future',?,?,1,'new-course','v1')",
                         (self.target["curriculumVersion"], slot["boundaryVersion"]))
            conn.execute("INSERT INTO learning_curriculum_preparation_plans VALUES ('default-owner','default-build',?,'primary_6')",
                         (preparation_target_fingerprint(self.current),))
            conn.execute("INSERT INTO learning_curriculum_preparation_plans VALUES ('new-owner','new-build',?,'primary_6')",
                         (preparation_target_fingerprint(self.target),))
            conn.execute("INSERT INTO learning_course_supply_requests VALUES (?,'english','past_future',1,1)",
                         (preparation_target_fingerprint(self.target),))

    def context(self, **expected):
        with self.database.transaction() as conn:
            return self.service._catalog_production_scope(conn, "new-item", **expected)

    def assert_code(self, code, callback):
        with self.assertRaises(ApiError) as caught:
            callback()
        self.assertEqual(caught.exception.code, "learning_budget_" + code)

    def install_target(self, target):
        fingerprint = preparation_target_fingerprint(target)
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_catalog_build_jobs SET target_spec_json = ?", (json.dumps(target),))
            conn.execute("UPDATE learning_curriculum_preparation_plans SET library_target_fingerprint = ? WHERE id='new-owner'", (fingerprint,))
            conn.execute("UPDATE learning_course_supply_requests SET target_fingerprint = ?", (fingerprint,))

    def test_exact_v2_scope_issues_and_dispatches_under_default_v1_api(self):
        scope, required = self.context(expected_grade="primary_6", expected_subject="english", expected_skill="past_future")
        self.assertTrue(required)
        self.assertEqual(scope["productionJobId"], "new-item")
        self.assertEqual(scope["approvalReference"], "explicit-new-build")
        slot = next(s for s in self.target["courseTargets"] if (s["subject"], s["skillId"], s["variantOrdinal"]) == ("english", "past_future", 1))
        self.assertEqual(scope["courseVersion"], digest({"curriculumVersion": self.target["curriculumVersion"],
            "boundaryVersion": slot["boundaryVersion"], "targetSpec": self.target}))
        binding = self.service.issue_catalog_production_authorization(build_item_id="new-item")
        request = self.service.reserve(authorization_id=binding["authorizationId"], dispatch_id="synthetic-v2",
            request_sha256=digest("synthetic-v2"), price_key="fake-text-v1",
            max_units={"calls": 1, "input_tokens": 100, "output_tokens": 50})
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_course_supply_requests SET enabled = 0")
        dispatch = lambda: self.service.dispatch(authorization_id=binding["authorizationId"],
            reservation_id=request["reservationId"], request_sha256=request["requestSha256"])
        self.assert_code("catalog_scope_disabled", dispatch)
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_course_supply_requests SET enabled = 1")
        self.assertTrue(dispatch()["dispatchAllowed"])
        self.assert_code("catalog_scope_mismatch", lambda: self.context(expected_subject="math"))

    def test_unrelated_curriculum_drift_and_older_policy_remain_superseded(self):
        changed = deepcopy(self.target)
        changed["curriculumVersion"] += ".forged"
        self.install_target(changed)
        self.assert_code("catalog_scope_superseded", self.context)
        old = deepcopy(self.current)
        old["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(MULTISTATE_PROFESSIONAL_POLICY)
        self.install_target(old)
        self.assert_code("catalog_scope_superseded", self.context)

    def test_v2_exception_requires_exact_owner_target_and_slot(self):
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_curriculum_preparation_plans SET library_target_fingerprint = ? WHERE id='new-owner'", ("0" * 64,))
        self.assert_code("catalog_scope_superseded", self.context)
        self.install_target(self.target)
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_catalog_build_items SET boundary_version = 'wrong-boundary'")
        self.assert_code("catalog_target_scope_mismatch", self.context)


if __name__ == "__main__":
    unittest.main()
