from __future__ import annotations

import re

from core.errors import ApiError
from services.wake_name_constants import DEFAULT_WAKE_NAME

_BLOCKED_WAKE_FRAGMENTS = {"笨蛋", "傻瓜", "坏蛋", "讨厌", "滚"}


def validate_wake_name(
    value: object,
    *,
    family_names: set[str] | None = None,
    allow_fallback: bool = False,
) -> str:
    raw = str(value or "").strip()
    if not raw and allow_fallback:
        return DEFAULT_WAKE_NAME
    if not raw:
        raise ApiError("missing_wakeName", "请输入摄像头名字")
    if family_names and raw in family_names:
        raise ApiError("confusing_wakeName", "这个名字容易和家人称呼混淆，请换一个")
    if any(word in raw for word in _BLOCKED_WAKE_FRAGMENTS):
        raise ApiError("blocked_wakeName", "这个名字不太适合孩子使用，请换一个")
    chinese_only = re.fullmatch(r"[\u4e00-\u9fff]{2,6}", raw)
    short_name = re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", raw)
    if not chinese_only and not short_name:
        raise ApiError("invalid_wakeName", "名字建议 2 到 6 个中文，或简短好读的名称")
    return raw


def clean_profile_value(value: object, fallback: str = "", max_len: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    return text[:max_len]
