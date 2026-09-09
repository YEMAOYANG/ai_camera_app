from __future__ import annotations

import base64
import json
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow
from repositories.formal_student_runtime_gate import (
    current_formal_runtime_sql,
    current_formal_validation_authority_sql,
)
from repositories.learning_repository import (
    _student_required_package_assets_sql,
    _student_visible_course_sql,
)


_SUBJECT_LABELS = {"chinese": "语文", "math": "数学", "english": "英语"}
_BUCKETS = {"all", "continue", "makeup", "completed", "favorites"}


def _classroom_availability_sql(*, require_full_runtime: bool) -> str:
    """Return a fail-closed, release-scoped classroom availability check.

    A historical course/package binding is not sufficient.  Student delivery
    requires the exact package approved in the active catalog release, with
    every required asset passing the same gates used by catalog activation.
    The full-classroom flag accepts either the legacy reviewed Runtime path or
    the exact formal grade pointer plus 057/058/059 machine evidence.  Formal
    publication never falls back to a human-review/sample flag. Newly assigned
    tasks also accept the exact currently visible child-plan publication before
    their first session binding exists.
    """

    legacy_runtime_gate = (
        """
                    AND runtime.id IS NOT NULL
                    AND runtime.status = 'ready'
                    AND runtime.quality_status = 'approved'
                    AND runtime.upstream_classroom_id IS NOT NULL
                    AND runtime.retired_at IS NULL
        """
        if require_full_runtime
        else ""
    )
    return f"""
            (
              EXISTS (
                SELECT 1
                FROM learning_catalog_release_items AS release_item
                JOIN learning_catalog_releases AS catalog_release
                  ON catalog_release.id = release_item.release_id
                JOIN learning_course_lesson_package_bindings AS binding
                  ON binding.course_id = release_item.course_id
                 AND binding.course_version = release_item.course_version
                 AND binding.package_id = release_item.package_id
                 AND binding.package_version = release_item.package_version
                JOIN learning_lesson_packages AS package
                  ON package.id = binding.package_id
                 AND package.version = binding.package_version
                LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
                  ON runtime.package_id = package.id
                 AND runtime.package_version = package.version
                 AND runtime.course_id = release_item.course_id
                 AND runtime.course_version = release_item.course_version
                 AND runtime.retired_at IS NULL
                LEFT JOIN learning_student_formal_session_bindings
                  AS session_binding
                  ON session_binding.learning_session_id = session.id
                 AND session_binding.family_id = task.family_id
                 AND session_binding.child_id = task.child_id
                 AND session_binding.release_id = catalog_release.id
                 AND session_binding.grade_code = release_item.grade_code
                 AND session_binding.course_id = release_item.course_id
                 AND session_binding.course_version =
                   release_item.course_version
                 AND session_binding.package_id = release_item.package_id
                 AND session_binding.package_version =
                   release_item.package_version
                 AND session_binding.runtime_classroom_id = runtime.id
                LEFT JOIN learning_curriculum_grade_release_pointers
                  AS grade_pointer
                  ON grade_pointer.grade_code = release_item.grade_code
                 AND grade_pointer.release_id = catalog_release.id
                 AND grade_pointer.pointer_revision >= 1
                LEFT JOIN learning_curriculum_classroom_item_receipts
                  AS formal_receipt
                  ON formal_receipt.build_item_id =
                    runtime.candidate_build_item_id
                 AND formal_receipt.runtime_classroom_id = runtime.id
                 AND formal_receipt.release_id = catalog_release.id
                 AND formal_receipt.grade_code = release_item.grade_code
                 AND formal_receipt.course_id = release_item.course_id
                 AND formal_receipt.course_version = release_item.course_version
                 AND formal_receipt.package_id = release_item.package_id
                 AND formal_receipt.package_version = release_item.package_version
                LEFT JOIN learning_formal_qwen_audio_jobs AS formal_audio
                  ON formal_audio.build_item_id = formal_receipt.build_item_id
                 AND formal_audio.runtime_classroom_id = runtime.id
                 AND formal_audio.release_id = catalog_release.id
                 AND formal_audio.target_fingerprint =
                   COALESCE(
                     session_binding.target_fingerprint,
                     grade_pointer.target_fingerprint
                   )
                LEFT JOIN learning_openmaic_provider_readiness_jobs
                  AS formal_provider
                  ON formal_provider.release_id = catalog_release.id
                 AND formal_provider.grade_code = release_item.grade_code
                 AND formal_provider.target_fingerprint =
                   COALESCE(
                     session_binding.target_fingerprint,
                     grade_pointer.target_fingerprint
                   )
                WHERE release_item.course_id = course.id
                  AND release_item.course_version = course.version
                  AND course.status = 'published'
                  AND course.quality_status = 'released'
                  AND course.retired_at IS NULL
                  AND release_item.status = 'published'
                  AND release_item.quality_status = 'ready'
                  AND release_item.retired_at IS NULL
                  AND release_item.curriculum_version = course.curriculum_version
                  AND release_item.boundary_version = course.boundary_version
                  AND catalog_release.curriculum_version = course.curriculum_version
                  AND catalog_release.retired_at IS NULL
                  AND (
                    (
                      catalog_release.status = 'active'
                      AND catalog_release.quality_status = 'ready'
                      {legacy_runtime_gate}
                    )
                    OR (
                      (
                        (
                          grade_pointer.target_fingerprint IS NOT NULL
                          AND grade_pointer.contract_version =
                            'mira.learning.formal-publication.v1'
                        )
                        OR (
                          session.id IS NOT NULL
                          AND session.status <> 'completed'
                          AND session_binding.learning_session_id = session.id
                          AND session_binding.release_id = catalog_release.id
                          AND session_binding.runtime_classroom_id = runtime.id
                          AND session_binding.publication_contract_version =
                            'mira.learning.formal-publication.v1'
                        )
                      )
                      AND runtime.id IS NOT NULL
                      AND runtime.status = 'ready'
                      AND runtime.upstream_classroom_id IS NOT NULL
                      AND runtime.candidate_release_id = catalog_release.id
                      AND runtime.candidate_grade_code = release_item.grade_code
                      AND runtime.candidate_target_fingerprint =
                        COALESCE(
                          session_binding.target_fingerprint,
                          grade_pointer.target_fingerprint
                        )
                      {current_formal_runtime_sql(runtime_alias="runtime")}
                      AND formal_receipt.target_fingerprint =
                        COALESCE(
                          session_binding.target_fingerprint,
                          grade_pointer.target_fingerprint
                        )
                      AND formal_receipt.classroom_status = 'passed'
                      AND formal_receipt.tts_status = 'passed'
                      AND formal_receipt.asr_roundtrip_status = 'passed'
                      AND formal_receipt.conversation_provider_status = 'passed'
                      AND formal_receipt.auto_validated = 1
                      AND formal_receipt.publication_status = 'published'
                      AND formal_audio.state = 'auto_validated'
                      AND formal_audio.grade_code = release_item.grade_code
                      AND formal_audio.course_id = release_item.course_id
                      AND formal_audio.course_version =
                        release_item.course_version
                      AND formal_audio.package_id = release_item.package_id
                      AND formal_audio.package_version =
                        release_item.package_version
                      AND formal_audio.expected_segment_count BETWEEN 1 AND 240
                      AND formal_audio.tts_attempted_count = formal_audio.expected_segment_count
                      AND formal_audio.tts_completed_count = formal_audio.expected_segment_count
                      AND formal_audio.audio_validated_count = formal_audio.expected_segment_count
                      AND formal_audio.asr_attempted_count = formal_audio.expected_segment_count
                      AND formal_audio.asr_passed_count = formal_audio.expected_segment_count
                      AND formal_audio.terminal_receipt_hash IS NOT NULL
                      {current_formal_validation_authority_sql(
                          receipt_alias="formal_receipt",
                          provider_alias="formal_provider",
                      )}
                    )
                  )
                  AND package.status = 'published'
                  AND package.retired_at IS NULL
                  AND {_student_required_package_assets_sql(package_alias="package")}
              )
              OR EXISTS (
                SELECT 1
                FROM children AS availability_child
                WHERE session.id IS NULL
                  AND availability_child.family_id = task.family_id
                  AND availability_child.id = task.child_id
                  AND availability_child.grade_code = course.grade_code
                  AND availability_child.grade_selection_revision >= 1
                  AND course.status = 'published'
                  AND course.quality_status = 'released'
                  AND course.content_origin = 'openmaic_generated'
                  AND course.retired_at IS NULL
                  AND {_student_visible_course_sql(
                      course_alias="course",
                      child_alias="availability_child",
                      require_available_package_assets=True,
                  )}
              )
            )
    """


