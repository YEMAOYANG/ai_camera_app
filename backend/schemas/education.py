from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from core.errors import ApiError


KINDERGARTEN_GROWTH = "kindergarten_growth"
PRIMARY_LEARNING = "primary_learning"


@dataclass(frozen=True)
class GradeDefinition:
    code: str
    label: str
    education_stage_code: str
    education_stage_label: str
    content_mode: str
    kindergarten_template_grade: str | None = None

    @property
    def age_stage_label(self) -> str:
        return f"{self.education_stage_label} {self.label}"


GRADE_DEFINITIONS = (
    GradeDefinition(
        "kindergarten_small",
        "小班",
        "kindergarten",
        "幼儿园",
        KINDERGARTEN_GROWTH,
        "small",
    ),
    GradeDefinition(
        "kindergarten_middle",
        "中班",
        "kindergarten",
        "幼儿园",
        KINDERGARTEN_GROWTH,
        "middle",
    ),
    GradeDefinition(
        "kindergarten_big",
        "大班",
        "kindergarten",
        "幼儿园",
        KINDERGARTEN_GROWTH,
        "big",
    ),
    GradeDefinition("primary_1", "一年级", "primary", "小学", PRIMARY_LEARNING),
    GradeDefinition("primary_2", "二年级", "primary", "小学", PRIMARY_LEARNING),
    GradeDefinition("primary_3", "三年级", "primary", "小学", PRIMARY_LEARNING),
    GradeDefinition("primary_4", "四年级", "primary", "小学", PRIMARY_LEARNING),
    GradeDefinition("primary_5", "五年级", "primary", "小学", PRIMARY_LEARNING),
    GradeDefinition("primary_6", "六年级", "primary", "小学", PRIMARY_LEARNING),
)

GRADE_BY_CODE = {item.code: item for item in GRADE_DEFINITIONS}

_GRADE_ALIASES = {
    "small": "kindergarten_small",
    "小班": "kindergarten_small",
    "新小班": "kindergarten_small",
    "幼儿园小班": "kindergarten_small",
    "幼儿园 小班": "kindergarten_small",
    "middle": "kindergarten_middle",
    "中班": "kindergarten_middle",
    "新中班": "kindergarten_middle",
    "幼儿园中班": "kindergarten_middle",
    "幼儿园 中班": "kindergarten_middle",
    "big": "kindergarten_big",
    "大班": "kindergarten_big",
    "新大班": "kindergarten_big",
    "幼儿园大班": "kindergarten_big",
    "幼儿园 大班": "kindergarten_big",
    "一年级": "primary_1",
    "新一年级": "primary_1",
    "小学一年级": "primary_1",
    "小学 一年级": "primary_1",
    "二年级": "primary_2",
    "新二年级": "primary_2",
    "小学二年级": "primary_2",
    "小学 二年级": "primary_2",
    "三年级": "primary_3",
    "新三年级": "primary_3",
    "小学三年级": "primary_3",
    "小学 三年级": "primary_3",
    "四年级": "primary_4",
    "新四年级": "primary_4",
    "小学四年级": "primary_4",
    "小学 四年级": "primary_4",
    "五年级": "primary_5",
    "新五年级": "primary_5",
    "小学五年级": "primary_5",
    "小学 五年级": "primary_5",
    "六年级": "primary_6",
    "新六年级": "primary_6",
    "小学六年级": "primary_6",
    "小学 六年级": "primary_6",
}
_GRADE_ALIASES.update({code: code for code in GRADE_BY_CODE})

_EDUCATION_STAGE_ALIASES = {
    "kindergarten": "kindergarten",
    "preschool": "kindergarten",
    "幼儿园": "kindergarten",
    "学前": "kindergarten",
    "primary": "primary",
    "小学": "primary",
}


def grade_definition_for_code(value: object) -> GradeDefinition:
    code = _text(value)
    definition = GRADE_BY_CODE.get(code)
    if definition is None:
        raise ApiError("invalid_grade_code", "请选择有效的年级")
    return definition


def grade_definition_from_legacy(value: object, *, strict: bool = True) -> GradeDefinition | None:
    normalized = _GRADE_ALIASES.get(_text(value))
    if normalized:
        return GRADE_BY_CODE[normalized]
    if strict:
        raise ApiError("invalid_grade", "请选择有效的年级")
    return None


def education_stage_code(value: object, *, strict: bool = True) -> str | None:
    normalized = _EDUCATION_STAGE_ALIASES.get(_text(value))
    if normalized:
        return normalized
    if strict:
        raise ApiError("invalid_education_stage", "请选择幼儿园或小学年级")
    return None


