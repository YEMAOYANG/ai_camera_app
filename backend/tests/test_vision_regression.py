from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from routes.api.v1.camera_bridge import _normalize_monitor_observation
from schemas.vision import with_observation_reliability
from services.camera_command_service import lightweight_camera_event_from_observation
from services.observation_payload_builder import build_primary_payload, raw_detail_from_analysis
from services.observation_session_state import risk_escalated, session_snapshot_from_observation
from services.vision_observation_enrich import enrich_observation
from services.vision_observation_validator import VisionObservationValidator
from tests.fixtures.vision_regression_cases import VISION_REGRESSION_CASES, VisionRegressionCase


@dataclass
class VisionPipelineResult:
    case_id: str
    enriched: dict
    monitor: dict | None
    payload: dict | None
    display_title: str
    session: dict[str, str]


def run_vision_pipeline_from_enriched(
    *,
    case_id: str,
    enriched: dict,
    observed_at: int = 4_000,
) -> VisionPipelineResult:
    observation = with_observation_reliability(dict(enriched))

    payload = build_primary_payload(
        observation,
        family_id="fam_regression",
        child_id="child_regression",
        device_id="dev_regression",
        source="vision_regression",
        window_start_ms=1_000,
        window_end_ms=observed_at,
        observed_at=observed_at,
    )

    monitor_source = {
        **observation,
        "observedAt": observed_at,
        "confidence": observation.get("confidence", 0.86),
    }
    monitor = _normalize_monitor_observation(monitor_source)

    display_observation = {
        "hasPerson": observation.get("has_person"),
        "activity": observation.get("activity"),
        "summary": (monitor or {}).get("summary") or "",
        "description": observation.get("description") or "",
        "decisionReason": observation.get("decision_reason") or "",
        "isReliable": bool(observation.get("isReliable")),
        "scenario": payload.get("scenario") if isinstance(payload, dict) else "",
        "rawDetail": raw_detail_from_analysis(observation),
    }
    event = lightweight_camera_event_from_observation(
        event_id=f"evt_{case_id}",
        device_id="dev_regression",
        observation=display_observation,
        now=observed_at,
    )

    return VisionPipelineResult(
        case_id=case_id,
        enriched=observation,
        monitor=monitor,
        payload=payload if isinstance(payload, dict) else None,
        display_title=str(event.get("displayTitle") or ""),
        session=session_snapshot_from_observation(observation),
    )


def assert_vision_regression_expectation(
    case: VisionRegressionCase,
    result: VisionPipelineResult,
    *,
    test_case: unittest.TestCase,
) -> None:
    expect = case.expect

    if expect.activity:
        test_case.assertEqual(
            str(result.enriched.get("activity") or ""),
            expect.activity,
            msg=f"activity mismatch for {case.case_id}",
        )

    if expect.raw_activity is not None:
        test_case.assertEqual(
            str(result.enriched.get("raw_activity") or ""),
            expect.raw_activity,
            msg=f"raw_activity mismatch for {case.case_id}",
        )

    if expect.posture_status is not None:
        test_case.assertEqual(
            str(result.enriched.get("posture_status") or ""),
            expect.posture_status,
            msg=f"posture_status mismatch for {case.case_id}",
        )

    if expect.bad_posture is not None:
        test_case.assertEqual(
            bool(result.enriched.get("bad_posture")),
            expect.bad_posture,
            msg=f"bad_posture mismatch for {case.case_id}",
        )

    if expect.meal_standing is not None:
        test_case.assertEqual(
            bool(result.enriched.get("meal_standing")),
            expect.meal_standing,
            msg=f"meal_standing mismatch for {case.case_id}",
        )

    if expect.meal_etiquette_issue is not None:
        test_case.assertEqual(
            str(result.enriched.get("meal_etiquette_issue") or ""),
            expect.meal_etiquette_issue,
            msg=f"meal_etiquette_issue mismatch for {case.case_id}",
        )

    if expect.is_reliable is not None:
        test_case.assertEqual(
            bool(result.enriched.get("isReliable")),
            expect.is_reliable,
            msg=f"isReliable mismatch for {case.case_id}",
        )

    if expect.summary is not None:
        test_case.assertIsNotNone(result.monitor)
        assert result.monitor is not None
        test_case.assertEqual(result.monitor.get("summary"), expect.summary)

    if expect.display_title is not None:
        test_case.assertEqual(result.display_title, expect.display_title)

    for forbidden in expect.forbidden_display_titles:
        test_case.assertNotEqual(
            result.display_title,
            forbidden,
            msg=f"forbidden display title {forbidden!r} for {case.case_id}",
        )

    if expect.expect_payload is not None:
        if expect.expect_payload:
            test_case.assertIsNotNone(result.payload, msg=f"expected payload for {case.case_id}")
        else:
            test_case.assertIsNone(result.payload, msg=f"expected no payload for {case.case_id}")

    if expect.scenario is not None:
        test_case.assertIsNotNone(result.payload)
        assert result.payload is not None
        test_case.assertEqual(result.payload.get("scenario"), expect.scenario)

    if expect.signal_type is not None:
        test_case.assertIsNotNone(result.payload)
        assert result.payload is not None
        signals = result.payload.get("signals") or []
        test_case.assertTrue(signals, msg=f"missing signals for {case.case_id}")
        test_case.assertEqual(signals[0].get("signalType"), expect.signal_type)

    if expect.record_care_event is not None:
        test_case.assertIsNotNone(result.payload)
        assert result.payload is not None
        test_case.assertEqual(result.payload.get("recordCareEvent"), expect.record_care_event)

    if expect.session_bucket is not None:
        test_case.assertEqual(result.session.get("bucket"), expect.session_bucket)

    if expect.session_risk is not None:
        test_case.assertEqual(result.session.get("risk"), expect.session_risk)

    description = str(result.enriched.get("description") or "")
    for token in expect.description_contains:
        test_case.assertIn(token, description, msg=f"description should contain {token!r}")
    for token in expect.description_excludes:
        test_case.assertNotIn(token, description, msg=f"description should exclude {token!r}")


