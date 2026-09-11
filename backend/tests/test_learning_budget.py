"""Real SQL transactions on an isolated temporary DB, never the user's data.

SQLite BEGIN IMMEDIATE exercises durable races and rollback in the shared
repository. Production uses the migration's InnoDB UPDATE row lock; a dedicated
MySQL deployment check remains separate from these offline tests.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from flask import Flask

from content.learning_budget_policy import LearningBudgetPolicy, PURPOSES, UNITS, digest
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService


class IsolatedDatabase:
    def __init__(self, path):
        self.path = str(path)
        schema = (Path(__file__).parents[1] / "migrations/076_learning_paid_budget.sql").read_text()
        # Only auto-increment spelling differs. Production SQL remains untouched.
        schema = schema.replace("BIGINT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT").replace(" ENGINE=InnoDB", "")
        with sqlite3.connect(self.path) as conn:
            conn.executescript(schema)

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = lambda cur, row: {desc[0]: value for desc, value in zip(cur.description, row)}
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def test_policy():
    raw = LearningBudgetPolicy.load().raw
    raw.update(enabled=True, version="synthetic-test.v1")
    generous = dict.fromkeys(UNITS, 1000000)
    window = {"day": generous, "month": generous}
    raw["limits"] = {"global": {**window, "maxInflightCalls": 100},
        "purposes": {p: window for p in PURPOSES}, "user": window,
        "course": {"lifetime": generous}, "authorization": generous}
    raw["prices"] = {"fake-text-v1": {"provider": "fake", "model": "fake-text", "version": "test-1",
        "allowedUnits": ["calls", "input_tokens", "output_tokens"],
        "perCallMax": {"calls": 1, "input_tokens": 1000, "output_tokens": 1000},
        "microsPerMillionUnits": {"calls": 0, "input_tokens": 1000000, "output_tokens": 2000000}}}
    return json.loads(json.dumps(raw))


class LearningBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = IsolatedDatabase(Path(self.directory.name) / "budget.db")
        self.now = int(datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000)
        self.raw = test_policy()
        self.service = self.make_service()
        self.auth = self.authorize()

    def make_service(self, raw=None):
        return LearningBudgetService(self.database, policy=LearningBudgetPolicy(raw or self.raw), clock=lambda: self.now)

    def authorize(self, name="production", purpose="production", user="student-a", course="course-a", maximum=None):
        identity = digest(name)
        scope = {"purpose": purpose, "gradeCode": "primary_1", "subject": "math", "courseId": course,
            "courseVersion": "v1", "userId": None if purpose == "production" else user,
            "sessionId": None if purpose == "production" else "session-" + name,
            "productionJobId": "job-" + name if purpose == "production" else None,
            "approvalReference": "test-approval"}
        maximum = maximum or dict.fromkeys(UNITS, 1000000)
        self.service.create_authorization(authorization_id=identity, scope=scope, max_units=maximum,
            price_keys=["fake-text-v1"], expires_at=self.now + 2 * 86400000)
        return identity

    def reserve(self, name="dispatch-a", auth=None, **changes):
        args = {"authorization_id": auth or self.auth, "dispatch_id": name,
            "request_sha256": digest(name), "price_key": "fake-text-v1",
            "max_units": {"calls": 1, "input_tokens": 100, "output_tokens": 50}}
        args.update(changes)
        return self.service.reserve(**args)

    def dispatch(self, row):
        return self.service.dispatch(reservation_id=row["reservationId"],
            authorization_id=row["authorizationId"], request_sha256=row["requestSha256"])

    def settle(self, row, **changes):
        args = {"reservation_id": row["reservationId"], "authorization_id": row["authorizationId"],
            "actual_units": {"calls": 1, "input_tokens": 20, "output_tokens": 10},
            "provider_request_id": "fake-provider-id", "evidence_sha256": digest("fake-receipt")}
        args.update(changes)
        return self.service.settle(**args)

    def assert_code(self, code, fn):
        with self.assertRaises(ApiError) as caught:
            fn()
        self.assertEqual(caught.exception.code, "learning_budget_" + code)

    def test_default_policy_cannot_authorize_spending(self):
        self.service = self.make_service(LearningBudgetPolicy.load().raw)
        self.assertFalse(self.service.status()["enabled"])
        with self.assertRaises(ValueError):
            self.authorize("new")
        self.assertEqual(self.service.status()["states"], {})

    def test_observe_records_cost_beyond_every_cumulative_quota_without_changing_grant(self):
        maximum = {**dict.fromkeys(UNITS, 0), "calls": 1}
        identity = self.authorize("metering-only", maximum=maximum)
        with self.database.transaction() as conn:
            frozen = self.service.repository.authorization(conn, identity)
        self.assert_code("authorization_limit", lambda: self.reserve(auth=identity))
        self.raw["aggregateLimitsEnabled"] = False
        limits = self.raw["limits"]
        for pool in (limits["global"], limits["user"], *limits["purposes"].values()):
            pool["day"] = pool["month"] = dict.fromkeys(UNITS, 0)
        limits["course"]["lifetime"] = limits["authorization"] = dict.fromkeys(UNITS, 0)
        self.service = self.make_service()
        for index in range(2):
            row = self.reserve(f"metered-{index}", auth=identity)
            self.assertEqual(row["maxUnits"]["money_micros"], 200)
            self.assertTrue(self.dispatch(row)["dispatchAllowed"])
            self.assertEqual(self.settle(row)["actualUnits"]["money_micros"], 40)
        with self.database.transaction() as conn:
            self.assertEqual(self.service.repository.authorization(conn, identity), frozen)
            ledger = self.service.repository.authorization_ledger(conn, identity)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(sum(json.loads(r["actual_units_json"])["money_micros"] for r in ledger), 80)
        context = self.service.authorization_context(authorization_id=identity)
        self.assertFalse(context["aggregateLimitsEnabled"])
        self.assertEqual(context["unsettledReservationCount"], 0)
        self.assertEqual(context["latestProviderDispatchAt"], self.now)

    def test_observe_records_measurement_above_price_quota_while_default_rejects_it(self):
        measurement = {"calls": 1, "input_tokens": 2000, "output_tokens": 50}
        with self.assertRaisesRegex(ValueError, "per-call resource"):
            self.reserve(max_units=measurement)
        self.raw["aggregateLimitsEnabled"] = False
        self.service = self.make_service()
        row = self.reserve(max_units=measurement)
        self.assertEqual(row["maxUnits"]["input_tokens"], 2000)
        self.assertEqual(row["maxUnits"]["money_micros"], 2100)
        self.assertTrue(self.dispatch(row)["dispatchAllowed"])
        actual = {"calls": 1, "input_tokens": 1500, "output_tokens": 20}
        result = self.settle(row, actual_units=actual)
        self.assertEqual(result["actualUnits"]["money_micros"], 1540)
        self.assertFalse(result["overrun"])

    def test_observe_keeps_measurement_scope_unknown_and_concurrency_guards(self):
        self.raw["aggregateLimitsEnabled"] = False
        self.raw["limits"]["global"]["maxInflightCalls"] = 1
        self.service = self.make_service()
        with self.assertRaisesRegex(ValueError, "measurements differ"):
            self.reserve(max_units={"calls": 1, "input_tokens": 100, "output_tokens": 50, "images": 1})
        with self.assertRaisesRegex(ValueError, "one call"):
            self.reserve(max_units={"calls": 2, "input_tokens": 100, "output_tokens": 50})
        self.assert_code("authorization_required", lambda: self.reserve(auth=digest("wrong-scope")))
        row = self.reserve()
        self.assertTrue(self.dispatch(row)["dispatchAllowed"])
        self.service.unknown(reservation_id=row["reservationId"], authorization_id=self.auth, reason_code="connection_lost")
        self.assertEqual(self.reserve()["state"], "unknown")
        self.assertFalse(self.dispatch(row)["dispatchAllowed"])
        self.assertEqual(self.service.authorization_context(authorization_id=self.auth)["unsettledReservationCount"], 1)
        self.assert_code("inflight_limit", lambda: self.reserve("second-call"))
        self.assert_code("cannot_release_dispatched", lambda: self.service.release(
            reservation_id=row["reservationId"], authorization_id=self.auth, reason_code="retry"))

    def test_reserve_does_not_dispatch_and_duplicate_claim_never_reauthorizes(self):
        first = self.reserve()
        self.assertFalse(first["dispatchAllowed"])
        self.assertEqual(first["maxUnits"]["money_micros"], 200)
        self.assertTrue(self.reserve()["reused"])
        self.assertTrue(self.dispatch(first)["dispatchAllowed"])
        self.assertFalse(self.dispatch(first)["dispatchAllowed"])
        self.assertEqual(self.service.status()["states"], {"dispatched": 1})

    def test_same_dispatch_id_cannot_change_request_or_authorization(self):
        self.reserve()
        self.assert_code("dispatch_conflict", lambda: self.reserve(request_sha256=digest("changed")))
        other = self.authorize("other")
        self.assert_code("dispatch_conflict", lambda: self.reserve(auth=other))

    def test_concurrent_workers_cannot_overspend_global_budget(self):
        self.raw["limits"]["global"]["day"]["calls"] = 3
        def attempt(index):
            service = self.make_service()
            try:
                return service.reserve(authorization_id=self.auth, dispatch_id=f"concurrent-{index}",
                    request_sha256=digest(index), price_key="fake-text-v1",
                    max_units={"calls": 1, "input_tokens": 100, "output_tokens": 50})["reservationId"]
            except ApiError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(16)))
        self.assertEqual(sum(v is not None for v in results), 3)
        self.assertEqual(self.service.status()["states"], {"reserved": 3})

    def test_unknown_cost_retains_hold_across_month_and_restart(self):
        self.raw["limits"]["global"]["day"]["money_micros"] = 250
        self.service = self.make_service()
        row = self.reserve()
        self.dispatch(row)
        self.service.unknown(reservation_id=row["reservationId"], authorization_id=self.auth, reason_code="connection_lost")
        self.now += 32 * 86400000
        self.service = self.make_service()
        other = self.authorize("next-month")
        self.assert_code("global_day_limit", lambda: self.reserve("next", auth=other))
        self.assert_code("cannot_release_dispatched", lambda: self.service.release(
            reservation_id=row["reservationId"], authorization_id=self.auth, reason_code="restart"))
        self.assertEqual(self.settle(row)["state"], "settled")
        self.assertEqual(self.reserve("next", auth=other)["state"], "reserved")

    def test_settlement_is_idempotent_uses_frozen_price_and_releases_only_difference(self):
        row = self.reserve()
        self.dispatch(row)
        self.raw["prices"]["fake-text-v1"]["microsPerMillionUnits"]["input_tokens"] = 9000000
        self.service = self.make_service()
        settled = self.settle(row)
        self.assertEqual(settled["actualUnits"]["money_micros"], 40)
        self.assertTrue(self.settle(row)["reused"])
        self.assert_code("settlement_conflict", lambda: self.settle(row, evidence_sha256=digest("different")))

    def test_known_overrun_is_recorded_and_halts_new_calls(self):
        row = self.reserve()
        self.dispatch(row)
        result = self.settle(row, actual_units={"calls": 1, "input_tokens": 120, "output_tokens": 20})
        self.assertTrue(result["overrun"])
        self.assertEqual(result["actualUnits"]["input_tokens"], 120)
        self.assertTrue(self.service.status()["halted"])
        self.assert_code("halted", lambda: self.reserve("next"))

    def test_authorization_is_server_bound_and_cannot_broaden_or_use_wrong_price(self):
        self.assert_code("authorization_required", lambda: self.reserve(auth=digest("unknown")))
        self.assert_code("price_not_authorized", lambda: self.reserve(price_key="another-price"))
        row = self.reserve()
        other = self.authorize("other")
        self.assert_code("reservation_required", lambda: self.service.dispatch(
            reservation_id=row["reservationId"], authorization_id=other, request_sha256=row["requestSha256"]))

    def test_release_only_before_dispatch_and_cannot_claim_again(self):
        row = self.reserve()
        self.assert_code("not_dispatched", lambda: self.settle(row))
        result = self.service.release(reservation_id=row["reservationId"], authorization_id=self.auth, reason_code="cancel_before_send")
        self.assertEqual(result["state"], "released")
        self.assertFalse(self.dispatch(row)["dispatchAllowed"])
        self.assertTrue(self.reserve()["reused"])

    def test_required_teaching_package_is_reserved_before_first_call(self):
        self.raw["limits"]["global"]["day"]["money_micros"] = 500
        self.service = self.make_service()
        maximum = dict.fromkeys(UNITS, 0)
        maximum.update(calls=2, input_tokens=200, output_tokens=100, money_micros=400)
        required = self.authorize("required", "required_teaching", maximum=maximum)
        self.assert_code("global_day_limit", lambda: self.reserve("production-after-admission"))
        first = self.reserve("required-first", auth=required)
        self.assertTrue(self.dispatch(first)["dispatchAllowed"])
        self.settle(first)
        self.assert_code("global_day_limit", lambda: self.reserve("production-after-partial-teaching"))
        self.assertEqual(self.reserve("required-second", auth=required)["state"], "reserved")

    def test_optional_interaction_has_user_and_purpose_limits(self):
        self.raw["limits"]["user"]["day"]["calls"] = 1
        self.service = self.make_service()
        a = self.authorize("optional-a", "optional_interaction")
        b = self.authorize("optional-b", "optional_interaction", course="other-course")
        self.reserve("optional-1", auth=a)
        self.assert_code("user_day_limit", lambda: self.reserve("optional-2", auth=b))

    def test_units_reject_boolean_negative_unknown_money_and_missing_caps(self):
        for values in ({"calls": True, "input_tokens": 1, "output_tokens": 1},
                       {"calls": 1, "input_tokens": -1, "output_tokens": 1},
                       {"calls": 1, "input_tokens": 1},
                       {"calls": 1, "input_tokens": 1, "output_tokens": 1, "money_micros": 0}):
            with self.assertRaises(ValueError):
                self.reserve(max_units=values)
        self.assertEqual(self.service.status()["states"], {})

    def test_units_only_pricing_is_explicit_and_not_reported_as_free(self):
        raw = deepcopy(self.raw)
        raw["prices"]["fake-text-v1"]["microsPerMillionUnits"] = None
        with self.assertRaises(ValueError):
            LearningBudgetPolicy(raw)
        raw["allowUnpriced"] = True
        self.service = self.make_service(raw)
        self.auth = self.authorize("unpriced-grant")
        result = self.reserve()
        self.assertEqual(result["pricingStatus"], "unpriced_units_only")

    def test_replay_and_settlement_remain_available_after_policy_disabled(self):
        row = self.reserve()
        self.dispatch(row)
        self.service = self.make_service(LearningBudgetPolicy.load().raw)
        self.assertTrue(self.reserve()["reused"])
        self.assertEqual(self.settle(row)["state"], "settled")

    def test_authorization_freezes_prices_before_any_call(self):
        original = self.service.authorization_context(authorization_id=self.auth)["prices"]
        raw = deepcopy(self.raw)
        raw["prices"]["fake-text-v1"]["version"] = "changed-rate"
        raw["prices"]["fake-text-v1"]["microsPerMillionUnits"]["input_tokens"] = 9000000
        self.service = self.make_service(raw)
        self.assertEqual(self.service.authorization_context(authorization_id=self.auth)["prices"], original)
        self.assertEqual(self.reserve()["priceVersion"], "test-1")
        self.assert_code("authorization_conflict", lambda: self.authorize())

    def test_issue_template_derives_all_limits_and_reuses_expiry(self):
        with self.database.transaction() as conn:
            scope = json.loads(conn.execute("SELECT scope_json FROM learning_budget_authorizations WHERE id = ?", (self.auth,)).fetchone()["scope_json"])
        self.assertIsNone(self.service.issue_course_authorization(authorization_id=digest("template"), scope=scope))
        raw = deepcopy(self.raw)
        raw["authorizationTemplates"]["production"] = {"maxUnits": dict.fromkeys(UNITS, 1000000),
            "priceKeys": ["fake-text-v1"], "ttlMs": 60000}
        self.service = self.make_service(raw)
        binding = self.service.issue_course_authorization(authorization_id=digest("template"), scope=scope)
        self.now += 1000
        self.assertEqual(binding, self.service.issue_course_authorization(authorization_id=digest("template"), scope=scope))
        self.assertTrue(binding["required"])
        self.service.close_authorization(authorization_id=binding["authorizationId"])
        self.assert_code("authorization_expired", lambda: self.reserve(auth=binding["authorizationId"]))

    def test_catalog_package_grant_reuses_frozen_scope_and_rechecks_scope_reduction(self):
        from integrations.openmaic_formal_media import INTERACTIVE_PROFESSIONAL_POLICY
        from services.learning_curriculum_preparation_contract import preparation_target_fingerprint
        target = {"gradeCode": "primary_2", "formalRuntimePolicy": {"professionalCreationPolicy": INTERACTIVE_PROFESSIONAL_POLICY},
            "courseTargets": [{"subject": "math", "skillId": "skill-a", "variantOrdinal": 1, "boundaryVersion": "boundary-a"}]}
        with self.database.transaction() as conn:
            conn.execute("CREATE TABLE learning_catalog_build_jobs (id TEXT, target_spec_json TEXT, request_id TEXT)")
            conn.execute("CREATE TABLE learning_catalog_build_items (id TEXT, build_job_id TEXT, grade_code TEXT, subject TEXT, skill_id TEXT, curriculum_version TEXT, boundary_version TEXT, variant_ordinal INTEGER, course_id TEXT, course_version TEXT)")
            conn.execute("CREATE TABLE learning_curriculum_preparation_plans (id TEXT, catalog_build_id TEXT, library_target_fingerprint TEXT, grade_code TEXT)")
            conn.execute("CREATE TABLE learning_course_supply_requests (target_fingerprint TEXT, subject TEXT, skill_id TEXT, variant_ordinal INTEGER, enabled INTEGER)")
            conn.execute("INSERT INTO learning_catalog_build_jobs VALUES ('build-a', ?, 'approved-build-a')", (json.dumps(target),))
            conn.execute("INSERT INTO learning_catalog_build_items VALUES ('item-a', 'build-a', 'primary_2', 'math', 'skill-a', 'curriculum-a', 'boundary-a', 1, 'course-a', 'v1')")
            conn.execute("INSERT INTO learning_curriculum_preparation_plans VALUES ('owner-a','build-a', ?, 'primary_2')", (preparation_target_fingerprint(target),))
            conn.execute("INSERT INTO learning_course_supply_requests VALUES (?, 'math', 'skill-a', 1, 1)", (preparation_target_fingerprint(target),))
        raw = deepcopy(self.raw)
        raw["authorizationTemplates"]["production"] = {"maxUnits": dict.fromkeys(UNITS, 1000000), "priceKeys": ["fake-text-v1"], "ttlMs": 60000}
        self.service = self.make_service(raw)
        args = {"build_item_id": "item-a", "expected_grade": "primary_2", "expected_subject": "math", "expected_skill": "skill-a"}
        first = self.service.issue_catalog_production_authorization(**args)
        self.now += 1000
        second = self.service.issue_catalog_production_authorization(**args, expected_course_id="course-a", expected_course_version="v1")
        self.assertEqual(first, second)
        row = self.reserve("phase-one", auth=first["authorizationId"])
        self.assert_code("catalog_scope_mismatch", lambda: self.service.issue_catalog_production_authorization(**args, expected_course_id="forged"))
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_course_supply_requests SET enabled = 0")
        self.assert_code("catalog_scope_disabled", lambda: self.service.dispatch(authorization_id=first["authorizationId"], reservation_id=row["reservationId"], request_sha256=row["requestSha256"]))
        self.assertEqual(self.service.status()["states"], {"reserved": 1})

    def test_fixed_operator_scope_and_expiry_guard_actual_dispatch(self):
        other = self.authorize(name="outside-operator")
        with self.database.transaction() as conn:
            allowed = json.loads(self.service.repository.authorization(conn, self.auth)["scope_json"])
        raw = deepcopy(self.raw)
        raw["authorizationWindow"] = {"startsAt": self.now, "expiresAt": self.now + 1000, "scopes": [allowed]}
        self.service = self.make_service(raw)
        first = self.reserve("first-operator")
        self.service.dispatch(authorization_id=self.auth, reservation_id=first["reservationId"], request_sha256=first["requestSha256"])
        pending = self.reserve("pending-operator")
        self.assert_code("scope_not_approved", lambda: self.reserve("other-operator", auth=other))
        self.now += 1001
        self.assert_code("authorization_window_closed", lambda: self.service.dispatch(
            authorization_id=self.auth,reservation_id=pending["reservationId"],request_sha256=pending["requestSha256"]))
        self.service.settle(authorization_id=self.auth,reservation_id=first["reservationId"],
            actual_units={"calls":1,"input_tokens":1,"output_tokens":1},provider_request_id=None,evidence_sha256=digest("reported"))
        self.assertEqual(self.service.status()["states"], {"reserved":1,"settled":1})

    def test_internal_api_requires_guard_and_rejects_client_scope_fields(self):
        from routes.internal.learning_budget import internal_learning_budget_bp
        app = Flask("isolated-budget-api")
        app.register_blueprint(internal_learning_budget_bp, url_prefix="/internal/learning/budget")
        guard = Mock()
        guard.authorize.side_effect = ApiError("missing_internal_token", "missing", 401)
        with patch("routes.internal.learning_budget.internal_request_guard", return_value=guard), \
             patch("routes.internal.learning_budget.learning_budget_service", return_value=self.service):
            client = app.test_client()
            self.assertEqual(client.get("/internal/learning/budget/status").status_code, 401)
            guard.authorize.side_effect = None
            payload = {"authorizationId": self.auth, "dispatchId": "api-request", "requestSha256": digest("api"),
                "priceKey": "fake-text-v1", "maxUnits": {"calls": 1, "input_tokens": 100, "output_tokens": 50}}
            self.assertEqual(client.post("/internal/learning/budget/reserve", json={**payload, "userId": "forged"}).status_code, 400)
            response = client.post("/internal/learning/budget/reserve", json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["budget"]["dispatchAllowed"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(client.post("/internal/learning/budget/authorize", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
