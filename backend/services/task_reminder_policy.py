from __future__ import annotations

from typing import Mapping


REMINDER_PHASES = {
    "prepare",
    "start",
    "follow_up",
    "delay",
    "wrap_up",
    "finish",
}


def normalize_task_reminder_phase(value: str | None, *, default: str = "follow_up") -> str:
    phase = str(value or default).strip().lower()
    return phase if phase in REMINDER_PHASES else default


def build_task_reminder(
    task: Mapping,
    *,
    phase: str,
    child: Mapping | None = None,
    count: int = 0,
) -> dict:
    normalized_phase = normalize_task_reminder_phase(phase)
    title = _task_title(task)
    task_type = _task_type(task)
    age_group = _age_group(child)
    category = _category(task_type, title)
    text = _text_for(
        title=title,
        category=category,
        phase=normalized_phase,
        age_group=age_group,
        count=count,
    )
    return {
        "phase": normalized_phase,
        "taskType": task_type,
        "category": category,
        "ageGroup": age_group,
        "text": text,
    }


def _text_for(*, title: str, category: str, phase: str, age_group: str, count: int) -> str:
    if age_group == "preschool":
        return _preschool_text(title=title, category=category, phase=phase, count=count)
    return _school_age_text(title=title, category=category, phase=phase, count=count)


def _preschool_text(*, title: str, category: str, phase: str, count: int) -> str:
    if phase == "prepare":
        return f"小朋友，{title}快到了。先把要用的东西放到手边。"
    if phase == "start":
        if category == "sports_ball":
            return f"小朋友，{title}开始啦。先看周围安全，再慢慢动起来。"
        if category == "sports":
            return f"小朋友，{title}开始啦。先喝一口水，再慢慢动起来。"
        if category == "schoolbag":
            return f"小朋友，我们开始{title}。一样一样看，不着急。"
        if category == "sleep":
            return f"小朋友，{title}开始啦。先去洗漱，再把东西放好。"
        if category == "creative":
            return f"小朋友，{title}时间到啦。先准备材料，再开始玩和练。"
        return f"小朋友，现在开始{title}。先做第一小步。"
    if phase in {"follow_up", "delay"}:
        if count > 1:
            return f"还没开始也没关系。我们先准备{title}要用的东西。"
        return f"小朋友，现在轮到{title}啦。我们先做第一步。"
    if phase == "wrap_up":
        if category.startswith("sports"):
            return f"{title}快结束啦。放慢一点，准备喝水和整理物品。"
        return f"{title}快结束啦。我们把手上的这一步收好。"
    if phase == "finish":
        if category == "sports_ball":
            return f"{title}结束啦。先把球放好，喝口水，身体放松一下。"
        if category == "sports":
            return f"{title}结束啦。先喝口水，把运动用的东西放回去。"
        if category == "schoolbag":
            return f"{title}结束啦。书包放到固定位置，明天更轻松。"
        if category == "sleep":
            return f"{title}完成啦。现在把灯调暗，准备休息。"
        return f"{title}完成啦。把东西放回原位，就可以休息一下。"
    return f"小朋友，{title}到时间啦。"


def _school_age_text(*, title: str, category: str, phase: str, count: int) -> str:
    if phase == "prepare":
        return f"{title}快到时间了，先准备好要用的物品。"
    if phase == "start":
        if category == "sports_ball":
            return f"{title}开始了。先确认周围安全，再开始运动。"
        if category == "learning":
            return f"{title}开始了。先坐好，准备从第一步开始。"
        if category == "schoolbag":
            return f"{title}开始了。按清单逐项检查。"
        return f"{title}开始了，先完成第一步。"
    if phase in {"follow_up", "delay"}:
        if count > 1:
            return f"还没有开始也没关系，先把{title}需要的东西准备好。"
        return f"{title}到时间了，我们先开始第一步。"
    if phase == "wrap_up":
        return f"{title}快结束了，准备收尾并整理物品。"
    if phase == "finish":
        if category.startswith("sports"):
            return f"{title}结束了，先补水，再把物品放回原处。"
        return f"{title}结束了，把物品归位后记录完成情况。"
    return f"{title}到时间了。"


def _category(task_type: str, title: str) -> str:
    text = f"{task_type} {title}"
    if any(word in text for word in ("篮球", "足球", "排球", "羽毛球", "乒乓", "球")):
        return "sports_ball"
    if task_type == "sports_outdoor" or any(word in text for word in ("运动", "户外", "跳绳", "跑步", "散步")):
        return "sports"
    if task_type == "schoolbag" or any(word in text for word in ("书包", "水杯", "物品", "课本")):
        return "schoolbag"
    if task_type == "sleep" or any(word in text for word in ("睡", "洗漱", "刷牙")):
        return "sleep"
    if task_type == "reading_interest" or any(word in text for word in ("绘本", "阅读", "画画", "音乐", "积木")):
        return "creative"
    if task_type == "learning" or any(word in text for word in ("作业", "数学", "拼音", "听读", "练习")):
        return "learning"
    if task_type == "life" or any(word in text for word in ("喝水", "整理", "穿衣", "收玩具")):
        return "life"
    return "custom"


def _task_title(task: Mapping) -> str:
    title = str(task.get("title") or "").strip()
    return title or "这项任务"


def _task_type(task: Mapping) -> str:
    return str(task.get("type") or task.get("taskType") or "custom").strip() or "custom"


def _age_group(child: Mapping | None) -> str:
    if not child:
        return "preschool"
    text = " ".join(
        str(child.get(key) or "")
        for key in ("age_stage", "ageStage", "education_stage", "educationStage", "grade")
    )
    if any(word in text for word in ("幼", "学前", "托班", "小班", "中班", "大班")):
        return "preschool"
    if any(word in text for word in ("初", "中学", "青少年")):
        return "teen"
    if any(word in text for word in ("五", "六", "高年级")):
        return "upper_primary"
    return "lower_primary"
