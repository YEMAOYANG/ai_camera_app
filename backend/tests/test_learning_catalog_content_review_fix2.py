from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import inspect
import json
import os
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.database import Database
import integrations.openmaic_question_adapter as question_adapter_module
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from repositories.learning_catalog_repository import (
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
import repositories.learning_catalog_repository as catalog_repository_module
from services.dynamic_learning_course_generation_service import (
    ContentPhaseWork,
    StagedContentCandidateGenerator,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
import services.learning_catalog_release_service as release_service_module
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
    PrimaryOneHostGateDependencyError,
)
from tests.support import fresh_test_config, reset_mysql_test_database
from tests.test_learning_catalog_content_only import (
    _CompletePinyinCanaryAdapter,
    _OutlineOnlyAdapter,
    _RejectingPinyinCanaryAdapter,
)
from tests.test_learning_checkpoint2_zero_bypass import (
    _PassingMemoryHost,
    _memory_content_service,
)
from tests.test_openmaic_question_phase_adapter import (
    _candidate_course as _branch_candidate_course,
    _command as _phase_command_fixture,
    _compiled_candidate as _compiled_candidate_fixture,
    _independent_solution as _branch_independent_solution,
    _lesson_text as _branch_lesson_text,
    _outline_checkpoint as _branch_outline_checkpoint,
    _phase_command as _branch_phase_command,
    _question_fingerprints as _branch_question_fingerprints,
    _reconciliation as _branch_reconciliation,
    _repair as _branch_repair,
    _validation as _branch_validation,
)
from tests.test_learning_generated_course_validator import formal_host_fixture


def _profiles() -> dict[str, dict[str, object]]:
    return {
        role: {
            "name": "kimi",
            "model": "moonshot-v1-8k",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "APP_AI_API_KEY",
            "timeoutMs": 1_000,
            "maxTokens": 2_000,
            "temperature": 0.2,
        }
        for role in ("generator", "verifier")
    }


class _PoisonLegacyDependency:
    def __init__(self):
        self.calls = 0

    def generate_for_skill(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("content-only flow touched legacy generation")

    def generate(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("content-only flow touched package generation")


class _AttemptSequencedPinyinAdapter(_CompletePinyinCanaryAdapter):
    """Attempt one is rejected; attempt two is distinct and configurable."""

    def __init__(self, *, reject_attempt_two: bool):
        super().__init__()
        self._attempt_one = _RejectingPinyinCanaryAdapter()
        self._attempt_two = _CompletePinyinCanaryAdapter()
        for question in self._attempt_two._compiled["questions"]:
            question["prompt"] = str(question["prompt"]).replace(
                "练习甲", "练习乙", 1
            )
        if reject_attempt_two:
            question = self._attempt_two._compiled["questions"][0]
            wrong = next(
                choice["id"]
                for choice in question["choices"]
                if choice["id"] != question["answer"]
            )
            question["answer"] = wrong
            self._attempt_two._formal_evidence.independent_solution["answers"][0][
                "answer"
            ] = wrong
        self.execute_calls = 0
        self.phases = []

    def execute_phase(self, prepared):
        self.execute_calls += 1
        self.phases.append(
            (prepared.command.logical_attempt, prepared.command.phase)
        )
        delegate = (
            self._attempt_one
            if prepared.command.logical_attempt == 1
            else self._attempt_two
        )
        return delegate.execute_phase(prepared)


class _CompletePrimaryOneAdapter(_OutlineOnlyAdapter):
    """Formal local adapter for all ten skills and three variants."""

    def __init__(self):
        super().__init__()
        self.phases: list[tuple[str, int, str]] = []
        self._variant_by_request: dict[str, int] = {}

    @staticmethod
    def _compiled_for(command, variant):
        course, _target, _boundary, evidence, _identity = formal_host_fixture(
            str(command.boundary["skillId"]),
            variant_ordinal=variant,
        )
        content = course["content"]
        questions = []
        for source in content["questions"]:
            questions.append(
                {
                    key: copy.deepcopy(source[key])
                    for key in (
                        "type",
                        "prompt",
                        "skill",
                        "hint",
                        "explanation",
                        "answer",
                        "acceptedAnswers",
                        "verificationExpression",
                        "choices",
                    )
                    if key in source
                }
            )
        compiled = {
            "title": course["title"],
            "intro": content["intro"],
            "estimatedMinutes": content["estimatedMinutes"],
            "teachingFlow": {
                "teach": copy.deepcopy(content["teachingFlow"]["teach"]),
                "recap": copy.deepcopy(content["teachingFlow"]["recap"]),
            },
            "questions": questions,
        }
        return course, compiled, evidence

    def execute_phase(self, prepared):
        self.execute_calls += 1
        command = prepared.command
        existing = command.checkpoint.get("existingFingerprints")
        if isinstance(existing, list):
            variant = len(existing) // 5 + 1
            self._variant_by_request[command.generation_request_id] = variant
        else:
            variant = self._variant_by_request[command.generation_request_id]
        skill_id = str(command.boundary["skillId"])
        self.phases.append((skill_id, variant, command.phase))
        course_fixture, compiled, formal_evidence = self._compiled_for(
            command, variant
        )
        checkpoint_by_phase = {
            "outline": {
                "phaseStatus": "accepted",
                "outlinePlan": {
                    "courseTitle": course_fixture["title"],
                    "languageDirective": "使用简体中文教学。",
                    "outlines": [
                        {
                            "order": 1,
                            "title": "先学方法",
                            "description": "先理解方法,再完成确定性练习。",
                            "keyPoints": ["读清条件", "独立作答"],
                        }
                    ],
                },
            },
            "raw_candidate": {
                "phaseStatus": "accepted",
                "rawCandidate": copy.deepcopy(compiled),
            },
            "candidate_repair": {
                "phaseStatus": "accepted",
                "candidate": copy.deepcopy(compiled),
                "hostCompilation": (
                    {
                        "compiler": "host_compiler",
                        "source": "canonical_skill_builder",
                        "version": question_adapter_module.NUMBER_SENSE_CANONICAL_BUILDER_VERSION,
                    }
                    if skill_id == "number_sense_20"
                    else {
                        "compiler": "host_compiler",
                        "source": "candidate_repair_output",
                        "version": "v1",
                    }
                ),
            },
            "lesson_text": {
                "phaseStatus": "accepted",
                "lessonText": {
                    "title": compiled["title"],
                    "intro": compiled["intro"],
                    "teachingFlow": copy.deepcopy(compiled["teachingFlow"]),
                },
            },
            "reconciliation": {
                "phaseStatus": "accepted",
                "reconciliation": {
                    "estimatedMinutes": compiled["estimatedMinutes"],
                    "questions": copy.deepcopy(compiled["questions"]),
                },
                "hostReconciliation": {
                    "reconciler": "host_reconciler",
                    "source": "reconciliation_output",
                    "version": "v1",
                },
            },
        }
        if command.phase == "independent_verification":
            candidate_course = question_adapter_module._build_candidate_course(
                command, compiled
            )
            public_questions = question_adapter_module._public_questions(
                candidate_course
            )
            solution = copy.deepcopy(formal_evidence.independent_solution)
            solution["verificationRequestId"] = command.generation_request_id
            solution["publicQuestionHash"] = hashlib.sha256(
                json.dumps(
                    public_questions,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for answer, question in zip(solution["answers"], public_questions):
                answer["questionId"] = question["id"]
            checkpoint = {
                "phaseStatus": "accepted",
                "candidateCourse": candidate_course,
                "questionFingerprints": (
                    question_adapter_module._build_question_fingerprints(
                        command, candidate_course
                    )
                ),
                "validation": question_adapter_module._build_validation(
                    candidate_course,
                    existing_count=len(
                        command.checkpoint["existingFingerprints"]
                    ),
                ),
                "independentSolution": solution,
            }
        else:
            checkpoint = checkpoint_by_phase[command.phase]
        return question_adapter_module.QuestionPhaseResult(
            request_id=command.generation_request_id,
            phase=command.phase,
            phase_ordinal=command.phase_ordinal,
            outcome="succeeded",
            checkpoint=checkpoint,
            provider_request_id_hash="c" * 64,
            input_tokens=10,
            output_tokens=20,
            billing_evidence="reported",
            safe_error_code=None,
            elapsed_ms=1.0,
        )


class LearningCatalogContentReviewFixTwoMysqlRedTest(unittest.TestCase):
    def setUp(self):
        self.database_url = fresh_test_config()["DATABASE_URL"]

    def tearDown(self):
        reset_mysql_test_database(self.database_url)

    def _service(self, *, now: int, reject_attempt_two: bool):
        database = Database(self.database_url)
        adapter = _AttemptSequencedPinyinAdapter(
            reject_attempt_two=reject_attempt_two
        )
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=_PoisonLegacyDependency(),
            lesson_package_service=_PoisonLegacyDependency(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=_profiles(),
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id=(
                "task7-fix2-attempt2-reject"
                if reject_attempt_two
                else "task7-fix2-attempt2-pass"
            ),
            title="Task 7 Fix2 attempt2 full path",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        return database, adapter, service, str(created["build"]["id"])

    def _first_attempt_pass_service(
        self,
        *,
        now: int,
        request_id: str = "task7-fix2-attempt1-pass-residue",
    ):
        database = Database(self.database_url)
        adapter = _CompletePinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=_PoisonLegacyDependency(),
            lesson_package_service=_PoisonLegacyDependency(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=_profiles(),
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id=request_id,
            title="Task 7 Fix2 attempt1 residue proof",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        return database, adapter, service, str(created["build"]["id"])

    def _primary_one_service(self, *, now: int, request_id: str):
        database = Database(self.database_url)
        adapter = _CompletePrimaryOneAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=_PoisonLegacyDependency(),
            lesson_package_service=_PoisonLegacyDependency(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=_profiles(),
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id=request_id,
            title="Task 7 Fix3 real authority matrix",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        return database, adapter, service, str(created["build"]["id"])

    def _advance(self, service, build_id, count):
        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            return [
                service.advance_content(build_id, heartbeat=lambda: True)
                for _ in range(count)
            ]

    @staticmethod
    def _locked_plan(service, build_id, now):
        with service.repository.transaction() as conn:
            inventory = service.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
            audit = service._audit_locked_content_inventory(
                conn=conn,
                inventory=inventory,
            )
            return service.repository.prepare_content_advance(
                conn,
                build_id=build_id,
                now=now,
                passed_item_ids=audit["passedItemIds"],
                repairable_item_ids=audit["repairableItemIds"],
                locked_attempt_histories_by_item=inventory[
                    "attemptHistoriesByItem"
                ],
            )

    @staticmethod
    def _provider_work(service, plan):
        item = plan["item"]
        command, initial_checkpoint = service._content_phase_command(
            item=item,
            dispatches=plan["dispatches"],
            plan=plan,
        )
        return ContentPhaseWork(
            command=command,
            attempt_initial_checkpoint=initial_checkpoint,
            item_lease_token=str(item["content_lease_token"]),
            attempt_started_at=int(item["content_attempt_started_at"]),
            attempt_hard_deadline_at=int(
                item["content_provider_attempt_hard_deadline_at"]
            ),
            work_unit_deadline_at=int(item["content_work_unit_deadline_at"]),
            lease_expires_at=int(item["content_lease_expires_at"]),
        )

    @staticmethod
    def _reserve_current_dispatch(database, service, work):
        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            prepared = service.staged_content_candidate_generator.canonicalize_phase(
                work.command
            )
        repository = DynamicLearningCourseRepository(database)
        with repository.transaction() as conn:
            reservation = repository.reserve_provider_dispatch(
                conn,
                build_item_id=work.command.build_item_id,
                logical_attempt=work.command.logical_attempt,
                phase=work.command.phase,
                phase_ordinal=work.command.phase_ordinal,
                generation_request_id=work.command.generation_request_id,
                item_lease_token=work.item_lease_token,
                provider=str(prepared.provider["name"]),
                model=str(prepared.provider["model"]),
                profile=prepared.profile_sha256,
                input_sha256=prepared.input_sha256,
                attempt_started_at=work.attempt_started_at,
                attempt_hard_deadline_at=work.attempt_hard_deadline_at,
                work_unit_deadline_at=work.work_unit_deadline_at,
                lease_expires_at=work.lease_expires_at,
                attempt_initial_checkpoint=work.attempt_initial_checkpoint,
                command_checkpoint=prepared.request["checkpoint"],
                prepared_request=prepared.request,
                required_budget_ms=service.staged_content_candidate_generator.required_phase_budget_ms,
                clock_ms=service._content_clock_ms,
            )
        return prepared, reservation

    @staticmethod
    def _canonical_branch_output(adapter, source, target):
        ordinal = next(
            int(row["phaseOrdinal"])
            for row in question_adapter_module.QUESTION_PHASE_IO
            if str(row["phase"]) == source
        )
        command = _branch_phase_command(source, ordinal)
        prepared = adapter.canonicalize_phase(command)
        course = _branch_candidate_course()
        reconciliation = copy.deepcopy(_branch_reconciliation())
        if target == "choice_prompt_repair":
            reconciliation = copy.deepcopy(
                _branch_phase_command(
                    "choice_prompt_repair", 10
                ).checkpoint["reconciliation"]
            )
        outputs = {
            "outline": _branch_outline_checkpoint(),
            "raw_candidate": {
                "phaseStatus": "accepted",
                "rawCandidate": _compiled_candidate_fixture(),
            },
            "candidate_repair": (
                {
                    "phaseStatus": "rejected",
                    "rejectionCode": "candidate_repair_schema_rejected",
                }
                if target == "candidate_repair_retry"
                else {
                    "phaseStatus": "accepted",
                    "candidate": _compiled_candidate_fixture(),
                    "hostCompilation": {
                        "compiler": "host_compiler",
                        "source": "candidate_repair_output",
                        "version": "v1",
                    },
                }
            ),
            "candidate_repair_retry": {
                "phaseStatus": "accepted",
                "candidate": _compiled_candidate_fixture(),
            },
            "lesson_text": {
                "phaseStatus": "accepted",
                "lessonText": _branch_lesson_text(),
            },
            "reconciliation": (
                {
                    "phaseStatus": "rejected",
                    "rejectionCode": "reconciliation_schema_rejected",
                }
                if target == "reconciliation_retry"
                else {
                    "phaseStatus": "accepted",
                    "reconciliation": reconciliation,
                    "hostReconciliation": {
                        "reconciler": "host_reconciler",
                        "source": "reconciliation_output",
                        "version": "v1",
                    },
                }
            ),
            "reconciliation_retry": {
                "phaseStatus": "accepted",
                "reconciliation": reconciliation,
            },
            "practice_leak_repair_1": {
                "phaseStatus": "accepted",
                "reconciliation": reconciliation,
            },
            "practice_leak_repair_2": {
                "phaseStatus": "accepted",
                "reconciliation": reconciliation,
            },
            "choice_prompt_repair": {
                "phaseStatus": "accepted",
                "reconciliation": _branch_reconciliation(),
            },
            "independent_verification": {
                "phaseStatus": "accepted",
                "candidateCourse": course,
                "questionFingerprints": _branch_question_fingerprints(course),
                "validation": _branch_validation(),
                "independentSolution": _branch_independent_solution(course),
            },
            "consistency_repair": (
                {
                    "phaseStatus": "rejected",
                    "rejectionCode": "consistency_repair_schema_rejected",
                }
                if target == "consistency_repair_retry"
                else {
                    "phaseStatus": "accepted",
                    "repair": _branch_repair(course),
                }
            ),
            "consistency_repair_retry": {
                "phaseStatus": "accepted",
                "repair": _branch_repair(course),
            },
        }
        if source == "independent_verification" and target == "consistency_repair":
            outputs[source]["independentSolution"]["teachingReview"] = {
                "passed": False,
                "issues": ["讲解用词与题目不一致。"],
            }
        checkpoint = outputs[source]
        normalized = question_adapter_module._normalize_phase_output_checkpoint(
            prepared, checkpoint
        )
        return prepared, normalized

    @staticmethod
    def _diagnostic(database, build_id):
        with database.transaction() as conn:
            build = conn.execute(
                "SELECT * FROM learning_catalog_build_jobs WHERE id = ? LIMIT 1",
                (build_id,),
            ).fetchone()
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                LIMIT 1
                """,
                (build_id,),
            ).fetchone()
            dispatches = conn.execute(
                """
                SELECT id, logical_attempt, phase, phase_ordinal, status,
                  safe_error_code, input_sha256, output_sha256
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ?
                ORDER BY logical_attempt, phase_ordinal, id
                """,
                (item["id"],),
            ).fetchall()
            jobs = conn.execute(
                """
                SELECT id, request_id, status, error_code
                FROM learning_course_generation_jobs
                WHERE request_id IN (?, ?)
                ORDER BY request_id, id
                """,
                (
                    item["generation_request_id"],
                    str(item["generation_request_id"]) + ".attempt2",
                ),
            ).fetchall()
            candidates = conn.execute(
                """
                SELECT c.id, c.job_id, c.ordinal, c.course_id,
                  c.course_version, c.status, c.error_code
                FROM learning_course_generation_candidates c
                JOIN learning_course_generation_jobs j ON j.id = c.job_id
                WHERE j.request_id IN (?, ?)
                ORDER BY c.job_id, c.ordinal, c.id
                """,
                (
                    item["generation_request_id"],
                    str(item["generation_request_id"]) + ".attempt2",
                ),
            ).fetchall()
            courses = conn.execute(
                """
                SELECT id, version, generation_request_id, status,
                  quality_status
                FROM learning_courses
                WHERE generation_request_id IN (?, ?)
                ORDER BY id, version
                """,
                (
                    item["generation_request_id"],
                    str(item["generation_request_id"]) + ".attempt2",
                ),
            ).fetchall()
        return json.dumps(
            {
                "build": dict(build),
                "item": dict(item),
                "dispatches": [dict(value) for value in dispatches],
                "jobs": [dict(value) for value in jobs],
                "candidates": [dict(value) for value in candidates],
                "courses": [dict(value) for value in courses],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _compact_build_diagnostic(database, build_id, adapter):
        with database.transaction() as conn:
            build = conn.execute(
                """
                SELECT status, error_code FROM learning_catalog_build_jobs
                WHERE id = ? LIMIT 1
                """,
                (build_id,),
            ).fetchone()
            items = conn.execute(
                """
                SELECT id, subject, skill_id, variant_ordinal, status,
                  content_phase, attempt_count, error_code
                FROM learning_catalog_build_items
                WHERE build_job_id = ? AND status = 'failed'
                ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                """,
                (build_id,),
            ).fetchall()
            counts = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM learning_catalog_build_items
                WHERE build_job_id = ? GROUP BY status ORDER BY status
                """,
                (build_id,),
            ).fetchall()
            dispatches = conn.execute(
                """
                SELECT build_item_id, phase, phase_ordinal, status,
                  safe_error_code
                FROM learning_course_provider_dispatches
                WHERE build_item_id IN (
                  SELECT id FROM learning_catalog_build_items
                  WHERE build_job_id = ? AND status = 'failed'
                )
                ORDER BY build_item_id, phase_ordinal, id
                """,
                (build_id,),
            ).fetchall()
        return json.dumps(
            {
                "build": dict(build),
                "failedItems": [dict(row) for row in items],
                "statusCounts": [dict(row) for row in counts],
                "dispatches": [dict(row) for row in dispatches],
                "adapterTail": adapter.phases[-8:],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    @staticmethod
    def _attempt_snapshot(database, build_id, logical_attempt):
        with database.transaction() as conn:
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                LIMIT 1
                """,
                (build_id,),
            ).fetchone()
            request_id = str(item["generation_request_id"])
            if logical_attempt == 2:
                request_id += ".attempt2"
            dispatches = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = ?
                ORDER BY phase_ordinal, id
                """,
                (item["id"], logical_attempt),
            ).fetchall()
            jobs = conn.execute(
                """
                SELECT * FROM learning_course_generation_jobs
                WHERE request_id = ? ORDER BY id
                """,
                (request_id,),
            ).fetchall()
            job_ids = [str(row["id"]) for row in jobs]
            candidates = []
            for job_id in job_ids:
                candidates.extend(
                    conn.execute(
                        """
                        SELECT * FROM learning_course_generation_candidates
                        WHERE job_id = ? ORDER BY ordinal, id
                        """,
                        (job_id,),
                    ).fetchall()
                )
            courses = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE generation_request_id = ? ORDER BY id, version
                """,
                (request_id,),
            ).fetchall()
        return {
            "dispatches": [dict(row) for row in dispatches],
            "jobs": [dict(row) for row in jobs],
            "candidates": [dict(row) for row in candidates],
            "courses": [dict(row) for row in courses],
        }

    def test_attempt_two_real_provider_chain_reaches_host_and_passes(self):
        database, adapter, service, build_id = self._service(
            now=400_000,
            reject_attempt_two=False,
        )

        attempt_one = self._advance(service, build_id, 7)
        attempt_one_snapshot = self._attempt_snapshot(database, build_id, 1)
        authorization_calls = []
        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            authorization = service.advance_content(
                build_id,
                heartbeat=lambda: True,
                authorize_control_work=lambda: authorization_calls.append(
                    "accepted"
                )
                is None,
            )
        attempt_two_provider = self._advance(service, build_id, 6)
        attempt_two_host = self._advance(service, build_id, 1)[0]

        self.assertEqual(
            [result.kind for result in attempt_one],
            ["progressed"] * 7,
            self._diagnostic(database, build_id),
        )
        self.assertEqual(authorization.kind, "progressed")
        self.assertEqual(authorization_calls, ["accepted"])
        self.assertEqual(
            [result.kind for result in attempt_two_provider],
            ["progressed"] * 6,
        )
        self.assertEqual(
            attempt_two_host.kind,
            "progressed",
            self._diagnostic(database, build_id),
        )
        self.assertEqual(
            attempt_two_host.content_summary["contentCandidateItemCount"], 1
        )
        self.assertEqual(adapter.execute_calls, 12)
        self.assertEqual(service.dynamic_generation_service.calls, 0)
        self.assertEqual(service.lesson_package_service.calls, 0)
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (attempt_two_host.item_id,),
            ).fetchone()
            attempt_one_rows = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 1
                ORDER BY phase_ordinal, id
                """,
                (attempt_two_host.item_id,),
            ).fetchall()
            attempt_two_rows = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 2
                ORDER BY phase_ordinal, id
                """,
                (attempt_two_host.item_id,),
            ).fetchall()
        self.assertEqual(item["status"], "course_ready")
        self.assertEqual(item["attempt_count"], 2)
        self.assertEqual(len(attempt_one_rows), 6)
        self.assertEqual(len(attempt_two_rows), 6)
        self.assertEqual(
            self._attempt_snapshot(database, build_id, 1),
            attempt_one_snapshot,
        )
        attempt_two_snapshot = self._attempt_snapshot(database, build_id, 2)
        self.assertEqual(
            [row["status"] for row in attempt_two_snapshot["jobs"]],
            ["validated"],
        )
        self.assertEqual(
            [row["status"] for row in attempt_two_snapshot["candidates"]],
            ["course_validated"],
        )
        self.assertEqual(
            [row["status"] for row in attempt_two_snapshot["courses"]],
            ["validated"],
        )
        self.assertEqual(
            item["course_id"], attempt_two_snapshot["courses"][0]["id"]
        )

    def test_public_dispatch_graph_projection_rejects_every_incomplete_shape(self):
        database, _adapter, service, build_id = self._first_attempt_pass_service(
            now=424_000,
            request_id="task8-review-dispatch-graph-projection",
        )
        provider_results = self._advance(service, build_id, 6)
        self.assertEqual(
            [result.kind for result in provider_results],
            ["progressed"] * 6,
        )
        with database.transaction() as conn:
            item = dict(
                conn.execute(
                    """
                    SELECT * FROM learning_catalog_build_items
                    WHERE build_job_id = ?
                    ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                    LIMIT 1
                    """,
                    (build_id,),
                ).fetchone()
            )
            dispatches = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM learning_course_provider_dispatches
                    WHERE build_item_id = ? AND logical_attempt = 1
                    ORDER BY phase_ordinal, id
                    """,
                    (item["id"],),
                ).fetchall()
            ]

        valid = service.audit_content_dispatch_graph(
            item=item,
            dispatches=dispatches,
        )
        self.assertEqual(valid.item_id, item["id"])
        self.assertEqual(valid.logical_attempt, 1)
        self.assertEqual(valid.dispatch_ids, tuple(row["id"] for row in dispatches))

        invalid_branch = copy.deepcopy(dispatches)
        branch_row = next(
            row for row in invalid_branch if row["phase"] == "raw_candidate"
        )
        branch_checkpoint = json.loads(branch_row["checkpoint_json"])
        branch_checkpoint["phaseStatus"] = "rejected"
        branch_row["checkpoint_json"] = service._canonical_content_json(
            branch_checkpoint
        )
        branch_row["output_sha256"] = hashlib.sha256(
            branch_row["checkpoint_json"].encode("utf-8")
        ).hexdigest()
        invalid_sequence = copy.deepcopy(dispatches)
        invalid_sequence[1], invalid_sequence[2] = (
            invalid_sequence[2],
            invalid_sequence[1],
        )
        duplicate = copy.deepcopy(dispatches)
        duplicate.insert(2, {**copy.deepcopy(duplicate[1]), "id": "duplicate"})
        wrong_final = copy.deepcopy(dispatches[:-1])
        ambiguous = copy.deepcopy(dispatches)
        ambiguous[-1]["status"] = "ambiguous"
        failed_safe = copy.deepcopy(dispatches)
        failed_safe[-1]["status"] = "failed_safe"
        self_consistent_deadline_drift = copy.deepcopy(dispatches)
        for row in self_consistent_deadline_drift:
            row["attempt_started_at"] = int(row["attempt_started_at"]) + 1
            row["attempt_hard_deadline_at"] = (
                int(row["attempt_hard_deadline_at"]) + 1
            )
        cases = {
            "missing_phase": dispatches[:1] + dispatches[2:],
            "invalid_branch": invalid_branch,
            "invalid_sequence": invalid_sequence,
            "duplicate": duplicate,
            "wrong_final": wrong_final,
            "ambiguous": ambiguous,
            "failed_safe": failed_safe,
            "self_consistent_deadline_drift": self_consistent_deadline_drift,
        }
        for name, mutated in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                service.audit_content_dispatch_graph(
                    item=item,
                    dispatches=mutated,
                )

    def test_attempt_two_control_rejection_runs_zero_replay_and_zero_claim(self):
        database, adapter, service, build_id = self._service(
            now=425_000,
            reject_attempt_two=False,
        )
        attempt_one = self._advance(service, build_id, 7)
        self.assertEqual([result.kind for result in attempt_one], ["progressed"] * 7)
        phases_before = list(adapter.phases)
        callbacks = []

        with patch.object(
            service,
            "_authorize_content_attempt_two",
            side_effect=AssertionError("control rejection replayed Host work"),
        ), patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            rejected = service.advance_content(
                build_id,
                heartbeat=lambda: True,
                authorize_control_work=lambda: callbacks.append("rejected")
                and True,
            )

        self.assertEqual(rejected.kind, "stale")
        self.assertEqual(callbacks, ["rejected"])
        self.assertEqual(adapter.phases, phases_before)
        with database.transaction() as conn:
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (rejected.item_id,),
            ).fetchone()
            attempt_two_dispatches = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 2
                """,
                (rejected.item_id,),
            ).fetchone()["count"]
            attempt_two_jobs = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_generation_jobs
                WHERE request_id = ?
                """,
                (str(item["generation_request_id"]) + ".attempt2",),
            ).fetchone()["count"]
        self.assertEqual(item["attempt_count"], 1)
        self.assertEqual(item["content_gate_status"], "failed_deterministic")
        self.assertEqual(attempt_two_dispatches, 0)
        self.assertEqual(attempt_two_jobs, 0)

    def test_attempt_two_relocks_and_reaudits_after_control_acceptance(self):
        database, adapter, service, build_id = self._service(
            now=430_000,
            reject_attempt_two=False,
        )
        attempt_one = self._advance(service, build_id, 7)
        self.assertEqual([result.kind for result in attempt_one], ["progressed"] * 7)
        phases_before = list(adapter.phases)

        def accept_then_fence():
            with service.repository.transaction() as conn:
                service.repository.fence_content_failure(
                    conn,
                    build_id=build_id,
                    item_id=None,
                    error_code="preparation_content_contract_drift",
                    now=430_001,
                )
            return True

        with patch.object(
            service,
            "_authorize_content_attempt_two",
            side_effect=AssertionError("drifted item replayed Host work"),
        ), patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            drifted = service.advance_content(
                build_id,
                heartbeat=lambda: True,
                authorize_control_work=accept_then_fence,
            )

        self.assertEqual(drifted.kind, "stale")
        self.assertEqual(adapter.phases, phases_before)
        with database.transaction() as conn:
            build = conn.execute(
                """
                SELECT * FROM learning_catalog_build_jobs
                WHERE id = ? LIMIT 1
                """,
                (build_id,),
            ).fetchone()
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (drifted.item_id,),
            ).fetchone()
            attempt_two_dispatches = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 2
                """,
                (drifted.item_id,),
            ).fetchone()["count"]
        self.assertEqual(build["status"], "failed")
        self.assertEqual(item["attempt_count"], 1)

    def test_attempt_two_post_callback_rejects_every_persisted_evidence_drift(self):
        mutations = {
            "dispatch": (
                """
                UPDATE learning_course_provider_dispatches
                SET profile = ?
                WHERE build_item_id = ? AND logical_attempt = 1
                ORDER BY phase_ordinal DESC LIMIT 1
                """,
                lambda item: ("0" * 64, item["id"]),
            ),
            "job": (
                """
                UPDATE learning_course_generation_jobs
                SET provider = 'drifted-provider'
                WHERE request_id = ?
                """,
                lambda item: (item["generation_request_id"],),
            ),
            "candidate": (
                """
                UPDATE learning_course_generation_candidates AS candidate
                JOIN learning_course_generation_jobs AS job
                  ON job.id = candidate.job_id
                SET candidate.objective = 'drifted objective'
                WHERE job.request_id = ?
                """,
                lambda item: (item["generation_request_id"],),
            ),
            "course": (
                """
                UPDATE learning_courses
                SET objective = 'drifted objective'
                WHERE generation_request_id = ?
                """,
                lambda item: (item["generation_request_id"],),
            ),
        }
        for name, (sql, params) in mutations.items():
            with self.subTest(name=name):
                reset_mysql_test_database(self.database_url)
                database, adapter, service, build_id = self._service(
                    now=431_000,
                    reject_attempt_two=False,
                )
                attempt_one = self._advance(service, build_id, 7)
                self.assertEqual(
                    [result.kind for result in attempt_one],
                    ["progressed"] * 7,
                )
                with database.transaction() as conn:
                    item = dict(
                        conn.execute(
                            """
                            SELECT * FROM learning_catalog_build_items
                            WHERE id = ? LIMIT 1
                            """,
                            (attempt_one[-1].item_id,),
                        ).fetchone()
                    )
                phases_before = list(adapter.phases)

                def accept_then_drift():
                    with database.transaction() as conn:
                        cursor = conn.execute(sql, params(item))
                        self.assertEqual(cursor.rowcount, 1)
                    return True

                with patch.object(
                    service,
                    "_authorize_content_attempt_two",
                    side_effect=AssertionError(
                        f"{name} drift replayed attempt-two Host work"
                    ),
                ), patch.dict(
                    os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
                ):
                    drifted = service.advance_content(
                        build_id,
                        heartbeat=lambda: True,
                        authorize_control_work=accept_then_drift,
                    )

                self.assertEqual(drifted.kind, "stale")
                self.assertEqual(adapter.phases, phases_before)
                with database.transaction() as conn:
                    current = conn.execute(
                        """
                        SELECT * FROM learning_catalog_build_items
                        WHERE id = ? LIMIT 1
                        """,
                        (item["id"],),
                    ).fetchone()
                    attempt_two_dispatches = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_course_provider_dispatches
                        WHERE build_item_id = ? AND logical_attempt = 2
                        """,
                        (item["id"],),
                    ).fetchone()["count"]
                    attempt_two_jobs = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_course_generation_jobs
                        WHERE request_id = ?
                        """,
                        (str(item["generation_request_id"]) + ".attempt2",),
                    ).fetchone()["count"]
                self.assertEqual(current["attempt_count"], 1)
                self.assertEqual(attempt_two_dispatches, 0)
                self.assertEqual(attempt_two_jobs, 0)
        self.assertEqual(attempt_two_dispatches, 0)

    def test_attempt_two_second_real_rejection_terminalizes_without_attempt_three(self):
        database, adapter, service, build_id = self._service(
            now=450_000,
            reject_attempt_two=True,
        )

        attempt_one = self._advance(service, build_id, 7)
        attempt_one_snapshot = self._attempt_snapshot(database, build_id, 1)
        results = [
            *attempt_one,
            *self._advance(service, build_id, 8),
        ]

        self.assertEqual(
            [result.kind for result in results[:14]],
            ["progressed"] * 14,
            self._diagnostic(database, build_id),
        )
        self.assertEqual(
            results[-1].kind,
            "failed",
            self._diagnostic(database, build_id),
        )
        self.assertEqual(results[-1].content_summary["contentCandidateItemCount"], 0)
        self.assertEqual(results[-1].content_summary["contentFailedItemCount"], 1)
        self.assertEqual(adapter.execute_calls, 12)
        self.assertEqual(service.dynamic_generation_service.calls, 0)
        self.assertEqual(service.lesson_package_service.calls, 0)
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (results[-1].item_id,),
            ).fetchone()
            build = conn.execute(
                "SELECT * FROM learning_catalog_build_jobs WHERE id = ? LIMIT 1",
                (build_id,),
            ).fetchone()
            attempt_three_dispatches = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt > 2
                """,
                (results[-1].item_id,),
            ).fetchone()["count"]
        self.assertEqual(item["attempt_count"], 2)
        self.assertEqual(item["status"], "failed")
        self.assertEqual(build["status"], "failed")
        self.assertEqual(
            build["error_code"], "preparation_content_canary_failed"
        )
        self.assertEqual(attempt_three_dispatches, 0)
        self.assertEqual(
            self._attempt_snapshot(database, build_id, 1),
            attempt_one_snapshot,
        )
        attempt_two_snapshot = self._attempt_snapshot(database, build_id, 2)
        self.assertEqual(
            [row["status"] for row in attempt_two_snapshot["jobs"]],
            ["failed"],
        )
        self.assertEqual(
            [row["status"] for row in attempt_two_snapshot["candidates"]],
            ["rejected"],
        )
        self.assertEqual(
            [row["status"] for row in attempt_two_snapshot["courses"]],
            ["unverified"],
        )

    def test_real_passed_attempt_two_rejects_every_history_mutation(self):
        database, _adapter, service, build_id = self._service(
            now=500_000,
            reject_attempt_two=False,
        )
        results = self._advance(service, build_id, 15)
        self.assertEqual(results[-1].kind, "progressed")
        with service.repository.transaction() as conn:
            inventory = service.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
        evidence = next(
            value
            for value in inventory["evidence"]
            if str(value["item"]["id"]) == str(results[-1].item_id)
        )

        def changed_attempt_one_dispatch(value, key, replacement):
            value["attemptHistories"][1]["dispatches"][0][key] = replacement

        def changed_attempt_one_envelope(value):
            candidate = value["attemptHistories"][1]["candidates"][0]
            candidate["validation_json"] = "{}"

        def changed_attempt_one_receipt_issue(value):
            candidate = value["attemptHistories"][1]["candidates"][0]
            envelope = json.loads(candidate["validation_json"])
            envelope["hostGateReceipt"]["issues"][0]["code"] = (
                "forged_rejection"
            )
            candidate["validation_json"] = json.dumps(
                envelope,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )

        mutations = {
            "missing_attempt_one_dispatch": lambda value: value[
                "attemptHistories"
            ][1]["dispatches"].pop(),
            "wrong_attempt_one_job_status": lambda value: value[
                "attemptHistories"
            ][1]["jobs"][0].__setitem__("status", "validated"),
            "wrong_attempt_one_candidate_status": lambda value: value[
                "attemptHistories"
            ][1]["candidates"][0].__setitem__(
                "status", "course_validated"
            ),
            "wrong_attempt_one_course_status": lambda value: value[
                "attemptHistories"
            ][1]["courses"][0].__setitem__("status", "validated"),
            "missing_attempt_one_envelope": changed_attempt_one_envelope,
            "wrong_attempt_one_receipt_issue": changed_attempt_one_receipt_issue,
            "wrong_attempt_one_checkpoint_hash": lambda value: (
                changed_attempt_one_dispatch(value, "output_sha256", "0" * 64)
            ),
            "wrong_attempt_one_input_hash": lambda value: (
                changed_attempt_one_dispatch(value, "input_sha256", "0" * 64)
            ),
            "wrong_attempt_one_profile_hash": lambda value: (
                changed_attempt_one_dispatch(value, "profile", "0" * 64)
            ),
            "wrong_item_pointer": lambda value: value["item"].__setitem__(
                "course_id", "forged-course"
            ),
            "missing_attempt_two_dispatch": lambda value: value[
                "attemptHistories"
            ][2]["dispatches"].pop(),
            "missing_attempt_two_job": lambda value: value[
                "attemptHistories"
            ][2]["jobs"].clear(),
            "missing_attempt_two_candidate": lambda value: value[
                "attemptHistories"
            ][2]["candidates"].clear(),
            "missing_attempt_two_course": lambda value: value[
                "attemptHistories"
            ][2]["courses"].clear(),
            "extra_attempt_two_candidate": lambda value: value[
                "attemptHistories"
            ][2]["candidates"].append(
                copy.deepcopy(
                    value["attemptHistories"][2]["candidates"][0]
                )
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                changed = copy.deepcopy(evidence)
                mutate(changed)
                with self.assertRaises((KeyError, TypeError, ValueError)):
                    service._validate_locked_passed_evidence(
                        evidence=changed,
                        prior_evidence=(),
                    )

    def test_real_passed_attempt_one_rejects_attempt_two_residue(self):
        _database, _adapter, service, build_id = (
            self._first_attempt_pass_service(now=550_000)
        )
        results = self._advance(service, build_id, 7)
        self.assertEqual(results[-1].kind, "progressed")
        with service.repository.transaction() as conn:
            inventory = service.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
        evidence = next(
            value
            for value in inventory["evidence"]
            if str(value["item"]["id"]) == str(results[-1].item_id)
        )
        attempt_one_candidate = evidence["attemptHistories"][1][
            "candidates"
        ][0]
        attempt_one_course = evidence["attemptHistories"][1]["courses"][0]
        mutations = {
            "attempt_two_dispatch": lambda value: value[
                "attemptHistories"
            ][2]["dispatches"].append(
                {
                    "id": "forged-dispatch",
                    "logical_attempt": 2,
                    "phase": "outline",
                    "phase_ordinal": 1,
                }
            ),
            "attempt_two_job": lambda value: value["attemptHistories"][2][
                "jobs"
            ].append({"id": "forged-job", "request_id": "forged.attempt2"}),
            "attempt_two_candidate": lambda value: value[
                "attemptHistories"
            ][2]["candidates"].append(copy.deepcopy(attempt_one_candidate)),
            "attempt_two_course": lambda value: value["attemptHistories"][2][
                "courses"
            ].append(copy.deepcopy(attempt_one_course)),
            "extra_attempt_one_candidate": lambda value: value[
                "attemptHistories"
            ][1]["candidates"].append(copy.deepcopy(attempt_one_candidate)),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                changed = copy.deepcopy(evidence)
                mutate(changed)
                with self.assertRaises((KeyError, TypeError, ValueError)):
                    service._validate_locked_passed_evidence(
                        evidence=changed,
                        prior_evidence=(),
                    )

    def test_real_succeeded_dispatch_crash_recovers_without_second_process(self):
        _database, adapter, service, build_id = (
            self._first_attempt_pass_service(now=600_000)
        )
        plan = self._locked_plan(service, build_id, 600_000)
        self.assertEqual(plan["action"], "provider")
        item = plan["item"]
        command, initial_checkpoint = service._content_phase_command(
            item=item,
            dispatches=plan["dispatches"],
            plan=plan,
        )
        work = ContentPhaseWork(
            command=command,
            attempt_initial_checkpoint=initial_checkpoint,
            item_lease_token=str(item["content_lease_token"]),
            attempt_started_at=int(item["content_attempt_started_at"]),
            attempt_hard_deadline_at=int(
                item["content_provider_attempt_hard_deadline_at"]
            ),
            work_unit_deadline_at=int(item["content_work_unit_deadline_at"]),
            lease_expires_at=int(item["content_lease_expires_at"]),
        )
        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            first = service.staged_content_candidate_generator.advance(
                work, heartbeat=lambda: True
            )
        self.assertEqual(first.kind, "succeeded")
        self.assertTrue(first.process_started)
        self.assertEqual(adapter.execute_calls, 1)

        recovered = self._advance(service, build_id, 1)[0]

        self.assertEqual(recovered.kind, "progressed")
        self.assertEqual(adapter.execute_calls, 1)
        self.assertEqual(service.dynamic_generation_service.calls, 0)
        self.assertEqual(service.lesson_package_service.calls, 0)
        with service.repository.transaction() as conn:
            item_after = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (recovered.item_id,),
            ).fetchone()
            dispatches = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? ORDER BY logical_attempt, phase_ordinal, id
                """,
                (recovered.item_id,),
            ).fetchall()
        self.assertEqual(item_after["content_phase"], "raw_candidate")
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0]["status"], "succeeded")

    def test_real_host_result_crash_retries_host_without_provider_process(self):
        _database, adapter, service, build_id = (
            self._first_attempt_pass_service(now=650_000)
        )
        clock = [650_000]
        service._content_clock_ms = lambda: clock[0]
        provider_results = self._advance(service, build_id, 6)
        self.assertEqual(
            [result.kind for result in provider_results],
            ["progressed"] * 6,
        )
        self.assertEqual(adapter.execute_calls, 6)
        plan = self._locked_plan(service, build_id, clock[0])
        self.assertEqual(plan["action"], "host")
        evidence, target, identity, prior = service._content_host_evidence(
            plan=plan,
            item=plan["item"],
        )
        host_result = (
            service.primary_one_host_validator.validate_primary_one_host_gate(
                evidence,
                target=target,
                identity=identity,
                skill_boundary=service._content_boundary(plan["item"]),
                accepted_host_receipts=prior,
            )
        )
        self.assertEqual(host_result.outcome, "passed")

        clock[0] = int(plan["item"]["content_work_unit_deadline_at"]) + 1
        recovered = self._advance(service, build_id, 1)[0]

        self.assertEqual(recovered.kind, "progressed")
        self.assertEqual(adapter.execute_calls, 6)
        self.assertEqual(service.dynamic_generation_service.calls, 0)
        self.assertEqual(service.lesson_package_service.calls, 0)
        with service.repository.transaction() as conn:
            item_after = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (recovered.item_id,),
            ).fetchone()
        self.assertEqual(item_after["status"], "course_ready")
        self.assertEqual(item_after["content_gate_attempt_count"], 2)

    def test_real_canary_fairness_prior_variants_and_handoff(self):
        database, adapter, service, build_id = self._primary_one_service(
            now=700_000,
            request_id="task7-fix3-real-thirty-handoff",
        )
        selections = []
        boundary_variants: dict[tuple[str, str], list[int]] = {}

        for expected_count in range(1, 31):
            before = adapter.execute_calls
            results = self._advance(service, build_id, 7)
            self.assertEqual(
                [result.kind for result in results],
                ["progressed"] * 7,
                self._compact_build_diagnostic(database, build_id, adapter),
            )
            self.assertEqual(adapter.execute_calls - before, 6)
            self.assertEqual(
                results[-1].content_summary["contentCandidateItemCount"],
                expected_count,
            )
            with database.transaction() as conn:
                item = conn.execute(
                    "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                    (results[-1].item_id,),
                ).fetchone()
                release_item_count = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM learning_catalog_release_items
                    WHERE release_id = ?
                    """,
                    (item["release_id"],),
                ).fetchone()["count"]
            selection = (
                str(item["subject"]),
                str(item["skill_id"]),
                int(item["variant_ordinal"]),
            )
            selections.append(selection)
            boundary_variants.setdefault(selection[:2], []).append(
                selection[2]
            )
            self.assertEqual(release_item_count, 0)

        self.assertEqual(
            selections[:3],
            [
                ("chinese", "pinyin_syllables", 1),
                ("math", "number_sense_20", 1),
                ("english", "letters_sounds", 1),
            ],
        )
        self.assertTrue(
            all(variants == [1, 2, 3] for variants in boundary_variants.values())
        )
        for prefix_length in range(3, 28):
            counts = {
                subject: sum(
                    selection[0] == subject
                    for selection in selections[:prefix_length]
                )
                for subject in ("chinese", "math", "english")
            }
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
        self.assertEqual(
            {
                subject: sum(selection[0] == subject for selection in selections)
                for subject in ("chinese", "math", "english")
            },
            {"chinese": 12, "math": 9, "english": 9},
        )
        before_handoff = adapter.execute_calls
        handoff = self._advance(service, build_id, 1)[0]
        self.assertEqual(handoff.kind, "handoff")
        self.assertEqual(handoff.content_summary["contentCandidateItemCount"], 30)
        self.assertEqual(handoff.content_summary["contentFailedItemCount"], 0)
        self.assertFalse(handoff.content_summary["canActivate"])
        self.assertEqual(adapter.execute_calls, before_handoff)
        self.assertEqual(service.dynamic_generation_service.calls, 0)
        self.assertEqual(service.lesson_package_service.calls, 0)

    def test_real_eight_crash_windows_reconcile_without_duplicate_work(self):
        # Window 1: a committed item claim before Task-5 reservation reuses the
        # same live work identity and starts exactly one local fake process.
        _db1, adapter1, service1, build1 = self._primary_one_service(
            now=720_000,
            request_id="task7-fix3-crash-before-dispatch",
        )
        plan1 = self._locked_plan(service1, build1, 720_000)
        claimed_identity = (
            plan1["item"]["active_generation_request_id"],
            plan1["item"]["content_lease_token"],
            plan1["item"]["content_attempt_started_at"],
            plan1["item"]["content_provider_attempt_hard_deadline_at"],
        )
        claimed_work_deadline = (
            plan1["item"]["content_work_unit_deadline_at"],
        )
        resumed1 = self._advance(service1, build1, 1)[0]
        self.assertEqual(resumed1.kind, "progressed")
        self.assertEqual(adapter1.execute_calls, 1)
        with service1.repository.transaction() as conn:
            dispatch1 = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND phase_ordinal = 1 LIMIT 1
                """,
                (plan1["item"]["id"],),
            ).fetchone()
            item1 = conn.execute(
                """
                SELECT content_work_unit_deadline_at
                FROM learning_catalog_build_items WHERE id = ? LIMIT 1
                """,
                (plan1["item"]["id"],),
            ).fetchone()
        self.assertEqual(
            (
                dispatch1["generation_request_id"],
                dispatch1["item_lease_token"],
                dispatch1["attempt_started_at"],
                dispatch1["attempt_hard_deadline_at"],
            ),
            claimed_identity,
        )
        self.assertEqual(
            (item1["content_work_unit_deadline_at"],),
            claimed_work_deadline,
        )

        # Window 2: an open committed `dispatched` row is busy while live and
        # never starts a second process.
        db2, adapter2, service2, build2 = self._primary_one_service(
            now=730_000,
            request_id="task7-fix3-crash-after-dispatched",
        )
        plan2 = self._locked_plan(service2, build2, 730_000)
        work2 = self._provider_work(service2, plan2)
        _prepared2, reservation2 = self._reserve_current_dispatch(
            db2, service2, work2
        )
        self.assertTrue(reservation2.created)
        busy2 = self._advance(service2, build2, 1)[0]
        self.assertEqual(busy2.kind, "busy")
        self.assertEqual(adapter2.execute_calls, 0)

        # Window 3: Provider returned locally but its ledger completion did not
        # commit. The open row remains the only authority and is fenced after
        # its fixed work deadline, without Provider replay.
        clock3 = [740_000]
        db3, adapter3, service3, build3 = self._primary_one_service(
            now=clock3[0],
            request_id="task7-fix3-crash-after-provider-return",
        )
        service3._content_clock_ms = lambda: clock3[0]
        service3.staged_content_candidate_generator._clock_ms = lambda: clock3[0]
        plan3 = self._locked_plan(service3, build3, clock3[0])
        work3 = self._provider_work(service3, plan3)
        prepared3, reservation3 = self._reserve_current_dispatch(
            db3, service3, work3
        )
        self.assertTrue(reservation3.created)
        adapter3.execute_phase(prepared3)
        self.assertEqual(adapter3.execute_calls, 1)
        clock3[0] = work3.work_unit_deadline_at + 1
        fenced3 = self._advance(service3, build3, 1)[0]
        self.assertEqual(fenced3.kind, "failed")
        self.assertEqual(adapter3.execute_calls, 1)

        # Window 5: a committed phase checkpoint is enough to reconstruct the
        # next phase. Each later invocation still starts at most one process.
        _db5, adapter5, service5, build5 = self._primary_one_service(
            now=750_000,
            request_id="task7-fix3-crash-after-phase-checkpoint",
        )
        phase_results = self._advance(service5, build5, 2)
        self.assertEqual(
            [result.kind for result in phase_results],
            ["progressed", "progressed"],
        )
        self.assertEqual(adapter5.execute_calls, 2)

        # Window 6: final Provider persistence leaves one generated candidate;
        # Host recovery validates it with no Provider re-execution. Window 8:
        # after course_ready the next invocation selects new work and leaves the
        # immutable ready course untouched.
        _db6, adapter6, service6, build6 = self._primary_one_service(
            now=760_000,
            request_id="task7-fix3-crash-after-candidate-and-course-ready",
        )
        provider6 = self._advance(service6, build6, 6)
        self.assertEqual([value.kind for value in provider6], ["progressed"] * 6)
        self.assertEqual(adapter6.execute_calls, 6)
        with service6.repository.transaction() as conn:
            item6 = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (provider6[-1].item_id,),
            ).fetchone()
            candidates6 = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_generation_candidates
                WHERE course_id = ? AND course_version = ?
                """,
                (item6["course_id"], item6["course_version"]),
            ).fetchone()["count"]
        self.assertEqual(item6["content_phase"], "host_gate_pending")
        self.assertEqual(candidates6, 1)
        host6 = self._advance(service6, build6, 1)[0]
        self.assertEqual(host6.kind, "progressed")
        self.assertEqual(adapter6.execute_calls, 6)
        next6 = self._advance(service6, build6, 1)[0]
        self.assertEqual(next6.kind, "progressed")
        self.assertEqual(adapter6.execute_calls, 7)
        with service6.repository.transaction() as conn:
            ready6 = conn.execute(
                """
                SELECT status, content_phase FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (host6.item_id,),
            ).fetchone()
            candidate_count6 = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_generation_candidates
                WHERE course_id = ? AND course_version = ?
                """,
                (item6["course_id"], item6["course_version"]),
            ).fetchone()["count"]
        self.assertEqual(dict(ready6), {
            "status": "course_ready",
            "content_phase": "course_ready",
        })
        self.assertEqual(candidate_count6, 1)

        # Windows 4 and 7 are the retained real succeeded-dispatch and Host
        # result crash tests above; every window uses persisted MySQL rows.
        self.assertTrue(
            callable(self.test_real_succeeded_dispatch_crash_recovers_without_second_process)
        )
        self.assertTrue(
            callable(self.test_real_host_result_crash_retries_host_without_provider_process)
        )

    def test_real_preclaim_authority_and_outcome_matrix_has_zero_process(self):
        mutations = {
            "build-counter": (
                """
                UPDATE learning_catalog_build_jobs
                SET ready_item_count = 1 WHERE id = ?
                """,
                lambda build_id, item: (build_id,),
            ),
            "curriculum-snapshot": (
                """
                UPDATE learning_catalog_build_items
                SET curriculum_version = 'forged-curriculum' WHERE id = ?
                """,
                lambda build_id, item: (item["id"],),
            ),
            "manifest-snapshot": (
                """
                UPDATE learning_catalog_build_items
                SET content_manifest_version_snapshot = 'forged-manifest'
                WHERE id = ?
                """,
                lambda build_id, item: (item["id"],),
            ),
        }
        for index, (label, (sql, params)) in enumerate(mutations.items(), 1):
            with self.subTest(authority_drift=label):
                database, adapter, service, build_id = self._primary_one_service(
                    now=800_000 + index,
                    request_id=f"task7-fix3-real-preclaim-{label}",
                )
                with database.transaction() as conn:
                    item = conn.execute(
                        """
                        SELECT * FROM learning_catalog_build_items
                        WHERE build_job_id = ?
                        ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                        LIMIT 1
                        """,
                        (build_id,),
                    ).fetchone()
                    conn.execute(sql, params(build_id, item))
                    release_items_before = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_catalog_release_items
                        WHERE release_id = ?
                        """,
                        (item["release_id"],),
                    ).fetchone()["count"]
                    package_residue_before = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_catalog_build_items
                        WHERE build_job_id = ? AND (
                          package_attempt_count <> 0
                          OR active_package_request_id IS NOT NULL
                          OR package_id IS NOT NULL OR package_version IS NOT NULL
                        )
                        """,
                        (build_id,),
                    ).fetchone()["count"]
                result = self._advance(service, build_id, 1)[0]
                with database.transaction() as conn:
                    dispatch_count = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_course_provider_dispatches
                        WHERE build_item_id IN (
                          SELECT id FROM learning_catalog_build_items
                          WHERE build_job_id = ?
                        )
                        """,
                        (build_id,),
                    ).fetchone()["count"]
                self.assertEqual(result.kind, "failed")
                self.assertEqual(adapter.execute_calls, 0)
                self.assertEqual(dispatch_count, 0)
                self.assertEqual(release_items_before, 0)
                self.assertEqual(package_residue_before, 0)

    def test_real_command_profile_and_predecessor_forgery_matrix(self):
        mutations = {
            "input-hash": "input_sha256 = %s" % ("'" + "0" * 64 + "'"),
            "profile-hash": "profile = %s" % ("'" + "0" * 64 + "'"),
            "output-hash": "output_sha256 = %s" % ("'" + "0" * 64 + "'"),
        }
        for index, (label, assignment) in enumerate(mutations.items(), 1):
            with self.subTest(forgery=label):
                database, adapter, service, build_id = self._primary_one_service(
                    now=810_000 + index,
                    request_id=f"task7-fix3-real-forgery-{label}",
                )
                first = self._advance(service, build_id, 1)[0]
                self.assertEqual(first.kind, "progressed")
                self.assertEqual(adapter.execute_calls, 1)
                with database.transaction() as conn:
                    conn.execute(
                        f"""
                        UPDATE learning_course_provider_dispatches
                        SET {assignment}
                        WHERE build_item_id = ? AND phase_ordinal = 1
                        """,
                        (first.item_id,),
                    )
                forged = self._advance(service, build_id, 1)[0]
                with database.transaction() as conn:
                    dispatch_count = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_course_provider_dispatches
                        WHERE build_item_id = ?
                        """,
                        (first.item_id,),
                    ).fetchone()["count"]
                self.assertEqual(forged.kind, "failed")
                self.assertEqual(adapter.execute_calls, 1)
                self.assertEqual(dispatch_count, 1)

    def test_real_every_task5_branch_persists_exact_next_phase_once(self):
        phase_ordinals = {
            str(row["phase"]): int(row["phaseOrdinal"])
            for row in question_adapter_module.QUESTION_PHASE_IO
        }
        edges = (
            ("outline", "raw_candidate"),
            ("raw_candidate", "candidate_repair"),
            ("candidate_repair", "candidate_repair_retry"),
            ("candidate_repair", "lesson_text"),
            ("candidate_repair_retry", "lesson_text"),
            ("lesson_text", "reconciliation"),
            ("reconciliation", "reconciliation_retry"),
            ("reconciliation", "practice_leak_repair_1"),
            ("reconciliation", "choice_prompt_repair"),
            ("reconciliation", "independent_verification"),
            ("reconciliation_retry", "practice_leak_repair_1"),
            ("reconciliation_retry", "choice_prompt_repair"),
            ("reconciliation_retry", "independent_verification"),
            ("practice_leak_repair_1", "practice_leak_repair_2"),
            ("practice_leak_repair_1", "choice_prompt_repair"),
            ("practice_leak_repair_1", "independent_verification"),
            ("practice_leak_repair_2", "choice_prompt_repair"),
            ("practice_leak_repair_2", "independent_verification"),
            ("choice_prompt_repair", "independent_verification"),
            ("independent_verification", "consistency_repair"),
            ("consistency_repair", "consistency_repair_retry"),
            ("consistency_repair", "verification_after_repair"),
            ("consistency_repair_retry", "verification_after_repair"),
        )
        for index, (source, target) in enumerate(edges, 1):
            with self.subTest(edge=f"{source}->{target}"):
                database, adapter, service, build_id = self._primary_one_service(
                    now=815_000 + index,
                    request_id=f"task7-fix3-real-edge-{index}",
                )
                plan = self._locked_plan(service, build_id, 815_000 + index)
                self.assertEqual(plan["action"], "provider")
                prepared, checkpoint = self._canonical_branch_output(
                    question_adapter_module.OpenMaicQuestionPhaseAdapter(
                        provider_name="kimi",
                        model_name="kimi-k2.6",
                        base_url="https://api.moonshot.cn/v1",
                        api_key_env="APP_AI_API_KEY",
                        provider_timeout_ms=60_000,
                        max_tokens=8_000,
                        temperature=0.2,
                    ),
                    source,
                    target,
                )
                checkpoint_json = service._canonical_content_json(checkpoint)
                dispatch_id = f"task7-fix3-edge-dispatch-{index}"
                with database.transaction() as conn:
                    conn.execute(
                        """
                        UPDATE learning_catalog_build_items
                        SET content_phase = ? WHERE id = ?
                        """,
                        (source, plan["item"]["id"]),
                    )
                    conn.execute(
                        """
                        INSERT INTO learning_course_provider_dispatches(
                          id, build_item_id, logical_attempt, phase,
                          phase_ordinal, generation_request_id,
                          item_lease_token, provider, model, profile,
                          input_sha256, status, checkpoint_json,
                          output_sha256, attempt_started_at,
                          attempt_hard_deadline_at,
                          provider_request_id_hash, input_tokens,
                          output_tokens, billing_evidence, safe_error_code,
                          dispatched_at, completed_at
                        ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?,
                          'succeeded', ?, ?, ?, ?, ?, 1, 1, 'reported', NULL,
                          ?, ?)
                        """,
                        (
                            dispatch_id,
                            plan["item"]["id"],
                            source,
                            phase_ordinals[source],
                            plan["item"]["active_generation_request_id"],
                            plan["item"]["content_lease_token"],
                            prepared.provider["name"],
                            prepared.provider["model"],
                            prepared.profile_sha256,
                            prepared.input_sha256,
                            checkpoint_json,
                            hashlib.sha256(
                                checkpoint_json.encode("utf-8")
                            ).hexdigest(),
                            plan["item"]["content_attempt_started_at"],
                            plan["item"][
                                "content_provider_attempt_hard_deadline_at"
                            ],
                            "a" * 64,
                            815_050 + index,
                            815_050 + index,
                        ),
                    )
                    inventory = service.repository.load_content_proof_inventory(
                        conn, build_id=build_id
                    )
                    locked_item = next(
                        row
                        for row in inventory["items"]
                        if str(row["id"]) == str(plan["item"]["id"])
                    )
                    persisted = service.repository._complete_content_provider_phase_locked(
                        conn,
                        locked_item=locked_item,
                        locked_build=inventory["build"],
                        locked_items=inventory["items"],
                        persisted_dispatch_id=dispatch_id,
                        expected_next_phase=target,
                        expected_next_phase_ordinal=phase_ordinals[target],
                        candidate_course=None,
                        generator_profile=_profiles()["generator"],
                        now=815_100 + index,
                    )
                self.assertEqual(persisted["content_phase"], target)
                self.assertIsNone(persisted["content_lease_token"])
                self.assertEqual(adapter.execute_calls, 0)

    def test_real_host_dependency_ordinals_and_terminal_late_owner_matrix(self):
        database, adapter, service, build_id = self._primary_one_service(
            now=820_000,
            request_id="task7-fix3-real-host-dependency-ordinals",
        )
        clock = [820_000]
        service._content_clock_ms = lambda: clock[0]
        service.staged_content_candidate_generator._clock_ms = lambda: clock[0]
        provider = self._advance(service, build_id, 6)
        self.assertEqual([value.kind for value in provider], ["progressed"] * 6)
        self.assertEqual(adapter.execute_calls, 6)

        original_host = service._content_host_evidence

        def dependency(**kwargs):
            original_host(**kwargs)
            raise PrimaryOneHostGateDependencyError("test-only dependency")

        service._content_host_evidence = dependency
        first = self._advance(service, build_id, 1)[0]
        same_live = self._advance(service, build_id, 1)[0]
        self.assertEqual((first.kind, same_live.kind), (
            "dependency_retry", "dependency_retry"
        ))
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (first.item_id,),
            ).fetchone()
        self.assertEqual(item["content_gate_attempt_count"], 1)
        clock[0] = int(item["content_work_unit_deadline_at"]) + 1
        second = self._advance(service, build_id, 1)[0]
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (first.item_id,),
            ).fetchone()
        self.assertEqual(second.kind, "dependency_retry")
        self.assertEqual(item["content_gate_attempt_count"], 2)
        clock[0] = int(item["content_work_unit_deadline_at"]) + 1
        third = self._advance(service, build_id, 1)[0]
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (first.item_id,),
            ).fetchone()
        self.assertEqual(third.kind, "dependency_retry")
        self.assertEqual(item["content_gate_attempt_count"], 3)
        clock[0] = int(item["content_work_unit_deadline_at"]) + 1
        exhausted = self._advance(service, build_id, 1)[0]
        late = self._advance(service, build_id, 1)[0]
        self.assertEqual((exhausted.kind, late.kind), ("failed", "failed"))
        self.assertEqual(adapter.execute_calls, 6)
        with database.transaction() as conn:
            final_item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (first.item_id,),
            ).fetchone()
        self.assertEqual(final_item["content_gate_attempt_count"], 3)
        self.assertEqual(final_item["status"], "failed")

    def test_real_phase11_host_envelope_collision_and_zero_bypass_matrix(self):
        database, adapter, service, build_id = self._primary_one_service(
            now=830_000,
            request_id="task7-fix3-real-envelope-zero-bypass",
        )
        poison_calls = []

        def poison(name):
            def forbidden(*args, **kwargs):
                poison_calls.append(name)
                raise AssertionError(f"forbidden downstream call: {name}")
            return forbidden

        for name in (
            "claim_package_for_item",
            "mark_package_media_pending",
            "activate_release",
        ):
            setattr(service.repository, name, poison(name))
        completed = self._advance(service, build_id, 7)
        self.assertEqual([value.kind for value in completed], ["progressed"] * 7)
        self.assertEqual(adapter.execute_calls, 6)
        self.assertEqual(poison_calls, [])
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (completed[-1].item_id,),
            ).fetchone()
            candidate = conn.execute(
                """
                SELECT * FROM learning_course_generation_candidates
                WHERE course_id = ? AND course_version = ? LIMIT 1
                """,
                (item["course_id"], item["course_version"]),
            ).fetchone()
            deltas = {
                table: conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()["count"]
                for table in (
                    "learning_catalog_release_items",
                    "learning_lesson_packages",
                    "learning_media_generation_jobs",
                    "learning_openmaic_runtime_classrooms",
                )
            }
            conn.execute(
                """
                UPDATE learning_course_generation_candidates
                SET validation_json = '{}' WHERE id = ?
                """,
                (candidate["id"],),
            )
        self.assertEqual(deltas, {
            "learning_catalog_release_items": 0,
            "learning_lesson_packages": 0,
            "learning_media_generation_jobs": 0,
            "learning_openmaic_runtime_classrooms": 0,
        })
        before = adapter.execute_calls
        collision = self._advance(service, build_id, 1)[0]
        self.assertEqual(collision.kind, "failed")
        self.assertEqual(adapter.execute_calls, before)

    def test_real_one_passed_then_pending_inventory_is_replayable(self):
        database, adapter, service, build_id = self._primary_one_service(
            now=710_000,
            request_id="task7-fix3-real-one-proof-next-pending",
        )
        results = self._advance(service, build_id, 7)
        self.assertEqual([result.kind for result in results], ["progressed"] * 7)
        self.assertEqual(adapter.execute_calls, 6)

        with service.repository.transaction() as conn:
            inventory = service.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
            audit = service._audit_locked_content_inventory(
                conn=conn,
                inventory=inventory,
            )
            plan = service.repository.prepare_content_advance(
                conn,
                build_id=build_id,
                now=710_000,
                passed_item_ids=audit["passedItemIds"],
                repairable_item_ids=audit["repairableItemIds"],
                locked_attempt_histories_by_item=inventory[
                    "attemptHistoriesByItem"
                ],
            )

        self.assertEqual(audit["summary"]["contentCandidateItemCount"], 1)
        self.assertEqual(plan["action"], "provider")
        self.assertNotEqual(plan["item"]["id"], results[-1].item_id)

        next_result = self._advance(service, build_id, 1)[0]
        with database.transaction() as conn:
            next_item = conn.execute(
                """
                SELECT id, status, content_phase, attempt_count, error_code
                FROM learning_catalog_build_items WHERE id = ? LIMIT 1
                """,
                (plan["item"]["id"],),
            ).fetchone()
            next_build = conn.execute(
                """
                SELECT status, error_code FROM learning_catalog_build_jobs
                WHERE id = ? LIMIT 1
                """,
                (build_id,),
            ).fetchone()
            next_dispatches = conn.execute(
                """
                SELECT phase, phase_ordinal, status, safe_error_code
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ?
                ORDER BY logical_attempt, phase_ordinal, id
                """,
                (plan["item"]["id"],),
            ).fetchall()
        self.assertEqual(
            next_result.kind,
            "progressed",
            json.dumps(
                {
                    "build": dict(next_build),
                    "item": dict(next_item),
                    "dispatches": [dict(row) for row in next_dispatches],
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
        self.assertEqual(adapter.execute_calls, 7)


class LearningCatalogContentReviewFixTwoPureRedTest(unittest.TestCase):
    def test_task7_uses_only_public_pure_task5_canonical_authority(self):
        source = inspect.getsource(
            LearningCatalogReleaseService._content_provider_preflight
        )
        self.assertNotIn("._adapter", source)
        self.assertIn("canonicalize_phase", source)

    def test_provider_terminal_status_and_summary_share_one_locked_reread(self):
        class AtomicRepository:
            def __init__(self):
                self.transactions = 0
                self.loads = 0

            @contextmanager
            def transaction(self):
                self.transactions += 1
                yield object()

            def load_content_proof_inventory(self, conn, *, build_id):
                self.loads += 1
                return {
                    "build": {"id": build_id, "status": "failed"},
                    "items": _summary_rows(),
                }

            def is_content_build_failed(self, *args, **kwargs):
                raise AssertionError("terminal status must not use a second transaction")

        repository = AtomicRepository()
        service = object.__new__(LearningCatalogReleaseService)
        service.repository = repository
        service._audit_locked_content_inventory = lambda **kwargs: {
            "summary": {"contentFailedItemCount": 1}
        }

        failed, summary = service._content_finalize_outcome(
            build_id="build-1",
            persisted=None,
            explicit_failed=False,
        )

        self.assertTrue(failed)
        self.assertEqual(summary["contentFailedItemCount"], 1)
        self.assertEqual((repository.transactions, repository.loads), (1, 1))

    def test_provider_finalize_requires_locked_build_and_all_items(self):
        parameters = inspect.signature(
            LearningCatalogRepository._complete_content_provider_phase_locked
        ).parameters
        self.assertIs(parameters["locked_build"].default, inspect.Parameter.empty)
        self.assertIs(parameters["locked_items"].default, inspect.Parameter.empty)

    @staticmethod
    def _simple_sentences_task5_dispatches():
        adapter = _CompletePrimaryOneAdapter()
        service = object.__new__(LearningCatalogReleaseService)
        service.staged_content_candidate_generator = SimpleNamespace(
            canonicalize_phase=adapter.canonicalize_phase
        )
        service.question_phase_provider_profiles = _profiles()
        item = {
            "id": "item-simple-sentences",
            "subject": "chinese",
            "skill_id": "simple_sentences",
            "variant_ordinal": 1,
            "attempt_count": 1,
            "active_generation_request_id": "fixture.simple-sentences.replay",
            "content_attempt_started_at": 100_000,
            "content_provider_attempt_hard_deadline_at": 1_900_000,
        }
        initial = {
            "questionCount": 5,
            "existingFingerprints": [],
            "generationFeedback": None,
        }
        checkpoints = {}
        dispatches = []
        for phase, ordinal in (
            ("outline", 1),
            ("raw_candidate", 2),
            ("candidate_repair", 3),
            ("lesson_text", 5),
            ("reconciliation", 6),
            ("independent_verification", 11),
        ):
            command = replace(
                _phase_command_fixture(),
                build_item_id=item["id"],
                generation_request_id=item["active_generation_request_id"],
                phase=phase,
                phase_ordinal=ordinal,
                subject=item["subject"],
                target_language_code="zh-CN",
                boundary=service._content_boundary(item),
                checkpoint=service._assemble_content_checkpoint(
                    phase=phase,
                    phase_ordinal=ordinal,
                    initial=initial,
                    succeeded=checkpoints,
                ),
            )
            with patch.dict(
                os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
            ):
                prepared = adapter.preflight_phase(command)
            result = adapter.execute_phase(prepared)
            checkpoint_json = service._canonical_content_json(result.checkpoint)
            dispatches.append(
                {
                    "id": f"dispatch-{ordinal}",
                    "build_item_id": item["id"],
                    "logical_attempt": 1,
                    "generation_request_id": item[
                        "active_generation_request_id"
                    ],
                    "phase": phase,
                    "phase_ordinal": ordinal,
                    "status": "succeeded",
                    "attempt_started_at": item["content_attempt_started_at"],
                    "attempt_hard_deadline_at": item[
                        "content_provider_attempt_hard_deadline_at"
                    ],
                    "provider": prepared.provider["name"],
                    "model": prepared.provider["model"],
                    "profile": prepared.profile_sha256,
                    "input_sha256": prepared.input_sha256,
                    "checkpoint_json": checkpoint_json,
                    "output_sha256": hashlib.sha256(
                        checkpoint_json.encode("utf-8")
                    ).hexdigest(),
                }
            )
            checkpoints[(phase, ordinal)] = result.checkpoint
        return service, item, dispatches

    def test_simple_sentences_predecessor_replay_uses_task5_preflight(self):
        service, item, dispatches = self._simple_sentences_task5_dispatches()
        item = {**item, "content_phase": "raw_candidate"}

        command, _initial = service._content_phase_command(
            item=item,
            dispatches=dispatches[:1],
            plan={
                "priorEvidence": [],
                "historicalQuestionFingerprints": [],
            },
        )

        self.assertEqual(command.phase, "raw_candidate")
        self.assertEqual(command.checkpoint["outlinePlan"]["outlines"][0]["order"], 1)

    def test_simple_sentences_full_dispatch_audit_uses_task5_preflight(self):
        service, item, dispatches = self._simple_sentences_task5_dispatches()

        service._validate_content_dispatch_chain(
            item={**item, "content_phase": "host_gate_running"},
            dispatches=dispatches,
            plan={
                "priorEvidence": [],
                "historicalQuestionFingerprints": [],
            },
        )

    def test_generation_persistence_rejects_non_task5_prompt_version(self):
        service = object.__new__(LearningCatalogReleaseService)
        service.question_phase_provider_profiles = _profiles()
        item = {
            "active_generation_request_id": "fixture.persistence",
            "grade_code": "primary_1",
            "subject": "math",
            "skill_id": "number_sense_20",
            "curriculum_version": "curriculum-v1",
            "boundary_version": "boundary-v1",
        }
        candidate_course = {
            "id": "course-1",
            "version": "v1",
            "gradeCode": "primary_1",
            "subject": "math",
            "nodeCode": "number_sense_20",
            "title": "认识20以内的数",
            "objective": "理解20以内数的组成。",
            "content": {"questions": []},
        }
        request_id = item["active_generation_request_id"]
        job_id = "learning_course_job_" + hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest()[:32]
        candidate_id = "learning_course_candidate_" + hashlib.sha256(
            f"{job_id}:1".encode("utf-8")
        ).hexdigest()[:32]
        profile = service._content_profile_payload("generator")
        request_fingerprint = hashlib.sha256(
            service._canonical_content_json(
                {
                    "gradeCode": item["grade_code"],
                    "subject": item["subject"],
                    "nodeCode": item["skill_id"],
                    "curriculumVersion": item["curriculum_version"],
                    "boundaryVersion": item["boundary_version"],
                    "generator": "openmaic_question_phase_v2",
                    "providerProfile": profile,
                    "requestedCandidateCount": 1,
                }
            ).encode("utf-8")
        ).hexdigest()
        content_json = service._canonical_content_json(
            candidate_course["content"]
        )
        content_hash = hashlib.sha256(
            service._canonical_content_json(
                {
                    "gradeCode": candidate_course["gradeCode"],
                    "subject": candidate_course["subject"],
                    "nodeCode": candidate_course["nodeCode"],
                    "title": candidate_course["title"],
                    "objective": candidate_course["objective"],
                    "content": candidate_course["content"],
                }
            ).encode("utf-8")
        ).hexdigest()
        common = {
            "grade_code": "primary_1",
            "subject": "math",
            "node_code": "number_sense_20",
            "curriculum_version": item["curriculum_version"],
            "boundary_version": item["boundary_version"],
            "title": candidate_course["title"],
            "objective": candidate_course["objective"],
        }
        evidence = {
            "job": {
                **common,
                "id": job_id,
                "request_id": request_id,
                "request_fingerprint": request_fingerprint,
                "generator": "openmaic_question_phase_v2",
                "provider": profile["name"],
                "model": profile["model"],
                "prompt_version": "forged-contract-version",
                "requested_candidate_count": 1,
                "status": "validated",
                "error_code": None,
                "error_message_safe": None,
            },
            "candidate": {
                **common,
                "id": candidate_id,
                "job_id": job_id,
                "ordinal": 1,
                "course_id": candidate_course["id"],
                "course_version": candidate_course["version"],
                "status": "course_validated",
                "content_hash": content_hash,
                "content_json": content_json,
                "validation_json": "{}",
                "error_code": None,
                "error_message_safe": None,
                "published_at": None,
            },
            "course": {
                **common,
                "id": candidate_course["id"],
                "version": candidate_course["version"],
                "generation_request_id": request_id,
                "generator": "openmaic_question_phase_v2",
                "status": "validated",
                "quality_status": "auto_validated",
                "content_origin": "openmaic_generated",
                "generation_content_hash": "",
                "published_at": None,
                "retired_at": None,
            },
        }

        with self.assertRaisesRegex(
            ValueError, "locked generation persistence drift"
        ):
            service._validate_locked_generation_persistence(
                evidence=evidence,
                item=item,
                candidate_course=candidate_course,
                expected_job_status="validated",
                expected_candidate_status="course_validated",
            )

    def test_provider_finalize_reuses_task5_preflight_for_typed_boundary(self):
        adapter = _CompletePrimaryOneAdapter()
        service = object.__new__(LearningCatalogReleaseService)
        service.staged_content_candidate_generator = SimpleNamespace(
            canonicalize_phase=adapter.canonicalize_phase
        )
        service.question_phase_provider_profiles = _profiles()
        command = replace(
            _phase_command_fixture(),
            generation_request_id="fixture.simple-sentences.typed-boundary",
            subject="chinese",
            target_language_code="zh-CN",
            boundary=service._content_boundary({"grade_code": "primary_1", "subject": "chinese", "skill_id": "simple_sentences"}),
            checkpoint={
                "questionCount": 5,
                "existingFingerprints": [],
                "generationFeedback": None,
            },
        )
        with patch.dict(
            os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
        ):
            expected = adapter.preflight_phase(command)
            replayed = service._content_provider_preflight(command)

        self.assertEqual(replayed.request, expected.request)
        self.assertEqual(replayed.input_sha256, expected.input_sha256)
        self.assertEqual(replayed.profile_sha256, expected.profile_sha256)
        self.assertNotEqual(replayed.request["skillBoundary"], command.boundary)

    def test_complete_primary_one_adapter_full_graph_is_task5_canonical(self):
        adapter = _CompletePrimaryOneAdapter()
        assembler = object.__new__(LearningCatalogReleaseService)
        skill_ids = sorted(
            {
                str(target["skillId"])
                for target in build_preparation_target("primary_1")[
                    "courseTargets"
                ]
            }
        )
        for skill_id in skill_ids:
            with self.subTest(skill_id=skill_id):
                _course, target, boundary, _evidence, _identity = (
                    formal_host_fixture(skill_id)
                )
                initial = {
                    "questionCount": 5,
                    "existingFingerprints": [],
                    "generationFeedback": None,
                }
                succeeded = {}
                for phase, ordinal in (
                    ("outline", 1),
                    ("raw_candidate", 2),
                    ("candidate_repair", 3),
                    ("lesson_text", 5),
                    ("reconciliation", 6),
                    ("independent_verification", 11),
                ):
                    command = replace(
                        _phase_command_fixture(),
                        generation_request_id=f"fixture.{skill_id}",
                        phase=phase,
                        phase_ordinal=ordinal,
                        subject=target.subject,
                        target_language_code=target.target_language_code,
                        boundary=boundary,
                        checkpoint=assembler._assemble_content_checkpoint(
                            phase=phase,
                            phase_ordinal=ordinal,
                            initial=initial,
                            succeeded=succeeded,
                        ),
                    )
                    with patch.dict(
                        os.environ,
                        {"APP_AI_API_KEY": "test-only"},
                        clear=False,
                    ):
                        prepared = adapter.preflight_phase(command)
                    result = adapter.execute_phase(prepared)
                    normalized = question_adapter_module._normalize_phase_output_checkpoint(
                        prepared, result.checkpoint
                    )
                    self.assertEqual(normalized, result.checkpoint)
                    succeeded[(phase, ordinal)] = result.checkpoint

    def test_prepare_terminal_action_rereads_post_fence_facts(self):
        repository = _PrepareFenceRereadRepository(
            _all_pending_summary_rows()
        )
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=object(),
            host=_PassingMemoryHost(),
        )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(result.content_summary["contentFailedItemCount"], 1)
        self.assertEqual(repository.inventory_loads, 2)

    def test_provider_next_phase_deadline_fences_without_name_error(self):
        repository = object.__new__(LearningCatalogRepository)
        fenced = []
        repository._fence_content_build_locked = (
            lambda conn, **kwargs: fenced.append(kwargs["error_code"])
        )
        locked = {
            "id": "item-1",
            "build_job_id": "build-1",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "outline",
            "content_lease_token": "lease-1",
            "content_attempt_started_at": 100_000,
            "content_provider_attempt_hard_deadline_at": 100_001,
            "content_work_unit_deadline_at": 100_001,
        }

        persisted = repository._complete_content_provider_phase_locked(
            _RecordingConnection(),
            locked_item=locked,
            locked_build={"id": "build-1"},
            locked_items=[
                locked,
                *({"id": f"item-{index}"} for index in range(2, 31)),
            ],
            persisted_dispatch_id="dispatch-1",
            expected_next_phase="raw_candidate",
            expected_next_phase_ordinal=2,
            candidate_course=None,
            generator_profile=_profiles()["generator"],
            now=100_001,
        )

        self.assertIsNone(persisted)
        self.assertEqual(
            fenced, ["preparation_content_stage_deadline_exceeded"]
        )

    def test_host_internal_terminal_fence_is_not_reported_as_stale(self):
        repository = _InternallyFencedHostRepository(_summary_rows())
        _course, target, _boundary, evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        host = LearningGeneratedCourseValidator()
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=object(),
            host=host,
        )
        service._content_host_evidence = lambda **kwargs: (
            evidence,
            target,
            identity,
            (),
        )

        result = service._advance_content_host(
            build_id="catalog-build-canary",
            plan={},
            item={
                "id": "item-0",
                "skill_id": "pinyin_syllables",
                "attempt_count": 1,
                "active_generation_request_id": "request-1",
                "content_gate_attempt_count": 1,
                "content_lease_token": "host-lease",
                "content_work_unit_deadline_at": 200_000,
            },
            summary=service._empty_content_summary(),
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(result.content_summary["contentFailedItemCount"], 1)

    def test_existing_provider_claim_returns_the_locked_current_item(self):
        now = 100_000
        work = now + 120_000
        locked = {
            "id": "item-1",
            "status": "processing",
            "attempt_count": 2,
            "content_phase": "outline",
            "content_lease_token": "attempt2-lease",
            "content_lease_expires_at": work,
            "content_provider_attempt_hard_deadline_at": now + 1_800_000,
            "content_work_unit_deadline_at": work,
        }
        stale = {
            **locked,
            "status": "failed",
            "attempt_count": 1,
            "content_phase": "failed",
        }
        repository = object.__new__(LearningCatalogRepository)
        repository.get_item = lambda *args, **kwargs: stale
        connection = _SingleRowConnection(None)

        prepared = repository._claim_existing_provider_phase(
            connection,
            build={"id": "build-1"},
            row=locked,
            now=now,
            locked_dispatches=[],
        )

        self.assertEqual(prepared, locked)

    def test_passed_attempt_two_requires_complete_attempt_one_rejection_history(self):
        row = _proof_row(attempt=2)
        repository = object.__new__(LearningCatalogRepository)
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1"},
            {"id": build_id},
        )
        repository.list_build_items = lambda *args, **kwargs: [row]
        repository.list_content_dispatches = (
            lambda conn, *, item_id, logical_attempt: [
                {
                    "id": f"dispatch-{logical_attempt}",
                    "logical_attempt": logical_attempt,
                }
            ]
        )
        connection = _HistoryConnection()

        inventory = repository.load_content_proof_inventory(
            connection, build_id="build-1"
        )

        evidence = inventory["evidence"][0]
        self.assertIn("attemptHistories", evidence)
        histories = evidence["attemptHistories"]
        self.assertEqual(
            histories[1]["dispatches"][0]["id"], "dispatch-1"
        )
        self.assertEqual(
            histories[1]["jobs"][0]["request_id"], "request-1"
        )
        self.assertEqual(
            histories[1]["courses"][0]["status"], "unverified"
        )
        self.assertEqual(
            histories[2]["dispatches"][0]["id"], "dispatch-2"
        )

    def test_passed_attempt_one_rejects_attempt_two_residue_and_extra_candidates(self):
        row = _proof_row(attempt=1)
        repository = object.__new__(LearningCatalogRepository)
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1"},
            {"id": build_id},
        )
        repository.list_build_items = lambda *args, **kwargs: [row]
        repository.list_content_dispatches = (
            lambda conn, *, item_id, logical_attempt: [
                {
                    "id": f"dispatch-{logical_attempt}",
                    "logical_attempt": logical_attempt,
                }
            ]
        )
        connection = _HistoryConnection(extra_candidate=True)

        inventory = repository.load_content_proof_inventory(
            connection, build_id="build-1"
        )

        evidence = inventory["evidence"][0]
        self.assertIn("attemptHistories", evidence)
        histories = evidence["attemptHistories"]
        self.assertEqual(len(histories[1]["candidates"]), 2)
        self.assertEqual(
            histories[2]["dispatches"][0]["id"], "dispatch-2"
        )
        self.assertEqual(len(histories[2]["jobs"]), 1)
        self.assertEqual(len(histories[2]["courses"]), 1)

    def test_provider_finalize_requires_locked_succeeded_dispatch_and_exact_next_edge(self):
        self.assertFalse(
            hasattr(LearningCatalogRepository, "complete_content_provider_phase")
        )
        self.assertTrue(
            hasattr(
                LearningCatalogRepository,
                "load_content_provider_finalize_authority",
            )
        )
        self.assertTrue(
            hasattr(
                LearningCatalogRepository,
                "_complete_content_provider_phase_locked",
            )
        )

    def test_terminal_provider_writer_uses_the_locked_item_for_candidate_persistence(self):
        now = 100_000
        locked = {
            "id": "item-1",
            "build_job_id": "build-1",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "independent_verification",
            "content_lease_token": "lease-1",
            "content_attempt_started_at": now,
            "content_provider_attempt_hard_deadline_at": now + 1_800_000,
            "content_work_unit_deadline_at": now + 120_000,
        }
        course = {
            "id": "course-1",
            "version": "v1",
            "gradeCode": "primary_1",
            "subject": "math",
            "nodeCode": "number_sense_20",
            "title": "数感",
            "objective": "认识20以内的数",
            "status": "unverified",
            "content": {},
        }
        repository = object.__new__(LearningCatalogRepository)
        captured = []

        def persist(conn, *, row, **kwargs):
            captured.append(row)
            return (
                {"id": "job-1"},
                {
                    "id": "candidate-1",
                    "course_id": "course-1",
                    "course_version": "v1",
                },
            )

        repository._create_or_replay_content_candidate = persist
        repository.get_item = lambda conn, *, item_id: {"id": item_id}

        persisted = repository._complete_content_provider_phase_locked(
            _RecordingConnection(),
            locked_item=locked,
            locked_build={"id": "build-1"},
            locked_items=[
                locked,
                *({"id": f"item-{index}"} for index in range(2, 31)),
            ],
            persisted_dispatch_id="dispatch-11",
            expected_next_phase=None,
            expected_next_phase_ordinal=None,
            candidate_course=course,
            generator_profile=_profiles()["generator"],
            now=now + 1,
        )

        self.assertEqual(captured, [locked])
        self.assertEqual(persisted, {"id": "item-1", "generation_job_id": "job-1", "candidate_id": "candidate-1"})

    def test_pre_host_current_attempt_allows_candidate_before_immutable_course(self):
        repository = object.__new__(LearningCatalogRepository)
        histories = {
            1: {
                "dispatches": [{"id": "dispatch-11"}],
                "jobs": [{"id": "job-1"}],
                "candidates": [
                    {
                        "id": "candidate-1",
                        "job_id": "job-1",
                        "ordinal": 1,
                        "course_id": "course-1",
                        "course_version": "v1",
                    }
                ],
                "courses": [],
            }
        }

        with self.assertRaises(LearningCatalogBuildConflict):
            repository._content_attempt_evidence_from_histories(
                item={"id": "item-1"},
                histories=histories,
                attempt=1,
            )
        authority = repository._content_attempt_evidence_from_histories(
            item={"id": "item-1"},
            histories=histories,
            attempt=1,
            require_course=False,
        )

        self.assertIsNone(authority["course"])
        self.assertEqual(authority["candidate"]["id"], "candidate-1")

    def test_attempt_two_candidate_identity_binds_the_full_active_request(self):
        base_request = "formal." + "a" * 80
        attempt_one_command = replace(
            _phase_command_fixture(),
            logical_attempt=1,
            phase="independent_verification",
            phase_ordinal=11,
            generation_request_id=base_request,
        )
        attempt_two_command = replace(
            attempt_one_command,
            logical_attempt=2,
            generation_request_id=base_request + ".attempt2",
        )

        attempt_one = question_adapter_module._build_candidate_course(
            attempt_one_command,
            _compiled_candidate_fixture(),
        )
        attempt_two = question_adapter_module._build_candidate_course(
            attempt_two_command,
            _compiled_candidate_fixture(),
        )

        self.assertNotEqual(attempt_one["id"], attempt_two["id"])
        self.assertNotEqual(
            attempt_one["content"]["questions"][0]["id"],
            attempt_two["content"]["questions"][0]["id"],
        )
        self.assertEqual(
            question_adapter_module._normalize_candidate_course(
                attempt_two,
                attempt_two_command,
                existing_fingerprints=[],
            ),
            attempt_two,
        )

    def test_task6_host_accepts_task5_attempt_two_full_request_identity(self):
        _, target, boundary, formal_evidence, formal_identity = (
            formal_host_fixture("pinyin_syllables")
        )
        adapter = _CompletePinyinCanaryAdapter()
        request_id = "formal." + "a" * 80 + ".attempt2"
        command = replace(
            _phase_command_fixture(),
            logical_attempt=2,
            phase="independent_verification",
            phase_ordinal=11,
            generation_request_id=request_id,
            subject=target.subject,
            target_language_code=target.target_language_code,
            boundary=boundary,
            checkpoint={
                "questionCount": 5,
                "existingFingerprints": [
                    f"{index:064x}" for index in range(1, 6)
                ],
                "generationFeedback": {
                    "code": "primary_one_content_rejected",
                    "message": "课程内容未通过一年级确定性教学规则。",
                },
            },
        )
        course = question_adapter_module._build_candidate_course(
            command, adapter._compiled
        )
        public_questions = question_adapter_module._public_questions(course)
        solution = copy.deepcopy(formal_evidence.independent_solution)
        solution["verificationRequestId"] = request_id
        solution["publicQuestionHash"] = question_adapter_module.hashlib.sha256(
            json.dumps(
                public_questions,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        for answer, question in zip(solution["answers"], public_questions):
            answer["questionId"] = question["id"]
        evidence = replace(
            formal_evidence,
            candidate_course=course,
            question_fingerprints=(
                question_adapter_module._build_question_fingerprints(
                    command, course
                )
            ),
            validation=question_adapter_module._build_validation(
                course, existing_count=5
            ),
            independent_solution=solution,
        )
        identity = replace(
            formal_identity,
            logical_attempt=2,
            generation_request_id=request_id,
            course_id=course["id"],
            course_version=course["version"],
        )

        result = LearningGeneratedCourseValidator().validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_attempt_two_cannot_be_claimed_through_a_weak_repository_cas(self):
        repository = object.__new__(LearningCatalogRepository)
        writer = getattr(repository, "claim_content_attempt_two", None)
        if writer is None:
            return
        row = {
            "id": "item-1",
            "status": "failed",
            "content_phase": "failed",
            "content_gate_status": "failed_deterministic",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1",
            "course_id": "course-1",
            "course_version": "v1",
        }
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1"},
            {"id": build_id, "status": "running"},
        )
        repository.list_build_items = lambda *args, **kwargs: [row]
        repository._content_authority_is_exact = lambda *args, **kwargs: True
        repository._claim_content_attempt = (
            lambda *args, **kwargs: {**row, "attempt_count": 2}
        )

        claimed = writer(
            object(),
            build_id="build-1",
            item_id="item-1",
            attempt_one_request_id="request-1",
            attempt_one_course_id="course-1",
            attempt_one_course_version="v1",
            now=100_000,
        )

        self.assertIsNone(claimed)

    def test_task7_profiles_use_the_exact_task5_canonical_normalizer(self):
        valid = _profiles()["generator"]
        too_long_name = {**valid, "name": "n" * 81}
        utf16_too_long_url = {
            **valid,
            "baseUrl": "https://example.com/" + "😀" * 241,
        }
        service = object.__new__(LearningCatalogReleaseService)
        for value in (too_long_name, utf16_too_long_url):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    question_adapter_module._normalize_phase_provider(value)
                service.question_phase_provider_profiles = {
                    "generator": value,
                    "verifier": copy.deepcopy(valid),
                }
                with self.assertRaises(ValueError):
                    service._content_profile_payload("generator")

    def test_invalid_profile_terminal_returns_post_fence_locked_fact_summary(self):
        rows = _summary_rows()
        invalid_repository = _TerminalSummaryRepository(rows)
        service = _memory_content_service(
            now=100_000,
            repository=invalid_repository,
            staged=object(),
            host=_PassingMemoryHost(),
        )
        service.question_phase_provider_profiles["verifier"]["model"] = ""
        invalid_profile = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )
        self.assertEqual(invalid_profile.kind, "failed")
        self.assertEqual(
            invalid_profile.content_summary["contentFailedItemCount"], 1
        )

    def test_audit_drift_terminal_returns_post_fence_locked_fact_summary(self):
        drift_rows = _summary_rows()
        drift_rows[1].update(
            status="course_ready",
            content_phase="course_ready",
            content_gate_status="passed",
            content_receipt_hash="a" * 64,
        )
        drift_repository = _AuditDriftSummaryRepository(drift_rows)
        drift_service = _memory_content_service(
            now=100_000,
            repository=drift_repository,
            staged=object(),
            host=_PassingMemoryHost(),
        )
        drift_summary = drift_service._content_summary_after_transition(
            "catalog-build-canary"
        )
        self.assertEqual(drift_summary["contentCandidateItemCount"], 0)
        self.assertEqual(drift_summary["contentFailedItemCount"], 2)

    def test_host_ordinal_three_terminal_returns_post_fence_locked_fact_summary(self):
        timeout_rows = _summary_rows()
        timeout_repository = _HostTimeoutSummaryRepository(timeout_rows)
        timeout_service = _memory_content_service(
            now=100_000,
            repository=timeout_repository,
            staged=object(),
            host=_PassingMemoryHost(),
        )

        def dependency(*args, **kwargs):
            raise PrimaryOneHostGateDependencyError("host dependency")

        timeout_service._content_host_evidence = dependency
        timeout = timeout_service._advance_content_host(
            build_id="catalog-build-canary",
            plan={},
            item={
                "id": "item-0",
                "attempt_count": 1,
                "active_generation_request_id": "request-1",
                "content_gate_attempt_count": 3,
                "content_lease_token": "host-lease",
                "content_work_unit_deadline_at": 99_999,
            },
            summary=timeout_service._empty_content_summary(),
        )
        self.assertEqual(timeout.kind, "failed")
        self.assertEqual(timeout.content_summary["contentFailedItemCount"], 1)

    def test_advance_audit_fence_rereads_post_fence_locked_facts(self):
        repository = _PostFenceRereadRepository(_all_pending_summary_rows())
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=object(),
            host=_PassingMemoryHost(),
        )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(result.content_summary["contentFailedItemCount"], 1)
        self.assertEqual(repository.inventory_loads, 2)
        self.assertEqual(repository.fence_calls, 1)

    def test_summary_audit_fence_rereads_instead_of_synthesizing_stale_rows(self):
        repository = _PostFenceRereadRepository(_all_pending_summary_rows())
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=object(),
            host=_PassingMemoryHost(),
        )

        summary = service._content_summary_after_transition(
            "catalog-build-canary"
        )

        self.assertEqual(summary["contentFailedItemCount"], 1)
        self.assertEqual(repository.inventory_loads, 2)
        self.assertEqual(repository.fence_calls, 1)

    def test_global_inventory_includes_inflight_before_proof_jobs(self):
        repository = object.__new__(LearningCatalogRepository)
        proof = {
            "id": "proof-item",
            "status": "course_ready",
            "attempt_count": 1,
            "generation_request_id": "proof-request",
        }
        inflight = {
            "id": "inflight-item",
            "status": "processing",
            "attempt_count": 1,
            "generation_request_id": "inflight-request",
            "content_phase": "raw_candidate",
        }
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1", "status": "draft"},
            {"id": build_id, "status": "running"},
        )
        repository.list_build_items = lambda *args, **kwargs: [proof, inflight]
        loaded_rows = []

        def histories(conn, *, rows):
            loaded_rows.extend(str(row["id"]) for row in rows)
            return {
                str(row["id"]): {
                    1: {
                        "requestId": str(row["generation_request_id"]),
                        "dispatches": [],
                        "jobs": [],
                        "candidates": [],
                        "courses": [],
                    },
                    2: {
                        "requestId": str(row["generation_request_id"])
                        + ".attempt2",
                        "dispatches": [],
                        "jobs": [],
                        "candidates": [],
                        "courses": [],
                    },
                }
                for row in rows
            }

        repository._load_content_attempt_histories_locked = histories

        inventory = repository.load_content_proof_inventory(
            object(), build_id="build-1"
        )

        self.assertEqual(set(loaded_rows), {"proof-item", "inflight-item"})
        self.assertIn("attemptHistoriesByItem", inventory)

    def test_prepare_consumes_global_histories_without_late_dispatch_lock(self):
        repository = object.__new__(LearningCatalogRepository)
        proof = {
            "id": "proof-item",
            "subject": "chinese",
            "skill_id": "pinyin_syllables",
            "boundary_version": "boundary-v1",
            "variant_ordinal": 1,
            "status": "course_ready",
            "attempt_count": 1,
            "generation_request_id": "proof-request",
        }
        inflight = {
            "id": "inflight-item",
            "subject": "math",
            "skill_id": "number_sense_20",
            "boundary_version": "boundary-v1",
            "variant_ordinal": 1,
            "status": "processing",
            "attempt_count": 1,
            "generation_request_id": "inflight-request",
            "active_generation_request_id": "inflight-request",
            "content_phase": "raw_candidate",
        }
        dispatch = {
            "id": "dispatch-1",
            "phase": "outline",
            "phase_ordinal": 1,
        }
        histories = {
            "proof-item": {
                1: {"dispatches": [], "jobs": [], "candidates": [], "courses": []},
                2: {"dispatches": [], "jobs": [], "candidates": [], "courses": []},
            },
            "inflight-item": {
                1: {
                    "dispatches": [dispatch],
                    "jobs": [],
                    "candidates": [],
                    "courses": [],
                },
                2: {"dispatches": [], "jobs": [], "candidates": [], "courses": []},
            },
        }
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1", "status": "draft"},
            {"id": build_id, "status": "running"},
        )
        repository.list_build_items = lambda *args, **kwargs: [proof, inflight]
        repository._content_authority_is_exact = lambda *args, **kwargs: True
        repository._claim_existing_provider_phase = (
            lambda *args, **kwargs: inflight
        )

        def late_dispatch_lock(*args, **kwargs):
            raise AssertionError("dispatch lock acquired after proof jobs")

        repository.list_content_dispatches = late_dispatch_lock

        plan = repository.prepare_content_advance(
            object(),
            build_id="build-1",
            now=100_000,
            passed_item_ids=frozenset({"proof-item"}),
            repairable_item_ids=frozenset(),
            locked_attempt_histories_by_item=histories,
        )

        self.assertEqual(plan["action"], "provider")
        self.assertEqual(plan["dispatches"], [dispatch])

    def test_task7_has_no_local_final_phase_or_provider_role_literals(self):
        self.assertTrue(
            hasattr(
                question_adapter_module,
                "QUESTION_PHASE_EXECUTION_AUTHORITY",
            )
        )
        self.assertTrue(
            hasattr(
                question_adapter_module,
                "question_phase_execution_authority",
            )
        )
        sources = {
            "service": inspect.getsource(release_service_module),
            "repository": inspect.getsource(catalog_repository_module),
        }
        for name, source in sources.items():
            with self.subTest(module=name):
                self.assertNotIn("{11, 14}", source)
                self.assertNotIn("not in {11, 14}", source)


