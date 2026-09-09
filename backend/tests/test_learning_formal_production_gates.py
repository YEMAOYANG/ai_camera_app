from __future__ import annotations

from contextlib import contextmanager
import unittest

from core.config import ConfigError, apply_test_defaults, validate_flask_config
from services.learning_curriculum_preparation_runner import (
    FormalProductionStageAdapter,
    PreparationTransientError,
)


class _PreparationRepository:
    @contextmanager
    def transaction(self):
        yield self

    def persist_formal_stage_progress(self, _conn, **_kwargs):
        raise AssertionError("a disabled formal stage must not persist progress")


class _FormalRepository:
    @contextmanager
    def transaction(self):
        yield self

    def formal_pipeline_counts(self, _conn, **_scope):
        return {
            "total": 30,
            "classroomReady": 30,
            "classroomFailed": 0,
            "audioTotal": 29,
            "speechReady": 29,
            "speechFailed": 0,
        }


class _ForbiddenAudioService:
    def process_next(self, **_scope):
        raise AssertionError("disabled formal audio must never be called")


class _ForbiddenPublicationService:
    def activate_grade_release(self, **_scope):
        raise AssertionError("disabled formal publication must never switch a pointer")


def _plan(stage: str) -> dict[str, object]:
    return {
        "id": "formal-plan-1",
        "stage": stage,
        "grade_code": "primary_1",
        "catalog_build_id": "formal-build-1",
        "catalog_release_id": "formal-release-1",
        "target_fingerprint": "a" * 64,
        "lease_token": "formal-lease-1",
        "ready_course_count": 30,
        "failed_course_count": 0,
        "subject_progress_json": {
            "chinese": {"target": 10, "ready": 10, "failed": 0},
            "math": {"target": 10, "ready": 10, "failed": 0},
            "english": {"target": 10, "ready": 10, "failed": 0},
        },
    }


class LearningFormalProductionGatesTest(unittest.TestCase):
    def _adapter(self) -> FormalProductionStageAdapter:
        return FormalProductionStageAdapter(
            _ForbiddenPublicationService(),
            repository=_PreparationRepository(),
            runtime_candidate_processor=lambda: None,
            formal_repository=_FormalRepository(),
            formal_audio_service=_ForbiddenAudioService(),
            clock=lambda: 10_000,
        )

    def test_formal_audio_validation_is_default_off_before_provider_call(self) -> None:
        with self.assertRaisesRegex(
            PreparationTransientError,
            "formal audio validation is disabled",
        ):
            self._adapter().advance(
                _plan("generating_speech"),
                now_ms=9_000,
                heartbeat=lambda: True,
            )

    def test_formal_auto_publication_is_default_off_before_pointer_switch(self) -> None:
        with self.assertRaisesRegex(
            PreparationTransientError,
            "formal automatic publication is disabled",
        ):
            self._adapter().advance(
                _plan("publishing"),
                now_ms=9_000,
                heartbeat=lambda: True,
            )

    def test_test_config_defaults_both_formal_production_gates_off(self) -> None:
        config = apply_test_defaults({"TESTING": True})

        self.assertIs(config.get("LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED"), False)
        self.assertIs(config.get("LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED"), False)

    def test_flask_config_rejects_non_boolean_formal_production_gates(self) -> None:
        for key in (
            "LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED",
            "LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED",
        ):
            with self.subTest(key=key), self.assertRaisesRegex(
                ConfigError,
                "formal production enable flags must be booleans",
            ):
                validate_flask_config(
                    {
                        **apply_test_defaults(
                            {
                                "TESTING": True,
                                "APP_ENV": "test",
                                "DATABASE_URL": (
                                    "mysql+pymysql://test:test@127.0.0.1:3306/"
                                    "ai_camera_app_test"
                                ),
                            }
                        ),
                        key: "0",
                    }
                )


if __name__ == "__main__":
    unittest.main()
