from __future__ import annotations

import copy
import unittest
from collections import Counter

from tests.fixtures.primary_math_courses import PRIMARY_MATH_COURSES
from tests.fixtures.primary_subject_catalog import (
    COURSE_SCHEMA_VERSION,
    PRIMARY_COURSE_CATALOG,
    PRIMARY_SUBJECT_CODES,
)
from core.errors import ApiError
from schemas.learning import decode_question_response, question_payload
from services.learning_catalog_validator import (
    LearningCatalogValidator,
    PrimaryOneValidatedVariant,
)
from services.learning_generated_course_validator import (
    AcceptedPrimaryOneHostReceipt,
    LearningGeneratedCourseValidator,
)
from services.learning_question_evaluator import (
    STATUS_CORRECT,
    LearningQuestionEvaluator,
)
from tests.test_learning_generated_course_validator import (
    formal_host_fixture,
    math_candidate,
)


def _choice(question_id, prompt, labels, answer, *, hint="想一想题目里的关系。"):
    return {
        "id": question_id,
        "type": "single_choice",
        "prompt": prompt,
        "answer": answer,
        "skill": "一年级数学",
        "hint": hint,
        "explanation": "提交后再核对题目条件和正确选项。",
        "choices": [
            {"id": option_id, "label": label}
            for option_id, label in labels
        ],
        "evaluation": {
            "expectedOptionId": answer,
            "normalization": ["trim", "casefold"],
        },
    }


def _numeric(question_id, prompt, expression, answer):
    return {
        "id": question_id,
        "type": "numeric",
        "prompt": prompt,
        "answer": answer,
        "skill": "一年级数学",
        "hint": "先判断应该用加法还是减法。",
        "explanation": f"提交后复算，结果是 {answer}。",
        "verificationExpression": expression,
        "evaluation": {
            "expected": answer,
            "normalization": ["trim", "remove_grouping_separators"],
        },
    }


def _generated_p1_math_course(node_code, questions, teach_text):
    question_ids = [question["id"] for question in questions]
    return {
        "id": f"generated_primary_1_math_{node_code}",
        "version": "1.0.0",
        "gradeCode": "primary_1",
        "subject": "math",
        "nodeCode": node_code,
        "title": "一年级数学正式课程",
        "objective": "正式课程目标",
        "status": "published",
        "content": {
            "schemaVersion": "mira.learning.course.v1",
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "sourceAuthority": {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_validated",
                "textbookDependency": "none",
            },
            "reviewPolicy": "programmatic_guarded",
            "intro": "先学会方法，再完成练习。",
            "estimatedMinutes": 10,
            "questions": questions,
            "teachingFlow": {
                "schemaVersion": "mira.learning.teaching-flow.v1",
                "teach": {
                    "title": "先学方法",
                    "sayText": teach_text,
                    "keyPoints": ["看清条件", "独立作答"],
                },
                "demoQuestionId": question_ids[0],
                "guidedQuestionIds": question_ids[1:3],
                "independentQuestionIds": question_ids[3:5],
                "recap": {"sayText": "回顾方法，检查自己的答案。"},
            },
        },
    }


def _valid_number_sense_course():
    questions = [
        _choice("ns_q1", "例题：14和17哪个数更大？", [("A", "14"), ("B", "17")], "B"),
        _choice(
            "ns_q2",
            "从17往后数到20，17和20中间是哪两个数？",
            [("A", "18和19"), ("B", "16和17"), ("C", "19和20")],
            "A",
        ),
        _choice(
            "ns_q3",
            "16由几个十和几个一组成？",
            [("A", "1个十和6个一"), ("B", "1个十和5个一"), ("C", "2个十")],
            "A",
        ),
        _choice(
            "ns_q4",
            "独立比较9和12的大小，哪一个关系正确？",
            [("A", "9大于12"), ("B", "9小于12")],
            "B",
        ),
        _choice(
            "ns_q5",
            "20由几个十和几个一组成？",
            [("A", "2个十和0个一"), ("B", "1个十和0个一"), ("C", "0个十和2个一")],
            "A",
        ),
    ]
    return _generated_p1_math_course(
        "number_sense_20",
        questions,
        "20以内的数可以按顺序数，也可以比较大小。十和一能帮助我们理解数的组成。",
    )


