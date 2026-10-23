"""Strict review receipt for the intrinsic quality of a complete courseware lesson.

The receipt records human, whole-course play evidence.  It deliberately does
not infer teaching quality from renderer types, hidden state, audio completion,
or the fact that a workbench job was generated successfully.
"""
from __future__ import annotations

import re

from content.textbook_catalog import digest


SCHEMA = "mira.textbook.whole-course-quality-review.v1"
SHA = re.compile(r"^[a-f0-9]{64}$")
DIMENSIONS = (
    "courseArc",
    "characterAndArtContinuity",
    "childVisibleWorld",
    "mechanismDiversity",
    "specificFailureFeedback",
    "targetCannotBeBypassed",
    "newContextTransfer",
)
TOP_FIELDS = {
    "schemaVersion", "status", "policySha256", "sourceSha256", "dimensions",
    "coreActivities", "hardFailures",
}
ACTIVITY_FIELDS = {
    "sceneId", "childTask", "states", "visibleWorldChange", "failureOrAlternative",
    "targetShortcutCheck", "crossPageCarry", "newContextTransfer",
}
STATE_NAMES = ("before", "action", "after", "revise")


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _reject(message):
    raise ValueError(message)


def validate_whole_course_quality_review(review, *, classroom, policy_sha256, source_sha256):
    """Validate exact human evidence and return its immutable digest.

    Every interactive scene is a core activity for this receipt.  Requiring
    exact coverage prevents a reviewer from selecting only the strongest page
    while omitting a weak worksheet-like activity from the whole-course claim.
    """
    if not isinstance(review, dict) or set(review) != TOP_FIELDS:
        _reject("whole-course quality review has an invalid envelope")
    if review.get("schemaVersion") != SCHEMA or review.get("status") != "passed":
        _reject("whole-course quality review is not passed")
    if (not _sha(policy_sha256) or not _sha(source_sha256)
            or review.get("policySha256") != policy_sha256
            or review.get("sourceSha256") != source_sha256):
        _reject("whole-course quality review is not bound to the frozen policy and courseware")
    if review.get("hardFailures") != []:
        _reject("whole-course quality review contains a hard failure")

    dimensions = review.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        _reject("whole-course quality dimensions are incomplete")
    for name in DIMENSIONS:
        result = dimensions[name]
        if (not isinstance(result, dict) or set(result) != {"status", "evidence"}
                or result.get("status") != "passed"
                or not isinstance(result.get("evidence"), list) or not result["evidence"]
                or any(not _text(item) for item in result["evidence"])):
            _reject(f"whole-course quality dimension is not evidenced: {name}")

    if not isinstance(classroom, dict) or not isinstance(classroom.get("scenes"), list):
        _reject("courseware source is invalid")
    if digest(classroom) != source_sha256:
        _reject("whole-course quality review source digest differs from the courseware")
    expected = [scene.get("id") for scene in classroom["scenes"]
                if isinstance(scene, dict) and scene.get("type") == "interactive"]
    if not expected or any(not _text(scene_id) for scene_id in expected) or len(expected) != len(set(expected)):
        _reject("policy v2 courseware needs uniquely identified interactive activities")
    activities = review.get("coreActivities")
    if not isinstance(activities, list) or len(activities) != len(expected):
        _reject("whole-course quality review does not cover every interactive activity")
    actual = [activity.get("sceneId") for activity in activities if isinstance(activity, dict)]
    if len(actual) != len(activities) or len(actual) != len(set(actual)) or actual != expected:
        _reject("whole-course quality review activity identities differ from the courseware")

    for activity in activities:
        if set(activity) != ACTIVITY_FIELDS or not _text(activity.get("childTask")):
            _reject("core activity review has an invalid envelope")
        if any(not _text(activity.get(field)) for field in
               ("visibleWorldChange", "crossPageCarry", "newContextTransfer")):
            _reject("core activity lacks visible change, continuity, or transfer evidence")

        states = activity.get("states")
        if not isinstance(states, dict) or set(states) != set(STATE_NAMES):
            _reject("core activity must preserve before, action, after, and revise states")
        for state_name in STATE_NAMES:
            state = states[state_name]
            if (not isinstance(state, dict) or set(state) != {"description", "evidenceSha256"}
                    or not _text(state.get("description")) or not _sha(state.get("evidenceSha256"))):
                _reject(f"core activity state evidence is invalid: {state_name}")

        alternatives = activity.get("failureOrAlternative")
        if not isinstance(alternatives, list) or not alternatives:
            _reject("core activity needs a real failure or alternative path")
        for path in alternatives:
            if (not isinstance(path, dict)
                    or set(path) != {"kind", "trigger", "visibleOutcome", "teacherFeedback", "revisionStep"}
                    or path.get("kind") not in {"failure", "alternative"}
                    or any(not _text(path.get(field)) for field in
                           ("trigger", "visibleOutcome", "teacherFeedback", "revisionStep"))):
                _reject("core activity failure or alternative evidence is invalid")

        shortcut = activity.get("targetShortcutCheck")
        if (not isinstance(shortcut, dict) or set(shortcut) != {"shortcut", "outcome", "evidence"}
                or not _text(shortcut.get("shortcut")) or not _text(shortcut.get("evidence"))
                or shortcut.get("outcome") not in {"blocked", "not_applicable"}):
            _reject("core activity target-shortcut check is invalid")

    return {"sha256": digest(review), "activityCount": len(activities), "dimensions": list(DIMENSIONS)}