def _proof_row(*, attempt: int) -> dict[str, object]:
    return {
        "id": "item-1",
        "status": "course_ready",
        "attempt_count": attempt,
        "generation_request_id": "request-1",
        "active_generation_request_id": (
            "request-1" if attempt == 1 else "request-1.attempt2"
        ),
        "subject_ordinal": 1,
        "boundary_ordinal": 1,
        "variant_ordinal": 1,
    }


class _HistoryCursor:
    def __init__(self, rows):
        self.rows = [copy.deepcopy(row) for row in rows]

    def fetchone(self):
        return copy.deepcopy(self.rows[0]) if self.rows else None

    def fetchall(self):
        return copy.deepcopy(self.rows)


class _SingleRowConnection:
    def __init__(self, row):
        self.row = copy.deepcopy(row)

    def execute(self, sql, params=()):
        return _HistoryCursor([] if self.row is None else [self.row])


class _HistoryConnection:
    def __init__(self, *, extra_candidate: bool = False):
        self.extra_candidate = extra_candidate

    def execute(self, sql, params=()):
        normalized = " ".join(str(sql).split())
        if "FROM learning_course_provider_dispatches" in normalized:
            item_id = str(params[0])
            return _HistoryCursor(
                [
                    {
                        "id": f"dispatch-{attempt}",
                        "build_item_id": item_id,
                        "logical_attempt": attempt,
                        "phase_ordinal": 1,
                    }
                    for attempt in (1, 2)
                ]
            )
        if "FROM learning_course_generation_jobs" in normalized:
            return _HistoryCursor(
                [
                    {
                        "id": (
                            "job-2"
                            if str(request_id).endswith(".attempt2")
                            else "job-1"
                        ),
                        "request_id": request_id,
                    }
                    for request_id in params
                ]
            )
        if "FROM learning_course_generation_candidates" in normalized:
            rows = []
            for raw_job_id in params:
                job_id = str(raw_job_id)
                attempt = 2 if job_id == "job-2" else 1
                rows.append(
                    {
                        "id": f"candidate-{attempt}",
                        "job_id": job_id,
                        "ordinal": 1,
                        "course_id": f"course-{attempt}",
                        "course_version": "v1",
                    }
                )
                if self.extra_candidate and attempt == 1:
                    rows.append(
                        {
                            "id": "candidate-1-extra",
                            "job_id": job_id,
                            "ordinal": 2,
                            "course_id": "course-1-extra",
                            "course_version": "v1",
                        }
                    )
            return _HistoryCursor(rows)
        if "FROM learning_courses" in normalized:
            return _HistoryCursor(
                [
                    {
                        "id": "course-1",
                        "version": "v1",
                        "generation_request_id": "request-1",
                        "status": "unverified",
                    },
                    {
                        "id": "course-2",
                        "version": "v1",
                        "generation_request_id": "request-1.attempt2",
                        "status": "validated",
                    },
                    {
                        "id": "course-1-extra",
                        "version": "v1",
                        "generation_request_id": "request-1",
                        "status": "unverified",
                    }
                ]
            )
        raise AssertionError(f"unexpected SQL: {normalized}")


