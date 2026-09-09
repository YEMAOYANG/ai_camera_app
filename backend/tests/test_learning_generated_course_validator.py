from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import unittest
import unicodedata
from dataclasses import replace
from pathlib import Path
from unittest import mock

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_ONE_CONTENT_DATASET_SHA256,
    SUBJECT_LANGUAGE_POLICY_VERSION,
    boundaries_for,
)
from integrations.openmaic_question_adapter import (
    PRIMARY_ONE_ADD_SUB_HOST_SOLVER,
    PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER,
)
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from repositories.learning_question_fingerprint_inventory import (
    provider_question_fingerprint_projection,
)
from services.learning_generated_course_validator import (
    PRIMARY_ONE_HOST_FINGERPRINT_VERSION,
    PRIMARY_ONE_HOST_GATE_RECEIPT_SCHEMA_VERSION,
    PRIMARY_ONE_HOST_GATE_VERSION,
    AcceptedPrimaryOneHostReceipt,
    INDEPENDENT_SOLUTION_SCHEMA_VERSION,
    TEACHING_FLOW_SCHEMA_VERSION,
    GeneratedCourseValidationError,
    LearningGeneratedCourseValidator,
    PrimaryOneHostGateControlError,
    PrimaryOneHostGateDependencyError,
    PrimaryOneHostGateIdentity,
    QuestionPhaseCourseEvidence,
    QuestionPhaseProviderProfileEvidence,
)
from services.learning_catalog_validator import PrimaryOneCourseTarget


def set_teaching_flow(candidate: dict) -> None:
    question_ids = [
        question["id"] for question in candidate["content"]["questions"]
    ]
    candidate["content"]["teachingFlow"] = {
        "schemaVersion": TEACHING_FLOW_SCHEMA_VERSION,
        "teach": {
            "title": "先理解方法",
            "sayText": "先观察题目给出的信息与运算符号，再选择合适的方法分步完成。",
            "keyPoints": ["读清条件", "分步完成", "完成后检查"],
        },
        "demoQuestionId": question_ids[0],
        "guidedQuestionIds": question_ids[1:3],
        "independentQuestionIds": question_ids[3:5],
        "recap": {"sayText": "回顾今天的方法：读清题意，按步骤完成并检查。"},
    }


def math_candidate() -> dict:
    questions = []
    for index, (expression, answer) in enumerate(
        (("238+157", "395"), ("602-278", "324"), ("36*4", "144"), ("96/3", "32"), ("4*28", "112")),
        start=1,
    ):
        questions.append(
            {
                "id": f"generated_math_g3_q{index}",
                "type": "numeric",
                "prompt": f"计算第 {index} 题：{expression} = ?",
                "answer": answer,
                "skill": "三位数与乘除计算",
                "hint": "先看清运算符号，再分步计算。",
                "explanation": f"按运算规则计算，结果是 {answer}。",
                "verificationExpression": expression,
                "evaluation": {
                    "expected": answer,
                    "normalization": ["trim", "remove_grouping_separators"],
                },
            }
        )
    candidate = {
        "id": "candidate_primary_3_math_multi_digit_operations_req1",
        "version": "0.0.0-candidate",
        "gradeCode": "primary_3",
        "subject": "math",
        "nodeCode": "multi_digit_operations",
        "title": "多位数计算练习",
        "objective": "准确完成三位数加减与基础乘除计算。",
        "status": "unverified",
        "content": {
            "schemaVersion": "mira.learning.course.v1",
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "sourceAuthority": {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_candidate",
                "textbookDependency": "none",
            },
            "reviewPolicy": "programmatic_guarded",
            "intro": "今天完成五道多位数计算题。",
            "estimatedMinutes": 10,
            "questions": questions,
        },
    }
    set_teaching_flow(candidate)
    return candidate


def math_boundary() -> dict:
    return {
        "gradeCode": "primary_3",
        "subject": "math",
        "skillId": "multi_digit_operations",
        "learningObjectives": ["准确完成三位数加减与基础乘除计算。"],
        "allowedQuestionSkills": ["三位数与乘除计算"],
        "excludedContent": ["初中方程"],
        "questionCount": 5,
    }


def independent_solution(candidate: dict, *, subject: str = "math") -> dict:
    validator = LearningGeneratedCourseValidator()
    return {
        "schemaVersion": INDEPENDENT_SOLUTION_SCHEMA_VERSION,
        "solver": "kimi-independent-pass",
        "independentFromGeneration": True,
        "verificationRequestId": "test-verification-request",
        "publicQuestionHash": validator.public_question_hash(candidate),
        "gradeCode": candidate["gradeCode"],
        "subject": subject,
        "skillId": candidate["nodeCode"],
        "teachingReview": {"passed": True, "issues": []},
        "answers": [
            {
                "questionId": question["id"],
                "answer": question["answer"],
                **(
                    {"derivedExpression": question["verificationExpression"]}
                    if question["type"] == "numeric"
                    else {}
                ),
            }
            for question in candidate["content"]["questions"]
        ],
    }


def english_candidate() -> dict:
    candidate = math_candidate()
    candidate.update(
        {
            "id": "candidate_primary_3_english_daily_routines_req1",
            "subject": "english",
            "nodeCode": "daily_routines",
            "title": "日常作息",
            "objective": "理解并使用小学阶段常见日常活动词组。",
        }
    )
    candidate["content"]["intro"] = "Listen and choose the daily activity."
    candidate["content"]["questions"] = []
    rows = (
        ("get_up", "Which phrase means 起床?", "get up"),
        ("breakfast", "Which phrase means 吃早饭?", "have breakfast"),
        ("school", "Which phrase means 去上学?", "go to school"),
        ("homework", "Which phrase means 做作业?", "do homework"),
        ("bed", "Which phrase means 上床睡觉?", "go to bed"),
    )
    for index, (answer, prompt, label) in enumerate(rows, start=1):
        candidate["content"]["questions"].append(
            {
                "id": f"generated_english_g3_q{index}",
                "type": "single_choice",
                "prompt": prompt,
                "answer": answer,
                "skill": "日常活动词组",
                "hint": "Listen for the key action.",
                "explanation": f"{label} is the matching phrase.",
                "choices": [
                    {"id": "distractor_a", "label": "read a book"},
                    {"id": answer, "label": label},
                    {"id": "distractor_b", "label": "play football"},
                ],
                "evaluation": {
                    "expectedOptionId": answer,
                    "normalization": ["trim", "casefold"],
                },
            }
        )
    set_teaching_flow(candidate)
    return candidate


