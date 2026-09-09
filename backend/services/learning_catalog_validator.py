from __future__ import annotations

import ast
import copy
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    boundaries_for,
    primary_one_content_contract,
)
from core.errors import ApiError


SUPPORTED_PRIMARY_SUBJECTS = frozenset({"chinese", "math", "english"})
SUPPORTED_QUESTION_TYPES = frozenset(
    {"numeric", "exact_text", "accepted_text", "single_choice", "sequence"}
)
COURSE_SCHEMA_VERSION = "mira.learning.course.v1"
TEACHING_FLOW_SCHEMA_VERSION = "mira.learning.teaching-flow.v1"
SOURCE_AUTHORITY = {
    "basis": "national_curriculum_standard_2022",
    "contentOrigin": "mira_original",
    "textbookDependency": "none",
}
GENERATED_SOURCE_AUTHORITY = {
    "basis": "provided_skill_boundary",
    "contentOrigin": "openmaic_kimi_validated",
    "textbookDependency": "none",
}
_NORMALIZATION_BY_TYPE = {
    "numeric": frozenset({"trim", "remove_grouping_separators"}),
    "exact_text": frozenset(
        {
            "trim",
            "collapse_whitespace",
            "remove_whitespace",
            "casefold",
            "strip_terminal_punctuation",
            "strip_punctuation",
        }
    ),
    "accepted_text": frozenset(
        {
            "trim",
            "collapse_whitespace",
            "remove_whitespace",
            "casefold",
            "strip_terminal_punctuation",
            "strip_punctuation",
        }
    ),
    "single_choice": frozenset({"trim", "casefold"}),
    "sequence": frozenset(
        {
            "trim",
            "collapse_whitespace",
            "remove_whitespace",
            "casefold",
            "strip_terminal_punctuation",
            "strip_punctuation",
        }
    ),
}
_TERMINAL_PUNCTUATION = ".!?;:。！？；："


def _previous_non_whitespace_index(text: str, start: int) -> int:
    index = start - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    return index


