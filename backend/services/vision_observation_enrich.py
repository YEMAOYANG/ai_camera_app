from __future__ import annotations

import re
from typing import Mapping


HOMEWORK_ACTIVITIES = {"写作业", "看书", "写作业/看书"}
REMINDABLE_SCREEN_DEVICES = frozenset({"phone", "tablet"})
HOMEWORK_TEXT_RE = re.compile(
    r"(写作业|看书|书写|纸张|纸面|纸上|书本|练习册|作业本|笔记本(?!电脑)|纸笔|铅笔|钢笔|文具|写字)"
)
POSTURE_RISK_STATUSES = {"low_head", "leaning_too_close", "slouching"}
TOO_CLOSE_RE = re.compile(
    r"(离[^，。,.]{0,8}(书本|纸张|纸面|桌面)[^，。,.]{0,8}(太近|过近|很近)|距离[^，。,.]{0,8}(太近|过近|很近)|脸[^，。,.]{0,6}(贴近|靠近)|头部[^，。,.]{0,8}(过近|太近)|贴近[^，。,.]{0,6}(纸|书|桌))"
)
LOW_HEAD_RE = re.compile(r"(低头|头低|埋头|头部低|头离[^，。,.]{0,8}近)")
SLOUCHING_RE = re.compile(r"(趴|趴伏|趴桌|身体前倾|前倾明显|弯腰)")
NON_HOMEWORK_ACTIVITIES = {"玩手机", "看电视", "吃饭", "玩玩具", "收玩具", "走动", "离开", "发呆"}
MEAL_ACTION_RE = re.compile(
    r"(吃饭|用餐|进食|吃东西|拿食物|正在吃|咀嚼|咬着|喂|用(?:筷|勺))"
)
MEAL_CONTEXT_RE = re.compile(r"(餐桌|餐椅|饭菜|餐具|早餐|午餐|晚餐|碗|筷子|勺子|餐盘)")
TOY_CLEANUP_ACTIVITY_RE = re.compile(r"(收玩具|整理玩具|收拾玩具|收纳玩具|玩具归位|放回|归位)")
TOY_PLAY_ACTION_RE = re.compile(r"(玩玩具|玩积木|搭积木|摆弄玩具|操作玩具|玩具车|积木|playing with toys)")
MEAL_TOYS_ON_TABLE_RE = re.compile(r"(餐桌|餐椅|桌面|桌上)[^，。,.]{0,16}(玩具|积木|娃娃|车模)")
MEAL_STANDING_RE = re.compile(r"(站在.*餐椅|餐椅.*站|爬.*椅|跪.*餐椅|没坐|未坐|没坐好|没坐稳|站在.*椅)")
MEAL_DISTRACTION_RE = re.compile(r"(玩玩具|玩耍|玩食物|分心|离开餐桌|走开|跑开)")
TOY_PLAY_RE = re.compile(r"(玩玩具|玩积木|搭积木|摆弄玩具|操作玩具|playing with toys)")
PLAY_UNSAFE_CLIMB_RE = re.compile(r"(爬[^，。,.]{0,8}(家具|茶几|沙发|椅子|桌)|爬上|攀爬)")
PLAY_UNSAFE_ELEVATED_RE = re.compile(r"(站在[^，。,.]{0,8}(家具|茶几|沙发|椅子|桌)|站[^，。,.]{0,4}上玩)")
PLAY_UNSAFE_THROW_RE = re.compile(r"(扔[^，。,.]{0,8}(玩具|积木)|投掷|抛掷)")
PLAY_UNSAFE_MOUTH_RE = re.compile(r"(咬[^，。,.]{0,8}(玩具|积木)|放[^，。,.]{0,4}嘴里|小零件[^，。,.]{0,8}口)")
ABSENT_BEHAVIOR_RE = re.compile(r"(孩子|宝宝|小朋友)[^，。,.]{0,12}(看|玩|吃|坐|站|跑|走|拿)")
ABSENT_FORBIDDEN_RE = re.compile(
    r"(看屏幕|看电视|玩手机|注视.{0,6}屏|用眼距离|弹跳|蹦床上|跳蹦床|孩子在|宝宝在|小朋友在)"
)
SCREEN_ACTIVITY_RE = re.compile(
    r"(看屏幕|看电视|玩手机|看手机|注视.{0,8}(屏|电视|手机|平板)|玩.{0,4}手机)"
)
SCREEN_EVIDENCE_RE = re.compile(
    r"(手持|拿着|握着|低头看|注视|看着|面向|盯着).{0,12}(手机|平板|屏幕|电视|iPad|pad)"
    r"|(手机|平板|屏幕|电视).{0,12}(亮|播放|有画面|开着|屏幕亮)"
    r"|屏幕.{0,8}(有内容|有画面|亮着)"
)
TV_OFF_RE = re.compile(r"(电视关|黑屏|没开|未开|无画面|没有画面|屏幕黑|关机|熄屏)")
TRAMPOLINE_JUMP_RE = re.compile(r"(蹦床.{0,8}(跳|弹跳|蹦)|跳.{0,6}蹦床|在蹦床上|弹跳玩耍|蹦跳)")
TRAMPOLINE_CONTEXT_RE = re.compile(r"蹦床")
TRAMPOLINE_NEAR_RE = re.compile(r"(蹦床旁|蹦床边|蹦床附近|旁边.{0,6}蹦床|蹦床.{0,6}旁边|蹦床.{0,6}附近)")
SEDENTARY_RE = re.compile(r"(坐|坐着|安静|静止|待着|注视|看向|望着|面向|看向前|凝视|屏息)")
ACTIVE_TOY_INTERACTION_RE = re.compile(
    r"(玩|拿.{0,8}玩具|摆弄|操作|搭|推.{0,4}车|滑.{0,4}车|扔|咬).{0,8}(玩具|积木|车|娃娃|毛绒)"
)
FORWARD_GAZE_RE = re.compile(r"(看向前|面向前方|注视前方|看着前方|朝前|看向同一方向|视线向前)")


