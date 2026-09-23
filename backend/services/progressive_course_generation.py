"""Versioned, lesson-bound generation independent of sealed boundary contracts.

The existing dynamic generation entry calls this module for explicit lesson IDs.
Candidates still require downstream package/publication acceptance; validation
here never re-labels an older course or awards a child mastery.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
from collections.abc import Mapping

from core.errors import ApiError
from core.security import now_ms

CONTRACT_VERSION = "mira.learning.progressive-generation.v1"
COURSE_SCHEMA = "mira.learning.progressive-course.v1"
BINDING_SCHEMA = "mira.learning.progressive-binding.v1"
VALIDATION_SCHEMA = "mira.learning.progressive-host-validation.v1"
BRIEF_SCHEMA = "mira.learning.progressive-generation-brief.v1"
INPUT_SCHEMA = "mira.openmaic.progressive-generation-input.v1"
VERIFY_SCHEMA = "mira.openmaic.progressive-verification-input.v1"
OUTPUT_SCHEMA = "mira.openmaic.progressive-result.v1"
GENERATION_CONTEXT_SCHEMA = "mira.learning.progressive-generation-context.v1"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "progressive-course.v1.json"


def _registry():
    from content import progressive_curriculum
    return progressive_curriculum


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _fail(code: str, message: str):
    raise ApiError(code, message, 409)


def lesson_binding(lesson_id: str) -> dict:
    registry = _registry()
    lesson = registry.lesson_by_id(lesson_id)
    identity = registry.curriculum_identity()
    return {"schemaVersion": BINDING_SCHEMA, "curriculumVersion": registry.CURRICULUM_VERSION,
            "lessonId": lesson_id, "identitySha256": identity["datasetSha256"],
            "lessonSha256": digest(lesson), "difficultyCode": "basic",
            "assessmentMode": lesson["assessmentMode"]}


def generation_brief(lesson_id: str, *, difficulty_code: str = "basic") -> dict:
    """Bind all provider instructions to a specific immutable registry lesson."""
    if difficulty_code != "basic":
        _fail("progressive_basic_required", "细课次须先生成基础课，巩固和进阶使用后续独立授权。")
    registry = _registry()
    lesson = registry.lesson_by_id(lesson_id)
    prerequisites = [registry.lesson_by_id(item) for item in registry.prerequisite_closure(lesson_id)]
    prior_knowledge = sorted({key for item in prerequisites for key in item["introducedKnowledgeIds"]})
    allowed = set(prior_knowledge) | set(lesson["introducedKnowledgeIds"])
    future = sorted({key for item in registry.all_lessons() if item["subject"] == lesson["subject"]
                     for key in item["introducedKnowledgeIds"]} - allowed)
    return {"schemaVersion": BRIEF_SCHEMA, "contractVersion": CONTRACT_VERSION,
            "binding": lesson_binding(lesson_id), "lesson": lesson,
            "prerequisiteLessonIds": [item["lessonId"] for item in prerequisites],
            "priorKnowledgeIds": prior_knowledge, "allowedKnowledgeIds": sorted(allowed),
            "mustNotDependOnKnowledgeIds": future,
            "sequencePolicy": ["teach", "example", "guided", "independent"],
            "autoMasteryEligible": lesson["assessmentMode"] == "objective",
            "manualConfirmationRequired": lesson["assessmentMode"] != "objective"}


def _strings(value, field, *, nonempty=True) -> list[str]:
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(value) != len(set(value))):
        _fail("progressive_invalid_evidence", f"{field} 必须是有效且不重复的标识列表。")
    return value


def _text(value, field) -> str:
    maximum = 128 if field.endswith(".id") else 6000
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("progressive_invalid_content", f"{field} 缺少有效文本。")
    return value


def _public_text(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _public_text(item)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"text", "prompt", "label", "sayText", "explanation", "hint", "title", "intro", "objective"}:
                yield from _public_text(item)
            elif isinstance(item, (list, Mapping)) and key not in {"progressiveLesson", "runtimeAuthoringScope", "evidence", "evaluation"}:
                yield from _public_text(item)


_PAST_FORMS = re.compile(r"\b(?:went|did|didn't|was|were|had|saw|ate|bought|came|played|visited|walked|watched|yesterday)\b", re.I)
_FUTURE_FORMS = re.compile(r"\b(?:will|won't|going\s+to|tomorrow)\b", re.I)


def _validate_language_scope(content: dict, brief: dict) -> None:
    lesson = brief["lesson"]
    constraints = lesson.get("constraints") or {}
    text = "\n".join(_public_text(content))
    if lesson["subject"] == "english":
        grammar = set(constraints.get("allowedGrammarCodes") or [])
        if "simple_past" not in grammar and _PAST_FORMS.search(text):
            _fail("progressive_future_grammar", "本课尚未学习过去时，不能使用 went、did 等过去时内容。")
        if not {"future_will", "future_going_to"} & grammar and _FUTURE_FORMS.search(text):
            _fail("progressive_future_grammar", "本课尚未学习将来时，不能依赖将来时内容。")
    # These scopes apply to explicitly declared question evidence. Ordinary
    # Chinese teacher instructions may contain letters in technical metadata.
    allowed_tokens = set(constraints.get("allowedLetters") or []) | set(constraints.get("allowedPinyin") or [])
    if allowed_tokens:
        for question in content.get("questions", []):
            evidence = question.get("evidence") or {}
            if evidence.get("kind") == "token_match":
                labels = {str(item.get("label") or "") for item in question.get("choices", [])}
                if not labels.issubset(allowed_tokens | set(constraints.get("introducedTokens") or [])
                                        | set(constraints.get("neutralDistractorTokens") or [])):
                    _fail("progressive_future_token", "题目使用了本课及前置课尚未引入的字母或拼音。")


_DECIMAL_LITERAL = r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_NUMERIC_CHOICE = re.compile(rf"[+-]?(?:{_DECIMAL_LITERAL}|[0-9]+/[0-9]+)")


def _numeric_choice_value(label: str) -> Fraction:
    label = label.strip()
    if len(label) > 100 or not _NUMERIC_CHOICE.fullmatch(label):
        _fail("progressive_invalid_numeric_evidence", "数学选项须是十进制数或简单分数。")
    try:
        return Fraction(label)
    except (ValueError, ZeroDivisionError):
        _fail("progressive_invalid_numeric_evidence", "数学选项须是有效数值，分母不能为零。")


def _numeric_value(expression: str, constraints: Mapping) -> Fraction:
    if not isinstance(expression, str) or len(expression) > 100:
        _fail("progressive_invalid_numeric_evidence", "缺少可复算的数学表达式。")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError):
        _fail("progressive_invalid_numeric_evidence", "数学表达式无效。")
    operators = {"add": ast.Add, "subtract": ast.Sub, "multiply": ast.Mult, "divide": ast.Div}
    allowed_operators = tuple(operators[name] for name in constraints.get("allowedOperations", []) if name in operators)
    low, high = constraints.get("minimumNumber"), constraints.get("maximumNumber")
    low = Fraction(str(low)) if low is not None else None
    high = Fraction(str(high)) if high is not None else None

    def calculate(node):
        if isinstance(node, ast.Expression):
            return calculate(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            # Read the original decimal token so the AST float cannot round it.
            literal = ast.get_source_segment(expression, node)
            if literal is None or not re.fullmatch(_DECIMAL_LITERAL, literal):
                _fail("progressive_invalid_numeric_evidence", "数学表达式只能包含普通十进制数。")
            value = Fraction(literal)
            if (low is not None and value < low) or (high is not None and value > high):
                _fail("progressive_number_out_of_scope", "题目数值超出当前课次范围。")
            return value
        if isinstance(node, ast.BinOp) and isinstance(node.op, allowed_operators):
            a, b = calculate(node.left), calculate(node.right)
            if isinstance(node.op, ast.Add): return a + b
            if isinstance(node.op, ast.Sub): return a - b
            if isinstance(node.op, ast.Mult): return a * b
            if not b: _fail("progressive_invalid_numeric_evidence", "不能除以零。")
            return a / b
        _fail("progressive_unregistered_scoring", "本课未登记此运算的确定性验收能力。")
    result = calculate(tree)
    if (low is not None and result < low) or (high is not None and result > high):
        _fail("progressive_number_out_of_scope", "题目结果超出当前课次范围。")
    return result


def _validate_question(question, *, lesson, allowed, introduced):
    if not isinstance(question, Mapping):
        _fail("progressive_invalid_question", "题目必须是对象。")
    for field in ("id", "prompt", "hint", "explanation"):
        _text(question.get(field), f"question.{field}")
    knowledge = set(_strings(question.get("knowledgeIds"), "question.knowledgeIds"))
    if not knowledge.issubset(allowed) or not knowledge & introduced:
        _fail("progressive_question_knowledge_out_of_scope", "题目必须检验本课知识，并只能依赖已学前置知识。")
    constraints = lesson.get("constraints") or {}
    evidence = question.get("evidence")
    if not isinstance(evidence, Mapping) or evidence.get("kind") not in constraints.get("assessmentEvidenceKinds", []):
        _fail("progressive_unregistered_scoring", "本课未明确登记此题目的验收能力。")
    if question.get("type") == "tap_objects":
        objects = question.get("objects")
        if evidence.get("kind") != "count_objects" or not isinstance(objects, list) or not 1 <= len(objects) <= 20:
            _fail("progressive_invalid_object_count", "逐物数数需要一至二十个明确的目标物体。")
        object_ids = []
        for item in objects:
            if (not isinstance(item, Mapping) or set(item) != {"id", "shape", "color"}
                    or item.get("shape") not in {"circle", "square", "triangle"}
                    or item.get("color") not in {"red", "blue", "yellow", "green"}):
                _fail("progressive_invalid_object_count", "数数物体只能使用已登记的简单图形和颜色。")
            object_ids.append(_text(item.get("id"), "objects.id"))
        if (len(set(object_ids)) != len(object_ids) or not isinstance(question.get("answer"), list)
                or sorted(question["answer"]) != sorted(object_ids)):
            _fail("progressive_host_answer_mismatch", "数数答案必须逐一对应全部目标物体，不能重复或遗漏。")
        targets = {int(token) for token in constraints.get("introducedTokens", []) if str(token).isdigit()}
        if len(objects) not in targets or (constraints.get("maximumNumber") is not None and len(objects) > constraints["maximumNumber"]):
            _fail("progressive_number_out_of_scope", "物体数量超出当前课次所教数词。")
        return sorted(object_ids)
    if constraints.get("writtenNumberRecognitionRequired") is False and lesson["subject"] == "math":
        _fail("progressive_count_requires_objects", "逐物数数阶段不能以识读阿拉伯数字的选择题替代。")
    if question.get("type") != "single_choice":
        _fail("progressive_unregistered_scoring", "新课次只接受已登记的确定性单选验收，其他能力须人工观察。")
    choices = question.get("choices")
    if not isinstance(choices, list) or not 2 <= len(choices) <= 4:
        _fail("progressive_invalid_question", "单选题需要二至四个选项。")
    ids, labels = [], []
    for choice in choices:
        if not isinstance(choice, Mapping): _fail("progressive_invalid_question", "选项无效。")
        ids.append(_text(choice.get("id"), "choice.id"))
        labels.append(_text(choice.get("label"), "choice.label"))
    if len(ids) != len(set(ids)) or len(labels) != len(set(labels)):
        _fail("progressive_invalid_question", "选项不得重复。")
    if evidence.get("kind") == "token_match":
        token = _text(evidence.get("targetToken"), "evidence.targetToken")
        tokens = set(constraints.get("introducedTokens") or [])
        if token not in tokens:
            _fail("progressive_unregistered_scoring", "目标词元未被本课知识范围登记。")
        matches = [ids[index] for index, label in enumerate(labels) if label == token]
    elif evidence.get("kind") == "numeric_expression" and lesson["subject"] == "math":
        value = _numeric_value(evidence.get("expression"), constraints)
        matches = []
        for choice_id, label in zip(ids, labels):
            if _numeric_choice_value(label) == value:
                matches.append(choice_id)
    elif evidence.get("kind") == "independent_choice":
        # Semantic reading/grammar is independently reviewed. The host checks
        # deterministic answer-key structure, not an invented semantic solver.
        matches = [question["answer"]] if question.get("answer") in ids else []
    else:
        _fail("progressive_unregistered_scoring", "本课判分能力尚未登记，不能以模型自报答案冒充确定性验收。")
    if len(matches) != 1 or question.get("answer") != matches[0]:
        _fail("progressive_host_answer_mismatch", "主机复算结果与题目答案不一致。")
    return matches[0]


def validate_progressive_course(candidate, *, brief: dict, verification: dict,
                                request_id: str) -> tuple[dict, dict]:
    """Host gate for new contracts. Legacy v1/v2 validators remain untouched."""
    lesson = brief["lesson"]
    binding = lesson_binding(lesson["lessonId"])
    if brief != generation_brief(lesson["lessonId"]):
        _fail("progressive_registry_changed", "课程体系已更新，请重新创建本课生成任务。")
    if not isinstance(candidate, Mapping): _fail("progressive_invalid_content", "课件不是有效对象。")
    course = deepcopy(dict(candidate))
    for field, expected in (("gradeCode", lesson["gradeCode"]), ("subject", lesson["subject"]), ("nodeCode", lesson["lessonId"])):
        if course.get(field) != expected: _fail("progressive_lesson_identity_mismatch", "生成内容改变了指定课次。")
    for field in ("title", "objective"):
        _text(course.get(field), field)
    content = course.get("content")
    if not isinstance(content, dict) or content.get("schemaVersion") != COURSE_SCHEMA or content.get("progressiveLesson") != binding:
        _fail("progressive_lesson_binding_invalid", "新课程必须携带主机指定的完整课次版本绑定，旧课程不能重新贴标签。")
    if content.get("difficultyCode") != "basic" or content.get("assessmentMode") != lesson["assessmentMode"]:
        _fail("progressive_assessment_mismatch", "课程难度或验收模式与课次登记不一致。")
    from content.progressive_runtime_authoring_scope import validate_runtime_authoring_scope
    try:
        runtime_scope = validate_runtime_authoring_scope(content=content, lesson_id=lesson["lessonId"],
            binding=binding, request_id=request_id)
    except ValueError as exc:
        _fail("progressive_runtime_authoring_scope_invalid", str(exc))
    introduced, prior = set(lesson["introducedKnowledgeIds"]), set(brief["priorKnowledgeIds"])
    allowed = introduced | prior
    steps = content.get("progressiveFlow")
    if not isinstance(steps, list) or not 4 <= len(steps) <= 20:
        _fail("progressive_teach_before_practice", "课件必须含先讲解、示范、引导练习和独立验收的教学顺序。")
    seen, phases = set(prior), []
    questions = content.get("questions")
    if not isinstance(questions, list): _fail("progressive_invalid_question", "questions 必须是数组。")
    question_map = {item.get("id"): item for item in questions if isinstance(item, Mapping)}
    if len(question_map) != len(questions): _fail("progressive_invalid_question", "题目标识必须唯一。")
    referenced, independent = [], []
    for step in steps:
        if not isinstance(step, Mapping): _fail("progressive_invalid_evidence", "教学步骤无效。")
        phase = step.get("phase")
        if phase not in {"teach", "example", "guided", "independent", "observe", "recap"}:
            _fail("progressive_invalid_evidence", "教学阶段无效。")
        phases.append(phase)
        _text(step.get("text"), "progressiveFlow.text")
        knowledge = set(_strings(step.get("knowledgeIds"), "progressiveFlow.knowledgeIds"))
        dependencies = set(_strings(step.get("requiresKnowledgeIds", []), "requiresKnowledgeIds", nonempty=False))
        if not knowledge.issubset(allowed) or not dependencies.issubset(seen):
            _fail("progressive_untaught_dependency", "教学或练习依赖尚未学过的知识。")
        if phase == "teach":
            seen.update(knowledge)
        elif not knowledge.issubset(seen):
            _fail("progressive_teach_before_practice", "本课新知识必须先讲解，再示范或练习。")
        if phase in {"guided", "independent"} and lesson["assessmentMode"] == "objective":
            question_id = step.get("questionId")
            if question_id not in question_map or question_id in referenced:
                _fail("progressive_invalid_evidence", "练习与题目必须一一对应。")
            question = question_map[question_id]
            if not set(question.get("knowledgeIds") or []).issubset(knowledge):
                _fail("progressive_teach_before_practice", "题目知识必须包含在对应教学步骤中。")
            referenced.append(question_id)
            if phase == "independent": independent.append(question_id)
    if not introduced.issubset(seen) or phases[0] != "teach" or "example" not in phases:
        _fail("progressive_teach_before_practice", "本课新增知识必须完整讲解并展示示范。")
    exercise_positions = [index for index, phase in enumerate(phases) if phase in {"guided", "independent", "observe"}]
    if not exercise_positions or phases.index("example") > min(exercise_positions):
        _fail("progressive_teach_before_practice", "示范必须出现在练习和观察验收之前。")
    answers = {}
    if lesson["assessmentMode"] == "objective":
        minimum = max(5, int(lesson.get("assessmentCriteria", {}).get("minimumDistinctTasks") or 5))
        if not minimum <= len(independent) <= 10 or not minimum + 1 <= len(questions) <= 14 or set(referenced) != set(question_map) or "guided" not in phases:
            _fail("progressive_invalid_evidence", "基础课需要引导练习及课次登记要求的足量独立验收题。")
        independent_fingerprints = {_task_signature(question_map[key]) for key in independent}
        if len(independent_fingerprints) != len(independent):
            _fail("progressive_duplicate_assessment", "独立验收题不得重复充数。")
        if phases.index("guided") > phases.index("independent"):
            _fail("progressive_teach_before_practice", "独立验收必须在引导练习之后。")
        for question in questions:
            answers[question["id"]] = _validate_question(question, lesson=lesson, allowed=allowed, introduced=introduced)
        if content.get("autoMasteryEligible") is not True:
            _fail("progressive_assessment_mismatch", "确定性验收标识不一致。")
    else:
        if questions or content.get("autoMasteryEligible") is not False or content.get("manualConfirmationRequired") is not True or "observe" not in phases:
            _fail("progressive_observation_not_score", "观察类课程须人工确认，不能附带自动判分题或自动掌握结论。")
    _validate_language_scope(content, brief)
    verification_answers = verification.get("answers") if isinstance(verification, Mapping) else None
    if isinstance(verification_answers, Mapping):
        verification_answers = {key: sorted(value) if isinstance(value, list) and all(isinstance(item, str) for item in value) else value
                                for key, value in verification_answers.items()}
    if (not isinstance(verification, Mapping) or verification.get("requestId") != request_id + ":verify"
            or verification.get("lessonId") != lesson["lessonId"] or verification.get("binding") != binding
            or verification.get("passed") is not True or verification.get("issues") != []
            or verification.get("undeclaredKnowledgeIds") != [] or verification_answers != answers):
        _fail("progressive_independent_review_failed", "独立复核未通过：答案、课次范围或先教后练证据不一致。")
    course["id"] = "progressive_" + digest({"lessonId": lesson["lessonId"], "requestId": request_id})[:24]
    course["version"] = "1.0.0"
    course["curriculumVersion"] = binding["curriculumVersion"]
    course["boundaryVersion"] = binding["curriculumVersion"] + ":" + binding["lessonSha256"][:24]
    report = {"schemaVersion": VALIDATION_SCHEMA, "contractVersion": CONTRACT_VERSION,
              "binding": binding, "hostValidated": True, "publishable": True,
              "automaticPublication": False, "contentFingerprint": digest(content),
              "generationRequestId": request_id, "independentRequestId": verification["requestId"],
              "independentReview": deepcopy(dict(verification)),
              "independentReviewSha256": digest(verification),
              "autoMasteryEligible": content["autoMasteryEligible"],
              "checks": ["registry_identity", "basic_first", "knowledge_scope", "teach_before_practice",
                         "registered_objective_evidence" if answers else "observed_manual_only", "independent_review"]}
    if runtime_scope is not None:
        report["runtimeAuthoringScope"] = {key: runtime_scope[key] for key in (
            "policyVersion", "scopeSha256", "sourceGenerationRequestId", "sourceProviderContentSha256")}
        report["checks"].append("server_issued_runtime_authoring_scope")
    return course, report


def validate_stored_progressive_course(row: Mapping, *, expected_lesson_id: str,
                                      validation_receipt: Mapping) -> dict:
    """Revalidate exact stored content against its accepted generation receipt.

    This is content eligibility only. Callers must also retain package, runtime,
    audio/ASR, release ownership and explicit-publication gates.
    """
    if not isinstance(validation_receipt, Mapping) or validation_receipt.get("schemaVersion") != VALIDATION_SCHEMA:
        _fail("progressive_acceptance_receipt_missing", "缺少新课次独立验收凭证，不能发布或给旧课程补绑定。")
    content = row.get("content", row.get("content_json"))
    if isinstance(content, str):
        try: content = json.loads(content)
        except ValueError: _fail("progressive_invalid_content", "课程内容不是有效JSON。")
    binding = lesson_binding(expected_lesson_id)
    request_id = str(row.get("generation_request_id") or "")
    candidate = {"id": row.get("id"), "version": row.get("version"),
        "gradeCode": row.get("grade_code"), "subject": row.get("subject"),
        "nodeCode": row.get("node_code"), "title": row.get("title"),
        "objective": row.get("objective"), "content": content}
    if (not request_id or row.get("content_origin") != "openmaic_generated" or row.get("generator") != "openmaic"
            or row.get("curriculum_version") != binding["curriculumVersion"]
            or row.get("node_code") != expected_lesson_id
            or validation_receipt.get("generationRequestId") != request_id
            or validation_receipt.get("binding") != binding):
        _fail("progressive_lesson_binding_invalid", "课次身份或生成来源与验收凭证不一致。")
    validated, report = validate_progressive_course(candidate, brief=generation_brief(expected_lesson_id),
        verification=validation_receipt.get("independentReview"), request_id=request_id)
    if (row.get("id") != validated["id"] or str(row.get("version")) != validated["version"]
            or row.get("boundary_version") != validated["boundaryVersion"]
            or row.get("generation_content_hash") != report["contentFingerprint"]
            or canonical(dict(validation_receipt)) != canonical(report)):
        _fail("progressive_acceptance_receipt_mismatch", "课件内容、版本或独立验收凭证已变化。")
    return report


def validate_progressive_course_for_release(conn, *, course: Mapping, expected_lesson_id: str) -> dict:
    """Read the DB candidate/job provenance and invoke the fresh host gate."""
    accepted = conn.execute(
        "SELECT candidate.validation_json, job.request_id, job.curriculum_version, job.prompt_version "
        "FROM learning_course_generation_candidates AS candidate "
        "JOIN learning_course_generation_jobs AS job ON job.id = candidate.job_id "
        "WHERE candidate.course_id = ? AND candidate.course_version = ? "
        "AND candidate.status = 'course_validated' AND job.status IN ('validated','partially_validated') "
        "ORDER BY candidate.created_at DESC LIMIT 1",
        (course["id"], course["version"]),
    ).fetchone()
    if (accepted is None or accepted.get("request_id") != course.get("generation_request_id")
            or accepted.get("curriculum_version") != _registry().CURRICULUM_VERSION
            or accepted.get("prompt_version") != CONTRACT_VERSION):
        _fail("progressive_acceptance_receipt_missing", "未找到本课次的原始生成与独立验收记录。")
    receipt = accepted.get("validation_json")
    if isinstance(receipt, str):
        try: receipt = json.loads(receipt)
        except ValueError: _fail("progressive_acceptance_receipt_missing", "新课次验收凭证无效。")
    return validate_stored_progressive_course(course, expected_lesson_id=expected_lesson_id,
                                             validation_receipt=receipt)


def _public_candidate(candidate):
    public = deepcopy(candidate)
    content = public.get("content") or {}
    for question in content.get("questions") or []:
        for field in ("answer", "evaluation", "evidence", "hint", "explanation"):
            question.pop(field, None)
    # Review never receives the generator's expected answer or scoring evidence.
    return public


def progressive_boundary(course: Mapping) -> dict:
    """Explicit new boundary identity for package preparation, never old v1."""
    lesson_id = str(course.get("node_code") or "")
    brief = generation_brief(lesson_id)
    lesson, binding = brief["lesson"], brief["binding"]
    if (course.get("grade_code") != lesson["gradeCode"] or course.get("subject") != lesson["subject"]
            or (course.get("curriculum_version") is not None and course["curriculum_version"] != binding["curriculumVersion"])
            or (course.get("boundary_version") is not None and course["boundary_version"] != binding["curriculumVersion"] + ":" + binding["lessonSha256"][:24])):
        _fail("progressive_lesson_identity_mismatch", "课件准备的课次、年级、学科或版本不一致。")
    return {"schemaVersion": "mira.learning.progressive-skill-boundary.v1",
        "skillId": lesson_id, "skillTitle": lesson["title"], "learningObjectives": lesson["learningObjectives"],
        "allowedContent": brief["allowedKnowledgeIds"], "excludedContent": brief["mustNotDependOnKnowledgeIds"],
        "prerequisiteSkills": brief["prerequisiteLessonIds"], "constraints": lesson["constraints"],
        "language": "zh-CN", "estimatedMinutes": 10, "progressiveLesson": binding}


def progressive_runtime_teaching_brief(course: Mapping) -> tuple[dict, str, str]:
    """Pure answer-blind projection used by the formal package preparation path.

    The caller validates the persisted generation receipt before reserving a
    package. This projection supplies no student scoring or publication rights.
    """
    from content.progressive_difficulty_policy import progressive_difficulty_policy
    from content.progressive_runtime_authoring_scope import validate_runtime_authoring_scope

    raw = course.get("content_json")
    if not isinstance(raw, str): raise ValueError("progressive course content is missing")
    content = json.loads(raw)
    lesson_id = str(course.get("node_code") or "")
    boundary = progressive_boundary(course)
    binding = boundary["progressiveLesson"]
    if (not isinstance(content, Mapping) or content.get("schemaVersion") != COURSE_SCHEMA
            or content.get("progressiveLesson") != binding or content.get("difficultyCode") != "basic"
            or content.get("assessmentMode") != binding["assessmentMode"]):
        raise ValueError("progressive course binding is invalid")
    runtime_scope = validate_runtime_authoring_scope(content=content, lesson_id=lesson_id, binding=binding,
        request_id=course.get("generation_request_id"))
    if runtime_scope is not None:
        expected_course_id = "progressive_" + digest({"lessonId": lesson_id,
            "requestId": runtime_scope["sourceGenerationRequestId"]})[:24]
        if (course.get("id") or course.get("course_id")) != expected_course_id:
            raise ValueError("runtime authoring scope belongs to a different generated course")
    steps = content.get("progressiveFlow")
    if not isinstance(steps, list) or not steps:
        raise ValueError("progressive teaching flow is missing")
    projected_steps = []
    for step in steps:
        if not isinstance(step, Mapping): raise ValueError("progressive teaching step is invalid")
        _text(step.get("text"), "progressiveFlow.text")
        _strings(step.get("knowledgeIds"), "progressiveFlow.knowledgeIds")
        _strings(step.get("requiresKnowledgeIds", []), "progressiveFlow.requiresKnowledgeIds", nonempty=False)
        projected_steps.append({key: deepcopy(step[key]) for key in (
            "phase", "text", "knowledgeIds", "requiresKnowledgeIds", "questionId") if key in step})
    public_questions = []
    for question in content.get("questions") or []:
        lesson = _registry().lesson_by_id(lesson_id)
        generation = generation_brief(lesson_id)
        _validate_question(question, lesson=lesson, allowed=set(generation["allowedKnowledgeIds"]),
                           introduced=set(lesson["introducedKnowledgeIds"]))
        public = {key: deepcopy(question[key]) for key in ("id", "type", "prompt", "knowledgeIds") if key in question}
        if question.get("type") == "single_choice":
            public["choices"] = [{key: choice[key] for key in ("id", "label")} for choice in question["choices"]]
        elif question.get("type") == "tap_objects":
            public["objects"] = [{key: item[key] for key in ("id", "shape", "color")} for item in question["objects"]]
        else: raise ValueError("unregistered progressive question template")
        public_questions.append(public)
    teach_steps = [step for step in projected_steps if step["phase"] == "teach"]
    recaps = [step["text"] for step in projected_steps if step["phase"] == "recap"]
    minutes = content.get("estimatedMinutes")
    if type(minutes) is not int or not 5 <= minutes <= 30: raise ValueError("progressive lesson duration is invalid")
    source_hash = hashlib.sha256(raw.encode()).hexdigest()
    brief = {"schemaVersion": "mira.learning.formal-runtime-teaching-brief.progressive.v1",
        "sourceCourseContentSha256": source_hash,
        "course": {"id": course.get("id") or course.get("course_id"),
            "version": course.get("version") or course.get("course_version"),
            "gradeCode": course["grade_code"], "subject": course["subject"], "skillId": lesson_id,
            "title": course["title"], "objective": course["objective"], "difficultyCode": "basic"},
        "progressiveLesson": binding,
        "difficultyPolicy": progressive_difficulty_policy(
            course["grade_code"], course["subject"], lesson_id, "basic"),
        "lesson": {"intro": _text(content.get("intro"), "intro"), "estimatedMinutes": minutes,
            "assessmentMode": content["assessmentMode"], "autoMasteryEligible": content["autoMasteryEligible"],
            "manualConfirmationRequired": content["manualConfirmationRequired"],
            "progressiveFlow": projected_steps, "questions": public_questions,
            "teachingFlow": {"schemaVersion": "mira.learning.progressive-teaching-flow.v1",
                "teach": {"title": course["title"], "sayText": "\n".join(step["text"] for step in teach_steps),
                    "keyPoints": boundary["learningObjectives"]},
                "examples": [{"text": step["text"], "knowledgeIds": step["knowledgeIds"]} for step in projected_steps if step["phase"] == "example"],
                "guidedQuestionIds": [step["questionId"] for step in projected_steps if step["phase"] == "guided" and step.get("questionId")],
                "independentQuestionIds": [step["questionId"] for step in projected_steps if step["phase"] == "independent" and step.get("questionId")],
                "observations": [{"text": step["text"], "knowledgeIds": step["knowledgeIds"]} for step in projected_steps if step["phase"] == "observe"],
                "recap": {"sayText": "\n".join(recaps) if recaps else "今天的学习先到这里，接下来按本课要求练习或请家长观察。"}}},
        "authority": {"source": "locked_learning_course", "answerContractProvided": False,
            "scoringRulesProvided": False, "providerSecretsProvided": False}}
    if runtime_scope is not None:
        brief["runtimeAuthoringScope"] = runtime_scope
    text = canonical(brief)
    if len(text.encode()) > 64_000: raise ValueError("progressive teaching brief is too large")
    return brief, hashlib.sha256(text.encode()).hexdigest(), source_hash


def _task_signature(question):
    from services.progressive_learning_service import _question_fingerprint
    return _question_fingerprint(question)


def _independent_task_signature(content):
    independent = {step.get("questionId") for step in content.get("progressiveFlow", []) if step.get("phase") == "independent"}
    signatures = [_task_signature(question) for question in content.get("questions", []) if question.get("id") in independent]
    return digest(sorted(signatures)) if signatures else None


def _assessment_generation_context(conn, *, lesson_id, curriculum_version, request_id):
    from services.progressive_preruntime_replacement import excluded_unexposed_replacement_source
    excluded = excluded_unexposed_replacement_source(conn, request_id=request_id, lesson_id=lesson_id)
    previous = conn.execute(
        "SELECT id, version, content_json FROM learning_courses WHERE node_code=? AND curriculum_version=? "
        "AND (generation_request_id IS NULL OR generation_request_id<>?) "
        "AND status IN ('validated','published') ORDER BY id, version",
        (lesson_id, curriculum_version, request_id),
    ).fetchall()
    questions = []
    for course in previous:
        if excluded == (course["id"], course["version"]):
            continue
        content = json.loads(course["content_json"])
        for question in content.get("questions", []):
            # A prior guided question is already exposed too. Only public
            # fields belong in the generator and answer-blind reviewer input.
            public = {key: deepcopy(question[key]) for key in ("id", "type", "prompt")}
            if question["type"] == "single_choice":
                public["choices"] = [{key: choice[key] for key in ("id", "label")}
                                     for choice in question["choices"]]
            elif question["type"] == "tap_objects":
                public["objects"] = [{key: item[key] for key in ("id", "shape", "color")}
                                     for item in question["objects"]]
            else:
                _fail("progressive_invalid_generation_context", "已有课次包含未登记的题目模板。")
            questions.append({"courseId": str(course["id"]), "courseVersion": str(course["version"]),
                              "question": public})
    return {"schemaVersion": GENERATION_CONTEXT_SCHEMA, "curriculumVersion": curriculum_version,
            "lessonId": lesson_id, "previousQuestions": questions}


def _reject_reused_independent_tasks(content, generation_context):
    previous = {_task_signature(item["question"]) for item in generation_context["previousQuestions"]}
    independent = {step.get("questionId") for step in content.get("progressiveFlow", [])
                   if step.get("phase") == "independent"}
    duplicates = [str(question["id"]) for question in content.get("questions", [])
                  if question.get("id") in independent and _task_signature(question) in previous]
    if duplicates:
        _fail("progressive_duplicate_assessment_set",
              "新的一组独立验收不能沿用已有题目：" + "、".join(duplicates) + "。")


def _provider_call(owner, *, request_id, schema, brief, candidate=None, generation_context=None):
    adapter = owner.adapter
    if not adapter.fake_mode and (adapter.provider_name != "openmaic_runtime" or getattr(adapter, "execution_environment", None) is None):
        _fail("progressive_formal_runtime_required", "新课次须通过正式准备任务和已授权的课堂生成服务制作。")
    fake = adapter.generation_fake_responses if schema == INPUT_SCHEMA else adapter.verification_fake_responses
    payload = {"schemaVersion": schema, "requestId": request_id, "brief": brief,
               "promptRegistry": json.loads(PROMPT_PATH.read_text()),
               **adapter._execution_payload(fake)}
    if candidate is not None: payload["publicCandidate"] = _public_candidate(candidate)
    if generation_context is not None: payload["generationContext"] = generation_context
    response, _elapsed = adapter._call(payload)
    adapter._require_envelope(response, schema=OUTPUT_SCHEMA, request_id=request_id)
    value = response.get("candidateCourse" if schema == INPUT_SCHEMA else "verification")
    if not isinstance(value, Mapping): _fail("progressive_invalid_provider_reply", "新课次生成返回内容不完整。")
    return dict(value)


def generate_progressive_course(owner, data: Mapping, *, enqueue_classroom: bool):
    """Called by DynamicLearningCourseGenerationService.generate, with its jobs.

    No implicit retries: one generator call and one answer-blind reviewer call.
    Ambiguous provider outcomes remain persisted failures for explicit handling.
    """
    from services.dynamic_learning_course_generation_service import DynamicCourseGenerationResult
    if getattr(owner, "progressive_adapter", None) is not None:
        from copy import copy
        owner = copy(owner)
        owner.adapter = owner.progressive_adapter
    registry = _registry()
    lesson_id = str(data.get("lessonId") or "").strip()
    if not lesson_id or data.get("curriculumVersion") != registry.CURRICULUM_VERSION:
        _fail("progressive_lesson_required", "生成细课次必须指定 lessonId 和完整课程体系版本。")
    try:
        brief = generation_brief(lesson_id, difficulty_code=str(data.get("difficultyCode") or "basic"))
    except ValueError as exc:
        _fail("progressive_unknown_lesson", str(exc))
    lesson, binding = brief["lesson"], brief["binding"]
    for field in ("gradeCode", "subject"):
        if data.get(field) is not None and data[field] != lesson[field]:
            _fail("progressive_lesson_identity_mismatch", "请求年级或学科与固定课次不一致。")
    request_id = owner._request_id(data.get("requestId"))
    if len(request_id) > 113:
        _fail("progressive_request_id_too_long", "新课次请求标识不能超过 113 个字符。")
    boundary_version = binding["curriculumVersion"] + ":" + binding["lessonSha256"][:24]
    with owner.repository.transaction() as conn:
        job, created = owner.repository.create_or_get_job(
            conn, request_id=request_id, grade_code=lesson["gradeCode"], subject=lesson["subject"],
            node_code=lesson_id, curriculum_version=binding["curriculumVersion"], boundary_version=boundary_version,
            generator="openmaic", provider=owner.adapter.provider_name, model=owner.adapter.model_name,
            prompt_version=CONTRACT_VERSION, requested_candidate_count=1, generation_spec=brief, now=now_ms())
        if not created:
            return owner._persisted_result(conn, job=job, replayed=True)
        owner.repository.mark_job_generating(conn, job_id=str(job["id"]), now=now_ms())
    try:
        generation_context = None
        if lesson["assessmentMode"] == "objective":
            with owner.repository.transaction() as conn:
                generation_context = _assessment_generation_context(conn, lesson_id=lesson_id,
                    curriculum_version=binding["curriculumVersion"], request_id=request_id)
        candidate = _provider_call(owner, request_id=request_id, schema=INPUT_SCHEMA, brief=brief,
                                   generation_context=generation_context)
        # This is the first generation of a newly created job. The Native
        # Provider archive remains untouched; only the host can issue this
        # reserved metadata before the normal answer-blind review and receipt.
        from content.progressive_runtime_authoring_scope import issue_runtime_authoring_scope, CONTENT_FIELD
        provider_content = candidate.get("content")
        if not isinstance(provider_content, Mapping) or CONTENT_FIELD in provider_content:
            _fail("progressive_runtime_authoring_scope_provider_field", "课堂范围快照只能由服务器签发，生成者不得提供该保留字段。")
        candidate = deepcopy(candidate)
        candidate["content"][CONTENT_FIELD] = issue_runtime_authoring_scope(lesson_id=lesson_id,
            binding=binding, request_id=request_id, provider_content=provider_content)
        verification = _provider_call(owner, request_id=request_id + ":verify", schema=VERIFY_SCHEMA,
                                      brief=brief, candidate=candidate, generation_context=generation_context)
        course, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id=request_id)
        with owner.repository.transaction() as conn:
            if generation_context is not None:
                _reject_reused_independent_tasks(course["content"], generation_context)
                # Recheck accepted inventory in case another set was saved
                # while the providers were generating and reviewing this one.
                current_context = _assessment_generation_context(conn, lesson_id=lesson_id,
                    curriculum_version=binding["curriculumVersion"], request_id=request_id)
                _reject_reused_independent_tasks(course["content"], current_context)
            row, _ = owner.repository.create_or_get_candidate(conn, job_id=str(job["id"]), ordinal=1,
                                                              course=course, now=now_ms())
            owner.repository.mark_candidate_validated(conn, candidate_id=str(row["id"]), validation=report, now=now_ms())
        staged, _ = owner.repository.stage_candidate(candidate_id=str(row["id"]), now=now_ms())
        # The sealed classroom/publication pipeline is not an implicit adapter
        # for this contract. Its explicit progressive version must accept proof.
        return DynamicCourseGenerationResult({"ok": True, "replayed": False, "status": "validated",
            "requestId": request_id, "jobId": str(job["id"]), "candidateId": str(row["id"]),
            "course": owner._course_payload(staged), "validation": report,
            "classroomGeneration": {"status": "progressive_package_required", "automaticPublication": False},
            "progressiveLesson": binding})
    except Exception as exc:
        return owner._persist_failure(job_id=str(job["id"]),
            code=str(getattr(exc, "code", "progressive_generation_failed")),
            message=str(getattr(exc, "message", str(exc))))
