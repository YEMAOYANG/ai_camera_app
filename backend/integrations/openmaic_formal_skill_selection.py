"""Recompute the Runtime's versioned adaptive Skill plan from locked inputs."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


SKILL_REGISTRY_ID = "openmaic-builtin-skills.v1-23"
BASE_SKILL_IDS = ["mira-primary-courseware", "stage-design", "k12-core-literacy-planning",
                  "deep-interactive", "slide-craft", "learning-to-learn"]
BUILTIN_SKILL_IDS = [*BASE_SKILL_IDS, "understanding-by-design", "feynman-learning",
    "workshop-style", "social-emotional-learning", "deep-research", "lecture-style",
    "pro-editing", "stage-dsl", "slide-dsl", "pptx-import", "style-clone", "page-clone",
    "teacher-style-clone", "curriculum-planner", "spiral-curriculum", "build-personal-skill",
    "vocational"]
SKILL_SIGNALS = {
    "explanationGoal": "解释|说明.{0,12}(原因|理由)|因果|为什么|原理|规律|关系|理解|explain|reason|cause|concept",
    "explanationAllowed": "概念|理解|关系|规律|组成|数量|比较|原理|原因|意义|句意|表达|concept|relationship",
    "explanationTeaching": "因为|所以|原因|为什么|说明|表示|关系|相同|不同|变化|规律|意义|组成|because|therefore|why|means|relationship",
    "practiceGoal": "操作|摆|拼|画|测量|制作|书写|朗读|拼读|表达|造句|排序|计算|练习|掌握|识读|运用|完成|辨认|识别|比较|计数|认读|write|read|practice|build|operate|measure",
    "practiceTask": "操作|摆|拼|画|测量|制作|书写|朗读|拼读|造句|排序|计算|练习|选|填|数一数|圈|连线|比较|读|写|write|read|choose|fill|count|practice|build",
    "social": "合作|协作|同理|换位|倾听|轮流|同伴反馈|不同观点|分工|体谅|帮助他人|collaborat|empathy|take turns",
    "external": "最新|近期|现行|新闻|调查数据|统计数据|研究发现|政策|版本|当年|实时|latest|current data|version|policy",
}


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 16000


def _texts(value: object, required: bool = False) -> bool:
    return isinstance(value, list) and len(value) <= 50 and (not required or bool(value)) and all(_text(x) for x in value)


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("formal skill selection input is invalid")
    return value


def _matches(nodes: list[tuple[str, str]], expression: str) -> list[str]:
    pattern = re.compile(expression, re.I)
    negative = re.compile(r"(?:不要求|不涉及|不使用|不讲解|不讨论|无需|禁止|排除|避免).{0,12}(?:" + expression + ")", re.I)
    return [path for path, value in nodes if pattern.search(value) and not negative.search(value)]


def select_formal_skills(*, teaching_brief: object, grade_boundary: object,
                        grade_boundary_sha256: object) -> dict[str, Any]:
    boundary = _mapping(grade_boundary)
    if (set(boundary) != {"gradeCode", "subject", "curriculumVersion", "boundaryVersion", "skillId",
                         "skillTitle", "learningObjectives", "allowedContent", "excludedContent",
                         "prerequisiteSkills", "language", "estimatedMinutes"}
            or not isinstance(boundary["gradeCode"], str) or not re.fullmatch(r"primary_[1-6]", boundary["gradeCode"])
            or boundary["subject"] not in ("math", "chinese", "english")
            or any(not _text(boundary[key]) for key in ("curriculumVersion", "boundaryVersion", "skillId", "skillTitle"))
            or not _texts(boundary["learningObjectives"], True) or not _texts(boundary["allowedContent"], True)
            or not _texts(boundary["excludedContent"]) or not _texts(boundary["prerequisiteSkills"])
            or boundary["language"] != "zh-CN" or type(boundary["estimatedMinutes"]) is not int
            or not 5 <= boundary["estimatedMinutes"] <= 30 or grade_boundary_sha256 != _sha(boundary)):
        raise ValueError("formal skill grade boundary is invalid")
    brief = _mapping(teaching_brief)
    course = _mapping(brief.get("course"))
    lesson = _mapping(brief.get("lesson"))
    teach = _mapping(_mapping(lesson.get("teachingFlow")).get("teach"))
    questions = lesson.get("questions")
    if (brief.get("schemaVersion") != "mira.learning.formal-runtime-teaching-brief.v1"
            or any(course.get(key) != boundary[key] for key in ("gradeCode", "subject", "skillId"))
            or not _text(course.get("objective")) or not _text(teach.get("sayText"))
            or not _texts(teach.get("keyPoints"), True) or not isinstance(questions, list)
            or len(questions) != 5 or any(not isinstance(q, Mapping) or not _text(q.get("prompt")) for q in questions)):
        raise ValueError("formal skill brief and grade boundary mismatch")
    goals = [("/teachingBrief/course/objective", course["objective"]),
        *[(f"/gradeBoundary/learningObjectives/{i}", text) for i, text in enumerate(boundary["learningObjectives"])]]
    allowed = [(f"/gradeBoundary/allowedContent/{i}", text) for i, text in enumerate(boundary["allowedContent"])]
    tasks = [("/teachingBrief/lesson/teachingFlow/teach/sayText", teach["sayText"]),
        *[(f"/teachingBrief/lesson/teachingFlow/teach/keyPoints/{i}", text) for i, text in enumerate(teach["keyPoints"])],
        *[(f"/teachingBrief/lesson/questions/{i}/prompt", q["prompt"]) for i, q in enumerate(questions)]]
    explanation = [_matches(goals, SKILL_SIGNALS["explanationGoal"]),
        _matches(allowed, SKILL_SIGNALS["explanationAllowed"]), _matches(tasks, SKILL_SIGNALS["explanationTeaching"])]
    practice = [_matches(goals + allowed, SKILL_SIGNALS["practiceGoal"]), _matches(tasks, SKILL_SIGNALS["practiceTask"])]
    social = [_matches(goals + allowed, SKILL_SIGNALS["social"]), _matches(tasks, SKILL_SIGNALS["social"])]
    research = [_matches(goals + allowed, SKILL_SIGNALS["external"]), _matches(tasks, SKILL_SIGNALS["external"])]
    explanation_fits = all(explanation)
    practice_fits = bool(practice[0]) and len(practice[1]) >= 2
    primary_method = "feynman-learning" if explanation_fits else "workshop-style" if practice_fits else None
    decisions = []
    for skill_id in BUILTIN_SKILL_IDS:
        status, reason, paths = "not_applicable", "", []
        if skill_id in BASE_SKILL_IDS:
            status, reason, paths = "selected", "formal_primary_baseline", ["/gradeBoundary/gradeCode", "/gradeBoundary/subject"]
        elif skill_id == "understanding-by-design":
            status, reason, paths = "selected", "bounded_goal_and_assessment_backward_design", ["/teachingBrief/course/objective", "/teachingBrief/lesson/questions"]
        elif skill_id == "feynman-learning":
            if explanation_fits:
                status, reason, paths = "selected", "explanation_goal_allowed_and_taught", sum(explanation, [])
            else:
                reason = "no_supported_explanation_cycle"
        elif skill_id == "workshop-style":
            if primary_method == "workshop-style":
                status, reason, paths = "selected", "practice_goal_and_repeated_tasks", sum(practice, [])
            else:
                reason = "primary_method_feynman_wins" if explanation_fits else "no_supported_practice_sequence"
        elif skill_id == "social-emotional-learning":
            if all(social):
                status, reason, paths = "selected", "social_goal_and_concrete_learning_situation", sum(social, [])
            else:
                reason = "no_explicit_social_learning_situation"
        elif skill_id == "deep-research":
            if all(research):
                status, reason, paths = "selected", "external_fact_goal_and_teaching_evidence", sum(research, [])
            else:
                reason = "stable_subject_formal_source_gate_suffices"
        elif skill_id == "lecture-style":
            reason, paths = "dense_masterclass_conflicts_with_primary_contract", ["/gradeBoundary/gradeCode"]
        elif skill_id in ("pro-editing", "stage-dsl", "slide-dsl"):
            status, reason = "deferred", "only_after_persisted_page_requires_repair"
        elif skill_id in ("pptx-import", "style-clone", "page-clone"):
            reason = "no_authorized_layout_source_in_generated_single_course"
        elif skill_id == "teacher-style-clone":
            reason = "no_authorized_teacher_material"
        elif skill_id in ("curriculum-planner", "spiral-curriculum"):
            reason = "single_course_not_series_or_cross_course_memory"
        elif skill_id == "build-personal-skill":
            reason = "no_personal_history_or_skill_creation_request"
        elif skill_id == "vocational":
            reason, paths = "primary_subject_not_occupational_procedure", ["/gradeBoundary/subject"]
        decisions.append({"skillId": skill_id, "status": status, "reasonCode": reason, "evidencePaths": paths})
    grade = int(boundary["gradeCode"][-1])
    plan = {"schemaVersion": "mira.openmaic.skill-selection.v1", "registryId": SKILL_REGISTRY_ID,
        "inputSha256": _sha({"teachingBrief": brief, "gradeBoundary": boundary}),
        "gradeBoundarySha256": grade_boundary_sha256,
        "gradeBand": "lower_primary" if grade <= 2 else "middle_primary" if grade <= 4 else "upper_primary",
        "primaryMethod": primary_method,
        "selectedSkillIds": [item["skillId"] for item in decisions if item["status"] == "selected"],
        "decisions": decisions}
    return {**plan, "planSha256": _sha(plan)}


def skill_selection_plan(value: object) -> dict[str, Any]:
    """Validate an untrusted receipt shape before its generation is available."""

    plan = _mapping(value)
    if (set(plan) != {"schemaVersion", "registryId", "inputSha256", "gradeBoundarySha256",
                     "gradeBand", "primaryMethod", "selectedSkillIds", "decisions", "planSha256"}
            or plan["schemaVersion"] != "mira.openmaic.skill-selection.v1"
            or plan["registryId"] != SKILL_REGISTRY_ID
            or plan["gradeBand"] not in ("lower_primary", "middle_primary", "upper_primary")
            or plan["primaryMethod"] not in (None, "feynman-learning", "workshop-style")
            or any(not isinstance(plan[key], str) or not re.fullmatch(r"[0-9a-f]{64}", plan[key])
                   for key in ("inputSha256", "gradeBoundarySha256", "planSha256"))):
        raise ValueError("invalid formal skill selection plan")
    decisions = plan["decisions"]
    if (not isinstance(decisions, list) or len(decisions) != len(BUILTIN_SKILL_IDS)
            or any(not isinstance(item, Mapping) or set(item) != {"skillId", "status", "reasonCode", "evidencePaths"}
                   or item["skillId"] != skill_id or item["status"] not in ("selected", "not_applicable", "deferred")
                   or not _text(item["reasonCode"]) or not _texts(item["evidencePaths"])
                   or any(not path.startswith(("/teachingBrief/", "/gradeBoundary/")) for path in item["evidencePaths"])
                   for item, skill_id in zip(decisions, BUILTIN_SKILL_IDS))
            or plan["selectedSkillIds"] != [item["skillId"] for item in decisions if item["status"] == "selected"]
            or any(skill not in plan["selectedSkillIds"] for skill in [*BASE_SKILL_IDS, "understanding-by-design"])
            or [skill for skill in plan["selectedSkillIds"] if skill in ("feynman-learning", "workshop-style")]
               != ([plan["primaryMethod"]] if plan["primaryMethod"] else [])):
        raise ValueError("incomplete formal skill selection decisions")
    unsigned = dict(plan)
    digest = unsigned.pop("planSha256")
    if digest != _sha(unsigned):
        raise ValueError("formal skill selection plan hash mismatch")
    return dict(plan)