def observation_text(obs: Mapping[str, object]) -> str:
    return "".join(
        str(obs.get(key) or "")
        for key in ("activity", "raw_activity", "posture_status", "description", "child_message")
    )


def behavior_text(obs: Mapping[str, object]) -> str:
    return "".join(
        str(obs.get(key) or "")
        for key in ("raw_activity", "description", "child_message")
    )


def is_homework_like(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is False:
        return False
    if obs.get("activity") in NON_HOMEWORK_ACTIVITIES or obs.get("raw_activity") in NON_HOMEWORK_ACTIVITIES:
        return False
    if obs.get("activity") in HOMEWORK_ACTIVITIES or obs.get("raw_activity") in HOMEWORK_ACTIVITIES:
        return True
    return bool(HOMEWORK_TEXT_RE.search(observation_text(obs)))


def is_cleanup_activity(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is not True:
        return False
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    if activity == "收玩具":
        return True
    return bool(TOY_CLEANUP_ACTIVITY_RE.search(behavior_text(obs)))


def _raw_meal_standing(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is False:
        return False
    if obs.get("meal_standing") is True:
        return True
    return bool(MEAL_STANDING_RE.search(behavior_text(obs)))


def has_meal_action_evidence(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is False:
        return False
    if is_cleanup_activity(obs):
        return False
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    text = behavior_text(obs)
    description = str(obs.get("description") or "")
    if TOY_PLAY_ACTION_RE.search(text) and TOY_PLAY_ACTION_RE.search(description):
        if not MEAL_ACTION_RE.search(description):
            return False
    if TOY_PLAY_ACTION_RE.search(text) and not MEAL_ACTION_RE.search(text):
        return False
    if MEAL_ACTION_RE.search(text):
        return True
    if activity == "吃饭" and not TOY_PLAY_ACTION_RE.search(text):
        return True
    if _raw_meal_standing(obs) and (
        MEAL_ACTION_RE.search(text)
        or MEAL_CONTEXT_RE.search(text)
        or activity == "吃饭"
    ):
        return True
    return False


def is_meal_scene(obs: Mapping[str, object]) -> bool:
    return has_meal_action_evidence(obs)


def has_toys_on_table(obs: Mapping[str, object]) -> bool:
    if obs.get("toys_on_table") is True:
        return True
    if not is_meal_scene(obs):
        return False
    return bool(MEAL_TOYS_ON_TABLE_RE.search(observation_text(obs)))


def meal_standing_detected(obs: Mapping[str, object]) -> bool:
    if not has_meal_action_evidence(obs):
        return False
    return _raw_meal_standing(obs)


def is_toy_play_scene(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is not True:
        return False
    if is_cleanup_activity(obs):
        return False
    if is_meal_scene(obs):
        return False
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    if activity == "玩玩具":
        return True
    return bool(TOY_PLAY_RE.search(observation_text(obs)))


def play_safety_reason(obs: Mapping[str, object]) -> str:
    if not is_toy_play_scene(obs):
        return ""
    explicit = str(obs.get("play_safety_reason") or "").strip()
    if explicit and explicit not in {"none", "unknown"}:
        return explicit
    text = observation_text(obs)
    if PLAY_UNSAFE_CLIMB_RE.search(text):
        return "climbing_furniture"
    if PLAY_UNSAFE_ELEVATED_RE.search(text):
        return "standing_on_furniture"
    if PLAY_UNSAFE_THROW_RE.search(text):
        return "throwing"
    if PLAY_UNSAFE_MOUTH_RE.search(text):
        return "small_parts_mouth"
    status = str(obs.get("play_safety_status") or "").strip()
    if status in {"unsafe", "risk"}:
        return "climbing_furniture"
    return ""


def sanitize_absent_observation(obs: dict) -> dict:
    if obs.get("has_person") is not False:
        return obs
    description = str(obs.get("description") or "").strip()
    if description and (
        ABSENT_BEHAVIOR_RE.search(description)
        or ABSENT_FORBIDDEN_RE.search(description)
        or "看屏幕" in description
    ):
        obs["description"] = _room_scene_message(obs)
    obs["activity"] = "离开"
    obs["raw_activity"] = "离开"
    obs["child_message"] = ""
    obs["bad_posture"] = False
    obs["posture_status"] = "unknown"
    return obs


def _contains_child_behavior(text: str) -> bool:
    if not text:
        return False
    return bool(
        ABSENT_BEHAVIOR_RE.search(text)
        or ABSENT_FORBIDDEN_RE.search(text)
        or SCREEN_ACTIVITY_RE.search(text)
    )


def _has_screen_evidence(text: str) -> bool:
    return bool(SCREEN_EVIDENCE_RE.search(text))


def _normalize_trampoline_description(obs: dict) -> dict:
    if obs.get("has_person") is not True:
        return obs
    description = str(obs.get("description") or "").strip()
    if not description or not TRAMPOLINE_CONTEXT_RE.search(description):
        return obs
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    if activity == "玩玩具" and TRAMPOLINE_JUMP_RE.search(description):
        description = TRAMPOLINE_JUMP_RE.sub("在蹦床旁玩玩具", description)
        description = re.sub(r"在蹦床上[^，。,.]{0,12}", "在蹦床旁", description)
        obs["description"] = description
        obs["child_message"] = ""
        return obs
    if TRAMPOLINE_JUMP_RE.search(description):
        return obs
    if TRAMPOLINE_NEAR_RE.search(description) or TRAMPOLINE_CONTEXT_RE.search(description):
        description = TRAMPOLINE_JUMP_RE.sub("在蹦床旁玩玩具", description)
        description = re.sub(r"在蹦床上[^，。,.]{0,12}", "在蹦床旁", description)
        obs["description"] = description
        child_message = str(obs.get("child_message") or "").strip()
        if child_message and TRAMPOLINE_JUMP_RE.search(child_message):
            obs["child_message"] = ""
    return obs


def _normalize_false_toy_play(obs: dict) -> dict:
    if obs.get("has_person") is not True:
        return obs
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    if activity != "玩玩具":
        return obs
    text = behavior_text(obs)
    if (
        obs.get("toys_scattered")
        or obs.get("toys_visible")
        or re.search(r"玩具", text)
    ):
        return obs
    if ACTIVE_TOY_INTERACTION_RE.search(text) or TOY_PLAY_ACTION_RE.search(text):
        return obs
    if not SEDENTARY_RE.search(text) and not FORWARD_GAZE_RE.search(text):
        return obs
    if re.search(r"(手机|平板|iPad|pad)", text, re.I):
        obs["activity"] = "玩手机"
        obs["raw_activity"] = "玩手机"
    elif re.search(r"(电视|大屏|屏幕|荧幕)", text) or FORWARD_GAZE_RE.search(text):
        obs["activity"] = "看电视"
        obs["raw_activity"] = "看电视"
    else:
        obs["activity"] = "发呆"
        obs["raw_activity"] = "安静休息"
    obs["child_message"] = ""
    confidence = _float_or_zero(obs.get("confidence"))
    if confidence > 0.72:
        obs["confidence"] = 0.72
    return obs


def _normalize_screen_activity(obs: dict) -> dict:
    if obs.get("has_person") is False:
        activity = str(obs.get("activity") or obs.get("raw_activity") or "")
        if activity in {"看电视", "玩手机", "看屏幕"} or SCREEN_ACTIVITY_RE.search(observation_text(obs)):
            obs["activity"] = "离开"
            obs["raw_activity"] = "离开"
            obs["child_message"] = ""
        return obs
    text = observation_text(obs)
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    claims_screen = activity in {"看电视", "玩手机", "看屏幕"} or SCREEN_ACTIVITY_RE.search(text)
    if not claims_screen:
        return obs
    tv_off = TV_OFF_RE.search(text)
    has_evidence = _has_screen_evidence(text)
    if tv_off and not has_evidence:
        obs["activity"] = "发呆"
        obs["raw_activity"] = "发呆"
        obs["child_message"] = ""
        confidence = _float_or_zero(obs.get("confidence"))
        if confidence > 0.55:
            obs["confidence"] = 0.55
        return obs
    if not has_evidence:
        if activity == "看电视" and (SEDENTARY_RE.search(text) or FORWARD_GAZE_RE.search(text)):
            return obs
        obs["activity"] = "其他"
        obs["raw_activity"] = "其他"
        obs["child_message"] = ""
        confidence = _float_or_zero(obs.get("confidence"))
        if confidence > 0.6:
            obs["confidence"] = 0.6
    return obs


def _normalize_toy_meal_conflict(obs: dict) -> dict:
    if obs.get("has_person") is not True:
        return obs
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    text = behavior_text(obs)
    if activity == "吃饭" and TOY_PLAY_ACTION_RE.search(text) and not has_meal_action_evidence(obs):
        obs["activity"] = "玩玩具"
        obs["raw_activity"] = "玩玩具"
        obs["is_meal_scene"] = False
        obs.pop("meal_etiquette_issue", None)
        confidence = _float_or_zero(obs.get("confidence"))
        if confidence > 0.72:
            obs["confidence"] = 0.72
        return obs
    if activity in {"玩玩具", "收玩具"} and MEAL_ACTION_RE.search(text) and not TOY_PLAY_ACTION_RE.search(text):
        if has_meal_action_evidence(obs):
            return obs
    if activity == "玩玩具" and re.search(r"(用餐|吃饭|进食)", text) and TOY_PLAY_ACTION_RE.search(text):
        obs["activity"] = "玩玩具"
        obs["raw_activity"] = obs.get("raw_activity") or "玩玩具"
        obs["is_meal_scene"] = False
        obs.pop("meal_etiquette_issue", None)
    return obs


def enforce_observation_consistency(obs: dict) -> dict:
    obs = sanitize_absent_observation(obs)
    obs = _normalize_false_toy_play(obs)
    obs = _normalize_screen_activity(obs)
    obs = _normalize_trampoline_description(obs)
    obs = _normalize_toy_meal_conflict(obs)
    if obs.get("has_person") is False:
        description = str(obs.get("description") or "").strip()
        if _contains_child_behavior(description):
            obs["description"] = _room_scene_message(obs)
        obs["activity"] = "离开"
        obs["raw_activity"] = "离开"
        obs["child_message"] = ""
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    if activity == "离开" and _contains_child_behavior(str(obs.get("description") or "")):
        obs["description"] = _room_scene_message(obs)
    return obs


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _room_scene_message(obs: Mapping[str, object]) -> str:
    text = observation_text(obs)
    if "餐桌" in text or "餐椅" in text:
        return "餐桌区域暂时没有看到孩子。"
    if "玩具" in text:
        return "房间里有玩具，但暂时没有看到孩子。"
    return "刚才的画面里没有看到孩子。"


def normalize_activity(obs: dict) -> dict:
    if is_cleanup_activity(obs):
        obs["activity"] = "收玩具"
        raw = str(obs.get("raw_activity") or "").strip()
        obs["raw_activity"] = raw if raw else "收玩具"
        obs.pop("is_meal_scene", None)
        obs.pop("meal_etiquette_issue", None)
        return obs
    if is_meal_scene(obs):
        obs["activity"] = "吃饭"
        obs["raw_activity"] = "吃饭"
        obs["is_meal_scene"] = True
        if has_toys_on_table(obs):
            obs["meal_etiquette_issue"] = "toys_on_table"
        elif meal_standing_detected(obs):
            obs["meal_etiquette_issue"] = "standing"
        elif structured_screen_active(obs):
            obs["meal_etiquette_issue"] = "distracted"
        elif MEAL_DISTRACTION_RE.search(observation_text(obs)):
            obs["meal_etiquette_issue"] = "distracted"
    elif str(obs.get("activity") or "") in {"玩玩具", "收玩具"}:
        obs.pop("is_meal_scene", None)
        obs.pop("meal_etiquette_issue", None)
    return obs


def enrich_play_safety(obs: dict) -> dict:
    if not is_toy_play_scene(obs):
        obs["play_safety_status"] = "unknown"
        obs["play_safety_reason"] = "none"
        return obs
    reason = play_safety_reason(obs)
    if reason:
        obs["play_safety_status"] = "unsafe"
        obs["play_safety_reason"] = reason
    else:
        obs["play_safety_status"] = "safe"
        obs["play_safety_reason"] = "none"
    return obs


def posture_risk_reason(obs: Mapping[str, object]) -> str:
    if obs.get("has_person") is False:
        return ""
    status = str(obs.get("posture_status") or "unknown")
    text = observation_text(obs)
    if status in POSTURE_RISK_STATUSES:
        return status
    if obs.get("bad_posture"):
        return "bad_posture"
    if TOO_CLOSE_RE.search(text):
        return "leaning_too_close"
    if LOW_HEAD_RE.search(text):
        return "low_head"
    if SLOUCHING_RE.search(text):
        return "slouching"
    return ""


def has_structured_screen_fields(obs: Mapping[str, object]) -> bool:
    return isinstance(obs.get("screen_device_visible"), bool) and isinstance(
        obs.get("screen_use_active"), bool
    )


def structured_screen_active(obs: Mapping[str, object]) -> bool:
    return (
        has_structured_screen_fields(obs)
        and bool(obs.get("screen_device_visible"))
        and bool(obs.get("screen_use_active"))
    )


def is_remindable_screen_device(obs: Mapping[str, object]) -> bool:
    device_type = str(obs.get("screen_device_type") or "").strip().lower()
    return device_type in REMINDABLE_SCREEN_DEVICES


def screen_use_sustained(obs: Mapping[str, object]) -> bool:
    hint = str(obs.get("screen_use_duration_hint") or "").strip().lower()
    return hint == "sustained"


def enrich_screen_observation(obs: dict) -> dict:
    visible = obs.get("screen_device_visible")
    active = obs.get("screen_use_active")
    if visible is None and active is None:
        return obs
    obs["screen_device_type"] = str(obs.get("screen_device_type") or "unknown").strip().lower() or "unknown"
    obs["screen_distance_risk"] = str(obs.get("screen_distance_risk") or "unknown").strip().lower() or "unknown"
    obs["screen_use_context"] = str(obs.get("screen_use_context") or "unknown").strip().lower() or "unknown"
    obs["screen_use_duration_hint"] = (
        str(obs.get("screen_use_duration_hint") or "unknown").strip().lower() or "unknown"
    )
    return obs


def clear_posture_for_structured_screen(obs: dict) -> dict:
    if not structured_screen_active(obs) or not is_remindable_screen_device(obs):
        return obs
    obs["homework_like"] = False
    obs["posture_risk_reason"] = ""
    obs["bad_posture"] = False
    obs["posture_status"] = "ok"
    if str(obs.get("child_message") or "").strip():
        obs["child_message"] = ""
    return obs


def enrich_observation_risks(obs: dict) -> dict:
    reason = posture_risk_reason(obs)
    obs["homework_like"] = is_homework_like(obs)
    if obs["homework_like"] and reason:
        obs["posture_risk_reason"] = reason
        obs["bad_posture"] = True
        if obs.get("posture_status") in {"", "unknown", None} or reason in POSTURE_RISK_STATUSES:
            obs["posture_status"] = reason
        return obs

    obs["posture_risk_reason"] = ""
    obs["bad_posture"] = False
    if str(obs.get("posture_status") or "").strip() not in {"", "ok", "unknown"}:
        obs["posture_status"] = "ok"
    if not obs["homework_like"] and str(obs.get("child_message") or "").strip():
        obs["child_message"] = ""
    return obs


def enrich_observation(obs: dict) -> dict:
    obs = enrich_screen_observation(dict(obs))
    obs = enrich_observation_risks(obs)
    obs = clear_posture_for_structured_screen(obs)
    obs = normalize_activity(obs)
    obs = enrich_play_safety(obs)
    obs = enforce_observation_consistency(obs)
    return obs
