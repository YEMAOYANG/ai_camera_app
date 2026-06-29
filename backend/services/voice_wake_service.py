from __future__ import annotations

import re
import unicodedata

from services.wake_name_constants import FALLBACK_WAKE_NAME, WAKE_CONFIRMATION_GREETINGS
from services.wake_name_validator import clean_profile_value

PINYIN_FALLBACK = {
    "暖": "nuan",
    "小": "xiao",
    "伴": "ban",
    "办": "ban",
    "版": "ban",
    "半": "ban",
    "猪": "zhu",
    "朱": "zhu",
    "主": "zhu",
    "豆": "dou",
}


def normalize_wake_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    chars = []
    for char in value:
        category = unicodedata.category(char)
        if category.startswith(("P", "S", "Z", "C")):
            continue
        chars.append(char)
    return "".join(chars)


def text_to_pinyin_syllables(text: str) -> list[str]:
    normalized = normalize_wake_text(text)
    if not normalized:
        return []
    try:
        from pypinyin import Style, lazy_pinyin

        return [
            re.sub(r"[^a-z0-9]", "", item.lower())
            for item in lazy_pinyin(normalized, style=Style.NORMAL, errors="default")
            if item
        ]
    except Exception:
        return [
            char if char.isascii() and char.isalnum() else PINYIN_FALLBACK.get(char, char)
            for char in normalized
        ]


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if char_a == char_b else 1),
                )
            )
        previous = current
    return previous[-1]


def best_window_distance(text: str, target: str) -> tuple[int, str]:
    if not text or not target or len(text) < len(target):
        return len(target), ""
    best = (len(target), "")
    size = len(target)
    for index in range(0, len(text) - size + 1):
        window = text[index : index + size]
        distance = edit_distance(window, target)
        if distance < best[0]:
            best = (distance, window)
    return best


def contains_sequence(items: list[str], target: list[str]) -> bool:
    if not target or len(items) < len(target):
        return False
    size = len(target)
    return any(items[index : index + size] == target for index in range(0, len(items) - size + 1))


def wake_candidate_match(heard: str, wake_name: str, *, is_fallback: bool = False) -> dict:
    normalized_text = normalize_wake_text(heard)
    normalized_wake = normalize_wake_text(wake_name)
    base = {
        "matched": False,
        "name": wake_name,
        "normalized_wake": normalized_wake,
        "method": "",
        "reason": "not_checked",
        "score": 0.0,
        "is_fallback": is_fallback,
    }
    if len(normalized_wake) < 2:
        return {**base, "reason": "wake_name_too_short"}
    if not normalized_text:
        return {**base, "reason": "empty_text"}
    if normalized_wake in normalized_text:
        return {
            **base,
            "matched": True,
            "method": "text_exact",
            "reason": "wake_text_in_transcript",
            "score": 1.0,
        }
    text_pinyin = text_to_pinyin_syllables(normalized_text)
    wake_pinyin = text_to_pinyin_syllables(normalized_wake)
    if len(wake_pinyin) >= 2 and len(text_pinyin) >= len(wake_pinyin):
        size = len(wake_pinyin)
        for index in range(0, len(text_pinyin) - size + 1):
            if text_pinyin[index : index + size] == wake_pinyin:
                return {
                    **base,
                    "matched": True,
                    "method": "pinyin_exact",
                    "reason": "wake_pinyin_in_transcript",
                    "score": 0.94,
                }
    if len(normalized_wake) >= 3:
        distance, window = best_window_distance(normalized_text, normalized_wake)
        threshold = 1 if len(normalized_wake) <= 3 else 2
        if distance <= threshold:
            score = 1.0 - (distance / max(len(normalized_wake), 1))
            return {
                **base,
                "matched": True,
                "method": "text_fuzzy",
                "reason": "wake_text_close_to_transcript",
                "score": round(score, 3),
                "distance": distance,
                "matched_text": window,
            }
    return {**base, "reason": "no_wake_in_text"}


