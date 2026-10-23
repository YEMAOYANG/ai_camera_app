from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from services.course_file_writer import CourseFileWriteError, _quality_sha
from tests import test_course_file_writer as fixtures

raw, sha = fixtures.raw, fixtures.sha


class CourseFileReviewRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CourseFileWriterTest()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.f.writer.root = Path(self.tmp.name).resolve()
        self.identity = {"ownerId": "owner-test", "sessionId": "session-test", "stageId": "stage-test",
            "gradeBoundarySha256": "d" * 64, "selectionPlanSha256": "e" * 64, "teachingBriefSha256": "f" * 64}
        self.snapshot = {"stage": {"id": "stage-test"}, "scenes": [{"id": "scene-1"}]}
        self.snapshot_sha = _quality_sha(self.snapshot)
        self.folder = Path("openmaic-runtime/.runtime/OpenMAIC/data/formal-quality-reviews") / _quality_sha(self.identity)
        self.ledger = (self.folder / "attempts.json").as_posix()
        self.result = (self.folder / (self.snapshot_sha + ".json")).as_posix()
        self.browser = (self.folder / (self.snapshot_sha + "-browser.json")).as_posix()
        self.input = (self.folder / (self.snapshot_sha + "-input.json")).as_posix()
        self.original_attempt = {"snapshotSha256": self.snapshot_sha, "status": "needs_revision", "startedAt": 100}
        self.claimed_attempt = {**self.original_attempt, "browserRecheckedAt": 200}
        self.original_result = {"snapshotSha256": self.snapshot_sha, "status": "needs_revision",
            "issues": [{"problem": "Browser check probe failed", "sceneId": "scene-1", "repair": "修复实际探针"}],
            "reviewPromptVersion": "fixture-review-v1"}
        self.original_browser = [{"sceneId": "scene-1", "sceneSha256": "a" * 64,
            "viewport": {"width": 1280, "height": 720}, "screenshotSha256": "b" * 64,
            "domSha256": "c" * 64, "probeCount": 1, "passed": False}]
        self.good_browser = [{**self.original_browser[0], "passed": True, "screenshotSha256": "d" * 64}]
        self.bodies, self.versions = {}, {}
        for path, value in ((self.ledger, [self.original_attempt]), (self.result, self.original_result),
                            (self.browser, self.original_browser), (self.input, {**self.identity, "snapshot": self.snapshot})):
            body = raw(value)
            self.bodies[path] = body
            self.versions[(path, sha(body))] = body
            self.f.register(path=path, body=body)
        self.rejection = (self.folder / (self.snapshot_sha + "-browser-rejection-150.json")).as_posix()
        self.local(self.rejection, {"result": self.original_result, "browser": self.original_browser,
                                   "attempt": self.original_attempt})
        def read(path, expected=None):
            if expected is not None:
                return self.versions[(path, expected)]
            entry = self.f.repo.resolve(path, self.f.storage)
            return self.versions[(path, entry["sha256"])] if entry else self.bodies[path]
        self.f.read.side_effect = read
        def upload(**options):
            self.versions[(self.writing, sha(options["raw"]))] = options["raw"]
            return {"kind": "object", "objectKey": options["object_key"], "etag": '"verified-version"'}
        self.f.uploader.upload.side_effect = upload

    def local(self, path, value):
        body = value if isinstance(value, bytes) else raw(value)
        self.bodies[path] = body
        target = self.f.writer.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)

    def write(self, path, value):
        body = value if isinstance(value, bytes) else raw(value)
        entry = self.f.repo.resolve(path, self.f.storage)
        self.writing = path
        return self.f.writer.write_bytes(path, body, expected_sha256=entry["sha256"])

    def claim(self):
        return self.write(self.ledger, [self.claimed_attempt])

    def passed_result(self):
        dispatch = (self.folder / (self.snapshot_sha + "-provider-dispatch.json")).as_posix()
        response = (self.folder / (self.snapshot_sha + "-provider.json")).as_posix()
        self.local(dispatch, {"snapshotSha256": self.snapshot_sha, "startedAt": 201})
        self.local(response, {"providerRequestIdHash": "9" * 64, "content": "original verified response"})
        receipt = {"schemaVersion": "mira.openmaic.teaching-quality-receipt.v1", "policyId": "mira-primary-quality.v1",
            "status": "passed", "snapshotSha256": self.snapshot_sha,
            **{k: self.identity[k] for k in ("sessionId", "stageId", "gradeBoundarySha256", "selectionPlanSha256", "teachingBriefSha256")},
            "renderChecks": self.good_browser, "review": {"requestIdHash": "9" * 64}}
        receipt["receiptSha256"] = _quality_sha(receipt)
        return {"status": "passed", "snapshotSha256": self.snapshot_sha, "issues": [],
                "receipt": receipt, "reviewPromptVersion": "fixture-review-v1"}

    def test_actual_native_write_order_claim_same_input_browser_result_and_terminal_ledger(self):
        originals = {path: self.f.repo.resolve(path, self.f.storage)["sha256"] for path in (self.ledger, self.browser, self.result)}
        rejection = self.bodies[self.rejection]
        self.claim()
        self.write(self.input, self.bodies[self.input])  # unchanged Native input is a no-op
        self.write(self.browser, self.good_browser)
        self.write(self.result, self.passed_result())
        self.write(self.ledger, [{**self.claimed_attempt, "status": "passed"}])
        self.assertEqual(self.f.uploader.upload.call_count, 4)
        for path, original_sha in originals.items():
            self.assertIsNotNone(self.f.repo.resolve(path, self.f.storage, original_sha))
            self.assertNotEqual(self.f.repo.resolve(path, self.f.storage)["sha256"], original_sha)
        self.assertEqual(self.bodies[self.rejection], rejection)
        self.assertEqual(self.f.repo.head_scope(self.ledger, self.f.storage)["metadata"]["writePolicy"]["kind"], "browser_recheck_completed")

    def test_claim_refuses_prior_provider_dispatch_response_or_visual_evidence(self):
        for suffix in ("-provider-dispatch.json", "-provider.json", "-visual.json"):
            with self.subTest(suffix=suffix):
                path = (self.folder / (self.snapshot_sha + suffix)).as_posix()
                self.local(path, {"protected": "original"})
                with self.assertRaisesRegex(CourseFileWriteError, "already_dispatched"):
                    self.claim()
                (self.f.writer.root / path).unlink()
                del self.bodies[path]
        self.f.uploader.upload.assert_not_called()

    def test_claim_requires_exact_original_rejection_bundle_and_unchanged_snapshot_identity(self):
        self.local(self.rejection, {"result": {**self.original_result, "issues": []},
            "browser": self.original_browser, "attempt": self.original_attempt})
        with self.assertRaisesRegex(CourseFileWriteError, "rejection_archive_missing"):
            self.claim()
        self.local(self.rejection, {"result": self.original_result, "browser": self.original_browser,
            "attempt": self.original_attempt})
        changed = {**self.identity, "snapshot": {"changed": True}}
        self.versions[(self.input, sha(self.bodies[self.input]))] = raw(changed)
        with self.assertRaisesRegex(CourseFileWriteError, "identity_mismatch"):
            self.claim()
        self.f.uploader.upload.assert_not_called()

    def test_browser_or_result_cannot_advance_without_an_accepted_cas_claim(self):
        for path, value in ((self.browser, self.good_browser), (self.result, self.passed_result())):
            with self.subTest(path=path), self.assertRaisesRegex(CourseFileWriteError, "claim_missing"):
                self.write(path, value)
        self.f.uploader.upload.assert_not_called()

    def test_input_mutation_and_paid_provider_originals_remain_immutable(self):
        self.claim()
        with self.assertRaisesRegex(CourseFileWriteError, "write_forbidden"):
            self.write(self.input, {**self.identity, "snapshot": self.snapshot, "added": "not original"})
        path = (self.folder / (self.snapshot_sha + "-provider.json")).as_posix()
        self.f.register(path=path, body=raw({"original": "provider response"}))
        self.versions[(path, sha(raw({"original": "provider response"})))] = raw({"original": "provider response"})
        with self.assertRaisesRegex(CourseFileWriteError, "write_forbidden"):
            self.write(path, {"replacement": "forbidden"})
        self.assertEqual(self.f.uploader.upload.call_count, 1)

    def test_final_pass_must_match_new_dispatch_and_original_input_render_evidence(self):
        self.claim()
        self.write(self.browser, self.good_browser)
        result = self.passed_result()
        result["receipt"]["stageId"] = "stage-other"
        result["receipt"]["receiptSha256"] = _quality_sha({k: v for k, v in result["receipt"].items() if k != "receiptSha256"})
        with self.assertRaises(CourseFileWriteError):
            self.write(self.result, result)
        with self.assertRaises(CourseFileWriteError):
            self.write(self.ledger, [{**self.claimed_attempt, "status": "passed"}])
        self.assertEqual(self.f.uploader.upload.call_count, 2)

    def test_previously_failed_paid_attempt_is_never_relabelled_as_browser_only(self):
        changed = {**self.original_attempt, "status": "failed"}
        self.f.repo.register_scope({**self.f.meta, "scopeKey": "d" * 64}, [{"sourcePath": self.ledger,
            "sha256": sha(raw([changed])), "byteSize": len(raw([changed])), "mimeType": "application/json",
            "locator": {"kind": "object", "objectKey": "原始/失败记录.json", "etag": '"failed"'}}], self.f.storage)
        self.versions[(self.ledger, sha(raw([changed])))] = raw([changed])
        with self.assertRaises(CourseFileWriteError):
            self.write(self.ledger, [{**changed, "status": "passed", "browserRecheckedAt": 200}])
        self.f.uploader.upload.assert_not_called()

    def test_source_response_change_during_upload_prevents_head_activation(self):
        self.claim()
        self.write(self.browser, self.good_browser)
        result = self.passed_result()
        upload = self.f.uploader.upload.side_effect
        response = (self.folder / (self.snapshot_sha + "-provider.json")).as_posix()
        before = self.f.repo.resolve(self.result, self.f.storage)["sha256"]
        def changed(**options):
            descriptor = upload(**options)
            self.local(response, {"providerRequestIdHash": "9" * 64, "content": "different response bytes"})
            return descriptor
        self.f.uploader.upload.side_effect = changed
        with self.assertRaises(CourseFileWriteError):
            self.write(self.result, result)
        self.assertEqual(self.f.repo.resolve(self.result, self.f.storage)["sha256"], before)

    def test_approved_grant_appends_attempt_and_promotes_only_its_preserved_result(self):
        original = deepcopy(self.original_attempt)
        grant = {"schemaVersion": "mira.formal-quality-review-grant.v1", "grantId": "7" * 64,
            "approvalRef": "explicit-operator-approval", "maxAdditionalReviews": 1,
            "priorAttemptsSha256": _quality_sha([original]), "reviewIdentitySha256": self.folder.name,
            "sessionId": self.identity["sessionId"], "stageId": self.identity["stageId"], "snapshotSha256": self.snapshot_sha}
        prefix = self.snapshot_sha + "-grant-" + _quality_sha(grant)
        claim = {"snapshotSha256": self.snapshot_sha, "status": "started", "startedAt": 300,
            "grantId": grant["grantId"], "approvalRef": grant["approvalRef"], "artifactPrefix": prefix,
            "priorAttemptsSha256": grant["priorAttemptsSha256"]}
        grant_path = (self.folder / "operator-review-grant.json").as_posix()
        self.local(grant_path, {**grant, "reservedAt": 200})
        self.write(self.ledger, [original, claim])
        result = self.passed_result()
        for suffix, value in (("-previous-result.json", self.original_result), ("-input.json", {**self.identity, "snapshot": self.snapshot}),
                              ("-browser.json", self.good_browser), ("-provider-dispatch.json", {"snapshotSha256": self.snapshot_sha, "startedAt": 301}),
                              ("-provider.json", {"providerRequestIdHash": "9" * 64, "content": "original response"}), (".json", result)):
            self.local((self.folder / (prefix + suffix)).as_posix(), value)
        self.write(self.result, result)
        self.write(self.ledger, [original, {**claim, "status": "passed"}])
        self.assertEqual(self.f.uploader.upload.call_count, 3)
        self.assertEqual(self.original_attempt, original)
        self.assertIsNotNone(self.f.repo.resolve(self.result, self.f.storage, sha(raw(self.original_result))))

    def test_visual_predispatch_uses_new_prefix_keeps_failed_attempt_and_requires_original_claim(self):
        original = {"snapshotSha256": self.snapshot_sha, "status": "failed", "startedAt": 100}
        self.f.repo.register_scope({**self.f.meta, "scopeKey": "d" * 64}, [{"sourcePath": self.ledger,
            "sha256": sha(raw([original])), "byteSize": len(raw([original])), "mimeType": "application/json",
            "locator": {"kind": "object", "objectKey": "原始/失败记录.json", "etag": '"failed"'}}], self.f.storage)
        self.versions[(self.ledger, sha(raw([original])))] = raw([original])
        self.f.db.raw.execute("DELETE FROM course_storage_heads WHERE source_path_sha256=?", (sha(self.result.encode()),))
        self.f.db.raw.commit()
        checks = [{"sceneId": "scene-" + str(i), "viewport": {"width": 1280, "height": 720},
                   "passed": True, "screenshotSha256": "5" * 64} for i in range(16)]
        browser_raw = raw(checks)
        self.f.repo.register_scope({**self.f.meta, "scopeKey": "e" * 64}, [{"sourcePath": self.browser,
            "sha256": sha(browser_raw), "byteSize": len(browser_raw), "mimeType": "application/json",
            "locator": {"kind": "object", "objectKey": "原始/浏览器证据.json", "etag": '"browser"'}}], self.f.storage)
        self.versions[(self.browser, sha(browser_raw))] = browser_raw
        source_snapshot = "7" * 64
        source_visual = {"status": "passed", "snapshotSha256": source_snapshot}
        source_visual["receiptSha256"] = _quality_sha(source_visual)
        self.local((self.folder / (source_snapshot + "-visual.json")).as_posix(), source_visual)
        self.local((self.folder / (source_snapshot + "-browser.json")).as_posix(), checks)
        recovery = Path("openmaic-runtime/.runtime/OpenMAIC/data/formal-saved-stage-recoveries/omformal_fixture")
        identity = {"sourceJobSha256": "4" * 64, "sourceSnapshotSha256": source_snapshot,
            "repairSnapshotSha256": self.snapshot_sha, "sessionId": self.identity["sessionId"], "stageId": self.identity["stageId"]}
        prior_claim = {**identity, "createdAt": "1970-01-01T00:00:00.075Z"}
        claim_path = (recovery / ("complete-" + self.snapshot_sha + ".claim")).as_posix()
        self.local(claim_path, prior_claim)
        log = "original durable rejection MIRA_PAID_BUDGET_DISPATCH_ALREADY_CLAIMED"
        evidence = {"schemaVersion": "mira.english1.visual-predispatch-recovery.v1", "jobId": recovery.name,
            "identity": identity, "authorizationId": "8" * 64, "priorAttemptsSha256": _quality_sha([original]),
            "priorInputSha256": sha(self.bodies[self.input]), "priorClaimSha256": sha(self.bodies[claim_path]),
            "error": "MIRA_PAID_BUDGET_DISPATCH_ALREADY_CLAIMED", "failureLog": log, "failureLogSha256": sha(log.encode()),
            "browserSha256": _quality_sha(checks), "sourceVisualReceiptSha256": source_visual["receiptSha256"],
            "collisionReservation": {"authorization_id": "8" * 64, "state": "settled", "dispatched_at": 10, "settled_at": 20}}
        evidence_sha = _quality_sha(evidence)
        appended = {"snapshotSha256": self.snapshot_sha, "status": "started", "startedAt": 300,
            "artifactPrefix": self.snapshot_sha + "-predispatch-" + evidence_sha,
            "predispatchRecoverySha256": evidence_sha, "priorAttemptsSha256": evidence["priorAttemptsSha256"]}
        with self.assertRaisesRegex(CourseFileWriteError, "predispatch_not_proven"):
            self.write(self.ledger, [original, appended])
        self.f.uploader.upload.assert_not_called()
        self.local((recovery / ("complete-" + self.snapshot_sha + "-visual-predispatch.claim")).as_posix(),
            {**evidence, "evidenceSha256": evidence_sha, "pid": 1, "createdAt": "1970-01-01T00:00:00.200Z"})
        result = self.write(self.ledger, [original, appended])
        self.assertEqual(result["sha256"], sha(raw([original, appended])))
        self.assertIsNotNone(self.f.repo.resolve(self.ledger, self.f.storage, sha(raw([original]))))
        self.assertEqual(original["status"], "failed")


if __name__ == "__main__":
    unittest.main()
