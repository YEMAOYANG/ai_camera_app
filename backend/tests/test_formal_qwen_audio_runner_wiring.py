from __future__ import annotations

from contextlib import contextmanager
import unittest

from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import (
    FormalProductionStageAdapter,
    LearningCurriculumPreparationRunner,
)


class _Repository:
    def __init__(self) -> None:
        self.persisted: list[dict] = []
        self.released: list[dict] = []

    @contextmanager
    def transaction(self):
        yield self

    def persist_formal_stage_progress(self, _conn, **kwargs):
        self.persisted.append(dict(kwargs))
        next_stage = kwargs["expected_stage"]
        if next_stage == "building_classrooms" and kwargs["classroom_ready_count"] == 30:
            next_stage = "generating_speech"
        elif next_stage == "generating_speech" and kwargs["speech_ready_count"] == 30:
            next_stage = "validating"
        return True, next_stage

    def release_content_continuation(self, _conn, **kwargs):
        self.released.append(dict(kwargs))
        return True


class _FormalRepository:
    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts

    @contextmanager
    def transaction(self):
        yield self

    def formal_pipeline_counts(self, _conn, **_scope):
        return dict(self.counts)


class _FormalAudio:
    def __init__(self, repository: _FormalRepository) -> None:
        self.repository = repository
        self.scopes: list[dict] = []

    def process_next(self, **scope):
        self.scopes.append(dict(scope))
        self.repository.counts["audioTotal"] = 30
        self.repository.counts["speechReady"] = 30
        return {"state": "auto_validated"}


class _ProgressivePublicationService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def advance_progressive_grade_validation(self, **_scope):
        self.calls.append("publication")
        return {
            "total": 1,
            "ready": 1,
            "failed": 0,
            "ambiguous": 0,
            "published": 1,
        }


class _UnpublishedProgressiveService:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def advance_progressive_grade_validation(self, **_scope):
        self.calls.append("publication")
        return {
            "total": 0,
            "ready": 0,
            "failed": 0,
            "ambiguous": 0,
            "published": 0,
        }

    def advance_content(self, *_args, **_kwargs):
        raise AssertionError("next paid content item must wait for publication")


class _RecordingFormalAudio:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def process_next(self, **_scope):
        self.calls.append("audio")
        return {"state": "auto_validated"}


class _App:
    def __init__(self) -> None:
        self.config = {
            "TESTING": False,
            "LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED": True,
            "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED": True,
            "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST": ["primary_1"],
            "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK": 1,
            "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD": 1,
            "LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED": True,
            "LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND": True,
            "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED": False,
            "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS": 90,
        }


def _plan(stage: str) -> dict:
    return {
        "id": "formal-plan-1",
        "stage": stage,
        "catalog_build_id": "formal-build-1",
        "catalog_release_id": "formal-release-1",
        "target_fingerprint": "a" * 64,
        "lease_token": "formal-plan-lease",
        "ready_course_count": 0,
        "failed_course_count": 0,
        "subject_progress_json": {"chinese": {}, "math": {}, "english": {}},
    }


