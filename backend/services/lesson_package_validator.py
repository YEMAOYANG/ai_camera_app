from __future__ import annotations

from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
import re
from typing import Any, Mapping, Sequence

from content.primary_skill_boundaries import boundaries_for


LESSON_PACKAGE_SCHEMA = "mira.learning.lesson-package.v2"
LESSON_PACKAGE_PRIVATE_SCHEMA = "mira.learning.lesson-package-private.v2"
CLASSROOM_INTENT_SOURCE_SCHEMA = "mira.openmaic.classroom_intent.v2"
CLASSROOM_INTENT_SCHEMA = "mira.learning.classroom-intent.v1"
FORMAL_RUNTIME_PACKAGE_SCHEMA = (
    "mira.learning.formal-runtime-candidate-package.v1"
)
FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION = "mira.formal-runtime-package.v1"
FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA = (
    "mira.openmaic.formal-runtime-package-source.v1"
)
FORMAL_RUNTIME_TEACHING_BRIEF_SCHEMA = (
    "mira.learning.formal-runtime-teaching-brief.v1"
)
LESSON_PACKAGE_COMPILER_VERSION = "mira.lesson-package-compiler.v2.3.0"
SUPPORTED_OPENMAIC_DSL_VERSIONS = frozenset({"0.1.0"})

_SCENE_TYPES = frozenset({"slide", "interactive", "quiz", "recap", "video"})
_ACTION_TYPES = frozenset(
    {
        "narrate",
        "focus",
        "play_media",
        "await_continue",
        "await_interaction",
        "complete_scene",
    }
)
_TEMPLATES = frozenset({"tap_choice.v1", "match_pairs.v1", "sort_order.v1"})
_LAYOUT_TEMPLATES = frozenset({"concept_focus.v1", "phonics_focus.v1"})
_WIDGET_TEMPLATES = frozenset(
    {"listen_tap_choice.v1", "match_pairs.v1", "sort_order.v1"}
)
_ASSET_BRIEF_KINDS = frozenset({"audio", "image", "video"})
_ASSET_BRIEF_DELIVERY_MODES = frozenset({"tts", "generated_asset", "none"})
_PRIMARY_ONE_MATH_VISUAL_NODES = frozenset(
    {"number_sense_20", "addition_subtraction_20", "shapes_position"}
)
_GAME_FEEDBACK_MODES = frozenset({"encouraging_retry", "explain_then_retry"})
_BLOCK_TYPES = frozenset({"text", "shape", "image"})
_SHAPES = frozenset({"circle", "rectangle", "line"})
_WIDGET_TYPES = frozenset(
    {"simulation", "diagram", "code", "game", "visualization3d", "procedural-skill"}
)
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UNSAFE_TEXT = re.compile(
    r"<\s*/?\s*[a-z][^>]*>|javascript\s*:|data\s*:\s*text/html|"
    r"on(?:click|load|error)\s*=|&(?:lt|#0*60|#x0*3c);",
    re.IGNORECASE,
)
_ANSWER_KEYS = frozenset(
    {
        "answer",
        "answers",
        "correct",
        "correctanswer",
        "correctanswers",
        "analysis",
        "solution",
        "solutions",
        "evaluation",
        "expected",
        "acceptedanswers",
        "expectedoptionid",
        "expectedsequence",
        "score",
        "points",
        "directorprompt",
    }
)

_INTERACTIVE_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data: blob:; font-src data:; media-src blob:; connect-src 'none'; "
    "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
)
_INTERACTIVE_FORBIDDEN_JS = re.compile(
    r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon|"
    r"localStorage|sessionStorage|indexedDB|cookieStore|serviceWorker|"
    r"SharedWorker|Worker|BroadcastChannel|eval)\b|"
    r"\b(?:parent|top|opener)\b|\bdocument\s*\.\s*cookie\b|"
    r"\bwindow\s*\.\s*(?:location|open)\b|"
    r"\blocation\s*(?:=|\.|\[)|\bimport\s*\(|"
    r"\bnew\s+Function\b|https?\s*:\s*//|(?<!:)//[A-Za-z0-9]",
    re.IGNORECASE,
)
_RICH_TEXT_TAGS = frozenset(
    {"p", "span", "strong", "b", "em", "i", "u", "s", "br", "ul", "ol", "li", "sub", "sup"}
)
_SAFE_STYLE_PROPERTIES = frozenset(
    {
        "color",
        "background-color",
        "font-size",
        "font-family",
        "font-weight",
        "font-style",
        "text-decoration",
        "text-align",
        "letter-spacing",
        "line-height",
    }
)


def formal_runtime_request_id(item_id: str, attempt_ordinal: int) -> str:
    if not isinstance(item_id, str) or not item_id:
        raise ValueError("formal runtime item id is invalid")
    if type(attempt_ordinal) is not int or not 1 <= attempt_ordinal <= 3:
        raise ValueError("formal runtime attempt ordinal is invalid")
    value = f"mira-formal-runtime-{item_id}-attempt-{attempt_ordinal}"
    if len(value) <= 128 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"mira-formal-runtime-{digest}-attempt-{attempt_ordinal}"


