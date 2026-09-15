"""Receipt consumption against isolated SQL; no live stop, apply or Provider."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from content.learning_budget_policy import LearningBudgetPolicy, UNITS, canonical, digest
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService
from tests.test_learning_budget import IsolatedDatabase, test_policy


EVENT = "transport_terminal_confirmed"


class TransportTerminalAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = IsolatedDatabase(Path(self.directory.name) / "budget.db")
        self.now = 100000
        self.raw = test_policy()
        self.raw["aggregateLimitsEnabled"] = False
        self.raw["limits"]["global"]["maxInflightCalls"] = 4
        self.scope = {"purpose": "production", "gradeCode": "primary_6", "subject": "math",
            "courseId": "catalog-item:synthetic-item", "courseVersion": "frozen-version",
            "productionJobId": "synthetic-item", "userId": None, "sessionId": None,
            "approvalReference": "existing-approval"}
        self.auth = digest({"schema": "mira.catalog-paid-budget.v1", "scope": self.scope})
        self.other_auth = digest("other-original-grant")
        self.service = self.make_service()
        for identity in (self.auth, self.other_auth):
            self.service.create_authorization(authorization_id=identity, scope=self.scope,
                max_units=dict.fromkeys(UNITS, 1000000), price_keys=["fake-text-v1"],
                expires_at=self.now + 100000)
        self.old = []
        for index in range(4):
            row = self.reserve(f"old-{index}")
            self.dispatch(row)
            self.service.unknown(reservation_id=row["reservationId"], authorization_id=self.auth,
                reason_code="provider_result_unknown")
            self.old.append(row)
        self.now += 100
        self.before = self.rows()
        self.original_ids = {row["id"] for row in self.before}

    def make_service(self, raw=None):
        service = LearningBudgetService(self.database, policy=LearningBudgetPolicy(raw or self.raw),
            clock=lambda: self.now)
        service._catalog_production_scope = Mock(return_value=(self.scope, True))
        return service

    def reserve(self, name, *, auth=None, service=None):
        return (service or self.service).reserve(authorization_id=auth or self.auth,
            dispatch_id=name, request_sha256=digest(name), price_key="fake-text-v1",
            max_units={"calls": 1, "input_tokens": 100, "output_tokens": 50})

    def dispatch(self, row):
        return self.service.dispatch(reservation_id=row["reservationId"],
            authorization_id=row["authorizationId"], request_sha256=row["requestSha256"])

    def rows(self):
        with self.database.transaction() as conn:
            return conn.execute("SELECT * FROM learning_budget_reservations ORDER BY id").fetchall()

    def assert_blocked(self, operation, code="inflight_limit"):
        with self.assertRaises(ApiError) as caught:
            operation()
        self.assertEqual(caught.exception.code, "learning_budget_" + code)

    def install_receipts(self):
        # This is a synthetic trusted-event fixture, not the real operator apply.
        with self.database.transaction() as conn:
            claims = []
            for row in self.before:
                authority = conn.execute("SELECT * FROM learning_budget_authorizations WHERE id=?",
                    (row["authorization_id"],)).fetchone()
                claims.append({"reservationId": row["id"], "reservationSnapshotSha256": digest(row),
                    "authorizationId": row["authorization_id"], "authorizationSnapshotSha256": digest(authority),
                    "requestIdentitySha256": row["request_identity_sha256"], "dispatchedAt": row["dispatched_at"]})
            plan = {"schemaVersion": "mira.learning.transport-terminal-plan.v1",
                "confirmationKind": "managed_deployment_processes_exited",
                "scope": "local_transport_concurrency_only",
                "sourceAuditSha256": "cebd0b3f1d491452525e4707ff0afccd858955a38af858693b1e370d89d59267",
                "stopEvidenceSha256": digest("confirmed-old-process-exit"), "reservationClaims": claims,
                "localTransportEndedAt": self.now - 1, "approvalReference": "reviewed-synthetic-stop"}
            for claim in claims:
                evidence = {"schemaVersion": "mira.learning.transport-terminal-receipt.v1",
                    "planSha256": digest(plan), "reservationId": claim["reservationId"],
                    "batchSha256": digest(claims), "plan": plan}
                self.service.repository.event(conn, claim["reservationId"], EVENT, evidence, self.now)
        return plan

    def terminal_events(self):
        with self.database.transaction() as conn:
            return conn.execute("SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id", (EVENT,)).fetchall()

    def test_verified_history_keeps_money_and_allows_at_most_four_actual_calls(self):
        self.install_receipts()
        first = self.reserve("active-0", auth=self.other_auth)
        self.assertTrue(self.dispatch(first)["dispatchAllowed"])
        for index in range(1, 4):
            self.reserve(f"active-{index}")
        self.assert_blocked(lambda: self.reserve("fifth-active"))
        self.assertEqual([row for row in self.rows() if row["id"] in self.original_ids], self.before)
        self.assertEqual(len(self.terminal_events()), 4)

    def test_absent_partial_malformed_duplicate_and_forged_batches_keep_holds(self):
        self.assert_blocked(lambda: self.reserve("no-receipts"))
        self.install_receipts()
        original = self.terminal_events()
        for mutation in ("partial", "malformed", "duplicate", "hash", "identity"):
            with self.subTest(mutation=mutation):
                with self.database.transaction() as conn:
                    conn.execute("DELETE FROM learning_budget_events WHERE event_type=?", (EVENT,))
                    for index, event in enumerate(original):
                        if mutation == "partial" and index == 3:
                            continue
                        evidence = json.loads(event["evidence_json"])
                        if index == 0 and mutation in {"hash", "identity"}:
                            evidence["planSha256" if mutation == "hash" else "reservationId"] = digest("wrong")
                        encoded = "{" if index == 0 and mutation == "malformed" else canonical(evidence)
                        conn.execute("INSERT INTO learning_budget_events (reservation_id,event_type,evidence_json,created_at) VALUES (?,?,?,?)",
                            (event["reservation_id"], EVENT, encoded, self.now))
                        if mutation == "duplicate" and index == 0:
                            self.service.repository.event(conn, event["reservation_id"], EVENT, evidence, self.now)
                self.assert_blocked(lambda: self.reserve("bad-" + mutation))

    def test_changed_reservation_or_authority_invalidates_receipts(self):
        self.install_receipts()
        with self.database.transaction() as conn:
            row = self.before[0]
            conn.execute("UPDATE learning_budget_reservations SET request_sha256=? WHERE id=?",
                (digest("different-request"), row["id"]))
        self.assert_blocked(lambda: self.reserve("changed-request"))
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_budget_reservations SET request_sha256=? WHERE id=?",
                (row["request_sha256"], row["id"]))
            conn.execute("UPDATE learning_budget_authorizations SET policy_sha256=? WHERE id=?",
                (digest("changed-authority"), self.auth))
        self.assert_blocked(lambda: self.reserve("changed-authority", auth=self.other_auth))

    def test_future_unknown_without_its_own_receipt_still_counts(self):
        self.install_receipts()
        new = self.reserve("future-unknown")
        self.dispatch(new)
        self.service.unknown(reservation_id=new["reservationId"], authorization_id=self.auth,
            reason_code="provider_result_unknown")
        for index in range(3):
            self.reserve(f"active-{index}")
        self.assert_blocked(lambda: self.reserve("no-auto-release"))
        self.assertEqual(sum(row["state"] == "unknown" for row in self.rows()), 5)

    def test_strict_policy_never_consumes_terminal_receipts(self):
        self.install_receipts()
        raw = deepcopy(self.raw)
        raw["aggregateLimitsEnabled"] = True
        self.service = self.make_service(raw)
        with patch("services.learning_transport_terminal_reconciliation.verified_transport_terminal_reservation_ids",
                side_effect=AssertionError("strict accounting must not use transport receipts")):
            self.assert_blocked(lambda: self.reserve("strict-fifth"))

    def test_dispatch_rechecks_batch_and_leaves_unclaimed_reservation_intact(self):
        self.install_receipts()
        row = self.reserve("admitted-before-proof-loss")
        with self.database.transaction() as conn:
            conn.execute("DELETE FROM learning_budget_events WHERE event_type=?", (EVENT,))
        self.assert_blocked(lambda: self.dispatch(row))
        actual = next(r for r in self.rows() if r["id"] == row["reservationId"])
        self.assertEqual(actual["state"], "reserved")
        self.assertIsNone(actual["dispatched_at"])

    def test_later_real_settlement_does_not_reactivate_remaining_unknowns(self):
        self.install_receipts()
        row = self.old[0]
        self.service.settle(reservation_id=row["reservationId"], authorization_id=self.auth,
            actual_units={"calls": 1, "input_tokens": 20, "output_tokens": 10},
            provider_request_id=None, evidence_sha256=digest("actual-measured-usage"))
        for index in range(4):
            self.reserve(f"after-legitimate-settlement-{index}")
        self.assert_blocked(lambda: self.reserve("fifth-after-settlement"))
        original = [r for r in self.rows() if r["id"] in self.original_ids]
        self.assertEqual(sum(r["state"] == "unknown" for r in original), 3)
        self.assertEqual(sum(r["state"] == "settled" for r in original), 1)

    def test_forged_settlement_does_not_validate_remaining_batch(self):
        self.install_receipts()
        row = self.old[0]
        self.service.settle(reservation_id=row["reservationId"], authorization_id=self.auth,
            actual_units={"calls": 1, "input_tokens": 20, "output_tokens": 10},
            provider_request_id=None, evidence_sha256=digest("actual-measured-usage"))
        with self.database.transaction() as conn:
            current = conn.execute("SELECT actual_units_json FROM learning_budget_reservations WHERE id=?",
                (row["reservationId"],)).fetchone()
            actual = json.loads(current["actual_units_json"])
            actual["input_tokens"] += 1
            conn.execute("UPDATE learning_budget_reservations SET actual_units_json=? WHERE id=?",
                (canonical(actual), row["reservationId"]))
        # One slot is available because that row is settled; the other three
        # unknowns must regain their conservative hold when the batch is invalid.
        self.reserve("one-slot-after-invalid-settlement")
        self.assert_blocked(lambda: self.reserve("cannot-trust-forged-settlement"))

    def test_concurrent_reserves_share_the_existing_four_active_lock(self):
        self.install_receipts()
        def attempt(index):
            try:
                return self.reserve(f"parallel-{index}", service=self.make_service())
            except ApiError as error:
                self.assertEqual(error.code, "learning_budget_inflight_limit")
                return None
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(row is not None for row in results), 4)
        self.assertEqual(len(self.rows()), 8)

    def test_temporary_override_does_not_raise_actual_concurrency_after_receipts(self):
        self.install_receipts()
        self.raw["authorizationWindow"] = {"startsAt": self.now - 100, "expiresAt": self.now + 1000,
            "scopes": [self.scope]}
        self.raw["productionInflightOverride"] = {"scopeSha256": digest(self.scope), "authorizationId": self.auth,
            "maxInflightCalls": 5, "auditReferenceSha256": digest("reviewed-audit")}
        self.service = self.make_service()
        for index in range(4):
            self.reserve(f"with-override-{index}")
        self.assert_blocked(lambda: self.reserve("fifth-real-active-even-with-override"))
