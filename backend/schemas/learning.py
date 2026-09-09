from __future__ import annotations

import hashlib

from core.database import DatabaseRow
from repositories.learning_repository import LearningRepository
from schemas.tasks import task_payload


_SUBJECT_LABELS = {"chinese": "语文", "math": "数学", "english": "英语"}
TEACHING_FLOW_SCHEMA_VERSION = "mira.learning.teaching-flow.v1"
_INPUT_MODES = {
    "numeric": "numeric_text",
    "exact_text": "text",
    "accepted_text": "text",
    "single_choice": "single_choice",
    "sequence": "sequence",
}


def recommendation_payload(course: DatabaseRow) -> dict:
    content = LearningRepository.parse_json(course.get("content_json"), {})
    questions = content.get("questions") if isinstance(content, dict) else []
    question_count = len(questions) if isinstance(questions, list) else 0
    flow = content.get("teachingFlow") if isinstance(content, dict) else None
    if (
        isinstance(flow, dict)
        and flow.get("schemaVersion") == TEACHING_FLOW_SCHEMA_VERSION
        and isinstance(flow.get("guidedQuestionIds"), list)
        and isinstance(flow.get("independentQuestionIds"), list)
    ):
        question_count = len(flow["guidedQuestionIds"]) + len(
            flow["independentQuestionIds"]
        )
    subject = str(course["subject"])
    return {
        "courseId": course["id"],
        "courseVersion": course["version"],
        "gradeCode": course["grade_code"],
        "subject": subject,
        "subjectLabel": _SUBJECT_LABELS.get(subject, subject),
        "nodeCode": course["node_code"],
        "title": course["title"],
        "objective": course["objective"],
        "estimatedMinutes": int(content.get("estimatedMinutes") or 10),
        "questionCount": question_count,
        "intro": str(content.get("intro") or ""),
        "sessionKind": str(content.get("sessionKind") or "lesson"),
        "outcomeMode": str(
            content.get("outcomeMode") or "scored_deterministic"
        ),
    }


def learning_task_payload(task: DatabaseRow | None) -> dict | None:
    if task is None:
        return None
    payload = task_payload(task)
    payload["learningSlot"] = str(task.get("learning_slot") or "core")
    return payload


def lesson_payload(course: DatabaseRow, *, choice_seed: str = "") -> dict:
    recommendation = recommendation_payload(course)
    payload = {
        "courseId": recommendation["courseId"],
        "version": recommendation["courseVersion"],
        "title": recommendation["title"],
        "subject": recommendation["subject"],
        "subjectLabel": recommendation["subjectLabel"],
        "objective": recommendation["objective"],
        "intro": recommendation["intro"],
        "estimatedMinutes": recommendation["estimatedMinutes"],
        "questionCount": recommendation["questionCount"],
        "sessionKind": recommendation["sessionKind"],
        "outcomeMode": recommendation["outcomeMode"],
    }
    teaching_flow = public_teaching_flow_payload(course, choice_seed=choice_seed)
    if teaching_flow is not None:
        payload["teachingFlow"] = teaching_flow
        payload["questionCount"] = len(teaching_flow["guidedQuestionIds"]) + len(
            teaching_flow["independentQuestionIds"]
        )
    return payload


def question_payload(
    question: dict,
    *,
    index: int,
    attempt_number: int,
    choice_seed: str,
) -> dict:
    question_type = str(question.get("type") or "numeric")
    response = question.get("response")
    response = response if isinstance(response, dict) else {}
    payload = {
        "id": question["id"],
        "index": index,
        "type": question_type,
        "prompt": question["prompt"],
        "skill": question.get("skill") or "学科基础",
        "attemptNumber": attempt_number,
        "inputMode": str(
            question.get("inputMode")
            or response.get("inputMode")
            or response.get("kind")
            or _INPUT_MODES.get(question_type, "text")
        ),
        "choices": _public_choices(
            question.get("choices"),
            seed=f"{choice_seed}:{question['id']}",
            expected_sequence=(
                question.get("answer") if question_type == "sequence" else None
            ),
        ),
    }
    return payload


