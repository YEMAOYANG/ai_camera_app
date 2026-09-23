"""Strict, immutable textbook metadata and independently authored lesson briefs.

Importing a manifest does not approve its teaching scope or publish a course.
The manifest deliberately has no field for a PDF, original story or answer key.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from core.errors import ApiError

SCHEMA = "mira.learning.textbook-manifest.v1"
GENERATION_SCHEMA = "mira.learning.textbook-original-generation.v1"
SUBJECTS = {"chinese", "math", "english"}
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}\Z")
SOURCE_POLICY = {
    "allowWebSearch": False,
    "allowFullTextReproduction": False,
    "allowSourceParaphraseAsOriginal": False,
    "exerciseMode": "independently_authored",
    "visualMode": "original_or_licensed",
}
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/textbook-course.v1.json"


def authoring_prompt():
    return json.loads(PROMPT_PATH.read_text(encoding="utf-8"))


def one_of(value, options):
    return isinstance(value, str) and value in options


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def invalid(message):
    raise ApiError("textbook_manifest_invalid", message, 400)


def identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or not set(required) <= set(value):
        invalid("教材资料字段不完整或包含不支持的正文数据")


def text(value, maximum=300):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        invalid("教材文字字段无效")


def texts(value, *, maximum=30, required=True):
    if not isinstance(value, list) or len(value) > maximum or required and not value:
        invalid("教学目标列表无效")
    for item in value:
        text(item, 500)
    if len(set(value)) != len(value):
        invalid("教学目标列表包含重复内容")


def validate_manifest(value):
    fields(value, ("schemaVersion", "editionId", "revisionId", "title", "publisher", "editionLabel",
                   "gradeCode", "subject", "volume", "schoolSystem", "source", "coverage", "rightsReview", "units"))
    if value["schemaVersion"] != SCHEMA or not all(identifier(value[k]) for k in ("editionId", "revisionId")):
        invalid("教材版本标识无效")
    for key in ("title", "publisher", "editionLabel"):
        text(value[key])
    if (not one_of(value["gradeCode"], {f"primary_{i}" for i in range(1, 7)}) or not one_of(value["subject"], SUBJECTS)
            or not one_of(value["volume"], {"upper", "lower", "full"}) or not one_of(value["schoolSystem"], {"six_year", "five_four"})):
        invalid("教材学制、年级、学科或册次无效")
    if value["schoolSystem"] == "five_four" and value["gradeCode"] == "primary_6":
        invalid("五四学制小学仅包含一至五年级")
    source = value["source"]
    fields(source, ("url", "resourceId", "verifiedAt"))
    try:
        url = urlparse(source["url"] if isinstance(source["url"], str) else "")
        port = url.port
    except ValueError:
        invalid("教材来源链接无效")
    if (url.scheme != "https" or url.hostname != "basic.smartedu.cn" or url.username or url.password
            or port not in (None, 443) or url.path != "/tchMaterial/detail" or len(source["url"]) > 1000
            or url.fragment):
        invalid("教材来源必须是官方教材详情链接")
    text(source["resourceId"], 100)
    query = parse_qs(url.query, keep_blank_values=True)
    if (query.get("contentId") != [source["resourceId"]]
            or set(query) - {"contentId", "contentType", "catalogType", "subCatalog"}
            or any(len(items) != 1 for items in query.values())):
        invalid("教材来源链接与资源编号不一致")
    if not isinstance(source["verifiedAt"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["verifiedAt"]):
        invalid("教材核验日期无效")
    try:
        date.fromisoformat(source["verifiedAt"])
    except ValueError:
        invalid("教材核验日期无效")
    fields(value["coverage"], ("status", "note"))
    if not one_of(value["coverage"]["status"], {"index_only", "partial", "complete"}):
        invalid("请声明教材目录覆盖范围")
    text(value["coverage"]["note"], 500)
    fields(value["rightsReview"], ("status", "basis"))
    if not one_of(value["rightsReview"]["status"], {"pending", "cleared"}):
        invalid("教材使用依据状态无效")
    text(value["rightsReview"]["basis"], 1000)
    units = value["units"]
    if (not isinstance(units, list) or len(units) > 60
            or (value["coverage"]["status"] == "index_only") != (len(units) == 0)):
        invalid("教材单元无效")
    unit_ids, node_ids = set(), set()
    for ordinal, unit in enumerate(units, 1):
        fields(unit, ("unitId", "title", "sequence", "lessons"))
        if not identifier(unit["unitId"]) or unit["unitId"] in unit_ids or type(unit["sequence"]) is not int or unit["sequence"] != ordinal:
            invalid("教材单元标识或顺序重复、缺失")
        unit_ids.add(unit["unitId"])
        text(unit["title"])
        if not isinstance(unit["lessons"], list) or not 1 <= len(unit["lessons"]) <= 80:
            invalid("教材单元缺少课次")
        for position, lesson in enumerate(unit["lessons"], 1):
            fields(lesson, ("nodeId", "title", "sequence", "printedPage", "pdfPage", "brief"))
            if (not identifier(lesson["nodeId"]) or lesson["nodeId"] in node_ids
                    or type(lesson["sequence"]) is not int or lesson["sequence"] != position):
                invalid("教材课次标识或顺序重复、缺失")
            node_ids.add(lesson["nodeId"])
            text(lesson["title"])
            for page in (lesson["printedPage"], lesson["pdfPage"]):
                if page is not None and (type(page) is not int or not 1 <= page <= 2000):
                    invalid("教材页码无效")
            brief = lesson["brief"]
            fields(brief, ("status", "objectives", "knowledgePoints", "priorKnowledge", "excludedTopics", "assessmentMode", "reviewNote"))
            if not one_of(brief["status"], {"draft", "approved"}) or not one_of(brief["assessmentMode"], {"objective", "observed"}):
                invalid("教学任务书状态无效")
            for key in ("objectives", "knowledgePoints", "priorKnowledge", "excludedTopics"):
                texts(brief[key], required=key in {"objectives", "knowledgePoints"})
            text(brief["reviewNote"], 1000)
    if sum(len(u["lessons"]) for u in units) > 600:
        invalid("单册教材课次数量超出限制")
    return deepcopy(value)


def lesson_by_id(manifest, node_id):
    for unit in manifest["units"]:
        for lesson in unit["lessons"]:
            if lesson["nodeId"] == node_id:
                return unit, lesson
    raise ApiError("textbook_lesson_not_found", "这本教材中没有这节课", 404)


def generation_brief(manifest, node_id, *, teaching_revision="1", part_index=1):
    manifest = validate_manifest(manifest)
    unit, lesson = lesson_by_id(manifest, node_id)
    if manifest["rightsReview"]["status"] != "cleared" or lesson["brief"]["status"] != "approved":
        raise ApiError("textbook_review_required", "请先核验教材使用依据与本课教学目标", 409)
    if not identifier(teaching_revision) or type(part_index) is not int or not 1 <= part_index <= 20:
        raise ApiError("textbook_generation_invalid", "课时或讲解版本无效", 400)
    binding = {"editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"],
               "alignmentManifestSha256": digest(manifest), "nodeId": node_id,
               "partIndex": part_index, "teachingRevision": teaching_revision}
    brief = {"schemaVersion": GENERATION_SCHEMA, "textbookBinding": binding,
             "promptSha256": digest(authoring_prompt()),
             "gradeCode": manifest["gradeCode"], "subject": manifest["subject"],
             "unitTitle": unit["title"], "lessonTitle": lesson["title"],
             "knowledgeBrief": deepcopy(lesson["brief"]), "allowedReferenceBlockIds": [],
             "sourcePolicy": deepcopy(SOURCE_POLICY)}
    # Neither child identity nor access dates/provider configuration are content identity.
    return {**brief, "contentKey": digest(brief)}


def validate_frozen_brief(manifest, value):
    """A prompt upgrade must not invalidate an already reviewed fixed course."""
    if not isinstance(value, dict) or not isinstance(value.get("textbookBinding"), dict):
        raise ApiError("textbook_build_invalid", "课程缺少固定教材任务书", 409)
    binding = value["textbookBinding"]
    expected = generation_brief(manifest, binding.get("nodeId"), teaching_revision=binding.get("teachingRevision"), part_index=binding.get("partIndex"))
    prompt_hash = value.get("promptSha256")
    if not isinstance(prompt_hash, str) or re.fullmatch(r"[0-9a-f]{64}", prompt_hash) is None:
        raise ApiError("textbook_build_invalid", "课程任务书摘要无效", 409)
    expected["promptSha256"] = prompt_hash
    expected["contentKey"] = digest({k: v for k, v in expected.items() if k != "contentKey"})
    if expected != value:
        raise ApiError("textbook_build_invalid", "课程任务书与教材修订不一致", 409)
    return value
