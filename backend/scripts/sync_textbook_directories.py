"""Fetch official TOCs or build immutable manifests from audited snapshots.

This command never connects to a database, prepares a course, or calls a model.
Use textbooks.py import-catalog separately after reviewing the generated files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.textbook_catalog import digest, validate_manifest
from content.textbook_sync import TREE_BASE, directory_revision, normalized_tree

BASE = "https://s-file-1.ykt.cbern.com.cn/zxx"


def manifests(paths):
    result = []
    for root in paths:
        for path in sorted(root.rglob("*.json")) if root.is_dir() else [root]:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("schemaVersion") == "mira.learning.textbook-manifest.v1":
                result.append(validate_manifest(value))
    return result


def write_new(path, value):
    """An existing artifact is either identical or an explicit conflict."""
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != value:
            raise ValueError(f"Refusing to overwrite different data: {path}")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    return True


def read_public_json(url):
    # Only public metadata endpoints; no cookie, token, login or PDF retrieval.
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    allowed = {"s-file-1.ykt.cbern.com.cn", "r1-ndr.ykt.cbern.com.cn", "r2-ndr.ykt.cbern.com.cn", "r3-ndr.ykt.cbern.com.cn",
               "r1-ndr-private.ykt.cbern.com.cn", "r2-ndr-private.ykt.cbern.com.cn", "r3-ndr-private.ykt.cbern.com.cn"}
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Unexpected official metadata host")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://basic.smartedu.cn/"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Directory metadata exceeds limit")
    return json.loads(raw)


def fetch_snapshot(manifest, verified_at):
    resource = manifest["source"]["resourceId"]
    if manifest["source"].get("kind", "smartedu_textbook") != "smartedu_textbook":
        raise ValueError("This source requires a separately verified sync-classroom association")
    detail_url = f"{BASE}/ndrv2/resources/tch_material/details/{resource}.json"
    detail = read_public_json(detail_url)
    if detail.get("id") != resource or detail.get("status") != "ONLINE":
        raise ValueError("Official textbook identity/status does not match")
    item = next((item for item in detail.get("ti_items", []) if item.get("ti_file_flag") == "ebook_mapping"), None)
    if not item:
        raise ValueError("Official book has no separate verified directory mapping")
    mapping_url = item["ti_storages"][0].replace(".json", ".txt")
    mapping = read_public_json(mapping_url)
    relation_url = f"{BASE}/ndrs/resources/{resource}/relation_teachingmaterials.json"
    relations = read_public_json(relation_url)
    catalog = mapping["ebook_id"]
    if not any(r.get("relation_type_code") == "EBOOK_RELATION" and r.get("source_resource_id") == catalog
               and r.get("target_resource_id") == resource for r in relations):
        raise ValueError("Official directory is not associated with this textbook")
    return {"schemaVersion": "mira.smartedu-directory-snapshot.v1", "resourceId": resource,
            "kind": "smartedu_ebook_mapping", "catalogId": catalog, "verifiedAt": verified_at,
            "tree": normalized_tree(read_public_json(TREE_BASE + catalog + ".json")),
            "pages": {row["node_id"]: row["page_number"] for row in mapping["mappings"]},
            "frontPageCount": mapping["front_page"],
            "evidence": {"detailUrl": detail_url, "relationUrl": relation_url, "mappingUrl": mapping_url,
                         "officialTitle": detail["title"]}}


def build_catalog(existing, snapshots, output):
    by_resource = {}
    for manifest in existing:
        by_resource.setdefault(manifest["source"]["resourceId"], []).append(manifest)
    report = []
    for snapshot in snapshots:
        candidates = by_resource.get(snapshot["resourceId"], [])
        if not candidates:
            raise ValueError("Snapshot has no verified textbook index: " + snapshot["resourceId"])
        if any(m["units"] for m in candidates):
            report.append({"resourceId": snapshot["resourceId"], "status": "preserved_existing_directory"})
            continue
        base = max(candidates, key=lambda m: m["revisionId"])
        manifest = directory_revision(base, snapshot)
        path = output / (manifest["editionId"] + "." + manifest["revisionId"] + ".json")
        created = write_new(path, manifest)
        report.append({"resourceId": snapshot["resourceId"], "status": "created" if created else "unchanged",
                       "editionId": manifest["editionId"], "revisionId": manifest["revisionId"],
                       "lessonCount": sum(len(u["lessons"]) for u in manifest["units"]), "sha256": digest(manifest)})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "build"))
    parser.add_argument("--indexes", nargs="+", required=True, type=Path)
    parser.add_argument("--snapshots", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--verified-at", default=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat())
    args = parser.parse_args()
    existing = manifests(args.indexes)
    if args.action == "build":
        if args.output is None:
            parser.error("build requires --output")
        snapshots = [json.loads(p.read_text()) for p in sorted(args.snapshots.glob("*.json"))]
        report = build_catalog(existing, snapshots, args.output)
    else:
        report, seen = [], set()
        protected = {m["source"]["resourceId"] for m in existing if m["units"]}
        for manifest in existing:
            rid = manifest["source"]["resourceId"]
            if rid in seen:
                continue
            seen.add(rid)
            path = args.snapshots / (rid + ".json")
            if rid in protected or path.exists():
                report.append({"resourceId": rid, "status": "preserved_existing"})
                continue
            try:
                write_new(path, fetch_snapshot(manifest, args.verified_at))
                report.append({"resourceId": rid, "status": "fetched"})
            except (ValueError, OSError, KeyError) as exc:
                report.append({"resourceId": rid, "status": "directory_unavailable", "reason": str(exc)})
    result = {"providerDispatched": False, "counts": dict(Counter(r["status"] for r in report)), "books": report}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"providerDispatched": False, "counts": result["counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
