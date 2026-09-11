from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping
import uuid

from content.primary_skill_boundaries import boundaries_for
from content.teacher_profiles import list_teacher_profiles
from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_classroom_adapter import (
    CLASSROOM_SOURCE_OUTPUT_SCHEMA,
    ClassroomSourceResult,
    OpenMaicClassroomAdapter,
    OpenMaicClassroomError,
)
from repositories.lesson_package_repository import LessonPackageRepository
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_materialization_service import (
    LearningMediaMaterializationError,
    LearningMediaMaterializationService,
    NarrationSegmentSpec,
)
from services.lesson_package_validator import (
    FORMAL_RUNTIME_PACKAGE_SCHEMA,
    LESSON_PACKAGE_COMPILER_VERSION,
    LessonPackageValidationError,
    LessonPackageValidator,
    formal_runtime_request_id,
    formal_runtime_teaching_brief,
)
from services.learning_curriculum_preparation_contract import (
    preparation_target_fingerprint,
)


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CLASSROOM_GENERATION_LEASE_MS = 15 * 60 * 1000
@dataclass(frozen=True)
class LessonPackageGenerationResult:
    payload: dict[str, Any]
    status_code: int


class LessonPackageService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        adapter: OpenMaicClassroomAdapter | None = None,
        validator: LessonPackageValidator | None = None,
        media_service: LearningMediaMaterializationService | None = None,
    ):
        self.repository = LessonPackageRepository(Database(database_url))
        self.adapter = adapter or OpenMaicClassroomAdapter()
        self.validator = validator or LessonPackageValidator()
        self.media_service = media_service or LearningMediaMaterializationService(
            LearningTeacherMediaRepository(Database(database_url))
        )

    def status(self) -> dict[str, Any]:
        return {
            "schemaVersion": "mira.learning.classroom-generation-status.v1",
            "generator": "openmaic",
            "adapter": self.adapter.availability(),
            "policy": {
                "sourceAlwaysQuarantined": True,
                "automaticPublicationAfterValidation": False,
                "publicationRequiresNarrationAssets": True,
                "pronunciationReview": "manual_for_pinyin_and_english",
                "studentRequestGeneration": False,
                "answers": "published_learning_course_only",
                "sourceMode": "structured_intent_only",
                "rendererAuthority": "python_controlled_templates_only",
                "masteryEvidence": "q4_q5_first_attempt_two_of_two",
                "compilerVersion": LESSON_PACKAGE_COMPILER_VERSION,
            },
        }

    def job_status(self, request_id: object) -> dict[str, Any]:
        request_id = str(request_id or "").strip()
        if not _REQUEST_ID.fullmatch(request_id):
            raise ApiError("invalid_requestId", "requestId 格式无效")
        with self.repository.transaction() as conn:
            job = self.repository.get_job_by_request(
                conn,
                request_id=request_id,
            )
        if job is None:
            raise ApiError("classroom_job_not_found", "课堂生成任务不存在", 404)
        payload = {
            "ok": True,
            "status": str(job["status"]),
            "job": self._job_payload(job, created=False),
        }
        if job.get("package_id") is not None:
            payload["media"] = self.media_status(
                str(job["package_id"]),
                int(job["package_version"]),
            )["media"]
        return payload

    def process_next_pending(self) -> LessonPackageGenerationResult | None:
        """Process one queued classroom job; intended only for a background runner."""

        with self.repository.transaction() as conn:
            job = self.repository.get_next_pending_job(conn)
        if job is None:
            return None
        return self.generate(
            {
                "courseId": str(job["course_id"]),
                "courseVersion": str(job["course_version"]),
                "requestId": str(job["request_id"]),
            }
        )

    def process_next_formal_candidate(
        self, runtime_service: Any, *, preparation_plan: Mapping[str, object] | None = None
    ) -> LessonPackageGenerationResult | None:
        """Prepare one inert package authority and issue one full Runtime job.

        This path never invokes the legacy classroom adapter, publishes a
        package, binds it to a student course, or enqueues narration.
        """

        with self.repository.transaction() as conn:
            authority = self.repository.get_next_formal_candidate_authority(
                conn, preparation_plan=preparation_plan
            )
        if authority is None:
            return None
        item_id = str(authority["build_item_id"])
        course_id = str(authority["course_id"])
        course_version = str(authority["course_version"])
        attempt_ordinal = int(authority["attempt_ordinal"])
        raw_target = authority.get("target_spec_json")
        target_spec = (
            self.repository.decode_json(raw_target)
            if isinstance(raw_target, str)
            else raw_target
        )
        target_fingerprint = self._formal_target_fingerprint(target_spec)
        try:
            (
                teaching_brief,
                teaching_brief_sha256,
                source_course_content_sha256,
            ) = formal_runtime_teaching_brief(authority)
        except ValueError as exc:
            raise ApiError(
                "formal_candidate_course_content_invalid",
                "正式候选课堂的锁定课程内容无效",
                409,
            ) from exc
        package_seed = hashlib.sha256(item_id.encode("utf-8")).hexdigest()
        package_id = f"formal_runtime_package_{package_seed[:48]}"
        public_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "authority": "mira_backend_candidate_only",
            "buildItemId": item_id,
            "courseId": course_id,
            "courseVersion": course_version,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": source_course_content_sha256,
            "teachingBriefSha256": teaching_brief_sha256,
            "teachingBrief": teaching_brief,
            "studentLaunchEligible": False,
        }
        private_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "buildItemId": item_id,
            "targetFingerprint": target_fingerprint,
        }
        report = self.validator.validate_formal_runtime_package(
            payload=public_payload,
            build_item_id=item_id,
            course_id=course_id,
            course_version=course_version,
            target_fingerprint=target_fingerprint,
            teaching_brief=teaching_brief,
            teaching_brief_sha256=teaching_brief_sha256,
            source_course_content_sha256=source_course_content_sha256,
        )
        public_json = self.repository.encode_json(public_payload)
        private_json = self.repository.encode_json(private_payload)
        with self.repository.transaction() as conn:
            package, _created = self.repository.reserve_formal_runtime_package(
                conn,
                authority=authority,
                package_id=package_id,
                target_fingerprint=target_fingerprint,
                public_payload=public_payload,
                private_payload=private_payload,
                public_hash=hashlib.sha256(public_json.encode("utf-8")).hexdigest(),
                private_hash=hashlib.sha256(private_json.encode("utf-8")).hexdigest(),
                validation_report=report,
                now=now_ms(),
            )
        request_id = self._formal_runtime_request_id(
            item_id, attempt_ordinal
        )
        runtime = runtime_service.issue_candidate_generation(
            build_item_id=item_id,
            course_id=course_id,
            course_version=course_version,
            package_id=str(package["id"]),
            package_version=int(package["version"]),
            target_fingerprint=target_fingerprint,
            runtime_request_id=request_id,
        )
        return LessonPackageGenerationResult(
            payload={
                "ok": True,
                "status": str(runtime["runtime"]["status"]),
                "requestId": request_id,
                "job": {"requestId": request_id},
                "package": {
                    "id": str(package["id"]),
                    "version": int(package["version"]),
                    "status": str(package["status"]),
                },
                "runtime": dict(runtime["runtime"]),
            },
            status_code=202,
        )

    @staticmethod
    def _formal_target_fingerprint(value: object) -> str:
        if not isinstance(value, Mapping):
            raise ApiError(
                "formal_candidate_target_invalid",
                "正式候选课堂的目标合同无效",
                409,
            )
        try:
            return preparation_target_fingerprint(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(
                "formal_candidate_target_invalid",
                "正式候选课堂的目标合同无效",
                409,
            ) from exc

    @staticmethod
    def _formal_runtime_request_id(item_id: str, attempt_ordinal: int) -> str:
        return formal_runtime_request_id(item_id, attempt_ordinal)

    def enqueue(
        self,
        *,
        course_id: str,
        course_version: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        course_id = self._required(course_id, "courseId", 255)
        course_version = self._required(course_version, "courseVersion", 64)
        request_id = self._request_id(request_id)
        with self.repository.transaction() as conn:
            course = self.repository.get_course(
                conn,
                course_id=course_id,
                course_version=course_version,
            )
            if course is None:
                raise ApiError("learning_course_not_found", "学习课程版本不存在", 404)
            if (
                str(course.get("status") or "") not in {"validated", "published"}
                or course.get("retired_at") is not None
            ):
                raise ApiError(
                    "learning_course_not_validated",
                    "只有当前且已通过校验的课程可以生成互动课堂",
                    409,
                )
            job, created = self.repository.create_or_get_job(
                conn,
                request_id=request_id,
                course_id=course_id,
                course_version=course_version,
                now=now_ms(),
            )
            self._assert_job_target(
                job,
                course_id=course_id,
                course_version=course_version,
            )
            return self._job_payload(job, created=created)

    def generate(self, data: Mapping[str, Any]) -> LessonPackageGenerationResult:
        enqueued = self.enqueue(
            course_id=str(data.get("courseId") or ""),
            course_version=str(data.get("courseVersion") or ""),
            request_id=str(data.get("requestId") or "") or None,
        )
        request_id = enqueued["requestId"]
        claimed_at = now_ms()
        with self.repository.transaction() as conn:
            job = self.repository.get_job_by_request(
                conn,
                request_id=request_id,
                for_update=True,
            )
            if job is None:
                raise ApiError("classroom_job_not_found", "课堂生成任务不存在", 404)
            if str(job["status"]) not in {"pending", "generating"}:
                return self._persisted_result(job, replayed=True)
            if not self.repository.claim_job(
                conn,
                job_id=str(job["id"]),
                now=claimed_at,
                stale_before=claimed_at - CLASSROOM_GENERATION_LEASE_MS,
            ):
                latest = self.repository.get_job_by_request(
                    conn,
                    request_id=request_id,
                )
                return self._persisted_result(latest or job, replayed=True)
            job = self.repository.get_job_by_request(conn, request_id=request_id)
            course = self.repository.get_course(
                conn,
                course_id=str(job["course_id"]),
                course_version=str(job["course_version"]),
            )
            artifact = (
                self.repository.get_source_artifact(
                    conn,
                    artifact_id=str(job["source_artifact_id"]),
                )
                if job.get("source_artifact_id")
                else None
            )

        if artifact is not None:
            source = self.repository.decode_json(artifact.get("payload_json"))
            if not isinstance(source, dict):
                return self._fail(
                    job,
                    code="classroom_source_artifact_invalid",
                    message="互动课堂源课件无法恢复",
                )
            generated = ClassroomSourceResult(
                request_id=request_id,
                source=source,
                provider="persisted_source_artifact",
                model="persisted_source_artifact",
                elapsed_ms=0,
            )
            source_json = str(artifact["payload_json"])
            source_hash = str(artifact["source_hash"])
        else:
            try:
                boundary = self._boundary(course)
                public_questions = self._public_practice_questions(course)
                generated = self.adapter.generate(
                    request_id=request_id,
                    course=course,
                    skill_boundary=boundary,
                    public_questions=public_questions,
                )
            except (OpenMaicClassroomError, LessonPackageValidationError) as exc:
                return self._fail(job, code=exc.code, message=exc.message)
            except Exception:
                return self._fail(
                    job,
                    code="classroom_generation_failed",
                    message="互动课堂生成失败",
                )

            source_json = self.repository.encode_json(generated.source)
            source_hash = hashlib.sha256(source_json.encode("utf-8")).hexdigest()
            source_version = self._source_package_version(generated)
            dsl_version = str(generated.source.get("dslVersion") or "")
            artifact_created_at = now_ms()
            with self.repository.transaction() as conn:
                artifact = self.repository.create_source_artifact(
                    conn,
                    job=job,
                    source_format=CLASSROOM_SOURCE_OUTPUT_SCHEMA,
                    source_package_version=source_version,
                    dsl_version=dsl_version,
                    source_hash=source_hash,
                    payload_json=source_json,
                    now=artifact_created_at,
                )

        try:
            compiled = self.validator.compile(
                source=generated.source,
                course=course,
                source_hash=source_hash,
            )
            with self.repository.transaction() as conn:
                ready_assets = self.repository.list_ready_assets(
                    conn,
                    asset_ids=list(compiled.asset_refs),
                )
            missing_assets = set(compiled.asset_refs) - ready_assets
            if missing_assets:
                raise LessonPackageValidationError(
                    "classroom_assets_not_ready",
                    "课堂媒体资源尚未通过审核和处理",
                    path="package.assetRefs",
                )
        except LessonPackageValidationError as exc:
            with self.repository.transaction() as conn:
                self.repository.update_source_status(
                    conn,
                    artifact_id=str(artifact["id"]),
                    status="rejected",
                    validation_report={
                        "publishable": False,
                        "issues": [
                            {"code": exc.code, "message": exc.message, "path": exc.path}
                        ],
                    },
                    now=now_ms(),
                )
            return self._fail(job, code=exc.code, message=exc.message)

        try:
            with self.repository.transaction() as conn:
                package = self.repository.stage_package_for_media(
                    conn,
                    job=job,
                    artifact_id=str(artifact["id"]),
                    package_id=str(compiled.public_payload["id"]),
                    course_content_hash=hashlib.sha256(
                        str(course["content_json"]).encode("utf-8")
                    ).hexdigest(),
                    public_payload=compiled.public_payload,
                    private_payload=compiled.private_payload,
                    public_hash=compiled.public_hash,
                    private_hash=compiled.private_hash,
                    compiler_version=LESSON_PACKAGE_COMPILER_VERSION,
                    validation_report=compiled.report,
                    now=now_ms(),
                )
                media_job = self._enqueue_package_narration(
                    conn,
                    course=course,
                    package=package,
                    public_payload=compiled.public_payload,
                )
        except LearningMediaMaterializationError as exc:
            return self._fail(job, code=exc.code, message=exc.safe_message)
        except Exception:
            return self._fail(
                job,
                code="classroom_media_enqueue_failed",
                message="课件声音制作任务创建失败",
            )
        public_payload = self.repository.decode_json(package["public_payload_json"]) or {}
        return LessonPackageGenerationResult(
            payload={
                "ok": True,
                "replayed": False,
                "status": "media_pending",
                "job": self._job_payload(
                    {
                        **dict(job),
                        "status": "media_pending",
                        "package_id": package["id"],
                        "package_version": package["version"],
                    },
                    created=False,
                ),
                "package": self._package_payload(package, public_payload),
                "media": media_job,
                "validation": compiled.report,
                "generator": {
                    "name": "openmaic",
                    "provider": generated.provider,
                    "model": generated.model,
                    "elapsedMs": generated.elapsed_ms,
                },
            },
            status_code=202,
        )

    def media_status(self, package_id: object, package_version: object) -> dict[str, Any]:
        normalized_package_id = self._required(package_id, "packageId", 128)
        try:
            normalized_version = int(package_version)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_packageVersion", "packageVersion 无效") from exc
        if normalized_version < 1:
            raise ApiError("invalid_packageVersion", "packageVersion 无效")
        with self.repository.transaction() as conn:
            package = self.repository.get_package_any_status(
                conn,
                package_id=normalized_package_id,
                package_version=normalized_version,
            )
            if package is None:
                raise ApiError("lesson_package_not_found", "课件版本不存在", 404)
            media = self.repository.get_package_media_status(
                conn,
                package_id=normalized_package_id,
                package_version=normalized_version,
            )
        return {
            "ok": True,
            "package": {
                "id": normalized_package_id,
                "version": normalized_version,
                "status": str(package["status"]),
            },
            "media": media,
        }

    def finalize_media_package(
        self,
        *,
        package_id: object,
        package_version: object,
    ) -> dict[str, Any]:
        normalized_package_id = self._required(package_id, "packageId", 128)
        try:
            normalized_version = int(package_version)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_packageVersion", "packageVersion 无效") from exc
        if normalized_version < 1:
            raise ApiError("invalid_packageVersion", "packageVersion 无效")
        with self.repository.transaction() as conn:
            package = self.repository.get_package_any_status(
                conn,
                package_id=normalized_package_id,
                package_version=normalized_version,
                for_update=True,
            )
            if package is None:
                raise ApiError("lesson_package_not_found", "课件版本不存在", 404)
            media = self.repository.get_package_media_status(
                conn,
                package_id=normalized_package_id,
                package_version=normalized_version,
            )
            if media["status"] == "ready":
                package = self.repository.publish_staged_package(
                    conn,
                    package_id=normalized_package_id,
                    package_version=normalized_version,
                    now=now_ms(),
                )
            elif media["status"] in {"failed", "rejected"}:
                code = str(media.get("reason") or "media_generation_failed")
                package = self.repository.mark_staged_package_media_failed(
                    conn,
                    package_id=normalized_package_id,
                    package_version=normalized_version,
                    error_code=code,
                    error_message_safe=(
                        "课件发音审核未通过"
                        if media["status"] == "rejected"
                        else "课件声音生成失败"
                    ),
                    rejected=media["status"] == "rejected",
                    now=now_ms(),
                )
            if package is None:
                raise ApiError("lesson_package_not_found", "课件版本不存在", 404)
            public_payload = self.repository.decode_json(package["public_payload_json"]) or {}
        return {
            "ok": str(package["status"]) == "published",
            "status": str(package["status"]),
            "package": self._package_payload(package, public_payload),
            "media": media,
        }

    def _persisted_result(
        self,
        job: Mapping[str, Any],
        *,
        replayed: bool,
    ) -> LessonPackageGenerationResult:
        status = str(job.get("status") or "pending")
        payload = {
            "ok": status in {"published", "media_pending"},
            "replayed": replayed,
            "status": status,
            "job": self._job_payload(job, created=False),
        }
        if status in {"failed", "media_failed", "rejected"}:
            payload["error"] = str(job.get("error_code") or "classroom_generation_failed")
            payload["message"] = str(job.get("error_message_safe") or "互动课堂生成失败")
        if job.get("package_id") is not None:
            with self.repository.transaction() as conn:
                package = self.repository.get_package_any_status(
                    conn,
                    package_id=str(job["package_id"]),
                    package_version=int(job["package_version"]),
                )
                if package is not None:
                    public_payload = self.repository.decode_json(
                        package["public_payload_json"]
                    ) or {}
                    payload["package"] = self._package_payload(package, public_payload)
                    payload["media"] = self.repository.get_package_media_status(
                        conn,
                        package_id=str(job["package_id"]),
                        package_version=int(job["package_version"]),
                    )
        return LessonPackageGenerationResult(
            payload=payload,
            status_code=(
                200
                if status == "published"
                else 422
                if status in {"failed", "media_failed", "rejected"}
                else 202
            ),
        )

    def _enqueue_package_narration(
        self,
        conn,
        *,
        course: Mapping[str, Any],
        package: Mapping[str, Any],
        public_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        subject = str(course.get("subject") or "").strip().lower()
        profiles = list_teacher_profiles(subject=subject)
        if len(profiles) != 1:
            raise LearningMediaMaterializationError(
                "teacher_profile_not_found",
                "The controlled teacher profile is unavailable",
            )
        segments: list[NarrationSegmentSpec] = []
        scenes = public_payload.get("scenes")
        if not isinstance(scenes, list):
            raise LearningMediaMaterializationError(
                "invalid_narration_segments",
                "The lesson package has no narration scenes",
            )
        for scene in scenes:
            if not isinstance(scene, Mapping):
                continue
            scene_id = str(scene.get("id") or "").strip()
            for action in scene.get("actions") or []:
                if not isinstance(action, Mapping) or action.get("type") != "narrate":
                    continue
                segments.append(
                    NarrationSegmentSpec(
                        text=str(action.get("text") or ""),
                        subtitle=str(action.get("text") or ""),
                        scene_id=scene_id,
                        action_id=str(action.get("id") or "").strip(),
                    )
                )
        if not segments:
            raise LearningMediaMaterializationError(
                "invalid_narration_segments",
                "The lesson package has no narration actions",
            )
        fingerprint = hashlib.sha256(
            (
                f"{package['id']}:{package['version']}:"
                f"{package['public_content_hash']}"
            ).encode("utf-8")
        ).hexdigest()
        node_code = str(course.get("node_code") or "").strip().lower()
        pronunciation = (
            "english"
            if subject == "english"
            else "pinyin"
            if subject == "chinese" and node_code.startswith("pinyin")
            else "general"
        )
        profile = profiles[0]
        return self.media_service.enqueue_narration_in_transaction(
            conn,
            idempotency_key=f"lesson-media:{fingerprint}",
            teacher_profile_id=profile.profile_id,
            teacher_profile_version=profile.version,
            subject=subject,
            segments=segments,
            pronunciation_kind=pronunciation,
            package_id=str(package["id"]),
            package_version=int(package["version"]),
            course_id=str(course["id"]),
            course_version=str(course["version"]),
        )

    def _fail(
        self,
        job: Mapping[str, Any],
        *,
        code: str,
        message: str,
    ) -> LessonPackageGenerationResult:
        safe_code = re.sub(r"[^a-z0-9_]", "_", str(code).casefold())[:128]
        safe_message = str(message or "互动课堂生成失败")[:512]
        with self.repository.transaction() as conn:
            self.repository.mark_job_failed(
                conn,
                job_id=str(job["id"]),
                error_code=safe_code,
                error_message_safe=safe_message,
                now=now_ms(),
            )
        return LessonPackageGenerationResult(
            payload={
                "ok": False,
                "replayed": False,
                "status": "failed",
                "job": {
                    **self._job_payload(job, created=False),
                    "status": "failed",
                },
                "error": safe_code,
                "message": safe_message,
            },
            status_code=422,
        )

    @staticmethod
    def _public_practice_questions(course: Mapping[str, Any]) -> list[dict[str, Any]]:
        content = LessonPackageService._course_content(course)
        questions = content.get("questions")
        flow = content.get("teachingFlow")
        if not isinstance(questions, list) or not isinstance(flow, Mapping):
            raise LessonPackageValidationError(
                "invalid_classroom_course",
                "课程缺少可用的教学流程",
                path="course.content.teachingFlow",
            )
        practice_ids = [
            *[str(item) for item in flow.get("guidedQuestionIds") or []],
            *[str(item) for item in flow.get("independentQuestionIds") or []],
        ]
        by_id = {
            str(item.get("id") or ""): item
            for item in questions
            if isinstance(item, Mapping)
        }
        if len(practice_ids) != 4 or len(set(practice_ids)) != 4:
            raise LessonPackageValidationError(
                "invalid_classroom_course",
                "课程练习角色无效",
                path="course.content.teachingFlow",
            )
        result: list[dict[str, Any]] = []
        for question_id in practice_ids:
            item = by_id.get(question_id)
            if item is None:
                raise LessonPackageValidationError(
                    "invalid_classroom_course",
                    "课程练习题引用不存在",
                    path="course.content.questions",
                )
            public = {
                "id": question_id,
                "type": str(item.get("type") or ""),
                "prompt": str(item.get("prompt") or ""),
            }
            if item.get("type") in {"single_choice", "sequence"}:
                public["choices"] = [
                    {"id": choice.get("id"), "label": choice.get("label")}
                    for choice in item.get("choices") or []
                    if isinstance(choice, Mapping)
                ]
            result.append(public)
        return result

    @staticmethod
    def _boundary(course: Mapping[str, Any]) -> dict[str, Any]:
        candidates = boundaries_for(str(course["grade_code"]), str(course["subject"]))
        for boundary in candidates:
            if boundary.skill_id == str(course["node_code"]):
                if (
                    str(course.get("curriculum_version") or "")
                    != boundary.curriculum_version
                    or str(course.get("boundary_version") or "")
                    != boundary.boundary_version
                ):
                    raise LessonPackageValidationError(
                        "classroom_stale_skill_boundary",
                        "课程能力边界版本已过期",
                        path="course.boundary_version",
                    )
                return boundary.to_openmaic_payload()
        raise LessonPackageValidationError(
            "classroom_skill_boundary_not_found",
            "课程能力边界不存在",
            path="course.node_code",
        )

    @staticmethod
    def _course_content(course: Mapping[str, Any]) -> dict[str, Any]:
        try:
            value = json.loads(str(course.get("content_json") or ""))
        except json.JSONDecodeError as exc:
            raise LessonPackageValidationError(
                "invalid_classroom_course",
                "课程内容无效",
                path="course.content_json",
            ) from exc
        if not isinstance(value, dict):
            raise LessonPackageValidationError(
                "invalid_classroom_course",
                "课程内容无效",
                path="course.content_json",
            )
        return value

    @staticmethod
    def _source_package_version(generated: ClassroomSourceResult) -> str:
        metadata = generated.source.get("generationMeta")
        if isinstance(metadata, Mapping):
            value = metadata.get("sourcePackageVersion") or metadata.get("packageVersion")
            if value:
                return str(value)[:64]
        return ""

    @staticmethod
    def _package_payload(
        row: Mapping[str, Any],
        public_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "version": int(row["version"]),
            "contentHash": row["public_content_hash"],
            "status": str(row["status"]),
            "classroom": dict(public_payload),
        }

    @staticmethod
    def _job_payload(row: Mapping[str, Any], *, created: bool) -> dict[str, Any]:
        return {
            "id": row["id"],
            "requestId": row["request_id"],
            "courseId": row["course_id"],
            "courseVersion": row["course_version"],
            "status": row["status"],
            "created": created,
            "sourceArtifactId": row.get("source_artifact_id"),
            "packageId": row.get("package_id"),
            "packageVersion": row.get("package_version"),
            "error": (
                {
                    "code": row["error_code"],
                    "message": row.get("error_message_safe") or "",
                }
                if row.get("error_code")
                else None
            ),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _assert_job_target(
        job: Mapping[str, Any],
        *,
        course_id: str,
        course_version: str,
    ) -> None:
        if (
            str(job.get("course_id")) != course_id
            or str(job.get("course_version")) != course_version
        ):
            raise ApiError(
                "classroom_generation_request_conflict",
                "requestId 已绑定到其他课程版本",
                409,
            )

    @staticmethod
    def _required(value: object, label: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum:
            raise ApiError(f"invalid_{label}", f"{label} 无效")
        return text

    @staticmethod
    def _request_id(value: object) -> str:
        if value is None or not str(value).strip():
            return f"classroom_{uuid.uuid4().hex}"
        request_id = str(value).strip()
        if not _REQUEST_ID.fullmatch(request_id):
            raise ApiError("invalid_requestId", "requestId 格式无效")
        return request_id
