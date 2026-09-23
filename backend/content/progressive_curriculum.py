"""Versioned, offline lesson authority for Mira's progressive primary curriculum.

This registry is deliberately separate from the sealed legacy pilot authorities.
It describes lessons and prerequisites, not published inventory or student mastery.
All public accessors return detached values so consumers cannot mutate authority.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "mira.primary.progressive-curriculum.v1"
CURRICULUM_VERSION = "mira.primary.progressive.v1"
GRADE_CODES = tuple(f"primary_{n}" for n in range(1, 7))
SUBJECTS = ("chinese", "math", "english")
CURRICULUM_PATH = Path(__file__).with_name("progressive_curriculum.v1.json")
_PREFIXES = {"ZH": "chinese", "M": "math", "EN": "english"}
_UNIT_ID = re.compile(r"^(ZH|M|EN)([1-6])([AB])([0-9]{2})$")


def _fail(message: str) -> None:
    raise ValueError(f"invalid progressive curriculum: {message}")


def _texts(value: object, *, required: bool = False) -> bool:
    return (isinstance(value, list) and (bool(value) or not required)
            and all(isinstance(item, str) and bool(item.strip()) for item in value)
            and len(set(value)) == len(value))


def validate_curriculum(payload: object) -> None:
    """Reject malformed, dangling, cyclic, or backwards prerequisite authority."""
    if not isinstance(payload, Mapping):
        _fail("document must be an object")
    if payload.get("schemaVersion") != SCHEMA_VERSION or payload.get("curriculumVersion") != CURRICULUM_VERSION:
        _fail("version mismatch")
    units = payload.get("units")
    if not isinstance(units, list) or not units:
        _fail("units must be a nonempty array")
    unit_ids: set[str] = set()
    lessons: dict[str, Mapping[str, Any]] = {}
    positions: dict[str, tuple[int, int, int, int]] = {}
    subjects: dict[str, str] = {}
    coverage: set[tuple[str, str, str]] = set()
    sequences: dict[tuple[str, str], list[int]] = defaultdict(list)
    for unit in units:
        if not isinstance(unit, Mapping):
            _fail("unit must be an object")
        uid = unit.get("unitId")
        match = _UNIT_ID.fullmatch(uid) if isinstance(uid, str) else None
        if match is None or uid in unit_ids:
            _fail("invalid or duplicate unit id")
        prefix, grade, phase, _ = match.groups()
        expected = (f"primary_{grade}", _PREFIXES[prefix], "upper" if phase == "A" else "lower")
        if (unit.get("gradeCode"), unit.get("subject"), unit.get("phase")) != expected:
            _fail(f"unit metadata mismatch: {uid}")
        if any(not isinstance(unit.get(key), str) or not unit[key].strip() for key in ("strand", "title")):
            _fail(f"missing unit title or strand: {uid}")
        if type(unit.get("sequence")) is not int or unit["sequence"] < 1:
            _fail(f"invalid unit sequence: {uid}")
        sequences[expected[:2]].append(unit["sequence"])
        coverage.add(expected)
        unit_ids.add(uid)
        rows = unit.get("lessons")
        if not isinstance(rows, list) or not rows:
            _fail(f"unit has no lessons: {uid}")
        for index, lesson in enumerate(rows, 1):
            if not isinstance(lesson, Mapping):
                _fail(f"lesson is not an object: {uid}")
            lid = lesson.get("lessonId")
            if lid != f"{uid}.{index:02d}" or lid in lessons:
                _fail(f"lesson id/position mismatch: {lid}")
            if not isinstance(lesson.get("title"), str) or not lesson["title"].strip():
                _fail(f"missing lesson title: {lid}")
            for key in ("learningObjectives", "prerequisiteLessonIds", "introducedKnowledgeIds", "reviewKnowledgeIds"):
                if not _texts(lesson.get(key), required=key in ("learningObjectives", "introducedKnowledgeIds")):
                    _fail(f"invalid {key}: {lid}")
            if lesson["introducedKnowledgeIds"] != [lid]:
                _fail(f"knowledge identity must belong to its lesson: {lid}")
            if lesson.get("assessmentMode") not in ("objective", "observed"):
                _fail(f"invalid assessment mode: {lid}")
            criteria = lesson.get("assessmentCriteria")
            if not isinstance(criteria, Mapping) or criteria.get("requiresObservedConfirmation") != (lesson["assessmentMode"] == "observed"):
                _fail(f"assessment confirmation mismatch: {lid}")
            if any(type(criteria.get(key)) is not int or criteria[key] < 5 for key in ("minimumIndependentAttempts", "minimumDistinctTasks")):
                _fail(f"insufficient independent assessment floor: {lid}")
            if type(criteria.get("minimumAccuracy")) not in (int, float) or not 0.8 <= criteria["minimumAccuracy"] <= 1:
                _fail(f"invalid minimum accuracy: {lid}")
            constraints = lesson.get("constraints")
            if not isinstance(constraints, Mapping) or constraints.get("teachBeforeAssessment") is not True:
                _fail(f"missing teach-before-assessment: {lid}")
            for key in ("introducedTokens", "allowedLetters", "allowedPinyin", "introducedGrammarCodes", "allowedGrammarCodes", "excludedGrammarCodes", "allowedOperations", "assessmentEvidenceKinds", "neutralDistractorTokens"):
                if not _texts(constraints.get(key)):
                    _fail(f"invalid constraint {key}: {lid}")
            if not set(constraints["neutralDistractorTokens"]) <= {"○", "△", "□"}:
                _fail(f"unregistered neutral distractor: {lid}")
            if not set(constraints["allowedOperations"]) <= {"add", "subtract", "multiply", "divide"}:
                _fail(f"unregistered arithmetic operation: {lid}")
            evidence = set(constraints["assessmentEvidenceKinds"])
            if not evidence <= {"token_match", "numeric_expression", "independent_choice", "count_objects"} or bool(evidence) != (lesson["assessmentMode"] == "objective"):
                _fail(f"invalid assessment evidence authority: {lid}")
            if "numeric_expression" in evidence and not constraints["allowedOperations"]:
                _fail(f"numeric evidence lacks an operation scope: {lid}")
            if set(constraints["allowedGrammarCodes"]) & set(constraints["excludedGrammarCodes"]):
                _fail(f"contradictory grammar scope: {lid}")
            for key in ("minimumNumber", "maximumNumber"):
                if key not in constraints or constraints[key] is not None and type(constraints[key]) not in (int, float):
                    _fail(f"invalid numeric scope: {lid}")
            low, high = constraints["minimumNumber"], constraints["maximumNumber"]
            if (low is None) != (high is None) or low is not None and low > high:
                _fail(f"inconsistent numeric scope: {lid}")
            positions[lid] = (int(grade), 0 if phase == "A" else 1, unit["sequence"], index)
            subjects[lid] = expected[1]
            lessons[lid] = lesson
    expected_coverage = {(grade, subject, phase) for grade in GRADE_CODES for subject in SUBJECTS for phase in ("upper", "lower")}
    if coverage != expected_coverage:
        _fail("each grade and subject must contain both learning phases")
    for key, values in sequences.items():
        if sorted(values) != list(range(1, len(values) + 1)):
            _fail(f"noncontiguous unit sequence: {key}")
    for lid, lesson in lessons.items():
        for prior in lesson["prerequisiteLessonIds"]:
            if prior not in lessons:
                _fail(f"dangling prerequisite {prior} in {lid}")
            if prior == lid or subjects[prior] != subjects[lid] or positions[prior] >= positions[lid]:
                _fail(f"cyclic, cross-subject, or backwards prerequisite {prior} in {lid}")
        for prior in lesson["reviewKnowledgeIds"]:
            if prior not in lessons or prior not in _closure_from(lessons, lid):
                _fail(f"review knowledge is not a declared prerequisite: {lid}")


def _closure_from(lessons: Mapping[str, Mapping], lesson_id: str) -> set[str]:
    found: set[str] = set()
    pending = list(lessons[lesson_id]["prerequisiteLessonIds"])
    while pending:
        prior = pending.pop()
        if prior not in found:
            found.add(prior)
            if prior in lessons:
                pending.extend(lessons[prior]["prerequisiteLessonIds"])
    return found


@lru_cache(maxsize=1)
def _authority() -> tuple[dict, dict[str, dict], dict[str, dict], dict]:
    payload = json.loads(CURRICULUM_PATH.read_text(encoding="utf-8"))
    validate_curriculum(payload)
    units: dict[str, dict] = {}
    lessons: dict[str, dict] = {}
    counters: dict[tuple[str, str], int] = defaultdict(int)
    for unit in payload["units"]:
        units[unit["unitId"]] = unit
        for lesson in unit["lessons"]:
            key = (unit["gradeCode"], unit["subject"])
            counters[key] += 1
            lessons[lesson["lessonId"]] = {
                **lesson, "curriculumVersion": CURRICULUM_VERSION,
                **{key: unit[key] for key in ("unitId", "gradeCode", "subject", "phase", "strand")},
                "unitTitle": unit["title"], "unitSequence": unit["sequence"], "sequence": counters[key],
            }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    identity = {"schemaVersion": SCHEMA_VERSION, "curriculumVersion": CURRICULUM_VERSION,
                "datasetSha256": digest, "identitySha256": digest,
                "unitCount": len(units), "lessonCount": len(lessons)}
    return payload, units, lessons, identity


def load_curriculum() -> dict:
    return copy.deepcopy(_authority()[0])


def all_lessons() -> list[dict]:
    return copy.deepcopy(list(_authority()[2].values()))


def lesson_by_id(lesson_id: str) -> dict:
    if not isinstance(lesson_id, str) or lesson_id not in _authority()[2]:
        raise ValueError("unregistered progressive lesson")
    return copy.deepcopy(_authority()[2][lesson_id])


def unit_by_id(unit_id: str) -> dict:
    if not isinstance(unit_id, str) or unit_id not in _authority()[1]:
        raise ValueError("unregistered progressive unit")
    return copy.deepcopy(_authority()[1][unit_id])


def lessons_for(grade_code: str, subject: str | None = None) -> list[dict]:
    if grade_code not in GRADE_CODES or subject is not None and subject not in SUBJECTS:
        raise ValueError("unregistered progressive grade or subject")
    return [lesson for lesson in all_lessons() if lesson["gradeCode"] == grade_code and (subject is None or lesson["subject"] == subject)]


def prerequisite_closure(lesson_id: str) -> list[str]:
    lesson_by_id(lesson_id)
    lessons = _authority()[2]
    found = _closure_from(lessons, lesson_id)
    return [lid for lid in lessons if lid in found]


def curriculum_identity() -> dict:
    return copy.deepcopy(_authority()[3])