def session_payload(
    session: DatabaseRow,
    *,
    questions: list[dict],
    teaching_flow: dict | None = None,
) -> dict:
    index = int(session.get("current_question_index") or 0)
    answers = LearningRepository.parse_json(session.get("answers_json"), [])
    hint_count = sum(
        1
        for item in answers
        if isinstance(item, dict)
        and item.get("correct") is False
        and int(item.get("attemptNumber") or 0) == 1
    )
    current = None
    if session["status"] != "completed" and index < len(questions):
        attempts = sum(
            1
            for item in answers
            if isinstance(item, dict) and item.get("questionId") == questions[index]["id"]
        )
        current = question_payload(
            questions[index],
            index=index,
            attempt_number=attempts + 1,
            choice_seed=str(session["id"]),
        )
    payload = {
        "id": session["id"],
        "taskId": session["task_id"],
        "courseId": session["course_id"],
        "courseVersion": session["course_version"],
        "status": session["status"],
        "currentQuestionIndex": index,
        "totalQuestions": len(questions),
        "correctCount": int(session.get("correct_count") or 0),
        "attemptedCount": int(session.get("attempted_count") or 0),
        "hintCount": hint_count,
        "currentQuestion": current,
        "startedAt": session["started_at"],
        "completedAt": session.get("completed_at"),
    }
    if teaching_flow is not None:
        payload["teachingFlow"] = teaching_flow
    return payload


def public_teaching_flow_payload(
    course: DatabaseRow,
    *,
    choice_seed: str,
) -> dict | None:
    """Return the verified, child-facing teaching flow without private grading data."""

    content = LearningRepository.parse_json(course.get("content_json"), {})
    if not isinstance(content, dict):
        return None
    flow = content.get("teachingFlow")
    questions = content.get("questions")
    if not isinstance(flow, dict) or not isinstance(questions, list):
        return None
    if flow.get("schemaVersion") != TEACHING_FLOW_SCHEMA_VERSION:
        return None
    demo_question_id = str(flow.get("demoQuestionId") or "")
    demo = next(
        (
            question
            for question in questions
            if isinstance(question, dict)
            and str(question.get("id") or "") == demo_question_id
        ),
        None,
    )
    teach = flow.get("teach")
    recap = flow.get("recap")
    guided_ids = flow.get("guidedQuestionIds")
    independent_ids = flow.get("independentQuestionIds")
    if (
        demo is None
        or not isinstance(teach, dict)
        or not isinstance(recap, dict)
        or not isinstance(guided_ids, list)
        or not isinstance(independent_ids, list)
    ):
        return None

    worked_example = question_payload(
        demo,
        index=0,
        attempt_number=0,
        choice_seed=f"{choice_seed}:worked-example",
    )
    worked_example.pop("index", None)
    worked_example.pop("attemptNumber", None)
    worked_example["answerDisplayText"] = _answer_display_text(demo)
    worked_example["explanation"] = str(demo.get("explanation") or "")
    return {
        "schemaVersion": TEACHING_FLOW_SCHEMA_VERSION,
        "teach": {
            "title": str(teach.get("title") or ""),
            "sayText": str(teach.get("sayText") or ""),
            "keyPoints": [str(item) for item in teach.get("keyPoints") or []],
        },
        "workedExample": worked_example,
        "guidedQuestionIds": [str(item) for item in guided_ids],
        "independentQuestionIds": [str(item) for item in independent_ids],
        "recap": {"sayText": str(recap.get("sayText") or "")},
    }


def _answer_display_text(question: dict) -> str:
    question_type = str(question.get("type") or "")
    answer = question.get("answer")
    if question_type == "accepted_text":
        return " / ".join(str(item) for item in answer or [])
    if question_type in {"single_choice", "sequence"}:
        labels_by_id = {
            str(item.get("id")): str(item.get("label") or "")
            for item in question.get("choices") or []
            if isinstance(item, dict)
        }
        if question_type == "single_choice":
            return labels_by_id.get(str(answer), "")
        return " → ".join(labels_by_id.get(str(item), "") for item in answer or [])
    return "" if answer is None else str(answer)


