from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)
from services.openmaic_full_runtime_service import (
    FORMAL_REQUIRED_FEATURES,
    OpenMaicFullRuntimeService,
    OpenMaicRuntimeServiceError,
)
from services.lesson_package_validator import formal_runtime_teaching_brief
from tests.test_openmaic_full_runtime import (
    _complete_sample_widget_content,
    _generated_agent,
    _sample_parity_classroom,
    _sample_speech,
)


FINGERPRINT = "6" * 64
SOURCE_QUESTIONS = [
    {
        "id": f"q{ordinal}",
        "type": "numeric",
        "prompt": f"一个十和{ordinal}个一是多少？",
        "answer": str(10 + ordinal),
        "skill": "number_sense_20",
        "hint": "先看有几个十，再看有几个一。",
        "explanation": "把一个十和几个一合起来。",
        "verificationExpression": f"10+{ordinal}",
        "evaluation": {"expected": str(10 + ordinal), "normalization": ["trim"]},
    }
    for ordinal in range(1, 6)
]
SOURCE_COURSE_CONTENT = {
    "schemaVersion": "mira.learning.course.v1",
    "sessionKind": "lesson",
    "outcomeMode": "scored_deterministic",
    "sourceAuthority": {
        "basis": "provided_skill_boundary",
        "contentOrigin": "openmaic_kimi_candidate",
        "textbookDependency": "none",
    },
    "reviewPolicy": "programmatic_guarded",
    "intro": "把十个一组成一个十。",
    "estimatedMinutes": 10,
    "questions": SOURCE_QUESTIONS,
    "teachingFlow": {
        "schemaVersion": "mira.learning.teaching-flow.v1",
        "teach": {
            "title": "十和一",
            "sayText": "先数出十个，再把它们看成一个十。",
            "keyPoints": ["十个一是一个十"],
        },
        "demoQuestionId": "q1",
        "guidedQuestionIds": ["q2", "q3"],
        "independentQuestionIds": ["q4", "q5"],
        "recap": {"sayText": "一个十和几个一组成十几。"},
    },
}
SOURCE_COURSE_CONTENT_JSON = json.dumps(
    SOURCE_COURSE_CONTENT,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
SOURCE_COURSE_CONTENT_SHA256 = hashlib.sha256(
    SOURCE_COURSE_CONTENT_JSON.encode("utf-8")
).hexdigest()
TEACHING_BRIEF = {
    "schemaVersion": "mira.learning.formal-runtime-teaching-brief.v1",
    "sourceCourseContentSha256": SOURCE_COURSE_CONTENT_SHA256,
    "course": {
        "id": "candidate-course-1",
        "version": "course-version-1",
        "gradeCode": "primary_1",
        "subject": "math",
        "skillId": "number_sense_20",
        "title": "20以内数的认识",
        "objective": "理解20以内数的组成",
    },
    "lesson": {
        "intro": "把十个一组成一个十。",
        "estimatedMinutes": 10,
            "teachingFlow": {
                "schemaVersion": "mira.learning.teaching-flow.v1",
            "teach": {
                "title": "十和一",
                "sayText": "先数出十个，再把它们看成一个十。",
                "keyPoints": ["十个一是一个十"],
            },
                "recap": {"sayText": "一个十和几个一组成十几。"},
                "demoQuestionId": "q1",
                "guidedQuestionIds": ["q2", "q3"],
                "independentQuestionIds": ["q4", "q5"],
            },
        "questions": [
            {
                key: value
                for key, value in question.items()
                if key
                in {"id", "type", "prompt", "skill", "hint", "explanation"}
            }
            for question in SOURCE_QUESTIONS
        ],
    },
    "authority": {
        "source": "locked_learning_course",
        "answerContractProvided": False,
        "scoringRulesProvided": False,
        "providerSecretsProvided": False,
    },
}
TEACHING_BRIEF_SHA256 = hashlib.sha256(
    json.dumps(
        TEACHING_BRIEF,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def _formal_classroom() -> dict:
    classroom = _sample_parity_classroom()
    classroom["stage"]["id"] = "formal-classroom-1"
    formal_teacher = _generated_agent("teacher-1", "teacher")
    formal_teacher.update(
        {
            "name": "小数老师",
            "avatar": "/avatars/teacher.png",
            "voiceConfig": {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Ethan",
            },
        }
    )
    classroom["stage"]["generatedAgentConfigs"] = [
        formal_teacher,
        *[
            _generated_agent(f"student-{ordinal}", "student")
            for ordinal in range(1, 5)
        ],
    ]

    slides = []
    quizzes = []
    interactives = []
    for scene in classroom["scenes"]:
        if scene["type"] == "slide":
            slides.append(deepcopy(scene))
        elif scene["type"] == "quiz":
            quizzes.append(deepcopy(scene))
        elif len(interactives) < 3:
            interactives.append(deepcopy(scene))

    while len(slides) < 5:
        ordinal = len(slides) + 1
        slides.append(
            {
                "id": f"formal-slide-{ordinal}",
                "stageId": "stage-1",
                "title": f"正式讲解 {ordinal}",
                "order": 0,
                "type": "slide",
                "content": {
                    "type": "slide",
                    "canvas": {
                        "elements": [
                            {
                                "id": f"formal-text-{ordinal}",
                                "type": "text",
                                "text": f"正式讲解内容 {ordinal}",
                                "visible": True,
                                "width": 320,
                                "height": 80,
                            }
                        ]
                    },
                },
                "actions": [
                    {
                        "id": f"formal-spotlight-{ordinal}",
                        "type": "spotlight",
                        "elementId": f"formal-text-{ordinal}",
                    }
                ],
            }
        )

    scenes = slides[:5] + quizzes[:2] + interactives[:3]
    scored_quiz_groups = iter((("q2", "q3"), ("q4", "q5")))
    source_questions = {question["id"]: question for question in SOURCE_QUESTIONS}
    for index, scene in enumerate(scenes, start=1):
        scene["stageId"] = "formal-classroom-1"
        scene["order"] = index - 1
        scene["actions"] = [
            action
            for action in scene.get("actions", [])
            if action.get("type") not in {"speech", "discussion"}
        ]
        if scene["type"] == "slide":
            for element in scene["content"]["canvas"]["elements"]:
                if element.get("type") == "text":
                    element.setdefault("text", f"正式课件内容 {index}")
                    element.setdefault("visible", True)
                    element.setdefault("width", 320)
                    element.setdefault("height", 80)
            focus_target = next(
                element["id"]
                for element in scene["content"]["canvas"]["elements"]
                if element.get("type") == "text"
            )
            scene["actions"] = [
                {
                    "id": f"formal-spotlight-{index}",
                    "type": "spotlight",
                    "elementId": focus_target,
                },
                _sample_speech(index),
                *[
                    action
                    for action in scene["actions"]
                    if action.get("type") != "spotlight"
                ],
            ]
        elif scene["type"] == "quiz":
            scene["actions"].insert(0, _sample_speech(index))
            scene["content"]["questions"] = [
                {
                    "id": question_id,
                    "type": "short_answer",
                    "question": source_questions[question_id]["prompt"],
                    "hasAnswer": False,
                    "answer": None,
                    "points": 1,
                }
                for question_id in next(scored_quiz_groups)
            ]
        else:
            scene["actions"].insert(0, _sample_speech(index))
    scenes[0]["actions"].append(
        {
            "id": "formal-discussion-1",
            "type": "discussion",
            "topic": "请同学一说说第一种方法",
            "agentId": "student-1",
        }
    )
    scenes[1]["actions"].append(
        {
            "id": "formal-discussion-2",
            "type": "discussion",
            "topic": "请同学二比较两种方法",
            "agentId": "student-2",
        }
    )
    scenes[7]["content"] = _complete_sample_widget_content("simulation")
    scenes[7]["content"]["html"] = scenes[7]["content"]["html"].replace(
        "</body>",
        """
<script>
window.addEventListener('message', (event) => {
  if (event.data?.type === 'HIGHLIGHT_ELEMENT') {
    document.getElementById(event.data.target)?.classList.add('highlighted');
  }
});
</script></body>
""",
    )
    scenes[7]["actions"].append(
        {
            "id": "formal-highlight-1",
            "type": "widget_highlight",
            "target": "count-slider",
        }
    )
    scenes[8]["content"] = _complete_sample_widget_content("game")
    scenes[9]["content"] = _complete_sample_widget_content("visualization3d")
    classroom["scenes"] = scenes
    return classroom


class _CandidateRepository:
    def __init__(self):
        self.rows: list[dict] = []
        self.quarantined: list[str] = []
        self.generation_authority_error: str | None = None
        self.completion_authority_error: str | None = None
        self.provider_circuit = {
            "status": "closed",
            "reason_code": None,
            "last_probe_at": 1,
            "probe_succeeded_at": 1,
        }

    @contextmanager
    def transaction(self):
        yield object()

    def get_formal_candidate_generation_authority(self, _conn, **kwargs):
        if self.generation_authority_error:
            raise ValueError(self.generation_authority_error)
        brief = deepcopy(TEACHING_BRIEF)
        brief["course"].update(
            id=kwargs["course_id"], version=kwargs["course_version"]
        )
        digest = hashlib.sha256(
            json.dumps(
                brief,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        payload = {
            "teachingBrief": brief,
            "teachingBriefSha256": digest,
            "sourceCourseContentSha256": SOURCE_COURSE_CONTENT_SHA256,
            "professionalCreationPolicy": deepcopy(getattr(
                self, "professional_policy",
                OpenMaicFullRuntimeClient.LEGACY_FORMAL_PROFESSIONAL_CREATION_POLICY,
            )),
        }
        from integrations.openmaic_formal_pedagogy import adaptive_policy, registered_grade_boundary
        if adaptive_policy(payload["professionalCreationPolicy"]):
            boundary = registered_grade_boundary(grade_code=brief["course"]["gradeCode"],
                subject=brief["course"]["subject"], skill_id=brief["course"]["skillId"])
            payload.update(gradeBoundary=boundary, gradeBoundarySha256=hashlib.sha256(
                json.dumps(boundary, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        return payload

    def get_formal_provider_circuit(self, _conn, **_kwargs):
        return dict(self.provider_circuit) if self.provider_circuit else None

    def open_formal_provider_circuit(
        self, _conn, *, reason_code, runtime_id, now
    ):
        self.provider_circuit = {
            "status": "open",
            "reason_code": reason_code,
            "opened_by_runtime_id": runtime_id,
            "last_probe_at": None,
            "probe_succeeded_at": None,
            "updated_at": now,
        }
        return dict(self.provider_circuit)

    def close_formal_provider_circuit_after_probe(self, _conn, *, now):
        self.provider_circuit = {
            "status": "closed",
            "reason_code": None,
            "last_probe_at": now,
            "probe_succeeded_at": now,
        }
        return dict(self.provider_circuit)

    def record_formal_provider_probe_failure(
        self, _conn, *, reason_code, now
    ):
        return self.open_formal_provider_circuit(
            _conn,
            reason_code=reason_code,
            runtime_id=None,
            now=now,
        )

    def reserve_candidate_runtime(self, _conn, **kwargs):
        for row in self.rows:
            if row["request_id"] == kwargs["runtime_request_id"]:
                expected = (
                    kwargs["build_item_id"],
                    kwargs["course_id"],
                    kwargs["course_version"],
                    kwargs["package_id"],
                    kwargs["package_version"],
                    kwargs["target_fingerprint"],
                )
                actual = (
                    row["candidate_build_item_id"],
                    row["course_id"],
                    row["course_version"],
                    row["package_id"],
                    row["package_version"],
                    row["candidate_target_fingerprint"],
                )
                if actual != expected:
                    raise ValueError("candidate runtime request conflict")
                return row, False
        attempts = [
            row
            for row in self.rows
            if row["candidate_build_item_id"] == kwargs["build_item_id"]
        ]
        if attempts:
            previous = attempts[-1]
            if previous["quality_status"] == "quarantined":
                raise ValueError("candidate runtime state is ambiguous")
            if previous["status"] != "failed":
                raise ValueError("candidate runtime attempt is still active")
        attempt = len(attempts) + 1
        provider_attempt = (
            len(
                [
                    row
                    for row in attempts
                    if row.get("provider_attempt_ordinal") is not None
                ]
            )
            + 1
        )
        if attempt > 16 or provider_attempt > 3:
            raise ValueError("candidate Provider attempt limit reached")
        row = {
            "id": kwargs["runtime_id"],
            "request_id": kwargs["runtime_request_id"],
            "attempt_ordinal": attempt,
            "provider_attempt_ordinal": provider_attempt,
            "retry_of_runtime_id": attempts[-1]["id"] if attempts else None,
            "course_id": kwargs["course_id"],
            "course_version": kwargs["course_version"],
            "package_id": kwargs["package_id"],
            "package_version": kwargs["package_version"],
            "candidate_build_item_id": kwargs["build_item_id"],
            "candidate_release_id": "candidate-release-1",
            "candidate_grade_code": "primary_1",
            "candidate_target_fingerprint": kwargs["target_fingerprint"],
            "candidate_binding_contract_version": (
                "mira.learning.candidate-runtime-binding.v1"
            ),
            "candidate_bound_at": kwargs["now"],
            "status": "pending",
            "quality_status": "pending_review",
            "feature_manifest_json": kwargs["feature_manifest"],
            "upstream_job_id": None,
            "upstream_classroom_id": None,
            "ready_at": None,
            "updated_at": kwargs["now"],
        }
        self.rows.append(row)
        return row, True

    def mark_generating(self, _conn, *, runtime_id, upstream_job_id, now):
        row = next(item for item in self.rows if item["id"] == runtime_id)
        row.update(
            status="generating",
            upstream_job_id=upstream_job_id,
            updated_at=now,
        )
        return True

    def assert_candidate_completion_authority(
        self,
        _conn,
        *,
        runtime_id,
        build_item_id,
        target_fingerprint,
        expected_upstream_job_id,
    ):
        if self.completion_authority_error:
            raise ValueError(self.completion_authority_error)
        row = next(item for item in self.rows if item["id"] == runtime_id)
        if (
            row["candidate_build_item_id"] != build_item_id
            or row["candidate_target_fingerprint"] != target_fingerprint
            or row.get("upstream_job_id") != expected_upstream_job_id
        ):
            raise ValueError("candidate completion authority is no longer current")
        return row

    def quarantine_candidate_dispatch(
        self, _conn, *, runtime_id, error_code, error_message_safe, now
    ):
        row = next(item for item in self.rows if item["id"] == runtime_id)
        row.update(
            status="failed",
            quality_status="quarantined",
            error_code=error_code,
            error_message_safe=error_message_safe,
            updated_at=now,
        )
        self.quarantined.append(runtime_id)
        return row

    def quarantine_candidate_generation(self, _conn, **kwargs):
        return self.quarantine_candidate_dispatch(_conn, **kwargs)

    def reject_candidate_generation(
        self,
        _conn,
        *,
        runtime_id,
        error_code,
        error_message_safe,
        now,
        provider_attempt_consumed=True,
    ):
        row = next(item for item in self.rows if item["id"] == runtime_id)
        row.update(
            status="failed",
            quality_status="rejected",
            error_code=error_code,
            error_message_safe=error_message_safe,
            updated_at=now,
        )
        if not provider_attempt_consumed:
            row["provider_attempt_ordinal"] = None
        return row

    def get_runtime_classroom(self, _conn, *, runtime_id, **_kwargs):
        return next(item for item in self.rows if item["id"] == runtime_id)

    def get_by_upstream_job(self, _conn, *, upstream_job_id):
        return next(
            (
                item
                for item in self.rows
                if item.get("upstream_job_id") == upstream_job_id
            ),
            None,
        )

    def mark_ready(
        self,
        _conn,
        *,
        runtime_id,
        upstream_classroom_id,
        feature_manifest,
        now,
    ):
        row = next(item for item in self.rows if item["id"] == runtime_id)
        row.update(
            status="ready",
            upstream_classroom_id=upstream_classroom_id,
            feature_manifest_json=feature_manifest,
            ready_at=now,
            updated_at=now,
        )

    def mark_failed(
        self, _conn, *, runtime_id, error_code, error_message_safe, now
    ):
        row = next(item for item in self.rows if item["id"] == runtime_id)
        row.update(
            status="failed",
            error_code=error_code,
            error_message_safe=error_message_safe,
            updated_at=now,
        )

    @staticmethod
    def decode_json(value, _fallback):
        return value


class _CandidateClient:
    def __init__(self, *, lose_response: bool = False, query_ambiguous: bool = False):
        self.lose_response = lose_response
        self.query_ambiguous = query_ambiguous
        self.start_calls: list[dict] = []
        self.query_calls: list[str] = []
        self.jobs: dict[str, SimpleNamespace] = {}

    @staticmethod
    def formal_generation_readiness():
        return {
            "ready": True,
            "contractVersion": (
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
            ),
        }

    @staticmethod
    def formal_generation_provider_canary():
        return {
            "ready": True,
            "providerId": "deepseek",
            "modelId": "deepseek-v4-pro",
            "error": None,
        }

    def get_generation_job_by_request_id(self, runtime_request_id):
        self.query_calls.append(runtime_request_id)
        if self.query_ambiguous:
            raise OpenMaicFullRuntimeError(
                "openmaic_formal_query_unavailable",
                "formal query unavailable",
                status_code=503,
            )
        return self.jobs.get(runtime_request_id)

    def start_generation(self, **kwargs):
        self.start_calls.append(kwargs)
        request_payload = {
            "requirement": kwargs["requirement"],
            "enableWebSearch": kwargs["enable_web_search"],
            "enableImageGeneration": kwargs["enable_image_generation"],
            "enableVideoGeneration": kwargs["enable_video_generation"],
            "enableTTS": kwargs["enable_tts"],
            "agentMode": kwargs["agent_mode"],
            "runtimeRequestId": kwargs["runtime_request_id"],
            "formalRuntimeContract": kwargs["formal_runtime_contract"],
            "coursewareAuthority": dict(
                OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
            ),
            "professionalCreationPolicy": deepcopy(
                kwargs["professional_creation_policy"]
            ),
        }
        job = SimpleNamespace(
            job_id="formal-job-1",
            status="queued",
            step="queued",
            progress=0,
            done=False,
            classroom_id=None,
            scenes_count=10,
            error=None,
            speech_action_count=10,
            runtime_request_id=kwargs["runtime_request_id"],
            formal_contract_version=(
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
            ),
            formal_input_sha256=OpenMaicFullRuntimeClient.formal_input_sha256(
                request_payload
            ),
            dispatch_ambiguous=False,
        )
        self.jobs[kwargs["runtime_request_id"]] = job
        if self.lose_response:
            raise OpenMaicFullRuntimeError(
                "openmaic_transport_error",
                "response lost",
                status_code=503,
            )
        return job

    def get_generation_job(self, upstream_job_id):
        return next(
            job for job in self.jobs.values() if job.job_id == upstream_job_id
        )

    def get_classroom(self, classroom_id):
        assert classroom_id == "formal-classroom-1"
        return _formal_classroom()


class _CandidateCatalogRepository:
    def __init__(self):
        self.receipt = None

    def reserve_classroom_item_receipt(self, _conn, **kwargs):
        if self.receipt is None:
            self.receipt = {
                **kwargs,
                "classroom_status": "pending",
                "tts_status": "pending",
                "asr_roundtrip_status": "pending",
                "conversation_provider_status": "pending",
                "publication_status": "pending",
                "auto_validated": 0,
            }
            return self.receipt, True
        return self.receipt, False

    def get_classroom_item_receipt(self, _conn, *, build_item_id, **_kwargs):
        if self.receipt is None or self.receipt["build_item_id"] != build_item_id:
            return None
        return self.receipt

    def record_classroom_item_evidence(
        self,
        _conn,
        *,
        build_item_id,
        evidence_kind,
        outcome,
        receipt_hash,
        completed_at,
        now,
    ):
        assert self.receipt["build_item_id"] == build_item_id
        assert evidence_kind == "classroom"
        self.receipt.update(
            classroom_status=outcome,
            classroom_receipt_hash=receipt_hash,
            classroom_completed_at=completed_at,
            updated_at=now,
        )
        return self.receipt


def _candidate_service(client: _CandidateClient | None = None):
    service = object.__new__(OpenMaicFullRuntimeService)
    service.enabled = True
    service.generation_enabled = True
    service.public_url = "https://classroom.mira.test"
    service.video_export_enabled = False
    service.repository = _CandidateRepository()
    service.catalog_repository = _CandidateCatalogRepository()
    service.client = client or _CandidateClient()
    return service


class FormalRuntimeCandidateGenerationTest(unittest.TestCase):
    def test_provider_circuit_does_not_block_deterministic_classroom_compilation(self):
        service = _candidate_service()
        service.repository.provider_circuit = {
            "status": "open",
            "reason_code": "openmaic_formal_provider_billing_blocked",
            "last_probe_at": 1,
            "probe_succeeded_at": None,
        }

        service.issue_candidate_generation(
            build_item_id="candidate-item-fused",
            course_id="candidate-course-fused",
            course_version="course-version-1",
            package_id="candidate-package-fused",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-fused",
        )

        self.assertEqual(len(service.repository.rows), 1)
        self.assertEqual(len(service.client.start_calls), 1)
        generation = json.loads(service.client.start_calls[0]["requirement"])[
            "generation"
        ]
        self.assertEqual(generation["mode"], "deterministic_no_llm")
        self.assertEqual(generation["providerCalls"], 0)

    def test_explicit_provider_canary_closes_the_circuit(self):
        service = _candidate_service()
        service.repository.provider_circuit = None

        result = service.probe_formal_generation_provider()

        self.assertTrue(result["ready"])
        self.assertEqual(result["providerId"], "deepseek")
        self.assertEqual(result["modelId"], "deepseek-v4-pro")
        self.assertTrue(result["circuit"]["dispatchAllowed"])
        self.assertEqual(service.repository.provider_circuit["status"], "closed")

    def test_client_classifies_billing_rejection_without_exposing_raw_error(self):
        client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100")
        job = client._job_from_payload(
            {
                "jobId": "formal-job-billing",
                "status": "failed",
                "done": True,
                "error": (
                    "Provider account is suspended due to insufficient balance. "
                    "Please recharge."
                ),
            }
        )

        self.assertEqual(
            job.failure_code, "openmaic_formal_provider_billing_blocked"
        )

    def test_teaching_brief_rejects_nested_text_type_confusion(self):
        poisoned_content = deepcopy(SOURCE_COURSE_CONTENT)
        poisoned_content["questions"][0]["prompt"] = {"answer": "42"}
        poisoned_content["questions"][1]["hint"] = ["evaluation", "42"]
        course = {
            "id": "candidate-course-1",
            "version": "course-version-1",
            "grade_code": "primary_1",
            "subject": "math",
            "node_code": "number_sense_20",
            "title": "20以内数的认识",
            "objective": "理解20以内数的组成",
            "content_json": json.dumps(
                poisoned_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }

        with self.assertRaisesRegex(ValueError, "question 1 prompt is invalid"):
            formal_runtime_teaching_brief(course)

    def test_formal_readiness_is_scoped_and_rejects_the_wrong_runtime_version(self):
        requests = []

        class Response:
            status = 200

            def __init__(self, request):
                self.request = request
                self.headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.request.full_url

            def read(self, _limit):
                return json.dumps(
                    {
                        "success": True,
                        "status": "ok",
                        "version": "0.3.1",
                        "capabilities": {
                            "formalGeneration": True,
                            "professionalAgent": True,
                            "webSearch": True,
                            "speechAudioGeneration": True,
                        },
                        "runtimePolicy": {
                            "formalGeneration": (
                                OpenMaicFullRuntimeClient.FORMAL_GENERATION_POLICY
                            ),
                            "professionalResearch": (
                                OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_RESEARCH_POLICY
                            ),
                            "modelPolicy": (
                                OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_MODEL_POLICY
                            ),
                        },
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            return Response(request)

        client = OpenMaicFullRuntimeClient("https://runtime.mira.test")
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            side_effect=fake_urlopen,
        ):
            readiness = client.formal_generation_readiness()

        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["reportedVersion"], "0.3.1")
        self.assertTrue(
            requests[0][0].full_url.endswith(
                "/api/health?scope=formal-generation"
            )
        )

    def test_sample_and_formal_readiness_keep_distinct_health_scopes(self):
        calls = []
        sample_payload = {
            "success": True,
            "status": "ok",
            "version": OpenMaicFullRuntimeClient.SAMPLE_RUNTIME_VERSION,
            "capabilities": {"tts": True, "asr": True},
            "runtimePolicy": {
                "tts": OpenMaicFullRuntimeClient.SAMPLE_TTS_POLICY,
                "asr": OpenMaicFullRuntimeClient.SAMPLE_ASR_POLICY,
                "structuredScene": (
                    OpenMaicFullRuntimeClient.SAMPLE_STRUCTURED_SCENE_POLICY
                ),
            },
        }
        formal_payload = {
            "success": True,
            "status": "ok",
            "version": OpenMaicFullRuntimeClient.FORMAL_RUNTIME_VERSION,
            "capabilities": {
                "formalGeneration": True,
                "professionalAgent": True,
                "webSearch": True,
                "speechAudioGeneration": True,
            },
            "runtimePolicy": {
                "webSearch": {"schemaVersion":"mira.openmaic.web-search-production-config.v1","providerId":"brave","productionMode":"brave_api","formalProductionConfigured":True,"verification":"configuration_only"},
                "formalGeneration": (
                    OpenMaicFullRuntimeClient.FORMAL_GENERATION_POLICY
                ),
                "professionalResearch": (
                    OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_RESEARCH_POLICY
                ),
                "modelPolicy": (
                    OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_MODEL_POLICY
                ),
            },
        }

        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __init__(self, request, payload):
                self.request = request
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.request.full_url

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 30.0)
            calls.append(request.full_url)
            payload = (
                formal_payload
                if request.full_url.endswith("?scope=formal-generation")
                else sample_payload
            )
            return Response(request, payload)

        client = OpenMaicFullRuntimeClient("https://runtime.mira.test")
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            side_effect=fake_urlopen,
        ):
            sample_before = client.sample_generation_readiness()
            formal = client.formal_generation_readiness()
            sample_after = client.sample_generation_readiness()

        self.assertTrue(sample_before["ready"])
        self.assertTrue(formal["ready"])
        self.assertTrue(sample_after["ready"])
        self.assertEqual(
            calls,
            [
                "https://runtime.mira.test/api/health",
                "https://runtime.mira.test/api/health?scope=formal-generation",
                "https://runtime.mira.test/api/health",
            ],
        )

    def test_inactive_candidate_never_creates_a_student_launch(self):
        class Auth:
            @staticmethod
            def authenticate(_token):
                return {
                    "principal": {
                        "id": "student-1",
                        "family_id": "family-1",
                        "child_id": "child-1",
                    }
                }

        class Repository:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_owned_session_runtime(_conn, **_kwargs):
                return {
                    "child_grade_code": "primary_1",
                    "course_grade_code": "primary_1",
                    "course_subject": "math",
                    "course_node_code": "number_sense_20",
                    "runtime_classroom_id": "candidate-runtime-1",
                    "runtime_status": "ready",
                    "runtime_quality_status": "approved",
                    "upstream_classroom_id": "classroom-1",
                    "candidate_release_id": "inactive-release-1",
                    "feature_manifest_json": {},
                }

        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.student_auth_service = Auth()
        service.repository = Repository()

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-access", "session-1")

        self.assertEqual(raised.exception.code, "openmaic_candidate_not_activated")
        self.assertEqual(raised.exception.status_code, 404)

    def test_full_runtime_client_binds_post_and_query_to_runtime_request_id(self):
        requests = []

        class Response:
            headers = {"Content-Type": "application/json"}

            def __init__(self, request, payload):
                self.request = request
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.request.full_url

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            if request.get_method() == "POST":
                input_sha256 = OpenMaicFullRuntimeClient.formal_input_sha256(
                    json.loads(request.data.decode("utf-8"))
                )
                return Response(
                    request,
                    {
                        "success": True,
                        "jobId": "formal-job-client-1",
                        "status": "queued",
                        "step": "queued",
                        "progress": 0,
                        "done": False,
                        "runtimeRequestId": "formal-runtime-client-1",
                        "formalContractVersion": (
                            OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
                        ),
                        "formalInputSha256": input_sha256,
                    },
                )
            input_sha256 = OpenMaicFullRuntimeClient.formal_input_sha256(
                json.loads(requests[0][0].data.decode("utf-8"))
            )
            return Response(
                request,
                {
                    "success": True,
                    "jobId": "formal-job-client-1",
                    "status": "running",
                    "step": "generating_scenes",
                    "progress": 20,
                    "done": False,
                    "runtimeRequestId": "formal-runtime-client-1",
                    "formalContractVersion": (
                        OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
                    ),
                    "formalInputSha256": input_sha256,
                },
            )

        client = OpenMaicFullRuntimeClient(
            "https://runtime.mira.test",
            formal_audio_internal_token="t" * 32,
        )
        contract = deepcopy(
            OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT
        )
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            side_effect=fake_urlopen,
        ):
            created = client.start_generation(
                requirement="formal requirement",
                enable_web_search=True,
                enable_image_generation=False,
                enable_video_generation=False,
                enable_tts=False,
                agent_mode="generate",
                runtime_request_id="formal-runtime-client-1",
                formal_runtime_contract=contract,
            )
            queried = client.get_generation_job_by_request_id(
                "formal-runtime-client-1"
            )

        self.assertEqual(created.job_id, "formal-job-client-1")
        self.assertEqual(queried.job_id, "formal-job-client-1")
        body = json.loads(requests[0][0].data.decode("utf-8"))
        self.assertEqual(body["runtimeRequestId"], "formal-runtime-client-1")
        self.assertEqual(body["formalRuntimeContract"], contract)
        self.assertIn(
            "runtimeRequestId=formal-runtime-client-1",
            requests[1][0].full_url,
        )

    def test_formal_candidate_request_is_adaptive_and_idempotent(self):
        service = _candidate_service()
        method = getattr(service, "issue_candidate_generation", None)
        self.assertTrue(callable(method))

        kwargs = {
            "build_item_id": "candidate-item-1",
            "course_id": "candidate-course-1",
            "course_version": "course-version-1",
            "package_id": "candidate-package-1",
            "package_version": 1,
            "target_fingerprint": FINGERPRINT,
            "runtime_request_id": "formal-runtime-request-1",
        }
        first = method(**kwargs)
        replay = method(**kwargs)

        self.assertEqual(first["runtime"]["attemptOrdinal"], 1)
        self.assertEqual(replay["runtime"]["id"], first["runtime"]["id"])
        self.assertEqual(len(service.client.start_calls), 1)
        self.assertEqual(
            service.client.start_calls[0]["runtime_request_id"],
            "formal-runtime-request-1",
        )
        self.assertEqual(
            service.client.start_calls[0]["formal_runtime_contract"]
            ["scenePlanning"]["mode"],
            "adaptive",
        )
        self.assertEqual(
            service.client.start_calls[0]["formal_runtime_contract"]
            ["speechActions"]["perScene"],
            {"min": 1, "max": 20},
        )
        self.assertFalse(service.client.start_calls[0]["enable_tts"])
        self.assertNotIn("sampleMode", service.client.start_calls[0])

    def test_formal_candidate_request_contains_locked_teaching_brief_and_hashes(self):
        service = _candidate_service()

        service.issue_candidate_generation(
            build_item_id="candidate-item-1",
            course_id="candidate-course-1",
            course_version="course-version-1",
            package_id="candidate-package-1",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-teaching-brief",
        )

        requirement = json.loads(service.client.start_calls[0]["requirement"])
        self.assertEqual(requirement["teachingBrief"], TEACHING_BRIEF)
        self.assertEqual(
            requirement["teachingBriefSha256"], TEACHING_BRIEF_SHA256
        )
        self.assertEqual(
            requirement["sourceCourseContentSha256"],
            SOURCE_COURSE_CONTENT_SHA256,
        )
        self.assertEqual(
            requirement["teacher"],
            {
                "teacherProfile": {
                    "id": "mira_math_clear",
                    "version": 2,
                    "contentHash": "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
                    "displayName": "小数老师",
                    "avatarPath": "/teachers/ashu-math-v1.png",
                },
                "runtime": {
                    "name": "小数老师",
                    "role": "teacher",
                    "avatar": "/avatars/teacher.png",
                    "teacherGender": "male",
                    "voiceGender": "male",
                    "voiceConfig": {
                        "providerId": "qwen-tts",
                        "modelId": "qwen3-tts-flash",
                        "voiceId": "Ethan",
                    },
                },
            },
        )
        serialized = json.dumps(requirement, ensure_ascii=False)
        self.assertNotIn("authoritativeAnswer", serialized)
        self.assertNotIn('"providerSecret":', serialized)

    def test_formal_candidate_authority_drift_creates_no_runtime_and_no_post(self):
        service = _candidate_service()
        service.repository.generation_authority_error = (
            "formal candidate course content drifted"
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.issue_candidate_generation(
                build_item_id="candidate-item-drift",
                course_id="candidate-course-drift",
                course_version="course-version-1",
                package_id="candidate-package-drift",
                package_version=1,
                target_fingerprint=FINGERPRINT,
                runtime_request_id="formal-runtime-request-content-drift",
            )

        self.assertEqual(
            raised.exception.code, "openmaic_formal_candidate_conflict"
        )
        self.assertEqual(service.repository.rows, [])
        self.assertEqual(service.client.start_calls, [])

    def test_ready_formal_candidate_reserves_only_classroom_receipt(self):
        service = _candidate_service()
        issued = service.issue_candidate_generation(
            build_item_id="candidate-item-ready",
            course_id="candidate-course-ready",
            course_version="course-version-1",
            package_id="candidate-package-ready",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-ready",
        )
        job = service.client.jobs["formal-runtime-request-ready"]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }

        completed = service.generation_status(job.job_id)

        self.assertEqual(completed["runtime"]["id"], issued["runtime"]["id"])
        self.assertEqual(completed["runtime"]["status"], "ready")
        receipt = service.catalog_repository.receipt
        self.assertEqual(receipt["classroom_status"], "passed")
        self.assertRegex(receipt["classroom_receipt_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["tts_status"], "pending")
        self.assertEqual(receipt["asr_roundtrip_status"], "pending")
        self.assertEqual(receipt["conversation_provider_status"], "pending")
        self.assertEqual(receipt["publication_status"], "pending")
        self.assertEqual(receipt["auto_validated"], 0)

    def test_candidate_manifest_drift_never_downgrades_to_sample_completion(self):
        service = _candidate_service()
        service.issue_candidate_generation(
            build_item_id="candidate-item-manifest-drift",
            course_id="candidate-course-manifest-drift",
            course_version="course-version-1",
            package_id="candidate-package-manifest-drift",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-manifest-drift",
        )
        job = service.client.jobs["formal-runtime-request-manifest-drift"]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"
        service.repository.rows[0]["feature_manifest_json"].pop(
            "formalRuntimeContract", None
        )
        service.repository.rows[0]["feature_manifest_json"].pop(
            "generationContract", None
        )
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(job.job_id)

        self.assertEqual(
            raised.exception.code, "openmaic_formal_generation_ambiguous"
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertIsNone(service.catalog_repository.receipt)
        self.assertNotEqual(service.repository.rows[0]["status"], "ready")

    def test_completion_rechecks_the_polled_upstream_job_inside_the_lock(self):
        service = _candidate_service()
        service.issue_candidate_generation(
            build_item_id="candidate-item-job-binding-drift",
            course_id="candidate-course-job-binding-drift",
            course_version="course-version-1",
            package_id="candidate-package-job-binding-drift",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-job-binding-drift",
        )
        job = service.client.jobs["formal-runtime-request-job-binding-drift"]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"

        def drift_after_poll(_classroom_id):
            service.repository.rows[0]["upstream_job_id"] = "drifted-upstream-job"
            return _formal_classroom()

        service.client.get_classroom = drift_after_poll
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(job.job_id)

        self.assertEqual(
            raised.exception.code,
            "openmaic_formal_completion_authority_revoked",
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertIsNone(service.catalog_repository.receipt)

    def test_terminal_receipt_replay_rejects_premature_downstream_state(self):
        for field, value in (("approved", 1), ("tts_receipt_hash", "a" * 64)):
            with self.subTest(field=field):
                service = _candidate_service()
                service.issue_candidate_generation(
                    build_item_id=f"candidate-item-receipt-{field}",
                    course_id=f"candidate-course-receipt-{field}",
                    course_version="course-version-1",
                    package_id=f"candidate-package-receipt-{field}",
                    package_version=1,
                    target_fingerprint=FINGERPRINT,
                    runtime_request_id=f"formal-runtime-request-receipt-{field}",
                )
                job = service.client.jobs[
                    f"formal-runtime-request-receipt-{field}"
                ]
                job.status = "succeeded"
                job.done = True
                job.progress = 100
                job.classroom_id = "formal-classroom-1"
                stale_runtime = deepcopy(service.repository.rows[0])
                requested_manifest = deepcopy(stale_runtime["feature_manifest_json"])
                service._validate_and_manifest = lambda *_args, **_kwargs: {
                    "missing": [],
                    "present": list(FORMAL_REQUIRED_FEATURES),
                }
                service._complete_formal_candidate(
                    runtime=stale_runtime,
                    job=job,
                    classroom=_formal_classroom(),
                    requested_manifest=requested_manifest,
                )
                service.catalog_repository.receipt[field] = value

                with self.assertRaises(RuntimeError):
                    service._complete_formal_candidate(
                        runtime=stale_runtime,
                        job=job,
                        classroom=_formal_classroom(),
                        requested_manifest=requested_manifest,
                    )

    def test_concurrent_formal_completion_replays_one_terminal_receipt(self):
        service = _candidate_service()
        service.issue_candidate_generation(
            build_item_id="candidate-item-concurrent-completion",
            course_id="candidate-course-concurrent-completion",
            course_version="course-version-1",
            package_id="candidate-package-concurrent-completion",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-concurrent-completion",
        )
        job = service.client.jobs[
            "formal-runtime-request-concurrent-completion"
        ]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"
        stale_runtime = deepcopy(service.repository.rows[0])
        requested_manifest = deepcopy(stale_runtime["feature_manifest_json"])
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }

        with patch(
            "services.openmaic_full_runtime_service.now_ms", return_value=10_000
        ):
            first = service._complete_formal_candidate(
                runtime=stale_runtime,
                job=job,
                classroom=_formal_classroom(),
                requested_manifest=requested_manifest,
            )
        first_completed_at = service.catalog_repository.receipt[
            "classroom_completed_at"
        ]
        with patch(
            "services.openmaic_full_runtime_service.now_ms", return_value=20_000
        ):
            replay = service._complete_formal_candidate(
                runtime=stale_runtime,
                job=job,
                classroom=_formal_classroom(),
                requested_manifest=requested_manifest,
            )

        self.assertEqual(first["id"], replay["id"])
        self.assertEqual(replay["status"], "ready")
        self.assertEqual(
            service.catalog_repository.receipt["classroom_completed_at"],
            first_completed_at,
        )
        self.assertEqual(first_completed_at, 10_000)

    def test_classroom_receipt_hash_binds_the_canonical_classroom_content(self):
        def complete(classroom):
            service = _candidate_service()
            issued = service.issue_candidate_generation(
                build_item_id="candidate-item-content-hash",
                course_id="candidate-course-content-hash",
                course_version="course-version-1",
                package_id="candidate-package-content-hash",
                package_version=1,
                target_fingerprint=FINGERPRINT,
                runtime_request_id="formal-runtime-request-content-hash",
            )
            job = service.client.jobs["formal-runtime-request-content-hash"]
            job.status = "succeeded"
            job.done = True
            job.progress = 100
            job.classroom_id = "formal-classroom-1"
            service.client.get_classroom = lambda _classroom_id: deepcopy(classroom)
            service._validate_and_manifest = lambda *_args, **_kwargs: {
                "missing": [],
                "present": list(FORMAL_REQUIRED_FEATURES),
            }
            service.generation_status(job.job_id)
            runtime = next(
                row for row in service.repository.rows if row["id"] == issued["runtime"]["id"]
            )
            return (
                service.catalog_repository.receipt["classroom_receipt_hash"],
                runtime["feature_manifest_json"],
            )

        original = _formal_classroom()
        changed = deepcopy(original)
        changed["scenes"][0]["title"] += "（内容已变化）"

        original_receipt, original_manifest = complete(original)
        changed_receipt, changed_manifest = complete(changed)

        self.assertNotEqual(original_receipt, changed_receipt)
        self.assertNotEqual(
            original_manifest["classroomContentSha256"],
            changed_manifest["classroomContentSha256"],
        )

    def test_formal_completion_rejects_a_classroom_with_the_wrong_stage_identity(self):
        service = _candidate_service()
        issued = service.issue_candidate_generation(
            build_item_id="candidate-item-stage-mismatch",
            course_id="candidate-course-stage-mismatch",
            course_version="course-version-1",
            package_id="candidate-package-stage-mismatch",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-stage-mismatch",
        )
        job = service.client.jobs["formal-runtime-request-stage-mismatch"]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"
        classroom = _formal_classroom()
        classroom["stage"]["id"] = "different-classroom"
        for scene in classroom["scenes"]:
            scene["stageId"] = "different-classroom"
        service.client.get_classroom = lambda _classroom_id: classroom

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(job.job_id)

        self.assertEqual(
            raised.exception.code, "openmaic_formal_classroom_identity_mismatch"
        )
        self.assertIsNone(service.catalog_repository.receipt)
        self.assertNotEqual(service.repository.rows[0]["status"], "ready")

    def test_post_dispatch_authority_drift_is_quarantined_without_passed_receipt(self):
        service = _candidate_service()
        issued = service.issue_candidate_generation(
            build_item_id="candidate-item-post-dispatch-drift",
            course_id="candidate-course-post-dispatch-drift",
            course_version="course-version-1",
            package_id="candidate-package-post-dispatch-drift",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-post-dispatch-drift",
        )
        job = service.client.jobs[
            "formal-runtime-request-post-dispatch-drift"
        ]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }
        service.repository.completion_authority_error = (
            "candidate completion authority is no longer current"
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(job.job_id)

        self.assertEqual(
            raised.exception.code,
            "openmaic_formal_completion_authority_revoked",
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertEqual(len(service.client.start_calls), 1)
        self.assertIsNone(service.catalog_repository.receipt)
        self.assertEqual(issued["runtime"]["attemptOrdinal"], 1)

    def test_lost_response_is_reconciled_by_request_id_without_second_post(self):
        service = _candidate_service(_CandidateClient(lose_response=True))
        result = service.issue_candidate_generation(
            build_item_id="candidate-item-lost",
            course_id="candidate-course-lost",
            course_version="course-version-1",
            package_id="candidate-package-lost",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-lost",
        )
        self.assertEqual(result["runtime"]["status"], "generating")
        self.assertEqual(len(service.client.start_calls), 1)
        self.assertEqual(
            service.client.query_calls,
            ["formal-runtime-request-lost", "formal-runtime-request-lost"],
        )

    def test_unknown_query_is_quarantined_and_never_posts_or_retries(self):
        service = _candidate_service(_CandidateClient(query_ambiguous=True))
        kwargs = {
            "build_item_id": "candidate-item-ambiguous",
            "course_id": "candidate-course-ambiguous",
            "course_version": "course-version-1",
            "package_id": "candidate-package-ambiguous",
            "package_version": 1,
            "target_fingerprint": FINGERPRINT,
            "runtime_request_id": "formal-runtime-request-ambiguous",
        }
        with self.assertRaises(OpenMaicRuntimeServiceError) as first:
            service.issue_candidate_generation(**kwargs)
        self.assertEqual(first.exception.code, "openmaic_formal_dispatch_ambiguous")
        self.assertEqual(service.client.start_calls, [])
        self.assertEqual(len(service.repository.quarantined), 1)

        with self.assertRaises(OpenMaicRuntimeServiceError) as replay:
            service.issue_candidate_generation(**kwargs)
        self.assertEqual(replay.exception.code, "openmaic_formal_dispatch_ambiguous")
        self.assertEqual(service.client.start_calls, [])

    def test_preexisting_request_with_a_different_input_digest_is_quarantined(self):
        client = _CandidateClient()
        request_id = "formal-runtime-request-digest-conflict"
        client.jobs[request_id] = SimpleNamespace(
            job_id="formal-job-digest-conflict",
            status="queued",
            step="queued",
            progress=0,
            done=False,
            classroom_id=None,
            scenes_count=None,
            error=None,
            runtime_request_id=request_id,
            formal_contract_version="mira.openmaic.formal-runtime.v1",
            formal_input_sha256="0" * 64,
            dispatch_ambiguous=False,
        )
        service = _candidate_service(client)

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.issue_candidate_generation(
                build_item_id="candidate-item-digest-conflict",
                course_id="candidate-course-digest-conflict",
                course_version="course-version-1",
                package_id="candidate-package-digest-conflict",
                package_version=1,
                target_fingerprint=FINGERPRINT,
                runtime_request_id=request_id,
            )

        self.assertEqual(
            raised.exception.code,
            "openmaic_formal_dispatch_ambiguous",
        )
        self.assertEqual(client.start_calls, [])
        self.assertIsNone(service.repository.rows[0]["upstream_job_id"])
        self.assertEqual(
            service.repository.rows[0]["quality_status"], "quarantined"
        )
        self.assertEqual(len(service.repository.quarantined), 1)

    def test_unknown_poll_is_quarantined_and_cannot_open_attempt_two(self):
        service = _candidate_service()
        kwargs = {
            "build_item_id": "candidate-item-poll-ambiguous",
            "course_id": "candidate-course-poll-ambiguous",
            "course_version": "course-version-1",
            "package_id": "candidate-package-poll-ambiguous",
            "package_version": 1,
            "target_fingerprint": FINGERPRINT,
            "runtime_request_id": "formal-runtime-request-poll-ambiguous",
        }
        issued = service.issue_candidate_generation(**kwargs)

        def unknown(_upstream_job_id):
            raise OpenMaicFullRuntimeError(
                "openmaic_transport_error", "poll response unknown", status_code=503
            )

        service.client.get_generation_job = unknown
        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(issued["job"]["id"])
        self.assertEqual(
            raised.exception.code, "openmaic_formal_generation_ambiguous"
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertEqual(len(service.client.start_calls), 1)

        with self.assertRaises(OpenMaicRuntimeServiceError) as retry:
            service.issue_candidate_generation(
                **{
                    **kwargs,
                    "runtime_request_id": (
                        "formal-runtime-request-poll-ambiguous-attempt-2"
                    ),
                }
            )
        self.assertEqual(retry.exception.code, "openmaic_formal_dispatch_ambiguous")
        self.assertEqual(len(service.client.start_calls), 1)
        self.assertEqual(len(service.repository.quarantined), 1)

    def test_nonstale_poll_wrong_job_id_is_quarantined_without_receipt(self):
        service = _candidate_service()
        service.issue_candidate_generation(
            build_item_id="candidate-item-wrong-job",
            course_id="candidate-course-wrong-job",
            course_version="course-version-1",
            package_id="candidate-package-wrong-job",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-wrong-job",
        )
        actual = service.client.jobs["formal-runtime-request-wrong-job"]
        wrong = deepcopy(actual)
        wrong.job_id = "different-formal-job"
        wrong.status = "succeeded"
        wrong.done = True
        wrong.progress = 100
        wrong.classroom_id = "formal-classroom-1"
        service.client.get_generation_job = lambda _job_id: wrong
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(actual.job_id)

        self.assertEqual(
            raised.exception.code, "openmaic_formal_generation_ambiguous"
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertIsNone(service.catalog_repository.receipt)
        self.assertEqual(len(service.client.start_calls), 1)

    def test_stale_local_clock_queries_request_and_never_opens_attempt_two(self):
        service = _candidate_service()
        kwargs = {
            "build_item_id": "candidate-item-stale-running",
            "course_id": "candidate-course-stale-running",
            "course_version": "course-version-1",
            "package_id": "candidate-package-stale-running",
            "package_version": 1,
            "target_fingerprint": FINGERPRINT,
            "runtime_request_id": "formal-runtime-request-stale-running",
        }
        issued = service.issue_candidate_generation(**kwargs)
        service.repository.rows[0]["updated_at"] = 1

        with patch(
            "services.openmaic_full_runtime_service.now_ms",
            return_value=31 * 60 * 1000,
        ):
            polled = service.generation_status(issued["job"]["id"])

        self.assertEqual(polled["runtime"]["status"], "generating")
        self.assertEqual(
            service.client.query_calls[-1],
            "formal-runtime-request-stale-running",
        )
        self.assertEqual(len(service.client.start_calls), 1)
        with self.assertRaises(OpenMaicRuntimeServiceError) as attempt_two:
            service.issue_candidate_generation(
                **{
                    **kwargs,
                    "runtime_request_id": (
                        "formal-runtime-request-stale-running-attempt-2"
                    ),
                }
            )
        self.assertEqual(
            attempt_two.exception.code, "openmaic_formal_candidate_conflict"
        )
        self.assertEqual(len(service.client.start_calls), 1)

    def test_stale_authoritative_query_unknown_quarantines_without_retry(self):
        service = _candidate_service()
        kwargs = {
            "build_item_id": "candidate-item-stale-unknown",
            "course_id": "candidate-course-stale-unknown",
            "course_version": "course-version-1",
            "package_id": "candidate-package-stale-unknown",
            "package_version": 1,
            "target_fingerprint": FINGERPRINT,
            "runtime_request_id": "formal-runtime-request-stale-unknown",
        }
        issued = service.issue_candidate_generation(**kwargs)
        service.repository.rows[0]["updated_at"] = 1
        service.client.query_ambiguous = True

        with patch(
            "services.openmaic_full_runtime_service.now_ms",
            return_value=31 * 60 * 1000,
        ), self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(issued["job"]["id"])

        self.assertEqual(
            raised.exception.code, "openmaic_formal_generation_ambiguous"
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertEqual(len(service.client.start_calls), 1)

    def test_stale_upstream_dispatch_ambiguity_never_becomes_retryable_failed(self):
        service = _candidate_service()
        kwargs = {
            "build_item_id": "candidate-item-stale-dispatch",
            "course_id": "candidate-course-stale-dispatch",
            "course_version": "course-version-1",
            "package_id": "candidate-package-stale-dispatch",
            "package_version": 1,
            "target_fingerprint": FINGERPRINT,
            "runtime_request_id": "formal-runtime-request-stale-dispatch",
        }
        issued = service.issue_candidate_generation(**kwargs)
        service.repository.rows[0]["updated_at"] = 1
        service.client.jobs[kwargs["runtime_request_id"]].dispatch_ambiguous = True

        with patch(
            "services.openmaic_full_runtime_service.now_ms",
            return_value=31 * 60 * 1000,
        ), self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.generation_status(issued["job"]["id"])

        self.assertEqual(
            raised.exception.code, "openmaic_formal_generation_ambiguous"
        )
        self.assertEqual(service.repository.rows[0]["quality_status"], "quarantined")
        self.assertEqual(len(service.client.start_calls), 1)
        with self.assertRaises(OpenMaicRuntimeServiceError) as attempt_two:
            service.issue_candidate_generation(
                **{
                    **kwargs,
                    "runtime_request_id": (
                        "formal-runtime-request-stale-unknown-attempt-2"
                    ),
                }
            )
        self.assertEqual(
            attempt_two.exception.code, "openmaic_formal_dispatch_ambiguous"
        )
        self.assertEqual(len(service.client.start_calls), 1)

    def test_formal_runtime_quizzes_are_exactly_the_locked_scored_questions(self):
        service = _candidate_service()
        assessment = service._formal_runtime_assessment_contract(
            {"teachingBrief": deepcopy(TEACHING_BRIEF)}
        )
        teacher_contract = service._formal_teacher_contract("math")
        classroom = _formal_classroom()
        evidence = service._validate_formal_classroom(
            classroom,
            teacher_contract=teacher_contract,
            assessment_questions=assessment,
        )
        self.assertEqual(evidence["assessmentQuestionIds"], ["q2", "q3", "q4", "q5"])

        for mutate in (
            lambda value: value["scenes"][5]["content"]["questions"][0].update(id="q1"),
            lambda value: value["scenes"][5]["content"]["questions"][0].update(
                question="看起来相似但不是锁定题目"
            ),
            lambda value: value["scenes"][5]["content"]["questions"][0].update(
                options=[{"value": "forged", "label": "伪造选项"}]
            ),
            lambda value: value["scenes"][6]["content"]["questions"].pop(),
        ):
            invalid = deepcopy(classroom)
            mutate(invalid)
            with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
                service._validate_formal_classroom(
                    invalid,
                    teacher_contract=teacher_contract,
                    assessment_questions=assessment,
                )
            self.assertEqual(
                raised.exception.code,
                "openmaic_formal_assessment_mismatch",
            )

        choice_brief = deepcopy(TEACHING_BRIEF)
        choice_question = choice_brief["lesson"]["questions"][1]
        choice_question.update(
            type="single_choice",
            choices=[
                {"id": "eleven", "label": "11"},
                {"id": "twelve", "label": "12"},
            ],
        )
        choice_assessment = service._formal_runtime_assessment_contract(
            {"teachingBrief": choice_brief}
        )
        choice_classroom = deepcopy(classroom)
        choice_classroom["scenes"][5]["content"]["questions"][0] = {
            "id": "q2",
            "type": "single",
            "question": SOURCE_QUESTIONS[1]["prompt"],
            "options": [
                {"value": "eleven", "label": "11"},
                {"value": "twelve", "label": "12"},
            ],
            "hasAnswer": False,
            "answer": None,
            "points": 1,
        }
        service._validate_formal_classroom(
            choice_classroom,
            teacher_contract=teacher_contract,
            assessment_questions=choice_assessment,
        )
        choice_classroom["scenes"][5]["content"]["questions"][0]["options"][0][
            "label"
        ] = "漂移标签"
        with self.assertRaises(OpenMaicRuntimeServiceError) as choice_drift:
            service._validate_formal_classroom(
                choice_classroom,
                teacher_contract=teacher_contract,
                assessment_questions=choice_assessment,
            )
        self.assertEqual(
            choice_drift.exception.code,
            "openmaic_formal_assessment_mismatch",
        )

    def test_formal_structure_accepts_adaptive_scene_count_and_widget_set(self):
        service = _candidate_service()
        validator = service._validate_formal_classroom
        adaptive = _formal_classroom()
        adaptive["scenes"] = [
            scene
            for scene in adaptive["scenes"]
            if scene["type"] != "interactive" or scene["order"] == 7
        ]
        for order, scene in enumerate(adaptive["scenes"]):
            scene["order"] = order

        evidence = validator(
            adaptive,
            teacher_contract=service._formal_teacher_contract("math"),
        )

        self.assertEqual(
            evidence["sceneDistribution"],
            {"slide": 5, "quiz": 2, "interactive": 1, "pbl": 0},
        )
        self.assertEqual(evidence["speechSceneCount"], 8)
        self.assertEqual(evidence["speechActionCount"], 8)
        self.assertEqual(evidence["widgetTypes"], ["simulation"])

    def test_formal_slide_allows_multi_speech_and_consecutive_focus_actions(self):
        service = _candidate_service()
        classroom = _formal_classroom()
        first = classroom["scenes"][0]
        focused_speech = next(
            action for action in first["actions"] if action["type"] == "speech"
        )
        discussion = next(
            action for action in first["actions"] if action["type"] == "discussion"
        )
        target = first["actions"][0]["elementId"]
        first["actions"] = [
            {"id": "intro-speech", "type": "speech", "text": "先看看今天的目标。"},
            first["actions"][0],
            {
                "id": "second-focus",
                "type": "spotlight",
                "elementId": target,
            },
            focused_speech,
            {"id": "wrap-speech", "type": "speech", "text": "我们继续往下学。"},
            discussion,
        ]

        evidence = service._validate_formal_classroom(
            classroom,
            teacher_contract=service._formal_teacher_contract("math"),
        )

        self.assertEqual(evidence["speechSceneCount"], 10)
        self.assertEqual(evidence["speechActionCount"], 12)

    def test_formal_completion_rejects_speech_action_count_mismatch(self):
        service = _candidate_service()
        issued = service.issue_candidate_generation(
            build_item_id="candidate-item-speech-count",
            course_id="candidate-course-speech-count",
            course_version="course-version-1",
            package_id="candidate-package-speech-count",
            package_version=1,
            target_fingerprint=FINGERPRINT,
            runtime_request_id="formal-runtime-request-speech-count",
        )
        job = service.client.jobs["formal-runtime-request-speech-count"]
        job.status = "succeeded"
        job.done = True
        job.progress = 100
        job.classroom_id = "formal-classroom-1"
        job.speech_action_count = 11
        service._validate_and_manifest = lambda *_args, **_kwargs: {
            "missing": [],
            "present": list(FORMAL_REQUIRED_FEATURES),
        }

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service._complete_formal_candidate(
                runtime=issued["runtime"],
                job=job,
                classroom=_formal_classroom(),
                requested_manifest=service.repository.rows[0][
                    "feature_manifest_json"
                ],
            )

        self.assertEqual(
            raised.exception.code,
            "openmaic_formal_speech_count_mismatch",
        )

    def test_formal_structure_requires_one_focus_explanation_sequence_per_slide(self):
        service = _candidate_service()
        validator = service._validate_formal_classroom
        teacher_contract = service._formal_teacher_contract("math")
        valid = _formal_classroom()
        validator(valid, teacher_contract=teacher_contract)

        missing = deepcopy(valid)
        missing["scenes"][0]["actions"] = [
            action
            for action in missing["scenes"][0]["actions"]
            if action["type"] != "spotlight"
        ]
        with self.assertRaises(OpenMaicRuntimeServiceError) as absent:
            validator(missing, teacher_contract=teacher_contract)
        self.assertEqual(
            absent.exception.code,
            "openmaic_formal_slide_focus_sequence_invalid",
        )

        detached = deepcopy(valid)
        actions = detached["scenes"][0]["actions"]
        spotlight = next(
            action for action in actions if action["type"] == "spotlight"
        )
        speech = next(action for action in actions if action["type"] == "speech")
        remainder = [
            action
            for action in actions
            if action["type"] not in {"spotlight", "speech"}
        ]
        detached["scenes"][0]["actions"] = [speech, spotlight, *remainder]
        with self.assertRaises(OpenMaicRuntimeServiceError) as out_of_order:
            validator(detached, teacher_contract=teacher_contract)
        self.assertEqual(
            out_of_order.exception.code,
            "openmaic_formal_slide_focus_sequence_invalid",
        )

    def test_formal_structure_is_adaptive_and_rejects_invalid_evidence(self):
        service = _candidate_service()
        validator = getattr(service, "_validate_formal_classroom", None)
        self.assertTrue(callable(validator))
        valid = _formal_classroom()
        teacher_contract = service._formal_teacher_contract("math")
        evidence = validator(valid, teacher_contract=teacher_contract)
        self.assertEqual(
            evidence["sceneDistribution"],
            {"slide": 5, "quiz": 2, "interactive": 3, "pbl": 0},
        )
        self.assertEqual(evidence["peerCount"], 4)
        self.assertEqual(evidence["speechSceneCount"], 10)
        self.assertEqual(evidence["speechActionCount"], 10)
        self.assertEqual(evidence["distinctDiscussionPeerCount"], 2)
        self.assertTrue(evidence["spotlightVerified"])
        self.assertTrue(evidence["widgetHighlightVerified"])
        self.assertEqual(
            evidence["teacher"],
            {
                "agentId": "teacher-1",
                "name": "小数老师",
                "avatar": "/avatars/teacher.png",
                "teacherGender": "male",
                "voiceGender": "male",
                "voiceId": "Ethan",
            },
        )

        mismatched_teacher = deepcopy(valid)
        mismatched_teacher["stage"]["generatedAgentConfigs"][0].update(
            avatar="/avatars/teacher-2.png",
            voiceConfig={
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
            },
        )
        with self.assertRaises(OpenMaicRuntimeServiceError):
            validator(
                mismatched_teacher,
                teacher_contract=teacher_contract,
            )

        literal_decoy = deepcopy(valid)
        literal_decoy["scenes"][9]["content"]["html"] = literal_decoy[
            "scenes"
        ][9]["content"]["html"].replace(
            "const canvas = document.getElementById('three-canvas');",
            "const conciseArrowProof = \"const registerUnused = () => "
            "document.getElementById('rotate-button').addEventListener("
            "'click', () => {});\";\n"
            "/* const commentUnused = () => document.getElementById("
            "'rotate-button').addEventListener('click', () => {}); */\n"
            "const canvas = document.getElementById('three-canvas');",
        )
        validator(literal_decoy, teacher_contract=teacher_contract)

        called_block_helper = deepcopy(valid)
        called_block_helper["scenes"][9]["content"]["html"] = (
            called_block_helper["scenes"][9]["content"]["html"].replace(
                """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});""",
                """const registerRotation = () => {
  document.getElementById('rotate-button').addEventListener('click', () => {
    mesh.rotation.y += 0.25;
    renderModel();
  });
};
registerRotation();""",
            )
        )
        validator(called_block_helper, teacher_contract=teacher_contract)

        mutations = {}
        mutations["missing_required_scene_type"] = lambda value: value[
            "scenes"
        ].__setitem__(
            slice(None),
            [scene for scene in value["scenes"] if scene["type"] != "interactive"],
        )
        mutations["missing_roster"] = lambda value: value["stage"][
            "generatedAgentConfigs"
        ].pop()
        mutations["missing_speech"] = lambda value: value["scenes"][0].update(
            actions=[
                action
                for action in value["scenes"][0]["actions"]
                if action["type"] != "speech"
            ]
        )
        mutations["one_peer_discussion"] = lambda value: value["scenes"][1][
            "actions"
        ][-1].update(agentId="student-1")
        mutations["missing_spotlight"] = lambda value: [
            scene.update(
                actions=[
                    action
                    for action in scene["actions"]
                    if action["type"] != "spotlight"
                ]
            )
            for scene in value["scenes"]
        ]
        mutations["one_slide_missing_spotlight"] = lambda value: value[
            "scenes"
        ][0].update(
            actions=[
                action
                for action in value["scenes"][0]["actions"]
                if action["type"] != "spotlight"
            ]
        )

        def detached_slide_spotlight(value):
            actions = value["scenes"][0]["actions"]
            spotlight = next(
                action for action in actions if action["type"] == "spotlight"
            )
            speech = next(
                action for action in actions if action["type"] == "speech"
            )
            remainder = [
                action
                for action in actions
                if action["type"] not in {"spotlight", "speech"}
            ]
            value["scenes"][0]["actions"] = [speech, spotlight, *remainder]

        mutations["detached_slide_spotlight"] = detached_slide_spotlight
        mutations["missing_highlight"] = lambda value: [
            scene.update(
                actions=[
                    action
                    for action in scene["actions"]
                    if action["type"] != "widget_highlight"
                ]
            )
            for scene in value["scenes"]
        ]
        mutations["noop_script"] = lambda value: value["scenes"][7][
            "content"
        ].update(html="<html><button>点我</button><script></script></html>")
        mutations["fake_3d"] = lambda value: value["scenes"][9]["content"].update(
            html="<html><canvas></canvas><script>const scene = {};</script></html>"
        )
        mutations["nonexistent_highlight_target"] = lambda value: next(
            action
            for action in value["scenes"][7]["actions"]
            if action["type"] == "widget_highlight"
        ).update(target="does-not-exist")

        def dead_branch_fake_3d(value):
            content = value["scenes"][9]["content"]
            config_json = json.dumps(
                content["widgetConfig"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content["html"] = f"""
                <html><body>
                <button id="rotate-button">旋转</button>
                <div id="status">等待</div>
                <canvas id="three-canvas"></canvas>
                <script>
                document.getElementById('rotate-button').addEventListener('click', () => {{
                  document.getElementById('status').textContent = 'clicked';
                }});
                if (false) {{
                  const canvas = document.getElementById('three-canvas');
                  const gl = canvas.getContext('webgl');
                  const shader = gl.createShader(gl.VERTEX_SHADER);
                  const program = gl.createProgram();
                  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(), gl.STATIC_DRAW);
                  gl.drawArrays(gl.TRIANGLES, 0, 3);
                  object.rotation.x += 1;
                }}
                </script>
                <script type="application/json" id="widget-config">{config_json}</script>
                </body></html>
            """

        mutations["dead_branch_fake_3d"] = dead_branch_fake_3d

        def unused_function_fake_3d(value):
            content = value["scenes"][9]["content"]
            config_json = json.dumps(
                content["widgetConfig"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content["html"] = f"""
                <html><body>
                <button id="rotate-button">旋转</button>
                <div id="status">等待</div>
                <canvas id="three-canvas"></canvas>
                <script>
                function neverCalledRenderPath() {{
                  const canvas = document.getElementById('three-canvas');
                  const gl = canvas.getContext('webgl');
                  gl.createShader(gl.VERTEX_SHADER);
                  gl.createProgram();
                  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(), gl.STATIC_DRAW);
                  gl.drawArrays(gl.TRIANGLES, 0, 3);
                }}
                document.getElementById('rotate-button').addEventListener('click', () => {{
                  object.rotation.x += 1;
                  document.getElementById('status').textContent = 'clicked';
                }});
                </script>
                <script type="application/json" id="widget-config">{config_json}</script>
                </body></html>
            """

        mutations["unused_function_fake_3d"] = unused_function_fake_3d

        def disconnected_highlight_handler(value):
            content = _complete_sample_widget_content("simulation")
            content["html"] = content["html"].replace(
                "</body>",
                """
                <script>
                function neverCalledHighlight(event) {
                  document.getElementById(event.data.target)?.classList.add('highlighted');
                }
                window.addEventListener('message', (event) => {
                  if (event.data?.type === 'HIGHLIGHT_ELEMENT') {
                    const ignored = event.data.target;
                  }
                });
                </script></body>
                """,
            )
            value["scenes"][7]["content"] = content

        mutations["disconnected_highlight_handler"] = disconnected_highlight_handler

        mutations["unknown_roster_role"] = lambda value: value["stage"][
            "generatedAgentConfigs"
        ][-1].update(role="admin")
        mutations["empty_slide"] = lambda value: value["scenes"][2]["content"][
            "canvas"
        ].update(elements=[])
        mutations["hidden_spotlight_target"] = lambda value: value["scenes"][0][
            "content"
        ]["canvas"]["elements"][0].update(visible=False)
        mutations["empty_quiz"] = lambda value: value["scenes"][5][
            "content"
        ].update(questions=[])

        def missing_quiz_answer(value):
            value["scenes"][5]["content"]["questions"][0].update(
                hasAnswer=True,
                answer="42",
            )

        mutations["missing_quiz_answer"] = missing_quiz_answer

        def nested_dead_highlight_handler(value):
            content = _complete_sample_widget_content("simulation")
            content["html"] = content["html"].replace(
                "</body>",
                """
                <script>
                window.addEventListener('message', (event) => {
                  function deadHighlight() {
                    document.getElementById(event.data.target)?.classList.add('highlighted');
                  }
                  if (event.data?.type === 'HIGHLIGHT_ELEMENT') {
                    const ignored = event.data.target;
                  }
                });
                </script></body>
                """,
            )
            value["scenes"][7]["content"] = content

        mutations["nested_dead_highlight_handler"] = nested_dead_highlight_handler

        def disconnected_simulation(value):
            content = value["scenes"][7]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body>
              <input id="count-slider" data-var="count" type="range">
              <output id="count-output">10</output>
              <button id="decoy">点我</button>
              <script>
              document.getElementById('count-slider').addEventListener('input', () => {{
                const ignored = 1;
              }});
              document.getElementById('decoy').addEventListener('click', () => {{
                document.getElementById('count-output').textContent = 'changed';
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["disconnected_simulation"] = disconnected_simulation

        def dead_branch_simulation_registration(value):
            content = value["scenes"][7]["content"]
            content["html"] = content["html"].replace(
                "slider.addEventListener('input', updateSimulation);",
                "function registerDeadSimulation() {\n"
                "  slider.addEventListener('input', updateSimulation);\n"
                "}\n"
                "if (false) { registerDeadSimulation(); }",
            )

        mutations["dead_branch_simulation_registration"] = (
            dead_branch_simulation_registration
        )

        def disconnected_game(value):
            content = value["scenes"][8]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body><button id="start_button">开始</button>
              <strong id="score-status">0</strong><canvas id="game-canvas"></canvas>
              <script>
              function deadGame() {{ score++; requestAnimationFrame(renderGame); }}
              function renderGame() {{ gameContext.fillText('x', 1, 1); }}
              document.getElementById('start_button').addEventListener('click', () => {{
                document.getElementById('score-status').textContent = 'clicked';
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["disconnected_game"] = disconnected_game

        def dead_branch_game_registration(value):
            content = value["scenes"][8]["content"]
            listener = """document.getElementById('start_button').addEventListener('click', () => {
  score += 10;
  level++;
  scoreStatus.textContent = String(score);
  requestAnimationFrame(renderGame);
});"""
            content["html"] = content["html"].replace(
                listener,
                "function registerDeadGame() {\n"
                + listener
                + "\n}\nif (false) { registerDeadGame(); }",
            )

        mutations["dead_branch_game_registration"] = dead_branch_game_registration

        def unbound_3d_renderer(value):
            content = value["scenes"][9]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body><button id="rotate-button">旋转</button>
              <canvas id="three-canvas"></canvas>
              <script>
              const renderer = new THREE.WebGLRenderer({{canvas: document.getElementById('three-canvas')}});
              const scene = new THREE.Scene();
              const camera = new THREE.PerspectiveCamera();
              const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
              scene.add(mesh);
              document.getElementById('rotate-button').addEventListener('click', () => {{
                dummy.rotation.x += 1;
                renderer.render(scene, camera);
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["unbound_3d_renderer"] = unbound_3d_renderer

        def string_token_fake_3d(value):
            content = value["scenes"][9]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body><button id="rotate-button">旋转</button>
              <div id="status">等待</div><canvas id="three-canvas"></canvas>
              <script>
              const setupProof = "new THREE.WebGLRenderer(); new THREE.Scene();";
              document.getElementById('rotate-button').addEventListener('click', () => {{
                document.getElementById('status').textContent =
                  "renderer.render(scene,camera); mesh.rotation.x += 1";
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["string_token_fake_3d"] = string_token_fake_3d

        def highlight_mutates_decoy(value):
            content = _complete_sample_widget_content("simulation")
            content["html"] = content["html"].replace(
                "</body>",
                """
                <div id="decoy">无关元素</div>
                <script>
                window.addEventListener('message', (event) => {
                  if (event.data?.type === 'HIGHLIGHT_ELEMENT') {
                    const requested = document.getElementById(event.data.target);
                    document.getElementById('decoy').classList.add('highlighted');
                  }
                });
                </script></body>
                """,
            )
            value["scenes"][7]["content"] = content

        mutations["highlight_mutates_decoy"] = highlight_mutates_decoy

        def hidden_widget_highlight_target(value):
            content = value["scenes"][7]["content"]
            content["html"] = content["html"].replace(
                '<input id="count-slider"', '<input hidden id="count-slider"'
            )

        mutations["hidden_widget_highlight_target"] = hidden_widget_highlight_target

        def ancestor_hidden_widget_target(value):
            content = value["scenes"][7]["content"]
            content["html"] = content["html"].replace(
                '<input id="count-slider"',
                '<div hidden><input id="count-slider"',
            ).replace(
                '<output id="count-output"',
                '</div><output id="count-output"',
            )

        mutations["ancestor_hidden_widget_target"] = ancestor_hidden_widget_target

        def simulation_decoy_input(value):
            content = value["scenes"][7]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body>
              <input id="count-slider" data-var="count" type="range">
              <input id="decoy-slider" type="range">
              <output id="count-output">10</output>
              <script>
              document.getElementById('count-slider').addEventListener('input', () => {{
                const ignored = 1;
              }});
              document.getElementById('decoy-slider').addEventListener('input', (event) => {{
                document.getElementById('count-output').textContent = event.target.value;
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["simulation_decoy_input"] = simulation_decoy_input

        def game_decoy_control(value):
            content = value["scenes"][8]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body><button id="start_button">开始</button>
              <button id="decoy">无关按钮</button>
              <strong id="score-status">0</strong><canvas id="game-canvas"></canvas>
              <script>
              let score = 0;
              document.getElementById('start_button').addEventListener('click', () => {{
                const ignored = 1;
              }});
              document.getElementById('decoy').addEventListener('click', () => {{
                score += 10;
                document.getElementById('score-status').textContent = String(score);
                requestAnimationFrame(() => gameContext.fillText('x', 1, 1));
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["game_decoy_control"] = game_decoy_control

        def hidden_game_control(value):
            content = value["scenes"][8]["content"]
            content["html"] = content["html"].replace(
                '<button id="start_button"', '<button hidden id="start_button"'
            )

        mutations["hidden_game_control"] = hidden_game_control

        def off_dom_3d_renderer(value):
            content = value["scenes"][9]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body><button id="rotate-button">旋转</button>
              <script>
              const renderer = new THREE.WebGLRenderer();
              const scene = new THREE.Scene();
              const camera = new THREE.PerspectiveCamera();
              const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
              scene.add(mesh);
              document.getElementById('rotate-button').addEventListener('click', () => {{
                mesh.rotation.x += 1;
                renderer.render(scene, camera);
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["off_dom_3d_renderer"] = off_dom_3d_renderer

        def hidden_3d_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<canvas id="three-canvas"', '<canvas hidden id="three-canvas"'
            )

        mutations["hidden_3d_canvas"] = hidden_3d_canvas

        def string_dom_binding_fake_3d(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const canvas = document.getElementById('three-canvas');",
                "const bindingProof = \"const canvas = "
                "document.getElementById('three-canvas')\";",
            )

        mutations["string_dom_binding_fake_3d"] = string_dom_binding_fake_3d

        def dead_scope_dom_binding(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const canvas = document.getElementById('three-canvas');",
                "function neverCalledCanvasBinding() { "
                "const canvas = document.getElementById('three-canvas'); }",
            )

        mutations["dead_scope_dom_binding"] = dead_scope_dom_binding

        def dead_listener_registration(value):
            content = value["scenes"][9]["content"]
            listener = """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});"""
            content["html"] = content["html"].replace(
                listener,
                "function neverCalledRegistration() {\n"
                + listener
                + "\n}",
            )

        mutations["dead_listener_registration"] = dead_listener_registration

        def string_listener_registration(value):
            content = value["scenes"][9]["content"]
            listener = """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});"""
            content["html"] = content["html"].replace(
                listener,
                "const registrationProof = \"document.getElementById("
                "'rotate-button').addEventListener('click', () => { "
                "mesh.rotation.y += 0.25; renderModel(); });\";",
            )

        mutations["string_listener_registration"] = string_listener_registration

        def string_renderer_initializer(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const renderer = new THREE.WebGLRenderer({ canvas });",
                "const renderer = new THREE.WebGLRenderer();\n"
                "const rendererProof = \"renderer = new THREE.WebGLRenderer("
                "{canvas: document.getElementById('three-canvas')})\";",
            )

        mutations["string_renderer_initializer"] = string_renderer_initializer

        def string_renderer_mount(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const renderer = new THREE.WebGLRenderer({ canvas });",
                "const renderer = new THREE.WebGLRenderer();\n"
                "const mountProof = \"document.getElementById("
                "'three-canvas').appendChild(renderer.domElement)\";",
            )

        mutations["string_renderer_mount"] = string_renderer_mount

        def unused_concise_arrow_listener_registration(value):
            content = value["scenes"][9]["content"]
            listener = """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});"""
            content["html"] = content["html"].replace(
                listener,
                "const registerUnused = () => document.getElementById("
                "'rotate-button').addEventListener('click', () => { "
                "mesh.rotation.y += 0.25; renderModel(); });",
            )

        mutations["unused_concise_arrow_listener_registration"] = (
            unused_concise_arrow_listener_registration
        )

        def nested_default_concise_arrow_listener(value):
            content = value["scenes"][9]["content"]
            listener = """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});"""
            content["html"] = content["html"].replace(
                listener,
                "const registerUnused = (event = makeDefault()) => "
                "document.getElementById('rotate-button').addEventListener("
                "'click', () => { mesh.rotation.y += 0.25; renderModel(); });",
            )

        mutations["nested_default_concise_arrow_listener"] = (
            nested_default_concise_arrow_listener
        )

        def multiline_nested_concise_arrow_listener(value):
            content = value["scenes"][9]["content"]
            listener = """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});"""
            content["html"] = content["html"].replace(
                listener,
                """const registerUnused = (
  event = makeDefault(
    1
  )
) => document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});""",
            )

        mutations["multiline_nested_concise_arrow_listener"] = (
            multiline_nested_concise_arrow_listener
        )

        def string_named_function_fake_3d(value):
            content = value["scenes"][9]["content"]
            real_setup = """const canvas = document.getElementById('three-canvas');
const renderer = new THREE.WebGLRenderer({ canvas });
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
scene.add(mesh);
function renderModel() { renderer.render(scene, camera); }
document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});
renderModel();"""
            fake_setup = (
                "const proof = \"function fake() { const canvas = "
                "document.getElementById('three-canvas'); const renderer = new "
                "THREE.WebGLRenderer({ canvas }); const scene = new THREE.Scene(); "
                "const camera = new THREE.PerspectiveCamera(); const mesh = new "
                "THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial()); "
                "scene.add(mesh); document.getElementById('rotate-button')."
                "addEventListener('click', () => { mesh.rotation.y += 0.25; "
                "renderer.render(scene, camera); }); }\";\nfake();"
                "\ndocument.getElementById('rotate-button').textContent = '旋转';"
            )
            content["html"] = content["html"].replace(real_setup, fake_setup)

        mutations["string_named_function_fake_3d"] = string_named_function_fake_3d

        def cross_scope_renderer_alias(value):
            content = value["scenes"][9]["content"]
            config_json = json.dumps(
                content["widgetConfig"], ensure_ascii=False, separators=(",", ":")
            )
            content["html"] = f"""
              <html><body><button id="rotate-button">旋转</button>
              <canvas id="three-canvas"></canvas>
              <script>
              const renderer = new THREE.WebGLRenderer();
              const scene = new THREE.Scene();
              const camera = new THREE.PerspectiveCamera();
              const mesh = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial());
              scene.add(mesh);
              function decoyRendererScope() {{
                const canvas = document.getElementById('three-canvas');
                const renderer = new THREE.WebGLRenderer({{ canvas }});
              }}
              decoyRendererScope();
              document.getElementById('rotate-button').addEventListener('click', () => {{
                mesh.rotation.y += 0.25;
                renderer.render(scene, camera);
              }});
              </script>
              <script type="application/json" id="widget-config">{config_json}</script>
              </body></html>
            """

        mutations["cross_scope_renderer_alias"] = cross_scope_renderer_alias

        def unbound_3d_control(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "document.getElementById('rotate-button').addEventListener",
                "document.getElementById('does-not-exist').addEventListener",
            )

        mutations["unbound_3d_control"] = unbound_3d_control

        def block_shadow_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const canvas = document.getElementById('three-canvas');",
                "const canvas = document.createElement('canvas');\n"
                "{ const canvas = document.getElementById('three-canvas'); }",
            )

        mutations["block_shadow_canvas"] = block_shadow_canvas

        def block_shadow_renderer(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const renderer = new THREE.WebGLRenderer({ canvas });",
                "const renderer = new THREE.WebGLRenderer();\n"
                "{ const renderer = new THREE.WebGLRenderer({ "
                "canvas: document.getElementById('three-canvas') }); }",
            )

        mutations["block_shadow_renderer"] = block_shadow_renderer

        def duplicate_render_function(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "function renderModel() { renderer.render(scene, camera); }",
                "function renderModel() { renderer.render(scene, camera); }\n"
                "function renderModel() {}",
            )

        mutations["duplicate_render_function"] = duplicate_render_function

        def renderer_reassignment(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const renderer = new THREE.WebGLRenderer({ canvas });",
                "let renderer = new THREE.WebGLRenderer({ canvas });\n"
                "renderer = new THREE.WebGLRenderer();",
            )

        mutations["renderer_reassignment"] = renderer_reassignment

        def canvas_reassignment(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "const canvas = document.getElementById('three-canvas');",
                "let canvas = document.getElementById('three-canvas');\n"
                "canvas = document.createElement('canvas');",
            )

        mutations["canvas_reassignment"] = canvas_reassignment

        def render_function_reassignment(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "function renderModel() { renderer.render(scene, camera); }",
                "function renderModel() { renderer.render(scene, camera); }\n"
                "renderModel = () => {};",
            )

        mutations["render_function_reassignment"] = render_function_reassignment

        def css_hidden_3d_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "</body>",
                "<style>#three-canvas { display: none; }</style></body>",
            )

        mutations["css_hidden_3d_canvas"] = css_hidden_3d_canvas

        def css_hidden_3d_control(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "</body>",
                "<style>#rotate-button { visibility: hidden; }</style></body>",
            )

        mutations["css_hidden_3d_control"] = css_hidden_3d_control

        def disabled_3d_control(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<button id="rotate-button"',
                '<button disabled id="rotate-button"',
            )

        mutations["disabled_3d_control"] = disabled_3d_control

        def aria_disabled_3d_control(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<button id="rotate-button"',
                '<button aria-disabled="true" id="rotate-button"',
            )

        mutations["aria_disabled_3d_control"] = aria_disabled_3d_control

        def inline_pointer_events_none(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<button id="rotate-button"',
                '<button style="pointer-events:none" id="rotate-button"',
            )

        mutations["inline_pointer_events_none"] = inline_pointer_events_none

        def css_pointer_events_none(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "</body>",
                "<style>#rotate-button { pointer-events: none; }</style></body>",
            )

        mutations["css_pointer_events_none"] = css_pointer_events_none

        def inline_important_hidden_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<canvas id="three-canvas"',
                '<canvas style="display:none!important" id="three-canvas"',
            )

        mutations["inline_important_hidden_canvas"] = inline_important_hidden_canvas

        def inline_important_hidden_control(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<button id="rotate-button"',
                '<button style="visibility:hidden!important" id="rotate-button"',
            )

        mutations["inline_important_hidden_control"] = inline_important_hidden_control

        def numeric_zero_opacity_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<canvas id="three-canvas"',
                '<canvas style="opacity:0.0" id="three-canvas"',
            )

        mutations["numeric_zero_opacity_canvas"] = numeric_zero_opacity_canvas

        def exponent_zero_opacity_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "</body>",
                "<style>#three-canvas { opacity: 0e0; }</style></body>",
            )

        mutations["exponent_zero_opacity_canvas"] = exponent_zero_opacity_canvas

        def attribute_id_hidden_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                "</body>",
                '<style>[id="three-canvas"] { display:none; }</style></body>',
            )

        mutations["attribute_id_hidden_canvas"] = attribute_id_hidden_canvas

        def attribute_class_hidden_canvas(value):
            content = value["scenes"][9]["content"]
            content["html"] = content["html"].replace(
                '<canvas id="three-canvas"',
                '<canvas class="stage-canvas" id="three-canvas"',
            ).replace(
                "</body>",
                '<style>[class~="stage-canvas"] { display:none; }</style></body>',
            )

        mutations["attribute_class_hidden_canvas"] = attribute_class_hidden_canvas

        for scene_index, name in ((7, "simulation"), (8, "game"), (9, "3d")):
            mutations[f"{name}_top_level_extra"] = (
                lambda value, index=scene_index: value["scenes"][index]["content"][
                    "widgetConfig"
                ].update(unexpected=True)
            )

        def simulation_nested_extra(value):
            value["scenes"][7]["content"]["widgetConfig"]["variables"][0][
                "answer"
            ] = 42

        mutations["simulation_nested_extra"] = simulation_nested_extra

        def simulation_preset_out_of_range(value):
            value["scenes"][7]["content"]["widgetConfig"]["presets"][0][
                "variables"
            ]["count"] = 99

        mutations["simulation_preset_out_of_range"] = simulation_preset_out_of_range

        def game_duplicate_target(value):
            config = value["scenes"][8]["content"]["widgetConfig"]
            config["gameConfig"]["targets"].append(
                deepcopy(config["gameConfig"]["targets"][0])
            )

        mutations["game_duplicate_target"] = game_duplicate_target

        def game_nested_extra(value):
            value["scenes"][8]["content"]["widgetConfig"]["scoring"][
                "unexpected"
            ] = True

        mutations["game_nested_extra"] = game_nested_extra

        def game_duplicate_control(value):
            controls = value["scenes"][8]["content"]["widgetConfig"][
                "gameConfig"
            ]["controls"]
            controls.append(controls[0])

        mutations["game_duplicate_control"] = game_duplicate_control

        def game_duplicate_achievement(value):
            config = value["scenes"][8]["content"]["widgetConfig"]
            config["achievements"].append(deepcopy(config["achievements"][0]))

        mutations["game_duplicate_achievement"] = game_duplicate_achievement

        def visualization_missing_reference(value):
            value["scenes"][9]["content"]["widgetConfig"]["interactions"][0][
                "target"
            ] = "missing-object"

        mutations["visualization_missing_reference"] = visualization_missing_reference

        def visualization_duplicate_object(value):
            config = value["scenes"][9]["content"]["widgetConfig"]
            config["objects"].append(deepcopy(config["objects"][0]))

        mutations["visualization_duplicate_object"] = visualization_duplicate_object

        config_mutations = {
            "simulation_top_level_extra",
            "game_top_level_extra",
            "3d_top_level_extra",
            "simulation_nested_extra",
            "simulation_preset_out_of_range",
            "game_duplicate_target",
            "game_nested_extra",
            "game_duplicate_control",
            "game_duplicate_achievement",
            "visualization_missing_reference",
            "visualization_duplicate_object",
        }

        def sync_embedded_widget_config(value):
            marker = '<script type="application/json" id="widget-config">'
            for scene in value["scenes"]:
                if scene["type"] != "interactive":
                    continue
                content = scene["content"]
                html = content["html"]
                start = html.index(marker) + len(marker)
                end = html.index("</script>", start)
                encoded = json.dumps(
                    content["widgetConfig"],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                content["html"] = html[:start] + encoded + html[end:]

        for name, mutate in mutations.items():
            with self.subTest(name=name):
                invalid = deepcopy(valid)
                mutate(invalid)
                if name in config_mutations:
                    sync_embedded_widget_config(invalid)
                with self.assertRaises(OpenMaicRuntimeServiceError):
                    validator(invalid, teacher_contract=teacher_contract)

    def test_formal_widget_reachability_rejects_provably_dead_registration(self):
        validator = getattr(
            _candidate_service(), "_validate_formal_classroom", None
        )
        self.assertTrue(callable(validator))

        listeners = {
            "simulation": (
                7,
                "slider.addEventListener('input', updateSimulation);",
            ),
            "game": (
                8,
                """document.getElementById('start_button').addEventListener('click', () => {
  score += 10;
  level++;
  scoreStatus.textContent = String(score);
  requestAnimationFrame(renderGame);
});""",
            ),
        }
        dead_wrappers = {
            "if_false": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "if (false) { registerDead(); }"
            ),
            "if_zero": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "if (0) { registerDead(); }"
            ),
            "if_null": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "if (null) { registerDead(); }"
            ),
            "if_undefined": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "if (undefined) { registerDead(); }"
            ),
            "false_and": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "false && registerDead();"
            ),
            "zero_and": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "0 && registerDead();"
            ),
            "true_or": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "true || registerDead();"
            ),
            "false_ternary": lambda listener: (
                f"function registerDead() {{\n{listener}\n}}\n"
                "false ? registerDead() : 0;"
            ),
            "after_return": lambda listener: (
                "function registerDead() {\n  return;\n"
                f"{listener}\n}}\nregisterDead();"
            ),
            "after_throw": lambda listener: (
                "function registerDead() {\n  throw new Error('stop');\n"
                f"{listener}\n}}\nregisterDead();"
            ),
            "after_return_asi": lambda listener: (
                "function registerDead() {\n  return\n"
                f"{listener}\n}}\nregisterDead();"
            ),
            "after_throw_asi": lambda listener: (
                "function registerDead() {\n  throw new Error('stop')\n"
                f"{listener}\n}}\nregisterDead();"
            ),
            "if_true_return": lambda listener: (
                "function registerDead() {\n  if (true) return;\n"
                f"{listener}\n}}\nregisterDead();"
            ),
            "empty_try_catch": lambda listener: (
                "try { } catch (error) {\n"
                f"{listener}\n}}"
            ),
        }

        for widget_type, (scene_index, listener) in listeners.items():
            for flow_name, wrap in dead_wrappers.items():
                with self.subTest(widget=widget_type, flow=flow_name):
                    invalid = _formal_classroom()
                    invalid["scenes"][scene_index]["content"]["html"] = invalid[
                        "scenes"
                    ][scene_index]["content"]["html"].replace(
                        listener, wrap(listener)
                    )
                    with self.assertRaises(OpenMaicRuntimeServiceError):
                        validator(invalid)

        dynamic = _formal_classroom()
        simulation_listener = listeners["simulation"][1]
        dynamic["scenes"][7]["content"]["html"] = dynamic["scenes"][7][
            "content"
        ]["html"].replace(
            simulation_listener,
            "function registerWhenReady() {\n"
            + simulation_listener
            + "\n}\nif (window.formalReady) { registerWhenReady(); }",
        )
        validator(dynamic)

        dynamic_comparisons = {
            "strict_true_or": (
                "if (window.formalReady === true || window.forceReady) "
                "{ registerWhenReady(); }"
            ),
            "strict_false_and": (
                "if (window.formalReady === false && window.allow) "
                "{ registerWhenReady(); }"
            ),
            "strict_not_false_and": (
                "if (window.formalReady !== false && window.allow) "
                "{ registerWhenReady(); }"
            ),
            "loose_null_or": (
                "if (window.formalReady == null || window.forceReady) "
                "{ registerWhenReady(); }"
            ),
            "strict_undefined_ternary": (
                "window.formalReady === undefined ? registerWhenReady() : 0;"
            ),
            "loose_undefined_ternary": (
                "window.formalReady == undefined ? registerWhenReady() : 0;"
            ),
        }
        for widget_type, (scene_index, listener) in listeners.items():
            for comparison_name, condition in dynamic_comparisons.items():
                with self.subTest(
                    widget=widget_type,
                    dynamic_comparison=comparison_name,
                ):
                    dynamic_comparison = _formal_classroom()
                    dynamic_comparison["scenes"][scene_index]["content"][
                        "html"
                    ] = dynamic_comparison["scenes"][scene_index]["content"][
                        "html"
                    ].replace(
                        listener,
                        "function registerWhenReady() {\n"
                        + listener
                        + "\n}\n"
                        + condition,
                    )
                    validator(dynamic_comparison)

        dynamic_terminals = {
            "unbraced_dynamic_return": lambda listener: (
                "function registerWhenReady() {\n"
                "  if (window.skipRegistration) return;\n"
                f"{listener}\n}}\nregisterWhenReady();"
            ),
            "braced_dynamic_return": lambda listener: (
                "function registerWhenReady() {\n"
                "  if (window.skipRegistration) { return; }\n"
                f"{listener}\n}}\nregisterWhenReady();"
            ),
            "unbraced_dynamic_throw": lambda listener: (
                "function registerWhenReady() {\n"
                "  if (window.skipRegistration) throw new Error('skip');\n"
                f"{listener}\n}}\nregisterWhenReady();"
            ),
            "member_return_call": lambda listener: (
                "function registerWhenReady() {\n"
                "  window.controller.return();\n"
                f"{listener}\n}}\nregisterWhenReady();"
            ),
            "member_throw_call": lambda listener: (
                "function registerWhenReady() {\n"
                "  window.controller.throw();\n"
                f"{listener}\n}}\nregisterWhenReady();"
            ),
        }
        for widget_type, (scene_index, listener) in listeners.items():
            for terminal_name, wrap in dynamic_terminals.items():
                with self.subTest(
                    widget=widget_type,
                    dynamic_terminal=terminal_name,
                ):
                    dynamic_terminal = _formal_classroom()
                    dynamic_terminal["scenes"][scene_index]["content"][
                        "html"
                    ] = dynamic_terminal["scenes"][scene_index]["content"][
                        "html"
                    ].replace(listener, wrap(listener))
                    validator(dynamic_terminal)

        dead_3d = _formal_classroom()
        listener_3d = """document.getElementById('rotate-button').addEventListener('click', () => {
  mesh.rotation.y += 0.25;
  renderModel();
});"""
        dead_3d["scenes"][9]["content"]["html"] = dead_3d["scenes"][9][
            "content"
        ]["html"].replace(
            listener_3d,
            "function registerDead3d() {\n"
            + listener_3d
            + "\n}\ntrue || registerDead3d();",
        )
        with self.assertRaises(OpenMaicRuntimeServiceError):
            validator(dead_3d)


if __name__ == "__main__":
    unittest.main()
