from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from integrations.openmaic_draft_adapter import (
    OPENMAIC_DRAFT_SCHEMA,
    OpenMaicDraftAdapter,
    OpenMaicDraftError,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SIDECAR_ROOT = BACKEND_ROOT / "openmaic-sidecar"


def _completed(payload: dict, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["node"],
        returncode=returncode,
        stdout=json.dumps(payload, ensure_ascii=False),
        stderr="",
    )


class OpenMaicDraftAdapterTest(unittest.TestCase):
    def setUp(self):
        self.skill_boundary = {
            "gradeCode": "primary_3",
            "subject": "math",
            "skillId": "math.p3.addition.carry",
            "skillTitle": "两位数进位加法",
            "learningObjectives": ["理解个位满十向十位进一"],
            "allowedContent": ["和不超过100"],
            "excludedContent": ["小数", "负数"],
        }

    def test_generate_returns_stable_result_without_serializing_secret(self):
        captured = {}

        def runner(command, **kwargs):
            captured.update(kwargs)
            return _completed(
                {
                    "schemaVersion": OPENMAIC_DRAFT_SCHEMA,
                    "requestId": "req-1",
                    "generator": "openmaic",
                    "provider": "kimi",
                    "model": "kimi-k2.6",
                    "elapsedMs": 24,
                    "draft": {
                        "status": "unverified",
                        "authoritativeAnswersProvided": False,
                        "scenes": [],
                    },
                }
            )

        with mock.patch.dict(os.environ, {"APP_AI_API_KEY": "secret-never-in-stdin"}):
            adapter = OpenMaicDraftAdapter(
                sidecar_root=SIDECAR_ROOT,
                provider_name="kimi",
                model_name="kimi-k2.6",
                base_url="https://api.moonshot.cn/v1",
                process_runner=runner,
            )
            result = adapter.generate(self.skill_boundary, "req-1")

        self.assertEqual(result.generator, "openmaic")
        self.assertEqual(result.schema_version, OPENMAIC_DRAFT_SCHEMA)
        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(result.provider, "kimi")
        self.assertEqual(result.model, "kimi-k2.6")
        self.assertEqual(result.elapsed_ms, 24)
        self.assertFalse(result.draft["authoritativeAnswersProvided"])
        self.assertNotIn("secret-never-in-stdin", captured["input"])
        request = json.loads(captured["input"])
        self.assertEqual(request["provider"]["apiKeyEnv"], "APP_AI_API_KEY")
        self.assertNotIn("apiKey", request["provider"])

    def test_sidecar_error_becomes_recognizable_exception(self):
        def runner(command, **kwargs):
            return _completed(
                {
                    "schemaVersion": OPENMAIC_DRAFT_SCHEMA,
                    "generator": "openmaic",
                    "error": {"code": "invalid_input", "message": "fixed skill is required"},
                },
                returncode=1,
            )

        adapter = OpenMaicDraftAdapter(
            sidecar_root=SIDECAR_ROOT,
            model_name="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
            process_runner=runner,
        )
        with self.assertRaises(OpenMaicDraftError) as context:
            adapter.generate(self.skill_boundary, "req-1")
        self.assertEqual(context.exception.code, "invalid_input")

    def test_timeout_becomes_recognizable_exception(self):
        def runner(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        adapter = OpenMaicDraftAdapter(
            sidecar_root=SIDECAR_ROOT,
            model_name="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
            timeout_seconds=3,
            process_runner=runner,
        )
        with self.assertRaises(OpenMaicDraftError) as context:
            adapter.generate(self.skill_boundary, "req-1")
        self.assertEqual(context.exception.code, "openmaic_timeout")

    def test_availability_reports_runtime_and_provider_state(self):
        def runner(command, **kwargs):
            return _completed(
                {
                    "available": True,
                    "schemaVersion": OPENMAIC_DRAFT_SCHEMA,
                    "generator": "openmaic",
                    "packages": {
                        "@openmaic/generation": "0.3.0",
                        "@openmaic/dsl": "0.8.0",
                    },
                    "node": "v20.0.0",
                }
            )

        with mock.patch.dict(os.environ, {"APP_AI_API_KEY": "configured"}):
            adapter = OpenMaicDraftAdapter(
                sidecar_root=SIDECAR_ROOT,
                model_name="kimi-k2.6",
                base_url="https://api.moonshot.cn/v1",
                process_runner=runner,
            )
            result = adapter.availability()

        self.assertTrue(result["available"])
        self.assertTrue(result["runtimeAvailable"])
        self.assertTrue(result["providerConfigured"])
        self.assertEqual(result["packages"]["@openmaic/generation"], "0.3.0")


if __name__ == "__main__":
    unittest.main()
