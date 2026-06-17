from __future__ import annotations

from dataclasses import dataclass
import json
import re


FORBIDDEN_REMINDER_PATTERNS = (
    "我是 AI",
    "我是AI",
    "系统检测到",
    "你不乖",
    "不乖",
    "扣分",
    "妈妈会生气",
    "爸爸会生气",
    "再不",
    "惩罚",
    "威胁",
    "羞羞",
)

UNSPEAKABLE_PATTERNS = (
    "http://",
    "https://",
    "```",
    "{",
    "}",
    "[",
    "]",
    "1.",
    "2.",
    "- ",
    "解释",
    "原因",
    "系统",
)


@dataclass(frozen=True)
class ReminderTextValidation:
    ok: bool
    text: str = ""
    tone: str = "warm"
    scenario: str = ""
    safety: str = ""
    reason: str = ""


class ReminderTextValidator:
    def __init__(
        self,
        *,
        max_length: int = 40,
        forbidden_patterns: tuple[str, ...] = FORBIDDEN_REMINDER_PATTERNS,
    ):
        self.max_length = max(8, int(max_length))
        self.forbidden_patterns = forbidden_patterns

    def validate_json_text(
        self,
        raw_text: str | None,
        *,
        scenario: str,
        last_text: str | None = None,
    ) -> ReminderTextValidation:
        value = str(raw_text or "").strip()
        if not value:
            return ReminderTextValidation(False, reason="empty")
        parsed = self._parse_json(value)
        if parsed is None:
            return ReminderTextValidation(False, reason="invalid_json")
        text = self._clean_text(parsed.get("text"))
        if not text:
            return ReminderTextValidation(False, reason="missing_text")
        if len(text) > self.max_length:
            return ReminderTextValidation(False, reason="too_long")
        if self._normalized(text) == self._normalized(last_text):
            return ReminderTextValidation(False, reason="repeated")
        bad = self._first_forbidden(text)
        if bad:
            return ReminderTextValidation(False, reason=f"forbidden:{bad}")
        if self._is_unspeakable(text):
            return ReminderTextValidation(False, reason="unspeakable")
        safety = str(parsed.get("safety") or "").strip().lower()
        if safety and safety != "ok":
            return ReminderTextValidation(False, reason="unsafe")
        parsed_scenario = str(parsed.get("scenario") or scenario).strip()
        if parsed_scenario and parsed_scenario != scenario:
            return ReminderTextValidation(False, reason="scenario_mismatch")
        tone = str(parsed.get("tone") or "warm").strip() or "warm"
        return ReminderTextValidation(
            ok=True,
            text=text,
            tone=tone[:32],
            scenario=scenario,
            safety=safety or "ok",
        )

    def validate_plain_text(
        self,
        text: str | None,
        *,
        last_text: str | None = None,
    ) -> ReminderTextValidation:
        value = self._clean_text(text)
        if not value:
            return ReminderTextValidation(False, reason="empty")
        if len(value) > self.max_length:
            return ReminderTextValidation(False, reason="too_long")
        if self._normalized(value) == self._normalized(last_text):
            return ReminderTextValidation(False, reason="repeated")
        bad = self._first_forbidden(value)
        if bad:
            return ReminderTextValidation(False, reason=f"forbidden:{bad}")
        if self._is_unspeakable(value):
            return ReminderTextValidation(False, reason="unspeakable")
        return ReminderTextValidation(True, text=value, tone="warm", safety="ok")

    def _parse_json(self, value: str) -> dict | None:
        trimmed = re.sub(r"^```(?:json)?|```$", "", value.strip(), flags=re.IGNORECASE).strip()
        try:
            parsed = json.loads(trimmed)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _clean_text(self, value: object) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^[\"'“”‘’\s]+|[\"'“”‘’\s]+$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _first_forbidden(self, text: str) -> str:
        return next((item for item in self.forbidden_patterns if item in text), "")

    def _is_unspeakable(self, text: str) -> bool:
        if "\n" in text or "\r" in text or "\t" in text:
            return True
        if any(item in text for item in UNSPEAKABLE_PATTERNS):
            return True
        return text.count("，") + text.count("。") + text.count("；") > 3

    def _normalized(self, text: str | None) -> str:
        return re.sub(r"\s+", "", str(text or "").strip())
