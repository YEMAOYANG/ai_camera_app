from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from core.database import Database
from integrations.openmaic_classroom_adapter import ClassroomSourceResult
from repositories.learning_repository import LearningRepository
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    LearningMediaMaterializationService,
)
from services.lesson_package_service import LessonPackageService
from tests.support import fresh_test_config
from tests import test_grade_one_pinyin_gold_package as pinyin_fixture
from tests.test_learning_teacher_media_assets import ContractFakeVoxCpmProvider
from tests.test_lesson_package_v2 import _FakeClassroomAdapter
from tests.test_learning_generated_course_validator import math_candidate


class _StaticPinyinAdapter:
    def __init__(self, source: dict):
        self.source = copy.deepcopy(source)

    def availability(self):
        return {"available": True, "generator": "openmaic"}

    def generate(self, **kwargs):
        source = copy.deepcopy(self.source)
        source["requestId"] = kwargs["request_id"]
        return ClassroomSourceResult(
            request_id=kwargs["request_id"],
            source=source,
            provider="kimi",
            model="kimi-test",
            elapsed_ms=3,
        )


class LessonPackageMediaPipelineTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database = Database(config["DATABASE_URL"])
        self.temporary = tempfile.TemporaryDirectory(prefix="mira-package-media-")
        self.media_service = LearningMediaMaterializationService(
            LearningTeacherMediaRepository(self.database),
            tts_provider=ContractFakeVoxCpmProvider(),
            asset_store=FilesystemLearningMediaAssetStore(
                Path(self.temporary.name)
            ),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_math_package_is_private_until_all_narration_assets_are_ready(self):
        course = self._seed_math_course()
        adapter = _FakeClassroomAdapter()
        service = LessonPackageService(
            self.database.database_url,
            adapter=adapter,
            media_service=self.media_service,
        )
        first = service.generate(
            {
                "courseId": course["id"],
                "courseVersion": course["version"],
                "requestId": "package-media-math",
            }
        )
        self.assertEqual(first.status_code, 202, first.payload)
        self.assertEqual(first.payload["status"], "media_pending")
        self.assertEqual(first.payload["package"]["status"], "media_pending")
        self.assertEqual(len(first.payload["media"]["segments"]), 5)
        package = first.payload["package"]
        with self.database.transaction() as conn:
            binding = conn.execute(
                """
                SELECT 1 FROM learning_course_lesson_package_bindings
                WHERE course_id = ? AND course_version = ?
                """,
                (course["id"], course["version"]),
            ).fetchone()
        self.assertIsNone(binding)

        media = self.media_service.materialize_job(
            job_id=first.payload["media"]["id"]
        )
        self.assertEqual(media["status"], "ready")
        with self.database.transaction() as conn:
            required_assets = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM learning_lesson_package_assets
                WHERE package_id = ? AND package_version = ?
                  AND usage_kind = 'narration' AND required_asset = 1
                """,
                (package["id"], package["version"]),
            ).fetchone()
        self.assertEqual(int(required_assets["total"]), 5)

        finalized = service.finalize_media_package(
            package_id=package["id"],
            package_version=package["version"],
        )
        self.assertTrue(finalized["ok"], finalized)
        self.assertEqual(finalized["status"], "published")
        narrations = [
            action
            for scene in finalized["package"]["classroom"]["scenes"]
            for action in scene["actions"]
            if action["type"] == "narrate"
        ]
        self.assertEqual(len(narrations), 5)
        self.assertTrue(
            all(item["audioAssetRef"].startswith("asset:media_asset_") for item in narrations)
        )
        self.assertEqual(len(finalized["package"]["classroom"]["assetRefs"]), 5)
        replay = service.generate(
            {
                "courseId": course["id"],
                "courseVersion": course["version"],
                "requestId": "package-media-math",
            }
        )
        self.assertEqual(replay.status_code, 200, replay.payload)
        self.assertEqual(replay.payload["status"], "published")
        self.assertEqual(len(adapter.calls), 1)

    def test_stale_job_with_source_artifact_resumes_without_another_model_call(self):
        course = self._seed_math_course()
        adapter = _FakeClassroomAdapter()
        service = LessonPackageService(
            self.database.database_url,
            adapter=adapter,
            media_service=self.media_service,
        )
        request_id = "package-stale-source-resume"
        service.enqueue(
            course_id=course["id"],
            course_version=course["version"],
            request_id=request_id,
        )
        with service.repository.transaction() as conn:
            job = service.repository.get_job_by_request(
                conn,
                request_id=request_id,
                for_update=True,
            )
            self.assertTrue(
                service.repository.claim_job(
                    conn,
                    job_id=str(job["id"]),
                    now=2,
                )
            )
            job = service.repository.get_job_by_request(conn, request_id=request_id)
            stored_course = service.repository.get_course(
                conn,
                course_id=course["id"],
                course_version=course["version"],
            )
        generated = adapter.generate(
            request_id=request_id,
            course=stored_course,
            skill_boundary=service._boundary(stored_course),
            public_questions=service._public_practice_questions(stored_course),
        )
        source_json = service.repository.encode_json(generated.source)
        with service.repository.transaction() as conn:
            service.repository.create_source_artifact(
                conn,
                job=job,
                source_format="mira.openmaic.classroom_intent.v2",
                source_package_version=service._source_package_version(generated),
                dsl_version=str(generated.source["dslVersion"]),
                source_hash=hashlib.sha256(source_json.encode("utf-8")).hexdigest(),
                payload_json=source_json,
                now=3,
            )
            conn.execute(
                "UPDATE learning_classroom_generation_jobs SET updated_at = 3 WHERE id = ?",
                (job["id"],),
            )

        resumed = service.generate(
            {
                "courseId": course["id"],
                "courseVersion": course["version"],
                "requestId": request_id,
            }
        )
        self.assertEqual(resumed.payload["status"], "media_pending", resumed.payload)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(
            resumed.payload["generator"]["provider"],
            "persisted_source_artifact",
        )

    def test_pinyin_package_remains_unpublished_until_every_asset_is_reviewed(self):
        fixture = pinyin_fixture.GradeOnePinyinGoldPackageTest()
        fixture.setUp()
        course = self._seed_pinyin_course(fixture.course)
        service = LessonPackageService(
            self.database.database_url,
            adapter=_StaticPinyinAdapter(fixture.source),
            media_service=self.media_service,
        )
        generated = service.generate(
            {
                "courseId": course["id"],
                "courseVersion": course["version"],
                "requestId": "package-media-pinyin",
            }
        )
        self.assertEqual(generated.status_code, 202, generated.payload)
        media = self.media_service.materialize_job(
            job_id=generated.payload["media"]["id"]
        )
        self.assertEqual(media["status"], "awaiting_review")
        package = generated.payload["package"]
        blocked = service.finalize_media_package(
            package_id=package["id"],
            package_version=package["version"],
        )
        self.assertEqual(blocked["status"], "media_pending")
        self.assertEqual(blocked["media"]["readySegmentCount"], 0)

        for segment in media["segments"]:
            reviewed = self.media_service.review_pronunciation_asset(
                asset_id=segment["assetId"],
                approved=True,
                reviewer_type="content_reviewer",
                reviewer_id="reviewer-pinyin",
                findings={"pronunciationAccurate": True},
            )
        self.assertEqual(reviewed["job"]["status"], "ready")
        published = service.finalize_media_package(
            package_id=package["id"],
            package_version=package["version"],
        )
        self.assertEqual(published["status"], "published")

    def _seed_math_course(self) -> dict:
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
            "id": "package-media-math-course",
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

    def _seed_pinyin_course(self, raw: dict) -> dict:
        content = json.loads(raw["content_json"])
        course = {
            "id": raw["id"],
            "version": raw["version"],
            "gradeCode": raw["grade_code"],
            "subject": raw["subject"],
            "nodeCode": raw["node_code"],
            "title": raw["title"],
            "objective": "认识并准确听辨单韵母 a、o、e。",
            "status": "published",
            "content": content,
        }
        LearningRepository(self.database).ensure_published_courses(
            (course,),
            now=int(datetime.now().timestamp() * 1000),
        )
        return course


if __name__ == "__main__":
    unittest.main()