def education_stage_label(value: object) -> str:
    code = education_stage_code(value)
    return "幼儿园" if code == "kindergarten" else "小学"


def grade_definition_from_row(row: Mapping | None) -> GradeDefinition | None:
    if row is None:
        return None
    stored_code = _text(row.get("grade_code"))
    if stored_code:
        definition = GRADE_BY_CODE.get(stored_code)
        if definition is not None:
            return definition
    definition = grade_definition_from_legacy(row.get("grade"), strict=False)
    if definition is not None:
        return definition
    return grade_definition_from_legacy(row.get("age_stage"), strict=False)


def resolve_grade_definition(
    *,
    grade_code: object = None,
    legacy_grade: object = None,
    education_stage: object = None,
    age_stage: object = None,
) -> GradeDefinition | None:
    definitions: list[GradeDefinition] = []
    if _text(grade_code):
        definitions.append(grade_definition_for_code(grade_code))
    if _text(legacy_grade):
        definitions.append(grade_definition_from_legacy(legacy_grade))

    age_definition = None
    if _text(age_stage):
        age_definition = grade_definition_from_legacy(age_stage, strict=False)
        if age_definition is not None:
            definitions.append(age_definition)

    resolved = definitions[0] if definitions else None
    if resolved is not None and any(item.code != resolved.code for item in definitions[1:]):
        raise ApiError("grade_conflict", "年级信息不一致，请重新选择")

    stages: list[str] = []
    if _text(education_stage):
        stages.append(education_stage_code(education_stage))
    if _text(age_stage) and age_definition is None:
        age_stage_code = education_stage_code(age_stage, strict=False)
        if age_stage_code:
            stages.append(age_stage_code)
    if resolved is not None and any(stage != resolved.education_stage_code for stage in stages):
        raise ApiError("grade_stage_conflict", "年级与学段不一致，请重新选择")
    if len(set(stages)) > 1:
        raise ApiError("grade_stage_conflict", "年级与学段不一致，请重新选择")
    return resolved


def validate_school_year_start_year(
    value: object,
    *,
    required: bool,
    fallback_to_current_year: bool = False,
) -> int | None:
    text = _text(value)
    if not text:
        if required:
            raise ApiError("missing_school_year_start_year", "请选择对应的开学学年")
        return datetime.now().year if fallback_to_current_year else None
    try:
        year = int(text)
    except (TypeError, ValueError) as exc:
        raise ApiError("invalid_school_year_start_year", "开学学年不正确") from exc
    current_year = datetime.now().year
    if year != current_year:
        raise ApiError(
            "invalid_school_year_start_year",
            f"请选择 {current_year} 年 9 月开学后的年级",
        )
    return year


def grade_storage_fields(
    definition: GradeDefinition,
    *,
    school_year_start_year: int,
    confirmed_at: int,
) -> dict:
    return {
        "grade_code": definition.code,
        "grade": definition.label,
        "education_stage": definition.education_stage_label,
        "age_stage": definition.age_stage_label,
        "grade_school_year_start": school_year_start_year,
        "grade_confirmed_at": confirmed_at,
    }


def child_education_payload(row: Mapping | None) -> dict:
    if row is None:
        return {
            "ageStage": "",
            "educationStage": "",
            "educationStageCode": "",
            "educationStageLabel": "",
            "grade": "",
            "gradeCode": "",
            "gradeLabel": "",
            "contentMode": "",
            "schoolYearStartYear": None,
            "gradeConfirmedAt": None,
            "gradeSelectionRequired": True,
        }

    definition = grade_definition_from_row(row)

    school_year = _optional_int(row.get("grade_school_year_start"))
    confirmed_at = _optional_int(row.get("grade_confirmed_at"))
    grade_label = definition.label if definition else _text(row.get("grade"))
    stage_label = (
        definition.education_stage_label
        if definition
        else _text(row.get("education_stage") or row.get("age_stage"))
    )
    return {
        "ageStage": _text(row.get("age_stage")),
        "educationStage": stage_label,
        "educationStageCode": definition.education_stage_code if definition else "",
        "educationStageLabel": stage_label,
        "grade": grade_label,
        "gradeCode": definition.code if definition else "",
        "gradeLabel": grade_label,
        "contentMode": definition.content_mode if definition else "",
        "schoolYearStartYear": school_year,
        "gradeConfirmedAt": confirmed_at,
        "gradeSelectionRequired": not bool(definition and school_year and confirmed_at),
    }


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str:
    return str(value or "").strip()
