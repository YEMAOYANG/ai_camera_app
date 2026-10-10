"""Freeze original acceptance authoring for the real Native formal pipeline.

No HTTP, worker, database, provider call, publication, generation receipt or
student score is created by this script. Original authoring is deliberately
not presented as a previously generated catalog course. Bind a real isolated
budget grant later; an unbound template must never be sent to Native.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from content.progressive_curriculum import CURRICULUM_VERSION, lesson_by_id
from content.teacher_profiles import get_formal_runtime_teacher_contract
from integrations.openmaic_formal_media import generation_options
from integrations.openmaic_formal_pedagogy import grade_boundary_fields, validate_generation_grade_boundary
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient as Client
from services.progressive_course_generation import (
    COURSE_SCHEMA, canonical, digest, generation_brief, lesson_binding,
    progressive_runtime_teaching_brief, _validate_question,
)
from services.progressive_learning_service import _question_fingerprint

SCHEMA = "mira.eval.formal-flash-frozen-input.v1"
POLICY_ID = "deepseek-v4.1-flash-candidate-v1"
LESSONS = {"math": "M1A01.05", "chinese": "ZH1B02.03"}


def _question(subject, index, guided):
    lesson_id = LESSONS[subject]
    identifier = f"{subject}-{'guided' if guided else 'independent'}-{index + 1}"
    common = {"id": identifier, "knowledgeIds": [lesson_id]}
    if subject == "math":
        # Same taught quantity, genuinely different shape/colour sets. IDs and
        # choice order alone cannot manufacture distinct assessment evidence.
        arrangements = [
            [("circle", "red")] * 5,
            [("square", "blue")] * 5,
            [("triangle", "yellow")] * 5,
            [("circle", "green"), ("square", "green"), ("triangle", "green"), ("circle", "blue"), ("square", "blue")],
            [("circle", "red"), ("circle", "blue"), ("circle", "yellow"), ("circle", "green"), ("square", "red")],
            [("square", "yellow"), ("square", "green"), ("triangle", "red"), ("triangle", "blue"), ("circle", "yellow")],
            [("triangle", "green"), ("circle", "blue"), ("square", "red"), ("square", "green"), ("circle", "red")],
        ]
        offset = index if guided else index + 2
        prompts = [
            "看红色圆形，跟老师一起点，一个物体只点一次。",
            "看看蓝色方块，这次你来点，点过的留下记号。",
            "看黄色三角形，从一个开始，一个一个点，不重复。",
            "这些物体的形状不同，请你逐个点过，不漏掉。",
            "看看颜色不同的这组物体，每个只点一次。",
            "这一组换了颜色和形状，试着把每个物体都点到。",
            "再换一组物体，请你自己点，一个也不漏，一个也不重复。",
        ]
        objects = [{"id": f"{identifier}-object-{n + 1}", "shape": shape, "color": colour}
                   for n, (shape, colour) in enumerate(arrangements[offset])]
        return {**common, "type": "tap_objects", "prompt": prompts[offset],
                "objects": objects, "answer": [obj["id"] for obj in objects],
                "hint": "从一个物体开始，点一个数一个，点过的留下记号。",
                "explanation": "一、二、三、四、五，每个物体只点一次，没有漏掉。",
                "evidence": {"kind": "count_objects"}}
    # These are visual distractor glyphs only, not additional taught words or
    # semantic vocabulary. The sole introduced target is 天. Native must create
    # meaningful scene/glyph pictures and narrated instructions, not text UI.
    distractors = ["大", "夫", "无", "夭", "太", "犬", "木"]
    other = distractors[index if guided else index + 2]
    prompts = [
        "看两张字形图片，跟老师找一找，哪张和天字一样？",
        "这次指一指两张图片里，和刚才天字相同的字形。",
        "换了两张图片，请你自己找出天字的字形。",
        "再看这一对字形图片，点出和刚才学过的天字一样的。",
        "帮老师从这一对图片中，挑出天字的字形。",
        "图片又换了，看看哪张和天字的形状相同。",
        "最后这一对图片，请你自己点出天字的字形。",
    ]
    choices = [{"id": identifier + "-target", "label": "天"},
               {"id": identifier + "-distractor", "label": other}]
    if index % 2:
        choices.reverse()
    return {**common, "type": "single_choice", "prompt": prompts[index if guided else index + 2],
            "choices": choices, "answer": identifier + "-target",
            "hint": "看看天字上面的两横，再看看下面分开的两笔。",
            "explanation": "天字有上面的两横和下面分开的两笔；这里只练辨认这个字形。",
            "evidence": {"kind": "independent_choice"}}


def author_course(subject: str, *, run_id: str) -> tuple[dict, dict]:
    if subject not in LESSONS or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,48}", run_id) is None:
        raise ValueError("invalid original acceptance authoring identity")
    lesson_id = LESSONS[subject]
    generation = generation_brief(lesson_id)
    lesson, binding = generation["lesson"], lesson_binding(lesson_id)
    teach = ("看这些物体，老师一边点一边数：一、二、三、四、五。每个只点一次，点过留下记号。"
             if subject == "math" else
             "看天空的情境图，听老师说天。再看旁边的大字形：上面两横，下面两笔分开。本课只学天字的字形。")
    example = ("老师演示：从一个物体开始，点一个数一个；点过的留记号，到五时所有物体都数过了。"
               if subject == "math" else
               "老师先在天空图旁指给你看天字，再指上面的两横和下面分开的两笔。看两张字形图片，只找天字。")
    intro = "听老师说，看图动手试一试。"
    questions = [_question(subject, n, True) for n in range(2)] + [_question(subject, n, False) for n in range(5)]
    steps = [{"phase": "teach", "text": teach, "knowledgeIds": [lesson_id]},
             {"phase": "example", "text": example, "knowledgeIds": [lesson_id]}]
    for n, question in enumerate(questions):
        steps.append({"phase": "guided" if n < 2 else "independent", "questionId": question["id"],
                      "text": question["prompt"], "knowledgeIds": [lesson_id]})
    steps.append({"phase": "recap", "text": "今天先到这里，可以再听老师示范；学习记录只记录刚才的独立尝试。",
                  "knowledgeIds": [lesson_id]})
    content = {"schemaVersion": COURSE_SCHEMA, "progressiveLesson": binding, "difficultyCode": "basic",
               "assessmentMode": lesson["assessmentMode"], "autoMasteryEligible": True,
               "manualConfirmationRequired": False, "intro": intro, "estimatedMinutes": 10,
               "progressiveFlow": steps, "questions": questions}
    oracle = {}
    for question in questions:
        # Production deterministic task gate. This is not a forged provider
        # independent-review receipt or proof that Native generated the course.
        oracle[question["id"]] = _validate_question(question, lesson=lesson,
            allowed=set(generation["allowedKnowledgeIds"]), introduced=set(lesson["introducedKnowledgeIds"]))
    if subject == "chinese" and any(q["answer"] != next(c["id"] for c in q["choices"] if c["label"] == "天") for q in questions):
        raise ValueError("original glyph oracle changed")
    distinct = {_question_fingerprint(q) for q in questions[2:]}
    if len(distinct) != 5:
        raise ValueError("original independent tasks are not distinct")
    boundary_version = CURRICULUM_VERSION + ":" + binding["lessonSha256"][:24]
    identifier = "formal_eval_" + digest({"runId": run_id, "subject": subject, "content": content})[:24]
    course = {"id": identifier, "version": "original-authoring-v1", "grade_code": "primary_1",
              "subject": subject, "node_code": lesson_id, "title": lesson["title"],
              "objective": lesson["learningObjectives"][0], "curriculum_version": CURRICULUM_VERSION,
              "boundary_version": boundary_version, "generation_request_id": f"{run_id}:{subject}:authoring",
              "content_json": canonical(content)}
    private = {"schemaVersion": "mira.eval.original-authoring-oracle.v1", "source": "original_acceptance_authoring",
               "lessonBinding": binding, "sourceContentSha256": hashlib.sha256(course["content_json"].encode()).hexdigest(),
               "answers": oracle, "assessmentClaim": "this_lesson_only",
               "providerGenerationReceipt": None, "providerIndependentReviewReceipt": None,
               "publishable": False, "studentScoresWritten": False}
    return course, private


def freeze_course(subject: str, *, run_id: str) -> dict:
    course, private = author_course(subject, run_id=run_id)
    policy = Client.selected_professional_creation_policy(POLICY_ID)
    options = generation_options(policy)
    brief, brief_sha, source_sha = progressive_runtime_teaching_brief(course)
    build_id = "formal_eval_build_" + digest([run_id, subject, source_sha])[:24]
    runtime_request_id = f"formal-eval:{run_id}:{subject}:{source_sha[:16]}"
    contract = {"schemaVersion": Client.FORMAL_RUNTIME_CONTRACT_VERSION,
                "authority": "mira_backend_formal_candidate", "buildItemId": build_id,
                "course": {"id": course["id"], "version": course["version"],
                    "packageId": "formal_eval_package_" + digest(build_id)[:24], "packageVersion": 1,
                    "difficultyCode": "basic"},
                "targetFingerprint": digest({"lessonBinding": brief["progressiveLesson"], "creationPolicy": policy}),
                "runtimeRequestId": runtime_request_id, "coursewareAuthority": deepcopy(Client.COURSEWARE_AUTHORITY),
                "professionalCreationPolicy": policy, "sourceCourseContentSha256": source_sha,
                "teachingBriefSha256": brief_sha, "teachingBrief": brief,
                "teacher": get_formal_runtime_teacher_contract(subject),
                "requiredClassroom": deepcopy(Client.FORMAL_RUNTIME_CLASSROOM_CONTRACT),
                "generation": options, "difficultyPolicy": brief["difficultyPolicy"],
                **grade_boundary_fields(course, policy)}
    validate_generation_grade_boundary(contract, course)
    body = {"runtimeRequestId": runtime_request_id, "requirement": canonical(contract),
            "professionalCreationPolicy": policy, "coursewareAuthority": deepcopy(Client.COURSEWARE_AUTHORITY),
            "formalRuntimeContract": deepcopy(Client.FORMAL_RUNTIME_CLASSROOM_CONTRACT),
            "enableWebSearch": True, "enableImageGeneration": options["enableImageGeneration"],
            "enableVideoGeneration": options["enableVideoGeneration"], "enableTTS": False, "agentMode": "generate"}
    return {"schemaVersion": SCHEMA, "runId": run_id, "subject": subject,
            "source": "original_acceptance_authoring", "scope": (
                "一年级逐物对应数到5；不测加减法" if subject == "math" else
                "一年级只辨认天字字形；不是完整天地人课、不测你我他指代"),
            "productionLessonId": LESSONS[subject], "sourceCourse": course,
            "privateOracle": private, "nativeInputTemplate": body,
            "templateSha256": Client.formal_input_sha256(body),
            "readyForPaidDispatch": False, "missing": ["trusted_isolated_paid_budget_binding", "native_input_preflight"],
            "runtimeRequirements": {"sceneTypes": ["slide", "quiz", "interactive"],
                "guidedTasks": 2, "independentTasks": 5, "teacherAndPeers": "1+4",
                "research": "actual search + at least one fetched source",
                "interaction": "all tasks rendered; meaningful picture choices; executed scripts; no prompted mastery",
                "completion": "skill/research/quality/interaction/media receipts and Qwen TTS+ASR for every speech action",
                "minimumPlanningEstimateExternalOperations": 37,
                "planningEstimateBasis": "8 scenes: 16 content/actions + driver + readiness + quality + 16 TTS/ASR + search/fetch",
                "estimateDoesNotProveCompletion": True,
                "notIncludedInMinimum": "extra peer discussion speech, repairs, actual media needs and any additional scenes",
                "remainingCalls": "depends on real Native plan, action count and required reviews/repairs"},
            "businessPublication": False, "studentScoresWritten": False}


def validate_frozen(value: dict) -> None:
    if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA:
        raise ValueError("invalid formal frozen artifact")
    expected = freeze_course(value.get("subject"), run_id=value.get("runId"))
    if value != expected:
        raise ValueError("frozen formal artifact or production registry changed")


def bind_native_input(frozen: dict, *, budget_service, authorization_id: str) -> dict:
    """Read a real grant; no invented ID or grant issuance is possible here."""
    validate_frozen(frozen)
    context = budget_service.authorization_context(authorization_id=authorization_id)
    with budget_service.repository.database.transaction() as conn:
        authorization = budget_service.repository.authorization(conn, authorization_id)
    scope = json.loads(authorization["scope_json"])
    contract = json.loads(frozen["nativeInputTemplate"]["requirement"])
    if (context["purpose"] != "production" or scope["gradeCode"] != "primary_1"
            or scope["subject"] != frozen["subject"] or scope["courseId"] != contract["course"]["id"]
            or scope["courseVersion"] != contract["course"]["version"]
            or scope["productionJobId"] != contract["buildItemId"]
            or scope["userId"] is not None or scope["sessionId"] is not None):
        raise ValueError("isolated grant does not bind this exact formal input")
    body = deepcopy(frozen["nativeInputTemplate"])
    body["paidBudget"] = {"schemaVersion": "mira.learning.paid-budget-binding.v1",
                          "authorizationId": authorization_id, "required": True}
    return body


def write_json_new(path: Path, value) -> str:
    path = path.absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(path, flags, 0o600), "wb") as stream:
        raw = (canonical(value) + "\n").encode()
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subject", choices=["math", "chinese", "both"], default="both")
    args = parser.parse_args(argv)
    subjects = LESSONS if args.subject == "both" else [args.subject]
    files = []
    for subject in subjects:
        frozen = freeze_course(subject, run_id=args.run_id)
        # The private oracle belongs to this operator artifact. It is never
        # part of Native's answer-blind public requirement or POST body.
        path = args.output / (subject + ".frozen.json")
        files.append({"subject": subject, "path": str(path.absolute()), "sha256": write_json_new(path, frozen),
                      "lessonId": LESSONS[subject], "readyForPaidDispatch": False})
    print(canonical({"ok": True, "files": files, "externalCalls": 0, "published": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
