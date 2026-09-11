"""Personal availability is derived from published courses and the child's path.

Production progress and an already completed scope are different states. This
module performs reads only; registration and polling never dispatch generation.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from content.primary_skill_boundaries import boundaries_for

AVAILABILITY_STATUSES = frozenset({"ready", "preparing", "paused", "empty", "not_open", "scope_completed"})


def personal_learning_state(*, grade_code: str, courses: Sequence[Mapping[str, object]],
                            mastery: Mapping[str, str], supply: Mapping[str, object] | None,
                            grade_open: bool = True) -> dict[str, object]:
    if not grade_open:
        return _state("not_open", 0, 0, 0, "这个年级的课程还没有开放。")
    next_skills: set[str] = set()
    for subject in ("chinese", "math", "english"):
        for boundary in boundaries_for(grade_code, subject):
            identity = f"{subject}:{boundary.skill_id}"
            if mastery.get(identity) != "mastered":
                next_skills.add(identity)
                break
    # Different variants are separately playable but do not advance prerequisites.
    unique = {(str(row["id"]), str(row["version"])): row for row in courses}
    def identity(row):
        return f"{row['subject']}:{row['node_code']}"
    new_count = sum(1 for row in unique.values() if identity(row) in next_skills
                    and identity(row) not in mastery)
    review_count = sum(1 for row in unique.values() if identity(row) in mastery
                       and (mastery[identity(row)] == "mastered" or identity(row) in next_skills))
    scope = (supply or {}).get("scopeSkills")
    scope_ids = {f"{row.get('subject')}:{row.get('skillId')}" for row in scope if isinstance(row, Mapping)} if isinstance(scope, list) else set()
    scope_complete = bool(scope_ids) and all(mastery.get(skill) == "mastered" for skill in scope_ids)
    needs_reinforcement = any(identity(row) in next_skills and identity(row) in mastery
                              for row in unique.values())
    if new_count or needs_reinforcement:
        status, message = "ready", "课程已经准备好，可以开始学习。"
    elif scope_complete:
        # A withdrawn asset removes playback availability, not earned mastery.
        status = "scope_completed"
        message = "本单元已完成！可以复习学过的课程，下一单元开放后再继续。" if review_count else "本单元已完成！下一单元开放后再继续。"
    elif (supply or {}).get("paused") is True:
        status, message = "paused", "新课程准备已暂停，已学内容和进度会保留。"
    elif (supply or {}).get("availabilityStatus") == "empty":
        status = "empty"
        message = "暂时没有新课程，可以先复习已经学过的内容。" if review_count else "这里还没有课程，课程准备好后就会出现。"
    elif (supply or {}).get("availabilityStatus") == "not_open":
        status = "not_open"
        message = "下一单元还没有开放，可以先复习已经学过的内容。" if review_count else "这个年级的课程还没有开放，准备好后就能开始学习。"
    else:
        status, message = "preparing", "老师正在为你准备下一节小课，准备好后会自动出现。"
    return _state(status, new_count, review_count, len(unique), message)


def _state(status: str, new_count: int, review_count: int, published: int, message: str) -> dict[str, object]:
    return {"schemaVersion": "mira.learning.availability-state.v1", "availabilityStatus": status,
            "availableCourseCount": new_count + review_count, "newCourseCount": new_count,
            "reviewCourseCount": review_count, "publishedCourseCount": published, "message": message}
