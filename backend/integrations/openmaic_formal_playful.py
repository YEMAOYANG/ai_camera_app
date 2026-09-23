"""New-job teaching experience policy; no fixed game mechanics or course content."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

PLAYFUL_LEARNING_POLICY = {
    "schemaVersion": "mira.openmaic.playful-learning.v1",
    "policyId": "mira-primary-playful-exploration.v1",
    "aiDesigned": True,
    "maxQuizScenes": 2,
    "lockedAssessmentPreserved": True,
    "minimumReplayableGames": 1,
    "threeDUsage": "teaching_need",
}
REQUIRED_3D_PLAYFUL_LEARNING_POLICY = {
    **deepcopy(PLAYFUL_LEARNING_POLICY),
    "schemaVersion": "mira.openmaic.playful-learning.v2",
    "policyId": "mira-primary-playful-3d.v2",
    "threeDUsage": "required",
    "minimumThreeDScenes": 1,
}


def playful_quality_context(generation: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Rebuild Native's review context from the frozen generation contract."""
    if generation is None:
        return None
    policy = generation.get("professionalCreationPolicy")
    if not isinstance(policy, Mapping) or "playfulLearningPolicy" not in policy:
        return None
    from integrations.openmaic_formal_media import professional_policy
    from integrations.openmaic_formal_quality import quality_sha

    frozen_policy = professional_policy(policy)["playfulLearningPolicy"]
    brief = generation.get("teachingBrief")
    if not isinstance(brief, Mapping) or quality_sha(brief) != generation.get("teachingBriefSha256"):
        raise ValueError("playful review teaching brief is not frozen")
    course, lesson = brief.get("course"), brief.get("lesson")
    flow = lesson.get("teachingFlow") if isinstance(lesson, Mapping) else None
    if not isinstance(course, Mapping) or course.get("subject") not in {"math", "chinese", "english"} or not isinstance(flow, Mapping):
        raise ValueError("playful review teaching context is missing")
    groups = [flow.get("guidedQuestionIds"), flow.get("independentQuestionIds")]
    progressive = brief.get("schemaVersion") == "mira.learning.formal-runtime-teaching-brief.progressive.v1"
    if any(not isinstance(group, list) or any(
            not isinstance(q, str) or not q.strip() or len(q) > 128 for q in group) for group in groups):
        raise ValueError("playful review requires the frozen two question groups")
    if progressive:
        from services.progressive_course_generation import lesson_binding
        binding = lesson_binding(str(course.get("skillId") or ""))
        if (brief.get("progressiveLesson") != binding
                or lesson.get("assessmentMode") != binding["assessmentMode"]):
            raise ValueError("playful progressive lesson binding drifted")
        if flow.get("schemaVersion") != "mira.learning.progressive-teaching-flow.v1":
            raise ValueError("playful progressive teaching flow drifted")
        mode = lesson.get("assessmentMode")
        if mode == "observed":
            if (any(groups) or lesson.get("autoMasteryEligible") is not False
                    or lesson.get("manualConfirmationRequired") is not True
                    or not isinstance(flow.get("observations"), list) or not flow["observations"]):
                raise ValueError("playful observed lesson must preserve explicit confirmation")
        elif (mode != "objective" or not 1 <= len(groups[0]) <= 4
                or not 5 <= len(groups[1]) <= 10 or sum(map(len, groups)) > 14
                or lesson.get("autoMasteryEligible") is not True
                or lesson.get("manualConfirmationRequired") is not False):
            raise ValueError("playful progressive lesson needs guided and independent evidence")
    elif any(len(group) != 2 for group in groups):
        raise ValueError("playful review requires the frozen two question groups")
    ids = [q for group in groups for q in group]
    questions = lesson.get("questions")
    if (len(set(ids)) != len(ids) or not isinstance(questions, list)
            or progressive and len(questions) != len(ids)
            or any(sum(isinstance(q, Mapping) and q.get("id") == question_id for q in questions) != 1 for question_id in ids)):
        raise ValueError("playful review assessment identities drifted")
    context = {"policy": deepcopy(frozen_policy), "subject": course["subject"],
               "guidedQuestionIds": deepcopy(groups[0]), "independentQuestionIds": deepcopy(groups[1])}
    if progressive:
        context.update(assessmentMode=lesson["assessmentMode"],
                       manualConfirmationRequired=lesson.get("manualConfirmationRequired"),
                       progressiveLesson=deepcopy(brief.get("progressiveLesson")))
    return context


def playful_generation_kwargs(generation: object) -> dict[str, Any]:
    """Thread authority into receipt reads only for the versioned opt-in path."""
    policy = generation.get("professionalCreationPolicy") if isinstance(generation, Mapping) else None
    return {"generation_contract": generation} if isinstance(policy, Mapping) and "playfulLearningPolicy" in policy else {}


def validate_playful_classroom(generation: Mapping, classroom: Mapping) -> None:
    """Enforce the new artifact structure without reinterpreting old courses.

    This is a structural gate. Real playability, learning mechanisms and visual
    quality still require the existing browser and independent review evidence.
    """
    policy = generation.get("professionalCreationPolicy") or {}
    if "playfulLearningPolicy" not in policy:
        return
    from integrations.openmaic_formal_media import professional_policy
    frozen_policy = professional_policy(policy)["playfulLearningPolicy"]
    scenes = classroom.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("playful course scenes are missing")
    quiz_count = sum(isinstance(s, Mapping) and s.get("type") == "quiz" for s in scenes)
    game_count = sum(
        isinstance(s, Mapping) and s.get("type") == "interactive"
        and isinstance(s.get("content"), Mapping)
        and s["content"].get("widgetType") == "game"
        for s in scenes
    )
    if quiz_count > frozen_policy["maxQuizScenes"]:
        raise ValueError("playful course has too many quiz scenes")
    if game_count < frozen_policy["minimumReplayableGames"]:
        raise ValueError("playful course is missing an AI-designed game")
    if frozen_policy.get("threeDUsage") == "required":
        three_d_count = sum(
            isinstance(s, Mapping) and s.get("type") == "interactive"
            and isinstance(s.get("content"), Mapping)
            and s["content"].get("widgetType") == "visualization3d"
            for s in scenes
        )
        if three_d_count < frozen_policy["minimumThreeDScenes"]:
            raise ValueError("playful course is missing a separate interactive 3D scene")
