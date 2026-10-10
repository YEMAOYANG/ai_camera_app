"""Purpose-only hard limits use an isolated ledger; no provider or existing DB."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from content.learning_budget_policy import LearningBudgetPolicy, UNITS, digest
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService
from test_homework_paid_budget import HomeworkBudgetDatabase

CONTENT = Path(__file__).parents[1] / "content"


class HomeworkPurposeBudgetTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db = HomeworkBudgetDatabase(Path(temporary.name) / "budget.db")
        self.raw = json.loads((CONTENT / "learning_classroom_homework_policy.json").read_text())
        self.now = 1000
        self.service = self.make_service()

    def make_service(self):
        return LearningBudgetService(self.db, policy=LearningBudgetPolicy(self.raw), clock=lambda: self.now)

    def auth(self, item="hwi_test", revision=1, submission="hw_test", child="child-a"):
        with self.db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO homework_submissions VALUES (?,?,?,?,?,?,?)",
                         (submission, "family-a", child, "primary_1", "math", 1, None))
            conn.execute("INSERT OR IGNORE INTO homework_items VALUES (?,?,?,?)",
                         (item, submission, revision, json.dumps({"status": "incorrect", "answerMode": "picture_choice"})))
        return self.service.issue_homework_authorization(submission_id=submission, item_id=item, revision=revision)["authorizationId"]

    def reserve(self, auth, name, characters=10):
        return self.service.reserve(authorization_id=auth, dispatch_id=name, request_sha256=digest(name),
            price_key="qwen-tts-beijing", max_units={"calls": 1, "characters": characters})

    def dispatch(self, row):
        return self.service.dispatch(reservation_id=row["reservationId"], authorization_id=row["authorizationId"],
                                     request_sha256=row["requestSha256"])

    def settle(self, row):
        self.dispatch(row)
        return self.service.settle(reservation_id=row["reservationId"], authorization_id=row["authorizationId"],
            actual_units={"calls": 1, "characters": row["maxUnits"]["characters"]},
            provider_request_id="isolated-receipt", evidence_sha256=digest(row["reservationId"]))

    def assert_code(self, code, action):
        with self.assertRaises(ApiError) as caught:
            action()
        self.assertEqual(caught.exception.code, "learning_budget_" + code)

    def test_old_policy_bytes_hash_and_templates_remain_unchanged(self):
        original_bytes = (CONTENT / "learning_classroom_policy.json").read_bytes()
        self.assertEqual(hashlib.sha256(original_bytes).hexdigest(), "fea5736abb8710c7725f2e8a12090455a629510ed3a51980127675726828907c")
        original = json.loads(original_bytes)
        self.assertEqual(LearningBudgetPolicy(original).sha256, digest(original))
        self.assertNotIn("enforcedPurposes", LearningBudgetPolicy(original).raw)
        comparable = deepcopy(self.raw)
        comparable["version"] = original["version"]
        del comparable["enforcedPurposes"]
        del comparable["limits"]["purposes"]["homework"]
        del comparable["authorizationTemplates"]["homework"]
        # The current tutor adds a separately priced Flash model. Existing
        # classroom prices and templates must still match the immutable policy.
        self.assertEqual(set(comparable["prices"]) - set(original["prices"]),
                         {"deepseek-current-flash-peak"})
        del comparable["prices"]["deepseek-current-flash-peak"]
        self.assertEqual(comparable, original)

    def test_enforced_purpose_registry_is_strict(self):
        for value in (None, "homework", ["unregistered"], ["homework", "homework"], [True], [{}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                LearningBudgetPolicy({**self.raw, "enforcedPurposes": value})
        original = json.loads((CONTENT / "learning_classroom_policy.json").read_text())
        with self.assertRaises(ValueError):
            LearningBudgetPolicy({**original, "enforcedPurposes": ["homework"]})

    def test_published_homework_limits_are_explicit(self):
        template = self.raw["authorizationTemplates"]["homework"]
        self.assertEqual(template["priceKeys"], ["qwen-tts-beijing", "qwen-asr-beijing"])
        self.assertEqual(template["ttlMs"], 7 * 86400000)
        self.assertEqual([template["maxUnits"][k] for k in ("calls", "characters", "money_micros")], [100, 30000, 800000])
        limits = self.raw["limits"]["purposes"]["homework"]
        for actual, expected in ((limits["day"], [500, 60000, 10000000]),
                                 (limits["month"], [3000, 300000, 30000000]),
                                 (limits["course"]["lifetime"], [200, 30000, 2400000])):
            self.assertEqual([actual[k] for k in ("calls", "characters", "money_micros")], expected)

    def test_pilot_five_call_authority_remains_bounded_and_v2_issues_a_new_grant(self):
        current=self.raw
        self.raw=json.loads((CONTENT / "learning_classroom_homework_policy.v1.json").read_text())
        self.service=self.make_service()
        auth = self.auth()
        self.assertTrue(self.service.authorization_context(authorization_id=auth)["aggregateLimitsEnabled"])
        for index in range(5):
            self.settle(self.reserve(auth, f"clip-{index}", 200))
        self.assert_code("authorization_limit", lambda: self.reserve(auth, "sixth", 1))
        with self.db.transaction() as conn:
            old_authority=dict(self.service.repository.authorization(conn,auth))
        self.raw=current
        self.service=self.make_service()
        replacement=self.auth()
        self.assertNotEqual(replacement,auth)
        self.assertEqual(self.reserve(replacement,"first-new-tutor",900)["state"],"reserved")
        with self.db.transaction() as conn:
            self.assertEqual(dict(self.service.repository.authorization(conn,auth)),old_authority)
        self.raw["authorizationTemplates"]["homework"]["maxUnits"]["characters"]=1000
        self.service=self.make_service()
        other = self.auth("other-item")
        self.assert_code("authorization_limit", lambda: self.reserve(other, "too-long", 1001))
        self.raw["authorizationTemplates"]["homework"]["maxUnits"]["money_micros"] = 100
        self.service = self.make_service()
        third = self.auth("money-item")
        self.assert_code("authorization_limit", lambda: self.reserve(third, "money", 2))

    def test_v2_voice_questions_have_real_asr_budget_and_audio_ms_ceilings(self):
        auth=self.auth()
        self.assertEqual(self.service.reserve(authorization_id=auth,dispatch_id="voice-question",
            request_sha256=digest("voice-question"),price_key="qwen-asr-beijing",
            max_units={"calls":1,"audio_ms":60000})["state"],"reserved")
        self.raw["limits"]["purposes"]["homework"]["course"]["lifetime"]["audio_ms"]=60000
        self.service=self.make_service()
        self.assert_code("course_limit",lambda:self.service.reserve(authorization_id=auth,
            dispatch_id="another-voice",request_sha256=digest("another-voice"),
            price_key="qwen-asr-beijing",max_units={"calls":1,"audio_ms":1}))

    def test_original_classroom_authority_and_settled_ledger_do_not_block_homework(self):
        old = LearningBudgetPolicy.load(CONTENT / "learning_classroom_policy.json")
        old_service = LearningBudgetService(self.db, policy=old, clock=lambda: self.now)
        scope = {"purpose": "required_teaching", "gradeCode": "primary_1", "subject": "math",
            "courseId": "course-a", "courseVersion": "v1", "userId": "student-a", "sessionId": "session-a",
            "productionJobId": None, "approvalReference": "existing-classroom"}
        auth = old_service.issue_course_authorization(authorization_id=digest("old-classroom"), scope=scope)["authorizationId"]
        with self.db.transaction() as conn:
            original_authority = self.service.repository.authorization(conn, auth)
        # This already authorized classroom retains metering behavior beyond the
        # old global money/character and per-call price ceilings after switching.
        self.assertFalse(self.service.authorization_context(authorization_id=auth)["aggregateLimitsEnabled"])
        self.settle(self.reserve(auth, "classroom-metered", 200000))
        self.assertEqual(self.reserve(self.auth(), "homework-after-classroom")["state"], "reserved")
        with self.db.transaction() as conn:
            self.assertEqual(self.service.repository.authorization(conn, auth), original_authority)

    def test_submission_spending_survives_item_revision_and_new_items(self):
        self.raw["limits"]["purposes"]["homework"]["course"]["lifetime"]["calls"] = 1
        self.service = self.make_service()
        self.settle(self.reserve(self.auth(), "first"))
        with self.db.transaction() as conn:
            conn.execute("UPDATE homework_items SET revision=2 WHERE id='hwi_test'")
        for auth in (self.auth(revision=2), self.auth("new-item")):
            self.assert_code("course_limit", lambda: self.reserve(auth, "new-" + auth))

    def test_purpose_and_user_daily_monthly_caps_apply_across_submissions(self):
        for dimension, cap_name in (("calls", "purpose_day"), ("characters", "purpose_month"),
                                    ("money_micros", "user_day")):
            with self.subTest(cap=cap_name):
                # Fresh temporary ledger per independent boundary.
                self.setUp()
                pool, window = cap_name.split("_")
                limit = self.raw["limits"]["purposes"]["homework"]
                target = limit[window] if pool == "purpose" else limit["user"][window]
                target[dimension] = {"calls": 1, "characters": 10, "money_micros": 800}[dimension]
                self.service = self.make_service()
                self.settle(self.reserve(self.auth(), "first", 10))
                other = self.auth("other-item", submission="other-submission")
                self.assert_code(cap_name + "_limit", lambda: self.reserve(other, "second", 1))

    def test_unknown_hold_survives_month_and_restart_without_retry(self):
        self.raw["limits"]["purposes"]["homework"]["day"]["characters"] = 100
        self.service = self.make_service()
        row = self.reserve(self.auth(), "uncertain", 100)
        self.dispatch(row)
        self.service.unknown(reservation_id=row["reservationId"], authorization_id=row["authorizationId"], reason_code="timeout")
        self.now += 32 * 86400000
        self.service = self.make_service()
        other = self.auth("later-item", submission="later-submission")
        self.assert_code("purpose_day_limit", lambda: self.reserve(other, "later", 1))
        self.assertFalse(self.dispatch(row)["dispatchAllowed"])
        self.assert_code("cannot_release_dispatched", lambda: self.service.release(reservation_id=row["reservationId"],
            authorization_id=row["authorizationId"], reason_code="retry"))

    def test_global_inflight_ceiling_is_still_shared(self):
        self.raw["limits"]["global"]["maxInflightCalls"] = 1
        self.service = self.make_service()
        row = self.reserve(self.auth(), "occupied")
        self.dispatch(row)
        self.service.unknown(reservation_id=row["reservationId"], authorization_id=row["authorizationId"], reason_code="timeout")
        self.assert_code("inflight_limit", lambda: self.reserve(self.auth("other-item"), "another"))

    def test_parallel_reservations_cannot_overspend_purpose_budget(self):
        self.raw["limits"]["purposes"]["homework"]["day"]["calls"] = 2
        self.service = self.make_service()
        authorities = [self.auth(f"item-{index}", submission=f"submission-{index}") for index in range(8)]
        def attempt(pair):
            index, auth = pair
            try:
                return self.make_service().reserve(authorization_id=auth, dispatch_id=f"parallel-{index}",
                    request_sha256=digest(index), price_key="qwen-tts-beijing", max_units={"calls": 1, "characters": 10})
            except ApiError:
                return None
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt, enumerate(authorities)))
        self.assertEqual(sum(result is not None for result in results), 2)


if __name__ == "__main__":
    unittest.main()
