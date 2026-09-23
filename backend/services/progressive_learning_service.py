"""Personal learning paths from versioned lessons and trusted server evidence.

This module never calls a Provider. Public request bodies must not be passed to
record_session_evidence: its course, session, questions and answers are the
backend's frozen course and evaluated, completed session. Observation callers
must authenticate and authorize the parent/teacher before invoking this module.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
import time
import unicodedata

from content.progressive_curriculum import (
    CURRICULUM_VERSION, lesson_by_id, lessons_for,
    prerequisite_closure,
)
from core.errors import ApiError


DAY_MS = 24 * 60 * 60 * 1000
MASTERY_WINDOW = 5
MINIMUM_SETS = 2


def lesson_mastery_policy(lesson):
    """The registered lesson may demand more evidence than the global floor."""
    criteria = lesson['assessmentCriteria']
    return {'independentQuestionCount': max(MASTERY_WINDOW,
                int(criteria.get('minimumIndependentAttempts', MASTERY_WINDOW)),
                int(criteria.get('minimumDistinctTasks', MASTERY_WINDOW))),
            'distinctAssessmentSets': MINIMUM_SETS,
            'minimumAccuracy': max(0.8, float(criteria.get('minimumAccuracy', 0.8)))}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _content(course):
    value = course.get("content_json", course.get("content"))
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ValueError("progressive course content must be an object")
    return dict(value)


def _grade_number(grade):
    match = re.fullmatch(r"primary_([1-6])", str(grade))
    if match is None:
        raise ApiError("progressive_grade_invalid", "请选择一至六年级", 400)
    return int(match.group(1))


def _question_fingerprint(question):
    def normalize(value):
        if isinstance(value, str):
            return " ".join(unicodedata.normalize("NFKC", value).split())
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, Mapping):
            return {key: normalize(item) for key, item in value.items() if key != "id"}
        return value
    # Source-local question ids and order do not manufacture new evidence.
    payload = {key: normalize(question[key]) for key in ("type", "prompt") if key in question}
    if isinstance(question.get("choices"), list):
        payload["choices"] = sorted([normalize(item.get("label"))
                                     for item in question["choices"] if isinstance(item, Mapping)], key=_canonical)
    if isinstance(question.get("objects"), list):
        payload["objects"] = sorted([
            {"shape": normalize(item.get("shape", "circle")),
             "color": normalize(item.get("color", "blue"))}
            for item in question["objects"] if isinstance(item, Mapping)
        ], key=_canonical)
    return _sha(payload)


class ProgressiveLearningService:
    def __init__(self, repository, *, course_validator=None):
        self.repository = repository
        self.course_validator = course_validator

    @staticmethod
    def _scope(child):
        if not child.get("family_id") or not child.get("id"):
            raise ApiError("progressive_child_scope_invalid", "孩子身份不可用", 403)
        return {"family_id": str(child["family_id"]), "child_id": str(child["id"]),
                "curriculum_version": CURRICULUM_VERSION}

    def _lock_child(self, conn, child):
        scope = self._scope(child)
        current = self.repository.lock_child(
            conn, family_id=scope["family_id"], child_id=scope["child_id"]
        )
        if current is None or current.get("grade_code") != child.get("grade_code"):
            raise ApiError("progressive_child_scope_changed", "孩子学习资料已变化，请重新打开", 409)
        return current

    def bind_course(self, conn, *, course, lesson_id, assessment_set_id, now):
        """Call only after formal publication verification; a binding is not proof."""
        from services.progressive_course_generation import lesson_binding

        lesson = lesson_by_id(lesson_id)
        if (course.get("grade_code") != lesson["gradeCode"]
                or course.get("subject") != lesson["subject"]
                or course.get("curriculum_version") != CURRICULUM_VERSION
                or course.get("node_code") != lesson_id
                or _content(course).get("progressiveLesson") != lesson_binding(lesson_id)
                or course.get("status") != "published"
                or course.get("quality_status") != "released"
                or course.get("retired_at") is not None):
            raise ApiError("progressive_course_binding_invalid", "课程与细课次或发布状态不一致", 409)
        if not isinstance(assessment_set_id, str) or not assessment_set_id.strip() or len(assessment_set_id) > 128:
            raise ValueError("a stable assessment set id is required")
        return self.repository.bind_course(conn, binding={
            "course_id": str(course["id"]), "course_version": str(course["version"]),
            "curriculum_version": CURRICULUM_VERSION, "lesson_id": lesson_id,
            "grade_code": lesson["gradeCode"], "subject": lesson["subject"],
            "assessment_set_id": assessment_set_id, "content_sha256": _sha(_content(course)),
            "created_at": int(now), "retired_at": None,
        })

    def binding_for_course(self, conn, *, course):
        binding = self.repository.binding_for_course(
            conn, course_id=str(course["id"]), course_version=str(course["version"])
        )
        if binding is None:
            content = _content(course)
            declaration = content.get("progressiveCurriculum") or {}
            if (course.get("curriculum_version") == CURRICULUM_VERSION
                    or content.get("curriculumVersion") == CURRICULUM_VERSION
                    or content.get("progressiveCurriculumVersion") == CURRICULUM_VERSION
                    or isinstance(content.get("progressiveLesson"), Mapping)
                    and content["progressiveLesson"].get("curriculumVersion") == CURRICULUM_VERSION
                    or isinstance(declaration, Mapping) and declaration.get("version") == CURRICULUM_VERSION):
                raise ApiError("progressive_course_binding_required", "细课次课程尚未完成正式绑定", 409)
            return None
        if (binding["curriculum_version"] != CURRICULUM_VERSION
                or binding["content_sha256"] != _sha(_content(course))
                or binding["grade_code"] != course.get("grade_code")
                or binding["subject"] != course.get("subject")):
            raise ApiError("progressive_course_binding_changed", "课程内容与细课次绑定不一致", 409)
        lesson = lesson_by_id(binding["lesson_id"])
        from services.progressive_course_generation import lesson_binding
        if (lesson["gradeCode"] != binding["grade_code"] or lesson["subject"] != binding["subject"]
                or _content(course).get("progressiveLesson") != lesson_binding(binding["lesson_id"])):
            raise ApiError("progressive_course_binding_changed", "课程体系版本已变化", 409)
        return dict(binding)

    def course_candidates(self, conn, *, lesson_id):
        lesson_by_id(lesson_id)
        candidates = []
        for course in self.repository.course_candidates(
            conn, curriculum_version=CURRICULUM_VERSION, lesson_id=lesson_id
        ):
            try:
                if self.binding_for_course(conn, course=course) is not None:
                    candidates.append(course)
            except ApiError:
                continue
        return candidates

    def _verified_course(self, conn, *, child, lesson_id, difficulty_code, validator):
        if validator is None:
            return None
        candidates = self.course_candidates(conn, lesson_id=lesson_id)
        if not candidates:
            return None
        scope = self._scope(child)
        activity = self.repository.course_activity(conn, **scope, lesson_id=lesson_id)
        used_sets = {row["assessment_set_id"] for row in self.repository.list_evidence(
            conn, **scope, lesson_id=lesson_id,
        )}
        used_sets.update(row["assessment_set_id"] for row in activity.values()
                         if row["session_status"] == "completed" or row["task_status"] == "completed")
        from repositories.learning_placement_repository import LearningPlacementRepository
        used_sets.update(LearningPlacementRepository(self.repository.database).reserved_assessment_sets(
            conn, **scope, lesson_id=lesson_id))
        observed = lesson_by_id(lesson_id)["assessmentMode"] == "observed"
        resumable, fresh, review = [], [], []
        for course in candidates:
            state = activity.get((str(course["id"]), str(course["version"]))) or {}
            if state.get("task_status") in {"cancelled", "rejected", "expired"}:
                continue
            if state.get("session_status") == "in_progress":
                resumable.append(course)
                continue
            if difficulty_code == "basic" and _content(course).get("difficultyCode") != "basic":
                continue
            if course["assessment_set_id"] not in used_sets:
                fresh.append(course)
            elif difficulty_code != "basic" or observed:
                # A mastered learner can revisit a completed classroom. Such a
                # revisit is not a new assessment set or fresh mastery evidence.
                review.append(course)
        resumable.sort(key=lambda course: -int(activity[
            (str(course["id"]), str(course["version"]))
        ].get("session_updated_at") or 0))
        for course in [*resumable, *fresh, *review]:
            if validator(conn, child=child, course=course):
                return {"courseId": str(course["id"]), "courseVersion": str(course["version"])}
        return None

    @staticmethod
    def _mastered(progress, lesson_id):
        return (progress.get(lesson_id) or {}).get("mastery_status") == "mastered"

    def _lesson_payload(self, lesson, progress, *, now):
        row = progress.get(lesson["lessonId"]) or {}
        # Enrolling in a grade establishes its entry baseline. Missing records
        # from earlier grades are not evidence that those foundations are
        # unknown. Keep the baseline separate from earned mastery evidence.
        entry_grade = _grade_number(lesson['gradeCode'])
        blockers = [identifier for identifier in prerequisite_closure(lesson["lessonId"])
                    if _grade_number(lesson_by_id(identifier)['gradeCode']) >= entry_grade
                    and not self._mastered(progress, identifier)]
        mastered = self._mastered(progress, lesson["lessonId"])
        status = ("locked" if blockers else "mastered" if mastered else
                  "needs_practice" if row else "available")
        mastered_at = row.get("mastered_at")
        stability = ("stable" if row.get("stable_at") is not None else
                     "due" if mastered_at is not None and now >= int(mastered_at) + DAY_MS else
                     "not_due")
        return {
            **{key: lesson[key] for key in ("lessonId", "title", "unitTitle", "unitId",
               "gradeCode", "subject", "phase", "sequence", "assessmentMode",
               "prerequisiteLessonIds")},
            "status": status, "canStart": not blockers,
            "message": ("请先完成前面的基础课次。" if blockers else
                        "已经掌握，可以复习。" if mastered else
                        "继续独立练习，掌握后进入下一课。" if row else
                        "从入门课程开始学习。"),
            "blockedByLessonIds": blockers,
            "difficultyCode": "standard" if mastered else "basic",
            "independentEvidenceCount": int(row.get("independent_count") or 0),
            "independentCorrectCount": int(row.get("independent_correct_count") or 0),
            "distinctAssessmentSets": int(row.get("distinct_assessment_sets") or 0),
            "accuracy": row.get("accuracy"), "masteredAt": mastered_at,
            "stabilityStatus": stability, "stableAt": row.get("stable_at"),
            "course": None, "courseId": None, "courseVersion": None,
        }

    def get_path(self, conn, *, child, subject, grade_code=None, now=None,
                 course_validator=None):
        """Start within the selected grade; other grades are catalog previews."""
        if subject not in {"chinese", "math", "english"}:
            raise ApiError("progressive_subject_invalid", "请选择语文、数学或英语", 400)
        grade = grade_code or child["grade_code"]
        _grade_number(grade)
        child_grade = _grade_number(child["grade_code"])
        timestamp = int(time.time() * 1000) if now is None else int(now)
        # Cross-subject prerequisites, when registered, use their own exact ids.
        progress = self.repository.list_progress(conn, **self._scope(child))
        targets = lessons_for(grade, subject)
        rows = [self._lesson_payload(lesson, progress, now=timestamp) for lesson in targets]
        validator = course_validator or self.course_validator
        for row in rows:
            if _grade_number(row["gradeCode"]) != child_grade:
                row.update(status="locked", canStart=False, message="这是其他年级的课程目录，请回当前年级学习。")
            if row["canStart"]:
                course = self._verified_course(conn, child=child, lesson_id=row["lessonId"],
                    difficulty_code=row["difficultyCode"], validator=validator)
                if course is not None:
                    row.update(course=course, **course)
                elif row["status"] == "needs_practice" and row["independentEvidenceCount"] > 0:
                    row["message"] = "下一组独立练习正在准备，已完成的作答会保留。"
            if row["assessmentMode"] == "observed":
                row["observation"] = self._observation_payload(
                    conn, child=child, lesson=lesson_by_id(row["lessonId"]),
                    row=row, now=timestamp, validator=validator,
                )
        next_lesson = next((row for row in rows if row["status"] in {"available", "needs_practice"}), None)
        # Cross-grade remediation needs an explicit scope. Merely having no
        # history must never create an automatic back-to-grade-one assessment.
        assessment = self._assessment_payload([], grade)
        return {"schemaVersion": "mira.learning.progressive-path.v1",
                "curriculumVersion": CURRICULUM_VERSION, "gradeCode": grade,
                "subject": subject, "lessons": rows, "currentGradeLessons": rows,
                "prerequisites": [], "nextLesson": next_lesson,
                "assessment": assessment,
                "masteryPolicy": {"independentQuestionCount": MASTERY_WINDOW,
                    "distinctAssessmentSets": MINIMUM_SETS, "minimumAccuracy": 0.8,
                    "delayedReviewAfterHours": 24,
                    "observedRequiresAuthorizedConfirmation": True}}

    @staticmethod
    def _assessment_payload(prerequisites, grade):
        missing = [row for row in prerequisites if row["status"] != "mastered"
                   and _grade_number(row["gradeCode"]) < _grade_number(grade)]
        tasks = [{"lessonId": row["lessonId"], "title": row["title"],
                  "gradeCode": row["gradeCode"], "subject": row["subject"],
                  "assessmentMode": row["assessmentMode"],
                  "canAssess": row["canStart"], "blockedByLessonIds": row["blockedByLessonIds"],
                  "kind": "prerequisite_assessment"} for row in missing]
        return {"required": bool(tasks), "missingLessonIds": [row["lessonId"] for row in tasks],
                "tasks": tasks, "nextTask": next((row for row in tasks if row["canAssess"]), None)}

    def assessment_eligibility(self, conn, *, child, subject, grade_code=None):
        return self.get_path(conn, child=child, subject=subject, grade_code=grade_code)["assessment"]

    def progression_for_course(self, conn, *, child, course):
        """Compatibility payload for current learning screens, at lesson granularity."""
        binding = self.binding_for_course(conn, course=course)
        if binding is None:
            return None
        progress = self.repository.list_progress(conn, **self._scope(child))
        row = self._lesson_payload(lesson_by_id(binding["lesson_id"]), progress, now=0)
        if _grade_number(course["grade_code"]) != _grade_number(child["grade_code"]):
            row.update(canStart=False, status="locked", message="请选择当前年级的课程；已开始的课堂可以继续。")
        elif row["canStart"] and row["difficultyCode"] == "basic" and _content(course).get("difficultyCode") != "basic":
            row.update(canStart=False, status="locked", message="请先从这部分的入门课程开始。")
        return {"schemaVersion": "mira.learning.progression.v1",
                "curriculumVersion": CURRICULUM_VERSION, "granularity": "lesson",
                "lessonId": row["lessonId"], "skillId": row["lessonId"],
                "sequence": row["sequence"], "learningStatus": row["status"],
                "canStart": row["canStart"], "blockedBySkillIds": row["blockedByLessonIds"],
                "message": row["message"], "difficultyCode": row["difficultyCode"]}

    def assert_course_progression(self, conn, *, child, course):
        """False means legacy/unbound; only the caller can decide legacy access."""
        binding = self.binding_for_course(conn, course=course)
        if binding is None:
            return False
        if _grade_number(course["grade_code"]) != _grade_number(child["grade_code"]):
            raise ApiError("learning_grade_scope_mismatch", "请选择当前年级的课程", 409)
        progress = self.repository.list_progress(conn, **self._scope(child))
        row = self._lesson_payload(lesson_by_id(binding["lesson_id"]), progress, now=0)
        if not row["canStart"]:
            first = lesson_by_id(row["blockedByLessonIds"][0])
            raise ApiError("learning_prerequisite_not_mastered", f"请先学会「{first['title']}」", 409)
        if row["difficultyCode"] == "basic" and _content(course).get("difficultyCode") != "basic":
            raise ApiError("learning_introductory_course_required", "请先从这部分的入门课程开始", 409)
        return True

    def record_session_evidence(self, conn, *, child, course, session, questions, answers, now):
        binding = self.binding_for_course(conn, course=course)
        if binding is None:
            return None
        self._lock_child(conn, child)
        expected = {"family_id": child["family_id"], "child_id": child["id"],
                    "course_id": course["id"], "course_version": course["version"]}
        if (not session.get("id") or session.get("status") != "completed"
                or session.get("completed_at") is None
                or any(str(session.get(key)) != str(value) for key, value in expected.items())):
            raise ApiError("progressive_evidence_session_invalid", "学习证据与已完成课堂不一致", 409)
        persisted = session.get("answers_json")
        persisted = json.loads(persisted) if isinstance(persisted, str) else persisted
        if not isinstance(answers, list) or _canonical(persisted) != _canonical(answers):
            raise ApiError("progressive_evidence_answers_invalid", "学习证据与服务器作答记录不一致", 409)
        lesson = lesson_by_id(binding["lesson_id"])
        content = _content(course)
        source_questions = {str(item["id"]): item for item in content.get("questions", [])
                            if isinstance(item, Mapping) and item.get("id")}
        for question in questions:
            if source_questions.get(str(question.get("id"))) != question:
                raise ApiError("progressive_evidence_question_invalid", "题目与发布课程不一致", 409)
        # Fine lessons use the validated, frozen progressive flow. A legacy
        # teachingFlow cannot assign independent roles to a new lesson.
        independent_ids = {str(step.get("questionId"))
                           for step in content.get("progressiveFlow", [])
                           if isinstance(step, Mapping) and step.get("phase") == "independent"
                           and step.get("questionId")}
        first = {}
        for answer in answers:
            if (isinstance(answer, Mapping) and answer.get("attemptNumber") == 1
                    and isinstance(answer.get("correct"), bool)):
                identifier = str(answer.get("questionId") or "")
                if identifier in first and first[identifier] != answer:
                    raise ApiError("progressive_evidence_answers_invalid", "题目包含冲突的首答记录", 409)
                first[identifier] = answer
        # Issuing a placement reserves its questions permanently. Seeing a
        # known placement question later in class is practice, not fresh proof.
        exposed = {row['question_fingerprint'] for row in conn.execute(
            'SELECT question.question_fingerprint FROM learning_placement_questions AS question '
            'JOIN learning_placement_attempts AS attempt ON attempt.id=question.attempt_id '
            'WHERE attempt.family_id=? AND attempt.child_id=?',
            (child['family_id'], child['id']),
        ).fetchall()}
        for identifier, answer in first.items():
            if identifier not in independent_ids or identifier not in source_questions:
                continue
            # Runtime's hintProvided denotes feedback AFTER an incorrect answer.
            # Excluding those wrong first answers would inflate the success rate.
            hints = int(answer.get("hintCountBeforeAnswer") or 0)
            hints = max(hints, int(answer.get("hintUsedBeforeAnswer") is True))
            fingerprint = _question_fingerprint(source_questions[identifier])
            if fingerprint in exposed:
                continue
            occurred = int(answer.get("answeredAt") or session["completed_at"])
            if occurred > int(now) or occurred < int(session.get("started_at") or 0):
                raise ApiError("progressive_evidence_time_invalid", "学习证据时间与课堂不一致", 409)
            evidence = {**self._scope(child), "lesson_id": binding["lesson_id"],
                "grade_code": lesson["gradeCode"], "subject": lesson["subject"],
                "source_kind": "session_answer", "source_session_id": str(session["id"]),
                "source_question_id": identifier, "question_fingerprint": fingerprint,
                "assessment_set_id": binding["assessment_set_id"], "attempt_number": 1,
                "independent": int(answer.get("independent") is not False),
                "hint_count_before_answer": max(0, hints), "correct": int(answer["correct"]),
                "actor_role": None, "actor_id": None, "occurred_at": occurred}
            self._append(conn, evidence, now=now)
        return self._refresh_progress(conn, child=child, lesson=lesson, now=now)

    def record_placement_evidence(self, conn, *, child, attempt, now):
        """Internal boundary: only completed persisted server-scored attempts."""
        from repositories.learning_placement_repository import LearningPlacementRepository
        self._lock_child(conn, child)
        placements = LearningPlacementRepository(self.repository.database)
        persisted = placements.get_attempt(conn, family_id=child['family_id'], child_id=child['id'], attempt_id=attempt['id'])
        if persisted is None or _canonical(dict(persisted)) != _canonical(dict(attempt)):
            raise ApiError('placement_evidence_invalid', '摸底记录与服务器结果不一致', 409)
        lesson = lesson_by_id(attempt['lesson_id'])
        policy = lesson_mastery_policy(lesson)
        frozen_policy = json.loads(attempt['policy_json']) if isinstance(attempt['policy_json'], str) else attempt['policy_json']
        if (attempt['status'] != 'completed' or attempt['completed_at'] is None
                or attempt['curriculum_version'] != CURRICULUM_VERSION
                or attempt['grade_code'] != child['grade_code']
                or int(attempt['grade_revision']) != int(child['grade_selection_revision'])
                or _grade_number(lesson['gradeCode']) >= _grade_number(child['grade_code'])
                or lesson['assessmentMode'] != 'objective' or frozen_policy != policy):
            raise ApiError('placement_evidence_invalid', '摸底记录与当前基础课次不一致', 409)
        items = placements.items(conn, attempt['id'])
        if (len(items) != policy['independentQuestionCount']
                or len({item['question_fingerprint'] for item in items}) != len(items)
                or len({item['assessment_set_id'] for item in items}) < policy['distinctAssessmentSets']
                or any(item['correct'] not in (0, 1) or not item['response_sha256']
                       or item['answered_at'] is None or int(item['answered_at']) > int(now)
                       or int(item['answered_at']) < int(attempt['created_at']) for item in items)
                or sum(int(item['correct']) for item in items) != int(attempt['correct_count'])):
            raise ApiError('placement_evidence_invalid', '摸底首答记录不完整', 409)
        for item in items:
            question = json.loads(item['snapshot_json']) if isinstance(item['snapshot_json'], str) else item['snapshot_json']
            if _sha(question) != item['snapshot_sha256'] or _question_fingerprint(question) != item['question_fingerprint']:
                raise ApiError('placement_evidence_invalid', '摸底题目记录已变化', 409)
            self._append(conn, {**self._scope(child), 'lesson_id': lesson['lessonId'],
                'grade_code': lesson['gradeCode'], 'subject': lesson['subject'],
                'source_kind': 'placement_answer', 'source_session_id': attempt['id'],
                'source_question_id': item['question_id'], 'question_fingerprint': item['question_fingerprint'],
                'assessment_set_id': item['assessment_set_id'], 'attempt_number': 1,
                'independent': 1, 'hint_count_before_answer': 0, 'correct': int(item['correct']),
                'actor_role': None, 'actor_id': None, 'occurred_at': int(item['answered_at'])}, now=now)
        return self._refresh_progress(conn, child=child, lesson=lesson, now=now)

    def record_observed_confirmation(self, conn, *, child, lesson_id, confirmation_id,
                                     actor_role, actor_id, confirmed, now):
        """Internal boundary: the caller must authenticate and authorize the actor."""
        if actor_role not in {"parent", "teacher"} or not actor_id or type(confirmed) is not bool:
            raise ApiError("progressive_observer_invalid", "需要家长或老师明确确认观察结果", 403)
        if not isinstance(confirmation_id, str) or not confirmation_id or len(confirmation_id) > 128:
            raise ValueError("a stable server-issued confirmation id is required")
        self._lock_child(conn, child)
        lesson = lesson_by_id(lesson_id)
        if lesson["assessmentMode"] != "observed":
            raise ApiError("progressive_observation_not_applicable", "此课次需要独立作答证据", 409)
        prior = self.repository.list_evidence(conn, **self._scope(child), lesson_id=lesson_id)
        replay = next((item for item in prior if item["source_kind"] == "observed_confirmation"
                       and item["source_session_id"] == confirmation_id), None)
        if replay is not None:
            if replay["correct"] != int(confirmed) or replay["actor_role"] != actor_role or str(replay["actor_id"]) != str(actor_id):
                raise ApiError("progressive_observation_changed", "确认内容已变化，请刷新后再确认", 409)
            return self.repository.list_progress(conn, **self._scope(child))[lesson_id]
        progress = self.repository.list_progress(conn, **self._scope(child))
        row = self._lesson_payload(lesson, progress, now=now)
        observation = self._observation_payload(
            conn, child=child, lesson=lesson, row=row, now=now, validator=self.course_validator,
        )
        if not observation["canConfirm"] or observation["confirmationId"] != confirmation_id:
            raise ApiError("progressive_observation_not_ready", "请先完成这节课，并刷新后按实际表现确认", 409)
        evidence = {**self._scope(child), "lesson_id": lesson_id,
            "grade_code": lesson["gradeCode"], "subject": lesson["subject"],
            "source_kind": "observed_confirmation", "source_session_id": confirmation_id,
            "source_question_id": confirmation_id, "question_fingerprint": _sha(["observed", confirmation_id]),
            "assessment_set_id": f"observed:{confirmation_id}"[:128], "attempt_number": 1,
            "independent": 0, "hint_count_before_answer": 0, "correct": int(confirmed),
            "actor_role": actor_role, "actor_id": str(actor_id), "occurred_at": int(now)}
        self._append(conn, evidence, now=now)
        return self._refresh_progress(conn, child=child, lesson=lesson, now=now)

    def _observation_payload(self, conn, *, child, lesson, row, now, validator):
        criteria = list(lesson["learningObjectives"])
        if lesson["assessmentCriteria"].get("promptedAnswersCountAsIndependent") is False:
            criteria.append("请在不示范、不提示的情况下，观察孩子能否独立完成。")
        result = {"criteria": criteria, "canConfirm": False, "confirmationId": None}
        if (validator is None or not row["canStart"]
                or _grade_number(lesson["gradeCode"]) > _grade_number(child["grade_code"])):
            return result
        completed = self.repository.completed_observation_courses(
            conn, **self._scope(child), lesson_id=lesson["lessonId"],
        )
        for course in completed:
            try:
                binding = self.binding_for_course(conn, course=course)
                if binding is None or binding["lesson_id"] != lesson["lessonId"]:
                    continue
                content = _content(course)
                if content.get("assessmentMode") != "observed" or not validator(conn, child=child, course=course):
                    continue
            except (ApiError, ValueError):
                continue
            observed_text = [step["text"] for step in content.get("progressiveFlow", [])
                             if isinstance(step, Mapping) and step.get("phase") == "observe"
                             and isinstance(step.get("text"), str) and step["text"].strip()]
            if observed_text:
                result["criteria"] = [*observed_text, criteria[-1]]
            evidence = [item for item in self.repository.list_evidence(
                conn, **self._scope(child), lesson_id=lesson["lessonId"],
            ) if item["source_kind"] == "observed_confirmation"]
            latest = evidence[-1] if evidence else None
            if (latest is not None and latest["correct"] == 1
                    and int(course["observation_completed_at"]) <= int(latest["occurred_at"])
                    and not (row["stabilityStatus"] == "due"
                             and int(latest["occurred_at"]) < int(row["masteredAt"]) + DAY_MS)):
                return result
            result.update(canConfirm=True, confirmationId="obs_" + _sha([
                self._scope(child), lesson["lessonId"], course["observation_session_id"],
                binding["content_sha256"], latest["id"] if latest else None,
            ]))
            return result
        return result

    def _append(self, conn, evidence, *, now):
        identity = [evidence[key] for key in ("family_id", "child_id", "curriculum_version",
                    "lesson_id", "source_kind", "source_session_id", "question_fingerprint")]
        self.repository.append_evidence(conn, evidence={
            "id": _sha(identity), **evidence,
            "evidence_sha256": _sha({key: value for key, value in evidence.items()
                                     if key != "occurred_at"}), "created_at": int(now),
        })

    def _refresh_progress(self, conn, *, child, lesson, now):
        scope = self._scope(child)
        rows = self.repository.list_evidence(conn, **scope, lesson_id=lesson["lessonId"])
        previous = self.repository.list_progress(conn, **scope).get(lesson["lessonId"]) or {}
        first_by_question = {}
        for row in rows:
            if row["source_kind"] in {"session_answer", "placement_answer"} and row["attempt_number"] == 1:
                first_by_question.setdefault(row["question_fingerprint"], row)
        independent = [row for row in first_by_question.values()
                       if row["independent"] == 1 and row["hint_count_before_answer"] == 0]
        policy = lesson_mastery_policy(lesson)
        window_size = policy['independentQuestionCount']
        window = independent[-window_size:]
        if len(window) == window_size and len({row["assessment_set_id"] for row in window}) == 1:
            latest_set = window[-1]["assessment_set_id"]
            other_set = next((row for row in reversed(independent[:-window_size])
                              if row["assessment_set_id"] != latest_set), None)
            if other_set is not None:
                # Selection never depends on correctness: keep a recent task
                # from another set plus the remaining latest tasks.
                window = [other_set, *window[1:]]
        correct = sum(int(row["correct"] == 1) for row in window)
        sets = len({row["assessment_set_id"] for row in window})
        accuracy = correct / len(window) if window else None
        confirmations = [row for row in rows if row["source_kind"] == "observed_confirmation"
                         and row["actor_role"] in {"parent", "teacher"} and row["actor_id"]]
        if lesson["assessmentMode"] == "observed":
            mastered = bool(confirmations) and confirmations[-1]["correct"] == 1
            status = "mastered" if mastered else "needs_practice" if rows else "unstarted"
        else:
            mastered = (len(window) >= window_size and sets >= policy['distinctAssessmentSets']
                        and accuracy >= policy['minimumAccuracy'])
            status = "mastered" if mastered else "needs_practice" if rows else "unstarted"
        mastered_at = ((previous.get("mastered_at") if previous.get("mastery_status") == "mastered" else None)
                       if mastered else None)
        if mastered and mastered_at is None:
            mastered_at = int(now)
        stable_at = previous.get("stable_at") if mastered else None
        if mastered_at is not None and stable_at is None:
            threshold = int(mastered_at) + DAY_MS
            if lesson["assessmentMode"] == "observed":
                delayed = [row for row in confirmations if row["occurred_at"] >= threshold]
                if delayed and delayed[-1]["correct"] == 1:
                    stable_at = int(delayed[-1]["occurred_at"])
            else:
                prior_sets = {row["assessment_set_id"] for row in independent
                              if row["occurred_at"] <= int(mastered_at)}
                delayed = [row for row in independent if row["occurred_at"] >= threshold
                           and row["assessment_set_id"] not in prior_sets]
                if len(delayed) >= 2 and all(row["correct"] == 1 for row in delayed[-2:]):
                    stable_at = int(delayed[-1]["occurred_at"])
        progress = {**scope, "lesson_id": lesson["lessonId"],
            "grade_code": lesson["gradeCode"], "subject": lesson["subject"],
            "mastery_status": status, "independent_count": len(window),
            "independent_correct_count": correct, "distinct_assessment_sets": sets,
            "total_evidence_count": len(rows), "accuracy": accuracy,
            "mastered_at": mastered_at, "stable_at": stable_at,
            "last_evidence_at": max((row["occurred_at"] for row in rows), default=None),
            "updated_at": int(now)}
        return self.repository.save_progress(conn, progress=progress)
