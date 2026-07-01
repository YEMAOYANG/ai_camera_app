from __future__ import annotations

import os
import unittest
from pathlib import Path

from services.prompt_registry import PromptRegistry
from services.service_factory import build_ai_vision_provider_from_config
from services.vision_observation_cadence import VisionCadenceGate
from services.vision_observation_service import VisionObservationService
from services.vision_observation_validator import VisionObservationValidator
from tests.fixtures.vision_live_cases import VISION_IMAGES_ROOT, VISION_LIVE_CASES, VisionLiveCase
from tests.fixtures.vision_regression_cases import VisionRegressionCase, VisionRegressionExpectation
from tests.test_vision_regression import assert_vision_regression_expectation, run_vision_pipeline_from_enriched

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOT = BACKEND_ROOT / "prompts"
IMAGES_ROOT = BACKEND_ROOT / VISION_IMAGES_ROOT


def _live_regression_enabled() -> bool:
    return os.getenv("KIMI_VISION_LIVE", "").strip() == "1"


def _vision_config_from_env() -> dict:
    return {
        "AI_VISION_ENABLED": True,
        "AI_PROVIDER": os.getenv("AI_PROVIDER", "kimi"),
        "AI_API_KEY": os.getenv("AI_API_KEY", ""),
        "AI_BASE_URL": os.getenv("AI_BASE_URL", ""),
        "AI_VISION_MODEL": os.getenv("AI_VISION_MODEL") or os.getenv("AI_MODEL", ""),
        "AI_VISION_TIMEOUT_SECONDS": float(os.getenv("AI_VISION_TIMEOUT_SECONDS", "30")),
        "AI_VISION_MAX_BYTES": int(os.getenv("AI_VISION_MAX_BYTES", "524288")),
        "AI_VISION_MAX_DIMENSION": int(os.getenv("AI_VISION_MAX_DIMENSION", "1280")),
        "AI_VISION_JPEG_QUALITY": int(os.getenv("AI_VISION_JPEG_QUALITY", "85")),
        "PROMPT_ROOT": str(PROMPT_ROOT),
    }


def _build_live_service(device_key: str) -> VisionObservationService:
    config = _vision_config_from_env()
    provider = build_ai_vision_provider_from_config(config)
    return VisionObservationService(
        vision_provider=provider,
        prompt_registry=PromptRegistry(PROMPT_ROOT),
        validator=VisionObservationValidator(),
        cadence=VisionCadenceGate(),
        enabled=True,
        min_interval_seconds=0,
        max_calls_per_hour=100,
        backoff_seconds=1,
    )


def _image_path(case: VisionLiveCase) -> Path:
    return IMAGES_ROOT / case.image_filename


def _live_case_as_regression_case(case: VisionLiveCase) -> VisionRegressionCase:
    return VisionRegressionCase(
        case_id=case.case_id,
        title=case.title,
        raw_model={},
        expect=case.expect,
        notes=case.notes,
        use_validator=False,
        tags=case.tags,
    )


@unittest.skipUnless(_live_regression_enabled(), "set KIMI_VISION_LIVE=1 to run live Kimi vision regression")
class VisionLiveRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = _vision_config_from_env()
        missing = [
            name
            for name, value in (
                ("AI_API_KEY", config.get("AI_API_KEY")),
                ("AI_BASE_URL", config.get("AI_BASE_URL")),
                ("AI_VISION_MODEL", config.get("AI_VISION_MODEL")),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise unittest.SkipTest(f"missing live vision env: {', '.join(missing)}")

    def test_live_cases(self):
        service = _build_live_service("vision_live_regression")
        failures: list[str] = []
        skipped = 0
        ran = 0

        for case in VISION_LIVE_CASES:
            image_path = _image_path(case)
            if not image_path.is_file():
                skipped += 1
                continue
            with self.subTest(case_id=case.case_id, image=str(image_path)):
                ran += 1
                try:
                    image_bytes = image_path.read_bytes()
                    suffix = image_path.suffix.lower()
                    content_type = "image/png" if suffix == ".png" else "image/jpeg"
                    enriched = service.analyze_snapshot(
                        image_bytes=image_bytes,
                        content_type=content_type,
                        device_key=f"live_{case.case_id}",
                        context=dict(case.context),
                        force_analyze=True,
                    )
                    self.assertNotEqual(
                        str(enriched.get("decision_reason") or enriched.get("reason") or ""),
                        "vision_provider_unavailable",
                        msg="vision provider unavailable",
                    )
                    result = run_vision_pipeline_from_enriched(
                        case_id=case.case_id,
                        enriched=enriched,
                    )
                    assert_vision_regression_expectation(
                        _live_case_as_regression_case(case),
                        result,
                        test_case=self,
                    )
                except AssertionError as exc:
                    failures.append(f"{case.case_id}: {exc}")

        if ran == 0:
            self.skipTest(
                f"no live images under {IMAGES_ROOT}; skipped {skipped} case(s). "
                "See tests/fixtures/vision_images/README.md"
            )

        if failures:
            joined = "\n".join(f"  - {item}" for item in failures)
            self.fail(f"{len(failures)} live vision case(s) failed:\n{joined}")


class VisionLiveRegressionSkeletonTest(unittest.TestCase):
    def test_live_cases_defined(self):
        self.assertGreaterEqual(len(VISION_LIVE_CASES), 4)
        for case in VISION_LIVE_CASES:
            self.assertTrue(case.image_filename)
            self.assertIsInstance(case.expect, VisionRegressionExpectation)

    def test_live_regression_disabled_by_default(self):
        if _live_regression_enabled():
            self.skipTest("live mode enabled")
        suite = unittest.TestLoader().loadTestsFromName(
            "tests.test_vision_live_regression.VisionLiveRegressionTest"
        )
        self.assertGreater(suite.countTestCases(), 0)


if __name__ == "__main__":
    unittest.main()
