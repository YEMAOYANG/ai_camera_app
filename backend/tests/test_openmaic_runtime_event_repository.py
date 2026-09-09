from __future__ import annotations

import json
import unittest

from core.database import Database
from repositories.openmaic_runtime_event_repository import OpenMaicRuntimeEventRepository


class _Cursor:
    def __init__(self, row=None, rows=None, rowcount=1):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.calls = []
        self.stream = {
            "runtime_session_id": "runtime-session-1",
            "learning_session_id": "learning-session-1",
            "runtime_classroom_id": "runtime-row-1",
            "upstream_classroom_id": "classroom-1",
            "family_id": "family-1",
            "child_id": "child-1",
            "release_id": "release-1",
            "target_fingerprint": "a" * 64,
            "expected_scene_count": 10,
            "last_sequence": 0,
            "completed_at": None,
            "report_id": None,
        }

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, tuple(params)))
        if "FROM student_openmaic_runtime_sessions AS runtime_session" in normalized:
            return _Cursor(row={"runtime_session_id": "runtime-session-1"})
        if normalized.startswith("SELECT * FROM learning_openmaic_runtime_event_streams"):
            return _Cursor(row=dict(self.stream))
        if normalized.startswith("UPDATE learning_openmaic_runtime_event_streams"):
            self.stream["last_sequence"] = params[0]
            self.stream["completed_at"] = params[1]
            self.stream["report_id"] = params[2]
            return _Cursor(rowcount=1)
        if normalized.startswith("SELECT scene_id FROM learning_openmaic_runtime_events"):
            return _Cursor(row={"scene_id": "scene-0"})
        if normalized.startswith("SELECT COUNT(DISTINCT CASE"):
            return _Cursor(
                row={"scene_count": 10, "action_scene_count": 10, "maximum_scene_index": 9}
            )
        if normalized.startswith("SELECT question_id FROM learning_openmaic_runtime_events"):
            return _Cursor(rows=[{"question_id": "q2"}, {"question_id": "q3"}])
        return _Cursor(rowcount=1)


class OpenMaicRuntimeEventRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.repository = OpenMaicRuntimeEventRepository(
            Database("mysql://user:pass@127.0.0.1/test")
        )

    def test_authority_query_binds_runtime_learning_and_upstream_classroom(self):
        conn = _Connection()
        row = self.repository.get_runtime_authority(
            conn,
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
            for_update=True,
        )
        sql, params = conn.calls[-1]
        self.assertEqual(row["runtime_session_id"], "runtime-session-1")
        self.assertEqual(
            params,
            ("runtime-session-1", "learning-session-1", "classroom-1"),
        )
        self.assertIn("runtime_session.family_id = session.family_id", sql)
        self.assertIn("runtime_session.child_id = session.child_id", sql)
        self.assertIn("runtime.id = runtime_session.runtime_classroom_id", sql)
        self.assertIn("learning_student_formal_session_bindings", sql)
        self.assertIn(
            "formal_binding.release_id = runtime.candidate_release_id",
            sql,
        )
        self.assertIn(
            "formal_binding.runtime_classroom_id = runtime.id",
            sql,
        )
        for binding in (
            "formal_binding.learning_session_id = session.id",
            "formal_binding.family_id = runtime_session.family_id",
            "formal_binding.child_id = runtime_session.child_id",
            "formal_binding.target_fingerprint = runtime.candidate_target_fingerprint",
            "formal_binding.build_item_id = runtime.candidate_build_item_id",
            "formal_binding.package_content_hash = session.lesson_package_content_hash",
            "formal_binding.upstream_classroom_id = runtime.upstream_classroom_id",
            "formal_binding.publication_contract_version = 'mira.learning.formal-publication.v1'",
        ):
            self.assertIn(binding, sql)
        self.assertTrue(sql.endswith("FOR UPDATE"), sql)

    def test_formal_course_ownership_keeps_build_identity_without_package_link(self):
        conn = _Connection()

        self.repository.get_formal_course_ownership_for_update(
            conn,
            learning_session_id="learning-session-1",
            release_id="release-1",
            grade_code="primary_1",
            course_id="course-1",
            course_version="1",
            package_id="package-1",
            package_version=1,
        )

        sql, params = conn.calls[-1]
        self.assertEqual(
            params,
            (
                "learning-session-1",
                "release-1",
                "primary_1",
                "course-1",
                "1",
                "package-1",
                1,
            ),
        )
        self.assertIn("build_item.release_id = release_row.id", sql)
        self.assertIn("build_item.course_id = binding.course_id", sql)
        self.assertNotIn("build_item.package_id = binding.package_id", sql)
        self.assertNotIn("build_item.package_version = binding.package_version", sql)
        self.assertIn("release_item.package_id = binding.package_id", sql)
        self.assertIn("package.id = release_item.package_id", sql)
        self.assertTrue(sql.endswith("FOR UPDATE"), sql)

    def test_append_event_advances_stream_by_compare_and_swap_and_freezes_completion(self):
        conn = _Connection()
        stream = dict(conn.stream)
        event = {
            "schemaVersion": "mira.openmaic.student-runtime-event.v1",
            "sequence": 1,
            "type": "classroom_completed",
            "idempotencyKey": "b" * 64,
            "payload": {"sceneIndex": 9, "sceneId": "scene-9"},
        }
        response = {
            "ok": True,
            "completed": True,
            "reportId": "report-1",
            "receiptSha256": "c" * 64,
        }
        self.repository.append_event(
            conn,
            stream=stream,
            event=event,
            request_sha256="d" * 64,
            authoritative=None,
            response=response,
            now=1_777_777_777_000,
        )

        update_sql, update_params = next(
            call
            for call in conn.calls
            if call[0].startswith("UPDATE learning_openmaic_runtime_event_streams")
        )
        self.assertEqual(update_params[0:3], (1, 1_777_777_777_000, "report-1"))
        self.assertIn("last_sequence = ?", update_sql)
        self.assertIn("AND last_sequence = ?", update_sql)
        self.assertIn("AND completed_at IS NULL", update_sql)
        self.assertEqual(conn.stream["last_sequence"], 1)
        self.assertEqual(conn.stream["report_id"], "report-1")

    def test_write_authority_repository_exposes_child_first_lock_sequence(self):
        conn = _Connection()
        self.repository.get_runtime_subject(
            conn,
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
        )
        self.repository.get_child_for_update(
            conn,
            family_id="family-1",
            child_id="child-1",
        )
        self.repository.get_principal_for_update(
            conn,
            principal_id="principal-1",
        )
        self.repository.get_task_for_update(
            conn,
            family_id="family-1",
            task_id="task-1",
        )
        self.repository.get_learning_session_for_update(
            conn,
            family_id="family-1",
            learning_session_id="learning-session-1",
        )
        self.repository.get_formal_pointer_for_update(
            conn,
            grade_code="primary_1",
        )
        self.repository.get_formal_plan_for_update(
            conn,
            family_id="family-1",
            child_id="child-1",
            grade_code="primary_1",
            grade_selection_revision=1,
        )
        self.repository.get_formal_history_for_update(
            conn,
            history_id="history-1",
            grade_code="primary_1",
        )
        self.repository.get_formal_course_ownership_for_update(
            conn,
            learning_session_id="learning-session-1",
            release_id="release-1",
            grade_code="primary_1",
            course_id="course-1",
            course_version="1",
            package_id="package-1",
            package_version=1,
        )
        self.repository.get_runtime_authority(
            conn,
            runtime_session_id="runtime-session-1",
            learning_session_id="learning-session-1",
            upstream_classroom_id="classroom-1",
            for_update=True,
        )

        statements = [sql for sql, _params in conn.calls]
        self.assertNotIn("FOR UPDATE", statements[0])
        locked_tables = (
            "FROM children",
            "FROM student_principals",
            "FROM tasks",
            "FROM learning_sessions",
            "FROM learning_curriculum_grade_release_pointers",
            "FROM learning_curriculum_preparation_plans",
            "FROM learning_curriculum_grade_release_history",
            "FROM learning_student_formal_session_bindings",
            "FROM student_openmaic_runtime_sessions AS runtime_session",
        )
        lock_positions = []
        for table in locked_tables:
            position = next(
                index
                for index, statement in enumerate(statements[1:], start=1)
                if table in statement
            )
            self.assertTrue(statements[position].endswith("FOR UPDATE"))
            lock_positions.append(position)
        self.assertEqual(lock_positions, sorted(lock_positions))
        self.assertIn(
            "course.content_origin = 'openmaic_generated'",
            statements[lock_positions[-2]],
        )

    def test_scene_evidence_is_server_aggregated_and_response_decode_is_closed(self):
        conn = _Connection()
        identity = self.repository.get_scene_identity(
            conn,
            runtime_session_id="runtime-session-1",
            scene_index=0,
        )
        evidence = self.repository.scene_evidence(
            conn,
            runtime_session_id="runtime-session-1",
        )
        lesson_evidence = self.repository.learning_session_scene_evidence(
            conn,
            family_id="family-1",
            child_id="child-1",
            learning_session_id="learning-session-1",
            runtime_classroom_id="runtime-row-1",
            release_id="release-1",
            target_fingerprint="a" * 64,
        )
        answered_question_ids = self.repository.answered_question_ids(
            conn,
            runtime_session_id="runtime-session-1",
        )
        self.assertEqual(identity, {"scene_id": "scene-0"})
        self.assertEqual(evidence["action_scene_count"], 10)
        self.assertEqual(lesson_evidence["scene_count"], 10)
        aggregate_sql, aggregate_params = next(
            call
            for call in conn.calls
            if "JOIN learning_openmaic_runtime_event_streams AS stream" in call[0]
        )
        self.assertEqual(
            aggregate_params,
            (
                "family-1",
                "child-1",
                "learning-session-1",
                "runtime-row-1",
                "release-1",
                "a" * 64,
            ),
        )
        for identity_column in (
            "stream.family_id = ?",
            "stream.child_id = ?",
            "stream.learning_session_id = ?",
            "stream.runtime_classroom_id = ?",
            "stream.release_id = ?",
            "stream.target_fingerprint = ?",
        ):
            self.assertIn(identity_column, aggregate_sql)
        self.assertEqual(answered_question_ids, ["q2", "q3"])
        self.assertEqual(
            self.repository.decode_response(
                {"response_json": json.dumps({"ok": True, "sequence": 1})}
            ),
            {"ok": True, "sequence": 1},
        )
        self.assertIsNone(self.repository.decode_response({"response_json": "[]"}))


if __name__ == "__main__":
    unittest.main()
