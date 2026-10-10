"""Offline inventory and immutable authoring tasks, never a course generator.

The preferred revision is the most complete file available to this audit. It is
not the database's latest import or a parent's saved textbook selection.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path

from content.textbook_catalog import SCHEMA, SUBJECTS, canonical, digest, superseded_resources, validate_manifest
from content.textbook_pedagogy import teaching_profile

PLAN_SCHEMA = "mira.learning.textbook-batch-plan.v1"
TASK_SCHEMA = "mira.learning.textbook-authoring-task.v1"
COVERAGE_RANK = {"index_only": 0, "partial": 1, "complete": 2}
IDENTITY_FIELDS = ("editionId", "publisher", "gradeCode", "subject", "volume", "schoolSystem")
QUALITY_POLICY_PATH = Path(__file__).parent / "textbook_courseware_quality.v1.json"


def book_identity(manifest):
    return {**{key: manifest[key] for key in IDENTITY_FIELDS},
            "resourceId": manifest["source"]["resourceId"]}


def load_manifests(catalog):
    """Validate recursively, deduplicate exact revisions, fail on conflicts."""
    catalog = Path(catalog).resolve()
    if not catalog.exists():
        raise ValueError(f"Catalog does not exist: {catalog}")
    paths = sorted(catalog.rglob("*.json")) if catalog.is_dir() else [catalog]
    revisions, identities = {}, {}
    file_count = 0
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schemaVersion") != SCHEMA:
            continue
        manifest = validate_manifest(value)
        file_count += 1
        identity = book_identity(manifest)
        edition = manifest["editionId"]
        if edition in identities and identities[edition] != identity:
            raise ValueError(f"Immutable textbook identity changed: {edition} ({path})")
        identities[edition] = identity
        key = edition, manifest["revisionId"]
        sha = digest(manifest)
        if key in revisions:
            if revisions[key]["manifestSha256"] != sha:
                raise ValueError(f"Conflicting immutable textbook revision: {edition}/{key[1]} ({path})")
            revisions[key]["sourcePaths"].append(str(path))
        else:
            revisions[key] = {"manifest": manifest, "manifestSha256": sha, "sourcePaths": [str(path)]}
    if not revisions:
        raise ValueError("No textbook manifests found in catalog")
    return list(revisions.values()), file_count


def revision_rank(row):
    value = row["manifest"]
    return (COVERAGE_RANK[value["coverage"]["status"]], len(value["units"]),
            sum(len(unit["lessons"]) for unit in value["units"]),
            bool(value.get("introduction")),
            sum(bool(unit.get("introduction")) for unit in value["units"]), value["revisionId"])


def _revision_summary(row):
    value = row["manifest"]
    return {"revisionId": value["revisionId"], "manifestSha256": row["manifestSha256"],
            "coverage": deepcopy(value["coverage"]), "unitCount": len(value["units"]),
            "knownDirectoryLessonNodes": sum(len(unit["lessons"]) for unit in value["units"]),
            "hasExplorationContent": bool(value.get("introduction")),
            "unitGuideContentCount": sum(bool(unit.get("introduction")) for unit in value["units"]),
            "sourcePaths": row["sourcePaths"]}


def _task(row, kind, *, quality, unit=None, lesson=None, introduction=None):
    value = row["manifest"]
    scope = {key: value[key] for key in ("editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume")}
    scope.update(unitId=unit["unitId"] if unit else None, nodeId=lesson["nodeId"] if lesson else None)
    blockers = []
    if value["rightsReview"]["status"] != "cleared":
        blockers.append("textbook_rights_review_pending")
    if value["coverage"]["status"] == "index_only":
        blockers.append("official_directory_missing")
    elif value["coverage"]["status"] == "partial":
        blockers.append("official_directory_incomplete")
    if lesson and lesson["brief"]["status"] != "approved":
        blockers.append("lesson_teaching_brief_unapproved")
    if lesson:
        blockers.append("lesson_segmentation_review_required")
    if quality["status"] == "missing":
        blockers.append("courseware_quality_policy_missing")
    # Reusing text is deliberately independent of picture/audio or classroom QA.
    content = deepcopy(introduction) if introduction else None
    knowledge = deepcopy(lesson["brief"]) if lesson else None
    profile = teaching_profile(value["gradeCode"])
    scoped_units = [unit] if unit else value["units"]
    directory_scope = [{"unitId": entry["unitId"], "title": entry["title"], "lessons": [
        {"nodeId": node["nodeId"], "title": node["title"], "sectionTitle": node.get("sectionTitle"),
         "brief": deepcopy(node["brief"])} for node in entry["lessons"]
        if not lesson or node["nodeId"] == lesson["nodeId"]]} for entry in scoped_units]
    identity = {"schemaVersion": TASK_SCHEMA, "kind": kind, "scope": scope,
                "manifestSha256": row["manifestSha256"], "teachingProfileSha256": digest(profile),
                "qualityPolicySha256": quality["policySha256"],
                "knowledgeBriefSha256": digest(knowledge) if knowledge else None,
                "originalContentSha256": digest(content) if content else None}
    return {**identity, "taskId": digest(identity),
            "title": lesson["title"] if lesson else unit["title"] if unit else value["title"],
            "bookTitle": value["title"], "unitTitle": unit["title"] if unit else None,
            "deliveryBatchId": value["gradeCode"] + "-" + value["subject"],
            "directoryScope": directory_scope,
            "sourcePaths": row["sourcePaths"], "source": deepcopy(value["source"]),
            "qualityPolicyRef": deepcopy(quality),
            "directorySource": deepcopy(value.get("directorySource")),
            "directoryCoverage": deepcopy(value["coverage"]), "rightsReview": deepcopy(value["rightsReview"]),
            "teachingProfile": profile, "knowledgeBrief": knowledge,
            "objectives": deepcopy(knowledge["objectives"]) if knowledge else [],
            "priorKnowledge": deepcopy(knowledge["priorKnowledge"]) if knowledge else [],
            "excludedTopics": deepcopy(knowledge["excludedTopics"]) if knowledge else [],
            "originalContent": content,
            "contentStatus": "reuse_original_content_only" if content else "requires_authoring",
            "blockers": blockers, "status": "blocked" if blockers else "planned_unexecuted",
            "executionReady": False, "providerDispatched": False, "published": False,
            "verification": {"narration": "not_checked", "pictures": "not_checked",
                             "interaction": "not_checked", "gradeAlignment": "not_checked",
                             "openmaicRuntime": "not_checked", "publication": "not_checked"}}


def quality_policy_reference(path=QUALITY_POLICY_PATH):
    if not path.exists():
        return {"path": "content/textbook_courseware_quality.v1.json", "status": "missing", "policySha256": None}
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = digest({key: field for key, field in value.items() if key != "policySha256"})
    if (value.get("schemaVersion") != "mira.textbook.courseware-quality-policy.v1"
            or value.get("policySha256") != expected):
        raise ValueError("Courseware quality policy schema or immutable hash is invalid")
    return {"path": "content/textbook_courseware_quality.v1.json", "status": value.get("status"),
            "policySha256": expected, "fileContentSha256": digest(value), "runtimeEnforcementVerified": False}


def build_plan(catalog, *, include_superseded=False, superseded_ids=None, quality_policy_path=QUALITY_POLICY_PATH):
    rows, file_count = load_manifests(catalog)
    quality = quality_policy_reference(Path(quality_policy_path))
    excluded_resources = set(superseded_resources() if superseded_ids is None else superseded_ids)
    groups = defaultdict(list)
    for row in rows:
        groups[row["manifest"]["editionId"]].append(row)
    selected, excluded = [], []
    for edition in sorted(groups):
        options = sorted(groups[edition], key=revision_rank, reverse=True)
        if not include_superseded and options[0]["manifest"]["source"]["resourceId"] in excluded_resources:
            excluded.append({"editionId": edition, "resourceId": options[0]["manifest"]["source"]["resourceId"],
                             "revisionCount": len(options), "reason": "superseded_resource"})
            continue
        selected.append((options[0], options))

    tasks, books, subject_counts = [], [], {}
    for row, options in selected:
        value = row["manifest"]
        tasks.append(_task(row, "book_exploration", quality=quality, introduction=value.get("introduction")))
        for unit in value["units"]:
            tasks.append(_task(row, "unit_guide", quality=quality, unit=unit, introduction=unit.get("introduction")))
            for lesson in unit["lessons"]:
                tasks.append(_task(row, "lesson_courseware", quality=quality, unit=unit, lesson=lesson))
        books.append({**book_identity(value), **_revision_summary(row),
                      "selectionBasis": "most_complete_offline",
                      "runtimeOrParentSelectionVerified": False,
                      "multipleAvailableRevisions": len(options) > 1,
                      "alternatives": [_revision_summary(option) for option in options[1:]]})
    for subject in SUBJECTS:
        subject_books = [book for book in books if book["subject"] == subject]
        subject_tasks = [task for task in tasks if task["scope"]["subject"] == subject]
        subject_counts[subject] = {
            "bookCount": len(subject_books),
            "withDirectoryCount": sum(book["unitCount"] > 0 for book in subject_books),
            "directoryMissingCount": sum(book["coverage"]["status"] == "index_only" for book in subject_books),
            "directoryPartialCount": sum(book["coverage"]["status"] == "partial" for book in subject_books),
            "unitCount": sum(book["unitCount"] for book in subject_books),
            "knownDirectoryLessonNodes": sum(book["knownDirectoryLessonNodes"] for book in subject_books),
            "explorationContentCount": sum(book["hasExplorationContent"] for book in subject_books),
            "unitGuideContentCount": sum(book["unitGuideContentCount"] for book in subject_books),
            "explorationAuthoringGapCount": sum(not book["hasExplorationContent"] for book in subject_books),
            "unitGuideAuthoringGapCount": sum(book["unitCount"] - book["unitGuideContentCount"] for book in subject_books),
            "taskCount": len(subject_tasks),
        }
    batches = []
    for grade in (f"primary_{number}" for number in range(1, 7)):
        for subject in SUBJECTS:
            batch_books = [book for book in books if (book["gradeCode"], book["subject"]) == (grade, subject)]
            batch_tasks = [task for task in tasks if (task["scope"]["gradeCode"], task["scope"]["subject"]) == (grade, subject)]
            batches.append({"batchId": grade + "-" + subject, "gradeCode": grade, "subject": subject,
                            "bookCount": len(batch_books), "taskCount": len(batch_tasks),
                            "directoryMissingCount": sum(book["coverage"]["status"] == "index_only" for book in batch_books),
                            "directoryPartialCount": sum(book["coverage"]["status"] == "partial" for book in batch_books),
                            "knownDirectoryLessonNodes": sum(book["knownDirectoryLessonNodes"] for book in batch_books),
                            "executionReady": False, "published": False})
    summary = {
        "schemaVersion": PLAN_SCHEMA, "selectionBasis": "most_complete_offline",
        "selectionOrder": ["coverage_complete_partial_index_only", "unit_count", "lesson_node_count",
                           "exploration_content", "unit_guide_content_count", "revision_id_lexicographic"],
        "runtimeOrParentSelectionVerified": False, "nationalCatalogCompletenessVerified": False,
        "fullScopeEnumerated": all(subject_counts[subject]["bookCount"] for subject in SUBJECTS)
                               and all(book["coverage"]["status"] == "complete" for book in books),
        "qualityPolicyRef": quality,
        "executionReady": False, "providerDispatched": False, "databaseTouched": False, "published": False,
        "limitations": ["Offline authoring backlog only; no courseware or media was generated.",
                        "Directory leaf nodes are not necessarily equal to textbook teaching periods.",
                        "No saved parent choice, database import order or published course was inspected.",
                        "Missing directories have unknown unit and lesson counts; totals are lower bounds.",
                        "Original exploration/guide text reuse does not verify narration, visuals, QA or publication."],
        "scope": {"requestedSubjects": list(SUBJECTS), "catalogSubjectCodes": list(SUBJECTS)},
        "counts": {"manifestFileCount": file_count, "uniqueRevisionCount": len(rows),
                   "identicalDuplicateFileCount": file_count - len(rows), "allBookIdentityCount": len(groups),
                   "excludedSupersededBookCount": len(excluded),
                   "excludedSupersededRevisionCount": sum(book["revisionCount"] for book in excluded),
                   "activeBookCount": len(books), "unitCount": sum(book["unitCount"] for book in books),
                   "knownDirectoryLessonNodes": sum(book["knownDirectoryLessonNodes"] for book in books),
                   "activeRightsReviewCounts": dict(Counter(row["manifest"]["rightsReview"]["status"] for row, _ in selected)),
                   "activeLessonBriefStatusCounts": dict(Counter(node["brief"]["status"]
                       for row, _ in selected for unit in row["manifest"]["units"] for node in unit["lessons"])),
                   "taskCount": len(tasks), "taskKindCounts": dict(Counter(task["kind"] for task in tasks)),
                   "blockedTaskCount": sum(bool(task["blockers"]) for task in tasks),
                   "reusableOriginalContentTaskCount": sum(task["originalContent"] is not None for task in tasks),
                   "executionReadyTaskCount": 0, "publishedTaskCount": 0},
        "bySubject": subject_counts, "deliveryBatches": batches, "excludedBooks": excluded, "books": books,
    }
    summary["tasksSha256"] = digest(tasks)
    summary["planSha256"] = digest(summary)
    return summary, tasks


def write_plan(output, summary, tasks):
    """Create immutable artifacts; identical reruns recover without rewriting."""
    output = Path(output)
    documents = {"summary.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                 "tasks.jsonl": "".join(canonical(task) + "\n" for task in tasks)}
    # Check both before creating either to avoid partial output on known conflicts.
    for name, content in documents.items():
        path = output / name
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Refusing to overwrite different batch plan: {path}")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in documents.items():
        path = output / name
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != content:
                raise ValueError(f"Concurrent batch plan conflict: {path}")
    return {name: str((output / name).resolve()) for name in documents}
