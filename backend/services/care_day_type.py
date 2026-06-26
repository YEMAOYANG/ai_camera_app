from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from models.care import DAY_TYPE_SCHOOL_DAY, DAY_TYPE_WEEKEND, DAY_TYPES

DEFAULT_TIMEZONE = "Asia/Shanghai"


def effective_day_type(
    observed_at: int,
    *,
    timezone: str = DEFAULT_TIMEZONE,
    explicit_day_type: str | None = None,
) -> str:
    if explicit_day_type in DAY_TYPES:
        return str(explicit_day_type)
    zone = _zone(timezone)
    dt = datetime.fromtimestamp(observed_at / 1000, tz=zone)
    return DAY_TYPE_WEEKEND if dt.weekday() >= 5 else DAY_TYPE_SCHOOL_DAY


def _zone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)
