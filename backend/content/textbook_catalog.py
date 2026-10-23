"""Strict, immutable textbook metadata and independently authored lesson briefs.

Importing a manifest does not approve its teaching scope or publish a course.
The manifest deliberately has no field for a PDF, original story or answer key.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

from core.errors import ApiError
from content.textbook_metadata import matches_source_label

SCHEMA = "mira.learning.textbook-manifest.v1"
GENERATION_SCHEMA = "mira.learning.textbook-original-generation.v2"
SUBJECTS = ("chinese", "math", "english", "science")
IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}\Z")
SOURCE_POLICY = {
    "allowWebSearch": False,
    "allowFullTextReproduction": False,
    "allowSourceParaphraseAsOriginal": False,
    "exerciseMode": "independently_authored",
    "visualMode": "original_or_licensed",
}
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/textbook-course.v2.json"


@lru_cache(maxsize=1)
def superseded_resources():
    """A reviewed inventory changes picker availability, never saved choices."""
    inventory = Path(__file__).parent / "textbooks/sources/smartedu-current-primary-20260928.json"
    from content.textbook_journey_registry import course_json
    return frozenset(course_json(inventory, source_root=inventory.parent)["supersededResourceIds"])


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
                   "gradeCode", "subject", "volume", "schoolSystem", "source", "coverage", "rightsReview", "units"), ("introduction", "directorySource"))
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
    fields(source, ("url", "resourceId", "verifiedAt"), ("kind",))
    try:
        url = urlparse(source["url"] if isinstance(source["url"], str) else "")
        port = url.port
    except ValueError:
        invalid("教材来源链接无效")
    if source.get("kind") == "official_catalog":
        # Exact verified records, not a wildcard trust of arbitrary government URLs.
        from content.textbook_journey_registry import course_json
        sources = Path(__file__).parent / 'textbooks/sources'
        records = course_json(sources / 'official-low-grade-english-20260928.json', source_root=sources)['records']
        record = next((r for r in records if r["recordId"] == source["resourceId"]), None)
        if (record is None or source["url"] != record["url"]
                or any(value[k] != record[k] for k in ("editionId", "publisher", "editionLabel", "gradeCode", "subject", "volume", "schoolSystem"))):
            invalid("教材与官方目录核验记录不一致")
    elif source.get("kind") == "smartedu_sync_classroom":
        if value["subject"] != "english":
            invalid("同步课堂补充教材须为已逐册核验的英语教材")
        # Supplement exact reviewed editions missing from the ebook inventory.
        # Starting grade/editor are part of the record, not publisher aliases.
        inventories = ("smartedu-sync-english-20260928.json", "smartedu-sync-fltrp-primary-20260928.json",
                       "smartedu-sync-fltrp-three-year-20260928.json")
        from content.textbook_journey_registry import course_json
        sources = Path(__file__).parent / 'textbooks/sources'
        records = [record for name in inventories for record in
                   course_json(sources / name, source_root=sources)['records']]
        record = next((r for r in records if r["resourceId"] == source["resourceId"]), None)
        if (record is None or source["url"] != record["url"]
                or any(value[k] != record[k] for k in ("editionId", "publisher", "gradeCode", "subject", "volume", "schoolSystem"))
                or not matches_source_label(value, record["editionLabel"])):
            invalid("教材与国家平台同步课堂核验记录不一致")
    elif source.get("kind", "smartedu_textbook") == "smartedu_textbook":
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
    else:
        invalid("教材来源类型无效")
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
        fields(unit, ("unitId", "title", "sequence", "lessons"), ("kind", "introduction"))
        if not one_of(unit.get("kind", "unit"), {"unit", "orientation"}):
            invalid("教材板块类型无效")
        if not identifier(unit["unitId"]) or unit["unitId"] in unit_ids or type(unit["sequence"]) is not int or unit["sequence"] != ordinal:
            invalid("教材单元标识或顺序重复、缺失")
        unit_ids.add(unit["unitId"])
        text(unit["title"])
        if not isinstance(unit["lessons"], list) or not 1 <= len(unit["lessons"]) <= 80:
            invalid("教材单元缺少课次")
        for position, lesson in enumerate(unit["lessons"], 1):
            fields(lesson, ("nodeId", "title", "sequence", "printedPage", "pdfPage", "brief"), ("sectionTitle",))
            if (not identifier(lesson["nodeId"]) or lesson["nodeId"] in node_ids
                    or type(lesson["sequence"]) is not int or lesson["sequence"] != position):
                invalid("教材课次标识或顺序重复、缺失")
            node_ids.add(lesson["nodeId"])
            text(lesson["title"])
            if "sectionTitle" in lesson:
                text(lesson["sectionTitle"], 500)
            for page in (lesson["printedPage"], lesson["pdfPage"]):
                if page is not None and (type(page) is not int or not 1 <= page <= 2000):
                    invalid("教材页码无效")
            brief = lesson["brief"]
            fields(brief, ("status", "objectives", "knowledgePoints", "priorKnowledge", "excludedTopics", "assessmentMode", "reviewNote"))
            if not one_of(brief["status"], {"draft", "approved"}) or not one_of(brief["assessmentMode"], {"objective", "observed"}):
                invalid("教学任务书状态无效")
            for key in ("objectives", "knowledgePoints", "priorKnowledge", "excludedTopics"):
                # A verified directory is not an authored teaching plan. Never
                # invent objectives merely to fill a newly imported lesson.
                texts(brief[key], required=brief["status"] == "approved" and key in {"objectives", "knowledgePoints"})
            text(brief["reviewNote"], 1000)
    if sum(len(u["lessons"]) for u in units) > 600:
        invalid("单册教材课次数量超出限制")
    if "directorySource" in value:
        directory = value["directorySource"]
        fields(directory, ("kind", "resourceId", "catalogId", "url", "verifiedAt", "snapshotSha256", "baseRevisionId"))
        expected_directory_url = (source["url"] if directory["kind"] == "smartedu_preview_directory" else
                                  f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/{directory['catalogId']}.json")
        if (not one_of(directory["kind"], {"smartedu_ebook_mapping", "smartedu_sync_classroom", "smartedu_preview_directory"})
                or not identifier(directory["catalogId"])
                or directory["resourceId"] != source["resourceId"]
                or directory["verifiedAt"] != source["verifiedAt"]
                or not isinstance(directory["snapshotSha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", directory["snapshotSha256"]) is None
                or (directory["baseRevisionId"] is not None and (not identifier(directory["baseRevisionId"])
                    or directory["baseRevisionId"] == value["revisionId"]))
                or directory["url"] != expected_directory_url
                or not units):
            invalid("教材目录来源或补充修订标识无效")
        if directory["kind"] == "smartedu_preview_directory" and (source.get("kind", "smartedu_textbook") != "smartedu_textbook" or directory["catalogId"] != source["resourceId"]):
            invalid("目录页必须来自同一本国家平台电子课本")
        if directory["kind"] == "smartedu_sync_classroom":
            if value["subject"] != "english" or (value["gradeCode"] not in {"primary_1", "primary_2"}
                    and source.get("kind") != "smartedu_sync_classroom"):
                invalid("同步课堂目录须关联已核验的英语教材版本")
            if source.get("kind") == "smartedu_sync_classroom" and directory["catalogId"] != source["resourceId"]:
                invalid("同步课堂目录与核验的教材资源编号不一致")
    # Optional additions preserve all previously imported manifests and hashes.
    from content.textbook_introductions import validate_introduction
    introductions = []
    if "introduction" in value:
        validate_introduction(value["introduction"], node_ids)
        introductions.append(value["introduction"])
    for unit in units:
        if "introduction" in unit:
            validate_introduction(unit["introduction"], {n["nodeId"] for n in unit["lessons"]})
            introductions.append(unit["introduction"])
    if len({g["introductionId"] for g in introductions}) != len(introductions):
        invalid("同册导学标识不能重复")
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
    from content.textbook_pedagogy import teaching_profile
    brief["teachingProfile"] = teaching_profile(manifest["gradeCode"])
    # Neither child identity nor access dates/provider configuration are content identity.
    return {**brief, "contentKey": digest(brief)}


def validate_frozen_brief(manifest, value):
    """A prompt upgrade must not invalidate an already reviewed fixed course."""
    from content.textbook_pedagogy import teaching_profile
    if not isinstance(value, dict) or not isinstance(value.get("textbookBinding"), dict):
        raise ApiError("textbook_build_invalid", "课程缺少固定教材任务书", 409)
    binding = value["textbookBinding"]
    expected = generation_brief(manifest, binding.get("nodeId"), teaching_revision=binding.get("teachingRevision"), part_index=binding.get("partIndex"))
    if value.get("schemaVersion") == "mira.learning.textbook-original-generation.v1":
        expected["schemaVersion"] = value["schemaVersion"]
        expected.pop("teachingProfile")
    elif value.get('teachingProfile', {}).get('schemaVersion') == 'mira.textbook.grade-pedagogy.v1':
        # A new low-reading policy must not invalidate reviewed historical
        # content identities. Only the exact registered v1 profile is accepted.
        expected['teachingProfile'] = teaching_profile(manifest['gradeCode'], version=1)
    prompt_hash = value.get("promptSha256")
    if not isinstance(prompt_hash, str) or re.fullmatch(r"[0-9a-f]{64}", prompt_hash) is None:
        raise ApiError("textbook_build_invalid", "课程任务书摘要无效", 409)
    expected["promptSha256"] = prompt_hash
    expected["contentKey"] = digest({k: v for k, v in expected.items() if k != "contentKey"})
    if expected != value:
        raise ApiError("textbook_build_invalid", "课程任务书与教材修订不一致", 409)
    return value
