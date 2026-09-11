from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from core.database import Database, DatabaseConnection, DatabaseRow


class OpenMaicRuntimeEventRepository:
    def __init__(self, database: Database):
        self.database = database

    def transaction(self):
        return self.database.transaction()

    def get_runtime_subject(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
    ) -> DatabaseRow | None:
        """Resolve immutable lock keys without taking a row lock.

        ``record`` uses this snapshot only to discover the exact child, task,
        session and formal rows that must subsequently be locked.  Every value
        is compared with the locked rows before a mutation is allowed.
        """

        return conn.execute(
            """
            SELECT runtime_session.id AS runtime_session_id,
              runtime_session.principal_id, runtime_session.family_id,
              runtime_session.child_id, runtime_session.learning_session_id,
              runtime_session.runtime_classroom_id,
              runtime.upstream_classroom_id,
              session.task_id, session.course_id, session.course_version,
              session.lesson_package_id AS package_id,
              session.lesson_package_version AS package_version,
              session.lesson_package_content_hash AS package_content_hash,
              formal_binding.authority_kind AS binding_authority_kind,
              formal_binding.pointer_history_id AS binding_history_id,
              formal_binding.pointer_revision AS binding_pointer_revision,
              formal_binding.preparation_plan_id AS binding_plan_id,
              formal_binding.grade_selection_revision AS binding_grade_revision,
              formal_binding.release_id AS binding_release_id,
              formal_binding.grade_code AS binding_grade_code,
              formal_binding.target_fingerprint AS binding_target_fingerprint,
              formal_binding.publication_contract_version
                AS binding_contract_version,
              formal_binding.runtime_binding_contract_version
                AS binding_runtime_contract_version,
              formal_binding.build_item_id AS binding_build_item_id,
              formal_binding.course_id AS binding_course_id,
              formal_binding.course_version AS binding_course_version,
              formal_binding.package_id AS binding_package_id,
              formal_binding.package_version AS binding_package_version,
              formal_binding.package_content_hash AS binding_package_content_hash
            FROM student_openmaic_runtime_sessions AS runtime_session
            JOIN learning_sessions AS session
              ON session.id = runtime_session.learning_session_id
             AND session.family_id = runtime_session.family_id
             AND session.child_id = runtime_session.child_id
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = runtime_session.runtime_classroom_id
            JOIN learning_student_formal_session_bindings AS formal_binding
              ON formal_binding.learning_session_id = session.id
             AND formal_binding.family_id = runtime_session.family_id
             AND formal_binding.child_id = runtime_session.child_id
             AND formal_binding.runtime_classroom_id = runtime.id
             AND formal_binding.upstream_classroom_id =
               runtime.upstream_classroom_id
            WHERE runtime_session.id = ?
              AND runtime_session.learning_session_id = ?
              AND runtime.upstream_classroom_id = ?
            LIMIT 1
            """,
            (runtime_session_id, learning_session_id, upstream_classroom_id),
        ).fetchone()

    def get_child_for_update(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM children
            WHERE family_id = ? AND id = ?
            LIMIT 1 FOR UPDATE
            """,
            (family_id, child_id),
        ).fetchone()

    def get_principal_for_update(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM student_principals
            WHERE id = ?
            LIMIT 1 FOR UPDATE
            """,
            (principal_id,),
        ).fetchone()

    def get_task_for_update(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE family_id = ? AND id = ?
            LIMIT 1 FOR UPDATE
            """,
            (family_id, task_id),
        ).fetchone()

    def get_learning_session_for_update(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        learning_session_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_sessions
            WHERE family_id = ? AND id = ?
            LIMIT 1 FOR UPDATE
            """,
            (family_id, learning_session_id),
        ).fetchone()

    def get_formal_pointer_for_update(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_grade_release_pointers
            WHERE grade_code = ?
            LIMIT 1 FOR UPDATE
            """,
            (grade_code,),
        ).fetchone()

    def get_formal_plan_for_update(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        grade_selection_revision: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_preparation_plans
            WHERE family_id = ? AND child_id = ? AND grade_code = ?
              AND grade_selection_revision = ?
              AND status = 'ready' AND stage = 'completed'
              AND superseded_at IS NULL
            ORDER BY retry_ordinal DESC, created_at DESC
            LIMIT 1 FOR UPDATE
            """,
            (family_id, child_id, grade_code, grade_selection_revision),
        ).fetchone()

    def get_formal_history_for_update(
        self,
        conn: DatabaseConnection,
        *,
        history_id: str,
        grade_code: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_grade_release_history
            WHERE id = ? AND grade_code = ?
            LIMIT 1 FOR UPDATE
            """,
            (history_id, grade_code),
        ).fetchone()

    def get_formal_course_ownership_for_update(
        self,
        conn: DatabaseConnection,
        *,
        learning_session_id: str,
        release_id: str,
        grade_code: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
    ) -> DatabaseRow | None:
        """Lock the exact course artifact owned by the current grade release."""

        return conn.execute(
            """
            SELECT release_row.id AS release_id,
              release_row.status AS release_status,
              release_row.quality_status AS release_quality_status,
              release_row.ready_item_count AS release_ready_item_count,
              release_row.activated_at AS release_activated_at,
              release_row.retired_at AS release_retired_at,
              release_item.status AS release_item_status,
              release_item.quality_status AS release_item_quality_status,
              release_item.retired_at AS release_item_retired_at,
              release_item.grade_code, release_item.course_id,
              release_item.course_version, release_item.package_id,
              release_item.package_version,
              binding.authority_kind AS binding_authority_kind,
              binding.build_item_id,
              binding.pointer_history_id AS binding_history_id,
              binding.pointer_revision AS binding_pointer_revision,
              binding.preparation_plan_id AS binding_plan_id,
              binding.grade_selection_revision AS binding_grade_revision,
              binding.target_fingerprint AS binding_target_fingerprint,
              binding.publication_contract_version
                AS binding_contract_version,
              binding.runtime_binding_contract_version
                AS binding_runtime_contract_version,
              binding.package_content_hash AS binding_package_content_hash,
              binding.runtime_classroom_id,
              binding.upstream_classroom_id,
              build_item.build_job_id, build_item.status AS build_item_status,
              build_item.execution_mode_snapshot
                AS build_item_execution_mode_snapshot,
              build_item.content_phase AS build_item_content_phase,
              build_item.content_gate_status AS build_item_content_gate_status,
              build_item.content_gate_passed_at
                AS build_item_content_gate_passed_at,
              build_item.content_validation_contract_version
                AS build_item_content_validation_contract_version,
              build_item.content_receipt_hash
                AS build_item_content_receipt_hash,
              authority_plan.id AS authority_plan_id,
              authority_plan.family_id AS authority_plan_family_id,
              authority_plan.child_id AS authority_plan_child_id,
              authority_plan.grade_code AS authority_plan_grade_code,
              authority_plan.grade_selection_revision
                AS authority_plan_grade_revision,
              authority_plan.catalog_build_id AS authority_plan_build_id,
              authority_plan.catalog_release_id AS authority_plan_release_id,
              authority_plan.target_fingerprint AS authority_plan_fingerprint,
              authority_plan.status AS authority_plan_status,
              authority_history.id AS authority_history_id,
              authority_history.grade_code AS authority_history_grade_code,
              authority_history.pointer_revision AS authority_history_revision,
              authority_history.target_fingerprint
                AS authority_history_fingerprint,
              authority_history.contract_version
                AS authority_history_contract_version,
              authority_history.release_id AS authority_history_release_id,
              authority_history.activation_source
                AS authority_history_activation_source
            FROM learning_student_formal_session_bindings AS binding
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = binding.release_id
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = release_row.id
             AND release_item.grade_code = binding.grade_code
             AND release_item.course_id = binding.course_id
             AND release_item.course_version = binding.course_version
             AND release_item.package_id = binding.package_id
             AND release_item.package_version = binding.package_version
            JOIN learning_catalog_build_items AS build_item
              ON build_item.id = binding.build_item_id
             AND build_item.release_id = release_row.id
             AND build_item.grade_code = binding.grade_code
             AND build_item.course_id = binding.course_id
             AND build_item.course_version = binding.course_version
            LEFT JOIN learning_curriculum_preparation_plans AS authority_plan
              ON authority_plan.id = binding.preparation_plan_id
            LEFT JOIN learning_curriculum_grade_release_history
              AS authority_history
              ON authority_history.id = binding.pointer_history_id
            JOIN learning_courses AS course
              ON course.id = release_item.course_id
             AND course.version = release_item.course_version
             AND course.grade_code = release_item.grade_code
            JOIN learning_lesson_packages AS package
              ON package.id = release_item.package_id
             AND package.version = release_item.package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
             AND package.public_content_hash = binding.package_content_hash
            WHERE binding.learning_session_id = ?
              AND binding.release_id = ? AND binding.grade_code = ?
              AND binding.course_id = ? AND binding.course_version = ?
              AND binding.package_id = ? AND binding.package_version = ?
              AND course.status = 'published'
              AND course.quality_status = 'released'
              AND course.content_origin = 'openmaic_generated'
              AND course.retired_at IS NULL
              AND package.status = 'published'
              AND package.retired_at IS NULL
            LIMIT 1 FOR UPDATE
            """,
            (
                learning_session_id,
                release_id,
                grade_code,
                course_id,
                course_version,
                package_id,
                package_version,
            ),
        ).fetchone()

    def get_runtime_authority(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT runtime_session.id AS runtime_session_id,
              runtime_session.principal_id,
              runtime_session.family_id,
              runtime_session.child_id,
              runtime_session.learning_session_id,
              runtime_session.runtime_classroom_id,
              runtime_session.expires_at AS runtime_expires_at,
              runtime_session.revoked_at AS runtime_revoked_at,
              runtime.upstream_classroom_id,
              runtime.status AS runtime_status,
              runtime.package_id AS runtime_package_id,
              runtime.package_version AS runtime_package_version,
              runtime.candidate_build_item_id,
              runtime.candidate_release_id,
              runtime.candidate_grade_code,
              runtime.candidate_target_fingerprint,
              runtime.feature_manifest_json,
              session.status AS session_status,
              session.current_question_index AS session_current_question_index,
              session.correct_count AS session_correct_count,
              session.attempted_count AS session_attempted_count,
              session.answers_json AS session_answers_json,
              session.task_id AS session_task_id,
              session.course_id AS session_course_id,
              session.course_version AS session_course_version,
              session.lesson_package_id AS session_package_id,
              session.lesson_package_version AS session_package_version,
              session.started_at AS session_started_at,
              session.completed_at AS session_completed_at,
              course.grade_code AS course_grade_code,
              course.subject AS course_subject,
              course.node_code AS course_node_code,
              course.title AS course_title,
              course.objective AS course_objective,
              course.content_json AS course_content_json
            FROM student_openmaic_runtime_sessions AS runtime_session
            JOIN learning_sessions AS session
              ON session.id = runtime_session.learning_session_id
             AND runtime_session.family_id = session.family_id
             AND runtime_session.child_id = session.child_id
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = runtime_session.runtime_classroom_id
             AND runtime.package_id = session.lesson_package_id
             AND runtime.package_version = session.lesson_package_version
            JOIN learning_student_formal_session_bindings AS formal_binding
              ON formal_binding.learning_session_id = session.id
             AND formal_binding.family_id = runtime_session.family_id
             AND formal_binding.child_id = runtime_session.child_id
             AND formal_binding.release_id = runtime.candidate_release_id
             AND formal_binding.grade_code = runtime.candidate_grade_code
             AND formal_binding.target_fingerprint =
               runtime.candidate_target_fingerprint
             AND formal_binding.build_item_id =
               runtime.candidate_build_item_id
             AND formal_binding.course_id = session.course_id
             AND formal_binding.course_version = session.course_version
             AND formal_binding.package_id = session.lesson_package_id
             AND formal_binding.package_version =
               session.lesson_package_version
             AND formal_binding.package_content_hash =
               session.lesson_package_content_hash
             AND formal_binding.runtime_classroom_id = runtime.id
             AND formal_binding.upstream_classroom_id =
               runtime.upstream_classroom_id
             AND formal_binding.publication_contract_version =
               'mira.learning.formal-publication.v1'
            JOIN learning_courses AS course
              ON course.id = session.course_id
             AND course.version = session.course_version
             AND course.grade_code = runtime.candidate_grade_code
            WHERE runtime_session.id = ?
              AND runtime_session.learning_session_id = ?
              AND runtime.upstream_classroom_id = ?
              AND runtime.retired_at IS NULL
            LIMIT 1
            """
            + lock,
            (runtime_session_id, learning_session_id, upstream_classroom_id),
        ).fetchone()

    def create_or_get_stream(
        self,
        conn: DatabaseConnection,
        *,
        authority: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        manifest = self._json_object(authority.get("feature_manifest_json"))
        expected_scene_count = int(manifest.get("sceneCount") or 0)
        conn.execute(
            """
            INSERT INTO learning_openmaic_runtime_event_streams(
              runtime_session_id, learning_session_id, runtime_classroom_id,
              upstream_classroom_id, principal_id, family_id, child_id,
              release_id, target_fingerprint, expected_scene_count,
              last_sequence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON DUPLICATE KEY UPDATE runtime_session_id = runtime_session_id
            """,
            (
                authority["runtime_session_id"],
                authority["learning_session_id"],
                authority["runtime_classroom_id"],
                authority["upstream_classroom_id"],
                authority["principal_id"],
                authority["family_id"],
                authority["child_id"],
                authority["candidate_release_id"],
                authority["candidate_target_fingerprint"],
                expected_scene_count,
                now,
                now,
            ),
        )
        stream = conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_event_streams
            WHERE runtime_session_id = ?
            LIMIT 1 FOR UPDATE
            """,
            (authority["runtime_session_id"],),
        ).fetchone()
        if stream is None:
            raise RuntimeError("OpenMAIC runtime event stream was not persisted")
        return stream

    def get_stream(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_event_streams
            WHERE runtime_session_id = ?
            LIMIT 1
            """
            + lock,
            (runtime_session_id,),
        ).fetchone()

    def get_event_by_idempotency(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        idempotency_key: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_events
            WHERE runtime_session_id = ? AND idempotency_key = ?
            LIMIT 1
            """,
            (runtime_session_id, idempotency_key),
        ).fetchone()

    def get_event_by_sequence(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        sequence: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_events
            WHERE runtime_session_id = ? AND sequence = ?
            LIMIT 1
            """,
            (runtime_session_id, sequence),
        ).fetchone()

    def get_scene_identity(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        scene_index: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT scene_id FROM learning_openmaic_runtime_events
            WHERE runtime_session_id = ? AND scene_index = ?
              AND event_type = 'scene_entered'
            ORDER BY sequence ASC
            LIMIT 1
            """,
            (runtime_session_id, scene_index),
        ).fetchone()

    def scene_evidence(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
    ) -> dict[str, int]:
        row = conn.execute(
            """
            SELECT
              COUNT(DISTINCT CASE WHEN event_type = 'scene_entered'
                THEN scene_index END) AS scene_count,
              COUNT(DISTINCT CASE WHEN event_type = 'action_completed'
                THEN scene_index END) AS action_scene_count,
              COALESCE(MAX(CASE WHEN event_type = 'scene_entered'
                THEN scene_index END), -1) AS maximum_scene_index
            FROM learning_openmaic_runtime_events
            WHERE runtime_session_id = ?
            """,
            (runtime_session_id,),
        ).fetchone()
        return {
            "scene_count": int((row or {}).get("scene_count") or 0),
            "action_scene_count": int((row or {}).get("action_scene_count") or 0),
            "maximum_scene_index": int(
                (row or {}).get("maximum_scene_index")
                if (row or {}).get("maximum_scene_index") is not None
                else -1
            ),
        }

    def learning_session_scene_evidence(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_session_id: str,
        runtime_classroom_id: str,
        release_id: str,
        target_fingerprint: str,
    ) -> dict[str, int]:
        """Aggregate immutable classroom evidence across legitimate re-entry.

        Runtime sequence/idempotency remains scoped to one runtime session, but
        learning completion belongs to the longer-lived learning session.  All
        stream identity columns are included so evidence from another child,
        classroom, release, or frozen target can never be mixed in.
        """

        row = conn.execute(
            """
            SELECT
              COUNT(DISTINCT CASE WHEN event.event_type = 'scene_entered'
                THEN event.scene_index END) AS scene_count,
              COUNT(DISTINCT CASE WHEN event.event_type = 'action_completed'
                THEN event.scene_index END) AS action_scene_count,
              COALESCE(MAX(CASE WHEN event.event_type = 'scene_entered'
                THEN event.scene_index END), -1) AS maximum_scene_index
            FROM learning_openmaic_runtime_events AS event
            JOIN learning_openmaic_runtime_event_streams AS stream
              ON stream.runtime_session_id = event.runtime_session_id
            WHERE stream.family_id = ? AND stream.child_id = ?
              AND stream.learning_session_id = ?
              AND stream.runtime_classroom_id = ?
              AND stream.release_id = ? AND stream.target_fingerprint = ?
            """,
            (
                family_id,
                child_id,
                learning_session_id,
                runtime_classroom_id,
                release_id,
                target_fingerprint,
            ),
        ).fetchone()
        return {
            "scene_count": int((row or {}).get("scene_count") or 0),
            "action_scene_count": int(
                (row or {}).get("action_scene_count") or 0
            ),
            "maximum_scene_index": int(
                (row or {}).get("maximum_scene_index")
                if (row or {}).get("maximum_scene_index") is not None
                else -1
            ),
        }

    def learning_session_completed_action_scene_ids(
        self, conn: DatabaseConnection, *, family_id: str, child_id: str,
        learning_session_id: str, runtime_classroom_id: str, release_id: str,
        target_fingerprint: str,
    ) -> list[str]:
        """Accepted completion only; the complete frozen authority isolates re-entry."""
        rows = conn.execute(
            """
            SELECT DISTINCT event.scene_id
            FROM learning_openmaic_runtime_events AS event
            JOIN learning_openmaic_runtime_event_streams AS stream
              ON stream.runtime_session_id = event.runtime_session_id
            WHERE stream.family_id = ? AND stream.child_id = ?
              AND stream.learning_session_id = ? AND stream.runtime_classroom_id = ?
              AND stream.release_id = ? AND stream.target_fingerprint = ?
              AND event.event_type = 'action_completed'
            ORDER BY event.scene_id
            """,
            (family_id, child_id, learning_session_id, runtime_classroom_id,
             release_id, target_fingerprint),
        ).fetchall()
        return [str(row["scene_id"]) for row in rows]

    def learning_session_interaction_evidence(
        self, conn: DatabaseConnection, *, family_id: str, child_id: str,
        learning_session_id: str, runtime_classroom_id: str, release_id: str,
        target_fingerprint: str,
    ) -> list[dict[str, Any]]:
        # The same immutable learning-session identity as scene evidence supports
        # genuine re-entry without mixing another child's or another release's work.
        rows = conn.execute("""
            SELECT event.event_type, event.payload_json
            FROM learning_openmaic_runtime_events AS event
            JOIN learning_openmaic_runtime_event_streams AS stream
              ON stream.runtime_session_id = event.runtime_session_id
            WHERE stream.family_id = ? AND stream.child_id = ?
              AND stream.learning_session_id = ? AND stream.runtime_classroom_id = ?
              AND stream.release_id = ? AND stream.target_fingerprint = ?
              AND event.event_type = 'interaction_completed'
            ORDER BY event.created_at, event.sequence
        """, (family_id, child_id, learning_session_id, runtime_classroom_id, release_id, target_fingerprint)).fetchall()
        result = []
        for row in rows:
            raw = row.get("payload_json")
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except (ValueError, TypeError):
                continue
            if isinstance(payload, Mapping):
                result.append({"event_type": str(row["event_type"]), "payload": dict(payload)})
        return result

    def answered_question_ids(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT question_id
            FROM learning_openmaic_runtime_events
            WHERE runtime_session_id = ?
              AND event_type = 'answer_submitted'
              AND question_id IS NOT NULL
            GROUP BY question_id
            ORDER BY MIN(sequence) ASC
            """,
            (runtime_session_id,),
        ).fetchall()
        return [str(row["question_id"]) for row in rows]

    def append_event(
        self,
        conn: DatabaseConnection,
        *,
        stream: Mapping[str, Any],
        event: Mapping[str, Any],
        request_sha256: str,
        authoritative: Mapping[str, Any] | None,
        response: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        payload = event["payload"]
        identity = (
            f"{stream['runtime_session_id']}:{event['sequence']}:"
            f"{event['idempotencyKey']}"
        )
        event_id = "openmaic_runtime_event_" + hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:32]
        conn.execute(
            """
            INSERT INTO learning_openmaic_runtime_events(
              id, runtime_session_id, sequence, idempotency_key,
              request_sha256, event_type, scene_index, scene_id,
              action_id, question_id, attempt_number, payload_json,
              authoritative_json, response_json, receipt_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                stream["runtime_session_id"],
                event["sequence"],
                event["idempotencyKey"],
                request_sha256,
                event["type"],
                payload["sceneIndex"],
                payload["sceneId"],
                payload.get("actionId"),
                payload.get("questionId"),
                payload.get("attemptNumber"),
                self._canonical_json(payload),
                self._canonical_json(authoritative) if authoritative is not None else None,
                self._canonical_json(response),
                response["receiptSha256"],
                now,
            ),
        )
        completed_at = now if response.get("completed") is True else None
        report_id = response.get("reportId") if completed_at is not None else None
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_event_streams
            SET last_sequence = ?, completed_at = ?, report_id = ?, updated_at = ?
            WHERE runtime_session_id = ? AND last_sequence = ?
              AND completed_at IS NULL
            """,
            (
                event["sequence"],
                completed_at,
                report_id,
                now,
                stream["runtime_session_id"],
                int(stream.get("last_sequence") or 0),
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("OpenMAIC runtime event stream advance conflict")
        return {
            "id": event_id,
            "runtime_session_id": stream["runtime_session_id"],
            "sequence": event["sequence"],
            "idempotency_key": event["idempotencyKey"],
            "request_sha256": request_sha256,
            "event_type": event["type"],
            "response_json": self._canonical_json(response),
        }

    @classmethod
    def decode_response(cls, row: Mapping[str, Any]) -> dict[str, Any] | None:
        return cls._json_object(row.get("response_json")) or None

    @staticmethod
    def _canonical_json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    @staticmethod
    def _json_object(value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        try:
            payload = json.loads(str(value or ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}
