"""Original, ungraded discovery activities attached to a frozen textbook revision.

These are not lesson assessments or OpenMAIC publication records. No provider
is called while importing, reading or revisiting an introduction.
"""
from copy import deepcopy

from content.textbook_catalog import digest, fields, identifier, invalid, text, texts


def validate_introduction(value, node_ids):
    fields(value, ("introductionId", "title", "hook", "estimatedMinutes", "authorship", "steps", "nextNodeIds"))
    if not identifier(value["introductionId"]) or value["authorship"] != "original":
        invalid("导学标识或原创声明无效")
    for key in ("title", "hook"):
        text(value[key], 120)
    if type(value["estimatedMinutes"]) is not int or not 2 <= value["estimatedMinutes"] <= 10:
        invalid("导学时长无效")
    steps = value["steps"]
    if not isinstance(steps, list) or len(steps) != 4:
        invalid("导学需要观察、探索、行动和衔接四个环节")
    for step, kind in zip(steps, ("discover", "choose", "do", "bridge")):
        extra = {"discover": "cards", "choose": "options", "do": "actions", "bridge": "question"}[kind]
        fields(step, ("kind", "title", "body", extra))
        if step["kind"] != kind:
            invalid("导学环节顺序无效")
        text(step["title"], 80)
        text(step["body"], 220)
        if kind in {"discover", "choose"}:
            items = step[extra]
            if not isinstance(items, list) or not 2 <= len(items) <= 4:
                invalid("导学探索选项无效")
            labels = set()
            for item in items:
                fields(item, ("label", "response"))
                text(item["label"], 40)
                text(item["response"], 180)
                if item["label"] in labels:
                    invalid("导学探索选项重复")
                labels.add(item["label"])
        elif kind == "do":
            texts(step["actions"], maximum=4)
        else:
            text(step["question"], 140)
    next_ids = value["nextNodeIds"]
    if (not isinstance(next_ids, list) or not 1 <= len(next_ids) <= 4
            or any(not identifier(n) or n not in node_ids for n in next_ids)
            or len(set(next_ids)) != len(next_ids)):
        invalid("导学必须衔接本册或本单元的真实课次")


def public_introduction(value, *, manifest=None):
    if not value:
        return None
    result = {**deepcopy(value), "contentSha256": digest(value)}
    if manifest:
        from content.textbook_picture_guides import picture_guide
        presentation = picture_guide(value, edition_id=manifest["editionId"], revision_id=manifest["revisionId"], grade_code=manifest["gradeCode"])
        if presentation:
            result["presentation"] = presentation
    return result
