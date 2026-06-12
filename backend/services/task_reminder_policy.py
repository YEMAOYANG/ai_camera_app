from __future__ import annotations

import re
from typing import Mapping

from services.ai_text_provider import AiTextProvider


OUTDOOR_WALK_KEYWORDS = (
    "遛娃",
    "溜娃",
    "遛弯",
    "溜弯",
    "遛一遛",
    "溜达",
    "散步",
    "走走",
    "公园",
    "下楼",
    "楼下",
    "出门",
    "外出",
    "户外",
    "晒太阳",
    "放风",
)

OUTDOOR_WALK_BAD_COPY = (
    "第一步",
    "怎么做",
    "准备东西",
    "准备物品",
    "准备材料",
    "要用的东西",
    "放到手边",
)

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
    ai_text_provider: AiTextProvider | None = None,
    prompt: str = "",
) -> dict:
    normalized_phase = normalize_task_reminder_phase(phase)
    title = _task_title(task)
    task_type = _task_type(task)
    age_group = _age_group(child)
    child_name = _child_name(child)
    category = _category(task_type, title, task)
    spoken_title = _spoken_task_title(title, category)
    text_source = "fallback"
    text = _ai_text_for(
        ai_text_provider=ai_text_provider,
        prompt=prompt,
        task=task,
        title=title,
        spoken_title=spoken_title,
        task_type=task_type,
        category=category,
        phase=normalized_phase,
        age_group=age_group,
        child_name=child_name,
        count=count,
    )
    if text:
        text_source = "ai"
    else:
        text = _text_for(
            title=spoken_title,
            category=category,
            phase=normalized_phase,
            age_group=age_group,
            child_name=child_name,
            count=count,
        )
    return {
        "phase": normalized_phase,
        "taskType": task_type,
        "category": category,
        "ageGroup": age_group,
        "text": text,
        "textSource": text_source,
    }


def _ai_text_for(
    *,
    ai_text_provider: AiTextProvider | None,
    prompt: str,
    task: Mapping,
    title: str,
    spoken_title: str,
    task_type: str,
    category: str,
    phase: str,
    age_group: str,
    child_name: str,
    count: int,
) -> str | None:
    if ai_text_provider is None or not prompt:
        return None
    user_prompt = _task_reminder_user_prompt(
        task=task,
        title=title,
        spoken_title=spoken_title,
        task_type=task_type,
        category=category,
        phase=phase,
        age_group=age_group,
        child_name=child_name,
        count=count,
    )
    response = ai_text_provider.complete(
        system_prompt=prompt,
        user_prompt=user_prompt,
        max_tokens=80,
        temperature=0.35,
    )
    if response is None:
        return None
    return _clean_ai_text(response.text, category=category, child_name=child_name)


def _task_reminder_user_prompt(
    *,
    task: Mapping,
    title: str,
    spoken_title: str,
    task_type: str,
    category: str,
    phase: str,
    age_group: str,
    child_name: str,
    count: int,
) -> str:
    description = str(task.get("description") or "").strip() or "无"
    scheduled_start = (
        str(task.get("scheduled_start") or task.get("scheduledStart") or "").strip()
        or "未设置"
    )
    scheduled_end = (
        str(task.get("scheduled_end") or task.get("scheduledEnd") or "").strip()
        or "未设置"
    )
    return "\n".join(
        [
            f"任务标题：{title}",
            f"孩子可听懂说法：{spoken_title}",
            f"任务说明：{description}",
            f"任务类型：{task_type}",
            f"语义分类：{category}",
            f"提醒阶段：{phase}",
            f"孩子称呼：{child_name}",
            f"孩子年龄段：{age_group}",
            f"提醒次数：{count}",
            f"计划时间：{scheduled_start} - {scheduled_end}",
            "只输出要从摄像头播报给孩子的一句话。",
        ]
    )


