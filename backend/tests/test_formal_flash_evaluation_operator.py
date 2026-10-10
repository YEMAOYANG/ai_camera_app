"""Offline original authoring and real isolated durable accounting checks."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from content.learning_budget_policy import digest
from core.errors import ApiError
from integrations.openmaic_formal_pedagogy import validate_generation_grade_boundary
from integrations.openmaic_formal_skill_selection import select_formal_skills
from scripts.evaluate_formal_flash_course import (
    bind_native_input, freeze_course, validate_frozen, write_json_new,
)
from scripts.formal_flash_eval_budget import (
    APPROVAL_SCHEMA, PRICE_SCHEMA, PRICE_VERSION, REQUIRED_QUOTES, build_plan,
    create_app, initialize_ledger, open_ledger, validate_plan,
)


NOW = 1791446400000


def fixtures(path, *, calls=12, per_course=10):
    frozen = [freeze_course(subject, run_id="offline-original-acceptance") for subject in ("math", "chinese")]
    approval = {"schemaVersion": APPROVAL_SCHEMA, "humanAuthorizationVerified": True,
                "humanAuthorizationSha256": digest("synthetic human authorization; not a live spend grant"),
                "approvalReference": "isolated-test-approval", "ledgerPath": str(path),
                "frozenTemplateSha256s": sorted(value["templateSha256"] for value in frozen),
                "startsAt": NOW - 100, "expiresAt": NOW + 86400000,
                "maxCalls": calls, "perCourseMaxCalls": per_course, "maxNewSpendUsd": "8"}
    rate = {
        "deepseek-flash": {"currency": "USD", "inputMissPerMillion": "0.30", "outputPerMillion": "1.20"},
        "qwen-tts": {"currency": "CNY", "per10000Characters": "0.8"},
        "qwen-asr": {"currency": "CNY", "perSecond": "0.00022"},
        "qwen-image": {"currency": "CNY", "perImage": "0.5"},
        "happyhorse-video": {"currency": "CNY", "perSecond720p": "0.9"},
        "baidu-search": {"currency": "CNY", "perStandardCall": "0.036"},
    }
    urls = {"deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
            "aliyun": "https://help.aliyun.com/en/model-studio/model-pricing",
            "baidu": "https://ai.baidu.com/ai-doc/AppBuilder/Imca18xc6"}
    evidence = {"schemaVersion": PRICE_SCHEMA, "protectiveCnyPerUsd": "8",
                "fxPurpose": "budget_upper_bound_not_vendor_exchange_rate",
                "quotes": {key: {"provider": provider, "model": model, "sourceUrl": urls[vendor],
                    "sourceSnapshotSha256": digest("synthetic quote evidence: " + key),
                    "priceVersion": PRICE_VERSION, "verifiedAt": "2026-10-08T12:00:00+08:00",
                    "operatorVerified": True, "rates": rate[key]} for key, (vendor, provider, model) in REQUIRED_QUOTES.items()}}
    return frozen, approval, evidence


class FormalAuthoringTests(unittest.TestCase):
    def test_real_lesson_binding_and_complete_independent_tasks(self):
        for subject, lesson_id in (("math", "M1A01.05"), ("chinese", "ZH1B02.03")):
            with self.subTest(subject=subject):
                frozen = freeze_course(subject, run_id="freeze-test")
                validate_frozen(frozen)
                body = frozen["nativeInputTemplate"]
                contract = json.loads(body["requirement"])
                validate_generation_grade_boundary(contract)
                brief = contract["teachingBrief"]
                flow = brief["lesson"]["teachingFlow"]
                self.assertEqual(brief["course"]["skillId"], lesson_id)
                self.assertEqual(len(flow["guidedQuestionIds"]), 2)
                self.assertEqual(len(flow["independentQuestionIds"]), 5)
                self.assertEqual(len(brief["lesson"]["questions"]), 7)
                self.assertEqual(body["agentMode"], "generate")
                self.assertTrue(body["enableWebSearch"])
                self.assertFalse(body["enableTTS"])
                self.assertNotIn("paidBudget", body)
                self.assertFalse(frozen["readyForPaidDispatch"])
                self.assertFalse(frozen["privateOracle"]["publishable"])
                self.assertIsNone(frozen["privateOracle"]["providerIndependentReviewReceipt"])

    def test_native_brief_is_answer_blind_and_source_hash_locked(self):
        for subject in ("math", "chinese"):
            frozen = freeze_course(subject, run_id="blind-test")
            contract = json.loads(frozen["nativeInputTemplate"]["requirement"])
            brief = contract["teachingBrief"]
            for question in brief["lesson"]["questions"]:
                self.assertTrue(set(question).isdisjoint({"answer", "evidence", "hint", "explanation", "evaluation"}))
            self.assertEqual(brief["sourceCourseContentSha256"], frozen["privateOracle"]["sourceContentSha256"])
            self.assertEqual(digest(brief), contract["teachingBriefSha256"])
            self.assertEqual(brief["authority"]["answerContractProvided"], False)

    def test_math_maximum_is_five_and_chinese_single_new_target(self):
        math = freeze_course("math", run_id="scopes")
        content = json.loads(math["sourceCourse"]["content_json"])
        self.assertTrue(all(q["type"] == "tap_objects" and len(q["objects"]) == 5 for q in content["questions"]))
        contract = json.loads(math["nativeInputTemplate"]["requirement"])
        self.assertEqual(contract["difficultyPolicy"]["lessonScope"]["constraints"]["maximumNumber"], 5)
        self.assertEqual(contract["difficultyPolicy"]["lessonScope"]["constraints"]["allowedOperations"], [])
        self.assertEqual(contract["gradeBoundary"]["constraints"],
                         contract["difficultyPolicy"]["lessonScope"]["constraints"])
        self.assertEqual(contract["gradeBoundary"]["constraints"]["maximumNumber"], 5)
        self.assertEqual(digest(contract["gradeBoundary"]), contract["gradeBoundarySha256"])
        self.assertNotIn("constraints", contract["teachingBrief"]["lesson"])
        chinese = freeze_course("chinese", run_id="scopes")
        source = json.loads(chinese["sourceCourse"]["content_json"])
        for question in source["questions"]:
            self.assertEqual(next(c["label"] for c in question["choices"] if c["id"] == question["answer"]), "天")
        self.assertIn("不是完整天地人", chinese["scope"])

    def test_candidate_constraints_are_registered_structural_authority_not_prompt_text(self):
        from integrations.openmaic_formal_media import PLAYFUL_PROFESSIONAL_POLICY, FLASH_CANDIDATE_PROFESSIONAL_POLICY
        from integrations.openmaic_formal_pedagogy import grade_boundary_fields, registered_grade_boundary
        from content.progressive_curriculum import lesson_by_id
        from services.progressive_course_generation import progressive_runtime_teaching_brief
        for subject in ("math", "chinese"):
            frozen = freeze_course(subject, run_id="structured-constraints-test")
            generation = json.loads(frozen["nativeInputTemplate"]["requirement"])
            course = frozen["sourceCourse"]
            brief, brief_sha, _source = progressive_runtime_teaching_brief(course)
            self.assertEqual(generation["teachingBrief"], brief)
            self.assertEqual(generation["teachingBriefSha256"], brief_sha)
            expected = lesson_by_id(course["node_code"])["constraints"]
            self.assertEqual(generation["gradeBoundary"]["constraints"], expected)
            old = grade_boundary_fields(course, PLAYFUL_PROFESSIONAL_POLICY)
            self.assertNotIn("constraints", old["gradeBoundary"])
            self.assertEqual(old["gradeBoundary"], registered_grade_boundary(
                grade_code=course["grade_code"], subject=subject, skill_id=course["node_code"]))
            self.assertNotEqual(old["gradeBoundarySha256"], generation["gradeBoundarySha256"])
            self.assertEqual(digest(frozen["nativeInputTemplate"]), frozen["templateSha256"])
            plan = select_formal_skills(teaching_brief=brief, grade_boundary=generation["gradeBoundary"],
                grade_boundary_sha256=generation["gradeBoundarySha256"],
                model_policy_id=FLASH_CANDIDATE_PROFESSIONAL_POLICY["modelPolicyId"])
            self.assertEqual(plan["gradeBoundarySha256"], generation["gradeBoundarySha256"])
            generation["professionalCreationPolicy"] = PLAYFUL_PROFESSIONAL_POLICY
            with self.assertRaises(ValueError): validate_generation_grade_boundary(generation, course)

    def test_candidate_missing_or_forged_constraints_fail_even_with_recomputed_hashes(self):
        frozen = freeze_course("math", run_id="forged-constraints-test")
        original = json.loads(frozen["nativeInputTemplate"]["requirement"])
        mutations = (
            lambda g: g["gradeBoundary"].pop("constraints"),
            lambda g: g["gradeBoundary"]["constraints"].update(maximumNumber=6),
            lambda g: g["gradeBoundary"]["constraints"].update(maximumNumber=None),
            lambda g: g["gradeBoundary"]["constraints"].update(maximumNumber=True),
            lambda g: g["gradeBoundary"]["constraints"].update(unregisteredOverride=5),
            lambda g: g["teachingBrief"]["difficultyPolicy"]["lessonScope"]["constraints"].update(maximumNumber=6),
        )
        for mutation in mutations:
            generation = deepcopy(original)
            mutation(generation)
            difficulty = generation["teachingBrief"]["difficultyPolicy"]
            difficulty["policySha256"] = digest({k: v for k, v in difficulty.items() if k != "policySha256"})
            generation["difficultyPolicy"] = deepcopy(difficulty)
            generation["teachingBriefSha256"] = digest(generation["teachingBrief"])
            generation["gradeBoundarySha256"] = digest(generation["gradeBoundary"])
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_generation_grade_boundary(generation, frozen["sourceCourse"])
            with self.subTest(parser=mutation), self.assertRaises(ValueError):
                select_formal_skills(teaching_brief=generation["teachingBrief"],
                    grade_boundary=generation["gradeBoundary"], grade_boundary_sha256=generation["gradeBoundarySha256"],
                    model_policy_id=generation["professionalCreationPolicy"]["modelPolicyId"])

    def test_scope_oracle_hash_and_fake_binding_changes_are_rejected(self):
        frozen = freeze_course("math", run_id="mutations")
        for mutation in (
            lambda f: f.update(productionLessonId="M1A04.01"),
            lambda f: f["nativeInputTemplate"].update(paidBudget={"authorizationId": "0" * 64}),
            lambda f: f["privateOracle"]["answers"].clear(),
            lambda f: f.update(readyForPaidDispatch=True),
        ):
            changed = deepcopy(frozen)
            mutation(changed)
            with self.assertRaises(ValueError):
                validate_frozen(changed)

    def test_write_is_new_file_only_and_private(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "new.json"
            write_json_new(path, {"ok": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                write_json_new(path, {"ok": False})
            self.assertEqual(json.loads(path.read_text()), {"ok": True})


class FormalIsolatedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "acceptance.sqlite3"
        self.frozen, self.approval, self.evidence = fixtures(self.path)
        self.plan = build_plan(self.frozen, approval=self.approval, price_evidence=self.evidence, now=NOW)

    def init(self):
        self.service, self.bindings = initialize_ledger(self.path, self.plan, now=NOW)
        self.auth = self.bindings["math"]["authorizationId"]

    def reserve(self, name="call-a", **extra):
        args = {"authorization_id": self.auth, "dispatch_id": name,
                "request_sha256": digest(name), "price_key": "deepseek-v4.1-flash-peak",
                "max_units": {"calls": 1, "input_tokens": 1000, "output_tokens": 1000}}
        args.update(extra)
        return self.service.reserve(**args)

    def dispatch(self, row, service=None):
        return (service or self.service).dispatch(authorization_id=row["authorizationId"],
            reservation_id=row["reservationId"], request_sha256=row["requestSha256"])

    def test_preflight_has_no_database_side_effect_and_rejects_missing_proofs(self):
        self.assertFalse(self.path.exists())
        for field in ("humanAuthorizationSha256", "humanAuthorizationVerified", "ledgerPath"):
            bad = deepcopy(self.approval)
            bad.pop(field)
            with self.assertRaises(ValueError):
                build_plan(self.frozen, approval=bad, price_evidence=self.evidence, now=NOW)
        for key in REQUIRED_QUOTES:
            bad = deepcopy(self.evidence)
            bad["quotes"].pop(key)
            with self.assertRaises(ValueError):
                build_plan(self.frozen, approval=self.approval, price_evidence=bad, now=NOW)
        self.assertFalse(self.path.exists())

    def test_production_alias_exact_prices_cny_upper_bound_and_unknown_holds(self):
        self.init()
        context = self.service.authorization_context(authorization_id=self.auth)
        price = context["prices"]["deepseek-v4.1-flash-peak"]
        self.assertEqual((price["provider"], price["model"]), ("deepseek", "deepseek-flash"))
        self.assertEqual(price["microsPerMillionUnits"], {"calls": 0, "input_tokens": 2400000, "output_tokens": 9600000})
        row = self.reserve()
        self.assertEqual(row["maxUnits"]["money_micros"], 12000)
        self.assertTrue(self.dispatch(row)["dispatchAllowed"])
        unknown = self.service.unknown(authorization_id=self.auth, reservation_id=row["reservationId"], reason_code="offline-test-timeout")
        self.assertEqual(unknown["state"], "unknown")
        self.assertEqual(unknown["maxUnits"]["money_micros"], 12000)
        self.assertIsNone(unknown["actualUnits"])
        with self.assertRaises(ApiError):
            self.service.release(authorization_id=self.auth, reservation_id=row["reservationId"], reason_code="no-refund")
        restarted = open_ledger(self.path, expected_plan_sha256=digest(self.plan), clock=lambda: NOW)
        self.assertFalse(self.dispatch(row, restarted)["dispatchAllowed"])
        self.assertEqual(restarted.status()["states"], {"unknown": 1})

    def test_real_structured_and_agent_output_caps_are_accepted(self):
        self.init()
        for name, output in (("structured", 65536), ("agent", 16384), ("quality", 8000), ("visual", 8192)):
            row = self.reserve(name, max_units={"calls": 1, "input_tokens": 90000, "output_tokens": output})
            self.assertEqual(row["maxUnits"]["output_tokens"], output)
            self.service.release(authorization_id=self.auth, reservation_id=row["reservationId"], reason_code="offline-preflight")
        with self.assertRaises(ValueError):
            self.reserve("outside-reviewed-formal-cap", max_units={"calls": 1, "input_tokens": 90000, "output_tokens": 393216})

    def test_exact_scope_binding_and_no_budget_reset_or_copied_ledger(self):
        self.init()
        body = bind_native_input(self.frozen[0], budget_service=self.service, authorization_id=self.auth)
        self.assertEqual(body["paidBudget"], self.bindings["math"])
        with self.assertRaises(ValueError):
            bind_native_input(self.frozen[1], budget_service=self.service, authorization_id=self.auth)
        with self.assertRaises(FileExistsError):
            initialize_ledger(self.path, self.plan, now=NOW)
        copied = Path(self.directory.name) / "copy.sqlite3"
        copied.write_bytes(self.path.read_bytes())
        with self.assertRaises(ValueError):
            open_ledger(copied, expected_plan_sha256=digest(self.plan), clock=lambda: NOW)
        with self.assertRaises(ValueError):
            initialize_ledger(Path(self.directory.name) / "other.sqlite3", self.plan, now=NOW)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_shared_sql_lock_allows_only_one_dispatch_across_services(self):
        self.init()
        row = self.reserve()
        second = open_ledger(self.path, expected_plan_sha256=digest(self.plan), clock=lambda: NOW)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outputs = list(executor.map(lambda service: self.dispatch(row, service), [self.service, second]))
        self.assertEqual(sum(result["dispatchAllowed"] for result in outputs), 1)

    def test_failed_unknown_and_settled_calls_all_consume_global_cap(self):
        self.approval.update(maxCalls=2, perCourseMaxCalls=2)
        self.plan = build_plan(self.frozen, approval=self.approval, price_evidence=self.evidence, now=NOW)
        self.init()
        a = self.reserve("a")
        self.dispatch(a)
        self.service.unknown(authorization_id=self.auth, reservation_id=a["reservationId"], reason_code="timeout")
        b = self.reserve("b", authorization_id=self.bindings["chinese"]["authorizationId"])
        self.dispatch(b)
        self.service.settle(authorization_id=b["authorizationId"], reservation_id=b["reservationId"],
            actual_units={"calls": 1, "input_tokens": 50, "output_tokens": 20}, provider_request_id="offline-receipt",
            evidence_sha256=digest("offline synthetic failed response receipt"))
        with self.assertRaises(ApiError) as caught:
            self.reserve("c")
        self.assertIn("limit", caught.exception.code)

    def test_auth_expiry_stays_closed_after_reopen(self):
        self.init()
        reopened = open_ledger(self.path, expected_plan_sha256=digest(self.plan), clock=lambda: self.approval["expiresAt"])
        with self.assertRaises(ApiError):
            reopened.authorization_context(authorization_id=self.auth)

    def test_http_production_tokenguard_loopback_no_grant_issuance(self):
        self.init()
        token = "isolated-test-token-" + "x" * 48
        client = create_app(self.service, token=token).test_client()
        payload = {"authorizationId": self.auth}
        self.assertEqual(client.post("/internal/learning/budget/context", json=payload).status_code, 401)
        headers = {"X-Mira-Internal-Token": token, "X-Mira-Internal-Source": "offline-acceptance-test"}
        result = client.post("/internal/learning/budget/context", json=payload, headers=headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.assertEqual(client.post("/internal/learning/budget/context", json=payload, headers=headers,
            environ_base={"REMOTE_ADDR": "192.0.2.1"}).status_code, 403)
        self.assertEqual(client.post("/internal/learning/budget/context", json={**payload, "priceKeys": []}, headers=headers).status_code, 400)
        self.assertEqual(client.post("/internal/learning/budget/create_authorization", json=payload, headers=headers).status_code, 404)
        with self.service.repository.database.transaction() as conn:
            rows = conn.execute("SELECT accepted,reason FROM audit_events ORDER BY created_at,id").fetchall()
            self.assertEqual(len(rows), 4)
            self.assertTrue(any(row["reason"] == "invalid_internal_token" or row["reason"] == "missing_internal_token" for row in rows))
            self.assertTrue(any(row["reason"] == "source_not_allowed" for row in rows))

    def test_plan_caps_scope_prices_and_global_switch_cannot_drift(self):
        for mutation in (
            lambda p: p["policy"].update(aggregateLimitsEnabled=False),
            lambda p: p["policy"]["limits"]["global"]["day"].update(calls=99),
            lambda p: p["approval"].update(maxCalls=99),
            lambda p: p["policy"]["prices"]["deepseek-v4.1-flash-peak"].update(model="deepseek-v4-flash"),
        ):
            changed = deepcopy(self.plan)
            mutation(changed)
            with self.assertRaises(ValueError):
                validate_plan(changed)


if __name__ == "__main__":
    unittest.main()
