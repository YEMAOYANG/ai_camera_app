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


def course_storage_labels(course, manifest=None):
    """Project readable storage names without rewriting frozen book metadata.

    Edition descriptions and volume are separate identities. The first saved
    grade-one preview omitted the explicit unified-edition prefix; its exact
    reviewed book/resource identity is the only implicit-label correction.
    """
    from schemas.education import GRADE_BY_CODE

    grade = course.get("grade_code", course.get("gradeCode"))
    definition = GRADE_BY_CODE.get(grade)
    grade_label = definition.label if definition else "未标注年级"
    if manifest is None:
        return {"storageEditionLabel": "未绑定教材（历史课件）", "storageGradeLabel": grade_label}
    label = reviewed_edition_label(manifest) if manifest.get("editionLabel") else "未标注教材版本"
    initial_unified_book = (
        manifest.get("editionId"), manifest.get("publisher"), manifest.get("subject"),
        manifest.get("gradeCode"), manifest.get("volume"), manifest.get("schoolSystem"),
        manifest.get("source", {}).get("resourceId"),
    ) == ("pep-chinese-g1-upper-2022-standard", "人民教育出版社", "chinese", "primary_1", "upper",
          "six_year", "1c73b348-e8b6-47d6-84b0-6dbacbe28268")
    if manifest.get("subject") == "chinese" and (label.startswith("统编版") or initial_unified_book):
        label = "统编版"
    volume = {"upper": "上册", "lower": "下册", "full": "全册"}.get(manifest.get("volume"), "")
    grade_label += volume
    if manifest.get("schoolSystem") == "five_four":
        grade_label += "（五四制）"
    return {"storageEditionLabel": label, "storageGradeLabel": grade_label}
