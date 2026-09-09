from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.openmaic_question_adapter import (
    OpenMaicQuestionPhaseAdapter,
    QuestionPhaseCommand,
    QuestionPhaseResult,
)
from repositories.dynamic_learning_course_repository import (
    complete_provider_dispatch,
    DynamicLearningCourseRepository,
    ProviderDispatchReservation,
    begin_provider_dispatch,
)
from core.database import Database
from services.learning_curriculum_preparation_contract import TARGET_SCHEMA_V2
from services.dynamic_learning_course_generation_service import (
    ContentPhaseWork,
    StagedContentCandidateGenerator,
)
from tests.support import fresh_test_config
from tests.test_openmaic_question_phase_adapter import (
    SIDECAR_ROOT,
    _Completed,
    _candidate_course,
    _compiled_candidate,
    _fixture_phase_command,
    _independent_solution,
    _lesson_text,
    _number_sense_boundary,
    _number_sense_candidate,
    _outline_checkpoint,
    _phase_command,
    _question_fingerprints,
    _reconciliation,
    _repair,
    _result_payload,
    _text_boundary,
    _text_candidate,
    _validation,
)


def _command(**overrides) -> QuestionPhaseCommand:
    values = {
        "build_item_id": "build-item-1",
        "logical_attempt": 1,
        "phase": "outline",
        "phase_ordinal": 1,
        "generation_request_id": "phase-request-1",
        "grade_code": "primary_1",
        "subject": "math",
        "instruction_language_code": "zh-CN",
        "target_language_code": "zh-CN",
        "boundary": {
            "skillId": "addition_subtraction_20",
            "skillTitle": "20以内加减法",
            "learningObjectives": ["完成20以内一步加减法"],
            "allowedContent": ["0到20的整数"],
            "excludedContent": ["负数"],
            "prerequisiteSkills": ["认识0到20"],
            "estimatedMinutes": 10,
        },
        "checkpoint": {
            "questionCount": 5,
            "existingFingerprints": [],
            "generationFeedback": None,
        },
    }
    values.update(overrides)
    return QuestionPhaseCommand(**values)


def _work(**overrides) -> ContentPhaseWork:
    values = {
        "command": _command(),
        "attempt_initial_checkpoint": {
            "questionCount": 5,
            "existingFingerprints": [],
            "generationFeedback": None,
        },
        "item_lease_token": "lease-token-1",
        "attempt_started_at": 1_000,
        "attempt_hard_deadline_at": 200_000,
        "work_unit_deadline_at": 200_000,
        "lease_expires_at": 200_000,
    }
    values.update(overrides)
    return ContentPhaseWork(**values)


def _checkpoint() -> dict[str, object]:
    return {
        "phaseStatus": "accepted",
        "outlinePlan": {
            "courseTitle": "20以内加减法",
            "languageDirective": "使用简体中文教学。",
            "outlines": [
                {
                    "order": 1,
                    "title": "先理解",
                    "description": "理解加法和减法的意义。",
                    "keyPoints": ["读题", "列式"],
                }
            ],
        },
    }


def _phase_result(
    *, outcome: str = "succeeded", safe_error_code: str | None = None
) -> QuestionPhaseResult:
    return QuestionPhaseResult(
        request_id="phase-request-1",
        phase="outline",
        phase_ordinal=1,
        outcome=outcome,
        checkpoint=_checkpoint() if outcome == "succeeded" else None,
        provider_request_id_hash=None,
        input_tokens=None,
        output_tokens=None,
        billing_evidence="unknown",
        safe_error_code=safe_error_code,
        elapsed_ms=5.0,
    )