class FormalQwenAudioRunnerWiringTest(unittest.TestCase):
    def test_progressive_tail_drains_ready_work_before_issuing_runtime(self) -> None:
        calls: list[str] = []
        adapter = FormalProductionStageAdapter(
            _ProgressivePublicationService(calls),
            repository=object(),
            runtime_candidate_processor=lambda: calls.append("runtime"),
            formal_repository=object(),
            formal_audio_service=_RecordingFormalAudio(calls),
            formal_audio_validation_enabled=True,
            formal_auto_publication_enabled=True,
            formal_provider_readiness_client=object(),
            formal_route_probe_service=object(),
            formal_route_probe_client=object(),
        )

        result = adapter._process_progressive_formal_tail(
            {**_plan("generating_content"), "grade_code": "primary_1"},
            stage="generating_content",
        )

        self.assertEqual(calls, ["audio", "publication", "runtime"])
        self.assertEqual(result, {
            "total": 1,
            "ready": 1,
            "failed": 0,
            "ambiguous": 0,
            "published": 1,
        })

    def test_content_generation_waits_when_one_course_is_not_yet_published(self) -> None:
        calls: list[str] = []
        repository = _Repository()
        formal_repository = _FormalRepository({
            "total": 30,
            "contentReady": 1,
            "classroomReady": 0,
            "classroomFailed": 0,
            "audioTotal": 0,
            "speechReady": 0,
            "speechFailed": 0,
        })
        adapter = FormalProductionStageAdapter(
            _UnpublishedProgressiveService(calls),
            repository=repository,
            runtime_candidate_processor=lambda: calls.append("runtime"),
            formal_repository=formal_repository,
            formal_audio_service=_RecordingFormalAudio(calls),
            formal_audio_validation_enabled=True,
            formal_auto_publication_enabled=True,
            formal_provider_readiness_client=object(),
            formal_route_probe_service=object(),
            formal_route_probe_client=object(),
            clock=lambda: 10_000,
            heartbeat_interval_ms=1_000,
        )

        result = adapter.advance(
            {
                **_plan("generating_content"),
                "grade_code": "primary_1",
                "work_unit_kind": "coordinator",
                "published_course_count": 0,
            },
            now_ms=9_000,
            heartbeat=lambda: True,
        )

        self.assertEqual(calls, ["audio", "publication", "runtime"])
        self.assertEqual(result.result_kind, "publication_wait")
        self.assertEqual(len(repository.released), 1)

    def test_building_and_speech_stages_drive_workers_and_handoff_once(self) -> None:
        repository = _Repository()
        counts = {
            "total": 30,
            "classroomReady": 29,
            "classroomFailed": 0,
            "audioTotal": 0,
            "speechReady": 0,
            "speechFailed": 0,
        }
        formal_repository = _FormalRepository(counts)
        formal_audio = _FormalAudio(formal_repository)
        runtime_calls = []

        def runtime_candidate_processor():
            runtime_calls.append(True)
            counts["classroomReady"] = 30

        adapter = FormalProductionStageAdapter(
            object(),
            repository=repository,
            runtime_candidate_processor=runtime_candidate_processor,
            formal_repository=formal_repository,
            formal_audio_service=formal_audio,
            formal_audio_validation_enabled=True,
            clock=lambda: 10_000,
            heartbeat_interval_ms=1_000,
        )
        building = adapter.advance(
            _plan("building_classrooms"),
            now_ms=9_000,
            heartbeat=lambda: True,
        )
        self.assertEqual(runtime_calls, [True])
        self.assertEqual(building.next_stage, "generating_speech")
        self.assertEqual(repository.persisted[-1]["classroom_ready_count"], 30)

        counts["audioTotal"] = 29
        counts["speechReady"] = 29
        speech = adapter.advance(
            _plan("generating_speech"),
            now_ms=9_000,
            heartbeat=lambda: True,
        )
        self.assertEqual(speech.next_stage, "validating")
        expected_audio_scope = {
            "build_id": "formal-build-1",
            "release_id": "formal-release-1",
            "target_fingerprint": "a" * 64,
        }
        self.assertEqual(formal_audio.scopes, [
            expected_audio_scope,
            expected_audio_scope,
        ])
        self.assertEqual(repository.persisted[-1]["speech_ready_count"], 30)
        self.assertTrue({"building_classrooms", "generating_speech"}.issubset(
            adapter.supported_stages
        ))

    def test_runner_schedules_the_inert_thirty_of_thirty_handoff_before_claim(self) -> None:
        class RunnerRepository:
            def __init__(self):
                self.started = False

            @contextmanager
            def transaction(self):
                yield self

            def start_next_formal_pipeline(self, _conn, **kwargs):
                self.started = True
                self.start_scope = kwargs
                return "formal-plan-1"

            def claim_next(self, _conn, **_kwargs):
                if not self.started:
                    raise AssertionError("formal handoff must be scheduled first")
                return None

        repository = RunnerRepository()
        adapter = type("Adapter", (), {"supported_stages": frozenset({
            "building_classrooms", "generating_speech"
        })})()
        runner = LearningCurriculumPreparationRunner(
            repository=repository,
            adapter=adapter,
            clock=lambda: 20_000,
        )
        result = runner.run_once(_App(), now_ms=20_000)
        expected_target = preparation_target_fingerprint(
            build_preparation_target("primary_1")
        )
        self.assertEqual(result, {"claimed": 0})
        self.assertEqual(repository.start_scope, {
            "grade_code": "primary_1",
            "target_fingerprint": expected_target,
            "now": 20_000,
        })


if __name__ == "__main__":
    unittest.main()
