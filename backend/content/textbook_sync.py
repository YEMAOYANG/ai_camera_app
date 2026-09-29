"""Deterministic import of official directory metadata, never course authoring.

Snapshots contain titles, hierarchy, public resource identifiers and page maps.
No textbook body, exercise, image, audio or learner data is copied into a manifest.
Existing nonempty directories are deliberately not regenerated.
"""
from __future__ import annotations

from copy import deepcopy

from content.textbook_catalog import digest, validate_manifest

TREE_BASE = "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/trees/"


def normalized_tree(nodes):
    """Keep official ordering and IDs; omit nodes the platform hides."""
    if not isinstance(nodes, list):
        raise ValueError("Official directory must be a list")
    result = []
    for node in nodes:
        if node.get("custom_properties", {}).get("hidden") is True:
            continue
        result.append({"id": node["id"], "title": node["title"].strip(),
                       "children": normalized_tree(node.get("child_nodes") or [])})
    return result


def draft_brief():
    return {"status": "draft", "objectives": [], "knowledgePoints": [],
            "priorKnowledge": [], "excludedTopics": [], "assessmentMode": "objective",
            "reviewNote": "仅同步官方目录；教学目标与原创课件尚未编制、审核。"}


def directory_revision(base, snapshot):
    """Enrich an empty index for the exact same book. Return None if preserved.

    Content-derived revisions and official node IDs make repeated offline runs
    byte stable. Callers must create files exclusively, never replace revisions.
    """
    if base["units"] or base["coverage"]["status"] != "index_only":
        return None
    if snapshot["resourceId"] != base["source"]["resourceId"]:
        raise ValueError("Directory belongs to a different textbook resource")
    if snapshot["kind"] not in {"smartedu_ebook_mapping", "smartedu_sync_classroom", "smartedu_preview_directory"}:
        raise ValueError("Unsupported directory source")
    pages = snapshot.get("pages", {})
    front = snapshot.get("frontPageCount")
    nodes_seen = set()

    def leaves(node, path=()):
        if node["id"] in nodes_seen:
            raise ValueError("Duplicate official directory node")
        nodes_seen.add(node["id"])
        if node["children"]:
            for child in node["children"]:
                yield from leaves(child, (*path, node["title"]))
        else:
            yield node, path

    units = []
    for root in snapshot["tree"]:
        lessons = []
        for node, parents in leaves(root):
            page = pages.get(node["id"])
            printed = page - front if type(page) is int and type(front) is int and page > front else None
            printed = snapshot.get("printedPages", {}).get(node["id"], printed)
            lesson = {"nodeId": node["id"], "title": node["title"], "sequence": len(lessons) + 1,
                      "pdfPage": page, "printedPage": printed, "brief": draft_brief()}
            # Preserve intermediate headings when adapting a deep official tree
            # to the app's unit/lesson structure (e.g. Section A / Let's talk).
            if len(parents) > 1:
                lesson["sectionTitle"] = " / ".join(parents[1:])
            lessons.append(lesson)
        units.append({"unitId": root["id"], "title": root["title"], "sequence": len(units) + 1, "lessons": lessons})
    if not units:
        raise ValueError("Official directory is empty")
    value = deepcopy(base)
    snapshot_hash = digest(snapshot)
    value["revisionId"] = "directory-" + snapshot_hash[:24]
    value["source"]["verifiedAt"] = snapshot["verifiedAt"]
    value["directorySource"] = {"kind": snapshot["kind"], "resourceId": snapshot["resourceId"],
        "catalogId": snapshot["catalogId"], "url": (base["source"]["url"] if snapshot["kind"] == "smartedu_preview_directory" else TREE_BASE + snapshot["catalogId"] + ".json"),
        "verifiedAt": snapshot["verifiedAt"], "snapshotSha256": snapshot_hash,
        "baseRevisionId": base["revisionId"]}
    value["units"] = units
    value["coverage"] = {"status": "complete", "note": (
        "已同步该教材关联的国家平台电子课本目录与页码；课件另行编制。"
        if snapshot["kind"] == "smartedu_ebook_mapping" else
        "已逐项核对国家平台电子课本目录页；保持原目录粒度与印刷页码，未推测课内细分栏目或 PDF 页码。"
        if snapshot["kind"] == "smartedu_preview_directory" else
        "已同步国家平台该版本的同步课堂目录；平台未提供对应课本页码。该系列不等同于最新年度修订版。")}
    if "coverage" in snapshot:
        coverage = snapshot["coverage"]
        if coverage.get("status") not in {"complete", "partial"} or not str(coverage.get("note", "")).strip():
            raise ValueError("Directory coverage must describe the verified source scope")
        value["coverage"] = deepcopy(coverage)
    value["rightsReview"] = {"status": "pending", "basis": "仅收录官方目录标题、层级、资源编号及可核实页码；未导入教材正文、题目或媒体，未批准课件生成。"}
    return validate_manifest(value)