class _FakeAdapter:
    required_phase_budget_ms = 85_000

    def __init__(self, *, result=None):
        self.result = result or _phase_result()
        self.preflight_calls = 0
        self.execute_calls = 0
        self.repository = None

    def preflight_phase(self, command):
        self.preflight_calls += 1
        canonical_input = json.dumps(
            {
                "requestId": command.generation_request_id,
                "phase": command.phase,
                "phaseOrdinal": command.phase_ordinal,
                "checkpoint": command.checkpoint,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        profile = {
            "name": "kimi",
            "model": "kimi-k2.6",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "APP_AI_API_KEY",
            "timeoutMs": 60_000,
            "maxTokens": 6_000,
            "temperature": 0.2,
        }
        profile_json = json.dumps(
            profile, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return SimpleNamespace(
            command=command,
            request=json.loads(canonical_input),
            canonical_input_json=canonical_input,
            input_sha256=hashlib.sha256(canonical_input.encode()).hexdigest(),
            provider=profile,
            canonical_profile_json=profile_json,
            profile_sha256=hashlib.sha256(profile_json.encode()).hexdigest(),
        )

    def execute_phase(self, prepared):
        self.execute_calls += 1
        if self.repository is not None:
            if not self.repository.last_transaction_committed:
                raise AssertionError("dispatch reservation was not committed before spawn")
        return self.result

    def _normalize_stored_dispatch_result(self, prepared, dispatch):
        checkpoint = json.loads(dispatch["checkpoint_json"])
        canonical = json.dumps(
            checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if hashlib.sha256(canonical.encode()).hexdigest() != dispatch["output_sha256"]:
            raise ValueError("stored checkpoint hash mismatch")
        return _phase_result()


class _SequenceAdapter(_FakeAdapter):
    def __init__(self, results):
        super().__init__(result=results[-1])
        self.results = iter(results)

    def execute_phase(self, prepared):
        self.execute_calls += 1
        if self.repository is not None:
            if not self.repository.last_transaction_committed:
                raise AssertionError("dispatch reservation was not committed before spawn")
        return next(self.results)


class _FakeRepository:
    def __init__(self, *, reservation=None, complete=True, reserve_error=None):
        self.reservation = reservation
        self.complete = complete
        self.reserve_error = reserve_error
        self.reserve_calls = 0
        self.reserve_call_kwargs = []
        self.complete_calls = []
        self.last_transaction_committed = False
        self.transaction_open = False

    @contextmanager
    def transaction(self):
        self.transaction_open = True
        self.last_transaction_committed = False
        try:
            yield object()
        except Exception:
            self.transaction_open = False
            raise
        else:
            self.transaction_open = False
            self.last_transaction_committed = True

    def reserve_provider_dispatch(self, conn, **kwargs):
        self.reserve_calls += 1
        self.reserve_call_kwargs.append(kwargs)
        if self.reserve_error is not None:
            raise self.reserve_error
        if self.reservation is not None:
            return self.reservation
        return ProviderDispatchReservation(
            dispatch={
                "id": "dispatch-1",
                "status": "dispatched",
                "attempt_hard_deadline_at": kwargs["attempt_hard_deadline_at"],
                "dispatched_at": 100_000,
            },
            created=True,
        )

    def complete_provider_dispatch(self, conn, **kwargs):
        self.complete_calls.append(kwargs)
        return self.complete


class StagedContentCandidateGeneratorTest(unittest.TestCase):
    def _generator(self, repository, adapter, times):
        adapter.repository = repository
        iterator = iter(times)
        return StagedContentCandidateGenerator(
            repository=repository,
            adapter=adapter,
            clock_ms=lambda: next(iterator),
        )

    def test_preflight_and_deadline_failure_have_zero_ledger_and_zero_process(self):
        repository = _FakeRepository()
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [115_001])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "dependency_retry")
        self.assertFalse(result.process_started)
        self.assertEqual(repository.reserve_calls, 0)
        self.assertEqual(adapter.execute_calls, 0)

    def test_request_url_and_model_storage_preflight_have_zero_ledger_and_process(self):
        cases = (
            ({"generation_request_id": "request@id"}, {}),
            ({}, {"base_url": "not-an-absolute-url"}),
            ({}, {"base_url": "https://example.com:bad"}),
            ({}, {"base_url": "https://example.com:99999"}),
            ({}, {"base_url": "https://exa mple.com"}),
            ({}, {"base_url": "https://%zz"}),
            ({}, {"base_url": "http://[::1]foo/v1"}),
            ({}, {"base_url": "http://[::1].evil/v1"}),
            ({}, {"base_url": "http://[::1]80/v1"}),
            ({}, {"base_url": "https://example.com/ｖ１"}),
            ({}, {"base_url": "https://example.com/" + "😀" * 241}),
            ({}, {"model_name": "m" * 129}),
        )
        for command_overrides, adapter_overrides in cases:
            with self.subTest(
                command_overrides=command_overrides,
                adapter_overrides=adapter_overrides,
            ):
                process_calls = []
                adapter = OpenMaicQuestionPhaseAdapter(
                    sidecar_root=SIDECAR_ROOT,
                    node_binary="node",
                    provider_name="kimi",
                    model_name=adapter_overrides.get("model_name", "kimi-k2.6"),
                    base_url=adapter_overrides.get(
                        "base_url", "https://api.moonshot.cn/v1"
                    ),
                    api_key_env="APP_AI_API_KEY",
                    provider_timeout_ms=60_000,
                    max_tokens=6_000,
                    temperature=0.2,
                    process_timeout_seconds=75,
                    process_runner=lambda *args, **kwargs: process_calls.append(
                        (args, kwargs)
                    ),
                )
                repository = _FakeRepository()
                generator = self._generator(repository, adapter, [100_000])
                with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
                    result = generator.advance(
                        _work(command=_command(**command_overrides)),
                        heartbeat=lambda: True,
                    )
                self.assertEqual(result.kind, "dependency_retry")
                self.assertFalse(result.process_started)
                self.assertEqual(repository.reserve_calls, 0)
                self.assertEqual(process_calls, [])

    def test_task4_invalid_compiled_and_course_inputs_have_zero_ledger_and_process(self):
        fixtures = []
        for label in (
            "0个十和16个一",
            "-2个十和0个一",
            "+2个十和0个一",
            "2.0个十和0个一",
            "−2个十和0个一",
            "负2个十和0个一",
            "2e0个十和0个一",
            "0x2个十和0个一",
            "2,0个十和0个一",
            "2/1个十和0个一",
            "2//0个十和0个一",
            "2∕1个十和0个一",
            ". 0个十和0个一",
            "2. 0个十和0个一",
            "个十和8个一",
            "1个十和8个一9",
        ):
            candidate = _number_sense_candidate()
            candidate["questions"][0]["choices"][1]["label"] = label
            fixtures.append((_number_sense_boundary(), candidate, "math", label))
        for english, answers in (
            (True, ["Straße", "STRASSE"]),
            (False, ["二\u0085十", "二十"]),
            (False, ["二\u001c十", "二十"]),
            (False, ["二\u001d十", "二十"]),
            (False, ["二\u001e十", "二十"]),
            (False, ["二\u001f十", "二十"]),
        ):
            fixtures.append(
                (
                    _text_boundary(english=english),
                    _text_candidate(answers=answers, english=english),
                    "english" if english else "chinese",
                    answers,
                )
            )

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            for boundary, candidate, subject, vector in fixtures:
                for phase, ordinal in (
                    ("reconciliation", 6),
                    ("independent_verification", 11),
                    ("verification_after_repair", 14),
                ):
                    with self.subTest(vector=vector, phase=phase):
                        process_calls = []
                        adapter = OpenMaicQuestionPhaseAdapter(
                            sidecar_root=SIDECAR_ROOT,
                            node_binary="node",
                            provider_name="kimi",
                            model_name="kimi-k2.6",
                            base_url="https://api.moonshot.cn/v1",
                            api_key_env="APP_AI_API_KEY",
                            provider_timeout_ms=60_000,
                            max_tokens=6_000,
                            temperature=0.2,
                            process_timeout_seconds=75,
                            process_runner=lambda *args, **kwargs: process_calls.append(
                                (args, kwargs)
                            ),
                        )
                        repository = _FakeRepository()
                        generator = self._generator(repository, adapter, [])
                        command = _fixture_phase_command(
                            phase,
                            ordinal,
                            boundary=copy.deepcopy(boundary),
                            candidate=copy.deepcopy(candidate),
                            subject=subject,
                        )
                        result = generator.advance(
                            _work(
                                command=command,
                                attempt_initial_checkpoint={
                                    "questionCount": 5,
                                    "existingFingerprints": [],
                                    "generationFeedback": None,
                                },
                            ),
                            heartbeat=lambda: True,
                        )
                        self.assertEqual(result.kind, "dependency_retry")
                        self.assertFalse(result.process_started)
                        self.assertEqual(repository.reserve_calls, 0)
                        self.assertEqual(process_calls, [])

    def test_nested_number_sense_checkpoint_strings_fail_before_ledger_and_process(self):
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            for phase, ordinal in (
                ("reconciliation", 6),
                ("independent_verification", 11),
                ("verification_after_repair", 14),
            ):
                with self.subTest(phase=phase):
                    process_calls = []
                    command = _fixture_phase_command(
                        phase,
                        ordinal,
                        boundary=_number_sense_boundary(),
                        candidate=_number_sense_candidate(),
                        subject="math",
                    )
                    adapter = OpenMaicQuestionPhaseAdapter(
                        sidecar_root=SIDECAR_ROOT,
                        node_binary="node",
                        provider_name="kimi",
                        model_name="kimi-k2.6",
                        base_url="https://api.moonshot.cn/v1",
                        api_key_env="APP_AI_API_KEY",
                        provider_timeout_ms=60_000,
                        max_tokens=6_000,
                        temperature=0.2,
                        process_timeout_seconds=75,
                        process_runner=lambda *args, **kwargs: (
                            process_calls.append((args, kwargs)),
                            _Completed(
                                _result_payload(
                                    outcome="failed_safe",
                                    checkpoint=None,
                                    safe_error_code="provider_no_candidate",
                                    phase=phase,
                                    phaseOrdinal=ordinal,
                                ),
                                returncode=1,
                            ),
                        )[1],
                    )
                    if phase == "verification_after_repair":
                        command.checkpoint["candidateCourse"]["content"][
                            "teachingFlow"
                        ]["teach"]["sayText"] = "2//0个十和0个一"
                    else:
                        command.checkpoint["lessonText"]["teachingFlow"]["teach"][
                            "sayText"
                        ] = "2//0个十和0个一"
                    repository = _FakeRepository()
                    generator = self._generator(
                        repository,
                        adapter,
                        [100_000, 100_000, 100_000],
                    )

                    result = generator.advance(
                        _work(
                            command=command,
                            attempt_initial_checkpoint={
                                "questionCount": 5,
                                "existingFingerprints": [],
                                "generationFeedback": None,
                            },
                        ),
                        heartbeat=lambda: True,
                    )

                    self.assertEqual(result.kind, "dependency_retry")
                    self.assertFalse(result.process_started)
                    self.assertEqual(repository.reserve_calls, 0)
                    self.assertEqual(process_calls, [])

    def test_exact_deadline_fit_reserves_commits_then_starts_one_process(self):
        repository = _FakeRepository()
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [115_000, 115_000, 115_000])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "succeeded")
        self.assertTrue(result.process_started)
        self.assertEqual(repository.reserve_calls, 1)
        self.assertEqual(
            repository.reserve_call_kwargs[0]["attempt_initial_checkpoint"],
            _work().attempt_initial_checkpoint,
        )
        self.assertEqual(adapter.execute_calls, 1)
        self.assertEqual(len(repository.complete_calls), 1)
        completion = repository.complete_calls[0]
        self.assertEqual(completion["outcome"], "succeeded")
        canonical = json.dumps(
            _checkpoint(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        self.assertEqual(
            completion["output_sha256"], hashlib.sha256(canonical.encode()).hexdigest()
        )

    def test_proven_uncompleted_provider_rejection_retries_then_succeeds(self):
        rejected = _phase_result(
            outcome="failed_safe", safe_error_code="provider_request_rejected"
        )
        repository = _FakeRepository()
        adapter = _SequenceAdapter([rejected, _phase_result()])
        adapter.repository = repository
        times = iter((100_000, 100_000, 100_000, 100_001, 100_002))
        sleeps = []
        generator = StagedContentCandidateGenerator(
            repository=repository,
            adapter=adapter,
            clock_ms=lambda: next(times),
            sleeper=sleeps.append,
        )

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "succeeded")
        self.assertTrue(result.process_started)
        self.assertEqual(adapter.execute_calls, 2)
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(len(repository.complete_calls), 1)
        self.assertEqual(repository.complete_calls[0]["outcome"], "succeeded")

    def test_provider_rejection_retry_is_bounded_to_two_retries(self):
        rejected = _phase_result(
            outcome="failed_safe", safe_error_code="provider_request_rejected"
        )
        repository = _FakeRepository()
        adapter = _SequenceAdapter([rejected, rejected, rejected])
        adapter.repository = repository
        times = iter(
            (100_000, 100_000, 100_000, 100_001, 100_002, 100_003, 100_004)
        )
        sleeps = []
        generator = StagedContentCandidateGenerator(
            repository=repository,
            adapter=adapter,
            clock_ms=lambda: next(times),
            sleeper=sleeps.append,
        )

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "failed_safe")
        self.assertEqual(adapter.execute_calls, 3)
        self.assertEqual(sleeps, [0.25, 0.75])
        self.assertEqual(len(repository.complete_calls), 1)
        self.assertEqual(
            repository.complete_calls[0]["safe_error_code"],
            "provider_request_rejected",
        )

    def test_ambiguous_or_identified_provider_outcome_never_retries(self):
        cases = (
            _phase_result(outcome="ambiguous", safe_error_code="provider_timeout"),
            replace(
                _phase_result(
                    outcome="failed_safe",
                    safe_error_code="provider_request_rejected",
                ),
                provider_request_id_hash="a" * 64,
            ),
            replace(
                _phase_result(
                    outcome="failed_safe",
                    safe_error_code="provider_request_rejected",
                ),
                input_tokens=1,
                billing_evidence="reported",
            ),
        )
        for terminal in cases:
            with self.subTest(terminal=terminal):
                repository = _FakeRepository()
                adapter = _SequenceAdapter([terminal])
                adapter.repository = repository
                times = iter((100_000, 100_000, 100_001))
                sleeps = []
                generator = StagedContentCandidateGenerator(
                    repository=repository,
                    adapter=adapter,
                    clock_ms=lambda: next(times),
                    sleeper=sleeps.append,
                )

                result = generator.advance(_work(), heartbeat=lambda: True)

                self.assertEqual(result.kind, terminal.outcome)
                self.assertEqual(adapter.execute_calls, 1)
                self.assertEqual(sleeps, [])

    def test_nonwinning_live_reservation_is_busy_and_never_spawns(self):
        reservation = ProviderDispatchReservation(
            dispatch={
                "id": "dispatch-1",
                "status": "dispatched",
                "generation_request_id": "phase-request-1",
                "item_lease_token": "lease-token-1",
                "attempt_hard_deadline_at": 200_000,
                "dispatched_at": 100_000,
            },
            created=False,
        )
        repository = _FakeRepository(reservation=reservation)
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000, 100_000])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "busy")
        self.assertFalse(result.process_started)
        self.assertEqual(adapter.execute_calls, 0)
        self.assertEqual(repository.complete_calls, [])

    def test_succeeded_replay_verifies_hash_and_returns_without_process(self):
        checkpoint = _checkpoint()
        canonical = json.dumps(
            checkpoint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        reservation = ProviderDispatchReservation(
            dispatch={
                "id": "dispatch-1",
                "status": "succeeded",
                "checkpoint_json": canonical,
                "output_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                "provider_request_id_hash": None,
                "input_tokens": None,
                "output_tokens": None,
                "billing_evidence": "unknown",
                "safe_error_code": None,
                "completed_at": 100_000,
            },
            created=False,
        )
        repository = _FakeRepository(reservation=reservation)
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "succeeded")
        self.assertTrue(result.replayed)
        self.assertFalse(result.process_started)
        self.assertEqual(result.result.checkpoint, checkpoint)
        self.assertEqual(adapter.execute_calls, 0)

    def test_hash_drifted_replay_is_ambiguous_and_never_spawns(self):
        reservation = ProviderDispatchReservation(
            dispatch={
                "id": "dispatch-1",
                "status": "succeeded",
                "checkpoint_json": json.dumps(_checkpoint()),
                "output_sha256": "0" * 64,
            },
            created=False,
        )
        repository = _FakeRepository(reservation=reservation)
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "ambiguous")
        self.assertFalse(result.process_started)
        self.assertEqual(adapter.execute_calls, 0)

    def test_local_deadline_failed_safe_receipt_replays_without_process(self):
        reservation = ProviderDispatchReservation(
            dispatch={
                "id": "dispatch-1",
                "status": "failed_safe",
                "checkpoint_json": None,
                "output_sha256": None,
                "provider_request_id_hash": None,
                "input_tokens": None,
                "output_tokens": None,
                "billing_evidence": "unknown",
                "safe_error_code": "phase_deadline_insufficient",
                "completed_at": 100_000,
            },
            created=False,
        )
        repository = _FakeRepository(reservation=reservation)
        adapter = OpenMaicQuestionPhaseAdapter(
            sidecar_root=SIDECAR_ROOT,
            node_binary="node",
            provider_name="kimi",
            model_name="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
            api_key_env="APP_AI_API_KEY",
            provider_timeout_ms=60_000,
            max_tokens=6_000,
            temperature=0.2,
            process_timeout_seconds=75,
            process_runner=lambda *args, **kwargs: self.fail("replay started a process"),
        )
        generator = self._generator(repository, adapter, [100_000])

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "failed_safe")
        self.assertTrue(result.replayed)
        self.assertFalse(result.process_started)
        self.assertEqual(result.result.safe_error_code, "phase_deadline_insufficient")

    def test_stale_open_dispatch_is_control_ambiguous_without_time_fabrication(self):
        reservation = ProviderDispatchReservation(
            dispatch={
                "id": "dispatch-1",
                "status": "dispatched",
                "generation_request_id": "phase-request-1",
                "item_lease_token": "lease-token-1",
                "attempt_hard_deadline_at": 99_999,
                "dispatched_at": 1_000,
                "completed_at": None,
            },
            created=False,
        )
        repository = _FakeRepository(reservation=reservation)
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000, 100_000])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "ambiguous")
        self.assertFalse(result.process_started)
        self.assertEqual(repository.complete_calls, [])
        self.assertIsNone(reservation.dispatch["completed_at"])

    def test_postcommit_heartbeat_loss_writes_truthful_failed_safe_without_spawn(self):
        repository = _FakeRepository()
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000, 100_000, 100_001])
        heartbeats = iter((True, False))

        result = generator.advance(_work(), heartbeat=lambda: next(heartbeats))

        self.assertEqual(result.kind, "failed_safe")
        self.assertFalse(result.process_started)
        self.assertEqual(adapter.execute_calls, 0)
        self.assertEqual(len(repository.complete_calls), 1)
        self.assertEqual(
            repository.complete_calls[0]["safe_error_code"], "phase_lease_lost"
        )

    def test_postcommit_deadline_consumption_never_spawns_or_backdates(self):
        repository = _FakeRepository()
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000, 115_001, 115_002])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "failed_safe")
        self.assertFalse(result.process_started)
        self.assertEqual(adapter.execute_calls, 0)
        self.assertEqual(
            repository.complete_calls[0]["safe_error_code"],
            "phase_deadline_insufficient",
        )
        self.assertEqual(repository.complete_calls[0]["completed_at"], 115_002)

    def test_terminal_cas_loss_returns_stale_and_never_replays(self):
        repository = _FakeRepository(complete=False)
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000, 100_000, 100_001])

        result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "stale")
        self.assertTrue(result.process_started)
        self.assertEqual(adapter.execute_calls, 1)
        self.assertEqual(repository.reserve_calls, 1)

    def test_generator_revalidates_full_result_identity_and_pairing_before_completion(self):
        valid = _phase_result()
        mutations = (
            replace(valid, request_id="wrong-request"),
            replace(valid, phase="raw_candidate"),
            replace(valid, phase_ordinal=2),
            replace(valid, checkpoint=None),
            replace(valid, safe_error_code="provider_invalid_response"),
            replace(valid, input_tokens=2_147_483_648, billing_evidence="reported"),
            replace(valid, input_tokens=1, billing_evidence="unknown"),
            replace(valid, provider_request_id_hash="A" * 64),
            replace(valid, elapsed_ms=-1.0),
            replace(
                valid,
                outcome="failed_safe",
                checkpoint=_checkpoint(),
                safe_error_code="provider_no_candidate",
            ),
            replace(
                valid,
                outcome="ambiguous",
                checkpoint=None,
                safe_error_code="provider_invalid_response",
            ),
        )
        for forged in mutations:
            with self.subTest(forged=forged):
                repository = _FakeRepository()
                adapter = _FakeAdapter(result=forged)
                generator = self._generator(
                    repository, adapter, [100_000, 100_000, 100_001]
                )

                result = generator.advance(_work(), heartbeat=lambda: True)

                self.assertEqual(result.kind, "ambiguous")
                self.assertTrue(result.process_started)
                self.assertEqual(
                    (result.result.outcome, result.result.safe_error_code),
                    ("ambiguous", "provider_outcome_unknown"),
                )
                self.assertIsNone(result.result.checkpoint)
                self.assertIsNone(result.result.input_tokens)
                self.assertIsNone(result.result.output_tokens)
                self.assertEqual(result.result.billing_evidence, "unknown")
                self.assertEqual(len(repository.complete_calls), 1)
                completion = repository.complete_calls[0]
                self.assertEqual(completion["outcome"], "ambiguous")
                self.assertIsNone(completion["checkpoint"])
                self.assertIsNone(completion["input_tokens"])
                self.assertIsNone(completion["output_tokens"])
                self.assertEqual(completion["billing_evidence"], "unknown")

    def test_repository_terminal_writer_rejects_pairing_and_int32_drift_before_sql(self):
        class NoSqlConnection:
            def execute(self, *args, **kwargs):
                raise AssertionError("invalid receipt reached SQL")

        repository = DynamicLearningCourseRepository(database=None)

        base = {
            "dispatch_id": "dispatch-1",
            "build_item_id": "build-item-1",
            "generation_request_id": "phase-request-1",
            "item_lease_token": "lease-token-1",
            "outcome": "failed_safe",
            "checkpoint": None,
            "output_sha256": None,
            "provider_request_id_hash": None,
            "input_tokens": None,
            "output_tokens": None,
            "billing_evidence": "unknown",
            "safe_error_code": "provider_no_candidate",
            "completed_at": 100_000,
        }
        mutations = (
            {"outcome": "failed_safe", "safe_error_code": "provider_timeout"},
            {"outcome": "ambiguous", "safe_error_code": "provider_invalid_response"},
            {
                "outcome": "succeeded",
                "checkpoint": {"phaseStatus": "accepted"},
                "output_sha256": "0" * 64,
                "safe_error_code": None,
            },
            {"input_tokens": 1, "billing_evidence": "unknown"},
            {"input_tokens": None, "output_tokens": None, "billing_evidence": "reported"},
            {"input_tokens": 2_147_483_648, "billing_evidence": "reported"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    repository.complete_provider_dispatch(
                        NoSqlConnection(), **{**base, **mutation}
                    )

    def test_module_terminal_writer_rejects_strict_drift_before_sql(self):
        class NoSqlConnection:
            def __init__(self):
                self.execute_calls = 0

            def execute(self, *args, **kwargs):
                self.execute_calls += 1
                raise AssertionError("invalid receipt reached SQL")

        base = {
            "dispatch_id": "dispatch-1",
            "build_item_id": "build-item-1",
            "generation_request_id": "phase-request-1",
            "item_lease_token": "lease-token-1",
            "outcome": "failed_safe",
            "checkpoint": None,
            "output_sha256": None,
            "provider_request_id_hash": None,
            "input_tokens": None,
            "output_tokens": None,
            "billing_evidence": "unknown",
            "safe_error_code": "provider_no_candidate",
            "completed_at": 100_000,
        }
        mutations = (
            {
                "input_tokens": 2_147_483_648,
                "billing_evidence": "reported",
            },
            {"billing_evidence": "reported"},
            {"outcome": "failed_safe", "safe_error_code": "provider_timeout"},
            {
                "outcome": "succeeded",
                "checkpoint": {"phaseStatus": "accepted"},
                "output_sha256": "0" * 64,
                "safe_error_code": None,
            },
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                conn = NoSqlConnection()
                with self.assertRaises(ValueError):
                    complete_provider_dispatch(conn, **{**base, **mutation})
                self.assertEqual(conn.execute_calls, 0)

    def test_generator_completion_cannot_bypass_the_repository_wrapper(self):
        repository = _FakeRepository()
        adapter = _FakeAdapter()
        generator = self._generator(
            repository, adapter, [100_000, 100_000, 100_001]
        )

        with patch(
            "repositories.dynamic_learning_course_repository.complete_provider_dispatch",
            side_effect=AssertionError("formal service bypassed repository wrapper"),
        ):
            result = generator.advance(_work(), heartbeat=lambda: True)

        self.assertEqual(result.kind, "succeeded")
        self.assertEqual(len(repository.complete_calls), 1)

    def test_forged_attempt_two_is_rejected_before_process(self):
        repository = _FakeRepository(reserve_error=ValueError("attempt identity mismatch"))
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000])
        work = _work(command=_command(logical_attempt=2))

        result = generator.advance(work, heartbeat=lambda: True)

        self.assertEqual(result.kind, "stale")
        self.assertFalse(result.process_started)
        self.assertEqual(adapter.execute_calls, 0)

    def test_restricted_generator_has_no_downstream_capabilities(self):
        repository = _FakeRepository()
        adapter = _FakeAdapter()
        generator = self._generator(repository, adapter, [100_000])
        forbidden = {
            "generate",
            "generate_for_skill",
            "enqueue_classroom",
            "claim_package_for_item",
            "activate",
            "runtime",
            "media",
            "tts",
            "asr",
            "publish",
        }
        self.assertTrue(all(not hasattr(generator, name) for name in forbidden))


class Task5ProviderDispatchMySqlTest(unittest.TestCase):
    DEADLINE = 1_000_000
    NOW = 100_000
    REQUIRED_BUDGET = 85_000

    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)
        self.repository = DynamicLearningCourseRepository(self.database)
        self._insert_active_content_item()

    def _adapter(self, *, runner=None):
        return OpenMaicQuestionPhaseAdapter(
            sidecar_root=SIDECAR_ROOT,
            node_binary="node",
            provider_name="kimi",
            model_name="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
            api_key_env="APP_AI_API_KEY",
            provider_timeout_ms=60_000,
            max_tokens=6_000,
            temperature=0.2,
            process_timeout_seconds=75,
            **({"process_runner": runner} if runner is not None else {}),
        )

    def _prepared(self, phase: str, ordinal: int, *, command=None):
        command = command or _phase_command(phase, ordinal)
        command = replace(command, build_item_id="task5-item")
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            return self._adapter().preflight_phase(command)

    def _reserve(
        self,
        conn,
        prepared,
        *,
        clock=None,
        attempt_initial_checkpoint=None,
    ):
        command = prepared.command
        initial = attempt_initial_checkpoint or {
            "questionCount": 5,
            "existingFingerprints": list(
                prepared.request.get("checkpoint", {}).get(
                    "existingFingerprints", []
                )
            ),
            "generationFeedback": prepared.request.get("checkpoint", {}).get(
                "generationFeedback"
            ),
        }
        return self.repository.reserve_provider_dispatch(
            conn,
            build_item_id=command.build_item_id,
            logical_attempt=command.logical_attempt,
            phase=command.phase,
            phase_ordinal=command.phase_ordinal,
            generation_request_id=command.generation_request_id,
            item_lease_token="task5-lease",
            provider=str(prepared.provider["name"]),
            model=str(prepared.provider["model"]),
            profile=prepared.profile_sha256,
            input_sha256=prepared.input_sha256,
            attempt_started_at=1_000,
            attempt_hard_deadline_at=self.DEADLINE,
            work_unit_deadline_at=self.DEADLINE,
            lease_expires_at=self.DEADLINE,
            attempt_initial_checkpoint=initial,
            command_checkpoint=prepared.request["checkpoint"],
            prepared_request=prepared.request,
            required_budget_ms=self.REQUIRED_BUDGET,
            clock_ms=clock or (lambda: self.NOW),
        )

    def _complete(self, conn, reservation, checkpoint, *, completed_at=None):
        canonical = json.dumps(
            checkpoint,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self.repository.complete_provider_dispatch(
            conn,
            dispatch_id=str(reservation.dispatch["id"]),
            build_item_id="task5-item",
            generation_request_id="phase-request-1",
            item_lease_token="task5-lease",
            outcome="succeeded",
            checkpoint=checkpoint,
            output_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            provider_request_id_hash=None,
            input_tokens=None,
            output_tokens=None,
            billing_evidence="unknown",
            safe_error_code=None,
            completed_at=completed_at or self.NOW + 1,
        )

    def _set_phase(self, conn, phase: str):
        conn.execute(
            "UPDATE learning_catalog_build_items SET content_phase = ? WHERE id = ?",
            (phase, "task5-item"),
        )

    @staticmethod
    def _accepted_checkpoint(phase: str, *, existing_count: int = 0):
        candidate = _compiled_candidate()
        course = _candidate_course()
        validation = _validation()
        validation["existingFingerprintsChecked"] = existing_count
        return {
            "outline": _outline_checkpoint(),
            "raw_candidate": {
                "phaseStatus": "accepted",
                "rawCandidate": copy.deepcopy(candidate),
            },
            "candidate_repair": {
                "phaseStatus": "accepted",
                "candidate": copy.deepcopy(candidate),
                "hostCompilation": {
                    "compiler": "host_compiler",
                    "source": "candidate_repair_output",
                    "version": "v1",
                },
            },
            "lesson_text": {
                "phaseStatus": "accepted",
                "lessonText": _lesson_text(),
            },
            "reconciliation": {
                "phaseStatus": "accepted",
                "reconciliation": _reconciliation(),
                "hostReconciliation": {
                    "reconciler": "host_reconciler",
                    "source": "reconciliation_output",
                    "version": "v1",
                },
            },
            "independent_verification": {
                "phaseStatus": "accepted",
                "candidateCourse": course,
                "questionFingerprints": _question_fingerprints(course),
                "validation": validation,
                "independentSolution": _independent_solution(course),
            },
            "consistency_repair": {
                "phaseStatus": "accepted",
                "repair": _repair(course),
            },
            "verification_after_repair": {
                "phaseStatus": "accepted",
                "repairedCandidateCourse": course,
                "questionFingerprints": _question_fingerprints(course),
                "validation": validation,
                "independentSolution": _independent_solution(course),
            },
        }[phase]

    def _persist_phase(self, phase: str, ordinal: int, *, inventory=()):
        command = _phase_command(phase, ordinal)
        checkpoint = copy.deepcopy(command.checkpoint)
        if "existingFingerprints" in checkpoint:
            checkpoint["existingFingerprints"] = list(inventory)
        if "validation" in checkpoint:
            checkpoint["validation"]["existingFingerprintsChecked"] = len(inventory)
        prepared = self._prepared(
            phase,
            ordinal,
            command=replace(command, checkpoint=checkpoint),
        )
        with self.database.transaction() as conn:
            self._set_phase(conn, phase)
            reservation = self._reserve(
                conn,
                prepared,
                attempt_initial_checkpoint={
                    "questionCount": 5,
                    "existingFingerprints": list(inventory),
                    "generationFeedback": None,
                },
            )
            self.assertTrue(reservation.created)
            self.assertTrue(
                self._complete(
                    conn,
                    reservation,
                    self._accepted_checkpoint(phase, existing_count=len(inventory)),
                )
            )
        return prepared, reservation

    def test_atomic_reservation_exact_replay_and_fresh_deadline_fit(self):
        prepared = self._prepared("outline", 1)
        with self.database.transaction() as conn:
            first = self._reserve(conn, prepared)
        with self.database.transaction() as conn:
            replay = self._reserve(conn, prepared)
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item'"
            ).fetchone()
        self.assertTrue(first.created)
        self.assertFalse(replay.created)
        self.assertEqual(first.dispatch["id"], replay.dispatch["id"])
        self.assertEqual(first.dispatch["dispatched_at"], self.NOW)
        self.assertEqual(count["count"], 1)

        config = fresh_test_config()
        self.database = Database(config["DATABASE_URL"])
        self.repository = DynamicLearningCourseRepository(self.database)
        self._insert_active_content_item()
        with self.assertRaisesRegex(ValueError, "budget|deadline"):
            with self.database.transaction() as conn:
                self._reserve(conn, prepared, clock=lambda: self.DEADLINE - self.REQUIRED_BUDGET + 1)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()
        self.assertEqual(count["count"], 0)

    def test_predecessor_artifact_and_output_hash_are_authoritative(self):
        self._persist_phase("outline", 1)
        forged_command = _phase_command("raw_candidate", 2)
        forged_checkpoint = copy.deepcopy(forged_command.checkpoint)
        forged_checkpoint["outlinePlan"]["courseTitle"] = "伪造课题"
        forged_prepared = self._prepared(
            "raw_candidate",
            2,
            command=replace(forged_command, checkpoint=forged_checkpoint),
        )
        with self.assertRaisesRegex(ValueError, "artifact|predecessor|provenance"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "raw_candidate")
                self._reserve(conn, forged_prepared)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()
        self.assertEqual(count["count"], 1)

    def test_legacy_wrong_phase1_input_hash_cannot_seed_strict_phase2(self):
        phase1 = self._prepared("outline", 1)
        with self.database.transaction() as conn:
            row = begin_provider_dispatch(
                conn,
                build_item_id="task5-item",
                logical_attempt=1,
                phase="outline",
                phase_ordinal=1,
                generation_request_id="phase-request-1",
                item_lease_token="task5-lease",
                provider=str(phase1.provider["name"]),
                model=str(phase1.provider["model"]),
                profile=phase1.profile_sha256,
                input_sha256="0" * 64,
                attempt_started_at=1_000,
                attempt_hard_deadline_at=self.DEADLINE,
                dispatched_at=self.NOW,
            )
            reservation = ProviderDispatchReservation(dispatch=row, created=True)
            self.assertTrue(
                self._complete(conn, reservation, _outline_checkpoint())
            )
            self._set_phase(conn, "raw_candidate")

        phase2 = self._prepared("raw_candidate", 2)
        with self.assertRaisesRegex(ValueError, "input hash|provenance"):
            with self.database.transaction() as conn:
                self._reserve(conn, phase2)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item' AND phase = 'raw_candidate'"
            ).fetchone()
        self.assertEqual(count["count"], 0)

    def test_every_intermediate_predecessor_input_hash_is_revalidated(self):
        for phase, ordinal in (
            ("outline", 1),
            ("raw_candidate", 2),
            ("candidate_repair", 3),
            ("lesson_text", 5),
        ):
            self._persist_phase(phase, ordinal)
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_course_provider_dispatches SET input_sha256 = ? "
                "WHERE build_item_id = ? AND phase = 'lesson_text'",
                ("f" * 64, "task5-item"),
            )
            self._set_phase(conn, "reconciliation")
        prepared = self._prepared("reconciliation", 6)
        with self.assertRaisesRegex(ValueError, "input hash|provenance"):
            with self.database.transaction() as conn:
                self._reserve(conn, prepared)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item' AND phase = 'reconciliation'"
            ).fetchone()
        self.assertEqual(count["count"], 0)

    def test_authorized_attempt2_feedback_is_byte_exact_through_phase2(self):
        feedback = {
            "code": "host_teaching_rejected",
            "message": "讲解需要更清楚。",
        }
        initial = {
            "questionCount": 5,
            "existingFingerprints": ["a" * 64],
            "generationFeedback": feedback,
        }
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_items SET attempt_count = 2, "
                "content_claim_attempt_ordinal = 2 WHERE id = 'task5-item'"
            )
        phase1_command = replace(
            _phase_command("outline", 1),
            build_item_id="task5-item",
            logical_attempt=2,
            checkpoint=copy.deepcopy(initial),
        )
        phase1 = self._prepared("outline", 1, command=phase1_command)
        with self.database.transaction() as conn:
            reservation = self._reserve(
                conn, phase1, attempt_initial_checkpoint=initial
            )
            self.assertTrue(
                self._complete(conn, reservation, _outline_checkpoint())
            )
            self._set_phase(conn, "raw_candidate")

        phase2_command = _phase_command("raw_candidate", 2)
        phase2_checkpoint = copy.deepcopy(phase2_command.checkpoint)
        phase2_checkpoint.update(copy.deepcopy(initial))
        phase2_command = replace(
            phase2_command,
            build_item_id="task5-item",
            logical_attempt=2,
            checkpoint=phase2_checkpoint,
        )
        phase2 = self._prepared("raw_candidate", 2, command=phase2_command)
        with self.database.transaction() as conn:
            reservation = self._reserve(
                conn, phase2, attempt_initial_checkpoint=initial
            )
        self.assertTrue(reservation.created)
        self.assertEqual(reservation.dispatch["logical_attempt"], 2)

    def test_formal_provider_text_allows_unicode_spaces_and_fits_columns(self):
        adapter = OpenMaicQuestionPhaseAdapter(
            sidecar_root=SIDECAR_ROOT,
            node_binary="node",
            provider_name="千问 正式",
            model_name="模型 v1" + "甲" * (128 - len("模型 v1")),
            base_url="https://api.moonshot.cn/v1",
            api_key_env="APP_AI_API_KEY",
            provider_timeout_ms=60_000,
            max_tokens=6_000,
            temperature=0.2,
            process_timeout_seconds=75,
        )
        command = replace(
            _phase_command("outline", 1), build_item_id="task5-item"
        )
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            prepared = adapter.preflight_phase(command)
        with self.database.transaction() as conn:
            reservation = self._reserve(conn, prepared)
        self.assertTrue(reservation.created)
        self.assertEqual(reservation.dispatch["provider"], "千问 正式")
        self.assertEqual(reservation.dispatch["model"], prepared.provider["model"])

    def test_usage_overflow_terminalizes_live_dispatch_as_canonical_ambiguous(self):
        process_calls = 0

        def runner(*args, **kwargs):
            nonlocal process_calls
            process_calls += 1
            return SimpleNamespace(
                stdout=json.dumps(
                    _result_payload(
                        inputTokens=2_147_483_648,
                        outputTokens=12,
                        billingEvidence="reported",
                    ),
                    ensure_ascii=False,
                ),
                stderr="must-not-escape",
                returncode=0,
            )

        adapter = self._adapter(runner=runner)
        generator = StagedContentCandidateGenerator(
            repository=self.repository,
            adapter=adapter,
            clock_ms=lambda: self.NOW,
        )
        work = ContentPhaseWork(
            command=replace(
                _phase_command("outline", 1), build_item_id="task5-item"
            ),
            attempt_initial_checkpoint={
                "questionCount": 5,
                "existingFingerprints": [],
                "generationFeedback": None,
            },
            item_lease_token="task5-lease",
            attempt_started_at=1_000,
            attempt_hard_deadline_at=self.DEADLINE,
            work_unit_deadline_at=self.DEADLINE,
            lease_expires_at=self.DEADLINE,
        )
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            result = generator.advance(work, heartbeat=lambda: True)
        self.assertEqual(process_calls, 1)
        self.assertTrue(result.process_started)
        self.assertEqual(
            (result.kind, result.result.safe_error_code),
            ("ambiguous", "provider_outcome_unknown"),
        )
        self.assertIsNone(result.result.input_tokens)
        self.assertIsNone(result.result.output_tokens)
        self.assertEqual(result.result.billing_evidence, "unknown")
        with self.database.transaction() as conn:
            row = conn.execute(
                "SELECT status, checkpoint_json, output_sha256, input_tokens, "
                "output_tokens, billing_evidence, safe_error_code "
                "FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item'"
            ).fetchone()
        self.assertEqual(row["status"], "ambiguous")
        self.assertIsNone(row["checkpoint_json"])
        self.assertIsNone(row["output_sha256"])
        self.assertIsNone(row["input_tokens"])
        self.assertIsNone(row["output_tokens"])
        self.assertEqual(row["billing_evidence"], "unknown")
        self.assertEqual(row["safe_error_code"], "provider_outcome_unknown")

    def test_item_subject_and_skill_are_part_of_the_locked_work_identity(self):
        prepared = self._prepared("outline", 1)
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_items "
                "SET subject = 'chinese', skill_id = 'number_sense_20' "
                "WHERE id = 'task5-item'"
            )
        with self.assertRaisesRegex(ValueError, "item|identity|subject|skill"):
            with self.database.transaction() as conn:
                self._reserve(conn, prepared)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()
        self.assertEqual(count["count"], 0)

    def test_retry_code_is_carried_from_the_actual_rejected_predecessor(self):
        self._persist_phase("outline", 1)
        self._persist_phase("raw_candidate", 2)
        phase3 = self._prepared("candidate_repair", 3)
        with self.database.transaction() as conn:
            self._set_phase(conn, "candidate_repair")
            reservation = self._reserve(conn, phase3)
            rejected = {
                "phaseStatus": "rejected",
                "rejectionCode": "candidate_repair_schema_rejected",
            }
            self.assertTrue(self._complete(conn, reservation, rejected))

        forged = _phase_command("candidate_repair_retry", 4)
        checkpoint = copy.deepcopy(forged.checkpoint)
        checkpoint["priorRejectionCode"] = "candidate_repair_originality_rejected"
        forged_prepared = self._prepared(
            "candidate_repair_retry",
            4,
            command=replace(forged, checkpoint=checkpoint),
        )
        with self.assertRaisesRegex(ValueError, "artifact|provenance|predecessor"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "candidate_repair_retry")
                self._reserve(conn, forged_prepared)
        correct = self._prepared("candidate_repair_retry", 4)
        with self.database.transaction() as conn:
            self._set_phase(conn, "candidate_repair_retry")
            reservation = self._reserve(conn, correct)
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item'"
            ).fetchone()
        self.assertTrue(reservation.created)
        self.assertEqual(count["count"], 4)

    def test_open_terminal_and_wrong_request_predecessors_never_create_target(self):
        prepared1 = self._prepared("outline", 1)
        prepared2 = self._prepared("raw_candidate", 2)
        with self.database.transaction() as conn:
            self._reserve(conn, prepared1)
        with self.assertRaisesRegex(ValueError, "predecessor"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "raw_candidate")
                self._reserve(conn, prepared2)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()
        self.assertEqual(count["count"], 1)

        config = fresh_test_config()
        self.database = Database(config["DATABASE_URL"])
        self.repository = DynamicLearningCourseRepository(self.database)
        self._insert_active_content_item()
        with self.database.transaction() as conn:
            reservation = self._reserve(conn, prepared1)
            self.repository.complete_provider_dispatch(
                conn,
                dispatch_id=str(reservation.dispatch["id"]),
                build_item_id="task5-item",
                generation_request_id="phase-request-1",
                item_lease_token="task5-lease",
                outcome="failed_safe",
                checkpoint=None,
                output_sha256=None,
                provider_request_id_hash=None,
                input_tokens=None,
                output_tokens=None,
                billing_evidence="unknown",
                safe_error_code="provider_no_candidate",
                completed_at=self.NOW + 1,
            )
        with self.assertRaisesRegex(ValueError, "predecessor"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "raw_candidate")
                self._reserve(conn, prepared2)

        config = fresh_test_config()
        self.database = Database(config["DATABASE_URL"])
        self.repository = DynamicLearningCourseRepository(self.database)
        self._insert_active_content_item()
        self._persist_phase("outline", 1)
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_course_provider_dispatches "
                "SET generation_request_id = 'wrong-request' "
                "WHERE build_item_id = 'task5-item' AND phase = 'outline'"
            )
        with self.assertRaisesRegex(ValueError, "identity|predecessor"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "raw_candidate")
                self._reserve(conn, prepared2)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item' AND phase = 'raw_candidate'"
            ).fetchone()
        self.assertEqual(count["count"], 0)

        config = fresh_test_config()
        self.database = Database(config["DATABASE_URL"])
        self.repository = DynamicLearningCourseRepository(self.database)
        self._insert_active_content_item()
        self._persist_phase("outline", 1)
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_course_provider_dispatches SET output_sha256 = ? "
                "WHERE build_item_id = ? AND phase = 'outline'",
                ("0" * 64, "task5-item"),
            )
        with self.assertRaisesRegex(ValueError, "hash|predecessor"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "raw_candidate")
                self._reserve(conn, prepared2)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()
        self.assertEqual(count["count"], 1)

    def test_full_valid_chain_and_phase14_inventory_proof(self):
        inventory = ["a" * 64]
        for phase, ordinal in (
            ("outline", 1),
            ("raw_candidate", 2),
            ("candidate_repair", 3),
            ("lesson_text", 5),
            ("reconciliation", 6),
            ("independent_verification", 11),
            ("consistency_repair", 12),
        ):
            self._persist_phase(phase, ordinal, inventory=inventory)

        forged = _phase_command("verification_after_repair", 14)
        checkpoint = copy.deepcopy(forged.checkpoint)
        checkpoint["existingFingerprints"] = ["f" * 64]
        checkpoint["validation"]["existingFingerprintsChecked"] = 1
        forged_prepared = self._prepared(
            "verification_after_repair",
            14,
            command=replace(forged, checkpoint=checkpoint),
        )
        with self.assertRaisesRegex(ValueError, "phase 11|inventory|input"):
            with self.database.transaction() as conn:
                self._set_phase(conn, "verification_after_repair")
                self._reserve(conn, forged_prepared)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item' AND phase = 'verification_after_repair'"
            ).fetchone()
        self.assertEqual(count["count"], 0)

        valid = _phase_command("verification_after_repair", 14)
        valid_checkpoint = copy.deepcopy(valid.checkpoint)
        valid_checkpoint["existingFingerprints"] = inventory
        valid_checkpoint["validation"]["existingFingerprintsChecked"] = 1
        prepared = self._prepared(
            "verification_after_repair",
            14,
            command=replace(valid, checkpoint=valid_checkpoint),
        )
        with self.database.transaction() as conn:
            self._set_phase(conn, "verification_after_repair")
            reservation = self._reserve(conn, prepared)
            self.assertTrue(
                self._complete(
                    conn,
                    reservation,
                    self._accepted_checkpoint(
                        "verification_after_repair", existing_count=1
                    ),
                )
            )
            rows = conn.execute(
                "SELECT phase_ordinal, status FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item' ORDER BY phase_ordinal"
            ).fetchall()
        self.assertEqual(
            [(row["phase_ordinal"], row["status"]) for row in rows],
            [(1, "succeeded"), (2, "succeeded"), (3, "succeeded"),
             (5, "succeeded"), (6, "succeeded"), (11, "succeeded"),
             (12, "succeeded"), (14, "succeeded")],
        )

    def test_two_generators_have_one_process_and_loser_busy(self):
        second_reserved = threading.Event()
        call_lock = threading.Lock()
        reserve_calls = 0
        process_calls = 0

        class ObservedRepository(DynamicLearningCourseRepository):
            def reserve_provider_dispatch(inner_self, conn, **kwargs):
                nonlocal reserve_calls
                reservation = super().reserve_provider_dispatch(conn, **kwargs)
                with call_lock:
                    reserve_calls += 1
                    if reserve_calls >= 2:
                        second_reserved.set()
                return reservation

        def runner(*args, **kwargs):
            nonlocal process_calls
            with call_lock:
                process_calls += 1
            self.assertTrue(second_reserved.wait(5), "loser did not observe committed reservation")
            return SimpleNamespace(
                stdout=json.dumps(_result_payload(), ensure_ascii=False),
                stderr="must-not-escape",
                returncode=0,
            )

        repository = ObservedRepository(self.database)
        adapter = self._adapter(runner=runner)
        generator = StagedContentCandidateGenerator(
            repository=repository,
            adapter=adapter,
            clock_ms=lambda: self.NOW,
        )
        work = ContentPhaseWork(
            command=replace(_phase_command("outline", 1), build_item_id="task5-item"),
            attempt_initial_checkpoint={
                "questionCount": 5,
                "existingFingerprints": [],
                "generationFeedback": None,
            },
            item_lease_token="task5-lease",
            attempt_started_at=1_000,
            attempt_hard_deadline_at=self.DEADLINE,
            work_unit_deadline_at=self.DEADLINE,
            lease_expires_at=self.DEADLINE,
        )
        barrier = threading.Barrier(3)
        results = []
        failures = []

        def invoke():
            try:
                barrier.wait(5)
                results.append(generator.advance(work, heartbeat=lambda: True))
            except BaseException as error:
                failures.append(error)

        threads = [threading.Thread(target=invoke) for _ in range(2)]
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only-secret"}):
            for thread in threads:
                thread.start()
            barrier.wait(5)
            for thread in threads:
                thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(process_calls, 1)
        self.assertEqual(sum(result.process_started for result in results), 1)
        self.assertEqual({result.kind for result in results}, {"succeeded", "busy"})
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches"
            ).fetchone()
        self.assertEqual(count["count"], 1)

    def test_completion_and_replay_overlap_use_distinct_connections_without_deadlock(self):
        prepared = self._prepared("outline", 1)
        with self.database.transaction() as conn:
            reservation = self._reserve(conn, prepared)
        item_locked = threading.Event()
        replay_started = threading.Event()
        connection_ids = []
        outcomes = []
        failures = []

        def complete_owner():
            try:
                with self.database.transaction() as conn:
                    connection_ids.append(conn.execute("SELECT CONNECTION_ID() AS id").fetchone()["id"])
                    conn.execute(
                        "SELECT id FROM learning_catalog_build_items WHERE id = ? FOR UPDATE",
                        ("task5-item",),
                    ).fetchone()
                    item_locked.set()
                    self.assertTrue(replay_started.wait(5))
                    outcomes.append(self._complete(conn, reservation, _outline_checkpoint()))
            except BaseException as error:
                failures.append(error)

        def replay_owner():
            try:
                self.assertTrue(item_locked.wait(5))
                with self.database.transaction() as conn:
                    connection_ids.append(conn.execute("SELECT CONNECTION_ID() AS id").fetchone()["id"])
                    replay_started.set()
                    outcomes.append(self._reserve(conn, prepared).created)
            except BaseException as error:
                failures.append(error)

        threads = [threading.Thread(target=complete_owner), threading.Thread(target=replay_owner)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(set(connection_ids)), 2)
        type(self).last_completion_overlap_connection_ids = tuple(connection_ids)
        self.assertEqual(sorted(outcomes), [False, True])

    def test_predecessor_lock_wait_crossing_fit_boundary_rolls_back_target(self):
        self._persist_phase("outline", 1)
        prepared = self._prepared("raw_candidate", 2)
        with self.database.transaction() as conn:
            self._set_phase(conn, "raw_candidate")
        locks_held = threading.Event()
        waiter_started = threading.Event()
        connection_ids = []
        failures = []

        def lock_owner():
            try:
                with self.database.transaction() as conn:
                    connection_ids.append(conn.execute("SELECT CONNECTION_ID() AS id").fetchone()["id"])
                    conn.execute(
                        "SELECT id FROM learning_catalog_build_items WHERE id = ? FOR UPDATE",
                        ("task5-item",),
                    ).fetchone()
                    conn.execute(
                        "SELECT id FROM learning_course_provider_dispatches "
                        "WHERE build_item_id = ? AND phase_ordinal = 1 FOR UPDATE",
                        ("task5-item",),
                    ).fetchone()
                    locks_held.set()
                    self.assertTrue(waiter_started.wait(5))
            except BaseException as error:
                failures.append(error)

        def reserve_waiter():
            try:
                self.assertTrue(locks_held.wait(5))
                with self.database.transaction() as conn:
                    connection_ids.append(conn.execute("SELECT CONNECTION_ID() AS id").fetchone()["id"])
                    waiter_started.set()
                    with self.assertRaisesRegex(ValueError, "budget|deadline"):
                        self._reserve(
                            conn,
                            prepared,
                            clock=lambda: self.DEADLINE - self.REQUIRED_BUDGET + 1,
                        )
            except BaseException as error:
                failures.append(error)

        threads = [threading.Thread(target=lock_owner), threading.Thread(target=reserve_waiter)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(failures, [])
        self.assertEqual(len(set(connection_ids)), 2)
        type(self).last_predecessor_wait_connection_ids = tuple(connection_ids)
        with self.database.transaction() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = 'task5-item' AND phase = 'raw_candidate'"
            ).fetchone()
        self.assertEqual(count["count"], 0)

    def _insert_active_content_item(self):
        canary = json.dumps(
            {"version": "mira.learning.primary-1-canary.v1", "targets": []},
            separators=(",", ":"),
        )
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO learning_catalog_releases("
                "id, curriculum_version, title, status, quality_status, "
                "required_boundary_count, ready_item_count, created_at, updated_at) "
                "VALUES ('task5-release', 'primary-cn-2026.1', 'Task5', 'draft', "
                "'building', 1, 0, 1, 1)"
            )
            conn.execute(
                "INSERT INTO learning_catalog_build_jobs("
                "id, request_id, release_id, curriculum_version, status, target_spec_json, "
                "total_item_count, ready_item_count, failed_item_count, execution_mode, "
                "content_manifest_version, canary_manifest_json, stage_ceiling, "
                "created_at, updated_at) VALUES ("
                "'task5-build', 'task5-build-request', 'task5-release', "
                "'primary-cn-2026.1', 'running', '{}', 1, 0, 0, 'content_only', ?, ?, "
                "'content_ready', 1, 1)",
                (TARGET_SCHEMA_V2, canary),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_build_items(
                  id, build_job_id, release_id, grade_code, subject, skill_id,
                  curriculum_version, boundary_version, variant_ordinal, status,
                  attempt_count, package_attempt_count, claim_origin_status,
                  generation_request_id, active_generation_request_id,
                  execution_mode_snapshot, content_manifest_version_snapshot,
                  subject_ordinal, boundary_ordinal, content_phase,
                  content_gate_status, content_gate_attempt_count,
                  content_lease_token, content_lease_expires_at,
                  content_heartbeat_at, content_attempt_started_at,
                  content_provider_attempt_hard_deadline_at,
                  content_work_unit_deadline_at, content_claim_attempt_ordinal,
                  created_at, updated_at
                ) VALUES (
                  'task5-item', 'task5-build', 'task5-release', 'primary_1',
                  'math', 'addition_subtraction_20', 'primary-cn-2026.1',
                  'boundary-v1', 1, 'processing', 1, 0, 'pending',
                  'phase-request-1', 'phase-request-1', 'content_only', ?, 1, 1,
                  'outline', 'not_started', 0, 'task5-lease', ?, ?, 1000, ?, ?, 1, 1, 1
                )
                """,
                (TARGET_SCHEMA_V2, self.DEADLINE, self.NOW, self.DEADLINE, self.DEADLINE),
            )


if __name__ == "__main__":
    unittest.main()
