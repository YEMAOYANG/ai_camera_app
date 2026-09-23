"""Pure eligibility rules for the registered, ordered primary skill boundaries.

This policy operates at the existing skill boundary granularity. It does not
claim that a boundary's individual teaching steps have been registered yet.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    PrimarySkillBoundary,
    boundaries_for,
)


def _mastery_level(mastery: Mapping | None, skill_id: str) -> str | None:
    state = (mastery or {}).get(skill_id)
    level = state.get("mastery_level") if isinstance(state, Mapping) else None
    return level if isinstance(level, str) else None


def _first_unmastered(boundaries: Sequence[PrimarySkillBoundary],
                      mastery: Mapping | None) -> int:
    return next((index for index, boundary in enumerate(boundaries)
                 if _mastery_level(mastery, boundary.skill_id) != "mastered"),
                len(boundaries))


def eligible_skill_order(boundaries: Sequence[PrimarySkillBoundary],
                         mastery: Mapping | None) -> list[str]:
    """Return the current skill, then the mastered prefix in review order.

    A later mastery record cannot bypass a gap in the registered sequence.
    Missing courses therefore never justify advancing to a later skill.
    """
    current = _first_unmastered(boundaries, mastery)
    prior = [boundary.skill_id for boundary in boundaries[:current]]
    if current < len(boundaries):
        return [boundaries[current].skill_id, *reversed(prior)]
    return list(reversed(prior))


def course_progression(*, grade_code: str, subject: str, skill_id: str,
                       mastery: Mapping | None) -> dict[str, object]:
    """Describe whether a child can start or review a registered skill.

    ``mastery`` is subject-local and keyed by skill id, with repository-shaped
    mappings containing ``mastery_level``. Unknown skills fail closed; their
    sequence is zero because no registered one-based position exists.
    """
    boundaries = boundaries_for(grade_code, subject)
    index = next((index for index, boundary in enumerate(boundaries)
                  if boundary.skill_id == skill_id), None)
    result: dict[str, object] = {
        "schemaVersion": "mira.learning.progression.v1",
        "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
        "granularity": "skill_boundary",
        "skillId": skill_id,
        "sequence": 0 if index is None else index + 1,
        "learningStatus": "locked",
        "canStart": False,
        "blockedBySkillIds": [],
        "message": "这节课尚未纳入当前年级和学科的学习顺序，暂时不能开始。",
    }
    if index is None:
        return result
    current = _first_unmastered(boundaries, mastery)
    if index > current:
        blockers = [boundary for boundary in boundaries[:index]
                    if _mastery_level(mastery, boundary.skill_id) != "mastered"]
        result.update(
            blockedBySkillIds=[boundary.skill_id for boundary in blockers],
            message=f"请先学会「{boundaries[current].skill_title}」，再按顺序学习这节课。",
        )
        return result
    level = _mastery_level(mastery, skill_id)
    if index < current:
        status, message = "mastered", "这部分已经学会，可以复习巩固。"
    elif level in {"developing", "needs_practice"}:
        status, message = "needs_practice", "继续练习这部分，学会后再进入下一课。"
    else:
        status, message = "available", "前面的基础已经具备，可以开始这部分的学习。" if index else "从这部分开始，循序渐进地学习。"
    result.update(learningStatus=status, canStart=True, message=message)
    return result
