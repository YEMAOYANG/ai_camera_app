"""Display-only portraits; immutable teaching and paid voice identities stay intact."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from content.teacher_profiles import TeacherProfile

_REGISTRY = json.loads(Path(__file__).with_name("teacher_presentations.v1.json").read_text(encoding="utf-8"))
TEACHER_PRESENTATION_REGISTRY_VERSION = _REGISTRY["registryVersion"]
TEACHER_LIBRARY_SUBJECTS = frozenset({"chinese", "math", "english", "science"})


def teacher_presentation(profile: TeacherProfile) -> dict | None:
    """Require the complete immutable profile key; never infer from a name."""
    key = {"id": profile.profile_id, "version": profile.version, "contentHash": profile.content_hash}
    for item in _REGISTRY["items"]:
        if item["teacherProfile"] == key:
            return deepcopy(item)
    return None


def public_teacher_payload(profile: TeacherProfile) -> dict:
    payload = profile.to_public_payload()
    presentation = teacher_presentation(profile)
    if presentation is not None:
        payload["avatarPath"] = presentation["avatarPath"]
    return payload
