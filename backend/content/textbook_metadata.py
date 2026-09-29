"""Reviewed display corrections for exact book identities, not revision rewrites.

Saved selections and published courses keep their original revision and digest.
Only a verified label is projected when presenting that same book to a parent.
"""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def reviewed_editions():
    path = Path(__file__).parent / "textbooks/sources/fltrp-edition-audit-20260928.json"
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    return {record["identity"]["editionId"]: record for record in records}


def review_for(manifest):
    record = reviewed_editions().get(manifest["editionId"])
    if record is None:
        return None
    identity = {key: manifest[key] for key in (
        "editionId", "publisher", "gradeCode", "subject", "volume", "schoolSystem")}
    identity["resourceId"] = manifest["source"]["resourceId"]
    labels = {*record["previousLabels"], record["editionLabel"]}
    return record if identity == record["identity"] and manifest["editionLabel"] in labels else None


def reviewed_edition_label(manifest):
    record = review_for(manifest)
    return record["editionLabel"] if record else manifest["editionLabel"]


def matches_source_label(manifest, source_label):
    if manifest["editionLabel"] == source_label:
        return True
    record = review_for(manifest)
    return bool(record and source_label in record["previousLabels"]
                and manifest["editionLabel"] == record["editionLabel"])