def _next_non_whitespace_index(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _is_han_character(character: str) -> bool:
    return len(character) == 1 and "\u3400" <= character <= "\u9fff"


_NUMBER_SENSE_COMPOSITION_STRONG_CONTEXT_DELIMITERS = frozenset(
    "。!?！？;；"
)
_NUMBER_SENSE_COMPOSITION_CLAUSE_DELIMITERS = frozenset(
    ",，:：.。!?！？;；、"
)
_NUMBER_SENSE_COMPOSITION_BACKGROUND_TEMPLATES = (
    ("果篮里有", "个水果"),
    ("果篮里有", "个果子"),
    ("企鹅画家有", "支画笔"),
    ("贴纸上的数字是", ""),
    ("果篮上标着数字", ""),
    ("小云雀的贝壳收藏架上标着数字", ""),
    ("小兔子的篮子里有", "个胡萝卜"),
    ("车票上写着", "号"),
    ("地上有", "颗石子"),
    ("上面写着数字", ""),
    ("车票上的数字是", ""),
    ("小水獭用石子摆出了数字", ""),
    ("车身上写着数字", ""),
    ("礼物盒上写着数字", ""),
    ("一共有", "张邮票"),
    ("有一张卡片上写着", ""),
    ("有一张卡片上写着数字", ""),
    ("上面标着数字", ""),
    ("小熊猫的果篮里正好装了", "个果子"),
    ("齿轮零件盒上写着数字", ""),
    ("它看到齿轮上标着数字", ""),
    ("车票上写着数字", ""),
    ("小车上的数字牌写着", ""),
    ("彩旗上写着数字", ""),
    ("小考拉的篮子里装了", "个月亮果"),
    ("贴纸摊位有", "张贴纸"),
    ("小象的礼物盒上写着数字", ""),
    ("看到一张写着数字", "的星星卡"),
    ("小猫书签上写着数字", ""),
    ("其中一张星星卡上写着数字", ""),
    ("星光邮局的花盆标签上写着数字", ""),
    ("有一个花盆上写着", ""),
    ("写着", ""),
    ("上面画着数字", ""),
    ("卡片上写着数字", ""),
    ("小刺猬有", "颗石子"),
    ("盒子装了", "个积木"),
    ("小猫钓到了", "条鱼"),
    ("拼板一共是", "块"),
    ("卡片写着", ""),
    ("卡片写着", "号"),
    ("卡片写着数字", ""),
    ("卡片的数字是", ""),
    ("小狐狸有一张写着数字", "的星星卡"),
    ("小狐狸有一张写着数字", "的车票"),
    ("它已经贴好了", "张贴纸"),
)
_NUMBER_SENSE_COMPOSITION_CHINESE_NUMERAL_PATTERN = re.compile(
    r"[零〇一二三四五六七八九十拾百佰千仟万萬亿億兆廿卅卌两兩壹贰貳叁參肆伍陆陸柒捌玖]+"
)
_NUMBER_SENSE_COMPOSITION_PAIRED_CUE_PATTERN = re.compile(
    r"几个十 *(?:和|与|、) *几个一"
)
_NUMBER_SENSE_COMPOSITION_FULL_QUESTION_PATTERN = re.compile(
    r"(?<![0-9])([0-9]{1,2})(?![0-9]) *(?:(?:这个|该)(?:数|数字) *)?"
    r"(?:(是由|由) *几个十 *(?:和|与|、) *几个一 *组成(?:的)?"
    r"|(里面有) *几个十 *(?:和|与|、) *几个一) *[？?]"
)


def _number_sense_composition_target_occurrence_has_allowed_left_context(
    text: str, token_start: int
) -> bool:
    prefix = text[:token_start].strip(" ")
    if not prefix:
        return True
    if prefix[-1] in _NUMBER_SENSE_COMPOSITION_STRONG_CONTEXT_DELIMITERS:
        return True
    last_delimiter_index = max(
        (
            index
            for index, character in enumerate(prefix)
            if character in _NUMBER_SENSE_COMPOSITION_STRONG_CONTEXT_DELIMITERS
        ),
        default=-1,
    )
    segment = prefix[last_delimiter_index + 1 :].strip(" ")
    return re.fullmatch(
        r"(?:数字|(?:请问|那么|其中) *[:：,，]?|小云雀想知道[:：])",
        segment,
    ) is not None


def _number_sense_composition_clause_bounds(
    text: str, token_start: int, token_end: int
) -> tuple[int, int]:
    start = 0
    for index in range(token_start - 1, -1, -1):
        if text[index] in _NUMBER_SENSE_COMPOSITION_CLAUSE_DELIMITERS:
            start = index + 1
            break
    end = len(text)
    for index in range(token_end, len(text)):
        if text[index] in _NUMBER_SENSE_COMPOSITION_CLAUSE_DELIMITERS:
            end = index
            break
    return start, end


def _number_sense_composition_background_occurrence_has_allowed_role(
    text: str, token_start: int, token_end: int
) -> bool:
    clause_start, clause_end = _number_sense_composition_clause_bounds(
        text, token_start, token_end
    )
    raw_clause = text[clause_start:clause_end]
    leading_length = len(raw_clause) - len(raw_clause.lstrip(" "))
    clause = raw_clause.strip(" ")
    relative_start = token_start - clause_start - leading_length
    relative_end = token_end - clause_start - leading_length
    token = text[token_start:token_end]
    return any(
        clause == f"{prefix}{token}{suffix}"
        and relative_start == len(prefix)
        and relative_end == len(prefix) + len(token)
        for prefix, suffix in _NUMBER_SENSE_COMPOSITION_BACKGROUND_TEMPLATES
    )


def _has_invalid_number_sense_target_right_continuation(
    text: str, start: int
) -> bool:
    index = _next_non_whitespace_index(text, start)
    if index >= len(text):
        return False
    character = text[index]
    return character in "_+-−负./*×÷∕%点" or (
        character.isascii() and character.isalnum()
    )


def _number_sense_composition_raw_numeric_characters_are_allowed(text: str) -> bool:
    for character in text:
        allowed_raw_digit = "0" <= character <= "9" or "０" <= character <= "９"
        normalized_contains_ascii_digit = any(
            "0" <= normalized_character <= "9"
            for normalized_character in unicodedata.normalize("NFKC", character)
        )
        category = unicodedata.category(character)
        is_decimal_number = category == "Nd"
        if not allowed_raw_digit and (
            normalized_contains_ascii_digit
            or is_decimal_number
            or category in {"Nl", "No"}
        ):
            return False
    return True


def _normalize_number_sense_composition_python_whitespace(text: str) -> str:
    mapped = "".join(" " if character.isspace() else character for character in text)
    return re.sub(r" +", " ", mapped)


def _number_sense_composition_has_chinese_numeral_in_numeric_role(
    text: str,
) -> bool:
    for match in _NUMBER_SENSE_COMPOSITION_CHINESE_NUMERAL_PATTERN.finditer(text):
        if _number_sense_composition_background_occurrence_has_allowed_role(
            text, match.start(), match.end()
        ):
            return True
        suffix = text[match.end() :]
        if (
            _number_sense_composition_target_occurrence_has_allowed_left_context(
                text, match.start()
            )
            and re.match(
                r"^(?: *(?:(?:这个|该)(?:数|数字) *)?"
                r"(?:(?:是由|由) *几个十 *(?:和|与|、) *几个一 *组成(?:的)?"
                r"|里面有 *几个十 *(?:和|与|、) *几个一) *[？?])",
                suffix,
            )
        ):
            return True
    return False


def _number_sense_composition_raw_prompt_is_allowed(raw_prompt: str) -> bool:
    if not _number_sense_composition_raw_numeric_characters_are_allowed(raw_prompt):
        return False
    if any(
        character in raw_prompt
        for character in "\u000A\u000B\u000C\u000D\u0085\u2028\u2029\uFEFF"
    ):
        return False
    normalized = _normalize_number_sense_composition_python_whitespace(
        unicodedata.normalize("NFKC", raw_prompt)
    )
    return not _number_sense_composition_has_chinese_numeral_in_numeric_role(
        normalized
    )


def _parse_number_sense_composition_prompt(
    question: Mapping[str, object], *, require_from_composition: bool = False
) -> dict[str, object] | None:
    if question.get("type") != "single_choice":
        return None
    raw_prompt = str(question.get("prompt") or question.get("question") or "")
    if not _number_sense_composition_raw_prompt_is_allowed(raw_prompt):
        return None
    prompt = _normalize_number_sense_composition_python_whitespace(
        unicodedata.normalize("NFKC", raw_prompt)
    )
    tens_cues = list(re.finditer(r"几个十", prompt))
    ones_cues = list(re.finditer(r"几个一", prompt))
    paired_cues = list(
        _NUMBER_SENSE_COMPOSITION_PAIRED_CUE_PATTERN.finditer(prompt)
    )
    semantic_matches = list(
        _NUMBER_SENSE_COMPOSITION_FULL_QUESTION_PATTERN.finditer(prompt)
    )
    if (
        len(tens_cues) != 1
        or len(ones_cues) != 1
        or len(paired_cues) != 1
        or len(semantic_matches) != 1
    ):
        return None
    semantic_match = semantic_matches[0]
    paired_cue = paired_cues[0]
    if not (
        semantic_match.start() <= paired_cue.start()
        and paired_cue.end() <= semantic_match.end()
    ):
        return None
    semantic_kind = "from" if semantic_match.group(2) else "inside"
    if require_from_composition and semantic_kind != "from":
        return None
    target_token_start = semantic_match.start(1)
    target_token_end = semantic_match.end(1)
    if not _number_sense_composition_target_occurrence_has_allowed_left_context(
        prompt, target_token_start
    ):
        return None
    tokens = list(re.finditer(r"[0-9]+", prompt))
    if not tokens:
        return None
    values: list[int] = []
    for token in tokens:
        raw = token.group(0)
        value = int(raw)
        if (
            re.fullmatch(r"(?:0|[1-9][0-9]*)", raw) is None
            or int(raw) > 9_007_199_254_740_991
            or not 0 <= value <= 20
            or _has_invalid_number_sense_target_right_continuation(
                prompt, token.end()
            )
        ):
            return None
        values.append(value)
    distinct_values = set(values)
    if len(distinct_values) != 1:
        return None
    target = int(semantic_match.group(1))
    if target not in distinct_values:
        return None
    for token in tokens:
        if token.start() == target_token_start and token.end() == target_token_end:
            continue
        if not _number_sense_composition_background_occurrence_has_allowed_role(
            prompt, token.start(), token.end()
        ):
            return None
    return {
        "prompt": prompt,
        "target": target,
        "semantic_kind": semantic_kind,
        "semantic_start": semantic_match.start(),
        "semantic_end": semantic_match.end(),
        "target_token_start": target_token_start,
        "target_token_end": target_token_end,
    }


def _number_sense_composition_prompt_target(
    question: Mapping[str, object], *, require_from_composition: bool = False
) -> int | None:
    parsed = _parse_number_sense_composition_prompt(
        question, require_from_composition=require_from_composition
    )
    return int(parsed["target"]) if parsed is not None else None


@dataclass(frozen=True)
class PrimaryOneCourseTarget:
    grade_code: str
    subject: str
    subject_ordinal: int
    skill_id: str
    boundary_ordinal: int
    boundary_version: str
    variant_ordinal: int
    instruction_language_code: str
    target_language_code: str


@dataclass(frozen=True)
class PrimaryOneValidatedVariant:
    target: PrimaryOneCourseTarget
    immutable_course: Mapping[str, object]
    receipt: Mapping[str, object]
    receipt_hash: str


class LearningCatalogValidator:
    """Rejects content that cannot be scored safely and deterministically."""

    def validate(self, courses: Sequence[dict]) -> None:
        if isinstance(courses, (str, bytes, Mapping)) or not isinstance(
            courses, Sequence
        ):
            self._reject("课程目录必须是序列")

        course_versions: set[tuple[str, str]] = set()
        course_nodes: set[tuple[str, str, str]] = set()
        grade_subject_counts = {
            (f"primary_{grade}", subject): 0
            for grade in range(1, 7)
            for subject in SUPPORTED_PRIMARY_SUBJECTS
        }
        question_ids: set[str] = set()

        for course in courses:
            self._required_course_fields(course)
            identity = (str(course["id"]), str(course["version"]))
            if identity in course_versions:
                self._reject("课程 ID 和版本重复")
            course_versions.add(identity)

            node_identity = (
                str(course["gradeCode"]),
                str(course["subject"]),
                str(course["nodeCode"]),
            )
            if node_identity in course_nodes:
                self._reject("同年级学科的能力点编码重复")
            course_nodes.add(node_identity)
            grade_subject_counts[node_identity[:2]] += 1

            if course["status"] != "published":
                self._reject("内置课程必须是 published 状态")
            content = course.get("content")
            self._validate_content(content, course)
            questions = content["questions"]
            for question in questions:
                self._validate_question(question, question_ids)
            self._validate_generated_primary_content(course, content)

        for (grade_code, subject), count in grade_subject_counts.items():
            if count < 3:
                self._reject(f"{grade_code}/{subject} 至少需要 3 门课程")

    def validate_course(self, course: dict) -> None:
        """Validate one publishable course without catalog-wide coverage rules."""

        self._required_course_fields(course)
        if course["status"] != "published":
            self._reject("课程必须是 published 状态")
        content = course.get("content")
        self._validate_content(content, course)
        question_ids: set[str] = set()
        for question in content["questions"]:
            self._validate_question(question, question_ids)
        self._validate_generated_primary_content(course, content)

    def validate_primary_one_generated_course(
        self,
        course: Mapping[str, object],
        *,
        target: PrimaryOneCourseTarget,
        skill_boundary: Mapping[str, object],
    ) -> tuple[str, ...]:
        """Apply the one repository-owned Grade-1 semantic implementation.

        This method is intentionally pure.  It accepts either the immutable
        unverified candidate at the Host boundary or the already-published
        projection used by the later catalog recheck.  It never changes the
        caller's object.
        """

        context = self._primary_one_context(target, skill_boundary)
        if not isinstance(course, Mapping):
            self._reject("一年级正式候选必须是对象")
        raw = copy.deepcopy(dict(course))
        if (
            raw.get("status") == "unverified"
            and isinstance(raw.get("content"), Mapping)
            and raw["content"].get("sourceAuthority")
            == {
                "basis": "provided_skill_boundary",
                "contentOrigin": "openmaic_kimi_candidate",
                "textbookDependency": "none",
            }
        ):
            publishable = copy.deepcopy(raw)
            publishable["status"] = "published"
            publishable["content"]["sourceAuthority"] = copy.deepcopy(
                GENERATED_SOURCE_AUTHORITY
            )
        elif (
            raw.get("status") == "published"
            and isinstance(raw.get("content"), Mapping)
            and raw["content"].get("sourceAuthority") == GENERATED_SOURCE_AUTHORITY
        ):
            publishable = raw
        else:
            self._reject("一年级正式候选状态或内容权威无效")

        if (
            publishable.get("gradeCode") != target.grade_code
            or publishable.get("subject") != target.subject
            or publishable.get("nodeCode") != target.skill_id
        ):
            self._reject("一年级正式候选与目标身份不一致")
        expected_objective = unicodedata.normalize(
            "NFKC", "；".join(context["registered"].learning_objectives)
        ).strip()
        if publishable.get("objective") != expected_objective:
            self._reject("一年级正式候选学习目标超出固定边界")

        self.validate_course(publishable)
        content = publishable["content"]
        questions = content["questions"]
        self._validate_primary_one_common_semantics(
            publishable,
            content,
            questions,
            target,
            context,
        )
        inventory_kinds = tuple(
            context["contract"]["inventories"][key]["kind"]
            for key in context["authority_boundary"]["validationInventoryKeys"]
        )
        dispatcher = {
            "pinyin_vowel_rules": self._validate_primary_one_pinyin_vowels,
            "pinyin_initial_rules": self._validate_primary_one_pinyin_initials,
            "character_radical_word_relation_rules": (
                self._validate_primary_one_characters_words
            ),
            "sentence_language_rules": self._validate_primary_one_sentences,
            "number_sense_rules": self._validate_primary_one_number_sense,
            "arithmetic_ast_rules": self._validate_primary_one_add_sub,
            "shape_position_rules": self._validate_primary_one_shapes,
            "letter_initial_sound_rules": self._validate_primary_one_letters,
            "greeting_phrase_rules": self._validate_primary_one_greetings,
            "number_color_rules": self._validate_primary_one_numbers_colors,
        }
        validator = next(
            (dispatcher[kind] for kind in inventory_kinds if kind in dispatcher),
            None,
        )
        if validator is None:
            self._reject("一年级正式候选缺少版本化验证器")
        validator(questions, content, context)
        return (
            "formal_schema",
            "target_binding",
            "five_role_contract",
            "answer_blind_practice",
            "deterministic_scoring",
            "subject_language_policy",
            f"inventory:{inventory_kinds[0]}",
        )

    def validate_primary_one_variant_set(
        self, variants: Sequence[PrimaryOneValidatedVariant]
    ) -> None:
        if isinstance(variants, (str, bytes, Mapping)) or not isinstance(
            variants, Sequence
        ):
            self._reject("一年级正式变体集合必须是序列")
        if len(variants) != 3 or any(
            not isinstance(item, PrimaryOneValidatedVariant) for item in variants
        ):
            self._reject("一年级正式边界必须恰好包含三个已验证变体")
        ordered = sorted(variants, key=lambda item: item.target.variant_ordinal)
        if [item.target.variant_ordinal for item in ordered] != [1, 2, 3]:
            self._reject("一年级正式变体序号必须精确为1、2、3")
        first = ordered[0].target
        stable = (
            first.grade_code,
            first.subject,
            first.subject_ordinal,
            first.skill_id,
            first.boundary_ordinal,
            first.boundary_version,
            first.instruction_language_code,
            first.target_language_code,
        )
        identities: set[tuple[str, str]] = set()
        fingerprints: set[str] = set()
        from services.learning_generated_course_validator import (
            AcceptedPrimaryOneHostReceipt,
            LearningGeneratedCourseValidator,
            PrimaryOneHostGateControlError,
        )

        receipt_validator = LearningGeneratedCourseValidator()
        for item in ordered:
            target = item.target
            if (
                target.grade_code,
                target.subject,
                target.subject_ordinal,
                target.skill_id,
                target.boundary_ordinal,
                target.boundary_version,
                target.instruction_language_code,
                target.target_language_code,
            ) != stable:
                self._reject("一年级正式变体集合跨越了能力边界")
            context = self._primary_one_context(target, None)
            boundary = context["skill_boundary"]
            self.validate_primary_one_generated_course(
                item.immutable_course,
                target=target,
                skill_boundary=boundary,
            )
            try:
                fingerprint = receipt_validator.validate_primary_one_accepted_receipt(
                    AcceptedPrimaryOneHostReceipt(
                        target=target,
                        immutable_course=item.immutable_course,
                        receipt=item.receipt,
                        receipt_hash=item.receipt_hash,
                    )
                )
            except PrimaryOneHostGateControlError as exc:
                self._reject(f"一年级正式变体回执无效: {exc}")
            identity = (
                str(item.immutable_course.get("id") or ""),
                str(item.immutable_course.get("version") or ""),
            )
            if not all(identity) or identity in identities:
                self._reject("一年级正式变体课程ID和版本必须互不相同")
            if fingerprint in fingerprints:
                self._reject("一年级正式变体语义指纹必须互不相同")
            identities.add(identity)
            fingerprints.add(fingerprint)

    def _primary_one_context(
        self,
        target: PrimaryOneCourseTarget,
        skill_boundary: Mapping[str, object] | None,
    ) -> dict[str, Any]:
        contract = primary_one_content_contract()
        if not isinstance(target, PrimaryOneCourseTarget):
            self._reject("一年级正式目标类型无效")
        for label, value in (
            ("subjectOrdinal", target.subject_ordinal),
            ("boundaryOrdinal", target.boundary_ordinal),
            ("variantOrdinal", target.variant_ordinal),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                self._reject(f"一年级正式目标{label}必须是整数")
        if target.grade_code != "primary_1" or target.variant_ordinal not in {1, 2, 3}:
            self._reject("一年级正式目标年级或变体无效")
        subject_policy = next(
            (
                item
                for item in contract["subjects"]
                if item["subject"] == target.subject
            ),
            None,
        )
        if subject_policy is None:
            self._reject("一年级正式目标学科无效")
        if (
            subject_policy["subjectOrdinal"] != target.subject_ordinal
            or subject_policy["instructionLanguageCode"]
            != target.instruction_language_code
            or subject_policy["targetLanguageCode"] != target.target_language_code
        ):
            self._reject("一年级正式目标学科序号或语言策略漂移")
        authority_boundary = next(
            (
                item
                for item in subject_policy["boundaries"]
                if item["skillId"] == target.skill_id
            ),
            None,
        )
        registered = next(
            (
                item
                for item in boundaries_for("primary_1", target.subject)
                if item.skill_id == target.skill_id
            ),
            None,
        )
        if authority_boundary is None or registered is None:
            self._reject("一年级正式目标能力边界无效")
        if (
            authority_boundary["boundaryOrdinal"] != target.boundary_ordinal
            or registered.boundary_version != target.boundary_version
            or tuple(authority_boundary["prerequisiteSkills"])
            != registered.prerequisite_skills
        ):
            self._reject("一年级正式目标边界版本或先修关系漂移")
        expected_boundary = {
            "skillId": registered.skill_id,
            "skillTitle": registered.skill_title,
            "learningObjectives": list(registered.learning_objectives),
            "allowedContent": list(registered.allowed_content),
            "excludedContent": list(registered.excluded_content),
            "prerequisiteSkills": list(registered.prerequisite_skills),
            "estimatedMinutes": 10,
        }
        if skill_boundary is not None:
            if not isinstance(skill_boundary, Mapping) or dict(skill_boundary) != expected_boundary:
                self._reject("一年级正式skillBoundary与密封权威不一致")
        return {
            "contract": contract,
            "subject_policy": subject_policy,
            "authority_boundary": authority_boundary,
            "registered": registered,
            "skill_boundary": expected_boundary,
        }

    def _validate_primary_one_common_semantics(
        self,
        course: Mapping[str, Any],
        content: Mapping[str, Any],
        questions: Sequence[Mapping[str, Any]],
        target: PrimaryOneCourseTarget,
        context: Mapping[str, Any],
    ) -> None:
        flow = content["teachingFlow"]
        expected_ids = [str(question["id"]) for question in questions]
        roles = [
            str(flow["demoQuestionId"]),
            *[str(item) for item in flow["guidedQuestionIds"]],
            *[str(item) for item in flow["independentQuestionIds"]],
        ]
        if roles != expected_ids:
            self._reject("一年级正式课程题目角色必须按q1到q5固定")
        for index, question in enumerate(questions):
            public_text = " ".join(
                str(question.get(key) or "")
                for key in ("prompt", "hint", "explanation")
            )
            if re.search(r"<[^>]+>|https?://|javascript:", public_text, re.I):
                self._reject("一年级正式题目必须是安全纯文本")
            if any(
                unicodedata.category(char) == "Cc" and not char.isspace()
                for char in public_text
            ):
                self._reject("一年级正式题目包含不安全控制字符")
            prompt = self._compact_text(question.get("prompt"))
            if prompt in {"请选择正确答案。", "请选择正确答案", "选择正确答案"}:
                self._reject("一年级正式题目无法唯一确定评分依据")
            if index >= 1 and self._formal_question_reveals_answer(question):
                self._reject("一年级正式练习题提示或题干泄漏答案")
        self._validate_independent_prompts(questions[3:5])
        all_text = self._course_instructional_text(content)
        for excluded in context["registered"].excluded_content:
            if self._compact_text(excluded) in self._compact_text(all_text):
                self._reject("一年级正式课程包含边界外教学内容")
        if target.target_language_code == "en-US":
            for question in questions:
                for value in self._formal_answer_labels(question):
                    if re.search(r"[\u3400-\u9fff]", value):
                        self._reject("一年级英语考核目标必须使用en-US词汇")

    def _formal_question_reveals_answer(self, question: Mapping[str, Any]) -> bool:
        hint = self._compact_text(question.get("hint"))
        semantic_hint = self._formal_semantic_text(question.get("hint"))
        combined = self._compact_text(
            f"{question.get('prompt') or ''} {question.get('hint') or ''}"
        )
        for answer in self._formal_answer_labels(question):
            normalized = self._compact_text(answer)
            semantic_answer = self._formal_semantic_text(answer)
            if normalized and (
                hint == normalized
                or (semantic_answer and semantic_hint == semantic_answer)
            ):
                return True
            if normalized and re.search(
                rf"(?:正确答案|答案|结果|应选|选择)(?:是|为)?[:：]?{re.escape(normalized)}(?:$|[,.!?;:，。！？；：])",
                combined,
                re.I,
            ):
                return True
        return False

    @staticmethod
    def _formal_answer_labels(question: Mapping[str, Any]) -> list[str]:
        question_type = str(question.get("type") or "")
        if question_type == "single_choice":
            answer = str(question.get("answer") or "")
            return [
                str(choice.get("label") or "")
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping) and str(choice.get("id") or "") == answer
            ]
        if question_type == "sequence":
            by_id = {
                str(choice.get("id") or ""): str(choice.get("label") or "")
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping)
            }
            return [by_id.get(str(item), "") for item in question.get("answer") or []]
        if question_type == "accepted_text":
            return [str(item) for item in question.get("answer") or []]
        return [str(question.get("answer") or "")]

    def _require_selected(self, question: Mapping[str, Any], expected: Sequence[str]) -> None:
        selected = [
            self._formal_semantic_text(item)
            for item in self._formal_answer_labels(question)
        ]
        wanted = {self._formal_semantic_text(item) for item in expected}
        if len(selected) == 1 and selected[0] in wanted:
            return
        if (
            len(selected) == 1
            and str(question.get("skill") or "") == "20以内加减法"
            and wanted
            and all(re.fullmatch(r"-?\d+", value) for value in wanted)
        ):
            measured = re.fullmatch(
                r"(-?\d+)(?:个|张|片|颗|本|只|支|朵|块|枚|条|辆|人|棵|盒|袋|根|把|件|次|米|厘米|元)",
                selected[0],
            )
            if measured is not None and measured.group(1) in wanted:
                return
        self._reject("一年级正式题目的确定性答案与版本化权威不一致")

    @staticmethod
    def _formal_semantic_text(value: object) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
        return text.rstrip(_TERMINAL_PUNCTUATION).rstrip()

    @staticmethod
    def _primary_one_pinyin_sound_cue_is_evidence(
        prompt: str, sound_cue: str
    ) -> bool:
        if not sound_cue:
            return False
        search_index = 0
        while search_index < len(prompt):
            cue_index = prompt.find(sound_cue, search_index)
            if cue_index < 0:
                return False
            left_context = prompt[max(0, cue_index - 16) : cue_index]
            if re.search(
                r"(?:听到|听见|发音|发出|读(?:作)?|念作|读音|声音)"
                r"[^\u3002！？!?；;]{0,10}$",
                left_context,
            ):
                return True
            opening_quote = prompt[max(0, cue_index - 1) : cue_index]
            right_context = prompt[
                cue_index + len(sound_cue) : cue_index + len(sound_cue) + 18
            ]
            if (
                opening_quote in {'"', "'", "“", "‘"}
                and right_context[:1] in {'"', "'", "”", "’"}
            ):
                after_quote = right_context[1:]
                if re.match(
                    r"(?:的)?(?:基本)?(?:发音|读音|声音)",
                    after_quote,
                ) or re.match(
                    r"[\s,，.。!！?？;；:：]{0,3}"
                    r"(?:这个|这种|该)(?:基本)?(?:发音|读音|声音)",
                    after_quote,
                ):
                    return True
            search_index = cue_index + len(sound_cue)
        return False

    def _validate_primary_one_pinyin_vowels(self, questions, content, context):
        rules = context["contract"]["inventories"][
            "chinese.pinyin_vowels_aoe.v1"
        ]["rules"]
        instructional_text = self._compact_text(
            self._course_instructional_text(content)
        )
        if any(
            self._compact_text(target) in instructional_text
            for target in rules["forbiddenTeachingTargets"]
        ):
            self._reject("a/o/e课程包含密封权威禁止的教学目标")
        symbols = rules["symbols"]
        for question in questions:
            prompt = str(question.get("prompt") or "")
            expected = {
                item["symbol"]
                for item in symbols
                if item["mouthShape"] in prompt
                or self._primary_one_pinyin_sound_cue_is_evidence(
                    prompt, item["soundCue"]
                )
            }
            expected.update(
                re.findall(
                    r"(?:跟我读|跟读)[^。！？!?；;]{0,16}?"
                    r"(?<![A-Za-z])([aoe])(?![A-Za-z])",
                    prompt,
                )
            )
            if len(expected) != 1:
                self._reject("a/o/e题目缺少唯一口形或听音证据")
            self._require_selected(question, sorted(expected))

    def _validate_primary_one_pinyin_initials(self, questions, content, context):
        inventories = context["contract"]["inventories"]
        initial_rules = inventories["chinese.initials.v1"]["rules"]
        syllable_rules = inventories[
            "chinese.simple_syllables.v1"
        ]["rules"]
        initials = tuple(
            sorted(initial_rules["initials"], key=len, reverse=True)
        )
        learned_finals = set(initial_rules["learnedFinals"])
        allowed = set(syllable_rules["syllables"])
        initial_pattern = "|".join(re.escape(item) for item in initials)
        for question in questions:
            match = re.search(
                rf"声母\s*({initial_pattern})\s*和韵母\s*([A-Za-z])",
                unicodedata.normalize("NFKC", str(question.get("prompt") or "")),
                re.I,
            )
            if not match:
                self._reject("声母音节题缺少可复算的两拼证据")
            initial = match.group(1).casefold()
            final = match.group(2).casefold()
            expected = f"{initial}{final}"
            if (
                initial not in set(initial_rules["initials"])
                or final not in learned_finals
                or expected not in allowed
                or syllable_rules["maxComponents"] != 2
            ):
                self._reject("声母音节题超出密封音节表")
            self._require_selected(question, [expected])
        if (
            initial_rules["toneOrdinals"] != [1, 2, 3, 4]
            or "四声" not in self._course_instructional_text(content)
        ):
            self._reject("声母音节课程必须覆盖密封的一至四声初步")

    def _validate_primary_one_characters_words(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "chinese.common_characters_radicals_words.v1"
        ]["rules"]
        characters = {item["character"]: item for item in rules["characters"]}
        radical_by_character = {
            character: item["radical"]
            for item in rules["radicals"]
            for character in item["characters"]
        }
        relations = rules["wordRelations"]
        for question in questions:
            prompt = str(question.get("prompt") or "")
            quoted = re.search(r"[“\"]([^”\"]+)[”\"]", prompt)
            token = quoted.group(1) if quoted else ""
            expected: list[str] = []
            if "读音" in prompt and token in characters:
                expected = [characters[token]["reading"]]
            elif "偏旁" in prompt and token in radical_by_character:
                expected = [radical_by_character[token]]
            elif "反义词" in prompt:
                expected = [
                    item["right"]
                    for item in relations
                    if item["relation"] == "antonym" and item["left"] == token
                ]
            elif "搭配" in prompt:
                expected = [
                    item["right"]
                    for item in relations
                    if item["relation"] == "collocation" and item["left"] == token
                ]
            elif "量词" in prompt:
                expected = [
                    item["classifier"]
                    for item in relations
                    if item["relation"] == "classifier" and item["noun"] == token
                ]
            if len(expected) != 1:
                self._reject("汉字词语题缺少唯一版本化关系")
            self._require_selected(question, expected)

    def _validate_primary_one_sentences(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "chinese.simple_sentence_punctuation.v1"
        ]["rules"]
        pattern_slots = {
            str(pattern["id"]): tuple(str(slot) for slot in pattern["slots"])
            for pattern in rules["sentencePatterns"]
            if isinstance(pattern, Mapping)
        }
        completeness_rules = set(rules["requiredCompleteness"])
        punctuation_by_intent = {
            str(item["intent"]): unicodedata.normalize("NFKC", str(item["terminal"]))
            for item in rules["punctuationRules"]
            if isinstance(item, Mapping)
        }
        for question in questions:
            selected = self._formal_answer_labels(question)
            if len(selected) != 1:
                self._reject("完整句子题必须有唯一答案")
            sentence = unicodedata.normalize("NFKC", selected[0]).strip()
            prompt = str(question.get("prompt") or "")
            intent = (
                "question"
                if any(word in prompt for word in ("问句", "询问"))
                else "statement"
            )
            expected_terminal = punctuation_by_intent.get(intent)
            allowed_terminals = {
                unicodedata.normalize("NFKC", str(item))
                for item in rules["terminalPunctuation"]
            }
            has_terminal = bool(sentence) and sentence[-1] in allowed_terminals
            if (
                "显式句末标点" in completeness_rules
                and (not has_terminal or sentence[-1] != expected_terminal)
            ):
                self._reject("句子题缺少意图匹配的显式句末标点")
            body = sentence[:-1].strip() if has_terminal else sentence
            pattern_id = self._primary_one_sentence_pattern(body, rules)
            if pattern_id is None:
                self._reject("句子题缺少版本化一年级常用动作或状态谓语")
            expected_slots = {
                "subject_action": ("谁", "做什么"),
                "subject_identity": ("谁", "是什么"),
                "subject_description": ("什么", "怎么样"),
            }[pattern_id]
            if pattern_slots.get(pattern_id) != expected_slots:
                self._reject("句子题不符合密封的有限句型")

    @staticmethod
    def _primary_one_sentence_pattern(
        body: str,
        rules: Mapping[str, object],
    ) -> str | None:
        aspect_markers = tuple(str(item) for item in rules["aspectMarkers"])
        marker_bearing_subject_nouns = frozenset(
            str(item) for item in rules["markerBearingSubjectNouns"]
        )
        identity_complements = frozenset(
            str(item) for item in rules["identityComplements"]
        )
        state_predicates = frozenset(
            str(item) for item in rules["statePredicates"]
        )
        identity_markers = tuple(str(item) for item in rules["identityMarkers"])
        description_markers = tuple(
            str(item) for item in rules["descriptionMarkers"]
        )
        all_markers = frozenset(
            (*aspect_markers, *identity_markers, *description_markers)
        )

        def is_han_text(value: str) -> bool:
            return re.fullmatch(r"[\u3400-\u9fff]+", value) is not None

        def is_subject(value: str) -> bool:
            if not is_han_text(value) or value.endswith(("的", "地", "得")):
                return False
            if any(marker in value for marker in all_markers):
                return value in marker_bearing_subject_nouns
            return True

        predicate_productions: list[
            tuple[str, tuple[str, ...], bool]
        ] = []
        complement_productions: list[
            tuple[str, tuple[str, ...], frozenset[str]]
        ] = []
        for shape_rule in rules["subjectPredicateShapes"]:
            if not isinstance(shape_rule, Mapping):
                return None
            shape = tuple(str(item) for item in shape_rule["shape"])
            pattern_id = str(shape_rule["patternId"])
            inventory_name = str(shape_rule["predicateInventory"])
            predicates = tuple(str(item) for item in rules[inventory_name])
            if shape == ("subject", "predicate"):
                predicate_productions.append(
                    (
                        pattern_id,
                        predicates,
                        shape_rule["aspectMarkersAllowed"] is True,
                    )
                )
            elif shape == ("subject", "predicate", "complement"):
                if inventory_name == "identityMarkers":
                    complements = identity_complements
                elif inventory_name == "descriptionMarkers":
                    complements = state_predicates
                else:
                    return None
                complement_productions.append(
                    (pattern_id, predicates, complements)
                )
            else:
                return None

        for pattern_id, markers, complements in complement_productions:
            for marker in markers:
                for complement in complements:
                    suffix = marker + complement
                    if body.endswith(suffix) and len(body) > len(suffix):
                        subject = body[: -len(suffix)]
                        if is_subject(subject):
                            return pattern_id

        for pattern_id, predicates, aspect_allowed in predicate_productions:
            if not aspect_allowed:
                continue
            for predicate in predicates:
                for marker in aspect_markers:
                    suffix = predicate + marker
                    if body.endswith(suffix) and len(body) > len(suffix):
                        subject = body[: -len(suffix)]
                        if is_subject(subject):
                            return pattern_id

        for pattern_id, predicates, _aspect_allowed in predicate_productions:
            for predicate in predicates:
                if body.endswith(predicate) and len(body) > len(predicate):
                    subject = body[: -len(predicate)]
                    if is_subject(subject):
                        return pattern_id
        return None

    def _validate_primary_one_number_sense(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "math.number_sense_20_ranges.v1"
        ]["rules"]
        minimum = rules["valueRange"]["minimum"]
        maximum = rules["valueRange"]["maximum"]
        evidence: set[str] = set()

        def selected_label(question):
            labels = self._formal_answer_labels(question)
            if len(labels) != 1:
                return None
            return self._formal_semantic_text(labels[0])

        def label_is_number_with_prompt_unit(
            label,
            prompt,
            target,
            compact_suffixes=(),
        ):
            compact = re.sub(r"\s+", "", label)
            if compact == str(target):
                return True
            if compact in {
                f"{target}{suffix}" for suffix in compact_suffixes
            }:
                return True
            labeled = re.fullmatch(
                rf"{target}(号|颗|张|支|盆|辆|本|朵|个)([\u3400-\u9fff]{{0,8}})",
                compact,
            )
            if not labeled:
                return False
            classifier, noun = labeled.groups()
            return f"{target}{classifier}" in prompt and (
                not noun or noun in prompt
            )

        def recomputable_binary_pair(prompt, *, allow_equal=False):
            number_pattern = r"(?<!\d)(\d{1,2})(?!\d)"
            unit_pattern = r"(?:号|颗|张|支|盆|辆|本|朵|个)?"
            direct_pattern = re.compile(
                number_pattern
                + unit_pattern
                + r"[\u3400-\u9fff]{0,8}?\s*(?:和|与|跟|、)\s*"
                + number_pattern
                + unit_pattern
            )
            measured_pattern = re.compile(
                r"(?:^|[。！？!?；;])"
                r"[^。！？!?；;,，\d]{0,24}?(?:有|写着|标着)\s*"
                + number_pattern
                + unit_pattern
                + r"[^。！？!?；;,，\d]{0,12}?[，,]"
                r"[^。！？!?；;,，\d]{0,24}?(?:有|写着|标着)\s*"
                + number_pattern
                + unit_pattern
            )

            def sentence_for(match):
                boundaries = "。！？!?；;"
                start = max(
                    (prompt.rfind(mark, 0, match.start()) for mark in boundaries),
                    default=-1,
                )
                ends = [
                    index
                    for mark in boundaries
                    if (index := prompt.find(mark, match.end())) >= 0
                ]
                end = min(ends, default=len(prompt))
                return prompt[start + 1 : end]

            pairs: dict[tuple[int, int], tuple[int, int]] = {}
            for pattern in (direct_pattern, measured_pattern):
                for match in pattern.finditer(prompt):
                    sentence_values = re.findall(
                        r"(?<!\d)\d{1,2}(?!\d)", sentence_for(match)
                    )
                    if len(sentence_values) != 2:
                        continue
                    left = int(match.group(1))
                    right = int(match.group(2))
                    pairs.setdefault(tuple(sorted((left, right))), (left, right))
            if len(pairs) != 1:
                return None
            pair = next(iter(pairs.values()))
            if not allow_equal and pair[0] == pair[1]:
                return None
            return pair

        def selected_is_unique_pair_target(
            question,
            prompt,
            pair,
            target,
            compact_suffixes=(),
        ):
            if question.get("type") != "single_choice":
                return False
            raw_choices = question.get("choices")
            if not isinstance(raw_choices, list) or not 2 <= len(raw_choices) <= 8:
                return False
            counts = {pair[0]: 0, pair[1]: 0}
            selected_targets: list[int] = []
            answer = str(question.get("answer") or "")
            for choice in raw_choices:
                if not isinstance(choice, Mapping):
                    return False
                label = self._formal_semantic_text(choice.get("label"))
                matching = [
                    value
                    for value in pair
                    if label_is_number_with_prompt_unit(
                        label,
                        prompt,
                        value,
                        compact_suffixes,
                    )
                ]
                if len(matching) > 1:
                    return False
                if matching:
                    value = matching[0]
                    counts[value] += 1
                    if str(choice.get("id") or "") == answer:
                        selected_targets.append(value)
            return (
                all(count == 1 for count in counts.values())
                and selected_targets == [target]
            )

        def selected_is_true_relation(question, left, right):
            selected = selected_label(question)
            if selected is None:
                return False
            relation = re.fullmatch(
                r"(\d{1,2})(大于|小于|等于)(\d{1,2})",
                re.sub(r"\s+", "", selected),
            )
            if not relation:
                return False
            selected_left = int(relation.group(1))
            selected_right = int(relation.group(3))
            if {selected_left, selected_right} != {left, right}:
                return False
            operator = relation.group(2)
            return (
                (operator == "大于" and selected_left > selected_right)
                or (operator == "小于" and selected_left < selected_right)
                or (operator == "等于" and selected_left == selected_right)
            )

        def looks_like_extrema_shell(prompt):
            return re.search(
                r"(?:最大|最小|从\s*(?:少\s*到\s*多|多\s*到\s*少)|"
                r"排在\s*(?:最后面|最前面))",
                prompt,
            ) is not None

        def recomputable_extrema_target(question, prompt, listed_values):
            if (
                question.get("type") != "single_choice"
                or not 2 <= len(listed_values) <= 8
                or len(set(listed_values)) != len(listed_values)
                or any(
                    value < minimum or value > maximum
                    for value in listed_values
                )
            ):
                return None

            requested_extrema: set[str] = set()
            if "最大" in prompt:
                requested_extrema.add("maximum")
            if "最小" in prompt:
                requested_extrema.add("minimum")
            endpoint = re.search(
                r"排在\s*(最后面|最前面)"
                r"[^。！？?]{0,40}?(?:数量|数|数字)?\s*"
                r"(?:是|为)?\s*(?:多少|几)",
                prompt,
            )
            if endpoint is not None:
                if (
                    re.search(r"从\s*少\s*到\s*多", prompt) is None
                    or re.search(r"从\s*多\s*到\s*少", prompt) is not None
                ):
                    return None
                requested_extrema.add(
                    "maximum" if endpoint.group(1) == "最后面" else "minimum"
                )
            if len(requested_extrema) != 1:
                return None
            target = (
                max(listed_values)
                if "maximum" in requested_extrema
                else min(listed_values)
            )

            raw_choices = question.get("choices")
            if not isinstance(raw_choices, list) or not 2 <= len(raw_choices) <= 8:
                return None
            choice_ids: list[str] = []
            choice_values: list[int] = []
            for choice in raw_choices:
                if not isinstance(choice, Mapping):
                    return None
                choice_id = unicodedata.normalize(
                    "NFKC", str(choice.get("id") or "")
                ).strip()
                label = unicodedata.normalize(
                    "NFKC", str(choice.get("label") or "")
                ).strip()
                if not choice_id or re.fullmatch(r"(?:0|[1-9]\d?)", label) is None:
                    return None
                value = int(label)
                if value < minimum or value > maximum:
                    return None
                choice_ids.append(choice_id)
                choice_values.append(value)
            if (
                len(set(choice_ids)) != len(choice_ids)
                or len(set(choice_values)) != len(choice_values)
                or choice_values.count(target) != 1
            ):
                return None
            return target

        for question in questions:
            prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
            calculation_prompt = re.sub(r"(?<!\d)20\s*以内", "", prompt)
            values = [
                int(item)
                for item in re.findall(r"(?<!\d)\d+(?!\d)", calculation_prompt)
            ]
            if any(value < minimum or value > maximum for value in values):
                self._reject("20以内数感题超出0到20")
            expected: list[str] = []
            selection_recomputed = False
            listed_middle = re.search(
                r"(?<!\d)(\d{1,2})(?:号|颗|张|支|盆|辆|本|朵|个)?\s*[、,]\s*"
                r"(\d{1,2})(?:号|颗|张|支|盆|辆|本|朵|个)?\s*[、,]\s*"
                r"(\d{1,2})(?:号|颗|张|支|盆|辆|本|朵|个)?(?!\d)",
                prompt,
            )
            adjacent = re.search(
                r"(?<!\d)(\d{1,2})(?!\d)\s*(?:的)?\s*"
                r"(前一个|后一个)\s*(?:数)?",
                prompt,
            )
            explicit_between = re.search(
                r"(?<!\d)(\d{1,2})(?!\d)\s*(?:和|与)\s*"
                r"(\d{1,2})(?!\d)\s*(?:中间|之间)",
                prompt,
            )
            extrema_target = recomputable_extrema_target(
                question, prompt, values
            )
            if looks_like_extrema_shell(prompt):
                if extrema_target is None:
                    self._reject("20以内数感题缺少唯一可复算证据")
                expected = [str(extrema_target)]
                evidence.add("comparison")
            elif "中间位置" in prompt and listed_middle:
                left, middle, right = (
                    int(listed_middle.group(index)) for index in range(1, 4)
                )
                if (left < middle < right) or (left > middle > right):
                    expected = [str(middle)]
                    evidence.add("number_order")
            elif adjacent:
                anchor = int(adjacent.group(1))
                target = anchor + (1 if adjacent.group(2) == "后一个" else -1)
                if target < minimum or target > maximum:
                    self._reject("20以内数感相邻数题超出0到20")
                expected = [str(target)]
                evidence.add("number_order")
            elif internal_blank := re.search(
                r"(?<!\d)(\d{1,2})(?!\d)\s*[、,]\s*"
                r"(?:□|_{1,4}|\?|\(\s*\))\s*[、,]\s*"
                r"(\d{1,2})(?!\d)",
                prompt,
            ):
                left = int(internal_blank.group(1))
                right = int(internal_blank.group(2))
                if abs(left - right) == 2:
                    expected = [str(min(left, right) + 1)]
                    evidence.add("number_order")
            elif explicit_between is not None:
                left = int(explicit_between.group(1))
                right = int(explicit_between.group(2))
                if values != [left, right] or abs(left - right) != 2:
                    self._reject("20以内数感题缺少唯一可复算证据")
                expected = [str(min(left, right) + 1)]
                evidence.add("number_order")
            elif "组成" in prompt:
                number = _number_sense_composition_prompt_target(question)
                if number is None:
                    self._reject("20以内数感组成题缺少唯一可复算目标")
                expected = [f"{number // 10}个十和{number % 10}个一"]
                evidence.add("tens_and_ones_composition")
            elif "关系" in prompt:
                pair = recomputable_binary_pair(prompt, allow_equal=True)
                if pair is not None:
                    left, right = pair
                    relation = (
                        "大于"
                        if left > right
                        else "小于" if left < right else "等于"
                    )
                    expected = [f"{left}{relation}{right}"]
                    evidence.add("comparison")
            elif "更大" in prompt:
                pair = recomputable_binary_pair(prompt)
                if pair is not None:
                    selection_recomputed = selected_is_unique_pair_target(
                        question,
                        prompt,
                        pair,
                        max(pair),
                        ("更大",),
                    ) or selected_is_true_relation(question, *pair)
                evidence.add("comparison")
            elif "更多" in prompt:
                pair = recomputable_binary_pair(prompt)
                if pair is not None:
                    selection_recomputed = selected_is_unique_pair_target(
                        question,
                        prompt,
                        pair,
                        max(pair),
                        ("更多",),
                    )
                evidence.add("comparison")
            elif "更小" in prompt or "更少" in prompt:
                pair = recomputable_binary_pair(prompt)
                if pair is not None:
                    selection_recomputed = selected_is_unique_pair_target(
                        question,
                        prompt,
                        pair,
                        min(pair),
                        tuple(
                            suffix
                            for suffix in ("更小", "更少")
                            if suffix in prompt
                        ),
                    )
                    evidence.add("comparison")
            elif "比较" in prompt:
                pair = recomputable_binary_pair(prompt, allow_equal=True)
                if pair is not None:
                    selection_recomputed = selected_is_true_relation(
                        question, *pair
                    )
                evidence.add("comparison")
            if len(expected) != 1 and not selection_recomputed:
                self._reject("20以内数感题缺少唯一可复算证据")
            if expected:
                self._require_selected(question, expected)
        if not set(rules["requiredEvidence"]).issubset(evidence):
            self._reject("20以内数感题未覆盖顺序、比较和组成")
        if not any("20" in str(question.get("prompt") or "") for question in questions):
            self._reject("20以内数感题未真实使用边界20")

    def _validate_primary_one_add_sub(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "math.addition_subtraction_20_ast.v1"
        ]["rules"]
        operations: set[str] = set()
        for index, question in enumerate(questions):
            prompt = str(question.get("prompt") or "")
            raw_expression = (
                str(question.get("verificationExpression") or "")
                if question.get("type") == "numeric"
                else prompt
            )
            expressions = re.findall(
                r"(?<!\d)(\d+\s*[+-]\s*\d+)(?!\d)", raw_expression
            )
            if not expressions and question.get("type") != "numeric":
                values = [
                    int(value)
                    for value in re.findall(r"(?<!\d)(\d+)(?!\d)", prompt)
                ]
                addition_cues = (
                    "又",
                    "一共",
                    "合起来",
                    "总共",
                    "增加",
                    "来了",
                    "送来",
                    "买了",
                )
                subtraction_cues = (
                    "还剩",
                    "拿走",
                    "用掉",
                    "送给",
                    "吃掉",
                    "走了",
                    "减少",
                    "兑换",
                    "花了",
                )
                addition = any(cue in prompt for cue in addition_cues)
                subtraction = any(cue in prompt for cue in subtraction_cues)
                if len(values) == 2 and addition != subtraction:
                    operator = "+" if addition else "-"
                    expressions = [f"{values[0]}{operator}{values[1]}"]
            if len(expressions) != 1 or (
                question.get("type") == "numeric"
                and re.fullmatch(r"\s*\d+\s*[+-]\s*\d+\s*", raw_expression)
                is None
            ):
                self._reject("20以内加减法题缺少一步运算证据")
            node = self.primary_one_numeric_ast(expressions[0])
            if (
                node.get("type") not in {"add", "subtract"}
                or len(node.get("operands") or []) != 2
                or any(
                    operand.get("type") != "integer"
                    for operand in node["operands"]
                )
            ):
                self._reject("20以内加减法题必须是一层整数AST")
            left_value, right_value = (
                int(operand["value"]) for operand in node["operands"]
            )
            result = (
                left_value + right_value
                if node["type"] == "add"
                else left_value - right_value
            )
            if (
                any(value < 0 or value > 20 for value in (left_value, right_value, result))
                or (node["type"] == "subtract" and result < 0)
            ):
                self._reject("20以内加减法操作数或结果越界")
            self._require_selected(question, [str(result)])
            if index >= 3:
                operations.add(node["type"])
        if operations != set(rules["requiredIndependentOperations"]):
            self._reject("20以内加减法独立题必须覆盖加法和减法")

    def _validate_primary_one_shapes(self, questions, content, context):
        rules = context["contract"]["inventories"][
            "math.shapes_position_relations.v1"
        ]["rules"]
        composition = rules["relationComposition"]
        relation_pattern = "|".join(
            rf"{re.escape(relation)}(?:边|侧|方|面)?"
            for relation in rules["positionRelations"]
        )
        direction_aliases = {
            "左": ("左", "左边", "左面", "左侧", "左方"),
            "右": ("右", "右边", "右面", "右侧", "右方"),
            "上": ("上", "上边", "上面", "上侧", "上方"),
            "下": ("下", "下边", "下面", "下侧", "下方"),
        }
        inverse_direction = {"左": "右", "右": "左", "上": "下", "下": "上"}

        def canonical_direction(value: str) -> str | None:
            return next(
                (direction for direction in direction_aliases if value.startswith(direction)),
                None,
            )

        def direct_position_expected(
            question: Mapping[str, Any], prompt: str
        ) -> list[str]:
            query = re.search(
                r"([^,，。?？!！]{1,24}?)在([^,，。?？!！]{1,24}?)的哪一(?:边|面|侧|方)",
                prompt,
            )
            if query is None:
                return []
            target_entity = query.group(1).strip()
            anchor_entity = query.group(2).strip()
            proved: set[str] = set()
            for clause in re.split(r"[,，。?？!！]", prompt):
                fact = re.fullmatch(
                    r"\s*([^,，。?？!！]{1,24}?)在([^,，。?？!！]{1,24}?)的"
                    r"(左边|右边|左面|右面|上边|下边|上面|下面|左侧|右侧|"
                    r"上侧|下侧|左方|右方|上方|下方)\s*",
                    clause,
                )
                if fact is None:
                    continue
                fact_target = fact.group(1).strip()
                fact_anchor = fact.group(2).strip()
                direction = canonical_direction(fact.group(3))
                if direction is None:
                    continue
                if fact_target == target_entity and fact_anchor == anchor_entity:
                    proved.add(direction)
                elif fact_target == anchor_entity and fact_anchor == target_entity:
                    proved.add(inverse_direction[direction])
            if len(proved) != 1:
                return []
            aliases = direction_aliases[next(iter(proved))]
            labels = [
                str(choice.get("label") or "")
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping)
            ]
            matches = [alias for alias in aliases if alias in labels]
            return matches if len(matches) == 1 else []

        for question in questions:
            prompt = str(question.get("prompt") or "")
            if any(marker in prompt for marker in ("图中", "上图", "布局", "两层")):
                self._reject("图形位置题不得依赖未提供的图像或布局")
            relation_clauses = re.findall(
                rf"在[^,，。?？]{{0,40}}?({relation_pattern})",
                prompt,
            )
            relation_axes = {
                "horizontal" if relation.startswith(("左", "右")) else "vertical"
                for relation in relation_clauses
            }
            shared_axis_evidence = any(
                marker in prompt
                for marker in ("同一行", "同一列", "同一横排", "同一竖排")
            )
            if (
                len(relation_clauses) > 1
                and composition["sameAxisOnly"] is True
                and len(relation_axes) > 1
                and composition["crossAxisRequiresSharedRowOrColumn"] is True
                and not shared_axis_evidence
            ):
                self._reject("图形位置题不得在缺少同行同列证据时跨轴推理")
            expected: list[str] = []
            rectangle_discriminators = rules["rectangleSquareRule"][
                "requiredDiscriminators"
            ]
            if any(item in prompt for item in rectangle_discriminators) or any(
                re.search(pattern, prompt)
                for pattern in (
                    r"四条边(?:并非|不是|不都|不全)(?:一样长|相等)",
                    r"相邻(?:的)?(?:两条)?边(?:长度)?(?:不同|不一样|不相等)",
                    r"长和宽(?:不同|不一样|不相等)",
                )
            ):
                expected = [
                    item["name"]
                    for item in rules["shapes"]
                    if "对边相等" in item["properties"]
                ]
            elif (
                re.search(r"四条边(?:都)?(?:一样长|同样长|相等)", prompt)
                and re.search(r"四个(?:角[^,，。?？]{0,12}直直|直角)", prompt)
            ):
                expected = [
                    item["name"]
                    for item in rules["shapes"]
                    if "四条边相等" in item["properties"]
                ]
            elif "三个角" in prompt or "三条直边" in prompt:
                expected = [
                    item["name"]
                    for item in rules["shapes"]
                    if "三个角" in item["properties"]
                ]
            elif "没有直边" in prompt or "没有角" in prompt:
                expected = [
                    item["name"]
                    for item in rules["shapes"]
                    if "没有直边" in item["properties"]
                ]
            elif "哪一" in prompt:
                expected = direct_position_expected(question, prompt)
            if len(expected) != 1:
                self._reject("图形位置题缺少唯一版本化关系")
            self._require_selected(question, expected)
        teaching = self._course_instructional_text(content)
        if rules["rectangleSquareRule"]["squareIsRectangle"] and "正方形是特殊的长方形" not in teaching:
            self._reject("图形课程必须明确正方形是特殊的长方形")

    def _validate_primary_one_letters(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "english.letter_case_initial_sound.v1"
        ]["rules"]
        by_upper = {item["uppercase"]: item for item in rules["letters"]}
        by_lower = {item["lowercase"]: item for item in rules["letters"]}
        for question in questions:
            prompt = str(question.get("prompt") or "")
            upper = re.search(r"大写字母\s*([A-Z])", prompt)
            lower = re.search(r"小写字母\s*([a-z])", prompt)
            generic_upper = re.search(r"字母\s*([A-Z])", prompt)
            item = (
                by_upper.get(upper.group(1))
                if upper
                else by_lower.get(lower.group(1))
                if lower
                else by_upper.get(generic_upper.group(1))
                if generic_upper and "首音" in prompt
                else None
            )
            if item is None:
                self._reject("字母题缺少唯一字母权威")
            if "首音" in prompt:
                expected = item["initialSoundWords"]
            elif upper and "小写" in prompt:
                expected = [item["lowercase"]]
            elif lower and "大写" in prompt:
                expected = [item["uppercase"]]
            else:
                self._reject("字母题缺少明确的大小写或首音考核模式")
            self._require_selected(question, expected)

    def _validate_primary_one_greetings(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "english.greeting_patterns.v1"
        ]["rules"]
        phrases = {item["intent"]: item["canonical"] for item in rules["phrases"]}
        for question in questions:
            prompt = str(question.get("prompt") or "")
            if "名字是" in prompt:
                match = re.search(r"名字是\s*([A-Za-z]+)", prompt)
                expected = [f"My name is {match.group(1)}."] if match else []
            elif "早晨" in prompt:
                expected = [phrases["morning_greeting"]]
            elif "近况" in prompt:
                expected = [phrases["ask_wellbeing"]]
            elif "我很好" in prompt:
                expected = [phrases["positive_response"]]
            elif "你好" in prompt:
                expected = [phrases["hello"]]
            else:
                expected = []
            if len(expected) != 1:
                self._reject("英语问候题缺少唯一固定句型")
            self._require_selected(question, expected)

    def _validate_primary_one_numbers_colors(self, questions, _content, context):
        rules = context["contract"]["inventories"][
            "english.numbers_1_20_colors.v1"
        ]["rules"]
        numbers = {item["value"]: item["word"] for item in rules["numbers"]}
        colors = set(rules["colors"])
        evidence: set[str] = set()
        for question in questions:
            prompt = str(question.get("prompt") or "")
            match = re.search(r"数字\s*(\d+)", prompt)
            if match:
                value = int(match.group(1))
                expected = [numbers[value]] if value in numbers else []
                evidence.add("number_word_matching")
            else:
                letters = re.findall(
                    r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])", prompt
                )
                spelled = "".join(letters).casefold()
                expected = [spelled] if spelled in colors else []
                evidence.add("color_word_matching")
            if len(expected) != 1:
                self._reject("英语数词颜色题超出1到20或基础颜色表")
            self._require_selected(question, expected)
        if not set(rules["assessmentModes"]).issubset(evidence):
            self._reject("英语数词颜色课程必须同时覆盖数词和基础颜色")

    def primary_one_numeric_ast(self, expression: str) -> dict[str, Any]:
        if not isinstance(expression, str) or not expression.strip() or len(expression) > 128:
            self._reject("正式数值表达式无效")
        try:
            root = ast.parse(expression.replace("×", "*").replace("÷", "/"), mode="eval")
        except SyntaxError as exc:
            raise ApiError("invalid_learning_catalog", "正式数值表达式格式错误", 503) from exc
        return self._primary_one_ast_node(root.body)

    def _primary_one_ast_node(self, node: ast.AST) -> dict[str, Any]:
        if isinstance(node, ast.Constant) and not isinstance(node.value, bool):
            if isinstance(node.value, int):
                return {"type": "integer", "value": str(node.value)}
            if isinstance(node.value, float):
                value = Decimal(str(node.value))
                if value.is_finite():
                    return {"type": "decimal", "value": self._decimal_text(value)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            child = self._primary_one_ast_node(node.operand)
            if child["type"] not in {"integer", "decimal"}:
                self._reject("正式数值表达式一元符号只允许数值字面量")
            value = Decimal(child["value"])
            if isinstance(node.op, ast.USub):
                value = -value
            child["value"] = self._decimal_text(value)
            return child
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
        ):
            left = self._primary_one_ast_node(node.left)
            right = self._primary_one_ast_node(node.right)
            kind = {
                ast.Add: "add",
                ast.Sub: "subtract",
                ast.Mult: "multiply",
                ast.Div: "divide",
            }[type(node.op)]
            operands = [left, right]
            if kind in {"add", "multiply"}:
                operands.sort(
                    key=lambda item: json.dumps(
                        item,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            return {"type": kind, "operands": operands}
        self._reject("正式数值表达式只允许Decimal四则运算")

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        if not value.is_finite():
            raise ApiError("invalid_learning_catalog", "正式数值必须有限", 503)
        if value == 0:
            return "0"
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    def _validate_generated_primary_content(
        self, course: Mapping[str, Any], content: Mapping[str, Any]
    ) -> None:
        """Fail-closed production gates for persisted generated primary courses.

        This deliberately lives on ``LearningCatalogValidator`` so a course is
        checked again from stored content before packaging or release.  It does
        not trust an earlier model review or ``auto_validated`` database state.
        """

        authority = content.get("sourceAuthority")
        if not isinstance(authority, Mapping) or authority.get("contentOrigin") != (
            GENERATED_SOURCE_AUTHORITY["contentOrigin"]
        ):
            return
        if (
            str(course.get("gradeCode") or "") != "primary_1"
            or str(course.get("subject") or "") != "math"
        ):
            return

        questions = content.get("questions")
        flow = content.get("teachingFlow")
        if not isinstance(questions, list) or not isinstance(flow, Mapping):
            self._reject("一年级数学生成课程缺少确定性教学结构")
        by_id = {
            str(question.get("id") or ""): question
            for question in questions
            if isinstance(question, Mapping)
        }
        guided = [
            by_id.get(str(question_id))
            for question_id in flow.get("guidedQuestionIds") or []
        ]
        independent = [
            by_id.get(str(question_id))
            for question_id in flow.get("independentQuestionIds") or []
        ]
        if (
            len(guided) != 2
            or len(independent) != 2
            or any(question is None for question in [*guided, *independent])
        ):
            self._reject("一年级数学生成课程的 guided/independent 证据无效")

        self._validate_practice_answer_leaks([*guided, *independent])
        self._validate_independent_prompts(independent)

        node_code = str(course.get("nodeCode") or "")
        if node_code == "number_sense_20":
            self._validate_number_sense_20(content, guided, independent)
        elif node_code == "addition_subtraction_20":
            self._validate_addition_subtraction_20(content, guided, independent)
        elif node_code == "shapes_position":
            self._validate_shapes_position(content, independent)

    def _validate_practice_answer_leaks(
        self, questions: Sequence[Mapping[str, Any]]
    ) -> None:
        for question in questions:
            if str(question.get("type") or "") != "single_choice":
                continue
            answer = str(question.get("answer") or "")
            choices = question.get("choices") or []
            selected_label = next(
                (
                    str(choice.get("label") or "")
                    for choice in choices
                    if isinstance(choice, Mapping)
                    and str(choice.get("id") or "") == answer
                ),
                "",
            )
            canonical_label = self._compact_text(selected_label)
            canonical_hint = self._compact_text(question.get("hint"))
            leaked = False
            if canonical_label.isdecimal():
                leaked = re.search(
                    rf"(?:答案|结果|等于|得到|应选|选择)[^\d]{{0,4}}{re.escape(canonical_label)}(?!\d)",
                    canonical_hint,
                ) is not None or re.search(
                    rf"=\s*{re.escape(canonical_label)}(?!\d)",
                    canonical_hint,
                ) is not None
            elif len(canonical_label) >= 2:
                leaked = canonical_label in canonical_hint
            elif canonical_label in {"上", "下", "左", "右", "圆"}:
                suffix = "(?:边|面|方|形)?"
                leaked = re.search(
                    rf"(?:答案|在|看|向|往|选|选择|应选|是).{{0,4}}{re.escape(canonical_label)}{suffix}",
                    canonical_hint,
                ) is not None
            if leaked:
                self._reject(
                    f"练习题 {question.get('id')} 的提示直接包含正确选项文案"
                )

            if self._prompt_copies_choice_list(question.get("prompt"), choices):
                self._reject(
                    f"练习题 {question.get('id')} 的题干重复展示选项文案"
                )

    def _validate_independent_prompts(
        self, questions: Sequence[Mapping[str, Any]]
    ) -> None:
        completed_equation = re.compile(
            r"(?<!\d)\d+\s*[+\-*/]\s*\d+\s*=\s*\d+(?!\d)"
        )
        for question in questions:
            prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
            if completed_equation.search(prompt) or any(
                marker in prompt for marker in ("先算", "再算", "拆成", "凑成")
            ):
                self._reject(
                    f"独立题 {question.get('id')} 的题干包含已完成的解题步骤"
                )

    def _validate_number_sense_20(
        self,
        content: Mapping[str, Any],
        guided: Sequence[Mapping[str, Any]],
        independent: Sequence[Mapping[str, Any]],
    ) -> None:
        practice = [*guided, *independent]
        if not any(self._uses_boundary_twenty(item) for item in practice):
            self._reject("20以内数感课程必须在可作答内容中真实使用边界值 20")

        independent_kinds = {self._number_sense_kind(item) for item in independent}
        if not {"comparison", "composition"}.issubset(independent_kinds):
            self._reject("20以内数感的两道独立题必须分别覆盖比较和数的组成")
        composition_question = next(
            item
            for item in independent
            if self._number_sense_kind(item) == "composition"
        )
        self._validate_number_sense_composition_question(composition_question)
        if not any(self._is_number_sequence_question(item) for item in practice):
            self._reject("20以内数感课程缺少数的顺序证据")
        if not any(self._is_cross_tens_comparison(item) for item in practice):
            self._reject("20以内数感课程必须包含十位数量不同的大小比较")

        all_text = self._course_instructional_text(content)
        compact_text = self._compact_text(all_text)
        if re.search(
            r"十位(?:数)?(?:分别)?(?:是)?1和1.{0,8}(?:不对|不是|不一样|不同)",
            compact_text,
        ):
            self._reject("20以内数感讲解不得否定两个十几数的十位都是1")
        different_tens_examples = [
            re.compile(
                r"十位(?:数)?(?:不一样|不同).{0,30}(?<!\d)(\d{2})"
                r"(?:和|与|、)(\d{2})(?!\d)"
            ),
            re.compile(
                r"(?<!\d)(\d{2})(?:和|与|、)(\d{2})(?!\d).{0,30}"
                r"十位(?:数)?(?:不一样|不同)"
            ),
        ]
        for pattern in different_tens_examples:
            for match in pattern.finditer(compact_text):
                left, right = (int(match.group(1)), int(match.group(2)))
                if 10 <= left <= 20 and 10 <= right <= 20 and left // 10 == right // 10:
                    self._reject("20以内数感讲解不得把相同十位的两数作为十位不同示例")
        for match in re.finditer(r"(?<!\d)(\d+)\s*个十(?:\s*和\s*(\d+)\s*个一)?", all_text):
            tens = int(match.group(1))
            ones = int(match.group(2) or 0)
            if tens * 10 + ones > 20:
                self._reject("20以内数感课程包含超过 20 的数位表示")

    def _validate_addition_subtraction_20(
        self,
        content: Mapping[str, Any],
        guided: Sequence[Mapping[str, Any]],
        independent: Sequence[Mapping[str, Any]],
    ) -> None:
        for question in content.get("questions") or []:
            if not isinstance(question, Mapping):
                continue
            values = [
                int(value)
                for value in re.findall(
                    r"(?<!\d)(\d+)(?!\d)", self._question_public_text(question)
                )
            ]
            if any(value < 0 or value > 20 for value in values):
                self._reject("20以内加减法的题干、提示和选项数值必须在 0 到 20 之间")
        if any(str(question.get("type") or "") != "numeric" for question in independent):
            self._reject("20以内加减法的两道独立题必须是可 AST 复算的 numeric 题")

        operations: set[str] = set()
        for question in independent:
            operation, operands, result = self._one_step_add_sub_contract(
                str(question.get("verificationExpression") or "")
            )
            operations.add(operation)
            if any(value < 0 or value > 20 for value in (*operands, result)):
                self._reject("20以内加减法的操作数和结果必须都在 0 到 20 之间")
        if operations != {"addition", "subtraction"}:
            self._reject("20以内加减法的 q4/q5 必须分别提供加法和减法独立证据")

        if not any(self._is_one_step_story_problem(question) for question in independent):
            self._reject("20以内加减法至少需要一道独立的一步生活问题")

        teach = content.get("teachingFlow", {}).get("teach", {})
        teach_text = str(teach.get("sayText") or "") if isinstance(teach, Mapping) else ""
        if "加法" not in teach_text or "减法" not in teach_text:
            self._reject("20以内加减法必须在练习前明确教学加法和减法")
        taught_operations: set[str] = set()
        for match in re.finditer(
            r"(?<!\d)(\d+)\s*(\+|-|加(?:上)?|减(?:去)?)\s*(\d+)"
            r"\s*(?:=|等于|是)\s*(\d+)(?!\d)",
            teach_text,
        ):
            left, operator, right, declared = match.groups()
            is_addition = operator in {"+", "加", "加上"}
            expected = int(left) + int(right) if is_addition else int(left) - int(right)
            if expected != int(declared):
                self._reject("20以内加减法教学示例的算式结果错误")
            if any(value < 0 or value > 20 for value in (int(left), int(right), expected)):
                self._reject("20以内加减法教学示例的数值必须在 0 到 20 之间")
            taught_operations.add("addition" if is_addition else "subtraction")
        if taught_operations != {"addition", "subtraction"}:
            self._reject("20以内加减法教学必须各含一个可复算的加法和减法示例")

        flow = content.get("teachingFlow") or {}
        teach = flow.get("teach") if isinstance(flow, Mapping) else {}
        prepractice_parts = [
            str(teach.get("title") or "") if isinstance(teach, Mapping) else "",
            str(teach.get("sayText") or "") if isinstance(teach, Mapping) else "",
            *(
                [str(item) for item in teach.get("keyPoints") or []]
                if isinstance(teach, Mapping)
                else []
            ),
        ]
        demo_id = str(flow.get("demoQuestionId") or "") if isinstance(flow, Mapping) else ""
        demo = next(
            (
                question
                for question in content.get("questions") or []
                if isinstance(question, Mapping)
                and str(question.get("id") or "") == demo_id
            ),
            None,
        )
        if isinstance(demo, Mapping):
            prepractice_parts.append(self._question_public_text(demo))
        prepractice_text = " ".join(prepractice_parts)
        for question in [*guided, *independent]:
            signature = self._primary_add_sub_signature(question)
            if signature and self._text_reveals_add_sub_signature(
                prepractice_text, signature
            ):
                self._reject(
                    f"20以内加减法练习题 {question.get('id')} 的算式与答案已在练习前讲解中出现"
                )

    def _primary_add_sub_signature(
        self, question: Mapping[str, Any]
    ) -> tuple[str, int, int, int] | None:
        question_type = str(question.get("type") or "")
        if question_type == "numeric":
            operation, operands, result = self._one_step_add_sub_contract(
                str(question.get("verificationExpression") or "")
            )
            return operation, operands[0], operands[1], result
        if question_type != "single_choice":
            return None

        answer_id = str(question.get("answer") or "")
        answer_label = next(
            (
                str(choice.get("label") or "")
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping)
                and str(choice.get("id") or "") == answer_id
            ),
            "",
        )
        answer_match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", answer_label)
        prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
        operands = [
            int(value)
            for value in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", prompt)
        ]
        if answer_match is None or len(operands) < 2:
            return None
        left, right = operands[0], operands[1]
        answer = int(answer_match.group(1))
        compact = self._compact_text(prompt)
        explicit = re.search(
            rf"{left}(?:\+|加(?:上)?){right}|{left}(?:-|减(?:去)?){right}",
            compact,
        )
        if explicit:
            token = explicit.group(0)
            operation = "subtraction" if re.search(r"-|减", token) else "addition"
        elif re.search(r"借走|拿走|吃(?:了|掉)|还剩|剩下|送出|用掉|走了|减少", compact):
            operation = "subtraction"
        elif re.search(r"又|一共|合起来|总共|增加|放进|来了|得到|再加", compact):
            operation = "addition"
        else:
            return None
        expected = left + right if operation == "addition" else left - right
        if expected != answer:
            return None
        return operation, left, right, answer

    def _text_reveals_add_sub_signature(
        self,
        value: object,
        signature: tuple[str, int, int, int],
    ) -> bool:
        operation, left, right, answer = signature
        text = self._compact_text(value)
        pairs = [(left, right)]
        if operation == "addition" and left != right:
            pairs.append((right, left))
        operator = r"(?:\+|加(?:上)?)" if operation == "addition" else r"(?:-|减(?:去)?)"
        answer_link = r"(?:=|等于|是|得|得到|结果(?:是|为)?|一共(?:是|有)?)"
        return any(
            re.search(
                rf"(?<!\d){first}{operator}{second}.{{0,24}}{answer_link}.{{0,4}}{answer}(?!\d)",
                text,
            )
            is not None
            for first, second in pairs
        )

    def _validate_shapes_position(
        self,
        content: Mapping[str, Any],
        independent: Sequence[Mapping[str, Any]],
    ) -> None:
        flow = content.get("teachingFlow") or {}
        teach = flow.get("teach") if isinstance(flow, Mapping) else {}
        recap = flow.get("recap") if isinstance(flow, Mapping) else {}
        teach_text = " ".join(
            [
                str(teach.get("title") or "") if isinstance(teach, Mapping) else "",
                str(teach.get("sayText") or "") if isinstance(teach, Mapping) else "",
                *(
                    [str(item) for item in teach.get("keyPoints") or []]
                    if isinstance(teach, Mapping)
                    else []
                ),
            ]
        )
        recap_text = (
            str(recap.get("sayText") or "") if isinstance(recap, Mapping) else ""
        )
        required_shapes = ("圆形", "三角形", "正方形", "长方形")
        if any(shape not in teach_text for shape in required_shapes):
            self._reject("图形与位置课程必须在练习前明确教学圆形、三角形、正方形和长方形")
        if any(shape not in recap_text for shape in required_shapes):
            self._reject("图形与位置课程总结必须回顾圆形、三角形、正方形和长方形")
        compact_teach = self._compact_text(teach_text)
        if not re.search(r"长方形.{0,24}(?:四条边|四个角|对边)", compact_teach):
            self._reject("图形与位置课程必须在练习前讲清长方形的可辨认特征")

        text = self._course_instructional_text(content)
        compact = self._compact_text(text)
        false_fact_patterns = (
            r"正方形.{0,12}(?:不是|不属于|不算|不能算).{0,8}长方形",
            r"长方形.{0,24}(?:一定|必须|都是|就是|但).{0,12}两条长.{0,8}两条短",
            r"写字的手.{0,8}(?:通常|一般|就是|是).{0,4}右手",
        )
        if any(re.search(pattern, compact) for pattern in false_fact_patterns):
            self._reject("图形与位置课程包含错误或排他的图形/左右事实")

        unseen_visual_pattern = (
            r"(?:图中|图里|图片中|画面中|示意图|如下图|所示|这些图形|"
            r"上图|下图|左图|右图|上层|下层|第一排|第二排)"
        )
        for question in content.get("questions") or []:
            if not isinstance(question, Mapping):
                continue
            if re.search(
                unseen_visual_pattern,
                self._compact_text(question.get("prompt")),
            ):
                self._reject("图形与位置的公开题不得引用未随题提供的图像或布局")
            if str(question.get("type") or "") != "single_choice":
                continue
            choices = {
                str(choice.get("id") or ""): self._compact_text(choice.get("label"))
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping)
            }
            answer_label = choices.get(str(question.get("answer") or ""), "")
            if answer_label == "长方形" and "正方形" in choices.values():
                prompt = self._compact_text(question.get("prompt"))
                disambiguates_rectangle = any(
                    re.search(pattern, prompt)
                    for pattern in (
                        r"四条边(?:并非|不是|不都|不全)(?:一样长|相等)",
                        r"相邻(?:的)?(?:两条)?边(?:长度)?(?:不同|不一样|不相等)",
                        r"两条长.{0,8}两条短",
                        r"有长边.{0,8}(?:也有|和|还有)短边",
                        r"长和宽(?:不同|不一样|不相等)",
                    )
                )
                if not disambiguates_rectangle:
                    self._reject(
                        "长方形识别题同时提供正方形选项时，必须写明该具体图形四条边不全相等"
                    )

        kinds = {self._shape_position_kind(question) for question in independent}
        if kinds != {"shape", "position"}:
            self._reject("图形与位置的两道独立题必须分别覆盖识图和位置关系")

        for question in independent:
            if self._shape_position_kind(question) != "shape":
                continue
            answer = str(question.get("answer") or "")
            label = next(
                (
                    str(choice.get("label") or "")
                    for choice in question.get("choices") or []
                    if isinstance(choice, Mapping)
                    and str(choice.get("id") or "") == answer
                ),
                "",
            )
            if self._compact_text(label) in self._compact_text(question.get("prompt")):
                self._reject("独立识图题不得在题干中重复展示正确图形选项")

    def _validate_number_sense_composition_question(
        self, question: Mapping[str, Any]
    ) -> None:
        if str(question.get("type") or "") != "single_choice":
            self._reject("20以内数感的独立组成题必须是单选题")
        target = _number_sense_composition_prompt_target(
            question, require_from_composition=True
        )
        if target is None:
            self._reject(
                "20以内数感的独立组成题必须先给出目标数字，再让孩子选择几个十和几个一"
            )

        values_by_id: dict[str, int] = {}
        for choice in question.get("choices") or []:
            if not isinstance(choice, Mapping):
                self._reject("20以内数感的独立组成题选项无效")
            label = unicodedata.normalize("NFKC", str(choice.get("label") or ""))
            match = re.fullmatch(r"\s*(\d+)\s*个十\s*和\s*(\d+)\s*个一\s*", label)
            if match is None:
                self._reject("20以内数感的独立组成题选项必须是几个十和几个一")
            value = int(match.group(1)) * 10 + int(match.group(2))
            if not 0 <= value <= 20:
                self._reject("20以内数感的独立组成题选项不得超出 0 到 20")
            values_by_id[str(choice.get("id") or "")] = value
        if len(set(values_by_id.values())) != len(values_by_id):
            self._reject("20以内数感的独立组成题选项必须表示不同的数")
        if values_by_id.get(str(question.get("answer") or "")) != target:
            self._reject("20以内数感的独立组成题正确选项必须与目标数字一致")

    def _one_step_add_sub_contract(
        self, expression: str
    ) -> tuple[str, tuple[int, int], int]:
        try:
            node = ast.parse(expression, mode="eval")
        except (SyntaxError, ValueError, TypeError):
            self._reject("20以内加减法独立题的 verificationExpression 无效")
        body = node.body
        if (
            not isinstance(body, ast.BinOp)
            or not isinstance(body.op, (ast.Add, ast.Sub))
            or not isinstance(body.left, ast.Constant)
            or not isinstance(body.right, ast.Constant)
            or isinstance(body.left.value, bool)
            or isinstance(body.right.value, bool)
            or not isinstance(body.left.value, int)
            or not isinstance(body.right.value, int)
        ):
            self._reject("20以内加减法独立题必须是一步整数加法或减法")
        left = int(body.left.value)
        right = int(body.right.value)
        if isinstance(body.op, ast.Add):
            return "addition", (left, right), left + right
        return "subtraction", (left, right), left - right

    def _number_sense_kind(self, question: Mapping[str, Any]) -> str:
        text = str(question.get("prompt") or "")
        if re.search(r"组成|几个十|几个一|十位|个位", text):
            return "composition"
        if re.search(r"比较|大小|更多|更少|大于|小于|[<>]", text):
            return "comparison"
        return "other"

    def _is_number_sequence_question(self, question: Mapping[str, Any]) -> bool:
        prompt = unicodedata.normalize("NFKC", str(question.get("prompt") or ""))
        internal_blank = re.search(
            r"(?<!\d)(\d{1,2})(?!\d)\s*[、,]\s*"
            r"(?:□|_{1,4}|\?|\(\s*\))\s*[、,]\s*"
            r"(\d{1,2})(?!\d)",
            prompt,
        )
        if internal_blank is not None and abs(
            int(internal_blank.group(1)) - int(internal_blank.group(2))
        ) == 2:
            return True
        return re.search(
            r"(?<!\d)(?:[0-9]|1[0-9]|20)(?!\d)\s*(?:的)?\s*"
            r"(?:前一个|后一个)\s*(?:数)?|"
            r"顺序|往前|往后|跳过|排列|相邻|排在|"
            r"从\s*\d+\s*(?:数|跳|走).*\d+",
            prompt,
        ) is not None

    def _is_cross_tens_comparison(self, question: Mapping[str, Any]) -> bool:
        if self._number_sense_kind(question) != "comparison":
            return False
        prompt = re.sub(r"20\s*以内", "", str(question.get("prompt") or ""))
        values = [
            int(value)
            for value in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", prompt)
            if 0 <= int(value) <= 20
        ]
        distinct = list(dict.fromkeys(values))
        return len(distinct) >= 2 and distinct[0] // 10 != distinct[1] // 10

    def _shape_position_kind(self, question: Mapping[str, Any]) -> str:
        prompt = str(question.get("prompt") or "")
        choices = " ".join(
            str(choice.get("label") or "")
            for choice in question.get("choices") or []
            if isinstance(choice, Mapping)
        )
        shape_terms = r"圆形|三角形|正方形|长方形"
        position_terms = r"上面|下面|左面|右面|上边|下边|左边|右边|上下左右"
        if re.search(r"哪个.*图形|是什么图形|什么形状|辨认", prompt) and re.search(
            shape_terms, choices
        ):
            return "shape"
        if re.search(position_terms, f"{prompt} {choices}"):
            return "position"
        return "other"

    def _is_one_step_story_problem(self, question: Mapping[str, Any]) -> bool:
        prompt = str(question.get("prompt") or "")
        return re.search(
            r"有\s*\d+|又|一共|还剩|拿走|吃掉|来了|走了|买了|送给|奖励",
            prompt,
        ) is not None

    def _uses_boundary_twenty(self, question: Mapping[str, Any]) -> bool:
        texts = [str(question.get("prompt") or "")]
        if str(question.get("type") or "") == "single_choice":
            answer = str(question.get("answer") or "")
            texts.extend(
                str(choice.get("label") or "")
                for choice in question.get("choices") or []
                if isinstance(choice, Mapping)
                and str(choice.get("id") or "") == answer
            )
        return any(
            re.search(r"(?<!\d)20(?!\d|\s*以内)", text) is not None
            for text in texts
        )

    def _course_instructional_text(self, content: Mapping[str, Any]) -> str:
        flow = content.get("teachingFlow") or {}
        teach = (flow.get("teach") or {}) if isinstance(flow, Mapping) else {}
        recap = (flow.get("recap") or {}) if isinstance(flow, Mapping) else {}
        values: list[str] = [
            str(content.get("intro") or ""),
            str(teach.get("title") or "") if isinstance(teach, Mapping) else "",
            str(teach.get("sayText") or "") if isinstance(teach, Mapping) else "",
            *(
                [str(item) for item in teach.get("keyPoints") or []]
                if isinstance(teach, Mapping)
                else []
            ),
            str(recap.get("sayText") or "") if isinstance(recap, Mapping) else "",
        ]
        for question in content.get("questions") or []:
            if isinstance(question, Mapping):
                values.append(self._question_public_text(question))
        return " ".join(values)

    @staticmethod
    def _question_public_text(question: Mapping[str, Any]) -> str:
        values = [
            str(question.get("prompt") or ""),
            str(question.get("hint") or ""),
            str(question.get("explanation") or ""),
        ]
        values.extend(
            str(choice.get("label") or "")
            for choice in question.get("choices") or []
            if isinstance(choice, Mapping)
        )
        return " ".join(values)

    @staticmethod
    def _compact_text(value: object) -> str:
        return re.sub(
            r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold()
        )

    @staticmethod
    def _prompt_copies_choice_list(
        prompt_value: object,
        choices: Sequence[Mapping[str, Any]],
    ) -> bool:
        prompt = unicodedata.normalize("NFKC", str(prompt_value or "")).casefold()
        occurrences: list[tuple[int, int]] = []
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            label = unicodedata.normalize(
                "NFKC", str(choice.get("label") or "")
            ).strip().casefold()
            if len(re.sub(r"\s+", "", label)) < 2:
                continue
            start = prompt.find(label)
            if start >= 0:
                occurrences.append((start, start + len(label)))
        occurrences.sort()
        if len(occurrences) < 2:
            return False
        run_length = 1
        for previous, current in zip(occurrences, occurrences[1:]):
            between = prompt[previous[1] : current[0]]
            if re.fullmatch(r"[\s、,，;；/／|]+", between):
                run_length += 1
                if run_length >= 2:
                    return True
            else:
                run_length = 1
        return False

    def _validate_content(self, content: object, course: Mapping[str, Any]) -> None:
        course_id = str(course["id"])
        if not isinstance(content, dict):
            self._reject("课程 content 必须是对象")
        expected_values = {
            "schemaVersion": COURSE_SCHEMA_VERSION,
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "reviewPolicy": "programmatic_guarded",
        }
        for key, expected in expected_values.items():
            if content.get(key) != expected:
                self._reject(f"课程 {course_id} 的 {key} 必须是 {expected}")
        authority = content.get("sourceAuthority")
        if not isinstance(authority, Mapping):
            self._reject(f"课程 {course_id} 缺少 sourceAuthority")
        origin = str(authority.get("contentOrigin") or "")
        if origin == GENERATED_SOURCE_AUTHORITY["contentOrigin"]:
            expected_authority = dict(GENERATED_SOURCE_AUTHORITY)
        else:
            expected_authority = dict(SOURCE_AUTHORITY)
            if (
                course.get("subject") == "english"
                and str(course.get("gradeCode")) in {"primary_1", "primary_2"}
            ):
                expected_authority["basis"] = "mira_primary_english_enrichment_v1"
        for key, expected in expected_authority.items():
            if authority.get(key) != expected:
                self._reject(f"课程 {course_id} 的 sourceAuthority.{key} 无效")
        if not str(content.get("intro") or "").strip():
            self._reject(f"课程 {course_id} 缺少 intro")
        minutes = content.get("estimatedMinutes")
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 5 <= minutes <= 30:
            self._reject(f"课程 {course_id} 的 estimatedMinutes 必须在 5 到 30 之间")
        questions = content.get("questions")
        if not isinstance(questions, list) or len(questions) != 5:
            self._reject("每门内置课程必须恰好包含 5 道题")
        if origin == GENERATED_SOURCE_AUTHORITY["contentOrigin"]:
            self._validate_teaching_flow(content.get("teachingFlow"), questions, course_id)

    def _validate_teaching_flow(
        self,
        flow: object,
        questions: list[object],
        course_id: str,
    ) -> None:
        if not isinstance(flow, Mapping) or set(flow) != {
            "schemaVersion",
            "teach",
            "demoQuestionId",
            "guidedQuestionIds",
            "independentQuestionIds",
            "recap",
        }:
            self._reject(f"动态课程 {course_id} 的 teachingFlow 结构无效")
        if flow.get("schemaVersion") != TEACHING_FLOW_SCHEMA_VERSION:
            self._reject(f"动态课程 {course_id} 的 teachingFlow.schemaVersion 无效")

        teach = flow.get("teach")
        if not isinstance(teach, Mapping) or set(teach) != {
            "title",
            "sayText",
            "keyPoints",
        }:
            self._reject(f"动态课程 {course_id} 的 teachingFlow.teach 结构无效")
        self._teaching_text(
            teach.get("title"),
            maximum=160,
            label=f"动态课程 {course_id} 的 teachingFlow.teach.title",
        )
        self._teaching_text(
            teach.get("sayText"),
            maximum=1200,
            label=f"动态课程 {course_id} 的 teachingFlow.teach.sayText",
        )
        key_points = teach.get("keyPoints")
        if not isinstance(key_points, list) or not 1 <= len(key_points) <= 3:
            self._reject(
                f"动态课程 {course_id} 的 teachingFlow.teach.keyPoints 必须包含 1 到 3 项"
            )
        normalized_points = [
            unicodedata.normalize(
                "NFKC",
                self._teaching_text(
                    point,
                    maximum=200,
                    label=(
                        f"动态课程 {course_id} 的 teachingFlow.teach.keyPoints[{index}]"
                    ),
                ),
            ).casefold()
            for index, point in enumerate(key_points)
        ]
        if len(normalized_points) != len(set(normalized_points)):
            self._reject(
                f"动态课程 {course_id} 的 teachingFlow.teach.keyPoints 不得重复"
            )

        recap = flow.get("recap")
        if not isinstance(recap, Mapping) or set(recap) != {"sayText"}:
            self._reject(f"动态课程 {course_id} 的 teachingFlow.recap 结构无效")
        self._teaching_text(
            recap.get("sayText"),
            maximum=600,
            label=f"动态课程 {course_id} 的 teachingFlow.recap.sayText",
        )

        question_ids = [
            str(question.get("id") or "")
            for question in questions
            if isinstance(question, Mapping)
        ]
        guided_ids = flow.get("guidedQuestionIds")
        independent_ids = flow.get("independentQuestionIds")
        if (
            len(question_ids) != 5
            or not isinstance(flow.get("demoQuestionId"), str)
            or not isinstance(guided_ids, list)
            or len(guided_ids) != 2
            or not all(isinstance(item, str) and item.strip() for item in guided_ids)
            or not isinstance(independent_ids, list)
            or len(independent_ids) != 2
            or not all(
                isinstance(item, str) and item.strip() for item in independent_ids
            )
        ):
            self._reject(f"动态课程 {course_id} 的 teachingFlow 题目角色无效")
        references = [
            str(flow["demoQuestionId"]).strip(),
            *[item.strip() for item in guided_ids],
            *[item.strip() for item in independent_ids],
        ]
        if references != question_ids or len(set(references)) != 5:
            self._reject(
                f"动态课程 {course_id} 的 teachingFlow 必须按顺序覆盖全部 5 道题且不得重复"
            )

    def _teaching_text(self, value: object, *, maximum: int, label: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            self._reject(f"{label} 必须是 1 到 {maximum} 个字符的非空文本")
        return value.strip()

    def _validate_question(self, question: object, question_ids: set[str]) -> None:
        if not isinstance(question, dict):
            self._reject("题目必须是对象")
        for key in ("id", "type", "prompt", "skill", "hint", "explanation"):
            if not str(question.get(key) or "").strip():
                self._reject(f"题目缺少 {key}")
        question_id = str(question["id"])
        if question_id in question_ids:
            self._reject(f"题目 ID 重复: {question_id}")
        question_ids.add(question_id)

        question_type = str(question["type"])
        if question_type not in SUPPORTED_QUESTION_TYPES:
            self._reject(f"不支持的确定性题型: {question_type}")
        evaluation = question.get("evaluation", {})
        if not isinstance(evaluation, Mapping):
            self._reject(f"题目 {question_id} 的 evaluation 必须是对象")
        operations = self._validate_normalization(
            question_type, evaluation.get("normalization"), question_id
        )

        if question_type == "numeric":
            self._validate_numeric(question, evaluation, question_id)
        elif question_type == "exact_text":
            self._validate_exact_text(question, evaluation, question_id)
        elif question_type == "accepted_text":
            self._validate_accepted_text(question, evaluation, operations, question_id)
        elif question_type == "single_choice":
            self._validate_single_choice(question, evaluation, operations, question_id)
        else:
            self._validate_sequence(question, evaluation, operations, question_id)

    def _validate_numeric(
        self, question: Mapping[str, Any], evaluation: Mapping[str, Any], question_id: str
    ) -> None:
        self._reject_incompatible(question, ("choices", "acceptedAnswers"), question_id)
        if set(evaluation) - {"expected", "expectedAnswer", "normalization"}:
            self._reject(f"题目 {question_id} 的 numeric evaluation 字段无效")
        answer = self._scalar_text(question.get("answer"))
        expression = str(question.get("verificationExpression") or "").strip()
        if answer is None or not expression:
            self._reject(f"numeric 题 {question_id} 缺少答案或复算表达式")
        if expression == answer.strip():
            self._reject(f"题目 {question_id} 的复算表达式不能与标准答案相同")
        calculated = self.evaluate_expression(expression)
        try:
            expected = Decimal(answer)
        except InvalidOperation as exc:
            raise ApiError(
                "invalid_learning_catalog", f"标准答案不是有效数字: {question_id}", 503
            ) from exc
        if calculated != expected:
            self._reject(
                f"题目 {question_id} 的复算结果 {calculated} 与标准答案 {expected} 不一致"
            )
        for key in ("expected", "expectedAnswer"):
            if key in evaluation:
                try:
                    matches = Decimal(str(evaluation[key])) == expected
                except InvalidOperation:
                    matches = False
                if not matches:
                    self._reject(f"题目 {question_id} 的 evaluation.{key} 与答案不一致")

    def _validate_exact_text(
        self, question: Mapping[str, Any], evaluation: Mapping[str, Any], question_id: str
    ) -> None:
        self._reject_incompatible(
            question, ("choices", "acceptedAnswers", "verificationExpression"), question_id
        )
        if set(evaluation) - {"expected", "normalization"}:
            self._reject(f"题目 {question_id} 的 exact_text evaluation 字段无效")
        answer = self._nonempty_scalar(question.get("answer"), question_id)
        if self._nonempty_scalar(evaluation.get("expected"), question_id) != answer:
            self._reject(f"题目 {question_id} 的 evaluation.expected 与答案不一致")

    def _validate_accepted_text(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        operations: tuple[str, ...],
        question_id: str,
    ) -> None:
        self._reject_incompatible(question, ("choices", "verificationExpression"), question_id)
        if set(evaluation) - {"acceptedAnswers", "normalization"}:
            self._reject(f"题目 {question_id} 的 accepted_text evaluation 字段无效")
        answer = self._text_list(question.get("answer"), question_id, maximum=6)
        declared = self._text_list(question.get("acceptedAnswers"), question_id, maximum=6)
        evaluated = self._text_list(evaluation.get("acceptedAnswers"), question_id, maximum=6)
        if answer != declared or answer != evaluated:
            self._reject(f"题目 {question_id} 的可接受答案契约不一致")
        normalized = [self._normalize_text(item, operations) for item in answer]
        if len(normalized) != len(set(normalized)):
            self._reject(f"题目 {question_id} 的可接受答案归一化后重复")

    def _validate_single_choice(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        operations: tuple[str, ...],
        question_id: str,
    ) -> None:
        self._reject_incompatible(question, ("acceptedAnswers", "verificationExpression"), question_id)
        if set(evaluation) - {"expectedOptionId", "normalization"}:
            self._reject(f"题目 {question_id} 的 single_choice evaluation 字段无效")
        option_ids = self._validate_choices(question.get("choices"), operations, question_id)
        answer = self._nonempty_scalar(question.get("answer"), question_id)
        expected = self._nonempty_scalar(evaluation.get("expectedOptionId"), question_id)
        normalized_answer = self._normalize_text(answer, operations)
        if normalized_answer != self._normalize_text(expected, operations):
            self._reject(f"题目 {question_id} 的 expectedOptionId 与答案不一致")
        if normalized_answer not in set(option_ids):
            self._reject(f"题目 {question_id} 的答案不是有效选项")

    def _validate_sequence(
        self,
        question: Mapping[str, Any],
        evaluation: Mapping[str, Any],
        operations: tuple[str, ...],
        question_id: str,
    ) -> None:
        self._reject_incompatible(question, ("acceptedAnswers", "verificationExpression"), question_id)
        if set(evaluation) - {"expectedSequence", "normalization"}:
            self._reject(f"题目 {question_id} 的 sequence evaluation 字段无效")
        option_ids = self._validate_choices(question.get("choices"), operations, question_id)
        answer = self._text_list(question.get("answer"), question_id, maximum=8)
        expected = self._text_list(evaluation.get("expectedSequence"), question_id, maximum=8)
        normalized_answer = [self._normalize_text(item, operations) for item in answer]
        normalized_expected = [self._normalize_text(item, operations) for item in expected]
        if normalized_answer != normalized_expected:
            self._reject(f"题目 {question_id} 的 expectedSequence 与答案不一致")
        if (
            len(normalized_answer) != len(set(normalized_answer))
            or set(normalized_answer) != set(option_ids)
        ):
            self._reject(f"题目 {question_id} 的顺序答案必须恰好排列全部选项")
        if normalized_answer == option_ids:
            self._reject(f"题目 {question_id} 的选项不能预先按正确顺序展示")

    def _validate_choices(
        self, choices: object, operations: tuple[str, ...], question_id: str
    ) -> list[str]:
        if not isinstance(choices, list) or not 2 <= len(choices) <= 8:
            self._reject(f"题目 {question_id} 必须有 2 到 8 个选项")
        ids: list[str] = []
        labels: list[str] = []
        for option in choices:
            if not isinstance(option, Mapping) or set(option) != {"id", "label"}:
                self._reject(f"题目 {question_id} 的选项必须只包含 id 和 label")
            ids.append(self._nonempty_scalar(option.get("id"), question_id))
            labels.append(self._nonempty_scalar(option.get("label"), question_id))
        normalized_ids = [self._normalize_text(item, operations) for item in ids]
        normalized_labels = [self._normalize_text(item, operations) for item in labels]
        if len(normalized_ids) != len(set(normalized_ids)):
            self._reject(f"题目 {question_id} 的选项 ID 重复")
        if len(normalized_labels) != len(set(normalized_labels)):
            self._reject(f"题目 {question_id} 的选项文案重复")
        return normalized_ids

    def _validate_normalization(
        self, question_type: str, raw: object, question_id: str
    ) -> tuple[str, ...]:
        if raw is None:
            return ("trim",)
        if not isinstance(raw, list) or not raw:
            self._reject(f"题目 {question_id} 的 normalization 必须是非空数组")
        operations: list[str] = []
        for item in raw:
            operation = str(item or "").strip()
            if operation not in _NORMALIZATION_BY_TYPE[question_type]:
                self._reject(f"题目 {question_id} 使用了不安全的 normalization")
            if operation in operations:
                self._reject(f"题目 {question_id} 的 normalization 重复")
            operations.append(operation)
        return tuple(operations)

    def evaluate_expression(self, expression: str) -> Decimal:
        if len(expression) > 128:
            self._reject("复算表达式过长")
        try:
            root = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ApiError("invalid_learning_catalog", "复算表达式格式错误", 503) from exc
        try:
            return self._node(root.body)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as exc:
            raise ApiError("invalid_learning_catalog", "复算表达式无法计算", 503) from exc

    def _node(self, node: ast.AST) -> Decimal:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                self._reject("复算表达式只允许数字")
            return Decimal(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._node(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = self._node(node.left)
            right = self._node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            return left / right
        self._reject("复算表达式只允许 Decimal 四则运算与括号")

    def _required_course_fields(self, course: object) -> None:
        if not isinstance(course, dict):
            self._reject("课程必须是对象")
        for key in ("id", "version", "gradeCode", "subject", "nodeCode", "title", "objective", "status"):
            if not str(course.get(key) or "").strip():
                self._reject(f"课程缺少 {key}")
        grade_code = str(course["gradeCode"])
        if grade_code not in {f"primary_{grade}" for grade in range(1, 7)}:
            self._reject(f"课程年级不受支持: {grade_code}")
        subject = str(course["subject"])
        if subject not in SUPPORTED_PRIMARY_SUBJECTS:
            self._reject(f"当前确定性目录不允许学科: {subject}")

    def _text_list(self, value: object, question_id: str, *, maximum: int) -> list[str]:
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
            self._reject(f"题目 {question_id} 的答案必须是数组")
        if not 1 <= len(value) <= maximum:
            self._reject(f"题目 {question_id} 的答案数组长度无效")
        return [self._nonempty_scalar(item, question_id) for item in value]

    def _nonempty_scalar(self, value: object, question_id: str) -> str:
        text = self._scalar_text(value)
        if text is None or not text.strip():
            self._reject(f"题目 {question_id} 的答案必须是非空标量")
        return text

    @staticmethod
    def _scalar_text(value: object) -> str | None:
        if value is None or isinstance(value, (bool, Mapping, list, tuple, set)):
            return None
        if isinstance(value, (str, int, float, Decimal)):
            return str(value)
        return None

    @staticmethod
    def _normalize_text(value: str, operations: tuple[str, ...]) -> str:
        result = unicodedata.normalize("NFKC", value)
        for operation in operations:
            if operation == "trim":
                result = result.strip()
            elif operation == "collapse_whitespace":
                result = " ".join(result.split())
            elif operation == "remove_whitespace":
                result = "".join(char for char in result if not char.isspace())
            elif operation == "casefold":
                result = result.casefold()
            elif operation == "strip_terminal_punctuation":
                result = result.rstrip(_TERMINAL_PUNCTUATION).rstrip()
            elif operation == "strip_punctuation":
                result = "".join(char for char in result if not unicodedata.category(char).startswith("P"))
            elif operation == "remove_grouping_separators":
                result = result.replace(",", "")
        return result

    def _reject_incompatible(
        self, question: Mapping[str, Any], keys: tuple[str, ...], question_id: str
    ) -> None:
        for key in keys:
            if key in question:
                self._reject(f"题目 {question_id} 的题型不允许字段 {key}")

    @staticmethod
    def _reject(message: str):
        raise ApiError("invalid_learning_catalog", message, 503)