def _valid_add_sub_course():
    questions = [
        _numeric("as_q1", "例题：7+5=?", "7+5", "12"),
        _choice("as_q2", "9+4的结果是哪一个？", [("A", "12"), ("B", "13")], "B"),
        _choice("as_q3", "14-6的结果是哪一个？", [("A", "8"), ("B", "9")], "A"),
        _numeric("as_q4", "小红有6支笔，又得到8支，现在一共有多少支？", "6+8", "14"),
        _numeric("as_q5", "独立计算15-7=?", "15-7", "8"),
    ]
    return _generated_p1_math_course(
        "addition_subtraction_20",
        questions,
        "加法表示合起来，例如8+4=12。减法表示去掉一部分，例如13-4=9。",
    )


def _valid_shapes_position_course():
    questions = [
        _choice("sp_q1", "例题：有三个角的图形叫什么？", [("A", "三角形"), ("B", "圆形")], "A"),
        _choice("sp_q2", "小猫在小狗左边，小狗在小猫哪一边？", [("A", "左边"), ("B", "右边")], "B"),
        _choice("sp_q3", "球在盒子上方，盒子在球的哪一边？", [("A", "上面"), ("B", "下面")], "B"),
        _choice(
            "sp_q4",
            "有四个直角而且四条边相等的是什么图形？",
            [("A", "圆形"), ("B", "正方形"), ("C", "三角形")],
            "B",
        ),
        _choice("sp_q5", "小鸟在树的左边，树在小鸟哪一边？", [("A", "左边"), ("B", "右边")], "B"),
    ]
    course = _generated_p1_math_course(
        "shapes_position",
        questions,
        "圆形、三角形、正方形和长方形都是常见图形。"
        "长方形有四条边和四个角，对边一样长。"
        "正方形是特殊的长方形。位置可以用上下左右描述。",
    )
    course["content"]["teachingFlow"]["recap"]["sayText"] = (
        "回顾圆形、三角形、正方形和长方形，再用上下左右说清位置。"
    )
    return course


