from __future__ import annotations

import re


def build_child_vision_context(child: dict | None) -> dict[str, str]:
    if not isinstance(child, dict) or not child:
        return {"child_reference": "孩子", "age_stage": "未知"}
    nickname = str(child.get("nickname") or "").strip()
    child_reference = nickname if nickname else "孩子"
    age_stage = (
        str(child.get("ageStage") or child.get("educationStage") or "").strip()
        or "未知"
    )
    context = {"child_reference": child_reference, "age_stage": age_stage}
    grade = str(child.get("grade") or "").strip()
    if grade:
        context["grade"] = grade
    return context


def sanitize_parent_facing_observation(
    text: str,
    *,
    child_reference: str = "孩子",
) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return ""
    reference = str(child_reference or "孩子").strip() or "孩子"
    replacements = (
        (r"画面[中里]?可见一个人的", f"画面中可见{reference}的"),
        (r"画面[中里]?可见有人", f"画面中可见{reference}"),
        (r"画面[中里]?有?一个人", f"画面中有{reference}"),
        (r"镜头[中里]?有?一个人", f"镜头中有{reference}"),
        (r"可见一个人的", f"可见{reference}的"),
        (r"可见有人", f"可见{reference}"),
        (r"一个人的", f"{reference}的"),
        (r"一名儿童", reference),
        (r"一名孩子", reference),
        (r"一个小孩", reference),
        (r"一名小孩", reference),
        (r"^一个人", reference),
        (r"^有人", reference),
        (r"^画面中可见", "画面中看到"),
        (r"^画面里可见", "画面中看到"),
    )
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = cleaned.replace("小孩", reference).replace("儿童", reference)
    cleaned = cleaned.replace("似乎", "可能")
    return cleaned.strip()
