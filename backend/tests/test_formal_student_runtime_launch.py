from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from contextlib import contextmanager
from copy import deepcopy

from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from repositories.lesson_package_repository import LessonPackageRepository
from services.lesson_runtime_service import LessonRuntimeService
from services.openmaic_full_runtime_service import (
    FORMAL_RUNTIME_CLASSROOM_CONTRACT,
    OpenMaicFullRuntimeService,
    OpenMaicRuntimeServiceError,
    SAMPLE_REQUIRED_FEATURES,
)


def _with_receipt_sha256(payload: dict) -> dict:
    result = deepcopy(payload)
    result["receiptSha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return result


def _formal_manifest(
    *, subject: str = "math", speech_action_count: int = 12
) -> dict:
    enabled = list(SAMPLE_REQUIRED_FEATURES)
    course_id = f"course-primary-2-{subject}"
    teacher = {
        "chinese": {
            "profileId": "mira_chinese_gentle",
            "contentHash": "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
            "name": "小语老师",
            "profileAvatar": "/teachers/mi-chinese-v1.png",
            "runtimeAvatar": "/avatars/teacher-2.png",
            "gender": "female",
            "voiceId": "Serena",
        },
        "math": {
            "profileId": "mira_math_clear",
            "contentHash": "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
            "name": "小数老师",
            "profileAvatar": "/teachers/ashu-math-v1.png",
            "runtimeAvatar": "/avatars/teacher.png",
            "gender": "male",
            "voiceId": "Ethan",
        },
        "english": {
            "profileId": "mira_english_standard",
            "contentHash": "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
            "name": "Mia 老师",
            "profileAvatar": "/teachers/coco-english-v1.png",
            "runtimeAvatar": "/avatars/teacher-2.png",
            "gender": "female",
            "voiceId": "Jennifer",
        },
    }[subject]
    teacher_contract = {
        "teacherProfile": {
            "id": teacher["profileId"],
            "version": 2,
            "contentHash": teacher["contentHash"],
            "displayName": teacher["name"],
            "avatarPath": teacher["profileAvatar"],
        },
        "runtime": {
            "name": teacher["name"],
            "role": "teacher",
            "avatar": teacher["runtimeAvatar"],
            "teacherGender": teacher["gender"],
            "voiceGender": teacher["gender"],
            "voiceConfig": {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": teacher["voiceId"],
            },
        },
    }
    professional = _with_receipt_sha256(
        {
            "schemaVersion": (
                OpenMaicFullRuntimeClient
                .FORMAL_PROFESSIONAL_CREATION_RECEIPT_VERSION
            ),
            "status": "succeeded",
            "runtimeRequestId": "runtime-request-1",
            "buildItemId": "build-item-1",
            "classroomId": "classroom-1",
            "teachingBriefSha256": "c" * 64,
            "sessionId": "professional-session-1",
            "workflowVersion": "openmaic-pro-agent.v1",
            "skillId": "mira-primary-courseware",
            "supportingSkillIds": [
                "k12-core-literacy-planning",
                "deep-interactive",
            ],
            "userPromptRequired": False,
            "studentToolsEnabled": False,
            "webSearchEnabled": True,
        }
    )
    research = _with_receipt_sha256(
        {
            "schemaVersion": (
                OpenMaicFullRuntimeClient.FORMAL_RESEARCH_RECEIPT_VERSION
            ),
            "status": "succeeded",
            "runtimeRequestId": "runtime-request-1",
            "buildItemId": "build-item-1",
            "classroomId": "classroom-1",
            "sessionId": "professional-session-1",
            "providerId": "openmaic-web-search",
            "searchCount": 1,
            "resultCount": 1,
            "fetchedSourceCount": 1,
            "citationCount": 1,
            "searches": [
                {
                    "query": "小学正式课堂资料",
                    "searchedAt": "2026-09-03T00:00:00Z",
                    "resultCount": 1,
                }
            ],
            "sources": [
                {
                    "title": "权威教学资料",
                    "url": "https://example.edu/primary",
                    "textSha256": "1" * 64,
                }
            ],
            "citations": [
                {
                    "url": "https://example.edu/primary",
                    "sceneIds": ["formal-scene-1"],
                }
            ],
        }
    )
    return {
        "schemaVersion": "mira.openmaic.runtime-features.v2",
        "sourceVersion": OpenMaicFullRuntimeService.SOURCE_VERSION,
        "sourceCommit": OpenMaicFullRuntimeService.SOURCE_COMMIT,
        "enabled": enabled,
        "requested": enabled,
        "required": enabled,
        "present": enabled,
        "missing": [],
        "evidence": {
            feature: {"verified": True, "signals": [f"{feature}:ok"], "reasons": []}
            for feature in enabled
        },
        "platform": {
            "mp4Export": False,
            "mp4ExportConfigured": False,
            "mp4ExportCapabilityProbed": False,
            "mp4ExportClassroomDryRun": False,
            "assessmentAuthority": "mira_backend",
        },
        "sceneTypes": ["slide", "quiz", "interactive"],
        "actionTypes": ["speech", "discussion", "spotlight", "widget_highlight"],
        "sceneCount": 10,
        "generationContract": {
            "schemaVersion": (
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
            ),
            "authority": "mira_backend_formal_candidate",
            "buildItemId": "build-item-1",
            "course": {
                "id": course_id,
                "version": "1",
                "packageId": "package-1",
                "packageVersion": 1,
            },
            "targetFingerprint": "a" * 64,
            "runtimeRequestId": "runtime-request-1",
            "sourceCourseContentSha256": "b" * 64,
            "teachingBriefSha256": "c" * 64,
            "teachingBrief": {
                "schemaVersion": "mira.learning.formal-runtime-teaching-brief.v1",
                "sourceCourseContentSha256": "b" * 64,
                "course": {
                    "id": course_id,
                    "version": "1",
                    "gradeCode": "primary_2",
                    "subject": subject,
                    "skillId": "skill-1",
                    "title": "正式课程",
                    "objective": "完成本节课学习",
                },
                "lesson": {
                    "intro": "开始学习",
                    "estimatedMinutes": 10,
                    "teachingFlow": {
                        "schemaVersion": "mira.learning.teaching-flow.v1",
                        "teach": {
                            "title": "讲解",
                            "sayText": "一起学习",
                            "keyPoints": ["重点"],
                        },
                        "demoQuestionId": "q1",
                        "guidedQuestionIds": ["q2", "q3"],
                        "independentQuestionIds": ["q4", "q5"],
                        "recap": {"sayText": "完成"},
                    },
                    "questions": [
                        {
                            "id": f"q{index}",
                            "type": "choice",
                            "prompt": f"题目{index}",
                            "skill": "skill-1",
                            "hint": "提示",
                            "explanation": "讲解",
                            "choices": [{"id": "a", "label": "答案"}],
                        }
                        for index in range(1, 6)
                    ],
                },
                "authority": {
                    "source": "locked_learning_course",
                    "answerContractProvided": False,
                    "scoringRulesProvided": False,
                    "providerSecretsProvided": False,
                },
            },
            "teacher": teacher_contract,
            "requiredClassroom": FORMAL_RUNTIME_CLASSROOM_CONTRACT,
            "coursewareAuthority": deepcopy(
                OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
            ),
            "professionalCreationPolicy": deepcopy(
                OpenMaicFullRuntimeClient.LEGACY_FORMAL_PROFESSIONAL_CREATION_POLICY
            ),
            "generation": deepcopy(
                OpenMaicFullRuntimeClient.LEGACY_FORMAL_GENERATION_OPTIONS
            ),
        },
        "formalRuntimeContract": FORMAL_RUNTIME_CLASSROOM_CONTRACT,
        "formalEvidence": {
            "sceneDistribution": {
                "slide": 5,
                "quiz": 2,
                "interactive": 3,
                "pbl": 0,
            },
            "peerCount": 4,
            "speechSceneCount": 10,
            "speechActionCount": speech_action_count,
            "distinctDiscussionPeerCount": 2,
            "spotlightVerified": True,
            "widgetHighlightVerified": True,
            "widgetTypes": ["game", "simulation", "visualization3d"],
            "teacher": {
                "agentId": "formal-teacher-1",
                "name": teacher["name"],
                "avatar": teacher["runtimeAvatar"],
                "teacherGender": teacher["gender"],
                "voiceGender": teacher["gender"],
                "voiceId": teacher["voiceId"],
            },
            "runtimeEventAuthority": {
                "schemaVersion": "mira.openmaic.runtime-event-authority.v1",
                "scenes": [
                    {"sceneIndex": scene_index}
                    for scene_index in range(10)
                ],
            },
            "professionalCreation": {
                "verified": True,
                "schemaVersion": professional["schemaVersion"],
                "sessionId": professional["sessionId"],
                "workflowVersion": professional["workflowVersion"],
                "skillId": professional["skillId"],
                "supportingSkillIds": list(
                    professional["supportingSkillIds"]
                ),
                "userPromptRequired": False,
                "studentToolsEnabled": False,
                "webSearchEnabled": True,
                "receiptSha256": professional["receiptSha256"],
            },
            "research": {
                "verified": True,
                "schemaVersion": research["schemaVersion"],
                "sessionId": research["sessionId"],
                "providerId": research["providerId"],
                "searchCount": 1,
                "resultCount": 1,
                "fetchedSourceCount": 1,
                "citationCount": 1,
                "citedSceneCount": 1,
                "receiptSha256": research["receiptSha256"],
            },
        },
        "professionalCreation": professional,
        "research": research,
        "sourceCourseContentSha256": "b" * 64,
        "teachingBriefSha256": "c" * 64,
        "classroomContentSha256": "d" * 64,
    }


def _formal_row(
    *, subject: str = "math", speech_action_count: int = 12
) -> dict:
    voice = {
        "chinese": ("mira_chinese_gentle", "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8", "小语老师", "female", "Serena", "zh-CN"),
        "math": ("mira_math_clear", "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb", "小数老师", "male", "Ethan", "zh-CN"),
        "english": ("mira_english_standard", "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040", "Mia 老师", "female", "Jennifer", "en-US"),
    }[subject]
    return {
        "learning_session_id": "session-1",
        "child_grade_code": "primary_2",
        "course_id": f"course-primary-2-{subject}",
        "course_version": "1",
        "course_grade_code": "primary_2",
        "course_subject": subject,
        "course_node_code": "skill-1",
        "lesson_package_id": "package-1",
        "lesson_package_version": 1,
        "lesson_package_content_hash": "9" * 64,
        "runtime_classroom_id": "runtime-1",
        "runtime_request_id": "runtime-request-1",
        "runtime_status": "ready",
        "runtime_quality_status": "pending_review",
        "upstream_classroom_id": "classroom-1",
        "feature_manifest_json": _formal_manifest(
            subject=subject,
            speech_action_count=speech_action_count,
        ),
        "candidate_build_item_id": "build-item-1",
        "candidate_release_id": "release-1",
        "candidate_grade_code": "primary_2",
        "candidate_target_fingerprint": "a" * 64,
        "candidate_binding_contract_version": (
            "mira.learning.candidate-runtime-binding.v1"
        ),
        # Formal visibility is owned by the grade pointer, not the legacy
        # curriculum-wide release status.
        "candidate_release_status": "candidate",
        "active_candidate_release_id": "release-1",
        "active_candidate_fingerprint": "a" * 64,
        "active_candidate_contract_version": "mira.learning.formal-publication.v1",
        "candidate_publication_status": "published",
        "candidate_auto_validated": 1,
        "candidate_tts_status": "passed",
        "candidate_asr_status": "passed",
        "candidate_conversation_status": "passed",
        "formal_audio_state": "auto_validated",
        "formal_audio_release_id": "release-1",
        "formal_audio_grade_code": "primary_2",
        "formal_audio_target_fingerprint": "a" * 64,
        "formal_audio_runtime_classroom_id": "runtime-1",
        "formal_audio_course_id": f"course-primary-2-{subject}",
        "formal_audio_course_version": "1",
        "formal_audio_package_id": "package-1",
        "formal_audio_package_version": 1,
        "formal_audio_classroom_sha256": "d" * 64,
        "formal_audio_subject": subject,
        "formal_audio_teacher_profile_id": voice[0],
        "formal_audio_teacher_profile_version": 2,
        "formal_audio_teacher_profile_hash": voice[1],
        "formal_audio_teacher_name": voice[2],
        "formal_audio_teacher_gender": voice[3],
        "formal_audio_voice_gender": voice[3],
        "formal_audio_voice_id": voice[4],
        "formal_audio_language_code": voice[5],
        "formal_audio_expected_segment_count": speech_action_count,
        "formal_audio_tts_attempted_count": speech_action_count,
        "formal_audio_tts_completed_count": speech_action_count,
        "formal_audio_validated_count": speech_action_count,
        "formal_audio_asr_attempted_count": speech_action_count,
        "formal_audio_asr_passed_count": speech_action_count,
        "formal_audio_receipt_hash": "e" * 64,
        "formal_provider_state": "auto_validated",
        "formal_provider_build_item_id": "build-item-1",
        "formal_provider_release_id": "release-1",
        "formal_provider_grade_code": "primary_2",
        "formal_provider_target_fingerprint": "a" * 64,
        "formal_provider_runtime_classroom_id": "runtime-1",
        "formal_provider_classroom_sha256": "d" * 64,
        "formal_provider_audio_receipt_hash": "e" * 64,
        "formal_provider_expected_count": 5,
        "formal_provider_attempted_count": 5,
        "formal_provider_passed_count": 5,
        "formal_provider_receipt_hash": "f" * 64,
        "formal_route_provider_call": 0,
        "formal_route_status": "passed",
    }


class _Auth:
    @staticmethod
    def authenticate(_token):
        return {
            "principal": {
                "id": "student-1",
                "family_id": "family-1",
                "child_id": "child-1",
            }
        }


class _Repository:
    def __init__(self, row: dict):
        self.row = row
        self.ticket_created = False
        self.ticket_consumed = False
        self.runtime_touched = False
        self.binding_calls = 0

    @contextmanager
    def transaction(self):
        yield object()

    def get_owned_session_runtime(self, _conn, **_kwargs):
        return self.row

    def bind_formal_session_to_active_release(self, _conn, **_kwargs):
        self.binding_calls += 1
        self.row.update(
            {
                "formal_binding_learning_session_id": self.row[
                    "learning_session_id"
                ],
                "formal_binding_family_id": "family-1",
                "formal_binding_child_id": "child-1",
                "formal_binding_grade_code": self.row["candidate_grade_code"],
                "formal_binding_authority_kind": "active_pointer",
                "formal_binding_pointer_history_id": "history-1",
                "formal_binding_pointer_revision": 1,
                "formal_binding_preparation_plan_id": None,
                "formal_binding_grade_selection_revision": None,
                "formal_binding_release_id": self.row["candidate_release_id"],
                "formal_binding_target_fingerprint": self.row[
                    "candidate_target_fingerprint"
                ],
                "formal_binding_contract_version": (
                    "mira.learning.formal-publication.v1"
                ),
                "formal_binding_runtime_contract_version": (
                    "mira.learning.candidate-runtime-binding.v1"
                ),
                "formal_binding_build_item_id": self.row[
                    "candidate_build_item_id"
                ],
                "formal_binding_course_id": self.row["course_id"],
                "formal_binding_course_version": self.row["course_version"],
                "formal_binding_package_id": self.row["lesson_package_id"],
                "formal_binding_package_version": self.row[
                    "lesson_package_version"
                ],
                "formal_binding_package_content_hash": "9" * 64,
                "formal_binding_runtime_classroom_id": self.row[
                    "runtime_classroom_id"
                ],
                "formal_binding_upstream_classroom_id": self.row[
                    "upstream_classroom_id"
                ],
            }
        )
        return self.row

    @staticmethod
    def decode_json(value, _fallback):
        return value

    @staticmethod
    def revoke_active_launch_tickets(_conn, **_kwargs):
        return None

    def create_launch_ticket(self, _conn, **_kwargs):
        self.ticket_created = True

    def get_launch_ticket_for_update(self, _conn, **_kwargs):
        return self.row

    def consume_launch_ticket(self, _conn, **_kwargs):
        self.ticket_consumed = True

    def get_runtime_session_for_update(self, _conn, **_kwargs):
        return self.row

    def touch_runtime_session(self, _conn, **_kwargs):
        self.runtime_touched = True


class _RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def fetchone(self):
        return self.connection.fetchone_results.pop(0)


class _RecordingConnection:
    def __init__(self, fetchone_results):
        self.fetchone_results = list(fetchone_results)
        self.calls = []

    def execute(self, statement, params=()):
        self.calls.append((statement, tuple(params)))
        return _RecordingCursor(self)


class FormalStudentRuntimeLaunchTest(unittest.TestCase):
    def _service(self, row: dict) -> OpenMaicFullRuntimeService:
        service = object.__new__(OpenMaicFullRuntimeService)
        service.enabled = True
        service.client = object()
        service.public_url = "https://classroom.mira.test"
        service.launch_ttl_seconds = 60
        service.session_ttl_seconds = 3600
        service.student_auth_service = _Auth()
        service.repository = _Repository(row)
        return service

    def test_formal_grade_two_course_launches_without_human_review(self):
        service = self._service(_formal_row(subject="math"))
        payload = service.create_student_launch("student-token", "session-1")

        self.assertTrue(service.repository.ticket_created)
        self.assertEqual(service.repository.binding_calls, 1)
        self.assertEqual(payload["features"]["teacherIdentity"]["voiceId"], "Ethan")
        self.assertEqual(payload["features"]["teacherIdentity"]["teacherGender"], "male")
        self.assertEqual(
            payload["features"]["teacherIdentity"]["agentId"],
            "formal-teacher-1",
        )
        self.assertEqual(
            payload["features"]["teacherIdentity"]["avatarPath"],
            "/teachers/ashu-math-v1.png",
        )
        self.assertEqual(
            payload["features"]["teacherIdentity"]["runtimeAvatar"],
            "/avatars/teacher.png",
        )
        self.assertEqual(
            payload["features"]["generationContract"]["teachingBrief"]["course"]["gradeCode"],
            "primary_2",
        )
        self.assertEqual(
            payload["features"]["formalEvidence"]["speechActionCount"],
            12,
        )

    def test_pending_review_formal_ticket_exchange_and_session_validation_succeed(self):
        row = _formal_row(subject="math")
        row.update(
            {
                "id": "runtime-access-1",
                "expires_at": 9_999_999_999_999,
                "revoked_at": None,
                "consumed_at": None,
            }
        )
        repository = _Repository(row)
        repository.bind_formal_session_to_active_release(object())
        service = self._service(row)
        service.repository = repository

        exchanged = service.exchange_launch_ticket("ticket-token-1")
        validated = service.validate_runtime_session("runtime-token-1")

        self.assertTrue(exchanged["ok"])
        self.assertTrue(validated["ok"])
        self.assertTrue(repository.ticket_consumed)
        self.assertTrue(repository.runtime_touched)

    def test_rejected_formal_create_fails_without_creating_access(self):
        row = _formal_row(subject="math")
        row["runtime_quality_status"] = "rejected"
        service = self._service(row)

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-token", "session-1")

        self.assertEqual(
            raised.exception.code,
            "openmaic_formal_quality_not_allowed",
        )
        self.assertFalse(service.repository.ticket_created)
        self.assertEqual(service.repository.binding_calls, 0)

    def test_rejected_formal_ticket_and_session_fail_without_advancing_access(self):
        row = _formal_row(subject="english")
        row.update(
            {
                "id": "runtime-access-1",
                "expires_at": 9_999_999_999_999,
                "revoked_at": None,
                "consumed_at": None,
            }
        )
        repository = _Repository(row)
        repository.bind_formal_session_to_active_release(object())
        row["runtime_quality_status"] = "rejected"
        service = self._service(row)
        service.repository = repository

        with self.assertRaises(OpenMaicRuntimeServiceError) as exchange:
            service.exchange_launch_ticket("ticket-token-1")
        with self.assertRaises(OpenMaicRuntimeServiceError) as validate:
            service.validate_runtime_session("runtime-token-1")

        self.assertEqual(
            exchange.exception.code,
            "openmaic_formal_quality_not_allowed",
        )
        self.assertEqual(
            validate.exception.code,
            "openmaic_formal_quality_not_allowed",
        )
        self.assertFalse(repository.ticket_consumed)
        self.assertFalse(repository.runtime_touched)

    def test_reject_review_revokes_live_student_access_in_same_transaction(self):
        runtime = {
            "id": "runtime-1",
            "request_id": "request-1",
            "course_id": "course-primary-2-math",
            "course_version": "1",
            "package_id": "package-1",
            "package_version": 1,
            "status": "ready",
            "quality_status": "pending_review",
            "feature_manifest_json": {},
            "updated_at": 100,
        }

        class ReviewRepository:
            def __init__(self):
                self.revocations = []

            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def decode_json(value, _fallback):
                return value

            @staticmethod
            def get_runtime_classroom(_conn, **_kwargs):
                return runtime

            @staticmethod
            def review_runtime_classroom(_conn, **_kwargs):
                runtime["quality_status"] = "rejected"
                return runtime

            def revoke_runtime_student_access(self, _conn, **kwargs):
                self.revocations.append(kwargs)

        service = object.__new__(OpenMaicFullRuntimeService)
        service.repository = ReviewRepository()

        payload = service.review_classroom(
            "runtime-1",
            {
                "decision": "reject",
                "reviewerId": "reviewer-1",
                "notes": "发音不合格",
            },
        )

        self.assertEqual(payload["runtime"]["qualityStatus"], "rejected")
        self.assertEqual(len(service.repository.revocations), 1)
        self.assertEqual(
            service.repository.revocations[0]["runtime_classroom_id"],
            "runtime-1",
        )

    def test_repository_revocation_targets_only_live_credentials_for_runtime(self):
        repository = OpenMaicRuntimeRepository(object())
        connection = _RecordingConnection([])

        repository.revoke_runtime_student_access(
            connection,
            runtime_classroom_id="runtime-1",
            now=123,
        )

        self.assertEqual(len(connection.calls), 2)
        ticket_statement, ticket_params = connection.calls[0]
        session_statement, session_params = connection.calls[1]
        self.assertIn("student_openmaic_launch_tickets", ticket_statement)
        self.assertIn("consumed_at IS NULL", ticket_statement)
        self.assertIn("revoked_at IS NULL", ticket_statement)
        self.assertIn("expires_at >= ?", ticket_statement)
        self.assertIn("student_openmaic_runtime_sessions", session_statement)
        self.assertIn("revoked_at IS NULL", session_statement)
        self.assertIn("expires_at >= ?", session_statement)
        self.assertEqual(ticket_params, (123, "runtime-1", 123))
        self.assertEqual(session_params, (123, "runtime-1", 123))

    def test_existing_formal_session_stays_pinned_after_grade_pointer_switch(self):
        row = _formal_row(subject="math")
        repository = _Repository(row)
        repository.bind_formal_session_to_active_release(object())
        row["active_candidate_release_id"] = "release-2"
        row["active_candidate_fingerprint"] = "b" * 64
        service = self._service(row)
        service.repository = repository

        payload = service.create_student_launch("student-token", "session-1")

        self.assertTrue(payload["ok"])
        self.assertEqual(repository.binding_calls, 1)
        self.assertTrue(repository.ticket_created)

    def test_existing_formal_binding_cannot_be_rebound_to_another_child(self):
        row = _formal_row(subject="english")
        repository = _Repository(row)
        repository.bind_formal_session_to_active_release(object())
        row["formal_binding_child_id"] = "child-2"
        service = self._service(row)
        service.repository = repository

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-token", "session-1")

        self.assertEqual(raised.exception.code, "openmaic_session_binding_conflict")
        self.assertFalse(repository.ticket_created)

    def test_progressive_plan_binding_launches_without_pointer_history(self):
        row = _formal_row(subject="math")
        row["child_grade_selection_revision"] = 3
        repository = _Repository(row)
        repository.bind_formal_session_to_active_release(object())
        row.update(
            {
                "formal_binding_authority_kind": "progressive_plan",
                "formal_binding_pointer_history_id": None,
                "formal_binding_pointer_revision": None,
                "formal_binding_preparation_plan_id": "plan-3",
                "formal_binding_grade_selection_revision": 3,
            }
        )
        service = self._service(row)
        service.repository = repository

        payload = service.create_student_launch("student-token", "session-1")

        self.assertTrue(payload["ok"])
        self.assertTrue(repository.ticket_created)

    def test_each_subject_launch_binds_visible_avatar_to_voice_gender(self):
        expected = {
            "chinese": ("female", "Serena", "/avatars/teacher-2.png"),
            "math": ("male", "Ethan", "/avatars/teacher.png"),
            "english": ("female", "Jennifer", "/avatars/teacher-2.png"),
        }
        for subject, (gender, voice_id, runtime_avatar) in expected.items():
            with self.subTest(subject=subject):
                payload = self._service(
                    _formal_row(subject=subject)
                ).create_student_launch("student-token", "session-1")
                teacher = payload["features"]["teacherIdentity"]
                self.assertEqual(teacher["teacherGender"], gender)
                self.assertEqual(teacher["voiceGender"], gender)
                self.assertEqual(teacher["voiceId"], voice_id)
                self.assertEqual(teacher["runtimeAvatar"], runtime_avatar)

    def test_formal_launch_fails_closed_when_provider_proof_is_missing(self):
        row = _formal_row(subject="english")
        row["formal_provider_state"] = "pending"
        service = self._service(row)

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-token", "session-1")
        self.assertEqual(raised.exception.code, "openmaic_formal_contract_not_verified")
        self.assertFalse(service.repository.ticket_created)

    def test_formal_math_launch_rejects_female_sample_voice(self):
        row = _formal_row(subject="math")
        row["formal_audio_voice_id"] = "Serena"
        service = self._service(row)

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-token", "session-1")
        self.assertEqual(raised.exception.code, "openmaic_formal_contract_not_verified")

    def test_all_launch_reads_join_formal_publication_audio_and_provider_authority(self):
        for method_name in (
            "get_owned_session_runtime",
            "get_launch_ticket_for_update",
            "get_runtime_session_for_update",
        ):
            source = inspect.getsource(getattr(OpenMaicRuntimeRepository, method_name))
            self.assertIn("learning_curriculum_grade_release_pointers", source)
            self.assertIn("learning_curriculum_classroom_item_receipts", source)
            self.assertIn("learning_formal_qwen_audio_jobs", source)
            self.assertIn("learning_openmaic_provider_readiness_jobs", source)
            self.assertIn("learning_student_formal_session_bindings", source)
            self.assertIn("candidate_binding_contract_version", source)
            self.assertIn("runtime_binding_contract_version", source)

    def test_new_session_resolves_the_formal_grade_pointer_before_legacy_package(self):
        resolver = inspect.getsource(
            LessonPackageRepository.get_active_formal_package
        )
        self.assertIn("learning_curriculum_grade_release_pointers", resolver)
        self.assertIn("learning_curriculum_classroom_item_receipts", resolver)
        self.assertIn("learning_formal_qwen_audio_jobs", resolver)
        self.assertIn("learning_openmaic_provider_readiness_jobs", resolver)
        attach = inspect.getsource(
            LessonRuntimeService.attach_classroom_in_transaction
        )
        self.assertLess(
            attach.index("get_active_formal_package"),
            attach.index("get_active_package"),
        )
        self.assertIn("bind_formal_session_to_active_release", attach)

    def test_formal_package_uses_candidate_binding_contract_not_publication_contract(self):
        repository = LessonPackageRepository(object())
        connection = _RecordingConnection([{"id": "package-1"}])

        package = repository.get_active_formal_package(
            connection,
            course_id="course-1",
            course_version="1",
        )

        self.assertEqual(package["id"], "package-1")
        statement, params = connection.calls[0]
        compact_statement = " ".join(statement.split())
        self.assertIn(
            "runtime.candidate_binding_contract_version = ?",
            compact_statement,
        )
        self.assertNotIn(
            "runtime.candidate_binding_contract_version = pointer.contract_version",
            compact_statement,
        )
        self.assertIn("build_item.status = 'course_ready'", compact_statement)
        self.assertIn("build_item.content_phase = 'course_ready'", compact_statement)
        self.assertIn("build_item.content_gate_status = 'passed'", compact_statement)
        self.assertIn(
            "provider.release_id = pointer.release_id",
            compact_statement,
        )
        self.assertNotIn("provider.build_item_id", compact_statement)
        self.assertNotIn("provider.runtime_classroom_id", compact_statement)
        self.assertEqual(
            params,
            (
                repository.CANDIDATE_BINDING_CONTRACT_VERSION,
                repository.CANDIDATE_BINDING_CONTRACT_VERSION,
                "course-1",
                "1",
            ),
        )
        self.assertNotEqual(
            repository.CANDIDATE_BINDING_CONTRACT_VERSION,
            "mira.learning.formal-publication.v1",
        )

    def test_formal_package_prefers_current_child_progressive_plan(self):
        repository = LessonPackageRepository(object())
        connection = _RecordingConnection([{"id": "progressive-package-1"}])

        package = repository.get_active_formal_package(
            connection,
            course_id="course-1",
            course_version="1",
            family_id="family-1",
            child_id="child-1",
        )

        self.assertEqual(package["id"], "progressive-package-1")
        self.assertEqual(len(connection.calls), 1)
        statement, params = connection.calls[0]
        compact_statement = " ".join(statement.split())
        self.assertIn(
            "plan.grade_selection_revision = child.grade_selection_revision",
            compact_statement,
        )
        self.assertIn("plan.catalog_build_id", compact_statement)
        self.assertIn("receipt.publication_status = 'published'", compact_statement)
        self.assertIn("audio.state = 'auto_validated'", compact_statement)
        self.assertIn("provider.state = 'auto_validated'", compact_statement)
        self.assertIn("build_item.status = 'course_ready'", compact_statement)
        self.assertIn("build_item.content_phase = 'course_ready'", compact_statement)
        self.assertIn("build_item.content_gate_status = 'passed'", compact_statement)
        self.assertIn(
            "provider.release_id = plan.catalog_release_id",
            compact_statement,
        )
        self.assertNotIn("provider.build_item_id", compact_statement)
        self.assertNotIn("provider.runtime_classroom_id", compact_statement)
        self.assertEqual(
            params,
            (
                repository.CANDIDATE_BINDING_CONTRACT_VERSION,
                repository.CANDIDATE_BINDING_CONTRACT_VERSION,
                "family-1",
                "child-1",
                "course-1",
                "1",
            ),
        )

    def test_formal_session_binding_uses_candidate_binding_contract(self):
        repository = OpenMaicRuntimeRepository(object())
        candidate_authority = {
            "authority_kind": "progressive_plan",
            "pointer_history_id": None,
            "pointer_revision": None,
            "preparation_plan_id": "plan-1",
            "grade_selection_revision": 2,
            "release_id": "release-1",
            "target_fingerprint": "a" * 64,
            "publication_contract_version": (
                "mira.learning.formal-publication.v1"
            ),
            "runtime_binding_contract_version": (
                repository.CANDIDATE_BINDING_CONTRACT_VERSION
            ),
            "build_item_id": "build-item-1",
            "course_id": "course-1",
            "course_version": "1",
            "package_id": "package-1",
            "package_version": 1,
            "package_content_hash": "9" * 64,
            "runtime_classroom_id": "runtime-1",
            "upstream_classroom_id": "classroom-1",
        }
        connection = _RecordingConnection(
            [
                None,
                {
                    "grade_code": "primary_1",
                    "grade_selection_revision": 2,
                },
                candidate_authority,
                {"learning_session_id": "session-1"},
            ]
        )

        binding = repository.bind_formal_session_to_active_release(
            connection,
            family_id="family-1",
            child_id="child-1",
            learning_session_id="session-1",
            now=123,
        )

        self.assertEqual(binding["learning_session_id"], "session-1")
        candidate_statement, candidate_params = next(
            call
            for call in connection.calls
            if "SELECT 'progressive_plan' AS authority_kind" in call[0]
        )
        compact_statement = " ".join(candidate_statement.split())
        self.assertIn(
            "runtime.candidate_binding_contract_version = ?",
            compact_statement,
        )
        self.assertNotIn(
            "runtime.candidate_binding_contract_version = pointer.contract_version",
            compact_statement,
        )
        self.assertIn("exact_item.release_id = plan.catalog_release_id", compact_statement)
        self.assertIn("exact_item.course_id = course.id", compact_statement)
        self.assertIn("plan.grade_selection_revision = child.grade_selection_revision", compact_statement)
        self.assertIn("plan.superseded_at IS NULL", compact_statement)
        self.assertNotIn("build_item.package_id = package.id", compact_statement)
        self.assertNotIn(
            "build_item.package_version = package.version",
            compact_statement,
        )
        self.assertIn("release_item.package_id = package.id", compact_statement)
        self.assertIn("runtime.package_id = package.id", compact_statement)
        self.assertIn("receipt.package_id = package.id", compact_statement)
        self.assertIn("exact_item.status = 'course_ready'", compact_statement)
        self.assertIn("exact_item.content_phase = 'course_ready'", compact_statement)
        self.assertIn("exact_item.content_gate_status = 'passed'", compact_statement)
        self.assertIn(
            "provider.release_id = plan.catalog_release_id",
            compact_statement,
        )
        self.assertNotIn("provider.build_item_id", compact_statement)
        self.assertNotIn("provider.runtime_classroom_id", compact_statement)
        self.assertEqual(
            candidate_params,
            (
                repository.CANDIDATE_BINDING_CONTRACT_VERSION,
                repository.CANDIDATE_BINDING_CONTRACT_VERSION,
                "session-1",
                "family-1",
                "child-1",
            ),
        )
        insert_statement, insert_params = next(
            call
            for call in connection.calls
            if "INSERT INTO learning_student_formal_session_bindings" in call[0]
        )
        self.assertIn(
            "authority_kind, pointer_history_id, pointer_revision",
            " ".join(insert_statement.split()),
        )
        self.assertEqual(insert_params[4:9], (
            "progressive_plan",
            None,
            None,
            "plan-1",
            2,
        ))

    def test_active_session_binding_accepts_content_ready_release_evidence(self):
        repository = OpenMaicRuntimeRepository(object())
        active_authority = {
            "authority_kind": "active_pointer",
            "pointer_history_id": "history-1",
            "pointer_revision": 2,
            "preparation_plan_id": None,
            "grade_selection_revision": None,
            "release_id": "release-1",
            "target_fingerprint": "a" * 64,
            "publication_contract_version": "mira.learning.formal-publication.v1",
            "runtime_binding_contract_version": (
                repository.CANDIDATE_BINDING_CONTRACT_VERSION
            ),
            "build_item_id": "build-item-1",
            "course_id": "course-1",
            "course_version": "1",
            "package_id": "package-1",
            "package_version": 1,
            "package_content_hash": "9" * 64,
            "runtime_classroom_id": "runtime-1",
            "upstream_classroom_id": "classroom-1",
        }
        connection = _RecordingConnection(
            [
                None,
                {"grade_code": "primary_1", "grade_selection_revision": 2},
                None,
                active_authority,
                {"learning_session_id": "session-1"},
            ]
        )

        binding = repository.bind_formal_session_to_active_release(
            connection,
            family_id="family-1",
            child_id="child-1",
            learning_session_id="session-1",
            now=123,
        )

        self.assertEqual(binding["learning_session_id"], "session-1")
        active_statement = next(
            statement
            for statement, _params in connection.calls
            if "SELECT 'active_pointer' AS authority_kind" in statement
        )
        compact_statement = " ".join(active_statement.split())
        self.assertIn("build_item.status = 'course_ready'", compact_statement)
        self.assertIn("build_item.content_phase = 'course_ready'", compact_statement)
        self.assertIn("build_item.content_gate_status = 'passed'", compact_statement)
        self.assertIn(
            "provider.release_id = pointer.release_id",
            compact_statement,
        )
        self.assertNotIn("provider.build_item_id", compact_statement)
        self.assertNotIn("provider.runtime_classroom_id", compact_statement)

    def test_formal_grade_never_falls_back_to_a_legacy_package(self):
        class FormalPointerWithoutExactPackage:
            @contextmanager
            def transaction(self):
                yield object()

            @staticmethod
            def get_session(_conn, **_kwargs):
                return {
                    "id": "session-1",
                    "course_id": "course-primary-2-math-old",
                    "course_version": "1",
                    "lesson_package_id": None,
                }

            @staticmethod
            def get_active_formal_package(_conn, **_kwargs):
                return None

            @staticmethod
            def has_formal_grade_pointer_for_course(_conn, **_kwargs):
                return True

            @staticmethod
            def get_active_package(_conn, **_kwargs):
                raise AssertionError("formal grade must not resolve a legacy package")

        service = object.__new__(LessonRuntimeService)
        service.repository = FormalPointerWithoutExactPackage()
        service.formal_runtime_repository = object()

        with self.assertRaises(ApiError) as raised:
            service.attach_classroom(
                family_id="family-1",
                child_id="child-1",
                start_payload={"session": {"id": "session-1"}},
            )

        self.assertEqual(raised.exception.code, "learning_classroom_release_changed")
        self.assertEqual(raised.exception.status_code, 409)

    def test_formal_start_does_not_expose_candidate_envelope_as_legacy_classroom(self):
        class FormalPackageRepository:
            @staticmethod
            def get_session(_conn, **_kwargs):
                return {
                    "id": "session-1",
                    "course_id": "course-1",
                    "course_version": "1",
                    "lesson_package_id": "formal-package-1",
                    "lesson_package_version": 1,
                }

            @staticmethod
            def get_package(_conn, **_kwargs):
                raise AssertionError(
                    "formal candidate envelope must not enter the legacy player"
                )

        class FormalRuntimeRepository:
            @staticmethod
            def bind_formal_session_to_active_release(_conn, **_kwargs):
                return {"learning_session_id": "session-1"}

        service = object.__new__(LessonRuntimeService)
        service.repository = FormalPackageRepository()
        service.formal_runtime_repository = FormalRuntimeRepository()

        payload = service.attach_classroom_in_transaction(
            object(),
            family_id="family-1",
            child_id="child-1",
            start_payload={
                "ok": True,
                "session": {"id": "session-1"},
                "lesson": {"courseId": "course-1"},
            },
        )

        self.assertEqual(payload["session"]["id"], "session-1")
        self.assertNotIn("classroom", payload)
        self.assertNotIn("package", payload)
        self.assertNotIn("cursor", payload)

    def test_wrong_teacher_identity_already_in_manifest_is_not_overwritten(self):
        row = _formal_row(subject="chinese")
        row["feature_manifest_json"] = deepcopy(row["feature_manifest_json"])
        row["feature_manifest_json"]["teacherIdentity"] = {"voiceId": "Ethan"}
        service = self._service(row)

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-token", "session-1")
        self.assertEqual(raised.exception.code, "openmaic_formal_contract_not_verified")

    def test_malformed_formal_manifest_fails_closed_as_a_product_error(self):
        row = _formal_row(subject="english")
        row["feature_manifest_json"] = deepcopy(row["feature_manifest_json"])
        row["feature_manifest_json"]["generationContract"]["course"][
            "packageVersion"
        ] = "not-an-integer"
        service = self._service(row)

        with self.assertRaises(OpenMaicRuntimeServiceError) as raised:
            service.create_student_launch("student-token", "session-1")
        self.assertEqual(raised.exception.code, "openmaic_formal_contract_not_verified")


if __name__ == "__main__":
    unittest.main()
