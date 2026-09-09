from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

from integrations.openmaic_formal_media import LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository as Repository,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.test_learning_planning_atomic_authority_unit import _planning_plan


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def legacy_target():
    target = build_preparation_target("primary_1")
    target["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(LEGACY_PROFESSIONAL_POLICY)
    from integrations.openmaic_formal_media import LEGACY_CONTENT_PROVIDER_PROFILE
    target["contentProviderProfileContractVersion"] = LEGACY_CONTENT_PROVIDER_PROFILE
    return target


def authority(target):
    fingerprint = preparation_target_fingerprint(target)
    request_id = f"grade-build:{fingerprint}"
    digest = hashlib.sha256(request_id.encode()).hexdigest()[:24]
    build = {
        "id": f"catalog_build_{digest}", "request_id": request_id,
        "release_id": f"catalog_release_{digest}",
        "curriculum_version": target["curriculumVersion"], "status": "running",
        "target_spec_json": encoded(target), "total_item_count": 30,
        "ready_item_count": 0, "failed_item_count": 0,
        "execution_mode": "content_only", "stage_ceiling": "content_ready",
        "content_manifest_version": target["schemaVersion"],
        "canary_manifest_json": encoded(target["canaryManifest"]),
    }
    release = {
        "id": build["release_id"], "curriculum_version": target["curriculumVersion"],
        "status": "draft", "quality_status": "building",
        "required_boundary_count": 10, "ready_item_count": 0,
    }
    plan = {
        **_planning_plan(), "retry_of_plan_id": None, "retry_ordinal": 0,
        "target_spec_json": encoded(target),
        "target_fingerprint": fingerprint, "shared_build_request_id": request_id,
        "curriculum_version": target["curriculumVersion"],
        "catalog_build_id": build["id"], "catalog_release_id": release["id"],
    }
    child = {"id": plan["child_id"], "family_id": plan["family_id"],
             "grade_code": "primary_1", "grade_selection_revision": 7}
    return dict(build=build, release=release, plan=plan, child=child,
                target_fingerprint=fingerprint)


class Cursor:
    rowcount = 1

    def __init__(self, value):
        self.value = value

    def fetchone(self):
        return self.value

    def fetchall(self):
        return self.value


class Connection:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.writes = []
        self.reads = []

    def execute(self, sql, parameters=()):
        if sql.lstrip().startswith("UPDATE"):
            self.writes.append((sql, parameters))
            return Cursor(None)
        self.reads.append((sql, parameters))
        return Cursor(next(self.responses))


class LegacyPreparationTargetTest(unittest.TestCase):
    def test_current_and_exact_legacy_keep_planning_and_shared_identity(self):
        image_target = build_preparation_target("primary_1")
        image_target["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(IMAGE_PROFESSIONAL_POLICY)
        from integrations.openmaic_formal_media import LEGACY_CONTENT_PROVIDER_PROFILE
        image_target["contentProviderProfileContractVersion"] = LEGACY_CONTENT_PROVIDER_PROFILE
        for target in (build_preparation_target("primary_1"), image_target, legacy_target()):
            with self.subTest(image="image" in target["formalRuntimePolicy"]["professionalCreationPolicy"]):
                data = authority(target)
                original = deepcopy(data)
                self.assertTrue(Repository._planning_authority_matches(
                    child=data["child"], plan=data["plan"], plan_lease_token="planning-lease",
                    target_fingerprint=data["target_fingerprint"], now=1001,
                ))
                self.assertTrue(Repository._shared_authority_matches(items=None, **data))
                self.assertEqual(data, original)
                self.assertFalse(Repository._planning_authority_matches(
                    child=data["child"], plan=data["plan"], plan_lease_token="planning-lease",
                    target_fingerprint="0" * 64, now=1001,
                ))
                mixed = deepcopy(data)
                mixed["build"]["target_spec_json"] = encoded(build_preparation_target("primary_1") if target == legacy_target() else legacy_target())
                self.assertFalse(Repository._shared_authority_matches(items=None, **mixed))

    def test_unrelated_drift_is_rejected_even_with_recomputed_ids(self):
        variants = []
        for field, value in (("gradeCode", "primary_2"), ("curriculumVersion", "changed")):
            target = legacy_target()
            target[field] = value
            variants.append(target)
        invalid_policy = legacy_target()
        invalid_policy["formalRuntimePolicy"]["professionalCreationPolicy"]["studentToolsEnabled"] = True
        variants.append(invalid_policy)
        for target in variants:
            data = authority(target)
            self.assertFalse(Repository._planning_authority_matches(
                child=data["child"], plan=data["plan"], plan_lease_token="planning-lease",
                target_fingerprint=data["target_fingerprint"], now=1001,
            ))
            self.assertFalse(Repository._shared_authority_matches(items=None, **data))

    def test_legacy_failed_recoveries_preserve_target_and_request_identity(self):
        for method, error, statuses in (
            ("recover_shared_content_validation_plans", "preparation_content_validation_failed", ["processing"] + ["pending"] * 29),
            ("recover_shared_content_audit_plans", "preparation_content_contract_drift", ["course_ready"] + ["pending"] * 29),
        ):
            with self.subTest(method=method):
                data = authority(legacy_target())
                plan = data["plan"]
                plan.update(status="failed", stage="completed", error_code=error, completed_at=2000)
                for field in ("lease_token", "lease_expires_at", "heartbeat_at", "next_run_at", "hard_deadline_at", "work_unit_kind"):
                    plan[field] = None
                original = deepcopy(data)
                repo = Repository(object())
                items = [{"status": status} for status in statuses]
                conn = Connection(data["build"], items, [plan])
                self.assertEqual(getattr(repo, method)(conn, build_id=data["build"]["id"], target_fingerprint=data["target_fingerprint"], now=3000), 1)
                self.assertEqual(data, original)
                self.assertEqual(len(conn.writes), 1)
                self.assertNotIn("target_spec_json", conn.writes[0][0])
                self.assertNotIn("shared_build_request_id", conn.writes[0][0])
                self.assertIn(data["target_fingerprint"], conn.writes[0][1])
                for invalid in (encoded(build_preparation_target("primary_1")), "malformed-json"):
                    changed = {**plan, "target_spec_json": invalid}
                    conn = Connection(data["build"], items, [changed])
                    self.assertEqual(getattr(repo, method)(conn, build_id=data["build"]["id"], target_fingerprint=data["target_fingerprint"], now=3000), 0)
                    self.assertEqual(conn.writes, [])

    def test_legacy_reconciliation_reaches_existing_evidence_auditor(self):
        data = authority(legacy_target())
        items = [{"id": f"item-{i}", "release_id": data["release"]["id"], "build_job_id": data["build"]["id"], "execution_mode_snapshot": "content_only", "content_manifest_version_snapshot": legacy_target()["schemaVersion"]} for i in range(30)]
        auditor = Mock(return_value=None)
        repo = Repository(object(), content_proof_auditor=auditor)
        conn = Connection(data["release"], data["build"], items)
        self.assertEqual(repo._reconcile_shared_build_locked(conn, build_id=data["build"]["id"], target_fingerprint=data["target_fingerprint"], now=3000), 0)
        auditor.assert_called_once_with(conn, build_id=data["build"]["id"])
        self.assertEqual(conn.writes, [])

    def test_terminal_fanout_preserves_legacy_identity(self):
        data = authority(legacy_target())
        original = deepcopy(data)
        conn = Connection([data["plan"]], [data["child"]], [data["plan"]])
        repo = Repository(object())
        self.assertEqual(repo._fanout_persisted_terminal_locked(conn, build_id=data["build"]["id"], release_id=data["release"]["id"], build={**data["build"], "error_code": "content_validation_failed"}, target_fingerprint=data["target_fingerprint"], now=3000), 1)
        self.assertEqual(data, original)
        self.assertNotIn("target_spec_json", conn.writes[0][0])
        self.assertNotIn("shared_build_request_id", conn.writes[0][0])

    def test_legacy_adoption_reaches_same_fingerprint_publication_lookup(self):
        data = authority(legacy_target())
        data["plan"].update(status="queued", stage="queued", lease_token=None)
        original = deepcopy(data)
        conn = Connection(None)
        repo = Repository(object())
        with patch.object(repo, "get_plan", return_value=data["plan"]):
            result = repo.adopt_active_formal_release(conn, plan_id=data["plan"]["id"], family_id=data["plan"]["family_id"], child_id=data["plan"]["child_id"], grade_selection_revision=7, target_fingerprint=data["target_fingerprint"], now=3000)
        self.assertIs(result, data["plan"])
        self.assertEqual(len(conn.reads), 1)
        self.assertIn(data["target_fingerprint"], conn.reads[0][1])
        self.assertEqual(data, original)
        self.assertEqual(conn.writes, [])


if __name__ == "__main__":
    unittest.main()