def wake_confirmation_match(heard: str, wake_name: str) -> dict:
    normalized_text = normalize_wake_text(heard)
    normalized_wake = normalize_wake_text(wake_name)
    base = {"confirmed": False, "method": "", "reason": "wake_phrase_not_confirmed"}
    if len(normalized_wake) < 2 or not normalized_text:
        return base
    if f"{normalized_wake}{normalized_wake}" in normalized_text:
        return {"confirmed": True, "method": "text_repeat", "reason": "wake_name_repeated"}
    for greeting in WAKE_CONFIRMATION_GREETINGS:
        if f"{normalized_wake}{normalize_wake_text(greeting)}" in normalized_text:
            return {
                "confirmed": True,
                "method": "text_greeting",
                "reason": "wake_name_with_greeting",
            }
    text_pinyin = text_to_pinyin_syllables(normalized_text)
    wake_pinyin = text_to_pinyin_syllables(normalized_wake)
    if len(wake_pinyin) >= 2:
        if contains_sequence(text_pinyin, wake_pinyin + wake_pinyin):
            return {"confirmed": True, "method": "pinyin_repeat", "reason": "wake_pinyin_repeated"}
        for greeting in WAKE_CONFIRMATION_GREETINGS:
            greeting_pinyin = text_to_pinyin_syllables(greeting)
            if greeting_pinyin and contains_sequence(text_pinyin, wake_pinyin + greeting_pinyin):
                return {
                    "confirmed": True,
                    "method": "pinyin_greeting",
                    "reason": "wake_pinyin_with_greeting",
                }
    return base


def match_wake_names(
    heard: str,
    wake_name: str = "",
    fallback_wake_name: str = FALLBACK_WAKE_NAME,
    *,
    require_confirmation: bool = False,
) -> dict:
    names = []
    for name, is_fallback in ((wake_name, False), (fallback_wake_name, True)):
        clean = clean_profile_value(name, "", 12)
        if clean and clean not in [item[0] for item in names]:
            names.append((clean, is_fallback))
    candidates = [
        wake_candidate_match(heard, name, is_fallback=is_fallback)
        for name, is_fallback in names
    ]
    raw_matched = next((item for item in candidates if item.get("matched")), None)
    matched = raw_matched
    if raw_matched and require_confirmation:
        confirmation = wake_confirmation_match(heard, raw_matched["name"])
        updated = {**raw_matched, "confirmation": confirmation}
        if not confirmation["confirmed"]:
            updated.update(
                {
                    "matched": False,
                    "raw_matched": True,
                    "raw_method": raw_matched.get("method", ""),
                    "method": "",
                    "reason": "wake_phrase_not_confirmed",
                    "score": 0.0,
                }
            )
        candidates = [
            updated
            if item.get("name") == raw_matched.get("name")
            and item.get("is_fallback") == raw_matched.get("is_fallback")
            else item
            for item in candidates
        ]
        matched = updated if updated.get("matched") else None
    result = {
        "matched": bool(matched),
        "heard": heard,
        "normalized_text": normalize_wake_text(heard),
        "confirmation_required": require_confirmation,
        "fallbackWakeName": fallback_wake_name,
        "candidates": candidates,
    }
    if matched:
        result.update(matched)
    elif raw_matched and require_confirmation:
        result.update(
            next((item for item in candidates if item.get("raw_matched")), None) or raw_matched
        )
    else:
        result.update(
            {
                "name": names[0][0] if names else "",
                "normalized_wake": normalize_wake_text(names[0][0]) if names else "",
                "method": "",
                "reason": candidates[0]["reason"] if candidates else "no_wake_configured",
                "score": 0.0,
                "is_fallback": False,
            }
        )
    return result


def wake_initial_prompt(wake_name: str, fallback_wake_name: str) -> str:
    names = [clean_profile_value(name, "", 12) for name in (wake_name, fallback_wake_name)]
    names = list(dict.fromkeys([name for name in names if name]))
    if not names:
        return ""
    phrases = []
    for name in names:
        phrases.extend([f"{name}{name}", f"{name}你好"])
    return "儿童在对摄像头说中文唤醒词。可能出现的短句：" + "、".join(phrases) + "。"


def clean_camera_command_text(text: str, profile: dict | None = None) -> str:
    profile = profile or {}
    value = str(text or "").strip()
    for name in (profile.get("wakeName"), profile.get("fallbackWakeName")):
        name = str(name or "").strip()
        if name:
            value = value.replace(name, "")
    prefix_re = re.compile(
        r"^\s*(你好呀|你好啊|你好|在吗|嗨|哈喽|hello|hi|请帮我|帮我|麻烦你)[，。！？,.!?\s]*",
        re.I,
    )
    while True:
        cleaned = prefix_re.sub("", value)
        if cleaned == value:
            break
        value = cleaned
    return value.strip(" ，。！？,.!?")


def wake_ack_text(wake_name: str) -> str:
    name = clean_profile_value(wake_name, FALLBACK_WAKE_NAME, 12)
    return f"{name}在听，你说吧。"
