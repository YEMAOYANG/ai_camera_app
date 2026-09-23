"""Immutable v1 classroom-authoring scope, issued only by the host.

Do not revise v1 rules in place. Register a new policy version for future
changes so accepted courses continue to reproduce their frozen scope.
This policy supplies no questions, answers or student scoring authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import hashlib
import json
import re

from content.progressive_curriculum import CURRICULUM_VERSION, curriculum_identity, lesson_by_id


SCOPE_SCHEMA = "mira.learning.progressive-runtime-authoring-scope.v1"
POLICY_VERSION = "mira.learning.progressive-runtime-authoring-policy.v1"
CONTENT_FIELD = "runtimeAuthoringScope"

# Frozen v1 rules: the tuple identifies a grade/subject/unit/lesson, not a
# generic subject-wide lesson. Later policies must keep these exact v1 bytes.
_V1_LESSON_RULES = {
    ("primary_6", "chinese", "观点事实证据", "区分信息性质"): {
        "allowed": (
            "辨认可核实的事实陈述、个人评价或建议；辨认已经给定的事实材料在短文中起的证据作用。",
            "事实是信息性质，证据是材料的语境作用；同一材料可以同时是事实并承担证据作用。",
            "使用另编的、自足的校园短材料与明确来源，分别演示信息性质和语境作用；只让学生辨认已给定句子的性质或作用。",
        ),
        "forbidden": (
            "不得从若干候选材料中挑选、配对或寻找支持某观点的证据；这属于后续‘证据对应观点’课次。",
            "不得评价证据是否直接支持、充分或可靠，也不要求补充证据、反驳观点或分析完整论证结构。",
            "不得把事实、观点、证据列作互斥类别；不得用有没有数字或‘我认为’字样代替对句子内容和来源的判断。",
        ),
    },
    ("primary_6", "math", "分数乘法", "分数乘整数的意义"): {
        "allowed": (
            "用同样大小的单位整体、相同分数的连加和同量分组解释分数乘整数的意义。",
            "操作每份量和整数份数，观察总量；使用简单分数及小整数，图示与文字数量关系一致。",
        ),
        "forbidden": (
            "不得提前教分数乘分数、分数除法、比或百分数，也不要求整个分数乘法单元的综合应用。",
            "三维展示只能服务于本课同量分组，不得因此加入体积公式、复杂立体几何或未登记知识。",
        ),
    },
    ("primary_6", "english", "指代连贯", "常见主宾形式"): {
        "allowed": (
            "先教少量常见人称代词主格与宾格的配对形式，再在简短连贯语境中展示主语位置和常见动词后的宾语位置。",
            "按本课允许语法组织简单现在时句子，语境明确代词所指对象；所有要考的形式及必要词汇先教后练。",
        ),
        "forbidden": (
            "不得提前加入过去时、将来时、现在进行时、复杂从句或被动结构，不得凭姓名、职业或外貌猜测代词性别。",
            "不得要求复杂篇章指代推理、篇章改写或整个指代连贯单元的综合能力，也不退回字母启蒙。",
        ),
    },
}


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def _binding(lesson):
    return {"schemaVersion": "mira.learning.progressive-binding.v1", "curriculumVersion": CURRICULUM_VERSION,
        "lessonId": lesson["lessonId"], "identitySha256": curriculum_identity()["datasetSha256"],
        "lessonSha256": _sha(lesson), "difficultyCode": "basic", "assessmentMode": lesson["assessmentMode"]}


def _protected_questions(content):
    questions, steps = content.get("questions"), content.get("progressiveFlow")
    if not isinstance(questions, list) or not isinstance(steps, list):
        raise ValueError("runtime authoring scope requires the actual public question and teaching flow")
    roles = {}
    for step in steps:
        if isinstance(step, Mapping) and step.get("phase") in {"guided", "independent"}:
            question_id = step.get("questionId")
            if not isinstance(question_id, str) or not question_id or question_id in roles:
                raise ValueError("runtime authoring scope requires unique question roles")
            roles[question_id] = step["phase"]
    result = []
    for question in questions:
        if not isinstance(question, Mapping) or question.get("id") not in roles:
            raise ValueError("runtime authoring scope question is missing its registered role")
        public = {key: deepcopy(question[key]) for key in ("id", "type", "prompt", "knowledgeIds") if key in question}
        if question.get("type") == "single_choice":
            public["choices"] = [{key: choice[key] for key in ("id", "label")} for choice in question["choices"]]
        elif question.get("type") == "tap_objects":
            public["objects"] = [{key: item[key] for key in ("id", "shape", "color")} for item in question["objects"]]
        else:
            raise ValueError("runtime authoring scope question type is unregistered")
        result.append({"questionId": question["id"], "phase": roles[question["id"]], "publicQuestionSha256": _sha(public)})
    if len({item["questionId"] for item in result}) != len(result) or set(roles) != {item["questionId"] for item in result}:
        raise ValueError("runtime authoring scope requires each actual question exactly once")
    return result


def issue_runtime_authoring_scope(*, lesson_id: str, binding: Mapping, request_id: str,
                                  provider_content: Mapping, policy_version: str = POLICY_VERSION) -> dict:
    """Issue a host-owned scope without mutating the retained model reply."""
    if policy_version != POLICY_VERSION:
        raise ValueError("unregistered runtime authoring policy version")
    lesson = lesson_by_id(lesson_id)
    if (dict(binding) != _binding(lesson) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,112}", request_id)
            or not isinstance(provider_content, Mapping) or CONTENT_FIELD in provider_content
            or provider_content.get("progressiveLesson") != binding):
        raise ValueError("runtime authoring scope must be issued for the exact new host-bound model reply")
    rules = _V1_LESSON_RULES.get((lesson["gradeCode"], lesson["subject"], lesson["unitTitle"], lesson["sourceStepTitle"]), {})
    scope = {
        "schemaVersion": SCOPE_SCHEMA, "policyVersion": policy_version, "issuer": "mira_backend",
        "progressiveLesson": deepcopy(dict(binding)), "sourceGenerationRequestId": request_id,
        "sourceProviderContentSha256": _sha(provider_content),
        "lessonScope": {key: deepcopy(lesson[key]) for key in (
            "gradeCode", "subject", "unitId", "unitTitle", "sourceStepTitle", "learningObjectives", "introducedKnowledgeIds", "constraints")},
        "allowedLearningActions": [
            "只围绕本年级当前课次的learningObjectives和sourceStepTitle讲解、示范与直接应用；单元标题不是要求首课完成整个单元。",
            "先修知识只用于支持本课，不替换为其他年级课程；示范题使用另外的材料，讲清示范答案与原因。",
            *rules.get("allowed", ()),
        ],
        "forbiddenLearningActions": [
            "不得扩大到后续课次目标、未登记词汇语法或运算；基础难度不表示回到一年级零起点。",
            *rules.get("forbidden", ()),
        ],
        "assessmentProtection": {
            "materialSource": "teachingBrief.lesson.questions",
            "protectedQuestions": _protected_questions(provider_content),
            "allowedUse": "exact_registered_quiz_role_only",
            "rules": [
                "保护清单对应lesson.questions中的全部正式公开题面，包括引导题和独立题；仅在各自登记的quiz阶段按原题使用。",
                "讲解、示范、三维场景、互动游戏、讨论和反馈必须另编材料，不得提前使用保护题的具体情境、数据、句子、选项或核心作答信息。",
                "换人物名、换题号、调选项顺序或只作近义改写仍算提前复用；不得先让学生操作或练习保护题材料，再将原题当成独立验收。",
                "可以迁移已教概念与解题方法；禁止透露正式题答案，游戏反馈仅说明另编练习材料的现象，不授予正式分数或掌握结论。",
            ],
        },
    }
    scope["scopeSha256"] = _sha(scope)
    return scope


def validate_runtime_authoring_scope(*, content: Mapping, lesson_id: str, binding: Mapping,
                                     request_id: str | None = None) -> dict | None:
    """Absent means the unchanged legacy projection; present must verify v1 exactly."""
    if CONTENT_FIELD not in content:
        return None
    actual = content[CONTENT_FIELD]
    if not isinstance(actual, Mapping) or actual.get("schemaVersion") != SCOPE_SCHEMA:
        raise ValueError("runtime authoring scope is invalid")
    source_request = actual.get("sourceGenerationRequestId")
    if not isinstance(source_request, str) or (request_id is not None and source_request != request_id):
        raise ValueError("runtime authoring scope source request changed")
    original = {key: deepcopy(value) for key, value in content.items() if key != CONTENT_FIELD}
    expected = issue_runtime_authoring_scope(lesson_id=lesson_id, binding=binding, request_id=source_request,
        provider_content=original, policy_version=actual.get("policyVersion"))
    if dict(actual) != expected:
        raise ValueError("runtime authoring scope or its model-source content changed")
    return deepcopy(expected)