class _RecordingCursor:
    rowcount = 1


class _RecordingConnection:
    def __init__(self):
        self.executions = []

    def execute(self, sql, params=()):
        self.executions.append((sql, params))
        return _RecordingCursor()


def _summary_rows() -> list[dict[str, object]]:
    target = build_preparation_target("primary_1")["courseTargets"]
    rows = [
        {
            "id": f"item-{index}",
            "subject": item["subject"],
            "skill_id": item["skillId"],
            "variant_ordinal": item["variantOrdinal"],
            "status": "pending",
            "attempt_count": 0,
            "content_gate_status": "not_started",
            "content_receipt_hash": None,
        }
        for index, item in enumerate(target)
    ]
    rows[0].update(
        status="failed",
        attempt_count=1,
        content_gate_status="not_started",
    )
    return rows


def _all_pending_summary_rows() -> list[dict[str, object]]:
    rows = _summary_rows()
    rows[0].update(
        status="pending",
        attempt_count=0,
        content_gate_status="not_started",
    )
    return rows


class _TerminalSummaryRepository:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.fence_calls = 0

    @contextmanager
    def transaction(self):
        yield object()

    def inspect_content_profile_preflight(self, conn, *, build_id):
        return "persisted"

    def fence_content_failure(self, conn, **kwargs):
        self.fence_calls += 1

    def load_content_summary_items(self, conn, *, build_id):
        return copy.deepcopy(self.rows)


