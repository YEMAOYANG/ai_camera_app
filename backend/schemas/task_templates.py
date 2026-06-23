from __future__ import annotations

import json

from core.database import DatabaseRow
from core.errors import ApiError


GRADE_OPTIONS = [
    {"value": "small", "label": "小班", "ageGroup": "kindergarten_small"},
    {"value": "middle", "label": "中班", "ageGroup": "kindergarten_middle"},
    {"value": "big", "label": "大班", "ageGroup": "kindergarten_big"},
]

DAY_TYPE_OPTIONS = [
    {"value": "school_day", "label": "上学日"},
    {"value": "weekend", "label": "周末"},
]

TEMPLATE_TAG_OPTIONS = [
    {"value": "all", "label": "全部"},
    {"value": "school_day", "label": "上学日"},
    {"value": "weekend", "label": "周末"},
    {"value": "morning", "label": "晨间"},
    {"value": "after_school", "label": "放学后"},
    {"value": "bedtime", "label": "睡前"},
    {"value": "outdoor", "label": "户外"},
    {"value": "cleanup", "label": "收纳"},
    {"value": "reading", "label": "阅读"},
    {"value": "meal", "label": "用餐"},
    {"value": "emotion", "label": "表达"},
    {"value": "self_care", "label": "自理"},
    {"value": "rules", "label": "规则"},
    {"value": "helper", "label": "小帮手"},
]

GRADE_ALIASES = {
    "small": "small",
    "kindergarten_small": "small",
    "小班": "small",
    "middle": "middle",
    "kindergarten_middle": "middle",
    "中班": "middle",
    "big": "big",
    "kindergarten_big": "big",
    "大班": "big",
}

DAY_TYPE_ALIASES = {
    "school_day": "school_day",
    "weekday": "school_day",
    "上学日": "school_day",
    "weekend": "weekend",
    "周末": "weekend",
}


def normalize_template_grade(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = GRADE_ALIASES.get(str(value).strip())
    if not normalized:
        raise ApiError("invalid_grade", "班级筛选不支持")
    return normalized


def normalize_template_day_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = DAY_TYPE_ALIASES.get(str(value).strip())
    if not normalized:
        raise ApiError("invalid_day_type", "日期类型不支持")
    return normalized


def normalize_template_tag(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized == "all":
        return None
    allowed = {item["value"] for item in TEMPLATE_TAG_OPTIONS}
    if normalized not in allowed:
        raise ApiError("invalid_tag", "模板标签不支持")
    return normalized


def template_catalog_payload(
    templates: list[tuple[DatabaseRow, list[DatabaseRow]]],
    *,
    recommended_grade: str | None,
) -> dict:
    return {
        "ok": True,
        "templates": [template_payload(row, items) for row, items in templates],
        "tags": TEMPLATE_TAG_OPTIONS,
        "grades": GRADE_OPTIONS,
        "dayTypes": DAY_TYPE_OPTIONS,
        "recommendedGrade": recommended_grade or "small",
        "recommendedGradeLabel": _label_for(GRADE_OPTIONS, recommended_grade or "small"),
    }


def template_payload(row: DatabaseRow, items: list[DatabaseRow]) -> dict:
    grade = str(row["grade"])
    day_type = str(row["day_type"])
    tags = _parse_json_list(row.get("tags_json"))
    return {
        "id": row["id"],
        "templateKey": row["template_key"],
        "title": row["title"],
        "subtitle": row["subtitle"],
        "grade": grade,
        "gradeLabel": _label_for(GRADE_OPTIONS, grade),
        "ageGroups": [row["age_group"]],
        "scheduleType": row["schedule_type"],
        "dayType": day_type,
        "dayTypeLabel": _label_for(DAY_TYPE_OPTIONS, day_type),
        "tags": tags,
        "tagLabels": [_label_for(TEMPLATE_TAG_OPTIONS, tag) for tag in tags],
        "rows": [template_item_payload(item) for item in items],
    }


def template_item_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "startTime": row["start_time"],
        "endTime": row["end_time"],
        "taskType": row["task_type"],
        "title": row["title"],
        "rewardPoints": int(row["reward_points"] or 0),
        "requiresParentConfirmation": bool(row["requires_parent_confirmation"]),
    }


def _label_for(options: list[dict], value: str) -> str:
    for item in options:
        if item["value"] == value:
            return item["label"]
    return value


def _parse_json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]
