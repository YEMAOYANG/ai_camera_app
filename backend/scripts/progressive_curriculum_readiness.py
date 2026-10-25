"""Read-only inventory and personal-path checks; never boot the application.

Counts are evidence checks against this checkout and database, not deployment
certification. No provider, worker, migrator or generation service is started.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "mira.learning.progressive-readiness.v1"
# The PostgreSQL baseline carries the former MySQL migrations 080 and 081.
REQUIRED_MIGRATIONS = (
    "100_postgres_baseline_schema.sql",
    "101_postgres_baseline_seed.sql",
    "102_postgres_baseline_foreign_keys.sql",
    "103_mysql_compat_functions.sql",
)
REQUIRED_TABLES = (
    "schema_migrations", "learning_progressive_course_bindings",
    "learning_progressive_evidence", "learning_progressive_lesson_progress",
    "learning_placement_attempts", "learning_placement_questions",
    "learning_courses", "learning_course_generation_jobs",
    "learning_course_generation_candidates", "learning_catalog_build_jobs",
    "learning_catalog_build_items", "learning_catalog_releases",
    "learning_catalog_release_items", "learning_curriculum_preparation_plans",
    "learning_curriculum_classroom_item_receipts",
    "learning_course_lesson_package_bindings", "learning_lesson_packages",
    "learning_lesson_package_assets", "learning_media_assets",
    "learning_media_asset_variants", "learning_media_quality_reviews",
    "learning_openmaic_runtime_classrooms", "learning_formal_qwen_audio_jobs",
    "learning_openmaic_provider_readiness_jobs",
)
CHILD_TABLES = (
    "children", "tasks", "learning_sessions",
    "learning_curriculum_grade_release_pointers",
    "learning_curriculum_grade_release_history",
)


class CheckTimeout(Exception):
    pass


class ReadOnlyConnection:
    """Also reject mutations at the caller boundary, before reaching MySQL."""

    def __init__(self, connection, deadline):
        self.connection = connection
        self.deadline = deadline

    def execute(self, sql, params=()):
        if time.monotonic() >= self.deadline:
            raise CheckTimeout()
        if sql.lstrip().split(None, 1)[0].upper() not in {"SELECT", "WITH"}:
            raise PermissionError("readiness checks accept reads only")
        return self.connection.execute(sql, params)


def _block(report, code, action):
    if not any(item["code"] == code for item in report["blockers"]):
        report["blockers"].append({"code": code, "action": action})


def _schema_check(conn, report, *, child_scope):
    existing = {str(row["table_name"]) for row in conn.execute(
        "SELECT TABLE_NAME AS table_name FROM information_schema.tables "
        "WHERE TABLE_SCHEMA = current_schema()"
    ).fetchall()}
    required = set(REQUIRED_TABLES) | (set(CHILD_TABLES) if child_scope else set())
    missing = sorted(required - existing)
    applied = ({row["version"] for row in conn.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()} if "schema_migrations" in existing else set())
    missing_sources = [name for name in REQUIRED_MIGRATIONS
                       if not (ROOT / "migrations" / name).is_file()]
    pending = [name for name in REQUIRED_MIGRATIONS if name not in applied]
    report["database"] = {
        "status": "blocked" if missing or pending or missing_sources else "schema_checked",
        "readOnly": True, "requiredMigrations": list(REQUIRED_MIGRATIONS),
        "pendingMigrations": pending, "missingMigrationSources": missing_sources,
        "missingRequiredTables": missing,
    }
    if pending:
        _block(report, "pending_migrations", "Review and apply the existing migrator with an authorized migration account, then rerun this check.")
    if missing_sources:
        _block(report, "migration_source_missing", "Deploy the complete migration sources before running the migrator.")
    if missing:
        _block(report, "required_tables_missing", "Resolve the listed missing tables through the versioned migrations; do not mark migrations applied manually.")
    return not (missing or pending or missing_sources)


def _inventory(conn, database, report, args):
    from content.progressive_curriculum import CURRICULUM_VERSION
    from repositories.course_supply_inventory import published_supply
    from repositories.progressive_learning_repository import ProgressiveLearningRepository
    from services.learning_curriculum_preparation_contract import (
        canonical_preparation_target_for, preparation_target_fingerprint,
    )
    from services.progressive_course_generation import validate_progressive_course_for_release
    from services.progressive_learning_service import ProgressiveLearningService

    service = ProgressiveLearningService(ProgressiveLearningRepository(database))
    scope, params = "course.curriculum_version = ? AND course.retired_at IS NULL", [CURRICULUM_VERSION]
    for field, value in (("grade_code", args.grade), ("subject", args.subject)):
        if value:
            scope += f" AND course.{field} = ?"
            params.append(value)
    declared = int(conn.execute(
        f"SELECT COUNT(*) AS total FROM learning_courses AS course WHERE {scope}", params,
    ).fetchone()["total"])
    bound_from = (
        "FROM learning_courses AS course JOIN learning_progressive_course_bindings AS binding "
        "ON binding.course_id = course.id AND binding.course_version = course.version "
        "AND binding.retired_at IS NULL AND binding.curriculum_version = course.curriculum_version "
        f"WHERE {scope}"
    )
    candidate_count = int(conn.execute(f"SELECT COUNT(*) AS total {bound_from}", params).fetchone()["total"])
    candidates = conn.execute(
        f"SELECT course.* {bound_from} ORDER BY course.id, course.version LIMIT ?",
        (*params, args.max_courses),
    ).fetchall()
    inventory = report["inventory"] = {
        "status": "checking", "complete": False, "countsAreLowerBounds": True,
        "declaredCoursewareCount": declared, "boundCandidateCount": candidate_count,
        "checkedCandidateCount": 0, "verifiedContentAndBindingCoursewareCount": 0,
        "rejectedContentOrBindingCount": 0, "formallyReadyCoursewareCount": 0,
        "readyLessonCount": 0, "distinctAssessmentSets": 0,
        "countSemantics": "Unique course versions selected as reusable supply by the existing exact-target publication resolver; assessment sets are distinct within each lesson.",
        "formalTargetsChecked": 0, "formalTargetsNotChecked": 0, "byGradeSubject": [],
        "evidence": ["current_registry_and_content_binding", "fresh_host_acceptance_receipt",
                     "exact_formal_publication", "current_runtime_contract", "tts_and_asr", "required_media_assets"],
    }
    valid = {}
    for course in candidates:
        try:
            binding = service.binding_for_course(conn, course=course)
            if binding is None:
                raise ValueError("binding missing")
            validate_progressive_course_for_release(conn, course=course, expected_lesson_id=binding["lesson_id"])
        except (ValueError, KeyError, TypeError):
            inventory["rejectedContentOrBindingCount"] += 1
        except Exception as error:
            from core.errors import ApiError
            if not isinstance(error, ApiError):
                raise
            inventory["rejectedContentOrBindingCount"] += 1
        else:
            valid[(str(course["id"]), str(course["version"]))] = (course, binding)
        inventory["checkedCandidateCount"] += 1
    inventory["verifiedContentAndBindingCoursewareCount"] = len(valid)

    # Resolve only targets referenced by the bounded, verified candidates. Never
    # construct a new target or infer publication from the generated row status.
    targets = {}
    malformed_targets = 0
    for course_id, course_version in valid:
        for row in conn.execute(
            "SELECT DISTINCT build.target_spec_json FROM learning_catalog_build_items AS item "
            "JOIN learning_catalog_build_jobs AS build ON build.id = item.build_job_id "
            "WHERE item.course_id = ? AND item.course_version = ?",
            (course_id, course_version),
        ).fetchall():
            try:
                raw = row["target_spec_json"]
                raw = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(raw, dict) or raw.get("curriculumVersion") != CURRICULUM_VERSION:
                    raise ValueError("wrong target version")
                target = canonical_preparation_target_for(raw)
                if target != raw:
                    raise ValueError("frozen target no longer matches the current contract")
                targets[preparation_target_fingerprint(target)] = target
            except (ValueError, KeyError, TypeError):
                malformed_targets += 1
    ready = set()
    target_items = sorted(targets.items())
    for _, target in target_items[:args.max_targets]:
        for row in published_supply(conn, target).values():
            key = (str(row["course_id"]), str(row["course_version"]))
            if key in valid:
                ready.add(key)
        inventory["formalTargetsChecked"] += 1
    inventory["formalTargetsNotChecked"] = max(0, len(targets) - args.max_targets)
    groups = {}
    lesson_ids, assessment_sets = set(), set()
    for key in ready:
        course, binding = valid[key]
        lesson_id, set_id = binding["lesson_id"], binding["assessment_set_id"]
        lesson_ids.add(lesson_id)
        assessment_sets.add((lesson_id, set_id))
        group = groups.setdefault((course["grade_code"], course["subject"]),
                                  {"courses": set(), "lessons": set(), "sets": set()})
        group["courses"].add(key)
        group["lessons"].add(lesson_id)
        group["sets"].add((lesson_id, set_id))
    complete = candidate_count == len(candidates) and not inventory["formalTargetsNotChecked"]
    inventory.update(
        status="checked" if complete else "partial", complete=complete,
        countsAreLowerBounds=not complete, formallyReadyCoursewareCount=len(ready),
        readyLessonCount=len(lesson_ids), distinctAssessmentSets=len(assessment_sets),
        byGradeSubject=[{"gradeCode": grade, "subject": subject,
                         "coursewareCount": len(group["courses"]), "lessonCount": len(group["lessons"]),
                         "distinctAssessmentSets": len(group["sets"])}
                        for (grade, subject), group in sorted(groups.items())],
    )
    if not complete:
        _block(report, "inventory_check_limited", "Narrow --grade/--subject or increase --max-courses/--max-targets; reported verified counts are lower bounds.")
    if inventory["rejectedContentOrBindingCount"] or malformed_targets:
        _block(report, "course_provenance_invalid", "Review the candidate binding, current registry identity, original host receipt and frozen preparation target; do not relabel legacy courses.")
    if complete and not ready:
        _block(report, "no_formally_ready_courseware", "Complete an explicitly authorized bounded formal course generation and publication, including classroom, audio/ASR and media gates.")
    elif complete and len(ready) < len(valid):
        _block(report, "formal_evidence_missing_or_stale", "Inspect formal publication receipts and current runtime/audio/media readiness for the unpublished or unavailable candidates.")


def _child_path(conn, database, report, args):
    from repositories.progressive_formal_course_repository import progressive_formal_authority
    from repositories.progressive_learning_repository import ProgressiveLearningRepository
    from services.progressive_course_generation import validate_progressive_course_for_release
    from services.progressive_learning_service import ProgressiveLearningService
    child = conn.execute("SELECT * FROM children WHERE id = ? LIMIT 1", (args.child_id,)).fetchone()
    if child is None:
        _block(report, "child_not_found", "Use an existing child ID in the configured database.")
        report["child"] = {"status": "not_found"}
        return
    if child.get("grade_code") not in {f"primary_{number}" for number in range(1, 7)}:
        _block(report, "child_grade_not_primary", "This check supports existing primary 1–6 learning profiles.")
        report["child"] = {"status": "unsupported_grade"}
        return
    service = ProgressiveLearningService(ProgressiveLearningRepository(database))
    checked = {}

    def validator(connection, *, child, course):
        key = (str(course["id"]), str(course["version"]))
        if key not in checked:
            try:
                binding = service.binding_for_course(connection, course=course)
                validate_progressive_course_for_release(connection, course=course,
                                                       expected_lesson_id=binding["lesson_id"])
                checked[key] = bool(progressive_formal_authority(
                    connection, database=database, child=child, course=course))
            except (ValueError, KeyError, TypeError):
                checked[key] = False
            except Exception as error:
                from core.errors import ApiError
                if not isinstance(error, ApiError):
                    raise
                checked[key] = False
        return checked[key]

    result = report["child"] = {"status": "checking", "gradeCode": child["grade_code"], "subjects": []}
    for subject in ([args.subject] if args.subject else ["chinese", "math", "english"]):
        path = service.get_path(conn, child=child, subject=subject, course_validator=validator)
        next_lesson = path.get("nextLesson")
        rows = [*path["prerequisites"], *path["currentGradeLessons"]]
        states = Counter(row["status"] for row in rows)
        summary = {"subject": subject, "lessonStatusCounts": dict(states),
                   "prerequisiteAssessmentRequired": path["assessment"]["required"], "nextLesson": None}
        if next_lesson:
            summary["nextLesson"] = {
                "lessonId": next_lesson["lessonId"], "gradeCode": next_lesson["gradeCode"],
                "learningStatus": next_lesson["status"], "canStart": next_lesson["canStart"],
                "assessmentMode": next_lesson["assessmentMode"],
                "coursewareReady": bool(next_lesson.get("courseId")),
                "distinctAssessmentSetsCompleted": next_lesson["distinctAssessmentSets"],
            }
            if not next_lesson.get("courseId"):
                _block(report, "child_next_courseware_unavailable", "Supply the child's next registered lesson or unused assessment set within the child's current grade; never fill the gap with another grade's course.")
        result["subjects"].append(summary)
    result["status"] = "checked"


def _safe_failure(report, error):
    # Never serialize exception text: database errors can contain host names,
    # credentials, SQL, stored content or a child's identity.
    number = error.args[0] if error.args and isinstance(error.args[0], int) else None
    if isinstance(error, CheckTimeout) or number in {1205, 1317, 3024}:
        code, action = "verification_timeout", "Narrow the requested scope or increase --timeout-seconds; unchecked readiness remains unknown."
    elif number in {1054, 1146}:
        code, action = "database_schema_drift", "Compare applied migration records with the actual schema and complete the versioned migration."
    elif number in {1044, 1045, 1142, 1227}:
        code, action = "database_read_access_denied", "Use the configured account with SELECT and information_schema visibility; this command needs no write privileges."
    elif number in {2002, 2003, 2006, 2013}:
        code, action = "database_unavailable", "Check the configured database connection and service, without printing credentials."
    elif isinstance(error, PermissionError) or number == 1792:
        code, action = "read_only_operation_rejected", "A dependency attempted a non-read operation; keep this check read-only and review that dependency."
    else:
        code, action = "readiness_verification_failed", "Check local dependency/configuration compatibility and rerun a narrower scope; no readiness conclusion was reached."
    _block(report, code, action)


def run_readiness(database, args):
    from content.progressive_curriculum import CURRICULUM_VERSION, curriculum_identity
    identity = curriculum_identity()
    report = {
        "schemaVersion": SCHEMA, "checkedAt": datetime.now(timezone.utc).isoformat(),
        "status": "checking", "deploymentReady": None,
        "scope": {"gradeCode": args.grade, "subject": args.subject, "childScoped": bool(args.child_id),
                  "maxCourses": args.max_courses, "maxTargets": args.max_targets,
                  "timeoutSeconds": args.timeout_seconds},
        "catalog": {"curriculumVersion": CURRICULUM_VERSION, "identitySha256": identity["identitySha256"],
                    "lessonCount": identity["lessonCount"], "unitCount": identity["unitCount"],
                    "meaning": "Registered lesson definitions, not generated or published courseware."},
        "database": {"status": "unknown", "readOnly": True},
        "inventory": {"status": "unknown", "formallyReadyCoursewareCount": None,
                      "distinctAssessmentSets": None},
        "child": {"status": "not_requested" if not args.child_id else "unknown"},
        "blockers": [],
        "notChecked": ["deployed_process_source_identity", "service_health", "browser_classroom_walkthrough",
                       "worker_and_paid_call_authorization"],
    }
    connection = None
    try:
        connection = database.connect()
        connection.execute("SET SESSION MAX_EXECUTION_TIME = 5000")
        connection.execute("SET TRANSACTION READ ONLY")
        conn = ReadOnlyConnection(connection, time.monotonic() + args.timeout_seconds)
        if _schema_check(conn, report, child_scope=bool(args.child_id)):
            _inventory(conn, database, report, args)
            if args.child_id:
                _child_path(conn, database, report, args)
    except Exception as error:
        _safe_failure(report, error)
    finally:
        if connection is not None:
            try:
                connection.rollback()
            finally:
                connection.close()
    report["status"] = "blocked" if report["blockers"] else "checked"
    if report["inventory"].get("status") == "checking":
        report["inventory"].update(status="partial", complete=False, countsAreLowerBounds=True)
    if report["child"]["status"] == "checking":
        report["child"]["status"] = "partial"
    return report


def _positive(value):
    parsed = int(value)
    if not 1 <= parsed <= 10000:
        raise argparse.ArgumentTypeError("must be between 1 and 10000")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--grade", choices=[f"primary_{number}" for number in range(1, 7)], help="Limit inventory to this course grade; an optional child's path always stays within their actual current grade.")
    parser.add_argument("--subject", choices=["chinese", "math", "english"], help="Limit inventory and optional personal path to one subject.")
    parser.add_argument("--child-id", help="Read an existing child's real path; never creates placement attempts, tasks or supply jobs.")
    parser.add_argument("--max-courses", type=_positive, default=200, help="Maximum candidate course versions to validate (default: 200).")
    parser.add_argument("--max-targets", type=_positive, default=24, help="Maximum exact formal targets to query (default: 24).")
    parser.add_argument("--timeout-seconds", type=_positive, default=45, help="Read budget after connecting, with a 5-second limit per SELECT (default: 45).")
    args = parser.parse_args(argv)
    try:
        from core.config import AppConfig
        from core.database import Database
        report = run_readiness(Database(AppConfig.from_env().DATABASE_URL), args)
    except Exception as error:
        report = {"schemaVersion": SCHEMA, "status": "blocked", "deploymentReady": None,
                  "inventory": {"status": "unknown", "formallyReadyCoursewareCount": None}, "blockers": []}
        _safe_failure(report, error)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
