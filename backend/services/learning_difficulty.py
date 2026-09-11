"""Personal selection from published difficulty tiers; never generates content."""
from __future__ import annotations

import json
from collections.abc import Mapping

from content.formal_difficulty_policy import require_difficulty


def preferred_difficulty(mastery):
    mastery = mastery or {}
    hints = int(mastery.get('hint_count') or 0)
    if mastery.get('mastery_level') == 'needs_practice' or hints >= 2:
        return 'basic'
    if (mastery.get('mastery_level') == 'mastered' and hints == 0
            and int(mastery.get('independent_correct_count') or 0) >= 2):
        return 'challenge'
    return 'standard'


def course_difficulty(course):
    content = course.get('content_json', course.get('content'))
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, Mapping):
        raise ValueError('course content is missing')
    return require_difficulty(content.get('difficultyCode'))


def available_skill_order(boundaries, mastery):
    """The first unmastered skill, followed by already mastered prerequisites."""
    prior = []
    for boundary in boundaries:
        if (mastery.get(boundary.skill_id) or {}).get('mastery_level') != 'mastered':
            return [boundary.skill_id, *reversed(prior)]
        prior.append(boundary.skill_id)
    return list(reversed(prior))


def selection_payload(course, mastery, *, review_fallback=False):
    actual, preferred = course_difficulty(course), preferred_difficulty(mastery)
    fallback = review_fallback or actual != preferred
    return {'difficultyCode': actual, 'preferredDifficultyCode': preferred,
            'mode': 'review' if fallback else 'adaptive',
            'message': '适合的新练习还没有准备好，先复习这节学过的课程。' if fallback else ''}