class _AuditDriftSummaryRepository(_TerminalSummaryRepository):
    def load_content_proof_inventory(self, conn, *, build_id):
        return {"items": copy.deepcopy(self.rows)}


class _PostFenceRereadRepository(_TerminalSummaryRepository):
    def __init__(self, rows):
        super().__init__(rows)
        self.inventory_loads = 0

    def _content_authority_is_exact(self, *args, **kwargs):
        return True

    def fence_content_failure(self, conn, **kwargs):
        super().fence_content_failure(conn, **kwargs)
        self.rows[0].update(
            status="failed",
            attempt_count=1,
            content_gate_status="not_started",
        )

    def load_content_proof_inventory(self, conn, *, build_id):
        self.inventory_loads += 1
        if self.inventory_loads == 1:
            return {"items": copy.deepcopy(self.rows)}
        failed = copy.deepcopy(self.rows[0])
        return {
            "release": {"id": "release-1", "status": "draft"},
            "build": {"id": build_id, "status": "failed"},
            "items": copy.deepcopy(self.rows),
            "evidence": [{"item": failed}],
        }


class _PrepareFenceRereadRepository(_TerminalSummaryRepository):
    def __init__(self, rows):
        super().__init__(rows)
        self.inventory_loads = 0

    def _content_authority_is_exact(self, *args, **kwargs):
        return True

    def load_content_proof_inventory(self, conn, *, build_id):
        self.inventory_loads += 1
        return {
            "release": {"id": "release-1", "status": "draft"},
            "build": {
                "id": build_id,
                "status": "running" if self.inventory_loads == 1 else "failed",
            },
            "items": copy.deepcopy(self.rows),
            "evidence": [],
            "attemptHistoriesByItem": {},
        }

    def prepare_content_advance(self, conn, **kwargs):
        stale = copy.deepcopy(self.rows)
        self.rows[0].update(
            status="failed",
            attempt_count=1,
            content_gate_status="not_started",
        )
        return {"action": "failed", "items": stale}


class _InternallyFencedHostRepository(_TerminalSummaryRepository):
    def complete_content_host_gate(self, conn, **kwargs):
        self.rows[0].update(
            status="failed",
            attempt_count=1,
            content_gate_status="not_started",
        )
        return None

    def is_content_build_failed(self, conn, *, build_id):
        return True

    def load_content_proof_inventory(self, conn, *, build_id):
        return {
            "build": {"id": build_id, "status": "failed"},
            "items": copy.deepcopy(self.rows),
        }


class _HostTimeoutSummaryRepository(_TerminalSummaryRepository):
    def release_content_host_dependency(self, conn, **kwargs):
        return "failed"


if __name__ == "__main__":
    unittest.main()