def _clean_ai_text(text: str, *, category: str, child_name: str) -> str | None:
    value = str(text or "").strip()
    if not value:
        return None
    value = re.sub(r"^[\"'“”‘’\s]+|[\"'“”‘’\s]+$", "", value)
    value = re.sub(r"^[\-\*\d.、\s]+", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return None
    if category == "outdoor_walk":
        if any(word in value for word in OUTDOOR_WALK_BAD_COPY):
            return None
        value = _replace_outdoor_parent_words(value)
    if category == "hydration" and any(
        word in value
        for word in (
            "准备东西",
            "准备物品",
            "准备材料",
            "要用的东西",
            "先把东西",
            "放到手边",
            "准备一下东西",
        )
    ):
        return None
    sentences = [
        item.strip()
        for item in re.split(r"(?<=[。！？!?])", value)
        if item.strip()
    ]
    if sentences:
        value = sentences[0]
    if child_name and child_name != "小朋友":
        value = re.sub(r"^小朋友[，,、\s]*", f"{child_name}，", value)
        if child_name not in value[:10]:
            value = f"{child_name}，{value}"
    max_chars = 54
    if len(value) > max_chars:
        value = value[:max_chars].rstrip(" ，,；;：:") + "。"
    return value


def _text_for(
    *,
    title: str,
    category: str,
    phase: str,
    age_group: str,
    child_name: str,
    count: int,
) -> str:
    if age_group == "preschool":
        return _preschool_text(
            title=title,
            category=category,
            phase=phase,
            child_name=child_name,
            count=count,
        )
    return _school_age_text(
        title=title,
        category=category,
        phase=phase,
        child_name=child_name,
        count=count,
    )


def _preschool_text(
    *,
    title: str,
    category: str,
    phase: str,
    child_name: str,
    count: int,
) -> str:
    if phase == "prepare":
        if category == "hydration":
            return f"{child_name}，等一下该{title}啦，慢慢喝几口水就好。"
        if category == "outdoor_walk":
            return f"{child_name}，等一下要出门走走啦，先穿好鞋子，跟着大人一起。"
        return f"{child_name}，{title}快到了。先想一想第一步怎么做。"
    if phase == "start":
        if category == "hydration":
            return f"{child_name}，{title}时间到啦。慢慢喝几口，喝完把杯子放好。"
        if category == "outdoor_walk":
            return f"{child_name}，我们出门走走啦，慢慢走，牵好大人的手。"
        if category == "sports_ball":
            return f"{child_name}，{title}开始啦。先看周围安全，再慢慢动起来。"
        if category == "sports":
            return f"{child_name}，{title}开始啦。先喝一口水，再慢慢动起来。"
        if category == "schoolbag":
            return f"{child_name}，我们开始{title}。一样一样看，不着急。"
        if category == "sleep":
            return f"{child_name}，{title}开始啦。先去洗漱，再把东西放好。"
        if category == "creative":
            return f"{child_name}，{title}时间到啦。先准备材料，再开始玩和练。"
        return f"{child_name}，现在开始{title}。先做第一小步。"
    if phase in {"follow_up", "delay"}:
        if category == "hydration":
            return f"{child_name}，先喝几口水吧，喝完我们就继续。"
        if category == "outdoor_walk":
            return f"{child_name}，准备好就和大人一起出门，慢慢走不着急。"
        if count > 1:
            return f"{child_name}，还没开始也没关系，先从{title}的第一步开始。"
        return f"{child_name}，现在轮到{title}啦。我们先做第一步。"
    if phase == "wrap_up":
        if category == "hydration":
            return f"{title}快结束啦。最后再喝一小口，把杯子放回原位。"
        if category == "outdoor_walk":
            return "户外活动快结束啦，和大人一起慢慢回家。"
        if category.startswith("sports"):
            return f"{title}快结束啦。放慢一点，准备喝水和整理物品。"
        return f"{title}快结束啦。我们把手上的这一步收好。"
    if phase == "finish":
        if category == "hydration":
            return f"{title}完成啦。杯子放好，嘴巴和手擦干净。"
        if category == "outdoor_walk":
            return "户外活动结束啦，回家先洗手喝水，休息一下。"
        if category == "sports_ball":
            return f"{title}结束啦。先把球放好，喝口水，身体放松一下。"
        if category == "sports":
            return f"{title}结束啦。先喝口水，把运动用的东西放回去。"
        if category == "schoolbag":
            return f"{title}结束啦。书包放到固定位置，明天更轻松。"
        if category == "sleep":
            return f"{title}完成啦。现在把灯调暗，准备休息。"
        return f"{title}完成啦。把东西放回原位，就可以休息一下。"
    return f"{child_name}，{title}到时间啦。"


def _school_age_text(
    *,
    title: str,
    category: str,
    phase: str,
    child_name: str,
    count: int,
) -> str:
    if phase == "prepare":
        if category == "hydration":
            return f"{child_name}，{title}快到时间了，等会儿慢慢喝几口水。"
        if category == "outdoor_walk":
            return f"{child_name}，等会儿要出门活动，穿好鞋子，跟家人一起走。"
        return f"{child_name}，{title}快到时间了，等会儿从第一步开始。"
    if phase == "start":
        if category == "hydration":
            return f"{child_name}，{title}时间到了，慢慢喝几口，喝完把杯子放好。"
        if category == "outdoor_walk":
            return f"{child_name}，出门活动开始了，注意看路，跟家人一起走。"
        if category == "sports_ball":
            return f"{child_name}，{title}开始了。先确认周围安全，再开始运动。"
        if category == "learning":
            return f"{child_name}，{title}开始了。先坐好，从第一步开始。"
        if category == "schoolbag":
            return f"{child_name}，{title}开始了。按清单逐项检查。"
        return f"{child_name}，{title}开始了，先完成第一步。"
    if phase in {"follow_up", "delay"}:
        if category == "hydration":
            return f"{child_name}，{title}还没完成，先喝几口水，别着急。"
        if category == "outdoor_walk":
            return f"{child_name}，准备好就出门活动，跟家人一起慢慢走。"
        if count > 1:
            return f"{child_name}，还没有开始也没关系，先做{title}的第一步。"
        return f"{child_name}，{title}到时间了，我们先开始第一步。"
    if phase == "wrap_up":
        if category == "hydration":
            return f"{title}快结束了，最后喝一小口，再把杯子放回去。"
        if category == "outdoor_walk":
            return "户外活动快结束了，准备和家人一起回家。"
        return f"{title}快结束了，准备收尾并整理物品。"
    if phase == "finish":
        if category == "hydration":
            return f"{title}完成了，杯子放回原处就可以继续下一件事。"
        if category == "outdoor_walk":
            return "户外活动结束了，回家先洗手喝水，休息一下。"
        if category.startswith("sports"):
            return f"{title}结束了，先补水，再把物品放回原处。"
        return f"{title}结束了，把物品归位后记录完成情况。"
    return f"{child_name}，{title}到时间了。"


def _category(task_type: str, title: str, task: Mapping | None = None) -> str:
    description = str((task or {}).get("description") or "").strip()
    text = f"{task_type} {title} {description}"
    if any(word in text for word in ("喝水", "补水", "喝几口水", "饮水")):
        return "hydration"
    if any(word in text for word in ("篮球", "足球", "排球", "羽毛球", "乒乓", "球")):
        return "sports_ball"
    if any(word in text for word in ("跳绳", "跑步", "轮滑", "骑车", "体能", "运动")):
        return "sports"
    if task_type == "sports_outdoor" or any(word in text for word in OUTDOOR_WALK_KEYWORDS):
        return "outdoor_walk"
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


def _spoken_task_title(title: str, category: str) -> str:
    if category == "outdoor_walk" and any(word in title for word in OUTDOOR_WALK_KEYWORDS):
        return "出门走走"
    return title


def _replace_outdoor_parent_words(text: str) -> str:
    value = text
    for word in ("遛娃", "溜娃", "遛弯", "溜弯", "遛一遛", "溜达"):
        value = value.replace(word, "出门走走")
    return value


def _child_name(child: Mapping | None) -> str:
    if not child:
        return "小朋友"
    for key in ("nickname", "name", "display_name", "displayName"):
        value = str(child.get(key) or "").strip()
        if value:
            return value
    return "小朋友"


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
