from __future__ import annotations

import re
from typing import Mapping


HOMEWORK_ACTIVITIES = {"写作业", "看书", "写作业/看书"}
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
MEAL_RE = re.compile(r"(吃饭|用餐|餐桌|餐椅|饭菜|餐具|碗|筷子|勺子|餐盘|早餐|午餐|晚餐|拿食物|进食|吃东西)")
MEAL_TOYS_ON_TABLE_RE = re.compile(r"(餐桌|餐椅|桌面|桌上)[^，。,.]{0,16}(玩具|积木|娃娃|车模)")
MEAL_STANDING_RE = re.compile(r"(站在.*餐椅|餐椅.*站|爬.*椅|跪.*餐椅|没坐|未坐|没坐好|没坐稳|站在.*椅)")
MEAL_DISTRACTION_RE = re.compile(r"(玩玩具|玩耍|玩食物|分心|离开餐桌|走开|跑开)")
TOY_PLAY_RE = re.compile(r"(玩玩具|玩积木|搭积木|摆弄玩具|操作玩具|playing with toys)")
PLAY_UNSAFE_CLIMB_RE = re.compile(r"(爬[^，。,.]{0,8}(家具|茶几|沙发|椅子|桌)|爬上|攀爬)")
PLAY_UNSAFE_ELEVATED_RE = re.compile(r"(站在[^，。,.]{0,8}(家具|茶几|沙发|椅子|桌)|站[^，。,.]{0,4}上玩)")
PLAY_UNSAFE_THROW_RE = re.compile(r"(扔[^，。,.]{0,8}(玩具|积木)|投掷|抛掷)")
PLAY_UNSAFE_MOUTH_RE = re.compile(r"(咬[^，。,.]{0,8}(玩具|积木)|放[^，。,.]{0,4}嘴里|小零件[^，。,.]{0,8}口)")
ABSENT_BEHAVIOR_RE = re.compile(r"(孩子|宝宝|小朋友)[^，。,.]{0,12}(看|玩|吃|坐|站|跑|走|拿)")


def observation_text(obs: Mapping[str, object]) -> str:
    return "".join(
        str(obs.get(key) or "")
        for key in ("activity", "raw_activity", "posture_status", "description", "child_message")
    )


def is_homework_like(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is False:
        return False
    if obs.get("activity") in NON_HOMEWORK_ACTIVITIES or obs.get("raw_activity") in NON_HOMEWORK_ACTIVITIES:
        return False
    if obs.get("activity") in HOMEWORK_ACTIVITIES or obs.get("raw_activity") in HOMEWORK_ACTIVITIES:
        return True
    return bool(HOMEWORK_TEXT_RE.search(observation_text(obs)))


def is_meal_scene(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is False:
        return False
    if bool(obs.get("is_meal_scene")):
        return True
    activity = str(obs.get("activity") or obs.get("raw_activity") or "")
    if activity == "吃饭":
        return True
    return bool(MEAL_RE.search(observation_text(obs)))


def has_toys_on_table(obs: Mapping[str, object]) -> bool:
    if obs.get("toys_on_table") is True:
        return True
    if not is_meal_scene(obs):
        return False
    return bool(MEAL_TOYS_ON_TABLE_RE.search(observation_text(obs)))


def meal_standing_detected(obs: Mapping[str, object]) -> bool:
    if obs.get("meal_standing") is True:
        return True
    if not is_meal_scene(obs):
        return False
    return bool(MEAL_STANDING_RE.search(observation_text(obs)))


def is_toy_play_scene(obs: Mapping[str, object]) -> bool:
    if obs.get("has_person") is not True:
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
    if description and (ABSENT_BEHAVIOR_RE.search(description) or "看屏幕" in description):
        obs["description"] = _room_scene_message(obs)
    obs["activity"] = "离开"
    obs["raw_activity"] = "离开"
    obs["child_message"] = ""
    obs["bad_posture"] = False
    obs["posture_status"] = "unknown"
    return obs


def _room_scene_message(obs: Mapping[str, object]) -> str:
    text = observation_text(obs)
    if "餐桌" in text or "餐椅" in text:
        return "餐桌区域暂时没有看到孩子。"
    if "玩具" in text:
        return "房间里有玩具，但暂时没有看到孩子。"
    return "刚才的画面里没有看到孩子。"


def normalize_activity(obs: dict) -> dict:
    if is_meal_scene(obs):
        obs["activity"] = "吃饭"
        obs["raw_activity"] = "吃饭"
        obs["is_meal_scene"] = True
        if has_toys_on_table(obs):
            obs["meal_etiquette_issue"] = "toys_on_table"
        elif meal_standing_detected(obs):
            obs["meal_etiquette_issue"] = "standing"
        elif MEAL_DISTRACTION_RE.search(observation_text(obs)):
            obs["meal_etiquette_issue"] = "distracted"
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
    obs = enrich_observation_risks(dict(obs))
    obs = normalize_activity(obs)
    obs = enrich_play_safety(obs)
    obs = sanitize_absent_observation(obs)
    return obs