class LearningCatalogValidatorTest(unittest.TestCase):
    def setUp(self):
        self.validator = LearningCatalogValidator()

    def test_three_subject_catalog_has_fifty_four_courses_and_270_questions(self):
        self.validator.validate(PRIMARY_COURSE_CATALOG)

        self.assertEqual(len(PRIMARY_COURSE_CATALOG), 54)
        self.assertEqual(
            sum(len(course["content"]["questions"]) for course in PRIMARY_COURSE_CATALOG),
            270,
        )
        self.assertEqual(
            Counter(
                (course["gradeCode"], course["subject"])
                for course in PRIMARY_COURSE_CATALOG
            ),
            Counter(
                {
                    (f"primary_{grade}", subject): 3
                    for grade in range(1, 7)
                    for subject in PRIMARY_SUBJECT_CODES
                }
            ),
        )
        self.assertEqual(
            {course["subject"] for course in PRIMARY_COURSE_CATALOG},
            {"chinese", "math", "english"},
        )
        self.assertTrue(
            all(
                course["content"]["schemaVersion"] == COURSE_SCHEMA_VERSION
                and course["content"]["sessionKind"] == "lesson"
                and course["content"]["outcomeMode"] == "scored_deterministic"
                and course["content"]["reviewPolicy"] == "programmatic_guarded"
                and len(course["content"]["questions"]) == 5
                for course in PRIMARY_COURSE_CATALOG
            )
        )
        question_ids = [
            question["id"]
            for course in PRIMARY_COURSE_CATALOG
            for question in course["content"]["questions"]
        ]
        self.assertEqual(len(question_ids), len(set(question_ids)))

    def test_math_source_is_not_mutated_when_contract_is_added(self):
        self.assertNotIn("schemaVersion", PRIMARY_MATH_COURSES[0]["content"])
        math_copy = next(
            course for course in PRIMARY_COURSE_CATALOG if course["subject"] == "math"
        )
        self.assertEqual(math_copy["content"]["schemaVersion"], COURSE_SCHEMA_VERSION)

    def test_grade_one_and_two_english_are_marked_as_enrichment(self):
        early_english = [
            course
            for course in PRIMARY_COURSE_CATALOG
            if course["subject"] == "english"
            and course["gradeCode"] in {"primary_1", "primary_2"}
        ]

        self.assertEqual(len(early_english), 6)
        self.assertTrue(
            all(
                course["content"]["sourceAuthority"]["basis"]
                == "mira_primary_english_enrichment_v1"
                for course in early_english
            )
        )

    def test_wrong_numeric_answer_is_rejected_before_publish(self):
        changed = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        math_course = next(course for course in changed if course["subject"] == "math")
        math_course["content"]["questions"][0]["answer"] = "999"

        with self.assertRaises(ApiError) as context:
            self.validator.validate(changed)

        self.assertEqual(context.exception.code, "invalid_learning_catalog")
        self.assertIn("复算结果", context.exception.message)

    def test_grade_subject_with_fewer_than_three_courses_is_rejected(self):
        changed = tuple(
            course
            for course in copy.deepcopy(PRIMARY_COURSE_CATALOG)
            if not (
                course["gradeCode"] == "primary_6"
                and course["subject"] == "english"
                and course["nodeCode"] == "reading_information"
            )
        )

        with self.assertRaises(ApiError) as context:
            self.validator.validate(changed)

        self.assertIn("primary_6/english 至少需要 3 门", context.exception.message)

    def test_unknown_subject_and_question_type_are_rejected(self):
        wrong_subject = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        wrong_subject[18]["subject"] = "science"
        with self.assertRaises(ApiError) as subject_context:
            self.validator.validate(wrong_subject)
        self.assertIn("不允许学科", subject_context.exception.message)

        wrong_type = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        wrong_type[18]["content"]["questions"][0]["type"] = "free_response"
        with self.assertRaises(ApiError) as type_context:
            self.validator.validate(wrong_type)
        self.assertIn("不支持的确定性题型", type_context.exception.message)

    def test_expression_whitelist_rejects_function_calls(self):
        changed = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        math_course = next(course for course in changed if course["subject"] == "math")
        math_course["content"]["questions"][0]["verificationExpression"] = (
            "__import__('os').system('echo unsafe')"
        )
        with self.assertRaises(ApiError):
            self.validator.validate(changed)

    def test_single_choice_requires_unique_options_and_valid_answer(self):
        changed = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        question = next(
            question
            for course in changed
            for question in course["content"]["questions"]
            if question["type"] == "single_choice"
        )
        question["choices"][1]["id"] = question["choices"][0]["id"]
        with self.assertRaises(ApiError) as context:
            self.validator.validate(changed)
        self.assertIn("选项 ID 重复", context.exception.message)

    def test_accepted_text_rejects_normalized_duplicate_answers(self):
        changed = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        question = next(
            question
            for course in changed
            for question in course["content"]["questions"]
            if question["type"] == "accepted_text"
        )
        question["answer"] = ["答案", " 答 案 "]
        question["acceptedAnswers"] = ["答案", " 答 案 "]
        question["evaluation"]["acceptedAnswers"] = ["答案", " 答 案 "]
        with self.assertRaises(ApiError) as context:
            self.validator.validate(changed)
        self.assertIn("归一化后重复", context.exception.message)

    def test_sequence_answer_must_be_a_permutation_of_choices(self):
        changed = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        question = next(
            question
            for course in changed
            for question in course["content"]["questions"]
            if question["type"] == "sequence"
        )
        question["answer"] = question["answer"][:-1]
        question["evaluation"]["expectedSequence"] = question["answer"]
        with self.assertRaises(ApiError) as context:
            self.validator.validate(changed)
        self.assertIn("排列全部选项", context.exception.message)

    def test_sequence_choices_cannot_be_preordered_as_the_answer(self):
        changed = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        question = next(
            question
            for course in changed
            for question in course["content"]["questions"]
            if question["type"] == "sequence"
        )
        order = {option_id: index for index, option_id in enumerate(question["answer"])}
        question["choices"].sort(key=lambda option: order[option["id"]])

        with self.assertRaises(ApiError) as context:
            self.validator.validate(changed)

        self.assertIn("不能预先按正确顺序", context.exception.message)

    def test_grade_one_letter_question_is_speech_friendly_choice(self):
        question = next(
            question
            for course in PRIMARY_COURSE_CATALOG
            for question in course["content"]["questions"]
            if question["id"] == "en_g1_ls_q5"
        )

        self.assertEqual(question["type"], "single_choice")
        self.assertIn("/g/ sound", question["prompt"])
        self.assertEqual(question["evaluation"]["expectedOptionId"], "goat")

    def test_private_choice_answers_are_not_always_first(self):
        answer_positions = [
            next(
                index
                for index, option in enumerate(question["choices"])
                if option["id"] == question["evaluation"]["expectedOptionId"]
            )
            for course in PRIMARY_COURSE_CATALOG
            for question in course["content"]["questions"]
            if question["type"] == "single_choice"
        ]

        self.assertGreater(len(set(answer_positions)), 1)
        self.assertLess(answer_positions.count(0), len(answer_positions))

    def test_all_catalog_answers_pass_the_public_choice_round_trip(self):
        evaluator = LearningQuestionEvaluator()
        evaluated = 0
        for course in PRIMARY_COURSE_CATALOG:
            for index, question in enumerate(course["content"]["questions"]):
                seed = f"catalog-test:{course['id']}"
                public = question_payload(
                    question,
                    index=index,
                    attempt_number=1,
                    choice_seed=seed,
                )
                question_type = question["type"]
                if question_type == "single_choice":
                    answer_id = question["evaluation"]["expectedOptionId"]
                    answer_label = next(
                        option["label"]
                        for option in question["choices"]
                        if option["id"] == answer_id
                    )
                    public_id = next(
                        option["id"]
                        for option in public["choices"]
                        if option["label"] == answer_label
                    )
                    response = {
                        "kind": "single_choice",
                        "optionId": public_id,
                    }
                elif question_type == "sequence":
                    labels_by_id = {
                        option["id"]: option["label"]
                        for option in question["choices"]
                    }
                    public_ids_by_label = {
                        option["label"]: option["id"]
                        for option in public["choices"]
                    }
                    response = {
                        "kind": "sequence",
                        "items": [
                            public_ids_by_label[labels_by_id[item_id]]
                            for item_id in question["evaluation"]["expectedSequence"]
                        ],
                    }
                elif question_type == "accepted_text":
                    response = question["evaluation"]["acceptedAnswers"][0]
                else:
                    response = question["answer"]

                decoded = decode_question_response(
                    question,
                    response,
                    choice_seed=f"{seed}:{question['id']}",
                )
                result = evaluator.evaluate(question, decoded)
                self.assertEqual(
                    result["status"],
                    STATUS_CORRECT,
                    f"{course['id']} / {question['id']}",
                )
                self.assertNotIn("answer", public)
                self.assertNotIn("evaluation", public)
                evaluated += 1

        self.assertEqual(evaluated, 270)

    def test_missing_course_contract_and_unsafe_normalization_are_rejected(self):
        missing_contract = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        del missing_contract[0]["content"]["outcomeMode"]
        with self.assertRaises(ApiError) as contract_context:
            self.validator.validate(missing_contract)
        self.assertIn("outcomeMode", contract_context.exception.message)

        unsafe_normalization = copy.deepcopy(PRIMARY_COURSE_CATALOG)
        question = next(
            question
            for course in unsafe_normalization
            for question in course["content"]["questions"]
            if question["type"] == "exact_text"
        )
        question["evaluation"]["normalization"].append("run_python")
        with self.assertRaises(ApiError) as normalization_context:
            self.validator.validate(unsafe_normalization)
        self.assertIn("不安全", normalization_context.exception.message)

    def test_generated_course_requires_valid_teaching_flow_but_static_courses_do_not(self):
        generated = math_candidate()
        generated["status"] = "published"
        generated["content"]["sourceAuthority"] = {
            "basis": "provided_skill_boundary",
            "contentOrigin": "openmaic_kimi_validated",
            "textbookDependency": "none",
        }
        self.validator.validate_course(generated)

        generated["content"].pop("teachingFlow")
        with self.assertRaises(ApiError) as context:
            self.validator.validate_course(generated)
        self.assertIn("teachingFlow", context.exception.message)

        self.validator.validate_course(copy.deepcopy(PRIMARY_COURSE_CATALOG[0]))

    def test_primary_one_math_production_gates_accept_complete_courses(self):
        for course in (
            _valid_number_sense_course(),
            _valid_add_sub_course(),
            _valid_shapes_position_course(),
        ):
            with self.subTest(node_code=course["nodeCode"]):
                self.validator.validate_course(course)

    def test_choice_list_copy_is_rejected_but_math_operands_are_allowed(self):
        semantic_comparison = _valid_number_sense_course()
        q4 = semantic_comparison["content"]["questions"][3]
        q4["prompt"] = "独立比较9和12，哪一个数更大？"
        q4["choices"] = [
            {"id": "A", "label": "9"},
            {"id": "B", "label": "12"},
            {"id": "C", "label": "一样大"},
        ]
        q4["answer"] = "B"
        q4["evaluation"]["expectedOptionId"] = "B"
        self.validator.validate_course(semantic_comparison)

        copied_list = _valid_number_sense_course()
        q2 = copied_list["content"]["questions"][1]
        q2["prompt"] += " 可选18和19、16和17、19和20。"
        with self.assertRaises(ApiError) as context:
            self.validator.validate_course(copied_list)
        self.assertIn("题干重复展示选项文案", context.exception.message)

    def test_production_gate_rejects_practice_answer_leak_and_worked_independent(self):
        leaked = _valid_shapes_position_course()
        leaked["content"]["questions"][2]["hint"] = "答案就在下面。"
        with self.assertRaises(ApiError) as leak_context:
            self.validator.validate_course(leaked)
        self.assertIn("提示直接包含正确选项", leak_context.exception.message)

        leaked_left = _valid_shapes_position_course()
        leaked_left["content"]["questions"][1]["choices"] = [
            {"id": "A", "label": "左"},
            {"id": "B", "label": "右"},
        ]
        leaked_left["content"]["questions"][1]["answer"] = "A"
        leaked_left["content"]["questions"][1]["evaluation"][
            "expectedOptionId"
        ] = "A"
        leaked_left["content"]["questions"][1]["hint"] = "看左边。"
        with self.assertRaises(ApiError) as left_context:
            self.validator.validate_course(leaked_left)
        self.assertIn("提示直接包含正确选项", left_context.exception.message)

        leaked_down = _valid_shapes_position_course()
        leaked_down["content"]["questions"][2]["choices"] = [
            {"id": "A", "label": "上"},
            {"id": "B", "label": "下"},
        ]
        leaked_down["content"]["questions"][2]["hint"] = "答案在下。"
        with self.assertRaises(ApiError) as down_context:
            self.validator.validate_course(leaked_down)
        self.assertIn("提示直接包含正确选项", down_context.exception.message)

        worked = _valid_add_sub_course()
        worked["content"]["questions"][3]["prompt"] += " 先算6+8=14。"
        with self.assertRaises(ApiError) as worked_context:
            self.validator.validate_course(worked)
        self.assertIn("包含已完成的解题步骤", worked_context.exception.message)

    def test_number_sense_gate_requires_20_cross_tens_and_in_boundary_place_value(self):
        missing_twenty = _valid_number_sense_course()
        q2 = missing_twenty["content"]["questions"][1]
        q2["prompt"] = "从14往后数到17，中间是哪两个数？"
        q2["choices"] = [
            {"id": "A", "label": "15和16"},
            {"id": "B", "label": "13和14"},
        ]
        q2["answer"] = "A"
        q2["evaluation"]["expectedOptionId"] = "A"
        q5 = missing_twenty["content"]["questions"][4]
        q5["prompt"] = "18由几个十和几个一组成？"
        q5["choices"] = [
            {"id": "A", "label": "1个十和8个一"},
            {"id": "B", "label": "1个十和7个一"},
        ]
        with self.assertRaises(ApiError) as twenty_context:
            self.validator.validate_course(missing_twenty)
        self.assertIn("边界值 20", twenty_context.exception.message)

        no_cross_tens = _valid_number_sense_course()
        q4 = no_cross_tens["content"]["questions"][3]
        q4["prompt"] = "独立比较13和18的大小，哪一个关系正确？"
        q4["choices"] = [
            {"id": "A", "label": "13大于18"},
            {"id": "B", "label": "13小于18"},
        ]
        with self.assertRaises(ApiError) as cross_context:
            self.validator.validate_course(no_cross_tens)
        self.assertIn("十位数量不同", cross_context.exception.message)

        out_of_boundary = _valid_number_sense_course()
        out_of_boundary["content"]["questions"][2]["choices"][1]["label"] = "6个十和1个一"
        with self.assertRaises(ApiError) as boundary_context:
            self.validator.validate_course(out_of_boundary)
        self.assertIn("超过 20 的数位表示", boundary_context.exception.message)

        self_denial = _valid_number_sense_course()
        self_denial["content"]["teachingFlow"]["teach"]["sayText"] = (
            "13和17的十位分别是1和1？不对。比较十几的数要看个位。"
        )
        with self.assertRaises(ApiError) as denial_context:
            self.validator.validate_course(self_denial)
        self.assertIn("不得否定", denial_context.exception.message)

        wrong_different_tens_example = _valid_number_sense_course()
        wrong_different_tens_example["content"]["teachingFlow"]["teach"][
            "sayText"
        ] = "如果十位不一样，比如18和15，就先比较十位。"
        with self.assertRaises(ApiError) as example_context:
            self.validator.validate_course(wrong_different_tens_example)
        self.assertIn("相同十位", example_context.exception.message)

    def test_number_sense_composition_requires_a_numeral_target_and_distinct_representations(self):
        copied_prompt = _valid_number_sense_course()
        q5 = copied_prompt["content"]["questions"][4]
        q5["prompt"] = "一个数由2个十和0个一组成，这个数是几？"
        with self.assertRaises(ApiError) as prompt_context:
            self.validator.validate_course(copied_prompt)
        self.assertIn("先给出目标数字", prompt_context.exception.message)

        duplicate_value = _valid_number_sense_course()
        duplicate_value["content"]["questions"][4]["choices"][1]["label"] = (
            "2个十和0个一"
        )
        with self.assertRaises(ApiError) as duplicate_context:
            self.validator.validate_course(duplicate_value)
        self.assertTrue(
            "选项文案重复" in duplicate_context.exception.message
            or "表示不同的数" in duplicate_context.exception.message
        )

        wrong_answer = _valid_number_sense_course()
        wrong_answer["content"]["questions"][4]["answer"] = "B"
        wrong_answer["content"]["questions"][4]["evaluation"][
            "expectedOptionId"
        ] = "B"
        with self.assertRaises(ApiError) as answer_context:
            self.validator.validate_course(wrong_answer)
        self.assertIn("与目标数字一致", answer_context.exception.message)

    def test_add_sub_gate_uses_private_ast_for_independent_operation_coverage(self):
        addition_only = _valid_add_sub_course()
        q5 = addition_only["content"]["questions"][4]
        q5.update(
            {
                "prompt": "独立计算7+8=?",
                "answer": "15",
                "verificationExpression": "7+8",
            }
        )
        q5["evaluation"]["expected"] = "15"
        with self.assertRaises(ApiError) as operation_context:
            self.validator.validate_course(addition_only)
        self.assertIn("分别提供加法和减法", operation_context.exception.message)

        nested = _valid_add_sub_course()
        q5 = nested["content"]["questions"][4]
        q5["verificationExpression"] = "20-(5+7)"
        q5["answer"] = "8"
        q5["evaluation"]["expected"] = "8"
        with self.assertRaises(ApiError) as nested_context:
            self.validator.validate_course(nested)
        self.assertIn("一步整数加法或减法", nested_context.exception.message)

        out_of_range = _valid_add_sub_course()
        q5 = out_of_range["content"]["questions"][4]
        q5["prompt"] = "独立计算21-7=?"
        q5["verificationExpression"] = "21-7"
        q5["answer"] = "14"
        q5["evaluation"]["expected"] = "14"
        with self.assertRaises(ApiError) as range_context:
            self.validator.validate_course(out_of_range)
        self.assertIn("0 到 20", range_context.exception.message)

    def test_add_sub_teaching_accepts_spoken_equations_but_keeps_exact_math_gate(self):
        spoken = _valid_add_sub_course()
        spoken["content"]["teachingFlow"]["teach"]["sayText"] = (
            "加法表示合起来，例如8加4等于12。"
            "减法表示去掉一部分，例如13减去4等于9。"
        )
        self.validator.validate_course(spoken)

        wrong_result = copy.deepcopy(spoken)
        wrong_result["content"]["teachingFlow"]["teach"]["sayText"] = (
            "加法表示合起来，例如8加4等于13。"
            "减法表示去掉一部分，例如13减去4等于9。"
        )
        with self.assertRaises(ApiError) as wrong_context:
            self.validator.validate_course(wrong_result)
        self.assertIn("算式结果错误", wrong_context.exception.message)

        incomplete = copy.deepcopy(spoken)
        incomplete["content"]["teachingFlow"]["teach"]["sayText"] = (
            "加法可以试试8加4，减法可以试试13减4。"
        )
        with self.assertRaises(ApiError) as incomplete_context:
            self.validator.validate_course(incomplete)
        self.assertIn("各含一个可复算", incomplete_context.exception.message)

    def test_add_sub_gate_rejects_same_story_equation_and_answer_before_practice(self):
        leaked = _valid_add_sub_course()
        leaked["content"]["teachingFlow"]["teach"]["sayText"] = (
            "加法表示合起来，例如9加4等于13。"
            "减法表示去掉一部分，例如13减去4等于9。"
        )
        with self.assertRaises(ApiError) as context:
            self.validator.validate_course(leaked)
        self.assertIn("已在练习前讲解中出现", context.exception.message)

        different_example = _valid_add_sub_course()
        different_example["content"]["teachingFlow"]["teach"]["sayText"] = (
            "加法表示合起来，例如8加5等于13。"
            "减法表示去掉一部分，例如13减去4等于9。"
        )
        self.validator.validate_course(different_example)

    def test_shapes_gate_rejects_false_square_fact_and_labeled_answer_prompt(self):
        avoids_inclusion = _valid_shapes_position_course()
        avoids_inclusion["content"]["teachingFlow"]["teach"]["sayText"] = (
            "圆形、三角形、正方形和长方形是常见图形。"
            "长方形有四条边和四个角，对边一样长。位置可以用上下左右描述。"
        )
        self.validator.validate_course(avoids_inclusion)

        false_fact = _valid_shapes_position_course()
        false_fact["content"]["teachingFlow"]["teach"]["sayText"] = (
            "圆形、三角形、正方形和长方形都是常见图形。"
            "长方形有四条边和四个角，对边一样长。"
            "正方形不是长方形。位置可以用上下左右描述。"
        )
        with self.assertRaises(ApiError) as fact_context:
            self.validator.validate_course(false_fact)
        self.assertIn("错误或排他的图形", fact_context.exception.message)

        leaked_shape = _valid_shapes_position_course()
        leaked_shape["content"]["questions"][3]["prompt"] += " 请选择B 正方形。"
        with self.assertRaises(ApiError) as shape_context:
            self.validator.validate_course(leaked_shape)
        self.assertTrue(
            "重复展示选项" in shape_context.exception.message
            or "重复展示正确图形" in shape_context.exception.message
        )

        missing_shape_evidence = _valid_shapes_position_course()
        missing_shape_evidence["content"]["questions"][3] = copy.deepcopy(
            missing_shape_evidence["content"]["questions"][4]
        )
        missing_shape_evidence["content"]["questions"][3]["id"] = "sp_q4"
        with self.assertRaises(ApiError) as evidence_context:
            self.validator.validate_course(missing_shape_evidence)
        self.assertIn("分别覆盖识图和位置关系", evidence_context.exception.message)

    def test_shapes_gate_requires_complete_teaching_and_recap_before_practice(self):
        missing_rectangle = _valid_shapes_position_course()
        missing_rectangle["content"]["teachingFlow"]["teach"]["sayText"] = (
            "圆形没有角，三角形有三个角，正方形有四条相等的边。"
            "位置可以用上下左右描述。"
        )
        with self.assertRaises(ApiError) as teach_context:
            self.validator.validate_course(missing_rectangle)
        self.assertIn("练习前明确教学", teach_context.exception.message)

        missing_recap = _valid_shapes_position_course()
        missing_recap["content"]["teachingFlow"]["recap"]["sayText"] = (
            "回顾圆形、三角形和正方形，再用上下左右描述位置。"
        )
        with self.assertRaises(ApiError) as recap_context:
            self.validator.validate_course(missing_recap)
        self.assertIn("总结必须回顾", recap_context.exception.message)

    def test_shapes_rectangle_question_must_exclude_the_square_when_both_are_choices(self):
        ambiguous = _valid_shapes_position_course()
        ambiguous["content"]["questions"][0] = _choice(
            "sp_q1",
            "这个图形有四条边、四个直角，而且对边一样长。它是什么图形？",
            [("A", "长方形"), ("B", "正方形"), ("C", "三角形")],
            "A",
        )
        with self.assertRaises(ApiError) as ambiguous_context:
            self.validator.validate_course(ambiguous)
        self.assertIn("四条边不全相等", ambiguous_context.exception.message)

        disambiguated = copy.deepcopy(ambiguous)
        disambiguated["content"]["questions"][0]["prompt"] = (
            "这个图形有四条边、四个直角、对边一样长，而且四条边不全相等。"
            "它是什么图形？"
        )
        self.validator.validate_course(disambiguated)

    def test_shapes_gate_requires_text_only_questions_to_be_self_contained(self):
        self_contained = _valid_shapes_position_course()
        self_contained["content"]["questions"][1]["prompt"] = (
            "下面哪个图形有三个角？"
        )
        self_contained["content"]["questions"][1]["choices"] = [
            {"id": "A", "label": "三角形"},
            {"id": "B", "label": "圆形"},
        ]
        self_contained["content"]["questions"][1]["answer"] = "A"
        self_contained["content"]["questions"][1]["evaluation"][
            "expectedOptionId"
        ] = "A"
        self.validator.validate_course(self_contained)

        unseen_layout = _valid_shapes_position_course()
        unseen_layout["content"]["questions"][2]["prompt"] = (
            "观察图中的两层图形，下层从左到右依次是什么图形？"
        )
        with self.assertRaises(ApiError) as layout_context:
            self.validator.validate_course(unseen_layout)
        self.assertIn("未随题提供的图像或布局", layout_context.exception.message)


