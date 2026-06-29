from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from repositories.conversation_repository import ConversationRepository
from repositories.profile_repository import ProfileRepository
from services.setting_policy import setting_value
from services.wake_name_constants import DEFAULT_WAKE_NAME, FALLBACK_WAKE_NAME
from services.wake_name_validator import validate_wake_name


BOUNDARY_DELAY_POLICY = {
    "loose": {"interval_seconds": 300, "max_count": 2},
    "balanced": {"interval_seconds": 180, "max_count": 3},
    "strict": {"interval_seconds": 120, "max_count": 4},
}


class ConversationPolicyService:
    def __init__(self, database_url: str | Path):
        database = Database(database_url)
        self.profile_repository = ProfileRepository(database)
        self.conversation_repository = ConversationRepository()

    def validate_wake_name(
        self,
        value: object,
        *,
        family_names: set[str] | None = None,
        allow_fallback: bool = False,
    ) -> str:
        return validate_wake_name(
            value,
            family_names=family_names,
            allow_fallback=allow_fallback,
        )

    def get_rules(self, conn, *, family_id: str) -> dict:
        row = self.profile_repository.get_setting(conn, family_id=family_id, key="conversation")
        rules = setting_value(row, "conversation")
        child = conn.execute(
            "SELECT sleep_time, nickname, name FROM children WHERE family_id = ? ORDER BY created_at LIMIT 1",
            (family_id,),
        ).fetchone()
        sleep_time = str(child.get("sleep_time") or "").strip() if child else ""
        child_nickname = ""
        if child:
            child_nickname = str(child.get("nickname") or child.get("name") or "").strip()
        return {
            **rules,
            "sleepTime": sleep_time,
            "childNickname": child_nickname,
            "fallbackWakeName": FALLBACK_WAKE_NAME,
        }

    def build_interaction_profile(self, rules: dict) -> dict:
        wake_name = str(rules.get("wakeName") or DEFAULT_WAKE_NAME).strip() or DEFAULT_WAKE_NAME
        sleep_time = str(rules.get("sleepTime") or "").strip()
        return {
            "wakeName": wake_name,
            "fallbackWakeName": FALLBACK_WAKE_NAME,
            "voiceStyle": str(rules.get("voiceStyle") or "温柔女声，语速偏慢"),
            "boundaryLevel": str(rules.get("boundaryLevel") or "balanced"),
            "freeChatEnabled": rules.get("freeChatEnabled") is True,
            "freeChatSingleMinutes": self._positive_int(rules.get("freeChatSingleMinutes"), 8),
            "freeChatDailyMinutes": self._positive_int(rules.get("freeChatDailyMinutes"), 25),
            "homeworkModeRestricted": rules.get("homeworkModeRestricted") is not False,
            "bedtimeQuietEnabled": rules.get("bedtimeQuietEnabled") is not False,
            "bedtimeQuietAfter": sleep_time or "21:00",
            "childNickname": str(rules.get("childNickname") or "").strip() or "小朋友",
        }

    def delay_reminder_policy(self, rules: dict) -> dict:
        boundary = str(rules.get("boundaryLevel") or "balanced")
        return BOUNDARY_DELAY_POLICY.get(boundary, BOUNDARY_DELAY_POLICY["balanced"])

    def evaluate_chat_turn(
        self,
        conn,
        *,
        family_id: str,
        rules: dict | None = None,
        now_ms: int | None = None,
    ) -> dict:
        rules = rules or self.get_rules(conn, family_id=family_id)
        profile = self.build_interaction_profile(rules)
        now = now_ms if now_ms is not None else self._now_ms()
        date_key = self._date_key(now)
        daily_used = self.conversation_repository.daily_free_chat_seconds(
            conn,
            family_id=family_id,
            date_key=date_key,
        )
        daily_limit = profile["freeChatDailyMinutes"] * 60
        single_limit = profile["freeChatSingleMinutes"] * 60
        active = self.conversation_repository.active_session(
            conn,
            family_id=family_id,
            session_type="free_chat",
        )
        active_seconds = 0
        if active is not None:
            active_seconds = max(0, (now - int(active["started_at"])) // 1000)

        bedtime_quiet = profile["bedtimeQuietEnabled"] and self._is_past_bedtime(
            profile.get("bedtimeQuietAfter") or "",
            now,
        )
        focus_restricted = profile["homeworkModeRestricted"] and self._has_active_task(conn, family_id)

        free_chat_allowed = profile["freeChatEnabled"] and not bedtime_quiet
        if free_chat_allowed and daily_limit > 0 and daily_used >= daily_limit:
            free_chat_allowed = False
        if free_chat_allowed and active is not None and single_limit > 0 and active_seconds >= single_limit:
            free_chat_allowed = False

        reason = "allowed"
        if not profile["freeChatEnabled"]:
            reason = "free_chat_disabled"
        elif bedtime_quiet:
            reason = "bedtime_quiet"
        elif daily_limit > 0 and daily_used >= daily_limit:
            reason = "daily_limit_reached"
        elif active is not None and single_limit > 0 and active_seconds >= single_limit:
            reason = "single_session_limit_reached"
        elif focus_restricted:
            reason = "focus_restricted"

        return {
            "allowed": free_chat_allowed and not focus_restricted,
            "freeChatAllowed": free_chat_allowed,
            "focusRestricted": focus_restricted,
            "bedtimeQuiet": bedtime_quiet,
            "reason": reason,
            "profile": profile,
            "usage": {
                "dailyFreeChatSeconds": daily_used,
                "dailyFreeChatLimitSeconds": daily_limit,
                "activeSessionSeconds": active_seconds,
                "singleSessionLimitSeconds": single_limit,
            },
        }

    def evaluate_speak_context(
        self,
        conn,
        *,
        family_id: str,
        task_id: str | None = None,
    ) -> dict:
        if task_id:
            return {"allowed": True, "reason": "task_speak"}
        evaluation = self.evaluate_chat_turn(conn, family_id=family_id)
        if evaluation["allowed"]:
            return {"allowed": True, "reason": "policy_allowed"}
        if evaluation["focusRestricted"]:
            return {
                "allowed": False,
                "reason": "focus_restricted",
                "message": "专注时间只保留当前事情相关问答和温和提示。",
            }
        if evaluation["bedtimeQuiet"]:
            return {
                "allowed": False,
                "reason": "bedtime_quiet",
                "message": "睡前不主动开启长时间自由聊天。",
            }
        if not evaluation["profile"]["freeChatEnabled"]:
            return {
                "allowed": False,
                "reason": "free_chat_disabled",
                "message": "自由聊天已关闭。",
            }
        return {
            "allowed": False,
            "reason": evaluation["reason"],
            "message": "聊天时间已达上限。",
        }

    def start_free_chat_session(
        self,
        conn,
        *,
        family_id: str,
        device_id: str,
        session_id: str,
        started_at: int | None = None,
    ) -> None:
        started = started_at if started_at is not None else self._now_ms()
        self.conversation_repository.create_session(
            conn,
            session_id=session_id,
            family_id=family_id,
            device_id=device_id,
            session_type="free_chat",
            started_at=started,
            date_key=self._date_key(started),
        )

    def end_active_free_chat_session(
        self,
        conn,
        *,
        family_id: str,
        ended_at: int | None = None,
    ) -> int:
        active = self.conversation_repository.active_session(
            conn,
            family_id=family_id,
            session_type="free_chat",
        )
        if active is None:
            return 0
        ended = ended_at if ended_at is not None else self._now_ms()
        duration = max(0, (ended - int(active["started_at"])) // 1000)
        self.conversation_repository.end_session(
            conn,
            session_id=active["id"],
            ended_at=ended,
            duration_seconds=duration,
        )
        if duration > 0:
            self.conversation_repository.add_daily_free_chat_seconds(
                conn,
                family_id=family_id,
                date_key=str(active["date_key"]),
                seconds=duration,
            )
        return duration

    def policy_payload(self, conn, *, family_id: str, device_id: str | None = None) -> dict:
        rules = self.get_rules(conn, family_id=family_id)
        profile = self.build_interaction_profile(rules)
        evaluation = self.evaluate_chat_turn(conn, family_id=family_id, rules=rules)
        return {
            "deviceId": device_id or "",
            "interactionProfile": profile,
            "flags": {
                "freeChatAllowed": evaluation["freeChatAllowed"],
                "focusRestricted": evaluation["focusRestricted"],
                "bedtimeQuiet": evaluation["bedtimeQuiet"],
            },
            "usage": evaluation["usage"],
            "reason": evaluation["reason"],
        }

    def _has_active_task(self, conn, family_id: str) -> bool:
        row = conn.execute(
            """
            SELECT id
            FROM tasks
            WHERE family_id = ?
              AND status IN ('in_progress', 'started', 'active')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (family_id,),
        ).fetchone()
        return row is not None

    def _is_past_bedtime(self, sleep_time: str, now_ms: int) -> bool:
        value = str(sleep_time or "").strip()
        if not value or ":" not in value:
            return False
        try:
            hour, minute = value.split(":", 1)
            bedtime = datetime.now().replace(
                hour=int(hour),
                minute=int(minute),
                second=0,
                microsecond=0,
            )
        except ValueError:
            return False
        now_local = datetime.fromtimestamp(now_ms / 1000)
        return now_local >= bedtime

    def _positive_int(self, value, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(0, parsed)

    def _now_ms(self) -> int:
        from core.security import now_ms

        return now_ms()

    def _date_key(self, now_ms: int) -> str:
        return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