class _InteractiveHtmlInspector(HTMLParser):
    _FORBIDDEN_TAGS = frozenset(
        {
            "link",
            "meta",
            "object",
            "embed",
            "base",
            "form",
            "iframe",
            "frame",
            "applet",
            "img",
            "audio",
            "video",
            "source",
        }
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.script_depth = 0
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._FORBIDDEN_TAGS:
            self.errors.append(f"forbidden element <{normalized_tag}>")
        attributes = {str(key).casefold(): str(value or "") for key, value in attrs}
        if normalized_tag == "script":
            self.script_depth += 1
            if attributes.get("src"):
                self.errors.append("external script src is forbidden")
            if set(attributes) - {"type"}:
                self.errors.append("script attributes are forbidden")
            if attributes.get("type") not in {
                None,
                "",
                "text/javascript",
                "application/javascript",
            }:
                self.errors.append("unsupported script type is forbidden")
        for key, value in attributes.items():
            if key.startswith("on"):
                self.errors.append(f"event handler attribute {key} is forbidden")
            if key in {"src", "href", "action", "formaction", "poster"} and value:
                self.errors.append(f"resource or navigation attribute {key} is forbidden")
            if key == "style" and re.search(
                r"url\s*\(|@import|expression\s*\(|javascript\s*:",
                value,
                re.IGNORECASE,
            ):
                self.errors.append("unsafe inline style is forbidden")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() == "script" and self.script_depth:
            self.script_depth -= 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self.script_depth:
            self.script_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.script_depth:
            self.scripts.append(data)


class LessonPackageValidationError(RuntimeError):
    def __init__(self, code: str, message: str, *, path: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path


def formal_runtime_teaching_brief(
    course: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str]:
    """Project a locked course into the bounded, answer-blind Provider brief.

    The full stored content digest remains part of the identity, while only
    explicitly allowlisted teaching text is exposed upstream.  Answer keys,
    evaluation rules, source/provider metadata, and unknown fields are never
    copied into the brief.
    """

    raw_content = course.get("content_json")
    if not isinstance(raw_content, str) or not raw_content:
        raise ValueError("formal candidate course content is missing")
    try:
        content = json.loads(raw_content)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("formal candidate course content is invalid") from None
    if not isinstance(content, Mapping):
        raise ValueError("formal candidate course content is invalid")
    if (
        content.get("schemaVersion") != "mira.learning.course.v1"
        or content.get("sessionKind") != "lesson"
        or content.get("outcomeMode") != "scored_deterministic"
    ):
        raise ValueError("formal candidate course content contract is invalid")

    def bounded_text(value: object, *, label: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"formal candidate {label} is invalid")
        text = value.strip()
        if not text or len(text) > maximum:
            raise ValueError(f"formal candidate {label} is invalid")
        return text

    def bounded_text_list(
        value: object, *, label: str, maximum: int
    ) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"formal candidate {label} is invalid")
        return [
            bounded_text(entry, label=label, maximum=maximum) for entry in value
        ]

    identity = {
        "id": bounded_text(
            course.get("id") or course.get("course_id"),
            label="course id",
            maximum=255,
        ),
        "version": bounded_text(
            course.get("version") or course.get("course_version"),
            label="course version",
            maximum=64,
        ),
        "gradeCode": bounded_text(
            course.get("grade_code"), label="grade", maximum=64
        ),
        "subject": bounded_text(
            course.get("subject"), label="subject", maximum=64
        ),
        "skillId": bounded_text(
            course.get("node_code"), label="skill", maximum=120
        ),
        "title": bounded_text(
            course.get("title"), label="title", maximum=160
        ),
        "objective": bounded_text(
            course.get("objective"), label="objective", maximum=600
        ),
    }
    intro = bounded_text(content.get("intro"), label="intro", maximum=1200)
    minutes = content.get("estimatedMinutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 5 <= minutes <= 30:
        raise ValueError("formal candidate estimated minutes are invalid")

    questions = content.get("questions")
    if not isinstance(questions, list) or len(questions) != 5:
        raise ValueError("formal candidate questions are invalid")
    projected_questions: list[dict[str, Any]] = []
    question_ids: list[str] = []
    for index, question in enumerate(questions):
        if not isinstance(question, Mapping):
            raise ValueError("formal candidate question is invalid")
        projected = {
            "id": bounded_text(
                question.get("id"), label=f"question {index + 1} id", maximum=160
            ),
            "type": bounded_text(
                question.get("type"),
                label=f"question {index + 1} type",
                maximum=32,
            ),
            "prompt": bounded_text(
                question.get("prompt"),
                label=f"question {index + 1} prompt",
                maximum=1200,
            ),
            "skill": bounded_text(
                question.get("skill"),
                label=f"question {index + 1} skill",
                maximum=240,
            ),
            "hint": bounded_text(
                question.get("hint"),
                label=f"question {index + 1} hint",
                maximum=800,
            ),
            "explanation": bounded_text(
                question.get("explanation"),
                label=f"question {index + 1} explanation",
                maximum=1600,
            ),
        }
        if projected["type"] in {"single_choice", "sequence"}:
            choices = question.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("formal candidate question choices are invalid")
            projected["choices"] = [
                {
                    "id": bounded_text(
                        choice.get("id") if isinstance(choice, Mapping) else None,
                        label="question choice id",
                        maximum=80,
                    ),
                    "label": bounded_text(
                        choice.get("label") if isinstance(choice, Mapping) else None,
                        label="question choice label",
                        maximum=480,
                    ),
                }
                for choice in choices
            ]
        question_ids.append(str(projected["id"]))
        projected_questions.append(projected)
    if len(set(question_ids)) != 5:
        raise ValueError("formal candidate question ids are invalid")

    flow = content.get("teachingFlow")
    if not isinstance(flow, Mapping) or flow.get("schemaVersion") != (
        "mira.learning.teaching-flow.v1"
    ):
        raise ValueError("formal candidate teaching flow is invalid")
    teach = flow.get("teach")
    recap = flow.get("recap")
    if not isinstance(teach, Mapping) or not isinstance(recap, Mapping):
        raise ValueError("formal candidate teaching flow is invalid")
    key_points = teach.get("keyPoints")
    if not isinstance(key_points, list) or not 1 <= len(key_points) <= 3:
        raise ValueError("formal candidate teaching key points are invalid")
    projected_flow = {
        "schemaVersion": "mira.learning.teaching-flow.v1",
        "teach": {
            "title": bounded_text(
                teach.get("title"), label="teaching title", maximum=320
            ),
            "sayText": bounded_text(
                teach.get("sayText"), label="teaching narration", maximum=2400
            ),
            "keyPoints": [
                bounded_text(point, label="teaching key point", maximum=400)
                for point in key_points
            ],
        },
        "demoQuestionId": bounded_text(
            flow.get("demoQuestionId"), label="demo question", maximum=160
        ),
        "guidedQuestionIds": bounded_text_list(
            flow.get("guidedQuestionIds"),
            label="guided question id",
            maximum=160,
        ),
        "independentQuestionIds": bounded_text_list(
            flow.get("independentQuestionIds"),
            label="independent question id",
            maximum=160,
        ),
        "recap": {
            "sayText": bounded_text(
                recap.get("sayText"), label="recap narration", maximum=1200
            )
        },
    }
    references = [
        projected_flow["demoQuestionId"],
        *projected_flow["guidedQuestionIds"],
        *projected_flow["independentQuestionIds"],
    ]
    if (
        not all(isinstance(value, str) and value for value in references)
        or len(projected_flow["guidedQuestionIds"]) != 2
        or len(projected_flow["independentQuestionIds"]) != 2
        or references != question_ids
        or len(set(references)) != 5
    ):
        raise ValueError("formal candidate teaching roles are invalid")

    source_content_sha256 = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    brief = {
        "schemaVersion": FORMAL_RUNTIME_TEACHING_BRIEF_SCHEMA,
        "sourceCourseContentSha256": source_content_sha256,
        "course": identity,
        "lesson": {
            "intro": intro,
            "estimatedMinutes": minutes,
            "teachingFlow": projected_flow,
            "questions": projected_questions,
        },
        "authority": {
            "source": "locked_learning_course",
            "answerContractProvided": False,
            "scoringRulesProvided": False,
            "providerSecretsProvided": False,
        },
    }
    canonical = json.dumps(
        brief, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if len(canonical.encode("utf-8")) > 64_000:
        raise ValueError("formal candidate teaching brief is too large")
    return brief, hashlib.sha256(canonical.encode("utf-8")).hexdigest(), source_content_sha256


@dataclass(frozen=True)
class CompiledLessonPackage:
    public_payload: dict[str, Any]
    private_payload: dict[str, Any]
    public_hash: str
    private_hash: str
    report: dict[str, Any]
    asset_refs: tuple[str, ...]


class LessonPackageValidator:
    def validate_formal_runtime_package(
        self,
        *,
        payload: Mapping[str, Any],
        build_item_id: str,
        course_id: str,
        course_version: str,
        target_fingerprint: str,
        teaching_brief: Mapping[str, Any],
        teaching_brief_sha256: str,
        source_course_content_sha256: str,
    ) -> dict[str, Any]:
        expected = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "authority": "mira_backend_candidate_only",
            "buildItemId": build_item_id,
            "courseId": course_id,
            "courseVersion": course_version,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": source_course_content_sha256,
            "teachingBriefSha256": teaching_brief_sha256,
            "teachingBrief": dict(teaching_brief),
            "studentLaunchEligible": False,
        }
        if dict(payload) != expected:
            self._fail(
                "formal_runtime_package_invalid",
                "Formal Runtime package authority is not exact",
                "package",
            )
        if any(
            re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in (
                target_fingerprint,
                teaching_brief_sha256,
                source_course_content_sha256,
            )
        ) or hashlib.sha256(
            json.dumps(
                teaching_brief,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest() != teaching_brief_sha256:
            self._fail(
                "formal_runtime_package_invalid",
                "Formal Runtime package evidence digest is invalid",
                "package",
            )
        forbidden = {
            "scenes",
            "actions",
            "html",
            "script",
            "sampleMode",
            "activeRelease",
            "published",
        }
        if forbidden.intersection(payload):
            self._fail(
                "formal_runtime_package_authority_leak",
                "Formal Runtime package attempted legacy or publication authority",
                "package",
            )
        return {
            "valid": True,
            "contractVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "candidateOnly": True,
            "legacyLessonPackageCompiled": False,
            "studentLaunchEligible": False,
        }

    """Compile an untrusted OpenMAIC source into a non-executable Mira package."""

    def compile(
        self,
        *,
        source: Mapping[str, Any],
        course: Mapping[str, Any],
        source_hash: str,
    ) -> CompiledLessonPackage:
        # New classroom publication is intent-only. OpenMAIC may choose the
        # teaching copy and a small set of named product templates, but it may
        # not ship renderer code, canvas geometry, actions, scoring rules, or
        # answers. The host compiles the intent into the immutable runtime
        # package below.
        if source.get("schemaVersion") != CLASSROOM_INTENT_SOURCE_SCHEMA:
            self._fail(
                "unsupported_classroom_source_schema",
                "Only structured classroom intent sources can be published",
                "source.schemaVersion",
            )
        return self._compile_structured_intent(
            source=source,
            course=course,
            source_hash=source_hash,
        )

        # Kept below temporarily as a parser reference for already persisted
        # source artifacts. It is intentionally unreachable: legacy raw
        # canvas/HTML classroom sources have no publication path.
        dsl_version = str(source.get("dslVersion") or "").strip()
        if dsl_version not in SUPPORTED_OPENMAIC_DSL_VERSIONS:
            self._fail(
                "unsupported_openmaic_dsl_version",
                "OpenMAIC DSL version is not explicitly supported",
                "source.dslVersion",
            )
        if (
            source.get("status") != "unverified"
            or source.get("publicationEligible") is not False
            or source.get("authoritativeAnswersProvided") is not False
        ):
            self._fail(
                "invalid_classroom_authority",
                "Classroom source attempted to claim publication or answer authority",
                "source",
            )
        self._validate_source_boundary(source, course)
        review = self._teaching_review(source)
        if review.get("passed") is not True or review.get("issues") != []:
            self._fail(
                "classroom_teaching_review_failed",
                "Independent teaching review did not pass cleanly",
                "source.generationMeta.teachingReview",
            )

        classroom = source.get("classroom")
        if not isinstance(classroom, Mapping):
            self._fail("invalid_classroom_source", "classroom must be an object", "classroom")
        content = self._course_content(course)
        questions = content.get("questions")
        if not isinstance(questions, list) or not questions:
            self._fail(
                "invalid_classroom_course",
                "Published course has no authoritative questions",
                "course.content.questions",
            )
        question_ids = {
            str(item.get("id") or "")
            for item in questions
            if isinstance(item, Mapping)
        }
        if len(question_ids) != len(questions) or "" in question_ids:
            self._fail(
                "invalid_classroom_course",
                "Published course question IDs are invalid",
                "course.content.questions",
            )
        guided_ids, independent_ids = self._practice_roles(content, question_ids)
        raw_scenes = classroom.get("scenes")
        if not isinstance(raw_scenes, list) or not 1 <= len(raw_scenes) <= 8:
            self._fail(
                "invalid_classroom_scenes",
                "Classroom must contain one through eight scenes",
                "classroom.scenes",
            )

        scene_ids: set[str] = set()
        asset_refs: set[str] = set()
        interactions: dict[str, dict[str, Any]] = {}
        scenes: list[dict[str, Any]] = []
        for index, raw_scene in enumerate(raw_scenes):
            scene = self._scene(
                raw_scene,
                index=index,
                question_ids=question_ids,
                guided_ids=guided_ids,
                independent_ids=independent_ids,
                asset_refs=asset_refs,
                interactions=interactions,
            )
            if scene["id"] in scene_ids:
                self._fail(
                    "duplicate_classroom_scene_id",
                    "Classroom scene IDs must be unique",
                    f"classroom.scenes[{index}].id",
                )
            scene_ids.add(scene["id"])
            scenes.append(scene)

        package_id = f"lesson_pkg_{source_hash[:24]}"
        public_payload = {
            "schemaVersion": LESSON_PACKAGE_SCHEMA,
            "id": package_id,
            "version": 1,
            "title": self._text(
                classroom.get("title") or course.get("title"),
                "classroom.title",
                160,
            ),
            "language": self._text(
                classroom.get("language") or "zh-CN",
                "classroom.language",
                20,
            ),
            "estimatedMinutes": self._integer(
                classroom.get("estimatedMinutes")
                or content.get("estimatedMinutes")
                or 10,
                "classroom.estimatedMinutes",
                minimum=3,
                maximum=45,
            ),
            "sourceCourse": {
                "id": str(course["id"]),
                "version": str(course["version"]),
                "gradeCode": str(course["grade_code"]),
                "subject": str(course["subject"]),
                "nodeCode": str(course["node_code"]),
            },
            "scenes": scenes,
            "assetRefs": sorted(asset_refs),
            "authority": {
                "curriculum": "published_learning_course",
                "assessment": "server_reference_only",
                "sourceArtifactHash": source_hash,
            },
        }
        private_payload = {
            "schemaVersion": LESSON_PACKAGE_PRIVATE_SCHEMA,
            "packageId": package_id,
            "packageVersion": 1,
            "interactions": interactions,
            "assessmentAuthority": {
                "courseId": str(course["id"]),
                "courseVersion": str(course["version"]),
                "endpoint": "learning_session_answer",
            },
        }
        self._reject_answer_fields(public_payload, path="package")
        self._reject_practice_answer_disclosure(
            public_payload,
            questions=questions,
            practice_ids=set(guided_ids) | set(independent_ids),
        )
        public_json = self._encode(public_payload)
        private_json = self._encode(private_payload)
        public_hash = hashlib.sha256(public_json.encode("utf-8")).hexdigest()
        private_hash = hashlib.sha256(private_json.encode("utf-8")).hexdigest()
        return CompiledLessonPackage(
            public_payload=public_payload,
            private_payload=private_payload,
            public_hash=public_hash,
            private_hash=private_hash,
            report={
                "publishable": True,
                "compilerVersion": LESSON_PACKAGE_COMPILER_VERSION,
                "dslVersion": dsl_version,
                "checks": [
                    "published_course_boundary",
                    "openmaic_dsl_allowlist",
                    "independent_teaching_review",
                    "scene_action_allowlists",
                    "question_reference_integrity",
                    "unsafe_html_and_url_rejection",
                    "public_answer_field_rejection",
                    "practice_answer_disclosure_scan",
                    "asset_reference_only",
                ],
                "sceneCount": len(scenes),
                "assetCount": len(asset_refs),
            },
            asset_refs=tuple(sorted(asset_refs)),
        )

    def _compile_structured_intent(
        self,
        *,
        source: Mapping[str, Any],
        course: Mapping[str, Any],
        source_hash: str,
    ) -> CompiledLessonPackage:
        self._exact_keys(
            source,
            {
                "schemaVersion",
                "dslVersion",
                "generator",
                "requestId",
                "provider",
                "model",
                "status",
                "publicationEligible",
                "authoritativeAnswersProvided",
                "sourceAuthority",
                "gradeCode",
                "subject",
                "skillBoundary",
                "classroom",
                "generationMeta",
            },
            "source",
        )
        dsl_version = str(source.get("dslVersion") or "").strip()
        if dsl_version not in SUPPORTED_OPENMAIC_DSL_VERSIONS:
            self._fail(
                "unsupported_openmaic_dsl_version",
                "OpenMAIC DSL version is not explicitly supported",
                "source.dslVersion",
            )
        if (
            source.get("generator") != "openmaic"
            or source.get("status") != "unverified"
            or source.get("publicationEligible") is not False
            or source.get("authoritativeAnswersProvided") is not False
            or source.get("sourceAuthority") != "openmaic_generation_untrusted"
        ):
            self._fail(
                "invalid_classroom_authority",
                "Classroom intent attempted to claim renderer, publication, or answer authority",
                "source",
            )
        self._validate_source_boundary(source, course)
        review = self._teaching_review(source)
        if review.get("passed") is not True or review.get("issues") != []:
            self._fail(
                "classroom_teaching_review_failed",
                "Independent teaching review did not pass cleanly",
                "source.generationMeta.teachingReview",
            )

        classroom = source.get("classroom")
        if not isinstance(classroom, Mapping):
            self._fail("invalid_classroom_source", "classroom must be an object", "classroom")
        self._exact_keys(classroom, {"id", "title", "language", "intent"}, "classroom")
        intent = classroom.get("intent")
        if not isinstance(intent, Mapping):
            self._fail(
                "invalid_classroom_intent",
                "classroom.intent must be an object",
                "classroom.intent",
            )
        self._exact_keys(
            intent,
            {
                "schemaVersion",
                "layoutTemplate",
                "widgetTemplate",
                "assetBrief",
                "misconceptions",
                "teach",
                "demo",
                "guided",
                "independent",
                "recap",
                "gameRules",
            },
            "classroom.intent",
        )
        if intent.get("schemaVersion") != CLASSROOM_INTENT_SCHEMA:
            self._fail(
                "unsupported_classroom_intent_schema",
                "Classroom intent schema is not supported",
                "classroom.intent.schemaVersion",
            )
        self._reject_structured_intent_fields(intent, path="classroom.intent")

        layout_template = self._identifier(
            intent.get("layoutTemplate"),
            "classroom.intent.layoutTemplate",
        )
        widget_template = self._identifier(
            intent.get("widgetTemplate"),
            "classroom.intent.widgetTemplate",
        )
        if layout_template not in _LAYOUT_TEMPLATES:
            self._fail(
                "unsupported_classroom_layout_template",
                "Classroom layout template is not enabled",
                "classroom.intent.layoutTemplate",
            )
        if widget_template not in _WIDGET_TEMPLATES:
            self._fail(
                "unsupported_classroom_widget_template",
                "Classroom widget template is not enabled",
                "classroom.intent.widgetTemplate",
            )

        content = self._course_content(course)
        questions = content.get("questions")
        if not isinstance(questions, list) or len(questions) != 5:
            self._fail(
                "invalid_classroom_course",
                "Published course must contain exactly five authoritative questions",
                "course.content.questions",
            )
        by_id = {
            str(question.get("id") or ""): question
            for question in questions
            if isinstance(question, Mapping)
        }
        if len(by_id) != len(questions) or "" in by_id:
            self._fail(
                "invalid_classroom_course",
                "Published course question IDs are invalid",
                "course.content.questions",
            )
        guided_ids, independent_ids = self._practice_roles(content, set(by_id))
        expected_guided_type = (
            "sequence"
            if widget_template == "sort_order.v1"
            else "single_choice"
        )
        incompatible_guided = [
            question_id
            for question_id in guided_ids
            if str(by_id[question_id].get("type") or "") != expected_guided_type
        ]
        if incompatible_guided:
            self._fail(
                "classroom_widget_question_type_mismatch",
                "The classroom widget does not support the guided question types",
                "classroom.intent.widgetTemplate",
            )
        teaching_flow = content.get("teachingFlow")
        demo_id = str(teaching_flow.get("demoQuestionId") or "")
        demo_question = by_id.get(demo_id)
        if demo_question is None:
            self._fail(
                "invalid_classroom_course",
                "Published course demonstration question is missing",
                "course.content.teachingFlow.demoQuestionId",
            )

        teach = self._intent_phase(intent.get("teach"), role="teach", require_points=True)
        demo = self._intent_phase(intent.get("demo"), role="demo", require_points=True)
        guided = self._intent_phase(
            intent.get("guided"),
            role="guided",
            expected_refs=guided_ids,
        )
        independent = self._intent_phase(
            intent.get("independent"),
            role="independent",
            expected_refs=independent_ids,
        )
        recap = self._intent_phase(intent.get("recap"), role="recap", require_points=True)
        game_rules = self._intent_game_rules(intent.get("gameRules"))
        self._validate_course_teaching_alignment(
            content=content,
            demo_question=demo_question,
            teach=teach,
            demo=demo,
            guided=guided,
            independent=independent,
            recap=recap,
        )
        self._validate_game_rules_for_widget(
            game_rules=game_rules,
            widget_template=widget_template,
        )
        asset_brief = self._intent_asset_brief(intent.get("assetBrief"))
        misconceptions = intent.get("misconceptions")
        if not isinstance(misconceptions, list) or not 1 <= len(misconceptions) <= 3:
            self._fail(
                "invalid_classroom_misconceptions",
                "Intent misconceptions must contain one through three items",
                "classroom.intent.misconceptions",
            )
        misconceptions = [
            self._text(item, f"classroom.intent.misconceptions[{index}]", 240)
            for index, item in enumerate(misconceptions)
        ]
        if len(set(misconceptions)) != len(misconceptions):
            self._fail(
                "invalid_classroom_misconceptions",
                "Intent misconceptions must be unique",
                "classroom.intent.misconceptions",
            )
        if re.search(r"(?:已经|完全|全部|都).{0,5}(?:掌握|学会|会了)", recap["sayText"]):
            self._fail(
                "classroom_recap_overclaims_mastery",
                "Recap must not claim mastery before independent evidence is evaluated",
                "classroom.intent.recap.sayText",
            )
        self._validate_gold_boundary(
            course=course,
            layout_template=layout_template,
            widget_template=widget_template,
            phases=(teach, demo, guided, independent, recap),
        )
        visual_aids, fulfilled_asset_brief_ids = self._controlled_visual_aids(
            course=course,
            content=content,
            teach=teach,
            asset_brief=asset_brief,
        )

        def actions(
            scene_id: str,
            *,
            narration: str = "",
            interaction_ref: str = "",
            focus_targets: Sequence[str] = (),
        ):
            result: list[dict[str, Any]] = []
            ordered_focus_targets = tuple(dict.fromkeys(focus_targets))
            if ordered_focus_targets:
                result.append(
                    {
                        "id": f"{scene_id}:focus:{ordered_focus_targets[0]}",
                        "type": "focus",
                        "targetId": ordered_focus_targets[0],
                    }
                )
            if narration:
                result.append(
                    {
                        "id": f"{scene_id}:narrate",
                        "type": "narrate",
                        "text": narration,
                    }
                )
            for target_id in ordered_focus_targets[1:]:
                result.append(
                    {
                        "id": f"{scene_id}:focus:{target_id}",
                        "type": "focus",
                        "targetId": target_id,
                    }
                )
            if interaction_ref:
                result.append(
                    {
                        "id": f"{scene_id}:interact",
                        "type": "await_interaction",
                        "interactionRef": interaction_ref,
                    }
                )
            elif scene_id != "scene-recap":
                result.append(
                    {
                        "id": f"{scene_id}:continue",
                        "type": "await_continue",
                    }
                )
            result.append({"id": f"{scene_id}:complete", "type": "complete_scene"})
            return result

        teach_blocks = [
            {
                "id": "teach-copy",
                "type": "text",
                "text": teach["sayText"],
                "styleToken": "teacher",
            },
            *[
                {
                    "id": f"teach-point-{index + 1}",
                    "type": "text",
                    "text": point,
                    "styleToken": "key_point",
                }
                for index, point in enumerate(teach["keyPoints"])
            ],
        ]
        focus_items = self._focus_items(course=course, key_points=teach["keyPoints"])
        teach_template_data: dict[str, Any] = {}
        if layout_template == "phonics_focus.v1":
            teach_template_data["focusItems"] = focus_items
        if visual_aids:
            teach_template_data["visualAids"] = visual_aids
        demo_prompt = self._text(
            demo_question.get("prompt"),
            "course.content.questions.demo.prompt",
            600,
        )
        demo_explanation = self._text(
            demo_question.get("explanation"),
            "course.content.questions.demo.explanation",
            800,
        )
        guided_ref = "guided:scene-guided"
        quiz_ref = "quiz:scene-independent"
        scenes = [
            {
                "id": "scene-teach",
                "type": "slide",
                "order": 1,
                "phaseRole": "teach",
                "title": teach["title"],
                "layoutTemplate": layout_template,
                "blocks": teach_blocks,
                "templateData": teach_template_data,
                "actions": actions(
                    "scene-teach",
                    narration=teach["sayText"],
                    focus_targets=tuple(
                        block["id"]
                        for block in teach_blocks
                        if block.get("styleToken") == "key_point"
                    ) or ("teach-copy",),
                ),
            },
            {
                "id": "scene-demo",
                "type": "slide",
                "order": 2,
                "phaseRole": "demo",
                "title": demo["title"],
                "layoutTemplate": "worked_example.v1",
                "blocks": [
                    {
                        "id": "demo-copy",
                        "type": "text",
                        "text": demo["sayText"],
                        "styleToken": "teacher",
                    },
                    {
                        "id": "demo-prompt",
                        "type": "text",
                        "text": demo_prompt,
                        "styleToken": "question",
                    },
                    {
                        "id": "demo-explanation",
                        "type": "text",
                        "text": demo_explanation,
                        "styleToken": "worked_answer",
                    },
                ],
                "templateData": {
                    "questionId": demo_id,
                    "prompt": demo_prompt,
                    "explanation": demo_explanation,
                },
                "actions": actions(
                    "scene-demo",
                    narration=demo["sayText"],
                    focus_targets=("demo-prompt", "demo-explanation"),
                ),
            },
            {
                "id": "scene-guided",
                "type": "interactive",
                "order": 3,
                "phaseRole": "guided",
                "title": guided["title"],
                "widgetTemplate": widget_template,
                "templateId": widget_template,
                "interactionRef": guided_ref,
                "questionRefs": list(guided_ids),
                "instructions": guided["sayText"],
                "gameRules": game_rules,
                "templateData": {
                    "questionRefs": list(guided_ids),
                    "questionSource": "session_questions",
                    "stateContract": {
                        "initial": "awaiting_answer",
                        "transitions": [
                            "awaiting_answer->answered",
                            "answered->retry_or_next",
                            "all_guided_evaluated->completed",
                        ],
                        "completion": "guided_questions_evaluated",
                    },
                },
                "actions": actions(
                    "scene-guided",
                    narration=guided["sayText"],
                    interaction_ref=guided_ref,
                ),
            },
            {
                "id": "scene-independent",
                "type": "quiz",
                "order": 4,
                "phaseRole": "independent",
                "title": independent["title"],
                "mode": "independent",
                "interactionRef": quiz_ref,
                "questionRefs": list(independent_ids),
                "instructions": independent["sayText"],
                "templateData": {
                    "questionRefs": list(independent_ids),
                    "questionSource": "session_questions",
                },
                "actions": actions(
                    "scene-independent",
                    narration=independent["sayText"],
                    interaction_ref=quiz_ref,
                ),
            },
            {
                "id": "scene-recap",
                "type": "recap",
                "order": 5,
                "phaseRole": "recap",
                "title": recap["title"],
                "sayText": recap["sayText"],
                "keyPoints": recap["keyPoints"],
                "actions": actions("scene-recap", narration=recap["sayText"]),
            },
        ]
        package_id = f"lesson_pkg_{source_hash[:24]}"
        public_payload = {
            "schemaVersion": LESSON_PACKAGE_SCHEMA,
            "id": package_id,
            "version": 1,
            "title": self._text(
                classroom.get("title") or course.get("title"),
                "classroom.title",
                160,
            ),
            "language": self._text(classroom.get("language") or "zh-CN", "classroom.language", 20),
            "estimatedMinutes": self._integer(
                source.get("skillBoundary", {}).get("estimatedMinutes") or 10,
                "source.skillBoundary.estimatedMinutes",
                minimum=3,
                maximum=45,
            ),
            "sourceCourse": {
                "id": str(course["id"]),
                "version": str(course["version"]),
                "gradeCode": str(course["grade_code"]),
                "subject": str(course["subject"]),
                "nodeCode": str(course["node_code"]),
            },
            "pedagogy": {
                "sequence": ["teach", "demo", "guided", "independent", "recap"],
                "teachBeforePractice": True,
            },
            "learningMetadata": {
                "gradeBand": str(course["grade_code"]),
                "subject": str(course["subject"]),
                "objectives": [
                    self._text(
                        item,
                        f"source.skillBoundary.learningObjectives[{index}]",
                        240,
                    )
                    for index, item in enumerate(
                        source.get("skillBoundary", {}).get("learningObjectives") or []
                    )
                ],
                "prerequisites": [
                    self._text(
                        item,
                        f"source.skillBoundary.prerequisiteSkills[{index}]",
                        240,
                    )
                    for index, item in enumerate(
                        source.get("skillBoundary", {}).get("prerequisiteSkills") or []
                    )
                ],
                "misconceptions": misconceptions,
                "masteryThreshold": {
                    "policy": "independent_all_correct_v1",
                    "evidenceCount": 2,
                    "requiredCorrect": 2,
                    "claimScope": "this_lesson_only",
                },
            },
            # An asset brief is a production request, not a student asset. It
            # is deliberately quarantined in the source artifact. Required
            # requests must be fulfilled by a real media asset or one of the
            # controlled visual-aid templates above before compilation can
            # succeed; unresolved briefs are never advertised to students.
            "assetBrief": [],
            "scenes": scenes,
            "assetRefs": [],
            "authority": {
                "curriculum": "published_learning_course",
                "assessment": "server_reference_only",
                "sourceArtifactHash": source_hash,
            },
        }
        private_payload = {
            "schemaVersion": LESSON_PACKAGE_PRIVATE_SCHEMA,
            "packageId": package_id,
            "packageVersion": 1,
            "interactions": {
                guided_ref: {
                    "templateId": widget_template,
                    "mode": "guided",
                    "questionRefs": list(guided_ids),
                },
                quiz_ref: {
                    "templateId": "server_quiz.v1",
                    "mode": "independent",
                    "questionRefs": list(independent_ids),
                },
            },
            "assessmentAuthority": {
                "courseId": str(course["id"]),
                "courseVersion": str(course["version"]),
                "endpoint": "learning_session_answer",
            },
        }
        self._reject_answer_fields(public_payload, path="package")
        self._reject_practice_answer_disclosure(
            public_payload,
            questions=questions,
            practice_ids=set(guided_ids) | set(independent_ids),
        )
        public_json = self._encode(public_payload)
        private_json = self._encode(private_payload)
        return CompiledLessonPackage(
            public_payload=public_payload,
            private_payload=private_payload,
            public_hash=hashlib.sha256(public_json.encode("utf-8")).hexdigest(),
            private_hash=hashlib.sha256(private_json.encode("utf-8")).hexdigest(),
            report={
                "publishable": True,
                "compilerVersion": LESSON_PACKAGE_COMPILER_VERSION,
                "dslVersion": dsl_version,
                "sourceMode": "structured_intent_only",
                "checks": [
                    "published_course_boundary",
                    "openmaic_intent_schema",
                    "independent_teaching_review",
                    "teach_before_practice_sequence",
                    "controlled_layout_template",
                    "controlled_spotlight_actions",
                    "controlled_widget_template",
                    "interactive_state_transition_required",
                    "authoritative_question_role_integrity",
                    "server_answer_authority_only",
                    "independent_mastery_evidence_two_of_two",
                    "recap_no_mastery_claim",
                    "asset_brief_no_url_or_path",
                    "required_asset_brief_fulfilled",
                    "controlled_visual_aids_only",
                    "grade_one_pinyin_aoe_gate",
                ],
                "sceneCount": 5,
                "sourceAssetBriefCount": len(asset_brief),
                "fulfilledAssetBriefCount": len(fulfilled_asset_brief_ids),
                "controlledVisualAidCount": len(visual_aids),
            },
            asset_refs=(),
        )

    def _intent_phase(
        self,
        value: object,
        *,
        role: str,
        require_points: bool = False,
        expected_refs: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        path = f"classroom.intent.{role}"
        if not isinstance(value, Mapping):
            self._fail("invalid_classroom_intent_phase", "Intent phase must be an object", path)
        allowed = {"title", "sayText", "keyPoints"}
        if expected_refs is not None:
            allowed.add("questionRefs")
        self._exact_keys(value, allowed, path)
        points = value.get("keyPoints")
        if not isinstance(points, list) or len(points) > 3 or (require_points and not points):
            self._fail(
                "invalid_classroom_intent_phase",
                "Intent keyPoints have an invalid size",
                f"{path}.keyPoints",
            )
        normalized = {
            "title": self._text(value.get("title"), f"{path}.title", 160),
            "sayText": self._text(
                value.get("sayText"),
                f"{path}.sayText",
                1200 if role == "teach" else 1000,
            ),
            "keyPoints": [
                self._text(point, f"{path}.keyPoints[{index}]", 240)
                for index, point in enumerate(points)
            ],
        }
        if len(set(normalized["keyPoints"])) != len(normalized["keyPoints"]):
            self._fail(
                "invalid_classroom_intent_phase",
                "Intent keyPoints must be unique",
                f"{path}.keyPoints",
            )
        if expected_refs is not None:
            refs = value.get("questionRefs")
            if not isinstance(refs, list) or [str(item) for item in refs] != list(expected_refs):
                self._fail(
                    "classroom_question_role_mismatch",
                    "Intent question references do not match the authoritative teaching roles",
                    f"{path}.questionRefs",
                )
            normalized["questionRefs"] = list(expected_refs)
        return normalized

    def _intent_game_rules(self, value: object) -> dict[str, Any]:
        path = "classroom.intent.gameRules"
        if not isinstance(value, Mapping):
            self._fail("invalid_classroom_game_rules", "gameRules must be an object", path)
        self._exact_keys(
            value,
            {"goal", "instructions", "successCriterion", "maxAttempts", "feedbackMode"},
            path,
        )
        instructions = value.get("instructions")
        if not isinstance(instructions, list) or not 1 <= len(instructions) <= 3:
            self._fail(
                "invalid_classroom_game_rules",
                "gameRules.instructions must contain one through three steps",
                f"{path}.instructions",
            )
        attempts = self._integer(
            value.get("maxAttempts"),
            f"{path}.maxAttempts",
            minimum=2,
            maximum=2,
        )
        feedback = self._text(value.get("feedbackMode"), f"{path}.feedbackMode", 40)
        if feedback not in _GAME_FEEDBACK_MODES:
            self._fail(
                "unsupported_classroom_feedback_mode",
                "Game feedback mode is not enabled",
                f"{path}.feedbackMode",
            )
        return {
            "goal": self._text(value.get("goal"), f"{path}.goal", 240),
            "instructions": [
                self._text(item, f"{path}.instructions[{index}]", 240)
                for index, item in enumerate(instructions)
            ],
            "successCriterion": self._text(
                value.get("successCriterion"),
                f"{path}.successCriterion",
                240,
            ),
            "maxAttempts": attempts,
            "feedbackMode": feedback,
        }

    def _validate_course_teaching_alignment(
        self,
        *,
        content: Mapping[str, Any],
        demo_question: Mapping[str, Any],
        teach: Mapping[str, Any],
        demo: Mapping[str, Any],
        guided: Mapping[str, Any],
        independent: Mapping[str, Any],
        recap: Mapping[str, Any],
    ) -> None:
        flow = content.get("teachingFlow")
        if not isinstance(flow, Mapping):
            self._fail(
                "invalid_classroom_course",
                "Published course teaching flow is unavailable",
                "course.content.teachingFlow",
            )
        source_teach = flow.get("teach")
        source_recap = flow.get("recap")
        if not isinstance(source_teach, Mapping) or not isinstance(source_recap, Mapping):
            self._fail(
                "invalid_classroom_course",
                "Published course teaching flow is incomplete",
                "course.content.teachingFlow",
            )
        expected_points = [
            self._canonical_text(item) for item in source_teach.get("keyPoints") or []
        ]
        actual_points = [
            self._canonical_text(item) for item in teach.get("keyPoints") or []
        ]
        aligned = (
            self._canonical_text(teach.get("title"))
            == self._canonical_text(source_teach.get("title"))
            and self._canonical_text(teach.get("sayText"))
            == self._canonical_text(source_teach.get("sayText"))
            and actual_points == expected_points
            and self._canonical_text(demo.get("sayText"))
            == self._canonical_text(demo_question.get("explanation"))
            and self._canonical_text(recap.get("sayText"))
            == self._canonical_text(source_recap.get("sayText"))
            and guided.get("keyPoints") == []
            and independent.get("keyPoints") == []
        )
        if not aligned:
            self._fail(
                "classroom_course_teaching_mismatch",
                "Classroom presentation changed the validated course teaching",
                "classroom.intent",
            )

    def _validate_game_rules_for_widget(
        self,
        *,
        game_rules: Mapping[str, Any],
        widget_template: str,
    ) -> None:
        instructions = " ".join(
            str(item) for item in game_rules.get("instructions") or []
        )
        if re.search(r"反馈|feedback|wait", instructions, flags=re.IGNORECASE) is None:
            self._fail(
                "classroom_game_rules_mismatch",
                "Guided instructions must explain that server feedback follows submission",
                "classroom.intent.gameRules.instructions",
            )
        if widget_template == "sort_order.v1":
            return
        success = str(game_rules.get("successCriterion") or "")
        if re.search(
            r"说明|说出|解释|口述|输入|填写|写出|拖动|排序|explain|type|write|drag|sort",
            success,
            flags=re.IGNORECASE,
        ):
            self._fail(
                "classroom_game_rules_mismatch",
                "Choice interaction success criteria require an unsupported response mode",
                "classroom.intent.gameRules.successCriterion",
            )

    def _intent_asset_brief(self, value: object) -> list[dict[str, Any]]:
        path = "classroom.intent.assetBrief"
        if not isinstance(value, list) or len(value) > 4:
            self._fail(
                "invalid_classroom_asset_brief",
                "assetBrief must contain at most four items",
                path,
            )
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, Mapping):
                self._fail("invalid_classroom_asset_brief", "Asset brief must be an object", item_path)
            self._exact_keys(
                item,
                {"id", "kind", "purpose", "required", "deliveryMode"},
                item_path,
            )
            item_id = self._identifier(item.get("id"), f"{item_path}.id")
            if item_id in seen:
                self._fail(
                    "invalid_classroom_asset_brief",
                    "Asset brief IDs must be unique",
                    f"{item_path}.id",
                )
            seen.add(item_id)
            kind = self._text(item.get("kind"), f"{item_path}.kind", 20)
            delivery = self._text(
                item.get("deliveryMode"),
                f"{item_path}.deliveryMode",
                40,
            )
            if kind not in _ASSET_BRIEF_KINDS or delivery not in _ASSET_BRIEF_DELIVERY_MODES:
                self._fail(
                    "invalid_classroom_asset_brief",
                    "Asset brief kind or delivery mode is unsupported",
                    item_path,
                )
            required = item.get("required")
            if not isinstance(required, bool):
                self._fail(
                    "invalid_classroom_asset_brief",
                    "Asset brief required must be boolean",
                    f"{item_path}.required",
                )
            purpose = self._text(item.get("purpose"), f"{item_path}.purpose", 300)
            if re.search(r"(?:[a-z][a-z0-9+.-]*:|/|\\\\|\.\.)", purpose, re.I):
                self._fail(
                    "unsafe_classroom_asset_brief",
                    "Asset brief must not contain a URL or file path",
                    f"{item_path}.purpose",
                )
            result.append(
                {
                    "id": item_id,
                    "kind": kind,
                    "purpose": purpose,
                    "required": required,
                    "deliveryMode": delivery,
                }
            )
        return result

    def _validate_gold_boundary(
        self,
        *,
        course: Mapping[str, Any],
        layout_template: str,
        widget_template: str,
        phases: Sequence[Mapping[str, Any]],
    ) -> None:
        if not (
            str(course.get("grade_code")) == "primary_1"
            and str(course.get("subject")) == "chinese"
            and str(course.get("node_code")) == "pinyin_syllables"
        ):
            return
        if layout_template != "phonics_focus.v1" or widget_template != "listen_tap_choice.v1":
            self._fail(
                "classroom_gold_template_mismatch",
                "The first pinyin lesson requires the controlled phonics and listening templates",
                "classroom.intent",
            )
        teaching_text = " ".join(
            item
            for phase in phases[:2]
            for item in [
                str(phase.get("sayText") or ""),
                *[str(point) for point in phase.get("keyPoints") or []],
            ]
        )
        for vowel in ("a", "o", "e"):
            if not re.search(rf"(?:^|[^a-z]){vowel}(?:[^a-z]|$)", teaching_text, re.I):
                self._fail(
                    "classroom_gold_content_missing",
                    f"The first pinyin lesson must explicitly teach {vowel}",
                    "classroom.intent.teach",
                )
        if any(term in teaching_text for term in ("偏旁", "部首", "生字", "整体认读", "声母")):
            self._fail(
                "classroom_gold_boundary_violation",
                "The first pinyin lesson crossed into later-grade-one content",
                "classroom.intent",
            )

    def _focus_items(
        self,
        *,
        course: Mapping[str, Any],
        key_points: Sequence[str],
    ) -> list[dict[str, Any]]:
        if (
            str(course.get("grade_code")) == "primary_1"
            and str(course.get("subject")) == "chinese"
            and str(course.get("node_code")) == "pinyin_syllables"
        ):
            return [
                {"id": "vowel-a", "label": "a", "mouthCue": "嘴巴张大 a a a"},
                {"id": "vowel-o", "label": "o", "mouthCue": "嘴巴圆圆 o o o"},
                {"id": "vowel-e", "label": "e", "mouthCue": "嘴巴扁扁 e e e"},
            ]
        return [
            {"id": f"focus-{index + 1}", "label": point}
            for index, point in enumerate(key_points)
        ]

    def _controlled_visual_aids(
        self,
        *,
        course: Mapping[str, Any],
        content: Mapping[str, Any],
        teach: Mapping[str, Any],
        asset_brief: Sequence[Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
        """Compile production briefs into deterministic, non-executable aids.

        OpenMAIC may describe desired imagery, but it never gets renderer or
        asset authority. For the three grade-one math boundaries Mira owns a
        small, reviewed visual grammar. Other required briefs remain blocked
        until a real asset pipeline exists for their kind.
        """

        grade_code = str(course.get("grade_code") or "")
        subject = str(course.get("subject") or "")
        node_code = str(course.get("node_code") or "")
        is_primary_one_math = (
            grade_code == "primary_1"
            and subject == "math"
            and node_code in _PRIMARY_ONE_MATH_VISUAL_NODES
        )
        required = [item for item in asset_brief if item.get("required") is True]
        if required and not is_primary_one_math:
            self._fail(
                "required_classroom_asset_unfulfilled",
                "Required classroom assets have no approved production renderer",
                "classroom.intent.assetBrief",
            )
        if is_primary_one_math:
            unsupported = [
                item
                for item in required
                if item.get("kind") != "image"
                or item.get("deliveryMode") != "generated_asset"
            ]
            if unsupported:
                self._fail(
                    "required_classroom_asset_unfulfilled",
                    "Grade-one math currently fulfills required image briefs only through controlled visuals",
                    "classroom.intent.assetBrief",
                )

            if node_code == "addition_subtraction_20":
                aids = self._addition_subtraction_visual_aids(teach)
            elif node_code == "number_sense_20":
                aids = self._number_sense_visual_aids(content)
            else:
                aids = self._shapes_position_visual_aids()
            fulfilled = tuple(
                str(item.get("id"))
                for item in asset_brief
                if item.get("kind") == "image"
                and item.get("deliveryMode") == "generated_asset"
            )
            return aids, fulfilled

        # Optional production ideas do not become student-facing promises.
        return [], ()

    def _addition_subtraction_visual_aids(
        self,
        teach: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        text = str(teach.get("sayText") or "")
        examples: dict[str, tuple[int, int, int]] = {}
        for match in re.finditer(
            r"(?<!\d)(\d+)\s*(\+|-|加(?:上)?|减(?:去)?)\s*(\d+)"
            r"\s*(?:=|等于|是)\s*(\d+)(?!\d)",
            text,
        ):
            left_text, operator, right_text, result_text = match.groups()
            left, right, result = int(left_text), int(right_text), int(result_text)
            operation = "combine" if operator in {"+", "加", "加上"} else "take_away"
            expected = left + right if operation == "combine" else left - right
            if expected != result or any(value < 0 or value > 20 for value in (left, right, result)):
                self._fail(
                    "invalid_controlled_visual_aid",
                    "A controlled counter aid requires a valid equation within 20",
                    "course.content.teachingFlow.teach.sayText",
                )
            examples.setdefault(operation, (left, right, result))
        if set(examples) != {"combine", "take_away"}:
            self._fail(
                "required_classroom_asset_unfulfilled",
                "The addition and subtraction lesson needs one reviewed example for each counter aid",
                "course.content.teachingFlow.teach.sayText",
            )
        add_left, add_right, add_result = examples["combine"]
        sub_left, sub_right, sub_result = examples["take_away"]
        return [
            {
                "id": "visual-addition-combine",
                "kind": "math_counters.v1",
                "operation": "combine",
                "left": add_left,
                "right": add_right,
                "result": add_result,
                "caption": "把两部分合起来，就是加法。",
            },
            {
                "id": "visual-subtraction-take-away",
                "kind": "math_counters.v1",
                "operation": "take_away",
                "left": sub_left,
                "right": sub_right,
                "result": sub_result,
                "caption": "从原来的一组里去掉一部分，就是减法。",
            },
        ]

    def _number_sense_visual_aids(
        self,
        content: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        questions = [item for item in content.get("questions") or [] if isinstance(item, Mapping)]
        flow = content.get("teachingFlow")
        demo_id = str(flow.get("demoQuestionId") or "") if isinstance(flow, Mapping) else ""
        practice_text = " ".join(
            self._public_text(question)
            for question in questions
            if str(question.get("id") or "") != demo_id
        )
        practice_numbers = {
            int(value)
            for value in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", practice_text)
            if 0 <= int(value) <= 20
        }
        lower = next((value for value in range(4, 10) if value not in practice_numbers), None)
        upper = next((value for value in range(11, 21) if value not in practice_numbers), None)
        place_value = next(
            (
                value
                for value in range(11, 21)
                if value not in practice_numbers and value != upper
            ),
            None,
        )
        if lower is None or upper is None or place_value is None:
            self._fail(
                "required_classroom_asset_unfulfilled",
                "Number-sense visuals could not be separated safely from practice questions",
                "course.content.questions",
            )
        return [
            {
                "id": "visual-number-cross-tens",
                "kind": "number_compare.v1",
                "left": lower,
                "right": upper,
                "relation": "less_than",
                "caption": "十位不一样时，先比较十位。",
            },
            {
                "id": "visual-number-place-value",
                "kind": "place_value.v1",
                "value": place_value,
                "tens": place_value // 10,
                "ones": place_value % 10,
                "caption": "一捆表示一个十，单个小方块表示一个一。",
            },
        ]

    @staticmethod
    def _shapes_position_visual_aids() -> list[dict[str, Any]]:
        return [
            {
                "id": "visual-shape-family",
                "kind": "shape_gallery.v1",
                "items": [
                    {"shape": "circle", "label": "圆形"},
                    {"shape": "triangle", "label": "三角形"},
                    {"shape": "square", "label": "正方形"},
                    {"shape": "rectangle", "label": "长方形"},
                ],
                "caption": "看边和角的特点，认出常见平面图形。",
            },
            {
                "id": "visual-position-compass",
                "kind": "position_compass.v1",
                "labels": {
                    "up": "上",
                    "down": "下",
                    "left": "左",
                    "right": "右",
                },
                "caption": "先找观察中心，再说清上下左右。",
            },
        ]

    def _reject_structured_intent_fields(self, value: Any, *, path: str) -> None:
        forbidden = _ANSWER_KEYS | frozenset(
            {
                "html",
                "javascript",
                "canvas",
                "actions",
                "src",
                "url",
                "code",
                "script",
            }
        )
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._reject_structured_intent_fields(item, path=f"{path}[{index}]")
            return
        if not isinstance(value, Mapping):
            return
        normalized_forbidden = {
            str(item).casefold().replace("_", "") for item in forbidden
        }
        for key, child in value.items():
            if str(key).casefold().replace("_", "") in normalized_forbidden:
                self._fail(
                    "unsafe_classroom_intent_field",
                    "Classroom intent contains renderer code or answer authority",
                    f"{path}.{key}",
                )
            self._reject_structured_intent_fields(child, path=f"{path}.{key}")

    def _scene(
        self,
        value: object,
        *,
        index: int,
        question_ids: set[str],
        guided_ids: Sequence[str],
        independent_ids: Sequence[str],
        asset_refs: set[str],
        interactions: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        path = f"classroom.scenes[{index}]"
        if not isinstance(value, Mapping):
            self._fail("invalid_classroom_scene", "Scene must be an object", path)
        scene_type = str(value.get("type") or "")
        if scene_type not in _SCENE_TYPES:
            self._fail(
                "unsupported_classroom_scene",
                "Scene type is not enabled",
                f"{path}.type",
            )
        allowed_by_type = {
            "slide": {
                "id",
                "type",
                "order",
                "title",
                "blocks",
                "canvas",
                "actions",
            },
            "interactive": {
                "id",
                "type",
                "order",
                "title",
                "templateId",
                "interactionRef",
                "widgetType",
                "html",
                "questionRefs",
                "instructions",
                "sandboxPolicy",
                "actions",
            },
            "quiz": {
                "id",
                "type",
                "order",
                "title",
                "mode",
                "interactionRef",
                "questionRefs",
                "actions",
            },
            "recap": {
                "id",
                "type",
                "order",
                "title",
                "sayText",
                "keyPoints",
                "actions",
            },
            "video": {
                "id",
                "type",
                "order",
                "title",
                "assetRef",
                "posterRef",
                "captionsRef",
                "minWatchRatio",
                "actions",
            },
        }
        self._exact_keys(value, allowed_by_type[scene_type], path)
        scene_id = self._identifier(value.get("id"), f"{path}.id")
        order = self._integer(value.get("order"), f"{path}.order", minimum=1, maximum=8)
        if order != index + 1:
            self._fail(
                "invalid_classroom_scene_order",
                "Scene order must be contiguous",
                f"{path}.order",
            )
        scene: dict[str, Any] = {
            "id": scene_id,
            "type": scene_type,
            "order": order,
            "title": self._text(value.get("title"), f"{path}.title", 160),
        }
        target_ids: set[str] = set()
        interaction_ref = ""
        scene_assets: set[str] = set()
        if scene_type == "slide":
            blocks = value.get("blocks") or []
            if not isinstance(blocks, list) or len(blocks) > 24:
                self._fail(
                    "invalid_classroom_slide",
                    "Slide blocks must contain at most 24 items",
                    f"{path}.blocks",
                )
            normalized_blocks: list[dict[str, Any]] = []
            for block_index, block in enumerate(blocks):
                normalized = self._block(
                    block,
                    path=f"{path}.blocks[{block_index}]",
                    asset_refs=asset_refs,
                    scene_assets=scene_assets,
                )
                if normalized["id"] in target_ids:
                    self._fail(
                        "duplicate_classroom_block_id",
                        "Slide block IDs must be unique",
                        f"{path}.blocks[{block_index}].id",
                    )
                target_ids.add(normalized["id"])
                normalized_blocks.append(normalized)
            if normalized_blocks:
                scene["blocks"] = normalized_blocks
            canvas = value.get("canvas")
            if canvas is not None:
                normalized_canvas, canvas_targets, canvas_assets = self._canvas(
                    canvas,
                    path=f"{path}.canvas",
                )
                scene["canvas"] = normalized_canvas
                target_ids.update(canvas_targets)
                scene_assets.update(canvas_assets)
                asset_refs.update(canvas_assets)
            if not normalized_blocks and canvas is None:
                self._fail(
                    "invalid_classroom_slide",
                    "Slide requires blocks or a safe canvas",
                    path,
                )
        elif scene_type == "interactive":
            template_id = str(value.get("templateId") or "").strip()
            html = value.get("html")
            if template_id and template_id not in _TEMPLATES:
                self._fail(
                    "unsupported_classroom_template",
                    "Interactive template is not enabled",
                    f"{path}.templateId",
                )
            if not template_id and not isinstance(html, str):
                self._fail(
                    "invalid_classroom_interactive",
                    "Interactive scene requires safe inline HTML or a template fallback",
                    path,
                )
            interaction_ref = self._identifier(
                value.get("interactionRef"),
                f"{path}.interactionRef",
            )
            refs = self._question_refs(
                value.get("questionRefs") or [],
                question_ids=question_ids,
                path=f"{path}.questionRefs",
                allow_empty=True,
            )
            if interaction_ref in interactions:
                self._fail(
                    "duplicate_classroom_interaction_ref",
                    "Interaction references must be unique",
                    f"{path}.interactionRef",
                )
            interactions[interaction_ref] = {
                "templateId": template_id or None,
                "questionRefs": refs,
            }
            scene.update({"interactionRef": interaction_ref, "questionRefs": refs})
            if template_id:
                scene["templateId"] = template_id
            if isinstance(html, str):
                scene["html"] = self._interactive_html(html, path=f"{path}.html")
                widget_type = str(value.get("widgetType") or "").strip()
                if widget_type not in _WIDGET_TYPES:
                    self._fail(
                        "invalid_classroom_widget_type",
                        "Interactive HTML requires a supported widgetType",
                        f"{path}.widgetType",
                    )
                scene["widgetType"] = widget_type
                scene["sandboxPolicy"] = {
                    "iframeSandbox": "allow-scripts",
                    "csp": _INTERACTIVE_CSP,
                }
            instructions = self._optional_text(
                value.get("instructions"),
                f"{path}.instructions",
                500,
            )
            if instructions:
                scene["instructions"] = instructions
        elif scene_type == "quiz":
            mode = str(value.get("mode") or "")
            expected_by_mode = {
                "guided": list(guided_ids),
                "independent": list(independent_ids),
                "practice": [*guided_ids, *independent_ids],
            }
            if mode not in expected_by_mode:
                self._fail(
                    "invalid_classroom_quiz_mode",
                    "Quiz mode must be guided, independent, or practice",
                    f"{path}.mode",
                )
            expected = expected_by_mode[mode]
            refs = self._question_refs(
                value.get("questionRefs"),
                question_ids=question_ids,
                path=f"{path}.questionRefs",
                allow_empty=False,
            )
            if refs != expected:
                self._fail(
                    "classroom_question_role_mismatch",
                    "Quiz references do not exactly match its teaching role and order",
                    f"{path}.questionRefs",
                )
            interaction_ref = self._identifier(
                value.get("interactionRef") or f"quiz:{scene_id}",
                f"{path}.interactionRef",
            )
            interactions[interaction_ref] = {
                "templateId": "server_quiz.v1",
                "mode": mode,
                "questionRefs": refs,
            }
            scene.update(
                {
                    "mode": mode,
                    "questionRefs": refs,
                    "interactionRef": interaction_ref,
                }
            )
        elif scene_type == "recap":
            points = value.get("keyPoints") or []
            if not isinstance(points, list) or len(points) > 5:
                self._fail(
                    "invalid_classroom_recap",
                    "Recap keyPoints must be an array of at most five items",
                    f"{path}.keyPoints",
                )
            scene.update(
                {
                    "sayText": self._text(
                        value.get("sayText"),
                        f"{path}.sayText",
                        1000,
                    ),
                    "keyPoints": [
                        self._text(item, f"{path}.keyPoints[{item_index}]", 240)
                        for item_index, item in enumerate(points)
                    ],
                }
            )
        elif scene_type == "video":
            asset_ref = self._asset_ref(value.get("assetRef"), f"{path}.assetRef")
            scene_assets.add(asset_ref)
            asset_refs.add(asset_ref)
            scene["assetRef"] = asset_ref
            for key in ("posterRef", "captionsRef"):
                if value.get(key):
                    ref = self._asset_ref(value.get(key), f"{path}.{key}")
                    scene[key] = ref
                    scene_assets.add(ref)
                    asset_refs.add(ref)
            ratio = value.get("minWatchRatio")
            if ratio is not None:
                if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
                    self._fail(
                        "invalid_classroom_video",
                        "minWatchRatio must be numeric",
                        f"{path}.minWatchRatio",
                    )
                scene["minWatchRatio"] = max(0.0, min(float(ratio), 1.0))

        scene["actions"] = self._actions(
            value.get("actions") or [],
            path=f"{path}.actions",
            target_ids=target_ids,
            interaction_ref=interaction_ref,
            scene_assets=scene_assets,
        )
        return scene

    def _block(
        self,
        value: object,
        *,
        path: str,
        asset_refs: set[str],
        scene_assets: set[str],
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            self._fail("invalid_classroom_block", "Block must be an object", path)
        block_type = str(value.get("type") or "")
        if block_type not in _BLOCK_TYPES:
            self._fail("unsupported_classroom_block", "Block type is not enabled", path)
        allowed = {
            "text": {"id", "type", "text", "styleToken"},
            "shape": {"id", "type", "shape", "styleToken"},
            "image": {"id", "type", "assetRef", "alt", "styleToken"},
        }[block_type]
        self._exact_keys(value, allowed, path)
        result = {
            "id": self._identifier(value.get("id"), f"{path}.id"),
            "type": block_type,
        }
        if block_type == "text":
            result["text"] = self._text(value.get("text"), f"{path}.text", 2000)
        elif block_type == "shape":
            shape = str(value.get("shape") or "")
            if shape not in _SHAPES:
                self._fail("unsupported_classroom_shape", "Shape is not enabled", path)
            result["shape"] = shape
        else:
            ref = self._asset_ref(value.get("assetRef"), f"{path}.assetRef")
            result.update(
                {
                    "assetRef": ref,
                    "alt": self._text(value.get("alt"), f"{path}.alt", 300),
                }
            )
            asset_refs.add(ref)
            scene_assets.add(ref)
        if value.get("styleToken"):
            result["styleToken"] = self._identifier(
                value.get("styleToken"),
                f"{path}.styleToken",
            )
        return result

    def _actions(
        self,
        values: object,
        *,
        path: str,
        target_ids: set[str],
        interaction_ref: str,
        scene_assets: set[str],
    ) -> list[dict[str, Any]]:
        if not isinstance(values, list) or len(values) > 8:
            self._fail(
                "invalid_classroom_actions",
                "Actions must be an array of at most eight items",
                path,
            )
        result: list[dict[str, Any]] = []
        action_ids: set[str] = set()
        for index, value in enumerate(values):
            item_path = f"{path}[{index}]"
            if not isinstance(value, Mapping):
                self._fail("invalid_classroom_action", "Action must be an object", item_path)
            action_type = str(value.get("type") or "")
            if action_type not in _ACTION_TYPES:
                self._fail(
                    "unsupported_classroom_action",
                    "Action type is not enabled",
                    f"{item_path}.type",
                )
            allowed = {
                "narrate": {"id", "type", "text", "assetRef", "audioAssetRef"},
                "focus": {"id", "type", "targetId"},
                "play_media": {"id", "type", "assetRef"},
                "await_continue": {"id", "type"},
                "await_interaction": {"id", "type", "interactionRef"},
                "complete_scene": {"id", "type"},
            }[action_type]
            self._exact_keys(value, allowed, item_path)
            action_id = self._identifier(value.get("id"), f"{item_path}.id")
            if action_id in action_ids:
                self._fail(
                    "duplicate_classroom_action_id",
                    "Action IDs must be unique in a scene",
                    f"{item_path}.id",
                )
            action_ids.add(action_id)
            action: dict[str, Any] = {"id": action_id, "type": action_type}
            if action_type == "narrate":
                action["text"] = self._text(value.get("text"), f"{item_path}.text", 1500)
                source_ref = value.get("assetRef") or value.get("audioAssetRef")
                if source_ref:
                    ref = self._asset_ref(
                        source_ref,
                        f"{item_path}.assetRef",
                    )
                    if ref not in scene_assets:
                        self._fail(
                            "classroom_action_reference_mismatch",
                            "Narration asset is not declared by its scene",
                            f"{item_path}.assetRef",
                        )
                    action["audioAssetRef"] = ref
            elif action_type == "focus":
                target = self._identifier(value.get("targetId"), f"{item_path}.targetId")
                if target not in target_ids:
                    self._fail(
                        "classroom_action_reference_mismatch",
                        "Focus target does not exist in its scene",
                        f"{item_path}.targetId",
                    )
                action["targetId"] = target
            elif action_type == "play_media":
                ref = self._asset_ref(value.get("assetRef"), f"{item_path}.assetRef")
                if ref not in scene_assets:
                    self._fail(
                        "classroom_action_reference_mismatch",
                        "Media action asset is not declared by its scene",
                        f"{item_path}.assetRef",
                    )
                action["assetRef"] = ref
            elif action_type == "await_interaction":
                ref = self._identifier(
                    value.get("interactionRef"),
                    f"{item_path}.interactionRef",
                )
                if not interaction_ref or ref != interaction_ref:
                    self._fail(
                        "classroom_action_reference_mismatch",
                        "Interaction action does not reference its scene interaction",
                        f"{item_path}.interactionRef",
                    )
                action["interactionRef"] = ref
            result.append(action)
        completion_indexes = [
            index for index, action in enumerate(result) if action["type"] == "complete_scene"
        ]
        if completion_indexes and completion_indexes != [len(result) - 1]:
            self._fail(
                "invalid_classroom_action_order",
                "complete_scene must occur exactly once at the end",
                path,
            )
        if not completion_indexes:
            result.append(
                {
                    "id": f"complete:{len(result) + 1}",
                    "type": "complete_scene",
                }
            )
        return result

    def _validate_source_boundary(
        self,
        source: Mapping[str, Any],
        course: Mapping[str, Any],
    ) -> None:
        boundary = source.get("skillBoundary")
        if not isinstance(boundary, Mapping):
            self._fail(
                "classroom_boundary_mismatch",
                "Classroom source has no skill boundary",
                "source.skillBoundary",
            )
        expected = {
            "gradeCode": str(course["grade_code"]),
            "subject": str(course["subject"]),
            "skillId": str(course["node_code"]),
        }
        for key, value in expected.items():
            actual = source.get(key) if key in {"gradeCode", "subject"} else boundary.get(key)
            if actual != value:
                self._fail(
                    "classroom_boundary_mismatch",
                    f"Classroom source changed {key}",
                    f"source.{key}",
                )
        registered = next(
            (
                item
                for item in boundaries_for(expected["gradeCode"], expected["subject"])
                if item.skill_id == expected["skillId"]
            ),
            None,
        )
        if registered is None:
            self._fail(
                "classroom_skill_boundary_not_found",
                "Published course skill boundary is not registered",
                "source.skillBoundary.skillId",
            )
        registered_payload = registered.to_openmaic_payload()
        for key, expected_value in registered_payload.items():
            if boundary.get(key) != expected_value:
                self._fail(
                    "classroom_boundary_mismatch",
                    f"Classroom source changed skillBoundary.{key}",
                    f"source.skillBoundary.{key}",
                )
        extras = set(boundary) - set(registered_payload) - {"outcomeMode", "sessionKind"}
        if extras:
            self._fail(
                "classroom_boundary_mismatch",
                "Classroom source added unsupported skill-boundary fields",
                "source.skillBoundary",
            )
        if boundary.get("outcomeMode", "scored_deterministic") != "scored_deterministic":
            self._fail(
                "classroom_boundary_mismatch",
                "Classroom source changed skillBoundary.outcomeMode",
                "source.skillBoundary.outcomeMode",
            )
        if boundary.get("sessionKind", "lesson") != "lesson":
            self._fail(
                "classroom_boundary_mismatch",
                "Classroom source changed skillBoundary.sessionKind",
                "source.skillBoundary.sessionKind",
            )

    def _teaching_review(self, source: Mapping[str, Any]) -> Mapping[str, Any]:
        metadata = source.get("generationMeta")
        review = metadata.get("teachingReview") if isinstance(metadata, Mapping) else None
        if not isinstance(review, Mapping):
            review = source.get("teachingReview")
        if (
            not isinstance(review, Mapping)
            or not isinstance(review.get("passed"), bool)
            or not isinstance(review.get("issues"), list)
        ):
            self._fail(
                "classroom_teaching_review_missing",
                "Classroom source is missing an independent teaching review",
                "source.generationMeta.teachingReview",
            )
        return review

    def _practice_roles(
        self,
        content: Mapping[str, Any],
        question_ids: set[str],
    ) -> tuple[list[str], list[str]]:
        flow = content.get("teachingFlow")
        if not isinstance(flow, Mapping):
            self._fail(
                "invalid_classroom_course",
                "Course has no authoritative teaching flow",
                "course.content.teachingFlow",
            )
        guided = [str(item) for item in flow.get("guidedQuestionIds") or []]
        independent = [str(item) for item in flow.get("independentQuestionIds") or []]
        combined = [*guided, *independent]
        if (
            not guided
            or not independent
            or len(combined) != 4
            or len(set(combined)) != len(combined)
            or any(item not in question_ids for item in combined)
        ):
            self._fail(
                "invalid_classroom_course",
                "Course teaching-flow question roles are invalid",
                "course.content.teachingFlow",
            )
        return guided, independent

    def _question_refs(
        self,
        value: object,
        *,
        question_ids: set[str],
        path: str,
        allow_empty: bool,
    ) -> list[str]:
        if not isinstance(value, list) or (not allow_empty and not value) or len(value) > 5:
            self._fail(
                "invalid_classroom_question_refs",
                "questionRefs has an invalid size",
                path,
            )
        refs = [self._identifier(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if len(set(refs)) != len(refs) or any(item not in question_ids for item in refs):
            self._fail(
                "invalid_classroom_question_refs",
                "questionRefs contains an unknown or duplicate question",
                path,
            )
        return refs

    def _reject_answer_fields(self, value: Any, *, path: str) -> None:
        if isinstance(value, str):
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._reject_answer_fields(item, path=f"{path}[{index}]")
            return
        if not isinstance(value, Mapping):
            return
        for key, child in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).casefold())
            if normalized in _ANSWER_KEYS:
                self._fail(
                    "unsafe_classroom_field",
                    f"Classroom source contains forbidden field: {key}",
                    f"{path}.{key}",
                )
            self._reject_answer_fields(child, path=f"{path}.{key}")

    def _interactive_html(self, value: str, *, path: str) -> str:
        html = str(value or "").strip()
        if not html or len(html.encode("utf-8")) > 100_000:
            self._fail(
                "invalid_classroom_interactive",
                "Interactive HTML is missing or exceeds 100 KB",
                path,
            )
        inspector = _InteractiveHtmlInspector()
        try:
            inspector.feed(html)
            inspector.close()
        except Exception:
            self._fail(
                "unsafe_classroom_html",
                "Interactive HTML could not be parsed safely",
                path,
            )
        script = "\n".join(inspector.scripts)
        if _INTERACTIVE_FORBIDDEN_JS.search(script):
            inspector.errors.append("network, storage, navigation, or parent access is forbidden")
        if re.search(
            r"(?:src|href|url)\s*[=:]\s*['\"]\s*(?:https?:|//|javascript:)",
            html,
            re.IGNORECASE,
        ):
            inspector.errors.append("remote or executable resource reference is forbidden")
        if inspector.errors:
            self._fail(
                "unsafe_classroom_html",
                inspector.errors[0],
                path,
            )
        return html

    def _canvas(
        self,
        value: object,
        *,
        path: str,
    ) -> tuple[dict[str, Any], set[str], set[str]]:
        if not isinstance(value, Mapping):
            self._fail("invalid_classroom_canvas", "Canvas must be an object", path)
        if len(self._encode(dict(value)).encode("utf-8")) > 200_000:
            self._fail(
                "invalid_classroom_canvas",
                "Canvas exceeds 200 KB",
                path,
            )
        allowed_canvas = {
            "id",
            "elements",
            "background",
            "viewportSize",
            "viewportRatio",
            "theme",
            "type",
            "turningMode",
            "sectionTag",
        }
        self._exact_keys(value, allowed_canvas, path)
        elements = value.get("elements")
        if not isinstance(elements, list) or not 1 <= len(elements) <= 60:
            self._fail(
                "invalid_classroom_canvas",
                "Canvas must contain one through 60 elements",
                f"{path}.elements",
            )
        target_ids: set[str] = set()
        assets: set[str] = set()
        normalized_elements: list[dict[str, Any]] = []
        for index, item in enumerate(elements):
            element_path = f"{path}.elements[{index}]"
            if not isinstance(item, Mapping):
                self._fail("invalid_classroom_canvas", "Canvas element must be an object", element_path)
            element = dict(item)
            element_type = str(element.get("type") or "")
            if element_type not in {"text", "shape", "image"}:
                self._fail(
                    "unsupported_classroom_canvas_element",
                    "Canvas element type is not enabled",
                    f"{element_path}.type",
                )
            element_id = self._identifier(element.get("id"), f"{element_path}.id")
            if element_id in target_ids:
                self._fail(
                    "duplicate_classroom_canvas_element_id",
                    "Canvas element IDs must be unique",
                    f"{element_path}.id",
                )
            target_ids.add(element_id)
            if element.get("link") is not None:
                self._fail(
                    "unsafe_classroom_canvas_link",
                    "Canvas links are not allowed",
                    f"{element_path}.link",
                )
            declared_asset_refs: set[str] = set()
            for key in ("src", "assetRef", "mediaRef", "audioId"):
                if element.get(key) is None:
                    continue
                ref = self._asset_ref(element.get(key), f"{element_path}.{key}")
                element[key] = ref
                assets.add(ref)
                declared_asset_refs.add(ref)
            if len(declared_asset_refs) > 1:
                self._fail(
                    "invalid_classroom_canvas",
                    "Canvas element asset references disagree",
                    element_path,
                )
            self._validate_canvas_tree(element, path=element_path)
            normalized_elements.append(element)
        canvas = dict(value)
        canvas["elements"] = normalized_elements
        return canvas, target_ids, assets

    def _validate_canvas_tree(self, value: Any, *, path: str) -> None:
        if isinstance(value, str):
            if len(value) > 20_000:
                self._fail("invalid_classroom_canvas", "Canvas string is too long", path)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._validate_canvas_tree(item, path=f"{path}[{index}]")
            return
        if not isinstance(value, Mapping):
            return
        for key, child in value.items():
            normalized = str(key).casefold()
            if (
                normalized in {
                    "answer",
                    "analysis",
                    "script",
                    "url",
                    "html",
                    "href",
                    "link",
                    "action",
                    "formaction",
                    "poster",
                }
                or normalized.startswith("on")
            ):
                self._fail(
                    "unsafe_classroom_canvas_field",
                    f"Canvas contains forbidden field: {key}",
                    f"{path}.{key}",
                )
            if normalized in {"content", "text"} and isinstance(child, str):
                self._safe_rich_text(child, f"{path}.{key}")
            elif isinstance(child, str):
                if re.search(r"(?:https?|wss?|ftp):\s*//|javascript\s*:", child, re.I):
                    self._fail(
                        "unsafe_classroom_canvas_field",
                        "Canvas contains an executable or remote URL",
                        f"{path}.{key}",
                    )
                self._safe_text(child, f"{path}.{key}")
            self._validate_canvas_tree(child, path=f"{path}.{key}")

    def _safe_rich_text(self, value: str, path: str) -> None:
        class RichTextInspector(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.error: str | None = None

            def handle_starttag(self, tag, attrs):
                if tag.casefold() not in _RICH_TEXT_TAGS:
                    self.error = f"unsupported rich-text element <{tag}>"
                    return
                for key, attr_value in attrs:
                    normalized_key = str(key).casefold()
                    if normalized_key != "style":
                        self.error = f"unsupported rich-text attribute {key}"
                        return
                    for declaration in str(attr_value or "").split(";"):
                        if not declaration.strip():
                            continue
                        property_name, separator, property_value = declaration.partition(":")
                        if (
                            not separator
                            or property_name.strip().casefold() not in _SAFE_STYLE_PROPERTIES
                            or re.search(r"url\s*\(|expression\s*\(|@import", property_value, re.I)
                        ):
                            self.error = "unsafe rich-text style"
                            return

        inspector = RichTextInspector()
        inspector.feed(value)
        inspector.close()
        if inspector.error:
            self._fail("unsafe_classroom_canvas_html", inspector.error, path)

    def _reject_practice_answer_disclosure(
        self,
        package: Mapping[str, Any],
        *,
        questions: Sequence[object],
        practice_ids: set[str],
    ) -> None:
        text = self._canonical_text(self._public_text(package.get("scenes")))
        for question in questions:
            if not isinstance(question, Mapping) or str(question.get("id")) not in practice_ids:
                continue
            for answer in self._answer_values(question):
                canonical = self._canonical_text(answer)
                if len(canonical) >= 2 and self._explicit_answer_disclosure(
                    text,
                    canonical,
                ):
                    self._fail(
                        "classroom_answer_disclosure",
                        "Classroom teaching text appears to disclose a practice answer",
                        "package.scenes",
                    )

    @staticmethod
    def _explicit_answer_disclosure(text: str, answer: str) -> bool:
        """Detect an explicit answer claim without matching normal teaching.

        Numeric lessons legitimately say things such as "15就是1个十和5个一，
        20也是……". A loose marker-to-number window misclassified that sentence
        as an answer leak. Publication still rejects direct claims, but the
        relation must now be grammatical and adjacent to the answer.
        """

        escaped = re.escape(answer)
        boundary = r"(?!\d)" if answer.isdigit() else ""
        patterns = (
            rf"(?:答案|正确答案|正确选项|应为|应选|应该选|结果)"
            rf"(?:就是|是|为|应为|应选|应该是|应该为)?(?<!\d){escaped}{boundary}",
            rf"正确(?:的答案|的选项|的数|结果)?(?:就是|是|为)"
            rf"(?<!\d){escaped}{boundary}",
            rf"(?:选择|选项)(?:就是|是|为|应选|应该选)?"
            rf"(?<!\d){escaped}{boundary}",
        )
        return any(re.search(pattern, text) is not None for pattern in patterns)

    @staticmethod
    def _answer_values(question: Mapping[str, Any]) -> list[str]:
        answer = question.get("answer")
        values = answer if isinstance(answer, list) else [answer]
        if question.get("type") == "single_choice":
            labels = {
                str(choice.get("id")): str(choice.get("label") or "")
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping)
            }
            values.extend(labels.get(str(item)) for item in list(values))
        return [str(item) for item in values if item is not None and str(item).strip()]

    def _block_public_text(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for child in value for item in self._block_public_text(child)]
        if not isinstance(value, Mapping):
            return []
        return [item for child in value.values() for item in self._block_public_text(child)]

    def _public_text(self, value: Any) -> str:
        return " ".join(self._block_public_text(value))

    @staticmethod
    def _course_content(course: Mapping[str, Any]) -> dict[str, Any]:
        value = course.get("content_json")
        try:
            payload = json.loads(str(value or ""))
        except json.JSONDecodeError as exc:
            raise LessonPackageValidationError(
                "invalid_classroom_course",
                "Published course content is invalid",
                path="course.content_json",
            ) from exc
        if not isinstance(payload, dict):
            raise LessonPackageValidationError(
                "invalid_classroom_course",
                "Published course content is invalid",
                path="course.content_json",
            )
        return payload

    def _exact_keys(self, value: Mapping[str, Any], allowed: set[str], path: str) -> None:
        extras = set(value) - allowed
        if extras:
            self._fail(
                "unsafe_classroom_field",
                f"Unsupported classroom fields: {', '.join(sorted(extras))}",
                path,
            )

    def _identifier(self, value: object, path: str) -> str:
        text = self._text(value, path, 128)
        if not _ID_PATTERN.fullmatch(text):
            self._fail("invalid_classroom_id", "Identifier contains unsupported characters", path)
        return text

    def _asset_ref(self, value: object, path: str) -> str:
        ref = self._identifier(value, path)
        if not ref.startswith("asset_"):
            self._fail(
                "invalid_classroom_asset_ref",
                "Media must use an opaque assetRef",
                path,
            )
        return ref

    def _text(self, value: object, path: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text or len(text) > maximum:
            self._fail("invalid_classroom_text", "Text is missing or too long", path)
        self._safe_text(text, path)
        return text

    def _optional_text(self, value: object, path: str, maximum: int) -> str:
        if value is None or not str(value).strip():
            return ""
        return self._text(value, path, maximum)

    def _safe_text(self, value: str, path: str) -> None:
        if _UNSAFE_TEXT.search(value):
            self._fail(
                "unsafe_classroom_html",
                "HTML, script, or executable URL content is not allowed",
                path,
            )

    def _integer(
        self,
        value: object,
        path: str,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            self._fail("invalid_classroom_number", "Expected an integer", path)
        if not minimum <= value <= maximum:
            self._fail("invalid_classroom_number", "Integer is outside allowed range", path)
        return value

    @staticmethod
    def _canonical_text(value: object) -> str:
        return re.sub(r"[\W_]+", "", str(value or "").casefold())

    @staticmethod
    def _encode(value: Mapping[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _fail(code: str, message: str, path: str) -> None:
        raise LessonPackageValidationError(code, message, path=path)