class PrimaryOneFormalVariantSetTest(unittest.TestCase):
    def setUp(self):
        self.catalog_validator = LearningCatalogValidator()
        self.host_validator = LearningGeneratedCourseValidator()

    def _pass_variants(self):
        accepted = []
        variants = []
        for ordinal in (1, 2, 3):
            _course, target, boundary, evidence, identity = formal_host_fixture(
                "pinyin_syllables", variant_ordinal=ordinal
            )
            result = self.host_validator.validate_primary_one_host_gate(
                evidence,
                target=target,
                identity=identity,
                skill_boundary=boundary,
                accepted_host_receipts=tuple(accepted),
            )
            proof = AcceptedPrimaryOneHostReceipt(
                target=target,
                immutable_course=result.course,
                receipt=result.receipt,
                receipt_hash=result.receipt_hash,
            )
            accepted.append(proof)
            variants.append(
                PrimaryOneValidatedVariant(
                    target=target,
                    immutable_course=result.course,
                    receipt=result.receipt,
                    receipt_hash=result.receipt_hash,
                )
            )
        return variants

    def test_formal_three_variant_set_allows_one_node_with_three_receipts(self):
        variants = self._pass_variants()
        self.catalog_validator.validate_primary_one_variant_set(variants)

        with self.assertRaises(ApiError):
            self.catalog_validator.validate_primary_one_variant_set(variants[:2])

        forged = copy.deepcopy(variants[2].receipt)
        forged["hostContentFingerprint"] = "0" * 64
        broken = [
            *variants[:2],
            PrimaryOneValidatedVariant(
                target=variants[2].target,
                immutable_course=variants[2].immutable_course,
                receipt=forged,
                receipt_hash=variants[2].receipt_hash,
            ),
        ]
        with self.assertRaises(ApiError):
            self.catalog_validator.validate_primary_one_variant_set(broken)

    def test_legacy_catalog_still_rejects_duplicate_node_identity(self):
        course = _valid_number_sense_course()
        duplicate = copy.deepcopy(course)
        duplicate["id"] = f"{course['id']}_other"
        duplicate["version"] = "2.0.0"
        with self.assertRaisesRegex(ApiError, "能力点编码重复"):
            self.catalog_validator.validate([course, duplicate])


