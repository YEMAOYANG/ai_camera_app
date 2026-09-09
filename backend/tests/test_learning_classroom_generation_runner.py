from __future__ import annotations

import json
import unittest
from contextlib import contextmanager

from core.config import ConfigError, _validate_formal_runtime_candidate_config
from core.errors import ApiError
from services.learning_classroom_generation_runner import (
    LearningClassroomGenerationRunner,
)
from services.lesson_package_service import LessonPackageGenerationResult
from services.lesson_package_service import LessonPackageService


class LearningClassroomGenerationRunnerTest(unittest.TestCase):
    def test_formal_candidate_config_requires_the_polling_runner(self):
        with self.assertRaisesRegex(
            ConfigError,
            "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED",
        ):
            _validate_formal_runtime_candidate_config(
                enabled=True,
                classroom_runner_enabled=True,
                runtime_enabled=True,
                generation_enabled=True,
                autorun_enabled=False,
            )

        _validate_formal_runtime_candidate_config(
            enabled=True,
            classroom_runner_enabled=True,
            runtime_enabled=True,
            generation_enabled=True,
            autorun_enabled=True,
        )

    def test_formal_path_prepares_candidate_package_and_issues_full_runtime_only(self):
        calls = []

        class Repository:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def encode_json(value):
                import json

                return json.dumps(value, sort_keys=True)

            @staticmethod
            def get_next_formal_candidate_authority(_conn):
                questions = [
                    {
                        "id": f"question-{index}",
                        "type": "single_choice",
                        "prompt": f"第 {index} 题",
                        "skill": "20以内加减法",
                        "hint": "先观察数量",
                        "explanation": "按步骤计算",
                        "choices": [
                            {"id": "a", "label": "答案甲"},
                            {"id": "b", "label": "答案乙"},
                        ],
                    }
                    for index in range(1, 6)
                ]
                return {
                    "build_item_id": "formal-item-1",
                    "preparation_plan_id": "formal-plan-1",
                    "course_id": "formal-course-1",
                    "course_version": "1",
                    "grade_code": "primary_1",
                    "subject": "math",
                    "node_code": "addition_within_20",
                    "title": "20以内加法",
                    "objective": "理解并练习20以内加法",
                    "content_json": json.dumps(
                        {
                            "schemaVersion": "mira.learning.course.v1",
                            "sessionKind": "lesson",
                            "outcomeMode": "scored_deterministic",
                            "intro": "通过数量变化学习加法。",
                            "estimatedMinutes": 15,
                            "questions": questions,
                            "teachingFlow": {
                                "schemaVersion": (
                                    "mira.learning.teaching-flow.v1"
                                ),
                                "teach": {
                                    "title": "理解加法",
                                    "sayText": "把两组数量合起来。",
                                    "keyPoints": ["先数第一组", "再合并第二组"],
                                },
                                "demoQuestionId": "question-1",
                                "guidedQuestionIds": [
                                    "question-2",
                                    "question-3",
                                ],
                                "independentQuestionIds": [
                                    "question-4",
                                    "question-5",
                                ],
                                "recap": {"sayText": "加法表示合起来。"},
                            },
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "target_spec_json": {
                        "schemaVersion": "target.v1",
                    },
                    "attempt_ordinal": 1,
                }

            @staticmethod
            def reserve_formal_runtime_package(_conn, **kwargs):
                calls.append(("package", kwargs))
                return {
                    "id": "formal-package-1",
                    "version": 1,
                    "status": "candidate",
                }, True

        class Validator:
            @staticmethod
            def validate_formal_runtime_package(**kwargs):
                calls.append(("validate", kwargs))
                return {"valid": True, "contractVersion": "formal-package.v1"}

        class Forbidden:
            def __getattr__(self, name):
                raise AssertionError(f"legacy formal call forbidden: {name}")

        class Runtime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                calls.append(("runtime", kwargs))
                return {
                    "ok": True,
                    "runtime": {
                        "id": "formal-runtime-1",
                        "requestId": kwargs["runtime_request_id"],
                        "status": "generating",
                    },
                }

        service = object.__new__(LessonPackageService)
        service.repository = Repository()
        service.validator = Validator()
        service.adapter = Forbidden()
        service.media_service = Forbidden()
        service._formal_target_fingerprint = lambda _value: "7" * 64

        generated = service.process_next_formal_candidate(Runtime())

        self.assertEqual(generated.payload["status"], "generating")
        self.assertEqual([name for name, _value in calls], [
            "validate", "package", "runtime"
        ])
        issued = calls[-1][1]
        self.assertEqual(issued["build_item_id"], "formal-item-1")
        self.assertEqual(issued["package_id"], "formal-package-1")
        self.assertEqual(issued["target_fingerprint"], "7" * 64)
        self.assertEqual(
            issued["runtime_request_id"],
            "mira-formal-runtime-formal-item-1-attempt-1",
        )
        validated = calls[0][1]
        self.assertEqual(len(validated["source_course_content_sha256"]), 64)
        self.assertEqual(len(validated["teaching_brief_sha256"]), 64)
        self.assertEqual(
            validated["teaching_brief"]["course"]["id"], "formal-course-1"
        )

    def test_formal_path_missing_locked_content_fails_before_runtime(self):
        runtime_calls = []

        class Repository:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_next_formal_candidate_authority(_conn):
                return {
                    "build_item_id": "formal-item-missing-content",
                    "course_id": "formal-course-missing-content",
                    "course_version": "1",
                    "attempt_ordinal": 1,
                    "target_spec_json": {"schemaVersion": "target.v1"},
                }

        class Runtime:
            @staticmethod
            def issue_candidate_generation(**kwargs):
                runtime_calls.append(kwargs)
                raise AssertionError("invalid authority must not reach Runtime")

        service = object.__new__(LessonPackageService)
        service.repository = Repository()
        service._formal_target_fingerprint = lambda _value: "7" * 64

        with self.assertRaises(ApiError) as raised:
            service.process_next_formal_candidate(Runtime())

        self.assertEqual(
            raised.exception.code, "formal_candidate_course_content_invalid"
        )
        self.assertEqual(runtime_calls, [])

    def test_configured_formal_runner_never_falls_back_to_legacy_queue(self):
        class Packages:
            legacy_calls = 0
            formal_calls = 0

            def process_next_pending(self):
                self.legacy_calls += 1
                raise AssertionError("legacy queue must stay untouched")

            def process_next_formal_candidate(self, runtime):
                self.formal_calls += 1
                self.runtime = runtime
                return LessonPackageGenerationResult(
                    payload={
                        "ok": True,
                        "status": "generating",
                        "job": {"requestId": "formal-runner-request-1"},
                    },
                    status_code=202,
                )

        packages = Packages()
        runtime = object()
        runner = LearningClassroomGenerationRunner()
        app = type(
            "App",
            (),
            {"config": {"LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED": True}},
        )()

        result = runner.run_configured_once(
            app=app,
            lesson_packages=packages,
            full_runtime=runtime,
            checked_at_ms=901,
        )

        self.assertEqual(result["status"], "generating")
        self.assertEqual(packages.formal_calls, 1)
        self.assertEqual(packages.legacy_calls, 0)
        self.assertIs(packages.runtime, runtime)

    def test_no_pending_job_is_an_observable_noop(self):
        runner = LearningClassroomGenerationRunner()
        result = runner.run_once(process_next=lambda: None, checked_at_ms=123)
        self.assertIsNone(result)
        self.assertEqual(runner.status()["lastCheckedAt"], 123)
        self.assertEqual(runner.status()["lastResult"], {})
        self.assertEqual(runner.status()["lastError"], "")

    def test_records_one_published_job_per_pass(self):
        runner = LearningClassroomGenerationRunner()
        calls = []

        def process_next():
            calls.append(True)
            return LessonPackageGenerationResult(
                payload={
                    "ok": True,
                    "status": "published",
                    "job": {"requestId": "classroom-runner-1"},
                },
                status_code=200,
            )

        result = runner.run_once(process_next=process_next, checked_at_ms=456)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "published")
        self.assertEqual(runner.status()["lastRequestId"], "classroom-runner-1")
        self.assertEqual(runner.status()["lastError"], "")

    def test_records_safe_failure_and_keeps_the_runner_retryable(self):
        runner = LearningClassroomGenerationRunner()
        failed = LessonPackageGenerationResult(
            payload={
                "ok": False,
                "status": "failed",
                "message": "provider unavailable",
                "job": {"requestId": "classroom-runner-failed"},
            },
            status_code=422,
        )
        result = runner.run_once(process_next=lambda: failed, checked_at_ms=789)
        self.assertFalse(result["ok"])
        self.assertEqual(runner.status()["lastError"], "provider unavailable")

        recovered = runner.run_once(
            process_next=lambda: LessonPackageGenerationResult(
                payload={
                    "ok": True,
                    "status": "published",
                    "job": {"requestId": "classroom-runner-recovered"},
                },
                status_code=200,
            ),
            checked_at_ms=790,
        )
        self.assertTrue(recovered["ok"])
        self.assertEqual(runner.status()["lastError"], "")

    def test_exception_is_visible_and_propagates_to_thread_boundary(self):
        runner = LearningClassroomGenerationRunner()

        def explode():
            raise RuntimeError("database temporarily unavailable")

        with self.assertRaises(RuntimeError):
            runner.run_once(process_next=explode, checked_at_ms=900)
        self.assertEqual(
            runner.status()["lastError"],
            "database temporarily unavailable",
        )


if __name__ == "__main__":
    unittest.main()
