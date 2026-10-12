"""Readiness evidence for exact requested books, with no generation authority.

This catalogue does not select a child's school books or create a course. The
existing student authentication service still performs its normal session touch.
"""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse

from core.errors import ApiError


SCHEMA = "mira.learning.international-trials.v1"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "content/international_textbook_trials.v1.json"
BOOK_IDENTITIES = {
    "hk-sfa-chinese-p5-lower": ("chinese", "primary_5", "lower"),
    "hk-sfa-english-p6-upper": ("english", "primary_6", "upper"),
}


def _require(condition):
    if not condition:
        raise ApiError("international_trials_unavailable", "教材核对资料暂时不可用，请稍后重试", 503)


def _fields(value, names):
    _require(isinstance(value, dict) and set(value) == set(names))


def _text(value, maximum=2000):
    _require(isinstance(value, str) and 0 < len(value.strip()) <= maximum)


def _url(value):
    _text(value)
    try:
        parsed = urlparse(value)
        _require(parsed.scheme == "https" and bool(parsed.hostname)
                 and not parsed.username and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        _require(False)


def validate_manifest(value):
    _fields(value, ("schemaVersion", "checkedAt", "school", "textbooks"))
    _require(value["schemaVersion"] == SCHEMA)
    _text(value["checkedAt"], 10)
    try:
        _require(date.fromisoformat(value["checkedAt"]).isoformat() == value["checkedAt"])
    except ValueError:
        _require(False)
    school = value["school"]
    _fields(school, ("requestedName", "name", "website", "booklistStatus"))
    _require(school["requestedName"] == "香港圣方济各英文小学"
             and school["name"] == "聖方濟各英文小學"
             and school["website"] == "https://sfaeps.edu.hk/"
             and school["booklistStatus"] == "unconfirmed")
    books = value["textbooks"]
    _require(isinstance(books, list) and len(books) == len(BOOK_IDENTITIES))
    seen = set()
    for book in books:
        _fields(book, ("id", "subject", "gradeCode", "semester", "requestedTitle", "matchedTitle",
                       "publisher", "editionStatus", "editionNote", "candidates", "evidence", "requiredMaterials"))
        identity = book["id"]
        _require(isinstance(identity, str) and identity in BOOK_IDENTITIES and identity not in seen)
        seen.add(identity)
        _require((book["subject"], book["gradeCode"], book["semester"]) == BOOK_IDENTITIES[identity])
        for field in ("requestedTitle", "editionNote"):
            _text(book[field])
        _require(book["editionStatus"] in ("catalog_verified", "needs_confirmation"))
        for field in ("matchedTitle", "publisher"):
            if book[field] is not None:
                _text(book[field])
            else:
                _require(book["editionStatus"] != "catalog_verified")
        candidates = book["candidates"]
        _require(isinstance(candidates, list) and len(candidates) <= 10)
        for candidate in candidates:
            _fields(candidate, ("title", "publisher", "editionNote", "url"))
            for field in ("title", "publisher", "editionNote"):
                _text(candidate[field])
            _url(candidate["url"])
        evidence = book["evidence"]
        _require(isinstance(evidence, list) and 1 <= len(evidence) <= 20)
        for source in evidence:
            _fields(source, ("label", "url", "detail"))
            _text(source["label"])
            _text(source["detail"])
            _url(source["url"])
        materials = book["requiredMaterials"]
        _require(isinstance(materials, list) and 1 <= len(materials) <= 10)
        for material in materials:
            _text(material)
    return deepcopy(value)


class InternationalTextbookTrialService:
    def __init__(self, *, student_auth, manifest=None):
        self.student_auth = student_auth
        self._manifest = deepcopy(manifest)

    def catalog(self, token, query=None):
        if query:
            raise ApiError("international_trials_query_invalid", "教材测试查询参数无效", 400)
        self.student_auth.authenticate(token)
        value = self._manifest
        if value is None:
            try:
                value = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                _require(False)
        manifest = validate_manifest(value)
        return {"ok": True, **manifest, "generation": {
            "status": "blocked_source", "canGenerate": False, "publishedCourseKey": None,
        }}