class PrimaryOneFormalIntrinsicRulesTest(unittest.TestCase):
    def test_simple_sentence_requires_a_complete_sealed_sentence_pattern(self):
        cases = (
            (3, "我你他她?"),
            (2, "一只可爱的。"),
            (4, "飞走了小鸟。"),
            (4, "小鸟桌子。"),
            (4, "妈妈学校。"),
            (4, "孩子苹果。"),
            (4, "小猫水杯。"),
        )
        for question_index, invalid_sentence in cases:
            with self.subTest(invalid_sentence=invalid_sentence):
                course, target, boundary, _evidence, _identity = formal_host_fixture(
                    "simple_sentences"
                )
                question = course["content"]["questions"][question_index]
                for choice in question["choices"]:
                    if choice["id"] == question["answer"]:
                        choice["label"] = invalid_sentence

                with self.assertRaises(ApiError):
                    LearningCatalogValidator().validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_simple_sentence_rejects_predicate_substrings_inside_nouns(self):
        for invalid_sentence in (
            "小画家作品。",
            "我洗衣机。",
            "妈妈的工作。",
            "孩子的学习。",
            "我太空人。",
            "我们真菌。",
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
                course, target, boundary, _evidence, _identity = formal_host_fixture(
                    "simple_sentences"
                )
                question = course["content"]["questions"][4]
                for choice in question["choices"]:
                    if choice["id"] == question["answer"]:
                        choice["label"] = invalid_sentence

                with self.assertRaises(ApiError):
                    LearningCatalogValidator().validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_simple_sentence_accepts_non_golden_sealed_predicate_forms(self):
        for valid_sentence in (
            "爸爸工作。",
            "小狗叫了。",
            "小狗跑步。",
            "我工作。",
            "他学习。",
            "我上学。",
            "我读书。",
            "太太工作。",
            "老太太工作。",
            "妈妈是太空人。",
        ):
            with self.subTest(valid_sentence=valid_sentence):
                course, target, boundary, _evidence, _identity = formal_host_fixture(
                    "simple_sentences"
                )
                question = course["content"]["questions"][4]
                for choice in question["choices"]:
                    if choice["id"] == question["answer"]:
                        choice["label"] = valid_sentence

                checks = (
                    LearningCatalogValidator().validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )
                )

                self.assertIn("inventory:sentence_language_rules", checks)

    def test_simple_sentence_rejects_unsealed_trailing_question_particles(self):
        for invalid_sentence in (
            "小狗叫吗。",
            "小狗叫了呢。",
            "妈妈是老师吗。",
            "我很开心呢。",
        ):
            with self.subTest(invalid_sentence=invalid_sentence):
                course, target, boundary, _evidence, _identity = formal_host_fixture(
                    "simple_sentences"
                )
                question = course["content"]["questions"][4]
                for choice in question["choices"]:
                    if choice["id"] == question["answer"]:
                        choice["label"] = invalid_sentence

                with self.assertRaises(ApiError):
                    LearningCatalogValidator().validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )


if __name__ == "__main__":
    unittest.main()