_FORMAL_SKILLS = (
    "pinyin_syllables",
    "pinyin_initials_syllables",
    "characters_words",
    "simple_sentences",
    "number_sense_20",
    "addition_subtraction_20",
    "shapes_position",
    "letters_sounds",
    "greetings",
    "numbers_colors",
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _provider_profile(
    *,
    name: str = "kimi",
    model: str = "moonshot-v1-8k",
    base_url: str = "https://api.moonshot.cn/v1",
    api_key_env: str = "KIMI_API_KEY",
    timeout_ms: int = 60_000,
    max_tokens: int = 8_000,
    temperature: float = 0.2,
) -> QuestionPhaseProviderProfileEvidence:
    payload = {
        "name": name,
        "model": model,
        "baseUrl": base_url,
        "apiKeyEnv": api_key_env,
        "timeoutMs": timeout_ms,
        "maxTokens": max_tokens,
        "temperature": temperature,
    }
    return QuestionPhaseProviderProfileEvidence(
        name=name,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        timeout_ms=timeout_ms,
        max_tokens=max_tokens,
        temperature=temperature,
        profile_hash=hashlib.sha256(_canonical_json(payload).encode()).hexdigest(),
    )


def _choice(prompt: str, answer: str, distractors: tuple[str, ...]) -> dict:
    labels = [*distractors, answer]
    choices = [
        {"id": f"option_{index + 1}", "label": label}
        for index, label in enumerate(labels)
    ]
    answer_id = choices[-1]["id"]
    return {
        "type": "single_choice",
        "prompt": prompt,
        "answer": answer_id,
        "hint": "先根据题目条件判断，再独立作答。",
        "explanation": f"提交后核对，正确内容是 {answer}。",
        "choices": choices,
        "evaluation": {
            "expectedOptionId": answer_id,
            "normalization": ["trim", "casefold"],
        },
    }


def _numeric(prompt: str, expression: str, answer: str) -> dict:
    return {
        "type": "numeric",
        "prompt": prompt,
        "answer": answer,
        "hint": "先判断运算关系，再独立计算。",
        "explanation": f"提交后复算，结果是 {answer}。",
        "verificationExpression": expression,
        "evaluation": {
            "expected": answer,
            "normalization": ["trim", "remove_grouping_separators"],
        },
    }


def _formal_rows(skill_id: str) -> tuple[list[dict], str, str]:
    rows: dict[str, list[dict]] = {
        "pinyin_syllables": [
            _choice("嘴巴张大时读哪个单韵母？", "a", ("o", "e")),
            _choice("嘴巴拢圆时读哪个单韵母？", "o", ("a", "e")),
            _choice("嘴巴扁平时读哪个单韵母？", "e", ("a", "o")),
            _choice("听到“啊”的基本读音，对应哪个单韵母？", "a", ("o", "e")),
            _choice("听到“鹅”的基本读音，对应哪个单韵母？", "e", ("a", "o")),
        ],
        "pinyin_initials_syllables": [
            _choice("声母 b 和韵母 a 拼成哪个简单音节？", "ba", ("bo", "pa")),
            _choice("声母 p 和韵母 o 拼成哪个简单音节？", "po", ("pa", "bo")),
            _choice("声母 m 和韵母 e 拼成哪个简单音节？", "me", ("ma", "mo")),
            _choice("声母 f 和韵母 a 拼成哪个简单音节？", "fa", ("fo", "ma")),
            _choice("声母 y 和韵母 e 拼成哪个简单音节？", "ye", ("ya", "wo")),
        ],
        "characters_words": [
            _choice("“人”的读音是哪一个？", "rén", ("rì", "kǒu")),
            _choice("“河”的偏旁是哪一个？", "氵", ("亻", "女")),
            _choice("“喝”常和哪个字搭配成词？", "水", ("山", "月")),
            _choice("“大”的反义词是哪一个？", "小", ("上", "下")),
            _choice("“书”前面可以用哪个量词？", "本", ("朵", "个")),
        ],
        "simple_sentences": [
            _choice("哪一句是完整的陈述句？", "小鸟飞走了。", ("小鸟。", "飞走了？")),
            _choice("哪一句是完整的问句？", "你去上学？", ("你去上学。", "去上学？")),
            _choice("哪一句有明确对象和完整谓语？", "小猫喝水。", ("小猫。", "喝水？")),
            _choice("想询问天气，应选择哪一句？", "今天下雨？", ("今天下雨。", "下雨？")),
            _choice("想陈述动作，应选择哪一句？", "妈妈开门。", ("妈妈？", "开门。")),
        ],
        "number_sense_20": [
            _choice("14和17相比，哪个数更大？", "17", ("14", "相等")),
            _choice("数字按0到20的顺序排列，数字18的后一个数是几？", "19", ("17", "20")),
            _choice("16由几个十和几个一组成？", "1个十和6个一", ("1个十和5个一", "2个十")),
            _choice("9和12的大小关系是哪一个？", "9小于12", ("9大于12", "9等于12")),
            _choice("20由几个十和几个一组成？", "2个十和0个一", ("1个十和0个一", "0个十和2个一")),
        ],
        "addition_subtraction_20": [
            _numeric("计算7+5。", "7+5", "12"),
            _choice("9+4的结果是哪一个？", "13", ("12", "14")),
            _choice("14-6的结果是哪一个？", "8", ("7", "9")),
            _numeric("小红有6支笔，又得到8支，现在一共有多少支？", "6+8", "14"),
            _numeric("独立计算15-7。", "15-7", "8"),
        ],
        "shapes_position": [
            _choice("有三个角的图形叫什么？", "三角形", ("圆形", "正方形")),
            _choice("小猫在小狗左边，小狗在小猫哪一边？", "右", ("左", "上")),
            _choice("球在盒子上方，盒子在球的哪一边？", "下", ("上", "左")),
            _choice("有四个直角而且四条边相等的是什么图形？", "正方形", ("圆形", "三角形")),
            _choice("小鸟在树的左边，树在小鸟哪一边？", "右", ("左", "下")),
        ],
        "letters_sounds": [
            _choice("大写字母 A 对应哪个小写字母？", "a", ("b", "e")),
            _choice("大写字母 B 对应哪个小写字母？", "b", ("d", "p")),
            _choice("哪个单词以字母 C 的首音开头？", "cat", ("dog", "egg")),
            _choice("大写字母 D 对应哪个小写字母？", "d", ("b", "p")),
            _choice("哪个单词以字母 E 的首音开头？", "egg", ("cat", "fish")),
        ],
        "greetings": [
            _choice("见面打招呼“你好”应说哪一句英语？", "Hello.", ("Good morning.", "How are you?")),
            _choice("早晨问候应说哪一句英语？", "Good morning.", ("Hello.", "How are you?")),
            _choice("询问对方近况应说哪一句英语？", "How are you?", ("Hello.", "Good morning.")),
            _choice("表示“我很好，谢谢”应说哪一句英语？", "I'm fine, thank you.", ("How are you?", "Hello.")),
            _choice("介绍自己的名字是Mia，应说哪一句英语？", "My name is Mia.", ("Hello Mia.", "How are you Mia?")),
        ],
        "numbers_colors": [
            _choice("数字1对应哪个英语数词？", "one", ("two", "ten")),
            _choice("数字7对应哪个英语数词？", "seven", ("six", "eight")),
            _choice("数字12对应哪个英语数词？", "twelve", ("twenty", "two")),
            _choice(
                "把字母 r、e、d 按顺序连起来，是哪个基础颜色词？",
                "red",
                ("blue", "green"),
            ),
            _choice(
                "把字母 b、l、u、e 按顺序连起来，是哪个基础颜色词？",
                "blue",
                ("red", "black"),
            ),
        ],
    }
    teaching = {
        "pinyin_syllables": "观察嘴巴口形，听辨单韵母的读音，再跟读。",
        "pinyin_initials_syllables": "声母和已学韵母可以拼成简单两拼音节，也要听四声。",
        "characters_words": "常用汉字有读音，也可结合基础偏旁和词语搭配来理解。",
        "simple_sentences": "完整句子要有明确对象和完整谓语；陈述句用句号，问句用问号。",
        "number_sense_20": "20以内的数可以按顺序数，也可以比较大小。十和一能帮助理解数的组成。",
        "addition_subtraction_20": "加法表示合起来，例如8+4=12。减法表示去掉一部分，例如13-4=9。",
        "shapes_position": (
            "圆形、三角形、正方形和长方形是常见图形。"
            "长方形有四条边和四个角，正方形是特殊的长方形。"
            "位置可用上下左右描述。"
        ),
        "letters_sounds": "认识大写字母和小写字母，并听单词开头的声音。",
        "greetings": "用英语礼貌问候，也可以用简单句介绍自己的名字。",
        "numbers_colors": "认识一到二十的英语数词和基础颜色词。",
    }[skill_id]
    recap = {
        "shapes_position": (
            "回顾圆形、三角形、正方形和长方形的性质，"
            "再用上下左右说清位置。"
        ),
        "addition_subtraction_20": "回顾一步加法和减法，独立复算答案。",
    }.get(skill_id, "回顾本课方法，读清题意后独立作答。")
    return copy.deepcopy(rows[skill_id]), teaching, recap


def _formal_target_and_boundary(
    skill_id: str, *, variant_ordinal: int = 1
) -> tuple[PrimaryOneCourseTarget, dict]:
    for subject_ordinal, subject in enumerate(("chinese", "math", "english"), start=1):
        for boundary_ordinal, registered in enumerate(
            boundaries_for("primary_1", subject), start=1
        ):
            if registered.skill_id != skill_id:
                continue
            target = PrimaryOneCourseTarget(
                grade_code="primary_1",
                subject=subject,
                subject_ordinal=subject_ordinal,
                skill_id=skill_id,
                boundary_ordinal=boundary_ordinal,
                boundary_version=registered.boundary_version,
                variant_ordinal=variant_ordinal,
                instruction_language_code="zh-CN",
                target_language_code="en-US" if subject == "english" else "zh-CN",
            )
            boundary = {
                "skillId": registered.skill_id,
                "skillTitle": registered.skill_title,
                "learningObjectives": list(registered.learning_objectives),
                "allowedContent": list(registered.allowed_content),
                "excludedContent": list(registered.excluded_content),
                "prerequisiteSkills": list(registered.prerequisite_skills),
                "estimatedMinutes": 10,
            }
            return target, boundary
    raise AssertionError(f"unknown formal skill: {skill_id}")


def _formal_course(
    skill_id: str,
    *,
    variant_ordinal: int = 1,
    request_id: str | None = None,
) -> tuple[dict, PrimaryOneCourseTarget, dict, str]:
    target, boundary = _formal_target_and_boundary(
        skill_id, variant_ordinal=variant_ordinal
    )
    request_id = request_id or f"formal.{skill_id}.v{variant_ordinal}"
    request_slug = re.sub(r"[^A-Za-z0-9]+", "_", request_id)[:48]
    question_slug = re.sub(r"[^A-Za-z0-9]+", "_", request_id)[:64]
    marker = ("甲", "乙", "丙")[variant_ordinal - 1]
    rows, teaching, recap = _formal_rows(skill_id)
    for index, question in enumerate(rows, start=1):
        question["id"] = f"{question_slug}_q{index}"
        question["skill"] = boundary["skillTitle"]
        delimiter = (
            "。"
            if skill_id == "number_sense_20" and "组成" in question["prompt"]
            else "："
        )
        question["prompt"] = f"练习{marker}{delimiter}{question['prompt']}"
    question_ids = [question["id"] for question in rows]
    course = {
        "id": (
            f"candidate_primary_1_{target.subject}_"
            f"{hashlib.sha256(skill_id.encode()).hexdigest()[:12]}_{request_slug}"
        ),
        "version": "0.0.0-candidate",
        "gradeCode": "primary_1",
        "subject": target.subject,
        "nodeCode": skill_id,
        "title": f"{boundary['skillTitle']}正式候选",
        "objective": "；".join(boundary["learningObjectives"]),
        "status": "unverified",
        "content": {
            "schemaVersion": "mira.learning.course.v1",
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "sourceAuthority": {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_candidate",
                "textbookDependency": "none",
            },
            "reviewPolicy": "programmatic_guarded",
            "intro": "先学习方法，再完成五道确定性练习。",
            "estimatedMinutes": 10,
            "teachingFlow": {
                "schemaVersion": TEACHING_FLOW_SCHEMA_VERSION,
                "teach": {
                    "title": "先学方法",
                    "sayText": teaching,
                    "keyPoints": ["读清条件", "独立作答"],
                },
                "demoQuestionId": question_ids[0],
                "guidedQuestionIds": question_ids[1:3],
                "independentQuestionIds": question_ids[3:5],
                "recap": {"sayText": recap},
            },
            "questions": rows,
        },
    }
    def normalize_checkpoint(value):
        if isinstance(value, dict):
            return {key: normalize_checkpoint(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize_checkpoint(item) for item in value]
        if isinstance(value, str):
            return unicodedata.normalize("NFKC", value).strip()
        return value

    course = normalize_checkpoint(course)
    return course, target, boundary, request_id


def _sidecar_comparable(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value))
    comparable = []
    for character in normalized:
        category = unicodedata.category(character)
        if (
            character.isspace()
            or category == "Cf"
            or category.startswith("P")
        ):
            continue
        comparable.append(character)
    return "".join(comparable).lower()


def _sidecar_question_fingerprints(
    course: dict, target: PrimaryOneCourseTarget, boundary: dict
) -> list[dict]:
    result = []
    for question in course["content"]["questions"]:
        payload = {
            "gradeCode": "primary_1",
            "subject": target.subject,
            "skillId": boundary["skillId"],
            "type": question["type"],
            "prompt": _sidecar_comparable(question["prompt"]),
            "choiceLabels": sorted(
                _sidecar_comparable(choice["label"])
                for choice in question.get("choices", [])
            ),
        }
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        result.append(
            {
                "questionId": question["id"],
                "fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
            }
        )
    return result


def _public_question_hash(course: dict) -> str:
    public = []
    for question in course["content"]["questions"]:
        item = {
            "id": question["id"],
            "type": question["type"],
            "prompt": question["prompt"],
        }
        if "choices" in question:
            item["choices"] = [
                {"id": choice["id"], "label": choice["label"]}
                for choice in question["choices"]
            ]
        public.append(item)
    encoded = json.dumps(public, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _formal_evidence(
    course: dict,
    target: PrimaryOneCourseTarget,
    boundary: dict,
    request_id: str,
    *,
    final_phase_ordinal: int = 11,
    teaching_review: dict | None = None,
    generator_profile: QuestionPhaseProviderProfileEvidence | None = None,
    verifier_profile: QuestionPhaseProviderProfileEvidence | None = None,
) -> tuple[QuestionPhaseCourseEvidence, PrimaryOneHostGateIdentity]:
    generator_profile = generator_profile or _provider_profile()
    verifier_profile = verifier_profile or _provider_profile()
    solution = {
        "schemaVersion": INDEPENDENT_SOLUTION_SCHEMA_VERSION,
        "solver": f"{verifier_profile.name}:{verifier_profile.model}:fresh_call",
        "independentFromGeneration": True,
        "verificationRequestId": request_id,
        "publicQuestionHash": _public_question_hash(course),
        "gradeCode": "primary_1",
        "subject": target.subject,
        "skillId": target.skill_id,
        "answers": [
            {
                "questionId": question["id"],
                "answer": copy.deepcopy(question["answer"]),
                **(
                    {"derivedExpression": question["verificationExpression"]}
                    if question["type"] == "numeric"
                    else {}
                ),
            }
            for question in course["content"]["questions"]
        ],
        "teachingReview": teaching_review or {"passed": True, "issues": []},
    }
    validation = {
        "schemaValidated": True,
        "boundaryPreserved": True,
        "plainTextOnly": True,
        "questionCount": 5,
        "allowedQuestionTypes": [
            "accepted_text",
            "exact_text",
            "numeric",
            "sequence",
            "single_choice",
        ],
        "guidedQuestionTypes": ["sequence", "single_choice"],
        "existingFingerprintsChecked": (target.variant_ordinal - 1) * 5,
        "duplicateFingerprints": [],
        "independentSolutionRequired": True,
        "independentSolutionProvided": False,
        "teachingFlowSchemaValidated": True,
        "teachingReviewRequired": True,
        "programmaticNumericRecalculationRequired": any(
            question["type"] == "numeric"
            for question in course["content"]["questions"]
        ),
    }
    phase = (
        "independent_verification"
        if final_phase_ordinal == 11
        else "verification_after_repair"
    )
    evidence = QuestionPhaseCourseEvidence(
        final_phase=phase,
        final_phase_ordinal=final_phase_ordinal,
        candidate_course=copy.deepcopy(course),
        question_fingerprints=_sidecar_question_fingerprints(
            course, target, boundary
        ),
        validation=validation,
        independent_solution=solution,
        generator_profile=generator_profile,
        verifier_profile=verifier_profile,
        existing_fingerprint_count=validation[
            "existingFingerprintsChecked"
        ],
    )
    identity = PrimaryOneHostGateIdentity(
        catalog_item_id=f"item_{target.skill_id}_v{target.variant_ordinal}",
        logical_attempt=1,
        generation_request_id=request_id,
        course_id=course["id"],
        course_version=course["version"],
        curriculum_version=PRIMARY_CURRICULUM_VERSION,
        content_validation_contract_version=CONTENT_VALIDATION_CONTRACT_VERSION,
        content_validation_dataset_sha256=PRIMARY_ONE_CONTENT_DATASET_SHA256,
        subject_language_policy_version=SUBJECT_LANGUAGE_POLICY_VERSION,
        generator_profile_hash=generator_profile.profile_hash,
        verifier_profile_hash=verifier_profile.profile_hash,
    )
    return evidence, identity


def formal_host_fixture(
    skill_id: str,
    *,
    variant_ordinal: int = 1,
    final_phase_ordinal: int = 11,
    teaching_review: dict | None = None,
) -> tuple[
    dict,
    PrimaryOneCourseTarget,
    dict,
    QuestionPhaseCourseEvidence,
    PrimaryOneHostGateIdentity,
]:
    course, target, boundary, request_id = _formal_course(
        skill_id, variant_ordinal=variant_ordinal
    )
    evidence, identity = _formal_evidence(
        course,
        target,
        boundary,
        request_id,
        final_phase_ordinal=final_phase_ordinal,
        teaching_review=teaching_review,
    )
    return course, target, boundary, evidence, identity


class LearningGeneratedCourseValidatorTest(unittest.TestCase):
    def setUp(self):
        self.validator = LearningGeneratedCourseValidator()

    def test_valid_json_candidate_becomes_publishable_without_mutating_source(self):
        candidate = math_candidate()
        source = copy.deepcopy(candidate)
        result = self.validator.validate(
            json.dumps(candidate, ensure_ascii=False),
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=json.dumps(
                independent_solution(candidate), ensure_ascii=False
            ),
        )

        self.assertTrue(result.publishable)
        self.assertEqual(candidate, source)
        self.assertEqual(result.course["status"], "published")
        self.assertEqual(
            result.course["content"]["sourceAuthority"],
            {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_validated",
                "textbookDependency": "none",
            },
        )
        self.assertEqual(len(result.report["contentFingerprint"]), 64)
        self.assertIn("math_ast_decimal_recompute", result.report["checksPassed"])
        self.assertIn("teaching_flow_contract", result.report["checksPassed"])
        self.assertIn("independent_teaching_review", result.report["checksPassed"])
        self.assertEqual(result.report["issues"], [])

    def test_require_publishable_raises_structured_first_issue(self):
        candidate = math_candidate()
        candidate["unexpected"] = True
        result = self.validator.validate(
            candidate,
            grade_code="primary_3",
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(candidate),
        )

        self.assertFalse(result.publishable)
        self.assertEqual(
            result.report["issues"][0]["code"],
            "invalid_generated_course_schema",
        )
        self.assertIn(
            "unexpected", result.report["issues"][0]["details"]["unknownFields"]
        )
        with self.assertRaises(GeneratedCourseValidationError) as context:
            result.require_publishable()
        self.assertEqual(context.exception.status_code, 422)

    def test_rejects_question_count_boundary_and_skill_drift(self):
        cases = []
        too_few = math_candidate()
        too_few["content"]["questions"].pop()
        cases.append((too_few, "invalid_generated_question_count"))

        wrong_grade = math_candidate()
        wrong_grade["gradeCode"] = "primary_6"
        cases.append((wrong_grade, "generated_course_boundary_mismatch"))

        wrong_skill = math_candidate()
        wrong_skill["content"]["questions"][0]["skill"] = "初中方程"
        cases.append((wrong_skill, "generated_course_boundary_mismatch"))

        for candidate, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                result = self.validator.validate(
                    candidate,
                    grade=3,
                    subject="math",
                    skill_boundary=math_boundary(),
                    independent_solution=independent_solution(candidate),
                )
                self.assertFalse(result.publishable)
                self.assertEqual(result.report["issues"][0]["code"], expected_code)

    def test_accepts_ordered_full_width_join_of_multiple_fixed_objectives(self):
        candidate = math_candidate()
        first = "准确完成三位数加减与基础乘除计算。"
        second = "能用逆运算检查计算结果。"
        candidate["objective"] = f"{first}；{second}"
        boundary = math_boundary()
        boundary["learningObjectives"] = [first, second]

        result = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=boundary,
            independent_solution=independent_solution(candidate),
        )
        self.assertTrue(result.publishable)

        candidate["objective"] = f"{second}；{first}"
        drift = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=boundary,
            independent_solution=independent_solution(candidate),
        )
        self.assertEqual(
            drift.report["issues"][0]["code"],
            "generated_course_boundary_mismatch",
        )

    def test_accepts_canonical_ascii_join_of_multiple_fixed_objectives(self):
        candidate = math_candidate()
        first = "准确完成三位数加减与基础乘除计算。"
        second = "能用逆运算检查计算结果。"
        candidate["objective"] = f"{first};{second}"
        boundary = math_boundary()
        boundary["learningObjectives"] = [first, second]

        result = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=boundary,
            independent_solution=independent_solution(candidate),
        )

        self.assertTrue(result.publishable, result.report)

    def test_rejects_unsafe_normalization_and_unknown_question_fields(self):
        unsafe = math_candidate()
        unsafe["content"]["questions"][0]["evaluation"]["normalization"].append(
            "run_python"
        )
        unsafe_result = self.validator.validate(
            unsafe,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(unsafe),
        )
        self.assertEqual(
            unsafe_result.report["issues"][0]["code"],
            "unsafe_generated_normalization",
        )

        unknown = math_candidate()
        unknown["content"]["questions"][0]["script"] = "print('unsafe')"
        unknown_result = self.validator.validate(
            unknown,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(unknown),
        )
        self.assertEqual(
            unknown_result.report["issues"][0]["code"],
            "invalid_generated_course_schema",
        )

    def test_hint_cannot_directly_reveal_answer_but_may_teach_an_intermediate_step(self):
        leaked = math_candidate()
        leaked["content"]["questions"][0]["hint"] = "正确答案是395。"
        result = self.validator.validate(
            leaked,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(leaked),
        )
        self.assertEqual(
            result.report["issues"][0]["code"], "generated_hint_answer_leak"
        )

        safe = math_candidate()
        safe["content"]["questions"][0]["hint"] = "先算个位8加7。"
        safe_result = self.validator.validate(
            safe,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(safe),
        )
        self.assertTrue(safe_result.publishable)

    def test_prompt_cannot_reveal_answer_or_use_an_unrelated_math_derivation(self):
        leaked = math_candidate()
        leaked["content"]["questions"][0]["prompt"] = (
            "2 + 2 = 5。请直接回答395。"
        )
        leaked_result = self.validator.validate(
            leaked,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(leaked),
        )
        self.assertEqual(
            leaked_result.report["issues"][0]["code"],
            "generated_prompt_answer_leak",
        )

        unrelated = math_candidate()
        solution = independent_solution(unrelated)
        solution["answers"][0]["derivedExpression"] = "200+195"
        unrelated_result = self.validator.validate(
            unrelated,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=solution,
        )
        self.assertEqual(
            unrelated_result.report["issues"][0]["code"],
            "invalid_independent_solution",
        )

    def test_independent_solution_is_bound_to_request_and_public_questions(self):
        candidate = math_candidate()
        solution = independent_solution(candidate)
        mismatch = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=solution,
            verification_request_id="another-request",
        )
        self.assertEqual(
            mismatch.report["issues"][0]["code"],
            "invalid_independent_solution",
        )

        solution = independent_solution(candidate)
        solution["publicQuestionHash"] = "0" * 64
        replay = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=solution,
        )
        self.assertEqual(
            replay.report["issues"][0]["code"],
            "independent_solution_mismatch",
        )

    def test_teaching_flow_must_cover_all_questions_once_in_fixed_roles(self):
        candidate = math_candidate()
        candidate["content"]["teachingFlow"]["guidedQuestionIds"] = [
            candidate["content"]["questions"][2]["id"],
            candidate["content"]["questions"][1]["id"],
        ]
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(candidate),
        )
        self.assertEqual(
            result.report["issues"][0]["code"], "invalid_generated_teaching_flow"
        )

        candidate = math_candidate()
        candidate["content"]["teachingFlow"]["teach"]["action"] = "play"
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(candidate),
        )
        self.assertEqual(
            result.report["issues"][0]["code"], "invalid_generated_course_schema"
        )

    def test_teaching_flow_rejects_excluded_content_and_practice_answer_leak(self):
        excluded = math_candidate()
        excluded["content"]["teachingFlow"]["teach"]["sayText"] = (
            "这一课先学习初中方程。"
        )
        result = self.validator.validate(
            excluded,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(excluded),
        )
        self.assertEqual(
            result.report["issues"][0]["code"],
            "generated_course_boundary_mismatch",
        )

        leaked = math_candidate()
        leaked["content"]["teachingFlow"]["recap"]["sayText"] = (
            "第二道练习的正确答案是324。"
        )
        result = self.validator.validate(
            leaked,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(leaked),
        )
        self.assertEqual(
            result.report["issues"][0]["code"], "generated_teaching_answer_leak"
        )

    def test_teaching_flow_leak_checks_public_choice_labels_not_cross_question_ids(self):
        candidate = english_candidate()
        first = candidate["content"]["questions"][0]
        second = candidate["content"]["questions"][1]
        old_second_answer = second["answer"]
        for choice in second["choices"]:
            if choice["id"] == old_second_answer:
                choice["id"] = first["answer"]
        second["answer"] = first["answer"]
        second["evaluation"]["expectedOptionId"] = first["answer"]
        candidate["content"]["teachingFlow"]["teach"]["sayText"] = (
            f"示范题内部选项 ID 是 {first['answer']}。"
        )
        boundary = {
            "gradeCode": "primary_3",
            "subject": "english",
            "skillId": "daily_routines",
            "learningObjectives": [candidate["objective"]],
            "allowedQuestionSkills": ["日常活动词组"],
        }
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="english",
            skill_boundary=boundary,
            independent_solution=independent_solution(candidate, subject="english"),
        )
        self.assertTrue(result.publishable, result.report)

    def test_teaching_flow_allows_coincidental_answer_but_rejects_same_equation(self):
        candidate = math_candidate()
        candidate["content"]["teachingFlow"]["recap"]["sayText"] = (
            "再看另一个例子：300+24=324。"
        )
        allowed = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(candidate),
        )
        self.assertTrue(allowed.publishable, allowed.report)

        leaked = math_candidate()
        leaked["content"]["teachingFlow"]["recap"]["sayText"] = (
            "第二题的算式是602-278=324。"
        )
        rejected = self.validator.validate(
            leaked,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(leaked),
        )
        self.assertEqual(
            rejected.report["issues"][0]["code"],
            "generated_teaching_answer_leak",
        )

    def test_teaching_flow_rejects_same_story_arithmetic_before_choice_practice(self):
        candidate = math_candidate()
        question = candidate["content"]["questions"][1]
        question.update(
            {
                "type": "single_choice",
                "prompt": "鱼缸里有8条金鱼，又放进5条，现在一共有多少条？",
                "answer": "B",
                "hint": "想一想一共表示什么。",
                "explanation": "8加5等于13，所以一共有13条。",
                "choices": [
                    {"id": "A", "label": "12条"},
                    {"id": "B", "label": "13条"},
                    {"id": "C", "label": "14条"},
                ],
                "evaluation": {
                    "expectedOptionId": "B",
                    "normalization": ["trim", "casefold"],
                },
            }
        )
        question.pop("verificationExpression", None)
        candidate["content"]["teachingFlow"]["teach"]["sayText"] = (
            "先看8加5，8加5等于13。"
        )
        rejected = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(candidate),
        )
        self.assertEqual(
            rejected.report["issues"][0]["code"],
            "generated_teaching_answer_leak",
        )

        candidate["content"]["teachingFlow"]["teach"]["sayText"] = (
            "先看另一个例子：9加4等于13。"
        )
        allowed = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(candidate),
        )
        self.assertTrue(allowed.publishable, allowed.report)

    def test_independent_teaching_review_must_pass_without_issues(self):
        candidate = math_candidate()
        solution = independent_solution(candidate)
        solution["teachingReview"] = {
            "passed": False,
            "issues": ["讲解超出能力边界"],
        }
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=solution,
        )
        self.assertEqual(
            result.report["issues"][0]["code"],
            "independent_teaching_review_failed",
        )
        self.assertIn(
            "讲解超出能力边界",
            result.report["issues"][0]["message"],
        )

        solution = independent_solution(candidate)
        solution["teachingReview"] = {"passed": True, "issues": ["矛盾"]}
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=solution,
        )
        self.assertEqual(
            result.report["issues"][0]["code"],
            "independent_teaching_review_failed",
        )

    def test_math_ast_decimal_recompute_rejects_calls_and_wrong_answers(self):
        unsafe = math_candidate()
        unsafe["content"]["questions"][0]["verificationExpression"] = (
            "__import__('os').system('false')"
        )
        unsafe_result = self.validator.validate(
            unsafe,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(unsafe),
        )
        self.assertEqual(
            unsafe_result.report["issues"][0]["code"],
            "invalid_generated_math_verification",
        )

        wrong = math_candidate()
        wrong["content"]["questions"][0]["answer"] = "396"
        wrong["content"]["questions"][0]["evaluation"]["expected"] = "396"
        wrong_solution = independent_solution(wrong)
        wrong_result = self.validator.validate(
            wrong,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=wrong_solution,
        )
        self.assertEqual(
            wrong_result.report["issues"][0]["code"],
            "generated_answer_verification_mismatch",
        )

    def test_independent_solution_is_required_and_must_cover_and_solve_every_item(self):
        candidate = math_candidate()
        missing = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=None,
        )
        self.assertEqual(
            missing.report["issues"][0]["code"], "missing_independent_solution"
        )

        solution = independent_solution(candidate)
        solution["answers"][0]["answer"] = "999"
        mismatch = self.validator.validate(
            candidate,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=solution,
        )
        self.assertEqual(
            mismatch.report["issues"][0]["code"], "independent_solution_mismatch"
        )

    def test_english_requires_independent_answer_agreement_and_publishes(self):
        candidate = english_candidate()
        boundary = {
            "gradeCode": "primary_3",
            "subject": "english",
            "skillId": "daily_routines",
            "learningObjectives": [candidate["objective"]],
            "allowedQuestionSkills": ["日常活动词组"],
        }
        solution = independent_solution(candidate, subject="english")
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="english",
            skill_boundary=boundary,
            independent_solution=solution,
        )
        self.assertTrue(result.publishable)
        self.assertIn(
            "independent_solution_agreement", result.report["checksPassed"]
        )

        solution["answers"][2]["answer"] = "distractor_a"
        mismatch = self.validator.validate(
            candidate,
            grade=3,
            subject="english",
            skill_boundary=boundary,
            independent_solution=solution,
        )
        self.assertEqual(
            mismatch.report["issues"][0]["code"], "independent_solution_mismatch"
        )

    def test_choice_ids_and_labels_must_be_unique_after_normalization(self):
        candidate = english_candidate()
        candidate["content"]["questions"][0]["choices"][2]["label"] = (
            " READ A BOOK "
        )
        result = self.validator.validate(
            candidate,
            grade=3,
            subject="english",
            skill_boundary={
                "skillId": "daily_routines",
                "learningObjectives": [candidate["objective"]],
            },
            independent_solution=independent_solution(candidate, subject="english"),
        )
        self.assertEqual(
            result.report["issues"][0]["code"], "duplicate_generated_choice"
        )

    def test_semantic_fingerprint_detects_duplicate_despite_ids_and_choice_order(self):
        candidate = english_candidate()
        fingerprint = self.validator.content_fingerprint(candidate)
        changed = copy.deepcopy(candidate)
        changed["id"] = "candidate_primary_3_english_daily_routines_req2"
        for index, question in enumerate(changed["content"]["questions"]):
            question["id"] = f"other_generated_id_{index}"
            question["choices"].reverse()
        set_teaching_flow(changed)
        result = self.validator.validate(
            changed,
            grade=3,
            subject="english",
            skill_boundary={
                "skillId": "daily_routines",
                "learningObjectives": [changed["objective"]],
            },
            independent_solution=independent_solution(changed, subject="english"),
            existing_fingerprints=[fingerprint],
        )

        self.assertFalse(result.publishable)
        self.assertEqual(
            result.report["issues"][0]["code"], "duplicate_generated_course"
        )

    def test_rejects_non_finite_json_and_does_not_execute_candidate_code(self):
        payload = json.dumps(math_candidate(), ensure_ascii=False).replace(
            '"estimatedMinutes": 10', '"estimatedMinutes": NaN'
        )
        result = self.validator.validate(
            payload,
            grade=3,
            subject="math",
            skill_boundary=math_boundary(),
            independent_solution=independent_solution(math_candidate()),
        )
        self.assertEqual(
            result.report["issues"][0]["code"], "invalid_generated_course_json"
        )

    @unittest.skipUnless(
        shutil.which("node")
        and (
            Path(__file__).resolve().parents[1]
            / "openmaic-sidecar"
            / "node_modules"
            / "@openmaic"
            / "generation"
        ).exists(),
        "OpenMAIC sidecar dependencies are not installed",
    )
    def test_real_sidecar_fake_mode_generation_and_second_solve_pass_validator(self):
        sidecar = Path(__file__).resolve().parents[1] / "openmaic-sidecar"
        cli = sidecar / "src" / "cli.mjs"
        boundary = {
            "skillId": "math.p3.multi-objective",
            "skillTitle": "三位数计算",
            "learningObjectives": [
                "正确完成三位数加减法",
                "会用乘除法解决一步问题",
            ],
            "allowedContent": ["整数四则运算", "一步应用题"],
            "excludedContent": ["负数", "方程"],
            "prerequisiteSkills": ["认识四则运算符号"],
            "language": "zh-CN",
            "estimatedMinutes": 10,
        }
        provider = {
            "name": "kimi",
            "model": "kimi-k2.6",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "APP_AI_API_KEY",
        }
        outline = {
            "courseTitle": "三位数计算",
            "languageDirective": "Use Simplified Chinese.",
            "outlines": [
                {
                    "id": "practice",
                    "type": "quiz",
                    "title": "五题练习",
                    "description": "在固定能力边界内练习",
                    "keyPoints": ["先理解题意", "独立作答"],
                }
            ],
        }
        generated = {
            "title": "三位数计算练习",
            "intro": "读清题意后完成五道计算题。",
            "estimatedMinutes": 10,
            "teachingFlow": {
                "teach": {
                    "title": "先学计算方法",
                    "sayText": "先读清运算符号，再按步骤完成计算。",
                    "keyPoints": ["读清符号", "分步计算", "完成后检查"],
                },
                "recap": {"sayText": "计算时先读清符号，再分步完成并检查。"},
            },
            "questions": [
                {
                    "type": "numeric",
                    "prompt": prompt,
                    "skill": "模型提供的技能名会被边界覆盖",
                    "hint": hint,
                    "explanation": explanation,
                    "answer": answer,
                    "verificationExpression": expression,
                }
                for prompt, hint, explanation, answer, expression in (
                    ("238 + 157 = ?", "先从个位相加。", "计算结果为395。", "395", "238+157"),
                    ("602 - 278 = ?", "注意连续退位。", "计算结果为324。", "324", "602-278"),
                    ("36 × 4 = ?", "拆成整十数和个位数。", "计算结果为144。", "144", "36*4"),
                    ("96 ÷ 3 = ?", "分别计算90和6。", "计算结果为32。", "32", "96/3"),
                    ("每层28本，4层共有多少本？", "把每层本数相加。", "一共有112本。", "112", "28*4"),
                )
            ],
        }
        for question in generated["questions"][1:3]:
            numeric_answer = int(question["answer"])
            question["type"] = "single_choice"
            question["answer"] = "B"
            question["choices"] = [
                {"id": "A", "label": str(numeric_answer - 1)},
                {"id": "B", "label": str(numeric_answer)},
                {"id": "C", "label": str(numeric_answer + 1)},
            ]
            question.pop("verificationExpression")
        generation_input = {
            "schemaVersion": "mira.openmaic.question_generation.v1",
            "requestId": "python-sidecar-integration-1",
            "gradeCode": "primary_3",
            "subject": "math",
            "skillBoundary": boundary,
            "questionCount": 5,
            "existingFingerprints": [],
            "provider": provider,
            "mode": "fake",
            "fakeResponses": [
                json.dumps(outline, ensure_ascii=False),
                json.dumps(generated, ensure_ascii=False),
                json.dumps(generated, ensure_ascii=False),
                json.dumps(
                    {
                        "title": generated["title"],
                        "intro": generated["intro"],
                        "teachingFlow": generated["teachingFlow"],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "estimatedMinutes": generated["estimatedMinutes"],
                        "questions": generated["questions"],
                    },
                    ensure_ascii=False,
                ),
            ],
        }
        generation_output = self._run_sidecar(cli, sidecar, generation_input)
        candidate = generation_output["candidateCourse"]
        public_questions = []
        independent_answers = []
        for question in candidate["content"]["questions"]:
            public = {
                "id": question["id"],
                "type": question["type"],
                "prompt": question["prompt"],
            }
            if "choices" in question:
                public["choices"] = question["choices"]
            public_questions.append(public)
            independent_answers.append(
                {
                    "questionId": question["id"],
                    "answer": question["answer"],
                    **(
                        {"derivedExpression": question["verificationExpression"]}
                        if question["type"] == "numeric"
                        else {}
                    ),
                }
            )
        verification_input = {
            "schemaVersion": "mira.openmaic.question_verification.v1",
            "requestId": "python-sidecar-independent-1",
            "gradeCode": "primary_3",
            "subject": "math",
            "skillBoundary": boundary,
            "publicQuestions": public_questions,
            "publicTeachingFlow": {
                **candidate["content"]["teachingFlow"],
                "workedExample": {
                    "questionId": candidate["content"]["questions"][0]["id"],
                    "explanation": candidate["content"]["questions"][0][
                        "explanation"
                    ],
                },
            },
            "provider": provider,
            "mode": "fake",
            "fakeResponses": [
                json.dumps(
                    {
                        "answers": independent_answers,
                        "teachingReview": {"passed": True, "issues": []},
                    },
                    ensure_ascii=False,
                )
            ],
        }
        verification_output = self._run_sidecar(
            cli, sidecar, verification_input
        )

        result = self.validator.validate(
            candidate,
            grade_code="primary_3",
            subject="math",
            skill_boundary=generation_output["skillBoundary"],
            independent_solution=verification_output["solution"],
        )
        self.assertTrue(result.publishable, result.report)
        self.assertEqual(
            result.course["objective"],
            "正确完成三位数加减法;会用乘除法解决一步问题",
        )

    @staticmethod
    def _run_sidecar(cli: Path, cwd: Path, payload: dict) -> dict:
        process = subprocess.run(
            [str(shutil.which("node")), str(cli)],
            cwd=cwd,
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "OPENMAIC_FAKE_MODE": "1"},
            timeout=20,
        )
        if process.returncode != 0:
            raise AssertionError(process.stderr or process.stdout)
        return json.loads(process.stdout)