def run_vision_regression_case(
    case: VisionRegressionCase,
    *,
    observed_at: int = 4_000,
) -> VisionPipelineResult:
    raw = dict(case.raw_model)
    raw["confidence"] = case.confidence

    if case.use_validator:
        validation = VisionObservationValidator().validate(
            json.dumps(raw, ensure_ascii=False),
            observed_at=observed_at,
        )
        observation = dict(validation.observation)
    else:
        observation = dict(raw)
        observation.setdefault("observed_at", observed_at)

    enriched = enrich_observation(observation)
    enriched = with_observation_reliability(enriched)

    payload = build_primary_payload(
        enriched,
        family_id="fam_regression",
        child_id="child_regression",
        device_id="dev_regression",
        source="vision_regression",
        window_start_ms=1_000,
        window_end_ms=observed_at,
        observed_at=observed_at,
    )

    monitor_source = {
        **enriched,
        "observedAt": observed_at,
        "confidence": enriched.get("confidence", case.confidence),
    }
    monitor = _normalize_monitor_observation(monitor_source)

    display_observation = {
        "hasPerson": enriched.get("has_person"),
        "activity": enriched.get("activity"),
        "summary": (monitor or {}).get("summary") or "",
        "description": enriched.get("description") or "",
        "decisionReason": enriched.get("decision_reason") or "",
        "isReliable": bool(enriched.get("isReliable")),
        "scenario": payload.get("scenario") if isinstance(payload, dict) else "",
        "rawDetail": raw_detail_from_analysis(enriched),
    }
    event = lightweight_camera_event_from_observation(
        event_id=f"evt_{case.case_id}",
        device_id="dev_regression",
        observation=display_observation,
        now=observed_at,
    )

    return VisionPipelineResult(
        case_id=case.case_id,
        enriched=enriched,
        monitor=monitor,
        payload=payload if isinstance(payload, dict) else None,
        display_title=str(event.get("displayTitle") or ""),
        session=session_snapshot_from_observation(enriched),
    )


class VisionRegressionTest(unittest.TestCase):
    def test_all_regression_cases(self):
        failures: list[str] = []
        for case in VISION_REGRESSION_CASES:
            with self.subTest(case_id=case.case_id, title=case.title):
                try:
                    self._assert_case(case)
                except AssertionError as exc:
                    failures.append(f"{case.case_id}: {exc}")

        if failures:
            joined = "\n".join(f"  - {item}" for item in failures)
            self.fail(f"{len(failures)} vision regression case(s) failed:\n{joined}")

    def _assert_case(self, case: VisionRegressionCase) -> None:
        result = run_vision_regression_case(case)
        assert_vision_regression_expectation(case, result, test_case=self)

    def test_meal_case_escalates_from_previous_toy_session(self):
        case = next(item for item in VISION_REGRESSION_CASES if item.case_id == "session_toy_to_meal_escalation")
        result = run_vision_regression_case(case)
        previous = {"bucket": "toy_play", "risk": "toy_playing_safe"}
        self.assertTrue(risk_escalated(previous, result.session))


class VisionPromptRegressionTest(unittest.TestCase):
    def test_scene_observation_prompt_has_priority_rules(self):
        from pathlib import Path

        prompt_path = (
            Path(__file__).resolve().parents[1]
            / "prompts"
            / "vision"
            / "scene_observation_v1.md"
        )
        body = prompt_path.read_text(encoding="utf-8")
        required_snippets = (
            "先认「人正在做什么」",
            "判定优先级",
            "用餐",
            "玩玩具",
            "has_person=false",
            "易错对照",
        )
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, body)


if __name__ == "__main__":
    unittest.main()
