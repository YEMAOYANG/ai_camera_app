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
    obs["posture_risk_reason"] = reason
    obs["homework_like"] = is_homework_like(obs)
    if obs["homework_like"] and reason:
        obs["bad_posture"] = True
        if obs.get("posture_status") in {"", "unknown", None} or reason in POSTURE_RISK_STATUSES:
            obs["posture_status"] = reason
    return obs
