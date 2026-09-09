from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from services.formal_learning_health import (
    FORMAL_EVENT_SCHEMA,
    FORMAL_HEALTH_SCHEMA,
    RUNTIME_LATEST_PATCH,
    RUNTIME_LATEST_PATCH_SHA256,
    formal_learning_health_attestation,
)


class FormalLearningHealthTest(unittest.TestCase):
    def test_attestation_is_exact_and_default_off(self) -> None:
        result = formal_learning_health_attestation(
            {
                "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST": ["primary_1"],
            }
        )

        self.assertEqual(result["schemaVersion"], FORMAL_HEALTH_SCHEMA)
        self.assertEqual(result["gradeAllowlist"], ["primary_1"])
        self.assertEqual(result["contracts"]["runtimeEvent"], FORMAL_EVENT_SCHEMA)
        self.assertEqual(result["runtimePatch"]["latest"], RUNTIME_LATEST_PATCH)
        self.assertEqual(result["runtimePatch"]["count"], 42)
        self.assertEqual(
            result["runtimePatch"]["latest"],
            "0042-mira-deepseek-courseware-routing.patch",
        )
        self.assertEqual(
            result["runtimePatch"]["latestSha256"],
            RUNTIME_LATEST_PATCH_SHA256,
        )
        self.assertEqual(set(result["gates"].values()), {False})
        self.assertFalse(result["rolloutEligible"])

        repository_root = Path(__file__).resolve().parents[2]
        lock = json.loads(
            (repository_root / "openmaic-runtime" / "upstream.lock.json").read_text(
                encoding="utf-8"
            )
        )
        patch_path = (
            repository_root
            / "openmaic-runtime"
            / "patches"
            / lock["patchManifest"]["latest"]
        )
        actual_patch_sha256 = hashlib.sha256(patch_path.read_bytes()).hexdigest()
        self.assertEqual(
            lock["version"], result["runtimePatch"]["upstreamVersion"]
        )
        self.assertEqual(
            lock["commit"], result["runtimePatch"]["upstreamCommit"]
        )
        self.assertEqual(lock["patchManifest"]["count"], result["runtimePatch"]["count"])
        self.assertEqual(lock["patchManifest"]["latest"], result["runtimePatch"]["latest"])
        self.assertEqual(
            lock["patchManifest"]["latestSha256"], actual_patch_sha256
        )
        self.assertEqual(result["runtimePatch"]["latestSha256"], actual_patch_sha256)

    def test_only_exact_grade_and_all_five_gates_are_rollout_eligible(self) -> None:
        config = {
            "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST": ["primary_1"],
            "LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED": True,
            "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED": True,
            "LEARNING_CLASSROOM_GENERATION_ENABLED": True,
            "LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED": True,
            "LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED": True,
            "LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED": True,
            "LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED": True,
        }
        self.assertTrue(formal_learning_health_attestation(config)["rolloutEligible"])

        config["LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST"] = [
            "primary_1",
            "primary_2",
        ]
        self.assertFalse(formal_learning_health_attestation(config)["rolloutEligible"])

        config["LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST"] = ["primary_1"]
        config["LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED"] = False
        self.assertFalse(formal_learning_health_attestation(config)["rolloutEligible"])


if __name__ == "__main__":
    unittest.main()