_PACKAGE_CLASSROOM_AVAILABILITY_SQL = _classroom_availability_sql(
    require_full_runtime=False
)
_FULL_CLASSROOM_AVAILABILITY_SQL = _classroom_availability_sql(
    require_full_runtime=True
)


class StudentLearningLibraryRepository:
    """Read-only learning history plus an explicit student favorite marker.

    Assigned tasks, sessions, reports, and published courses remain the source
    of truth. This repository deliberately never materializes a missing daily
    task while a student browses history.
    """

    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def list_library(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        bucket: str,
        subject: str | None,
        before_date: str,
        cursor: tuple[int, str] | None,
        limit: int,
    ) -> tuple[list[dict], str | None]:
        if bucket not in _BUCKETS:
            raise ValueError("unsupported library bucket")
        params: list[object] = [family_id, child_id]
        conditions = [
            "task.family_id = ?",
            "task.child_id = ?",
            "task.type = 'learning'",
            "task.learning_course_id IS NOT NULL",
            "task.status <> 'cancelled'",
        ]
        if subject:
            conditions.append("course.subject = ?")
            params.append(subject)
        if bucket == "continue":
            conditions.extend(
                (
                    "session.id IS NOT NULL",
                    "session.status <> 'completed'",
                )
            )
        elif bucket == "makeup":
            conditions.extend(
                (
                    "task.scheduled_date < ?",
                    "task.status NOT IN ("
                    "'completed', 'confirmed', 'awaiting_parent_confirmation', "
                    "'rejected', 'expired'"
                    ")",
                    "(session.id IS NULL OR session.status <> 'completed')",
                    "report.id IS NULL",
                    "NOT EXISTS ("
                    "SELECT 1 FROM task_events AS acknowledged "
                    "WHERE acknowledged.task_id = task.id "
                    "AND acknowledged.event_type = 'missed_acknowledged'"
                    ")",
                    "NOT EXISTS ("
                    "SELECT 1 FROM learning_task_carryovers AS current_carryover "
                    "WHERE current_carryover.source_task_id = task.id "
                    "AND current_carryover.target_date = ?"
                    ")",
                )
            )
            params.extend((before_date, before_date))
        elif bucket == "completed":
            conditions.append("session.status = 'completed'")
        elif bucket == "favorites":
            conditions.append("favorite.course_id IS NOT NULL")
        if bucket in {"all", "continue", "makeup"}:
            conditions.append(
                "NOT EXISTS ("
                "SELECT 1 FROM tasks AS newer_task "
                "JOIN learning_courses AS newer_course "
                "ON newer_course.id = newer_task.learning_course_id "
                "AND newer_course.version = newer_task.learning_course_version "
                "WHERE newer_task.family_id = task.family_id "
                "AND newer_task.child_id = task.child_id "
                "AND newer_task.type = 'learning' "
                "AND newer_task.learning_course_id IS NOT NULL "
                "AND newer_task.status NOT IN ('cancelled', 'rejected', 'expired') "
                "AND newer_course.grade_code = course.grade_code "
                "AND newer_course.subject = course.subject "
                "AND newer_course.node_code = course.node_code "
                "AND COALESCE(newer_course.curriculum_version, '') = "
                "COALESCE(course.curriculum_version, '') "
                "AND (newer_task.scheduled_date > task.scheduled_date "
                "OR (newer_task.scheduled_date = task.scheduled_date "
                "AND newer_task.created_at > task.created_at) "
                "OR (newer_task.scheduled_date = task.scheduled_date "
                "AND newer_task.created_at = task.created_at "
                "AND newer_task.id > task.id))"
                ")"
            )
        if cursor is not None:
            conditions.append(
                "(COALESCE(session.updated_at, task.updated_at) < ? "
                "OR (COALESCE(session.updated_at, task.updated_at) = ? "
                "AND task.id < ?))"
            )
            params.extend((cursor[0], cursor[0], cursor[1]))
        params.append(limit + 1)
        rows = conn.execute(
            f"""
            SELECT
              task.id AS task_id,
              task.status AS task_status,
              task.scheduled_date,
              task.scheduled_start,
              task.learning_slot,
              task.updated_at AS task_updated_at,
              course.id AS course_id,
              course.version AS course_version,
              course.grade_code,
              course.subject,
              course.node_code,
              course.title,
              course.objective,
              course.content_json,
              session.id AS session_id,
              session.status AS session_status,
              session.current_question_index,
              session.correct_count,
              session.attempted_count,
              session.started_at,
              session.completed_at AS session_completed_at,
              session.updated_at AS session_updated_at,
              report.id AS report_id,
              report.score AS report_score,
              report.mastery_level AS report_mastery_level,
              report.summary AS report_summary,
              report.next_step AS report_next_step,
              report.created_at AS report_created_at,
              favorite.course_id AS favorite_course_id,
              {_PACKAGE_CLASSROOM_AVAILABILITY_SQL}
                AS package_classroom_available,
              {_FULL_CLASSROOM_AVAILABILITY_SQL}
                AS full_classroom_available
            FROM tasks AS task
            JOIN learning_courses AS course
              ON course.id = task.learning_course_id
             AND course.version = task.learning_course_version
            LEFT JOIN learning_sessions AS session
              ON session.family_id = task.family_id
             AND session.task_id = task.id
            LEFT JOIN learning_reports AS report
              ON report.family_id = task.family_id
             AND report.session_id = session.id
            LEFT JOIN student_learning_course_favorites AS favorite
              ON favorite.family_id = task.family_id
             AND favorite.child_id = task.child_id
             AND favorite.course_id = course.id
             AND favorite.course_version = course.version
            WHERE {' AND '.join(conditions)}
            ORDER BY COALESCE(session.updated_at, task.updated_at) DESC,
              task.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [self._item_payload(row) for row in page]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = self.encode_cursor(
                int(last.get("session_updated_at") or last["task_updated_at"]),
                str(last["task_id"]),
            )
        return items, next_cursor

    def get_continue_item(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
    ) -> dict | None:
        items, _ = self.list_library(
            conn,
            family_id=family_id,
            child_id=child_id,
            bucket="continue",
            subject=None,
            before_date="9999-12-31",
            cursor=None,
            limit=1,
        )
        return items[0] if items else None

    def get_course_detail(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        course_id: str,
        course_version: str | None,
    ) -> dict | None:
        params: list[object] = [family_id, child_id, course_id]
        version_sql = ""
        if course_version:
            version_sql = " AND course.version = ?"
            params.append(course_version)
        row = conn.execute(
            f"""
            SELECT
              task.id AS task_id,
              task.status AS task_status,
              task.scheduled_date,
              task.scheduled_start,
              task.learning_slot,
              task.updated_at AS task_updated_at,
              course.id AS course_id,
              course.version AS course_version,
              course.grade_code,
              course.subject,
              course.node_code,
              course.title,
              course.objective,
              course.content_json,
              session.id AS session_id,
              session.status AS session_status,
              session.current_question_index,
              session.correct_count,
              session.attempted_count,
              session.started_at,
              session.completed_at AS session_completed_at,
              session.updated_at AS session_updated_at,
              report.id AS report_id,
              report.score AS report_score,
              report.mastery_level AS report_mastery_level,
              report.summary AS report_summary,
              report.next_step AS report_next_step,
              report.created_at AS report_created_at,
              favorite.course_id AS favorite_course_id,
              {_PACKAGE_CLASSROOM_AVAILABILITY_SQL}
                AS package_classroom_available,
              {_FULL_CLASSROOM_AVAILABILITY_SQL}
                AS full_classroom_available
            FROM tasks AS task
            JOIN learning_courses AS course
              ON course.id = task.learning_course_id
             AND course.version = task.learning_course_version
            LEFT JOIN learning_sessions AS session
              ON session.family_id = task.family_id
             AND session.task_id = task.id
            LEFT JOIN learning_reports AS report
              ON report.family_id = task.family_id
             AND report.session_id = session.id
            LEFT JOIN student_learning_course_favorites AS favorite
              ON favorite.family_id = task.family_id
             AND favorite.child_id = task.child_id
             AND favorite.course_id = course.id
             AND favorite.course_version = course.version
            WHERE task.family_id = ? AND task.child_id = ?
              AND task.type = 'learning'
              AND course.id = ?
              {version_sql}
            ORDER BY COALESCE(session.updated_at, task.updated_at) DESC,
              task.id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        return self._item_payload(row, include_intro=True) if row is not None else None

    def set_favorite(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        course_id: str,
        course_version: str,
        favorite: bool,
        now: int,
        allow_unassigned: bool = False,
    ) -> bool:
        if not allow_unassigned:
            assigned = conn.execute(
                """
                SELECT 1
                FROM tasks
                WHERE family_id = ? AND child_id = ? AND type = 'learning'
                  AND learning_course_id = ? AND learning_course_version = ?
                LIMIT 1
                """,
                (family_id, child_id, course_id, course_version),
            ).fetchone()
            if assigned is None:
                return False
        if favorite:
            conn.execute(
                """
                INSERT INTO student_learning_course_favorites(
                  family_id, child_id, course_id, course_version,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE updated_at = VALUES(updated_at)
                """,
                (family_id, child_id, course_id, course_version, now, now),
            )
        else:
            conn.execute(
                """
                DELETE FROM student_learning_course_favorites
                WHERE family_id = ? AND child_id = ?
                  AND course_id = ? AND course_version = ?
                """,
                (family_id, child_id, course_id, course_version),
            )
        return True

    @staticmethod
    def encode_cursor(updated_at: int, task_id: str) -> str:
        raw = json.dumps([updated_at, task_id], separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def decode_cursor(value: str | None) -> tuple[int, str] | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            padding = "=" * (-len(text) % 4)
            decoded = json.loads(
                base64.urlsafe_b64decode(text + padding).decode("utf-8")
            )
            if (
                not isinstance(decoded, list)
                or len(decoded) != 2
                or not isinstance(decoded[0], int)
                or decoded[0] < 0
                or not isinstance(decoded[1], str)
                or not decoded[1]
            ):
                raise ValueError
            return decoded[0], decoded[1]
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid library cursor") from exc

    @classmethod
    def _item_payload(
        cls,
        row: DatabaseRow,
        *,
        include_intro: bool = False,
    ) -> dict:
        content = cls._parse_json(row.get("content_json"), {})
        questions = content.get("questions") if isinstance(content, dict) else []
        flow = content.get("teachingFlow") if isinstance(content, dict) else None
        question_count = len(questions) if isinstance(questions, list) else 0
        if isinstance(flow, dict):
            guided = flow.get("guidedQuestionIds")
            independent = flow.get("independentQuestionIds")
            if isinstance(guided, list) and isinstance(independent, list):
                question_count = len(guided) + len(independent)
        subject = str(row["subject"])
        session = None
        if row.get("session_id"):
            session = {
                "id": row["session_id"],
                "status": row["session_status"],
                "currentQuestionIndex": int(row.get("current_question_index") or 0),
                "correctCount": int(row.get("correct_count") or 0),
                "attemptedCount": int(row.get("attempted_count") or 0),
                "startedAt": row.get("started_at"),
                "completedAt": row.get("session_completed_at"),
                "updatedAt": row.get("session_updated_at"),
            }
        report = None
        if row.get("report_id"):
            report = {
                "id": row["report_id"],
                "score": int(row.get("report_score") or 0),
                "masteryLevel": row.get("report_mastery_level"),
                "summary": row.get("report_summary"),
                "nextStep": row.get("report_next_step"),
                "createdAt": row.get("report_created_at"),
            }
        course = {
            "id": row["course_id"],
            "version": row["course_version"],
            "gradeCode": row["grade_code"],
            "subject": subject,
            "subjectLabel": _SUBJECT_LABELS.get(subject, subject),
            "nodeCode": row["node_code"],
            "title": row["title"],
            "objective": row["objective"],
            "estimatedMinutes": int(content.get("estimatedMinutes") or 10),
            "questionCount": question_count,
        }
        if include_intro:
            course["intro"] = str(content.get("intro") or "")
        return {
            "taskId": row["task_id"],
            "taskStatus": row["task_status"],
            "learningDate": row["scheduled_date"],
            "scheduledStart": row.get("scheduled_start"),
            "slot": str(row.get("learning_slot") or "core"),
            "course": course,
            "session": session,
            "report": report,
            "favorite": row.get("favorite_course_id") is not None,
            # ``classroomAvailable`` remains the backwards-compatible package
            # gate.  New clients can distinguish the controlled package player
            # from the reviewed full OpenMAIC classroom explicitly.
            "classroomAvailable": bool(row.get("package_classroom_available")),
            "packageClassroomAvailable": bool(
                row.get("package_classroom_available")
            ),
            "fullClassroomAvailable": bool(row.get("full_classroom_available")),
            "lastActivityAt": int(
                row.get("session_updated_at") or row["task_updated_at"]
            ),
        }

    @staticmethod
    def _parse_json(value: object, fallback: object) -> object:
        if isinstance(value, (dict, list)):
            return value
        if not value:
            return fallback
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
