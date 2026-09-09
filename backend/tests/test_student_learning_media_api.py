from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from core.database import Database
from repositories.learning_repository import LearningRepository
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    LearningMediaMaterializationService,
)
from services.lesson_package_service import LessonPackageService
from tests.support import fresh_test_config, request_debug_code
from tests.test_learning_generated_course_validator import math_candidate
from tests.test_learning_teacher_media_assets import ContractFakeVoxCpmProvider
from tests.test_lesson_package_v2 import _FakeClassroomAdapter


class StudentLearningMediaApiTest(unittest.TestCase):
    def setUp(self):
        # This media-delivery suite supplies its own third-grade course and
        # synthetic audio. Keep that fixture's grade open locally; production
        # grade eligibility is covered by the QR/auth access tests.
        grade_scope = patch(
            'services.formal_student_learning_access.FORMAL_STUDENT_GRADE_CODES',
            frozenset({'primary_3'}),
        )
        grade_scope.start()
        self.addCleanup(grade_scope.stop)
        self.temporary = tempfile.TemporaryDirectory(prefix="mira-student-media-")
        self.app = create_app(
            fresh_test_config(
                LEARNING_MEDIA_STORAGE_ROOT=self.temporary.name,
                LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED=True,
            )
        )
        self.app.extensions["mira_formal_learning_access_checker"] = (
            lambda conn, child: None
        )
        self.client = self.app.test_client()
        self.database = Database(self.app.config["DATABASE_URL"])
        self.course = self._seed_course()
        media_service = LearningMediaMaterializationService(
            LearningTeacherMediaRepository(self.database),
            tts_provider=ContractFakeVoxCpmProvider(),
            asset_store=FilesystemLearningMediaAssetStore(
                Path(self.temporary.name)
            ),
        )
        package_service = LessonPackageService(
            self.app.config["DATABASE_URL"],
            adapter=_FakeClassroomAdapter(),
            media_service=media_service,
        )
        generated = package_service.generate(
            {
                "courseId": self.course["id"],
                "courseVersion": self.course["version"],
                "requestId": "student-media-package",
            }
        )
        self.assertEqual(generated.status_code, 202, generated.payload)
        materialized = media_service.materialize_job(
            job_id=generated.payload["media"]["id"]
        )
        self.assertEqual(materialized["status"], "ready")
        self.package = package_service.finalize_media_package(
            package_id=generated.payload["package"]["id"],
            package_version=generated.payload["package"]["version"],
        )["package"]
        self.asset_ids = [
            action["audioAssetRef"].split(":", 1)[1]
            for scene in self.package["classroom"]["scenes"]
            for action in scene["actions"]
            if action["type"] == "narrate"
        ]

        self.parent_access_token = self._login_parent("13800003151")
        self._create_parent_identity()
        self.child_id = self._create_child("乐乐", "primary_3")
        self.sibling_id = self._insert_sibling("安安")
        self.student_access_token = self._pair_student(self.child_id, "2468")
        self.sibling_access_token = self._pair_student(self.sibling_id, "1357")
        self.session_id = self._insert_pinned_session()

    def tearDown(self):
        self.temporary.cleanup()

    def test_manifest_delivery_range_etag_and_student_isolation(self):
        manifest = self.client.get(
            f"/api/v2/student/learning/sessions/{self.session_id}/assets",
            headers=self._student_headers(),
        )
        self.assertEqual(manifest.status_code, 200, manifest.json)
        self.assertEqual(manifest.json["package"]["id"], self.package["id"])
        self.assertEqual(len(manifest.json["assets"]), 5)
        self.assertTrue(
            all(
                item["deliveryPath"].startswith(
                    "/api/v2/student/learning/assets/media_asset_"
                )
                for item in manifest.json["assets"]
            )
        )

        asset_path = f"/api/v2/student/learning/assets/{self.asset_ids[0]}"
        delivered = self.client.get(asset_path, headers=self._student_headers())
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(delivered.mimetype, "audio/wav")
        self.assertGreater(len(delivered.data), 10)
        self.assertEqual(delivered.headers["Accept-Ranges"], "bytes")
        self.assertEqual(delivered.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            delivered.headers["Cross-Origin-Resource-Policy"],
            "same-origin",
        )
        etag = delivered.headers["ETag"]
        delivered.close()

        ranged = self.client.get(
            asset_path,
            headers={**self._student_headers(), "Range": "bytes=0-9"},
        )
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(len(ranged.data), 10)
        self.assertTrue(ranged.headers["Content-Range"].startswith("bytes 0-9/"))
        ranged.close()

        unchanged = self.client.get(
            asset_path,
            headers={**self._student_headers(), "If-None-Match": etag},
        )
        self.assertEqual(unchanged.status_code, 304)
        unchanged.close()

        sibling = self.client.get(
            asset_path,
            headers=self._student_headers(self.sibling_access_token),
        )
        self.assertEqual(sibling.status_code, 404, sibling.json)
        self.assertEqual(sibling.json["error"], "learning_asset_not_found")

        parent = self.client.get(
            asset_path,
            headers=self._student_headers(self.parent_access_token),
        )
        self.assertEqual(parent.status_code, 401, parent.json)

    def test_review_regression_and_storage_escape_are_never_delivered(self):
        review_blocked_id = self.asset_ids[1]
        traversal_id = self.asset_ids[2]
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_media_quality_reviews
                SET status = 'pending', reviewed_at = NULL
                WHERE asset_id = ? AND required_review = 1
                """,
                (review_blocked_id,),
            )
            conn.execute(
                """
                UPDATE learning_media_asset_variants
                SET storage_key = '../../etc/passwd'
                WHERE asset_id = ? AND variant_key = 'original'
                """,
                (traversal_id,),
            )
        blocked = self.client.get(
            f"/api/v2/student/learning/assets/{review_blocked_id}",
            headers=self._student_headers(),
        )
        self.assertEqual(blocked.status_code, 404, blocked.json)
        escaped = self.client.get(
            f"/api/v2/student/learning/assets/{traversal_id}",
            headers=self._student_headers(),
        )
        self.assertEqual(escaped.status_code, 404, escaped.json)

    def _seed_course(self) -> dict:
        candidate = math_candidate()
        content = copy.deepcopy(candidate["content"])
        for index, question in enumerate(content["questions"]):
            answer = int(question.get("answer") or index + 10)
            question["type"] = "single_choice"
            question["choices"] = [
                {"id": "a", "label": str(answer)},
                {"id": "b", "label": str(answer + 1)},
                {"id": "c", "label": str(max(0, answer - 1))},
            ]
            question["answer"] = "a"
            question["evaluation"] = {"expectedOptionId": "a"}
        course = {
            "id": "student-media-course",
            "version": "1.0.0",
            "gradeCode": "primary_3",
            "subject": "math",
            "nodeCode": "multi_digit_operations",
            "title": candidate["title"],
            "objective": candidate["objective"],
            "status": "published",
            "content": content,
        }
        LearningRepository(self.database).ensure_published_courses(
            (course,),
            now=int(datetime.now().timestamp() * 1000),
        )
        return course

    def _insert_pinned_session(self) -> str:
        session_id = "student_media_session"
        now = int(datetime.now().timestamp() * 1000)
        with self.database.transaction() as conn:
            child = conn.execute(
                "SELECT family_id FROM children WHERE id = ?",
                (self.child_id,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO learning_sessions(
                  id, family_id, child_id, task_id, course_id, course_version,
                  status, current_question_index, correct_count,
                  attempted_count, answers_json, started_at, created_at,
                  updated_at, lesson_package_id, lesson_package_version,
                  lesson_package_content_hash, current_scene_index,
                  current_action_index, cursor_revision, runtime_state_json
                )
                VALUES (?, ?, ?, 'student_media_task', ?, ?, 'in_progress',
                  0, 0, 0, '[]', ?, ?, ?, ?, ?, ?, 0, 0, 0, '{}')
                """,
                (
                    session_id,
                    child["family_id"],
                    self.child_id,
                    self.course["id"],
                    self.course["version"],
                    now,
                    now,
                    now,
                    self.package["id"],
                    self.package["version"],
                    self.package["contentHash"],
                ),
            )
        return session_id

    def _login_parent(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        response = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _create_parent_identity(self) -> None:
        response = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)

    def _create_child(self, name: str, grade_code: str) -> str:
        response = self.client.post(
            "/api/setup/child",
            json={
                "name": name,
                "nickname": name,
                "gradeCode": grade_code,
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["child"]["id"]

    def _insert_sibling(self, name: str) -> str:
        sibling_id = "student_media_sibling"
        with self.database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, nickname, gender, age_stage,
                  education_stage, grade, grade_code,
                  grade_school_year_start, grade_confirmed_at, grade_selection_revision, birthday,
                  sleep_time, created_at, updated_at
                )
                SELECT ?, family_id, ?, ?, gender, age_stage,
                  education_stage, grade, grade_code,
                  grade_school_year_start, grade_confirmed_at, grade_selection_revision, birthday,
                  sleep_time, created_at + 1, updated_at
                FROM children WHERE id = ?
                """,
                (sibling_id, name, name, self.child_id),
            )
        return sibling_id

    def _pair_student(self, child_id: str, pin: str) -> str:
        pairing = self.client.post(
            f"/api/v2/parent/children/{child_id}/student-access/pairing-codes",
            json={"pin": pin},
            headers=self._parent_headers(),
        )
        self.assertEqual(pairing.status_code, 200, pairing.json)
        paired = self.client.post(
            "/api/v2/student/auth/pair",
            json={
                "pairingCode": pairing.json["pairingCode"],
                "clientDevice": {
                    "label": f"{child_id} 测试浏览器",
                    "type": "browser",
                    "platform": "web",
                },
            },
        )
        self.assertEqual(paired.status_code, 200, paired.json)
        return paired.json["tokens"]["accessToken"]

    def _parent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.parent_access_token}"}

    def _student_headers(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token or self.student_access_token}"}


if __name__ == "__main__":
    unittest.main()
