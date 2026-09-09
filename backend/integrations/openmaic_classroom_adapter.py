from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Mapping, Sequence


CLASSROOM_GENERATION_INPUT_SCHEMA = "mira.openmaic.classroom_generation.v1"
CLASSROOM_SOURCE_OUTPUT_SCHEMA = "mira.openmaic.classroom_intent.v2"
CLASSROOM_ADAPTER_AUTHORITY = "legacy_lesson_package_only"


class OpenMaicClassroomError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code or "classroom_generation_failed")
        self.message = str(message or "OpenMAIC classroom generation failed")


@dataclass(frozen=True)
class ClassroomSourceResult:
    request_id: str
    source: dict[str, Any]
    provider: str
    model: str
    elapsed_ms: int


class OpenMaicClassroomAdapter:
    """Call the isolated classroom sidecar without granting publication authority."""

    def __init__(
        self,
        *,
        sidecar_root: str | Path | None = None,
        node_binary: str = "node",
        timeout_seconds: float = 150.0,
        provider_name: str | None = None,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "APP_AI_API_KEY",
        provider_timeout_ms: int = 90_000,
        max_tokens: int = 10_000,
        temperature: float = 0.2,
        fake_mode: bool = False,
        fake_responses: Sequence[str] | None = None,
        process_runner=subprocess.run,
    ):
        backend_root = Path(__file__).resolve().parents[1]
        self.sidecar_root = Path(
            sidecar_root or backend_root / "openmaic-sidecar"
        ).resolve()
        self.node_binary = str(node_binary)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.provider_name = (
            provider_name or os.getenv("APP_AI_PROVIDER") or "kimi"
        ).strip()
        self.model_name = (model_name or os.getenv("APP_AI_MODEL") or "").strip()
        self.base_url = (base_url or os.getenv("APP_AI_BASE_URL") or "").strip()
        self.api_key_env = str(api_key_env).strip()
        self.provider_timeout_ms = int(provider_timeout_ms)
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.fake_mode = bool(fake_mode)
        self.fake_responses = list(fake_responses or [])
        self._run = process_runner

    @property
    def cli_path(self) -> Path:
        return self.sidecar_root / "src" / "cli.mjs"

    def availability(self) -> dict[str, Any]:
        runtime = self.cli_path.is_file() and shutil.which(self.node_binary) is not None
        provider = self.fake_mode or bool(
            self.model_name
            and self.base_url
            and os.getenv(self.api_key_env, "").strip()
        )
        return {
            "available": runtime and provider,
            "runtimeAvailable": runtime,
            "providerConfigured": provider,
            "generator": "openmaic",
            "inputSchema": CLASSROOM_GENERATION_INPUT_SCHEMA,
            "outputSchema": CLASSROOM_SOURCE_OUTPUT_SCHEMA,
            "provider": self.provider_name,
            "model": self.model_name,
            "authority": CLASSROOM_ADAPTER_AUTHORITY,
            "formalRuntimeCandidateSupported": False,
        }

    def generate(
        self,
        *,
        request_id: str,
        course: Mapping[str, Any],
        skill_boundary: Mapping[str, Any],
        public_questions: Sequence[Mapping[str, Any]],
    ) -> ClassroomSourceResult:
        payload = {
            "schemaVersion": CLASSROOM_GENERATION_INPUT_SCHEMA,
            "requestId": str(request_id),
            "gradeCode": str(course["grade_code"]),
            "subject": str(course["subject"]),
            "skillBoundary": dict(skill_boundary),
            "courseTeaching": self._course_teaching(course),
            "publicQuestions": [dict(item) for item in public_questions],
            "questionRefs": [str(item["id"]) for item in public_questions],
            "assets": [],
            "classroomOptions": {
                "maxScenes": 5,
                "maxActionsPerScene": 8,
                # Retained in the input envelope for sidecar backward parsing;
                # v2 never emits canvas or HTML and the Python host owns every
                # runtime action.
                "maxCanvasElements": 1,
                "maxHtmlChars": 1_000,
                "allowedSceneTypes": [
                    "slide",
                    "interactive",
                    "quiz",
                ],
                "requiredSceneTypes": [
                    "slide",
                    "interactive",
                    "quiz",
                ],
                "quizMode": "independent",
            },
            "mode": "fake" if self.fake_mode else "live",
            "provider": {
                "name": self.provider_name,
                "model": self.model_name,
                "baseUrl": self.base_url,
                "apiKeyEnv": self.api_key_env,
                "timeoutMs": self.provider_timeout_ms,
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
            **({"fakeResponses": self.fake_responses} if self.fake_mode else {}),
        }
        response, elapsed = self._call(payload)
        if response.get("schemaVersion") != CLASSROOM_SOURCE_OUTPUT_SCHEMA:
            raise OpenMaicClassroomError(
                "invalid_classroom_source",
                "OpenMAIC returned an unsupported classroom schema",
            )
        if (
            str(response.get("requestId") or "") != str(request_id)
            or response.get("generator") != "openmaic"
            or response.get("status") != "unverified"
            or response.get("publicationEligible") is not False
            or response.get("authoritativeAnswersProvided") is not False
            or not isinstance(response.get("classroom"), Mapping)
        ):
            raise OpenMaicClassroomError(
                "invalid_classroom_source",
                "OpenMAIC classroom source identity or authority is invalid",
            )
        return ClassroomSourceResult(
            request_id=str(request_id),
            source=dict(response),
            provider=str(response.get("provider") or self.provider_name),
            model=str(response.get("model") or self.model_name),
            elapsed_ms=max(int(response.get("elapsedMs") or elapsed), 0),
        )

    @staticmethod
    def _course_teaching(course: Mapping[str, Any]) -> dict[str, Any]:
        try:
            content = json.loads(str(course.get("content_json") or ""))
        except json.JSONDecodeError as exc:
            raise OpenMaicClassroomError(
                "invalid_classroom_course",
                "Course teaching content is invalid",
            ) from exc
        if not isinstance(content, Mapping):
            raise OpenMaicClassroomError(
                "invalid_classroom_course",
                "Course teaching content is invalid",
            )
        flow = content.get("teachingFlow")
        questions = content.get("questions")
        if not isinstance(flow, Mapping) or not isinstance(questions, list):
            raise OpenMaicClassroomError(
                "invalid_classroom_course",
                "Course teaching flow is unavailable",
            )
        teach = flow.get("teach")
        recap = flow.get("recap")
        demo_id = str(flow.get("demoQuestionId") or "")
        demo = next(
            (
                item
                for item in questions
                if isinstance(item, Mapping) and str(item.get("id") or "") == demo_id
            ),
            None,
        )
        if (
            not isinstance(teach, Mapping)
            or not isinstance(recap, Mapping)
            or not isinstance(demo, Mapping)
        ):
            raise OpenMaicClassroomError(
                "invalid_classroom_course",
                "Course teaching flow is incomplete",
            )
        return {
            "teach": {
                "title": teach.get("title"),
                "sayText": teach.get("sayText"),
                "keyPoints": list(teach.get("keyPoints") or []),
            },
            "workedExample": {
                "questionId": demo_id,
                "prompt": demo.get("prompt"),
                "explanation": demo.get("explanation"),
            },
            "recap": {"sayText": recap.get("sayText")},
        }

    def _call(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], int]:
        if not self.cli_path.is_file() or shutil.which(self.node_binary) is None:
            raise OpenMaicClassroomError(
                "openmaic_unavailable",
                "OpenMAIC classroom sidecar is unavailable",
            )
        environment = os.environ.copy()
        if self.fake_mode:
            environment["OPENMAIC_FAKE_MODE"] = "1"
        started = time.monotonic()
        try:
            completed = self._run(
                [self.node_binary, str(self.cli_path)],
                cwd=str(self.sidecar_root),
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                env=environment,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenMaicClassroomError(
                "openmaic_timeout",
                "OpenMAIC classroom generation timed out",
            ) from exc
        except OSError as exc:
            raise OpenMaicClassroomError(
                "openmaic_unavailable",
                "OpenMAIC classroom sidecar could not start",
            ) from exc
        response = self._parse(completed.stdout)
        if completed.returncode != 0:
            error = response.get("error")
            raise OpenMaicClassroomError(
                str(
                    error.get("code")
                    if isinstance(error, Mapping)
                    else "classroom_generation_failed"
                ),
                str(
                    error.get("message")
                    if isinstance(error, Mapping)
                    else "OpenMAIC classroom generation failed"
                ),
            )
        return response, int((time.monotonic() - started) * 1000)

    @staticmethod
    def _parse(value: object) -> dict[str, Any]:
        try:
            payload = json.loads(str(value or ""))
        except json.JSONDecodeError as exc:
            raise OpenMaicClassroomError(
                "invalid_classroom_source",
                "OpenMAIC classroom sidecar returned invalid JSON",
            ) from exc
        if not isinstance(payload, dict):
            raise OpenMaicClassroomError(
                "invalid_classroom_source",
                "OpenMAIC classroom sidecar returned a non-object response",
            )
        return payload