_HOST_RECEIPT_KEYS = {
    "schemaVersion",
    "validatorVersion",
    "fingerprintVersion",
    "contentValidationContractVersion",
    "contentValidationDatasetSha256",
    "subjectLanguagePolicyVersion",
    "catalogItemId",
    "logicalAttempt",
    "generationRequestIdHash",
    "courseId",
    "courseVersion",
    "gradeCode",
    "subject",
    "subjectOrdinal",
    "skillId",
    "boundaryOrdinal",
    "boundaryVersion",
    "variantOrdinal",
    "instructionLanguageCode",
    "targetLanguageCode",
    "finalProviderPhase",
    "finalProviderPhaseOrdinal",
    "generatorProfileHash",
    "verifierProfileHash",
    "verificationIsolation",
    "skillBoundarySha256",
    "candidateCourseSha256",
    "sidecarEvidenceSha256",
    "hostContentFingerprint",
    "outcome",
    "checksPassed",
    "issues",
}


class PrimaryOneFormalHostGateTest(unittest.TestCase):
    def setUp(self):
        self.validator = LearningGeneratedCourseValidator()

    def _run(
        self,
        fixture,
        *,
        accepted: tuple[AcceptedPrimaryOneHostReceipt, ...] = (),
    ):
        _course, target, boundary, evidence, identity = fixture
        return self.validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=accepted,
        )

    def _run_simple_sentence(self, sentence: str):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "simple_sentences"
        )
        question = course["content"]["questions"][4]
        selected = next(
            choice
            for choice in question["choices"]
            if choice["id"] == question["answer"]
        )
        selected["label"] = sentence
        evidence, refreshed_identity = _formal_evidence(
            course,
            target,
            boundary,
            identity.generation_request_id,
        )
        self.assertEqual(refreshed_identity, identity)
        return self.validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

    def test_host_accepts_allowlisted_primary_one_add_sub_solver_provenance(self):
        course, target, boundary, evidence, identity = formal_host_fixture(
            "addition_subtraction_20"
        )
        solution = copy.deepcopy(evidence.independent_solution)
        solution["solver"] = PRIMARY_ONE_ADD_SUB_HOST_SOLVER

        result = self.validator.validate_primary_one_host_gate(
            replace(evidence, independent_solution=solution),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_history_over_sidecar_limit_remains_host_deduplicated(self):
        _course, target, boundary, evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        duplicate = str(evidence.question_fingerprints[0]["fingerprint"])
        history = sorted(
            {
                duplicate,
                *(
                    hashlib.sha256(f"old-question-{index}".encode()).hexdigest()
                    for index in range(504)
                ),
            }
        )
        required = [hashlib.sha256(b"current-build-prior").hexdigest()]
        projection = None
        for index in range(2_000):
            projection = provider_question_fingerprint_projection(
                authoritative_fingerprints=history,
                required_fingerprints=required,
                request_id=f"capacity-regression-{index}",
            )
            if duplicate not in projection:
                break
        self.assertIsNotNone(projection)
        self.assertEqual(len(projection), 500)
        self.assertIn(required[0], projection)
        self.assertNotIn(duplicate, projection)

        validation = copy.deepcopy(evidence.validation)
        validation["existingFingerprintsChecked"] = len(projection)
        result = self.validator.validate_primary_one_host_gate(
            replace(
                evidence,
                validation=validation,
                existing_fingerprint_count=len(projection),
                authoritative_existing_fingerprints=history,
            ),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "rejected")
        self.assertEqual(
            result.receipt["issues"][0]["code"],
            "primary_one_historical_question_duplicate",
        )

    def test_host_accepts_allowlisted_primary_one_number_sense_solver_provenance(self):
        course, target, boundary, evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        solution = copy.deepcopy(evidence.independent_solution)
        solution["solver"] = PRIMARY_ONE_NUMBER_SENSE_HOST_SOLVER

        result = self.validator.validate_primary_one_host_gate(
            replace(evidence, independent_solution=solution),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_host_rejects_marker_before_bare_predicate_fallback(self):
        for invalid_sentence in (
            "小狗了叫。",
            "我很跑步。",
            "我太工作。",
            "我们真学习。",
            "妈妈的很开心。",
            "妈妈的是工作。",
            "很开心。",
            "太工作。",
            "了工作。",
            "我很太开心。",
            "我太很开心。",
            "了小狗叫。",
            "着小狗叫。",
            "过小狗叫。",
            "很我开心。",
            "太妈妈工作。",
            "我是了工作。",
            "妈妈是很跑步。",
            "妈妈是过学习。",
            "妈妈是真学习。",
        ):
            with self.subTest(invalid_sentence=invalid_sentence):
                result = self._run_simple_sentence(invalid_sentence)

                self.assertEqual(result.outcome, "rejected", result.receipt)
                self.assertIsNone(result.course)

    def test_host_accepts_sealed_marker_production_controls(self):
        for valid_sentence in (
            "小狗叫了。",
            "我很开心。",
            "妈妈是老师。",
            "太空人工作。",
            "真菌漂亮。",
            "过山车漂亮。",
            "太太工作。",
            "老太太工作。",
            "妈妈是太空人。",
        ):
            with self.subTest(valid_sentence=valid_sentence):
                result = self._run_simple_sentence(valid_sentence)

                self.assertEqual(result.outcome, "passed", result.receipt)
                self.assertIsNotNone(result.course)

    def test_host_receipt_rejects_unsealed_trailing_question_particles(self):
        for invalid_sentence in (
            "小狗叫吗。",
            "小狗叫了呢。",
            "妈妈是老师吗。",
            "我很开心呢。",
        ):
            with self.subTest(invalid_sentence=invalid_sentence):
                result = self._run_simple_sentence(invalid_sentence)

                self.assertEqual(result.outcome, "rejected", result.receipt)
                self.assertIsNone(result.course)

    def test_phase_11_and_phase_14_use_one_host_implementation(self):
        phase_11 = self._run(formal_host_fixture("pinyin_syllables"))
        phase_14 = self._run(
            formal_host_fixture(
                "pinyin_initials_syllables", final_phase_ordinal=14
            )
        )

        self.assertEqual(phase_11.outcome, "passed")
        self.assertEqual(phase_14.outcome, "passed")
        self.assertEqual(
            phase_11.receipt["finalProviderPhase"], "independent_verification"
        )
        self.assertEqual(
            phase_14.receipt["finalProviderPhase"], "verification_after_repair"
        )
        self.assertEqual(phase_14.receipt["finalProviderPhaseOrdinal"], 14)

    def test_host_recomputes_repository_question_fingerprints_consistently(self):
        course, target, boundary, evidence, identity = formal_host_fixture(
            "letters_sounds"
        )
        repository_fingerprints = [
            {
                "questionId": question["id"],
                "fingerprint": DynamicLearningCourseRepository.question_fingerprint(
                    grade_code=target.grade_code,
                    subject=target.subject,
                    node_code=target.skill_id,
                    question=question,
                ),
            }
            for question in course["content"]["questions"]
        ]

        self.assertEqual(list(evidence.question_fingerprints), repository_fingerprints)
        result = self.validator.validate_primary_one_host_gate(
            replace(evidence, question_fingerprints=repository_fingerprints),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_host_accepts_task4_scalar_accepted_text_independent_answer(self):
        course, target, boundary, request_id = _formal_course("pinyin_syllables")
        question = course["content"]["questions"][3]
        question["type"] = "accepted_text"
        question.pop("choices")
        question["answer"] = ["a"]
        question["acceptedAnswers"] = ["a"]
        question["evaluation"] = {
            "acceptedAnswers": ["a"],
            "normalization": [
                "trim",
                "collapse_whitespace",
                "remove_whitespace",
            ],
        }
        evidence, identity = _formal_evidence(
            course,
            target,
            boundary,
            request_id,
        )
        solution = copy.deepcopy(evidence.independent_solution)
        solution["answers"][3]["answer"] = "a"

        result = self.validator.validate_primary_one_host_gate(
            replace(evidence, independent_solution=solution),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_host_rejects_more_than_three_teaching_review_issues_as_control_drift(self):
        fixture = formal_host_fixture(
            "greetings",
            teaching_review={
                "passed": False,
                "issues": ["问题一", "问题二", "问题三", "问题四"],
            },
        )

        with self.assertRaises(PrimaryOneHostGateControlError):
            self._run(fixture)

    def test_passed_receipt_has_exact_safe_shape_and_hash(self):
        course, _target, _boundary, _evidence, identity = formal_host_fixture(
            "letters_sounds"
        )
        result = self._run(
            formal_host_fixture("letters_sounds")
        )

        self.assertEqual(set(result.receipt), _HOST_RECEIPT_KEYS)
        self.assertEqual(
            result.receipt["schemaVersion"],
            PRIMARY_ONE_HOST_GATE_RECEIPT_SCHEMA_VERSION,
        )
        self.assertEqual(
            result.receipt["validatorVersion"], PRIMARY_ONE_HOST_GATE_VERSION
        )
        self.assertEqual(
            result.receipt["fingerprintVersion"],
            PRIMARY_ONE_HOST_FINGERPRINT_VERSION,
        )
        self.assertEqual(result.receipt["outcome"], "passed")
        self.assertEqual(result.receipt["issues"], [])
        self.assertEqual(
            result.receipt["generationRequestIdHash"],
            hashlib.sha256(identity.generation_request_id.encode()).hexdigest(),
        )
        self.assertNotIn(identity.generation_request_id, _canonical_json(result.receipt))
        self.assertEqual(
            result.receipt_hash,
            hashlib.sha256(_canonical_json(result.receipt).encode()).hexdigest(),
        )
        self.assertEqual(len(result.receipt["hostContentFingerprint"]), 64)
        self.assertEqual(
            result.course["content"]["sourceAuthority"]["contentOrigin"],
            "openmaic_kimi_validated",
        )
        self.assertEqual(course["status"], "unverified")
        self.assertEqual(len(result.receipt["checksPassed"]), len(set(result.receipt["checksPassed"])))
        self.assertFalse(
            {"generationFeedback", "nextPhase", "retry", "providerCommand"}
            & set(result.receipt)
        )

    def test_sidecar_teaching_opinion_never_selects_host_outcome(self):
        good = formal_host_fixture(
            "greetings",
            teaching_review={"passed": False, "issues": ["模型认为讲解可改进"]},
        )
        self.assertEqual(self._run(good).outcome, "passed")

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "greetings"
        )
        question = course["content"]["questions"][0]
        question["answer"] = question["choices"][0]["id"]
        question["evaluation"]["expectedOptionId"] = question["answer"]
        evidence, drift_identity = _formal_evidence(
            course, target, boundary, identity.generation_request_id
        )
        self.assertEqual(drift_identity, identity)
        rejected = self.validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )
        self.assertEqual(rejected.outcome, "rejected")
        self.assertIsNone(rejected.course)
        self.assertEqual(len(rejected.receipt["issues"]), 1)
        self.assertEqual(
            set(rejected.receipt["issues"][0]), {"code", "path", "message"}
        )
        self.assertNotIn("Hello", _canonical_json(rejected.receipt))

    def test_checkpoint_and_provenance_drift_are_control_errors_without_receipt(self):
        course, target, boundary, evidence, identity = formal_host_fixture(
            "numbers_colors"
        )

        bad_course = copy.deepcopy(course)
        bad_course["unexpected"] = True
        bad_fingerprints = copy.deepcopy(evidence.question_fingerprints)
        bad_fingerprints[0]["fingerprint"] = "0" * 64
        bad_validation = copy.deepcopy(evidence.validation)
        bad_validation["schemaValidated"] = False
        bad_solution_hash = copy.deepcopy(evidence.independent_solution)
        bad_solution_hash["publicQuestionHash"] = "0" * 64
        bad_solution_grade = copy.deepcopy(evidence.independent_solution)
        bad_solution_grade["gradeCode"] = "primary_2"
        bad_solution_subject = copy.deepcopy(evidence.independent_solution)
        bad_solution_subject["subject"] = "math"
        bad_solution_skill = copy.deepcopy(evidence.independent_solution)
        bad_solution_skill["skillId"] = "greetings"
        bad_solution_question = copy.deepcopy(evidence.independent_solution)
        bad_solution_question["answers"][0]["questionId"] = "forged_q1"
        bad_solution_request = copy.deepcopy(evidence.independent_solution)
        bad_solution_request["verificationRequestId"] = "forged.request"
        bad_solution_solver = copy.deepcopy(evidence.independent_solution)
        bad_solution_solver["solver"] = "forged:solver:fresh_call"
        bad_boundary = {**boundary, "language": "en-US"}
        bad_profile = replace(
            evidence.generator_profile,
            api_key_env="sk-secret-value",
        )

        cases = {
            "phase-name": (
                replace(evidence, final_phase="verification_after_repair"),
                target,
                identity,
                boundary,
            ),
            "phase-ordinal": (
                replace(evidence, final_phase_ordinal=14),
                target,
                identity,
                boundary,
            ),
            "candidate-schema": (
                replace(evidence, candidate_course=bad_course),
                target,
                identity,
                boundary,
            ),
            "sidecar-fingerprint": (
                replace(evidence, question_fingerprints=bad_fingerprints),
                target,
                identity,
                boundary,
            ),
            "sidecar-validation": (
                replace(evidence, validation=bad_validation),
                target,
                identity,
                boundary,
            ),
            "public-question-hash": (
                replace(evidence, independent_solution=bad_solution_hash),
                target,
                identity,
                boundary,
            ),
            "solution-grade": (
                replace(evidence, independent_solution=bad_solution_grade),
                target,
                identity,
                boundary,
            ),
            "solution-subject": (
                replace(evidence, independent_solution=bad_solution_subject),
                target,
                identity,
                boundary,
            ),
            "solution-skill": (
                replace(evidence, independent_solution=bad_solution_skill),
                target,
                identity,
                boundary,
            ),
            "solution-question": (
                replace(evidence, independent_solution=bad_solution_question),
                target,
                identity,
                boundary,
            ),
            "solution-request": (
                replace(evidence, independent_solution=bad_solution_request),
                target,
                identity,
                boundary,
            ),
            "solution-profile": (
                replace(evidence, independent_solution=bad_solution_solver),
                target,
                identity,
                boundary,
            ),
            "profile-shape": (
                replace(evidence, generator_profile=bad_profile),
                target,
                identity,
                boundary,
            ),
            "profile-hash": (
                evidence,
                target,
                replace(identity, verifier_profile_hash="0" * 64),
                boundary,
            ),
            "identity-course": (
                evidence,
                target,
                replace(identity, course_id="forged-course"),
                boundary,
            ),
            "identity-attempt-bool": (
                evidence,
                target,
                replace(identity, logical_attempt=True),
                boundary,
            ),
            "boundary-extra-field": (evidence, target, identity, bad_boundary),
            "target-language": (
                evidence,
                replace(target, target_language_code="zh-CN"),
                identity,
                boundary,
            ),
        }
        for label, (bad_evidence, bad_target, bad_identity, skill_boundary) in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self.validator.validate_primary_one_host_gate(
                        bad_evidence,
                        target=bad_target,
                        identity=bad_identity,
                        skill_boundary=skill_boundary,
                        accepted_host_receipts=(),
                    )

    def test_every_host_identity_and_typed_profile_field_fails_closed(self):
        _course, target, boundary, evidence, identity = formal_host_fixture(
            "numbers_colors"
        )

        identity_mutations = {
            "catalog-item": replace(identity, catalog_item_id=""),
            "logical-attempt": replace(identity, logical_attempt=3),
            "generation-request": replace(
                identity, generation_request_id="not canonical"
            ),
            "course-id": replace(identity, course_id="forged-course"),
            "course-version": replace(identity, course_version="9.9.9"),
            "curriculum-version": replace(
                identity, curriculum_version="forged-curriculum"
            ),
            "contract-version": replace(
                identity,
                content_validation_contract_version="forged-contract",
            ),
            "dataset-hash": replace(
                identity, content_validation_dataset_sha256="0" * 64
            ),
            "language-policy": replace(
                identity,
                subject_language_policy_version="forged-language-policy",
            ),
            "generator-profile-hash": replace(
                identity, generator_profile_hash="0" * 64
            ),
            "verifier-profile-hash": replace(
                identity, verifier_profile_hash="0" * 64
            ),
        }
        for field, mutated in identity_mutations.items():
            with self.subTest(identity=field):
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self.validator.validate_primary_one_host_gate(
                        evidence,
                        target=target,
                        identity=mutated,
                        skill_boundary=boundary,
                        accepted_host_receipts=(),
                    )

        profile_mutations = {
            "name": replace(evidence.generator_profile, name="forged"),
            "model": replace(evidence.generator_profile, model="forged"),
            "base-url": replace(
                evidence.generator_profile, base_url="not-a-url"
            ),
            "api-key-secret": replace(
                evidence.generator_profile, api_key_env="sk-secret"
            ),
            "timeout-bool": replace(evidence.generator_profile, timeout_ms=True),
            "max-tokens-bool": replace(
                evidence.generator_profile, max_tokens=True
            ),
            "temperature-nonfinite": replace(
                evidence.generator_profile, temperature=float("nan")
            ),
            "profile-hash": replace(
                evidence.generator_profile, profile_hash="0" * 64
            ),
        }
        for field, profile in profile_mutations.items():
            with self.subTest(profile=field):
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self.validator.validate_primary_one_host_gate(
                        replace(evidence, generator_profile=profile),
                        target=target,
                        identity=identity,
                        skill_boundary=boundary,
                        accepted_host_receipts=(),
                    )

        with self.assertRaises(PrimaryOneHostGateControlError):
            self.validator.validate_primary_one_host_gate(
                {"forged": "evidence"},
                target=target,
                identity=identity,
                skill_boundary=boundary,
                accepted_host_receipts=(),
            )

    def test_v70_provider_profile_accepts_exact_180_second_timeout(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        profile = _provider_profile(timeout_ms=180_000)
        evidence, refreshed_identity = _formal_evidence(
            course,
            target,
            boundary,
            identity.generation_request_id,
            generator_profile=profile,
            verifier_profile=profile,
        )

        result = self.validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=refreshed_identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

        self.assertEqual(result.outcome, "passed")

        invalid = _provider_profile(timeout_ms=180_001)
        with self.assertRaises(PrimaryOneHostGateControlError):
            self.validator.validate_primary_one_host_gate(
                replace(evidence, generator_profile=invalid),
                target=target,
                identity=refreshed_identity,
                skill_boundary=boundary,
                accepted_host_receipts=(),
            )

    def test_independent_solution_exact_provenance_shape_fails_closed(self):
        _course, target, boundary, evidence, identity = formal_host_fixture(
            "numbers_colors"
        )
        mutations = {}
        for field, value in (
            ("schemaVersion", "forged-schema"),
            ("independentFromGeneration", False),
            ("teachingReview", {"passed": True, "issues": ["forged"]}),
        ):
            solution = copy.deepcopy(evidence.independent_solution)
            solution[field] = value
            mutations[field] = solution
        extra = copy.deepcopy(evidence.independent_solution)
        extra["unknown"] = True
        mutations["unknown"] = extra
        missing = copy.deepcopy(evidence.independent_solution)
        del missing["publicQuestionHash"]
        mutations["missing"] = missing

        for field, solution in mutations.items():
            with self.subTest(field=field):
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self.validator.validate_primary_one_host_gate(
                        replace(evidence, independent_solution=solution),
                        target=target,
                        identity=identity,
                        skill_boundary=boundary,
                        accepted_host_receipts=(),
                    )

    def test_sealed_authority_failure_is_dependency_not_content_rejection(self):
        _course, target, boundary, evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        with mock.patch(
            "services.learning_catalog_validator.primary_one_content_contract",
            side_effect=OSError("authority unavailable"),
        ):
            with self.assertRaises(PrimaryOneHostGateDependencyError):
                self.validator.validate_primary_one_host_gate(
                    evidence,
                    target=target,
                    identity=identity,
                    skill_boundary=boundary,
                    accepted_host_receipts=(),
                )

    def test_isolated_answer_disagreement_is_normal_rejection(self):
        _course, target, boundary, evidence, identity = formal_host_fixture(
            "letters_sounds"
        )
        solution = copy.deepcopy(evidence.independent_solution)
        solution["answers"][0]["answer"] = "option_1"
        result = self.validator.validate_primary_one_host_gate(
            replace(evidence, independent_solution=solution),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )
        self.assertEqual(result.outcome, "rejected")
        self.assertEqual(
            result.receipt["issues"][0]["code"],
            "primary_one_independent_solution_disagreement",
        )

    def test_verification_isolation_is_derived_only_from_profile_hashes(self):
        same = self._run(formal_host_fixture("pinyin_syllables"))
        self.assertEqual(
            same.receipt["verificationIsolation"],
            "isolated_request_same_profile",
        )

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        verifier = _provider_profile(
            name="qwen",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key_env="DASHSCOPE_API_KEY",
        )
        evidence, distinct_identity = _formal_evidence(
            course,
            target,
            boundary,
            identity.generation_request_id,
            verifier_profile=verifier,
        )
        distinct = self.validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=distinct_identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )
        self.assertEqual(
            distinct.receipt["verificationIsolation"],
            "isolated_request_distinct_profile",
        )

    def test_variants_require_exact_prior_passed_immutable_receipts(self):
        first_fixture = formal_host_fixture("pinyin_syllables", variant_ordinal=1)
        first = self._run(first_fixture)
        first_proof = AcceptedPrimaryOneHostReceipt(
            target=first_fixture[1],
            immutable_course=first.course,
            receipt=first.receipt,
            receipt_hash=first.receipt_hash,
        )

        second_fixture = formal_host_fixture("pinyin_syllables", variant_ordinal=2)
        with self.assertRaises(PrimaryOneHostGateControlError):
            self._run(second_fixture)
        second = self._run(second_fixture, accepted=(first_proof,))
        second_proof = AcceptedPrimaryOneHostReceipt(
            target=second_fixture[1],
            immutable_course=second.course,
            receipt=second.receipt,
            receipt_hash=second.receipt_hash,
        )

        third_fixture = formal_host_fixture("pinyin_syllables", variant_ordinal=3)
        with self.assertRaises(PrimaryOneHostGateControlError):
            self._run(third_fixture, accepted=(first_proof,))
        third = self._run(third_fixture, accepted=(first_proof, second_proof))
        self.assertEqual(third.outcome, "passed")

        forged_receipt = copy.deepcopy(first.receipt)
        forged_receipt["outcome"] = "rejected"
        forged = replace(first_proof, receipt=forged_receipt)
        with self.assertRaises(PrimaryOneHostGateControlError):
            self._run(second_fixture, accepted=(forged,))
        wrong_boundary = replace(
            first_proof,
            target=replace(first_proof.target, skill_id="greetings"),
        )
        with self.assertRaises(PrimaryOneHostGateControlError):
            self._run(second_fixture, accepted=(wrong_boundary,))

    def test_prior_receipt_recomputes_boundary_candidate_and_isolation_evidence(self):
        first_fixture = formal_host_fixture("pinyin_syllables", variant_ordinal=1)
        first = self._run(first_fixture)
        proof = AcceptedPrimaryOneHostReceipt(
            target=first_fixture[1],
            immutable_course=first.course,
            receipt=first.receipt,
            receipt_hash=first.receipt_hash,
        )
        self.assertEqual(
            self.validator.validate_primary_one_accepted_receipt(proof),
            first.receipt["hostContentFingerprint"],
        )

        for field in ("skillBoundarySha256", "candidateCourseSha256"):
            with self.subTest(field=field):
                forged_receipt = copy.deepcopy(first.receipt)
                forged_receipt[field] = "0" * 64
                forged = replace(
                    proof,
                    receipt=forged_receipt,
                    receipt_hash=hashlib.sha256(
                        _canonical_json(forged_receipt).encode()
                    ).hexdigest(),
                )
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self.validator.validate_primary_one_accepted_receipt(forged)

        forged_receipt = copy.deepcopy(first.receipt)
        forged_receipt["verificationIsolation"] = (
            "isolated_request_distinct_profile"
        )
        forged_isolation = replace(
            proof,
            receipt=forged_receipt,
            receipt_hash=hashlib.sha256(
                _canonical_json(forged_receipt).encode()
            ).hexdigest(),
        )
        with self.assertRaises(PrimaryOneHostGateControlError):
            self.validator.validate_primary_one_accepted_receipt(
                forged_isolation
            )

        changed_course = copy.deepcopy(first.course)
        changed_course["title"] += "复核版"
        with self.assertRaises(PrimaryOneHostGateControlError):
            self.validator.validate_primary_one_accepted_receipt(
                replace(proof, immutable_course=changed_course)
            )

    def test_semantic_fingerprint_pins_literal_payload_and_digest(self):
        _course, target, _boundary, _evidence, _identity = formal_host_fixture(
            "letters_sounds"
        )
        vector = {
            "gradeCode": "primary_1",
            "subject": "english",
            "nodeCode": "letters_sounds",
            "content": {
                "questions": [
                    {
                        "id": "ignored-1",
                        "type": "exact_text",
                        "prompt": " Ａ\u200b！ ",
                        "answer": " A. ",
                    },
                    {
                        "id": "ignored-2",
                        "type": "single_choice",
                        "prompt": "Pick CAT？",
                        "answer": "dog-id",
                        "choices": [
                            {"id": "cat-id", "label": "Cat!"},
                            {"id": "dog-id", "label": "DOG."},
                        ],
                    },
                    {
                        "id": "ignored-3",
                        "type": "accepted_text",
                        "prompt": "Say hello!",
                        "answer": ["Hi!", " HELLO. "],
                        "acceptedAnswers": ["Hi!", " HELLO. "],
                    },
                    {
                        "id": "ignored-4",
                        "type": "sequence",
                        "prompt": "Order.",
                        "answer": ["two", "one"],
                        "choices": [
                            {"id": "one", "label": "One!"},
                            {"id": "two", "label": "Two?"},
                        ],
                    },
                    {
                        "id": "ignored-5",
                        "type": "numeric",
                        "prompt": "1 + 2.00?",
                        "answer": "03.000",
                        "verificationExpression": "1+2.00",
                    },
                ]
            },
        }
        expected_payload = (
            '{"boundaryVersion":"mira.primary.2026-fall.v1:letters_sounds:'
            '6852d6709825eb79","gradeCode":"primary_1","questions":['
            '{"answer":"3","numericAst":{"operands":[{"type":"decimal",'
            '"value":"2"},{"type":"integer","value":"1"}],"type":"add"},'
            '"optionLabels":[],"prompt":"1+200","type":"numeric"},'
            '{"answer":"a","numericAst":null,"optionLabels":[],"prompt":"a",'
            '"type":"exact_text"},{"answer":"dog","numericAst":null,'
            '"optionLabels":["cat","dog"],"prompt":"pickcat",'
            '"type":"single_choice"},{"answer":["hello","hi"],'
            '"numericAst":null,"optionLabels":[],"prompt":"sayhello",'
            '"type":"accepted_text"},{"answer":["two","one"],'
            '"numericAst":null,"optionLabels":["one","two"],'
            '"prompt":"order","type":"sequence"}],"schemaVersion":'
            '"mira.learning.primary-1-semantic-fingerprint-payload.v1",'
            '"skillId":"letters_sounds","subject":"english"}'
        )
        payload = self.validator.primary_one_content_fingerprint_payload_json(
            vector, target=target
        )
        digest = self.validator.primary_one_content_fingerprint(
            vector, target=target
        )
        self.assertEqual(payload, expected_payload)
        self.assertEqual(
            digest,
            "1d0cf65342de829a5de65e742f38d257405bbb6d850622c8182bb75431d75061",
        )

    def test_semantic_fingerprint_ignores_presentation_but_not_meaning(self):
        course, target, _boundary, _evidence, _identity = formal_host_fixture(
            "letters_sounds"
        )
        baseline = self.validator.primary_one_content_fingerprint(
            course, target=target
        )
        formatting = copy.deepcopy(course)
        formatting["id"] = "different-course-id"
        formatting["content"]["questions"] = list(
            reversed(formatting["content"]["questions"])
        )
        for index, question in enumerate(formatting["content"]["questions"]):
            question["id"] = f"different-{index}"
            question["prompt"] = f" \u200b{question['prompt']}！！！ "
            for choice in question.get("choices", []):
                choice["id"] = f"different-{index}-{choice['id']}"
                choice["label"] = f" {choice['label']}！"
            if question["type"] == "single_choice":
                selected_index = next(
                    choice_index
                    for choice_index, choice in enumerate(course["content"]["questions"])
                    if choice["prompt"].strip() in question["prompt"]
                )
                original = course["content"]["questions"][selected_index]
                selected_label = next(
                    choice["label"]
                    for choice in original["choices"]
                    if choice["id"] == original["answer"]
                )
                question["answer"] = next(
                    choice["id"]
                    for choice in question["choices"]
                    if choice["label"].strip(" ！") == selected_label
                )
        self.assertEqual(
            self.validator.primary_one_content_fingerprint(formatting, target=target),
            baseline,
        )

        changed_answer = copy.deepcopy(course)
        changed_answer["content"]["questions"][0]["answer"] = "option_1"
        self.assertNotEqual(
            self.validator.primary_one_content_fingerprint(
                changed_answer, target=target
            ),
            baseline,
        )
        changed_target_word = copy.deepcopy(course)
        changed_target_word["content"]["questions"][0]["choices"][-1][
            "label"
        ] = "z"
        self.assertNotEqual(
            self.validator.primary_one_content_fingerprint(
                changed_target_word, target=target
            ),
            baseline,
        )
        changed_type = copy.deepcopy(course)
        changed_type["content"]["questions"][0]["type"] = "exact_text"
        self.assertNotEqual(
            self.validator.primary_one_content_fingerprint(changed_type, target=target),
            baseline,
        )

        add_course, add_target, _b, _e, _i = formal_host_fixture(
            "addition_subtraction_20"
        )
        add_fingerprint = self.validator.primary_one_content_fingerprint(
            add_course, target=add_target
        )
        subtract_course = copy.deepcopy(add_course)
        subtract_course["content"]["questions"][0]["verificationExpression"] = "7-5"
        subtract_course["content"]["questions"][0]["answer"] = "2"
        self.assertNotEqual(
            self.validator.primary_one_content_fingerprint(
                subtract_course, target=add_target
            ),
            add_fingerprint,
        )

        vector = copy.deepcopy(course)
        vector_question = vector["content"]["questions"][0]
        vector_question.update(
            {
                "type": "sequence",
                "answer": ["two", "one"],
                "choices": [
                    {"id": "one", "label": "One"},
                    {"id": "two", "label": "Two"},
                ],
            }
        )
        sequence_fingerprint = self.validator.primary_one_content_fingerprint(
            vector, target=target
        )
        vector_question["answer"] = ["one", "two"]
        self.assertNotEqual(
            self.validator.primary_one_content_fingerprint(vector, target=target),
            sequence_fingerprint,
        )

    def test_formatting_only_variant_is_deterministic_duplicate_rejection(self):
        first_fixture = formal_host_fixture("letters_sounds", variant_ordinal=1)
        first = self._run(first_fixture)
        proof = AcceptedPrimaryOneHostReceipt(
            target=first_fixture[1],
            immutable_course=first.course,
            receipt=first.receipt,
            receipt_hash=first.receipt_hash,
        )

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "letters_sounds", variant_ordinal=2
        )
        first_course = first_fixture[0]
        for index, question in enumerate(course["content"]["questions"]):
            original = first_course["content"]["questions"][index]
            question["prompt"] = f"\u200b{original['prompt']}!!!"
            question["answer"] = original["answer"]
            question["choices"] = copy.deepcopy(original["choices"])
            question["evaluation"] = copy.deepcopy(original["evaluation"])
            question["hint"] = original["hint"]
            question["explanation"] = original["explanation"]
            # Task-4 host-owned identities still belong to the second request.
            question["choices"] = [
                {
                    "id": choice["id"],
                    "label": f"{choice['label']}!",
                }
                for choice in question["choices"]
            ]
        evidence, refreshed_identity = _formal_evidence(
            course, target, boundary, identity.generation_request_id
        )
        self.assertEqual(refreshed_identity, identity)
        duplicate = self.validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(proof,),
        )
        self.assertEqual(duplicate.outcome, "rejected")
        self.assertEqual(
            duplicate.receipt["issues"][0]["code"],
            "primary_one_duplicate_variant",
        )

    def test_internal_formatting_only_duplicate_is_sidecar_control_error(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        original = course["content"]["questions"][0]
        duplicate = course["content"]["questions"][4]
        duplicate.update(copy.deepcopy(original))
        duplicate["id"] = f"formal_pinyin_syllables_v1_q5"
        duplicate["prompt"] = original["prompt"].rstrip("?") + "!!!"
        flow = course["content"]["teachingFlow"]
        flow["independentQuestionIds"][-1] = duplicate["id"]
        evidence, refreshed_identity = _formal_evidence(
            course, target, boundary, identity.generation_request_id
        )
        self.assertEqual(refreshed_identity, identity)

        with self.assertRaisesRegex(
            PrimaryOneHostGateControlError,
            "Sidecar question fingerprint duplicates",
        ):
            self.validator.validate_primary_one_host_gate(
                evidence,
                target=target,
                identity=identity,
                skill_boundary=boundary,
                accepted_host_receipts=(),
            )

    def test_host_gate_has_zero_process_network_and_provider_capability(self):
        fixture = formal_host_fixture("number_sense_20")
        with mock.patch(
            "subprocess.run", side_effect=AssertionError("process called")
        ), mock.patch(
            "socket.create_connection", side_effect=AssertionError("network called")
        ), mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("provider called")
        ):
            result = self._run(fixture)
        self.assertEqual(result.outcome, "passed")


if __name__ == "__main__":
    unittest.main()