def report_payload(report: DatabaseRow | None) -> dict | None:
    if report is None:
        return None
    strengths = LearningRepository.parse_json(report.get("strengths_json"), [])
    total_questions = int(report["total_questions"])
    uses_teach_before_practice_roles = total_questions == 4
    return {
        "id": report["id"],
        "childId": report["child_id"],
        "taskId": report["task_id"],
        "sessionId": report["session_id"],
        "courseId": report["course_id"],
        "courseVersion": report["course_version"],
        "courseTitle": str(report.get("course_title") or ""),
        "date": report["learning_date"],
        "gradeCode": report["grade_code"],
        "subject": report["subject"],
        "subjectLabel": _SUBJECT_LABELS.get(
            str(report["subject"]), str(report["subject"])
        ),
        "sessionKind": "lesson",
        "outcomeMode": "scored_deterministic",
        "score": int(report["score"]),
        "correctCount": int(report["correct_count"]),
        "independentCorrectCount": int(report["independent_correct_count"]),
        "hintCount": int(report["hint_count"]),
        "totalQuestions": total_questions,
        "evidenceCount": 2 if uses_teach_before_practice_roles else total_questions,
        "evidencePolicy": (
            "independent_all_correct_v1"
            if uses_teach_before_practice_roles
            else "all_runtime_questions_v1"
        ),
        "assessmentScope": (
            "this_lesson_only" if uses_teach_before_practice_roles else "course_session"
        ),
        "masteryLevel": report["mastery_level"],
        "summary": report["summary"],
        "strengths": strengths if isinstance(strengths, list) else [],
        "nextStep": report["next_step"],
        "createdAt": report["created_at"],
    }


def mastery_payload(mastery: DatabaseRow | None) -> dict | None:
    if mastery is None:
        return None
    return {
        "childId": mastery["child_id"],
        "nodeCode": mastery["node_code"],
        "subject": mastery["subject"],
        "subjectLabel": _SUBJECT_LABELS.get(
            str(mastery["subject"]), str(mastery["subject"])
        ),
        "gradeCode": mastery["grade_code"],
        "attempts": int(mastery["attempts"]),
        "correctCount": int(mastery["correct_count"]),
        "independentCorrectCount": int(mastery["independent_correct_count"]),
        "hintCount": int(mastery["hint_count"]),
        "latestScore": int(mastery["latest_score"]),
        "masteryLevel": mastery["mastery_level"],
        "lastPracticedAt": mastery["last_practiced_at"],
        "nextReviewDate": mastery["next_review_date"],
        "courseId": mastery["course_id"],
        "courseVersion": mastery["course_version"],
        "updatedAt": mastery["updated_at"],
    }


def _public_choices(
    value: object,
    *,
    seed: str,
    expected_sequence: object = None,
) -> list[dict]:
    if not isinstance(value, list):
        return []
    choices: list[dict] = []
    for option in value:
        if isinstance(option, dict):
            option_id = option.get("id", option.get("value"))
            label = option.get("label", option.get("text", option_id))
        else:
            option_id = option
            label = option
        if option_id is None or label is None:
            continue
        choices.append(
            {
                "id": public_choice_id(seed, str(option_id)),
                "label": str(label),
                "_sourceId": str(option_id),
            }
        )
    choices.sort(
        key=lambda option: hashlib.sha256(
            f"{seed}:{option['_sourceId']}".encode("utf-8")
        ).digest()
    )
    expected_ids = (
        [public_choice_id(seed, str(item)) for item in expected_sequence]
        if isinstance(expected_sequence, list)
        else []
    )
    if len(choices) > 1 and [option["id"] for option in choices] == expected_ids:
        choices = choices[1:] + choices[:1]
    return [
        {"id": option["id"], "label": option["label"]}
        for option in choices
    ]


def decode_question_response(
    question: dict,
    response: object,
    *,
    choice_seed: str,
) -> object:
    """Map public opaque choice tokens back to the private course option IDs."""

    question_type = str(question.get("type") or "")
    choices = question.get("choices")
    if question_type not in {"single_choice", "sequence"} or not isinstance(
        choices, list
    ):
        return response
    token_to_source: dict[str, str] = {}
    for option in choices:
        if not isinstance(option, dict) or option.get("id") is None:
            continue
        source_id = str(option["id"])
        token_to_source[public_choice_id(choice_seed, source_id)] = source_id

    if question_type == "single_choice":
        if isinstance(response, dict):
            option_id = response.get("optionId", response.get("value"))
            if option_id is None:
                return response
            decoded = dict(response)
            decoded["optionId"] = token_to_source.get(str(option_id), str(option_id))
            return decoded
        return token_to_source.get(str(response), response)

    if isinstance(response, dict):
        items = response.get("items", response.get("value"))
        if not isinstance(items, list):
            return response
        decoded = dict(response)
        decoded["items"] = [token_to_source.get(str(item), str(item)) for item in items]
        return decoded
    if isinstance(response, list):
        return [token_to_source.get(str(item), str(item)) for item in response]
    return response


def public_choice_id(seed: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{seed}:{source_id}".encode("utf-8")).hexdigest()[:16]
    return f"choice_{digest}"
