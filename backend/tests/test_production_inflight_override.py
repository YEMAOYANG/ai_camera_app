"""Bounded admission against isolated SQL; no live policy, grants or providers."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from content.learning_budget_policy import LearningBudgetPolicy, UNITS, digest
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService
from tests.test_learning_budget import IsolatedDatabase, test_policy


class ProductionInflightOverrideTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = IsolatedDatabase(Path(self.directory.name) / "budget.db")
        self.now = 100000
        self.scope = {"purpose": "production", "gradeCode": "primary_6", "subject": "math",
            "courseId": "catalog-item:item-a", "courseVersion": "frozen-version",
            "productionJobId": "item-a", "userId": None, "sessionId": None,
            "approvalReference": "existing-approval"}
        self.auth = digest({"schema": "mira.catalog-paid-budget.v1", "scope": self.scope})
        self.teaching_scope = {**self.scope, "purpose": "required_teaching", "courseId": "old-published-course",
            "productionJobId": None, "userId": "synthetic-child", "sessionId": "old-session"}
        self.teaching_auth = digest("old-teaching-authorization")
        self.raw = test_policy()
        self.raw["aggregateLimitsEnabled"] = False
        self.raw["limits"]["global"]["maxInflightCalls"] = 4
        self.raw["authorizationWindow"] = {"startsAt": self.now, "expiresAt": self.now + 1000,
            "scopes": [self.scope, self.teaching_scope]}
        self.service = self.make_service()
        self.create_authorization(self.auth, self.scope)
        self.create_authorization(self.teaching_auth, self.teaching_scope)
        self.alias_auth = digest("different-authorization-same-scope")
        self.create_authorization(self.alias_auth, self.scope)
        self.initial_authorities = self.authorities()

    def make_service(self, raw=None):
        service = LearningBudgetService(self.database, policy=LearningBudgetPolicy(raw or self.raw), clock=lambda: self.now)
        # This suite isolates admission. The original catalog guard remains called;
        # test_learning_budget covers its real catalog SQL and scope reductions.
        service._catalog_production_scope = Mock(return_value=(self.scope, True))
        return service

    def create_authorization(self, identity, scope):
        self.service.create_authorization(authorization_id=identity, scope=scope,
            max_units=dict.fromkeys(UNITS, 1000000), price_keys=["fake-text-v1"], expires_at=self.now + 2000)

    def authorities(self):
        with self.database.transaction() as conn:
            return conn.execute("SELECT * FROM learning_budget_authorizations ORDER BY id").fetchall()

    def ledger(self):
        with self.database.transaction() as conn:
            return conn.execute("SELECT * FROM learning_budget_reservations ORDER BY id").fetchall()

    def enable_override(self):
        self.raw["productionInflightOverride"] = {"scopeSha256": digest(self.scope), "authorizationId": self.auth,
            "maxInflightCalls": 5, "auditReferenceSha256": digest("reviewed-original-recovery-proof")}
        self.service = self.make_service()

    def reserve(self, name, auth=None, service=None):
        return (service or self.service).reserve(authorization_id=auth or self.auth, dispatch_id=name,
            request_sha256=digest(name), price_key="fake-text-v1",
            max_units={"calls": 1, "input_tokens": 100, "output_tokens": 50})

    def dispatch(self, row):
        return self.service.dispatch(reservation_id=row["reservationId"], authorization_id=row["authorizationId"],
            request_sha256=row["requestSha256"])

    def mark_unknown(self, row):
        self.dispatch(row)
        self.service.unknown(reservation_id=row["reservationId"], authorization_id=row["authorizationId"],
            reason_code="provider_result_unknown")

    def fill_four_unknowns(self):
        for index in range(4):
            self.mark_unknown(self.reserve(f"original-{index}", self.teaching_auth if index == 0 else self.auth))

    def assert_code(self, expected, operation):
        with self.assertRaises(ApiError) as caught:
            operation()
        self.assertEqual(caught.exception.code, "learning_budget_" + expected)

    def test_exact_production_gets_one_slot_old_unknowns_and_grants_unchanged(self):
        self.fill_four_unknowns()
        old = self.ledger()
        self.assert_code("inflight_limit", lambda: self.reserve("before-override"))
        self.enable_override()
        self.assert_code("inflight_limit", lambda: self.reserve("teaching", self.teaching_auth))
        self.assert_code("inflight_limit", lambda: self.reserve("alias", self.alias_auth))
        fifth = self.reserve("fifth")
        self.mark_unknown(fifth)
        self.assert_code("inflight_limit", lambda: self.reserve("sixth"))
        self.assertEqual(self.authorities(), self.initial_authorities)
        self.assertEqual([r for r in self.ledger() if r["id"] != fifth["reservationId"]], old)
        self.assertEqual([r["state"] for r in self.ledger()], ["unknown"] * 5)
        self.assert_code("cannot_release_dispatched", lambda: self.service.release(
            reservation_id=fifth["reservationId"], authorization_id=self.auth, reason_code="finished"))
        with self.database.transaction() as conn:
            event = conn.execute("SELECT evidence_json FROM learning_budget_events WHERE reservation_id=? AND event_type='reserved'",
                (fifth["reservationId"],)).fetchone()
        self.assertEqual(json.loads(event["evidence_json"])["productionInflightOverride"], self.raw["productionInflightOverride"])

    def test_missing_field_preserves_legacy_hash_and_four_slot_default(self):
        policy = LearningBudgetPolicy(self.raw)
        self.assertEqual(policy.raw, self.raw)
        self.assertEqual(policy.sha256, digest(self.raw))
        self.assertNotIn("productionInflightOverride", LearningBudgetPolicy.load().raw)
        self.fill_four_unknowns()
        self.assert_code("inflight_limit", lambda: self.reserve("fifth"))

    def test_concurrent_reserves_get_exactly_one_extra_slot(self):
        self.fill_four_unknowns()
        self.enable_override()
        def attempt(index):
            try:
                return self.reserve(f"parallel-{index}", service=self.make_service())
            except ApiError as error:
                self.assertEqual(error.code, "learning_budget_inflight_limit")
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(row is not None for row in results), 1)
        self.assertEqual(len(self.ledger()), 5)

    def test_dispatch_rechecks_policy_removal_and_original_window(self):
        self.fill_four_unknowns()
        self.enable_override()
        fifth = self.reserve("fifth")
        without = deepcopy(self.raw)
        del without["productionInflightOverride"]
        self.service = self.make_service(without)
        self.assert_code("inflight_limit", lambda: self.dispatch(fifth))
        self.service = self.make_service()
        self.now += 1000
        self.assert_code("authorization_window_closed", lambda: self.dispatch(fifth))
        self.assert_code("authorization_window_closed", lambda: self.reserve("after-window"))
        self.assertEqual(self.authorities(), self.initial_authorities)

    def test_no_new_grant_and_changed_catalog_still_refused(self):
        self.fill_four_unknowns()
        self.enable_override()
        self.assert_code("authorization_required", lambda: self.reserve("no-grant", digest("absent")))
        self.service._catalog_production_scope.return_value = ({**self.scope, "courseVersion": "changed"}, True)
        self.assert_code("catalog_scope_changed", lambda: self.reserve("changed-scope"))
        self.assertEqual(len(self.ledger()), 4)

    def test_admission_identity_compares_entire_scope_and_fixed_window(self):
        self.enable_override()
        policy = self.service.policy
        original = dict(scope=self.scope, authorization_id=self.auth, now=self.now)
        self.assertIsNotNone(policy.production_inflight_override(**original))
        for field, value in (("purpose", "required_teaching"), ("gradeCode", "primary_5"),
                ("subject", "chinese"), ("courseId", "another"), ("courseVersion", "v2"),
                ("productionJobId", "another-item"), ("userId", "child"), ("sessionId", "session"),
                ("approvalReference", "another-approval")):
            with self.subTest(field=field):
                self.assertIsNone(policy.production_inflight_override(**{**original, "scope": {**self.scope, field: value}}))
        self.assertIsNone(policy.production_inflight_override(**{**original, "authorization_id": self.alias_auth}))
        for now in (self.now - 1, self.now + 1000):
            self.assertIsNone(policy.production_inflight_override(**{**original, "now": now}))

    def test_policy_rejects_unbounded_or_unapproved_overrides(self):
        self.enable_override()
        variations = []
        for field, value in (("scopeSha256", digest(self.teaching_scope)), ("authorizationId", self.alias_auth),
                ("auditReferenceSha256", ""), ("maxInflightCalls", 6), ("maxInflightCalls", True),
                ("expiresAt", self.now + 99999)):
            raw = deepcopy(self.raw)
            raw["productionInflightOverride"][field] = value
            variations.append(raw)
        raw = deepcopy(self.raw)
        del raw["authorizationWindow"]
        variations.append(raw)
        raw = deepcopy(self.raw)
        raw["limits"]["global"]["maxInflightCalls"] = 5
        variations.append(raw)
        raw = deepcopy(self.raw)
        raw["aggregateLimitsEnabled"] = True
        variations.append(raw)
        raw = deepcopy(self.raw)
        raw["productionInflightOverride"] = None
        variations.append(raw)
        raw = deepcopy(self.raw)
        raw["authorizationWindow"]["scopes"].append({**self.scope, "courseVersion": "another"})
        variations.append(raw)
        for index, raw in enumerate(variations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                LearningBudgetPolicy(raw)
