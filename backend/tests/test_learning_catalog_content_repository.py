from __future__ import annotations

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import unittest

from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    PRIMARY_SKILL_BOUNDARIES,
)
from core.database import Database
from core.errors import ApiError
from repositories.learning_catalog_repository import (
    LearningCatalogActivationError,
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from tests.support import fresh_test_config, validated_test_database_url


class _UnexpectedDynamicGenerationService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def generate_for_skill(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("content-only build must not call dynamic generation")


class _UnexpectedLessonPackageService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    def generate(self, data):
        self.calls.append(dict(data))
        raise AssertionError("content-only build must not call package generation")


class _RecordingCatalogValidator:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def validate_course(self, course):
        self.calls.append(("validate_course", course))
        raise AssertionError("content-only activation must not validate a release")


class LearningCatalogContentRepositoryTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = validated_test_database_url(config["DATABASE_URL"])
        self.repository = LearningCatalogRepository(Database(self.database_url))
        self.target = build_preparation_target("primary_1")
        self.fingerprint = preparation_target_fingerprint(self.target)
        self.dynamic = _UnexpectedDynamicGenerationService()
        self.lesson = _UnexpectedLessonPackageService()
        self.validator = _RecordingCatalogValidator()
        self.service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=self.dynamic,
            lesson_package_service=self.lesson,
            catalog_validator=self.validator,
        )

    def _create(self, request_id: str = "cp2-content-build") -> dict[str, object]:
        return self.service.create_preparation_content_build(
            request_id=request_id,
            title="Mira 一年级正式内容候选",
            preparation_target=self.target,
            target_fingerprint=self.fingerprint,
        )

    def _rows(self, build_id: str):
        with self.repository.transaction() as conn:
            build = self.repository.get_build(conn, build_id=build_id)
            release = self.repository.get_release(
                conn,
                release_id=str(build["release_id"]),
            )
            items = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY subject_ordinal, boundary_ordinal, variant_ordinal
                """,
                (build_id,),
            ).fetchall()
        return build, release, list(items)

    def _mark_course_ready(self, item_id: str, *, now: int) -> None:
        receipt = hashlib.sha256(item_id.encode("utf-8")).hexdigest()
        with self.repository.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET status = 'course_ready', attempt_count = 1,
                  claim_origin_status = 'pending',
                  active_generation_request_id = generation_request_id,
                  course_id = ?, course_version = '1.0.0',
                  package_attempt_count = 0,
                  active_package_request_id = NULL,
                  package_id = NULL, package_version = NULL,
                  content_phase = 'course_ready',
                  content_gate_status = 'passed',
                  content_gate_attempt_count = 1,
                  content_gate_passed_at = ?,
                  content_validation_contract_version = ?,
                  content_receipt_hash = ?,
                  content_lease_token = NULL,
                  content_lease_expires_at = NULL,
                  content_heartbeat_at = NULL,
                  content_attempt_started_at = COALESCE(content_attempt_started_at, ?),
                  content_provider_attempt_hard_deadline_at = NULL,
                  content_work_unit_deadline_at = NULL,
                  content_claim_attempt_ordinal = 1,
                  started_at = COALESCE(started_at, ?),
                  completed_at = ?, updated_at = ?
                WHERE id = ? AND execution_mode_snapshot = 'content_only'
                """,
                (
                    f"course_{hashlib.sha256(item_id.encode()).hexdigest()[:24]}",
                    now,
                    self.target["contentValidationContractVersion"],
                    receipt,
                    now - 1,
                    now - 1,
                    now,
                    now,
                    item_id,
                ),
            )
            self.assertEqual(cursor.rowcount, 1)

    def _insert_release_item_pollution(
        self,
        *,
        release_id: str,
        curriculum_version: str,
        title: str = "Mira 一年级正式内容候选",
    ) -> None:
        suffix = hashlib.sha256(release_id.encode("utf-8")).hexdigest()[:16]
        course_id = f"pollution_course_{suffix}"
        job_id = f"pollution_job_{suffix}"
        artifact_id = f"pollution_artifact_{suffix}"
        package_id = f"pollution_package_{suffix}"
        now = 9_000
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO learning_catalog_releases(
                  id, curriculum_version, title, status, quality_status,
                  required_boundary_count, ready_item_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'draft', 'building', 10, 0, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (release_id, curriculum_version, title, now, now),
            )
            conn.execute(
                """
                INSERT INTO learning_courses(
                  id, version, grade_code, subject, node_code,
                  curriculum_version, boundary_version, title, objective,
                  status, quality_status, content_origin, content_json,
                  created_at, updated_at
                ) VALUES (?, '1.0.0', 'primary_1', 'math', 'pollution_skill',
                  ?, 'pollution.boundary.v1', 'pollution', 'pollution',
                  'published', 'released', 'openmaic_generated', '{}', ?, ?)
                """,
                (course_id, curriculum_version, now, now),
            )
            conn.execute(
                """
                INSERT INTO learning_classroom_generation_jobs(
                  id, request_id, course_id, course_version, generator, status,
                  source_artifact_id, package_id, package_version,
                  started_at, completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, '1.0.0', 'openmaic', 'completed', ?, ?, 1,
                  ?, ?, ?, ?)
                """,
                (
                    job_id,
                    f"pollution_request_{suffix}",
                    course_id,
                    artifact_id,
                    package_id,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_classroom_source_artifacts(
                  id, job_id, request_id, source_format, source_package_version,
                  dsl_version, status, source_hash, payload_json,
                  validation_report_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'openmaic_dsl', '0.3.2', '0.3.2',
                  'validated', ?, '{}', '{}', ?, ?)
                """,
                (
                    artifact_id,
                    job_id,
                    f"pollution_request_{suffix}",
                    hashlib.sha256(artifact_id.encode("utf-8")).hexdigest(),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_lesson_packages(
                  id, version, course_id, course_version,
                  source_course_content_hash, schema_version, status,
                  source_artifact_id, compiler_version, public_content_hash,
                  private_content_hash, public_payload_json,
                  validation_report_json, created_at, published_at, updated_at
                ) VALUES (?, 1, ?, '1.0.0', SHA2('{}', 256),
                  'mira.lesson-package.v2', 'published', ?, 'pollution-test',
                  ?, ?, '{}', '{}', ?, ?, ?)
                """,
                (
                    package_id,
                    course_id,
                    artifact_id,
                    hashlib.sha256(f"public:{suffix}".encode()).hexdigest(),
                    hashlib.sha256(f"private:{suffix}".encode()).hexdigest(),
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_release_items(
                  release_id, course_id, course_version, grade_code, subject,
                  skill_id, curriculum_version, boundary_version,
                  variant_ordinal, package_id, package_version, status,
                  quality_status, published_at, created_at, updated_at
                ) VALUES (?, ?, '1.0.0', 'primary_1', 'math',
                  'pollution_skill', ?, 'pollution.boundary.v1', 99, ?, 1,
                  'published', 'ready', ?, ?, ?)
                """,
                (
                    release_id,
                    course_id,
                    curriculum_version,
                    package_id,
                    now,
                    now,
                    now,
                ),
            )

    def test_preparation_build_has_exact_ordered_30_item_manifest_and_three_canaries(self):
        created = self._create()
        build_id = str(created["build"]["id"])
        build, release, items = self._rows(build_id)

        self.assertEqual(build["execution_mode"], "content_only")
        self.assertEqual(build["stage_ceiling"], "content_ready")
        self.assertEqual(
            build["content_manifest_version"],
            "mira.learning.preparation-target.v2",
        )
        self.assertEqual(json.loads(build["target_spec_json"]), self.target)
        self.assertEqual(
            build["canary_manifest_json"],
            self.repository.encode_json(self.target["canaryManifest"]),
        )
        self.assertEqual(int(build["total_item_count"]), 30)
        self.assertEqual(int(release["required_boundary_count"]), 10)
        self.assertEqual(len(items), 30)

        expected = [
            (
                target["subject"],
                target["subjectOrdinal"],
                target["skillId"],
                target["boundaryOrdinal"],
                target["boundaryVersion"],
                target["variantOrdinal"],
                target["instructionLanguageCode"],
                target["targetLanguageCode"],
            )
            for target in self.target["courseTargets"]
        ]
        actual = [
            (
                item["subject"],
                item["subject_ordinal"],
                item["skill_id"],
                item["boundary_ordinal"],
                item["boundary_version"],
                item["variant_ordinal"],
                json.loads(build["target_spec_json"])["courseTargets"][index][
                    "instructionLanguageCode"
                ],
                json.loads(build["target_spec_json"])["courseTargets"][index][
                    "targetLanguageCode"
                ],
            )
            for index, item in enumerate(items)
        ]
        self.assertEqual(actual, expected)
        self.assertTrue(
            all(item["execution_mode_snapshot"] == "content_only" for item in items)
        )
        self.assertTrue(
            all(
                item["content_manifest_version_snapshot"]
                == self.target["schemaVersion"]
                for item in items
            )
        )
        self.assertTrue(all(item["content_phase"] == "not_started" for item in items))
        self.assertTrue(all(item["content_gate_status"] == "not_started" for item in items))
        self.assertTrue(all(int(item["package_attempt_count"]) == 0 for item in items))
        self.assertTrue(all(item["package_id"] is None for item in items))

        canary_identities = {
            (item["subject"], item["skillId"], item["variantOrdinal"])
            for item in self.target["canaryManifest"]["targets"]
        }
        self.assertEqual(
            canary_identities,
            {
                ("chinese", "pinyin_syllables", 1),
                ("math", "number_sense_20", 1),
                ("english", "letters_sounds", 1),
            },
        )
        self.assertEqual(self.dynamic.calls, [])
        self.assertEqual(self.lesson.calls, [])

    def test_content_claim_has_one_real_mysql_winner_and_manifest_driven_order(self):
        created = self._create("cp2-content-claim")
        build_id = str(created["build"]["id"])
        barrier = Barrier(2)
        connection_ids: list[int] = []

        def claim_once():
            local = LearningCatalogRepository(Database(self.database_url))
            barrier.wait()
            with local.transaction() as conn:
                connection_ids.append(
                    int(conn.execute("SELECT CONNECTION_ID() AS id").fetchone()["id"])
                )
                return local.claim_next_content_item(
                    conn,
                    build_id=build_id,
                    now=10_000,
                    lease_ms=60_000,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _index: claim_once(), range(2)))
        winners = [claim for claim in claims if claim is not None]
        self.assertEqual(len(winners), 1, claims)
        self.assertEqual(len(set(connection_ids)), 2)
        first = winners[0]
        self.assertEqual(
            (first["subject"], first["skill_id"], first["variant_ordinal"]),
            ("chinese", "pinyin_syllables", 1),
        )
        self.assertEqual(int(first["attempt_count"]), 1)
        self.assertEqual(int(first["content_claim_attempt_ordinal"]), 1)
        self.assertEqual(first["content_phase"], "outline")
        self.assertEqual(
            first["active_generation_request_id"], first["generation_request_id"]
        )
        self.assertEqual(int(first["content_attempt_started_at"]), 10_000)
        self.assertEqual(
            int(first["content_provider_attempt_hard_deadline_at"]), 1_810_000
        )
        self.assertEqual(int(first["content_work_unit_deadline_at"]), 610_000)
        self.assertEqual(int(first["content_lease_expires_at"]), 70_000)
        with self.repository.transaction() as conn:
            dispatch_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_course_provider_dispatches "
                "WHERE build_item_id = ?",
                (first["id"],),
            ).fetchone()["count"]
        self.assertEqual(int(dispatch_count), 0)

        with self.repository.transaction() as conn:
            live_second = self.repository.claim_next_content_item(
                conn,
                build_id=build_id,
                now=20_000,
                lease_ms=60_000,
            )
        self.assertIsNone(live_second)

        immutable = {
            key: first[key]
            for key in (
                "id",
                "attempt_count",
                "active_generation_request_id",
                "content_attempt_started_at",
                "content_provider_attempt_hard_deadline_at",
                "content_work_unit_deadline_at",
            )
        }
        with self.repository.transaction() as conn:
            stale = self.repository.claim_next_content_item(
                conn,
                build_id=build_id,
                now=80_000,
                lease_ms=60_000,
            )
        self.assertIsNotNone(stale)
        self.assertEqual({key: stale[key] for key in immutable}, immutable)
        self.assertEqual(int(stale["content_lease_expires_at"]), 140_000)

        self._mark_course_ready(str(first["id"]), now=81_000)
        expected_canaries = [
            ("math", "number_sense_20", 1),
            ("english", "letters_sounds", 1),
        ]
        for index, identity in enumerate(expected_canaries, start=1):
            with self.repository.transaction() as conn:
                claimed = self.repository.claim_next_content_item(
                    conn,
                    build_id=build_id,
                    now=90_000 + index * 10_000,
                    lease_ms=1_000,
                )
            self.assertEqual(
                (claimed["subject"], claimed["skill_id"], claimed["variant_ordinal"]),
                identity,
            )
            self._mark_course_ready(str(claimed["id"]), now=90_500 + index * 10_000)

        with self.repository.transaction() as conn:
            expanded = self.repository.claim_next_content_item(
                conn,
                build_id=build_id,
                now=120_000,
                lease_ms=1_000,
            )
        self.assertEqual(
            (expanded["subject"], expanded["skill_id"], expanded["variant_ordinal"]),
            ("chinese", "pinyin_syllables", 2),
        )
        self._mark_course_ready(str(expanded["id"]), now=120_500)
        with self.repository.transaction() as conn:
            fair_next = self.repository.claim_next_content_item(
                conn,
                build_id=build_id,
                now=122_000,
                lease_ms=1_000,
            )
        self.assertEqual(
            (fair_next["subject"], fair_next["skill_id"], fair_next["variant_ordinal"]),
            ("math", "number_sense_20", 2),
        )

    def test_restricted_create_rejects_every_canonical_target_drift(self):
        mutations = []

        missing_subject = copy.deepcopy(self.target)
        missing_subject["subjects"].pop()
        mutations.append(("missing-subject", missing_subject))

        wrong_boundary = copy.deepcopy(self.target)
        wrong_boundary["courseTargets"][0]["boundaryVersion"] += ".wrong"
        mutations.append(("wrong-boundary", wrong_boundary))

        wrong_variant = copy.deepcopy(self.target)
        wrong_variant["courseTargets"][0]["variantOrdinal"] = 4
        mutations.append(("wrong-variant", wrong_variant))

        wrong_language = copy.deepcopy(self.target)
        wrong_language["courseTargets"][0]["instructionLanguageCode"] = "en-US"
        mutations.append(("wrong-language", wrong_language))

        wrong_dataset = copy.deepcopy(self.target)
        wrong_dataset["contentValidationDatasetSha256"] = "0" * 64
        mutations.append(("wrong-dataset", wrong_dataset))

        wrong_manifest = copy.deepcopy(self.target)
        wrong_manifest["schemaVersion"] = "mira.learning.preparation-target.v3"
        mutations.append(("wrong-manifest", wrong_manifest))

        wrong_canary = copy.deepcopy(self.target)
        wrong_canary["canaryManifest"]["targets"][0]["variantOrdinal"] = 2
        mutations.append(("wrong-canary", wrong_canary))

        injected_partial = copy.deepcopy(self.target)
        injected_partial["allowPartial"] = False
        mutations.append(("injected-allow-partial", injected_partial))

        for suffix, target in mutations:
            with self.subTest(suffix=suffix):
                with self.assertRaises(ApiError) as raised:
                    self.service.create_preparation_content_build(
                        request_id=f"cp2-drift-{suffix}",
                        title="drift",
                        preparation_target=target,
                        target_fingerprint=preparation_target_fingerprint(target),
                    )
                self.assertEqual(raised.exception.status_code, 409)

        with self.assertRaises(ApiError) as raised:
            self.service.create_preparation_content_build(
                request_id="cp2-wrong-fingerprint",
                title="wrong fingerprint",
                preparation_target=self.target,
                target_fingerprint="f" * 64,
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_repository_rejects_direct_and_persisted_canonical_manifest_drift(self):
        wrong_language = copy.deepcopy(self.target)
        wrong_language["courseTargets"][0]["targetLanguageCode"] = "fr-FR"
        with self.assertRaises(LearningCatalogBuildConflict):
            with self.repository.transaction() as conn:
                self.repository.create_or_get_content_build(
                    conn,
                    request_id="cp2-direct-target-drift",
                    curriculum_version=str(self.target["curriculumVersion"]),
                    title="direct drift",
                    target_spec=wrong_language,
                    target_fingerprint=preparation_target_fingerprint(wrong_language),
                    now=10_000,
                )

        build_id = str(self._create("cp2-persisted-target-drift")["build"]["id"])
        persisted_drift = copy.deepcopy(self.target)
        persisted_drift["courseTargets"][0]["instructionLanguageCode"] = "en-US"
        with self.repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_catalog_build_jobs
                SET target_spec_json = ? WHERE id = ?
                """,
                (self.repository.encode_json(persisted_drift), build_id),
            )
        with self.repository.transaction() as conn:
            claimed = self.repository.claim_next_content_item(
                conn,
                build_id=build_id,
                now=20_000,
                lease_ms=1_000,
            )
        self.assertIsNone(claimed)

    def test_repository_binds_canonical_curriculum_on_create_and_every_claim_row(self):
        wrong_curriculum = f"{self.target['curriculumVersion']}.wrong"
        with self.assertRaises(LearningCatalogBuildConflict):
            with self.repository.transaction() as conn:
                self.repository.create_or_get_content_build(
                    conn,
                    request_id="cp2-wrong-curriculum-create",
                    curriculum_version=wrong_curriculum,
                    title="wrong curriculum",
                    target_spec=self.target,
                    target_fingerprint=self.fingerprint,
                    now=10_000,
                )
        digest = hashlib.sha256(
            b"cp2-wrong-curriculum-create"
        ).hexdigest()[:24]
        with self.repository.transaction() as conn:
            counts = conn.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM learning_catalog_build_jobs
                    WHERE id = ?) AS builds,
                  (SELECT COUNT(*) FROM learning_catalog_releases
                    WHERE id = ?) AS releases
                """,
                (f"catalog_build_{digest}", f"catalog_release_{digest}"),
            ).fetchone()
        self.assertEqual((int(counts["builds"]), int(counts["releases"])), (0, 0))

        canonical_curriculum = str(self.target["curriculumVersion"])
        for column in ("build", "release", "item"):
            with self.subTest(column=column):
                created = self._create(f"cp2-claim-curriculum-{column}")
                build_id = str(created["build"]["id"])
                release_id = str(created["release"]["id"])
                with self.repository.transaction() as conn:
                    if column == "build":
                        conn.execute(
                            "UPDATE learning_catalog_build_jobs "
                            "SET curriculum_version = ? WHERE id = ?",
                            (wrong_curriculum, build_id),
                        )
                    elif column == "release":
                        conn.execute(
                            "UPDATE learning_catalog_releases "
                            "SET curriculum_version = ? WHERE id = ?",
                            (wrong_curriculum, release_id),
                        )
                    else:
                        conn.execute(
                            "UPDATE learning_catalog_build_items "
                            "SET curriculum_version = ? "
                            "WHERE build_job_id = ? ORDER BY id LIMIT 1",
                            (wrong_curriculum, build_id),
                        )
                with self.repository.transaction() as conn:
                    claimed = self.repository.claim_next_content_item(
                        conn,
                        build_id=build_id,
                        now=20_000,
                        lease_ms=1_000,
                    )
                self.assertIsNone(claimed)

                with self.repository.transaction() as conn:
                    conn.execute(
                        "UPDATE learning_catalog_build_jobs "
                        "SET curriculum_version = ? WHERE id = ?",
                        (canonical_curriculum, build_id),
                    )
                    conn.execute(
                        "UPDATE learning_catalog_releases "
                        "SET curriculum_version = ? WHERE id = ?",
                        (canonical_curriculum, release_id),
                    )
                    conn.execute(
                        "UPDATE learning_catalog_build_items "
                        "SET curriculum_version = ? WHERE build_job_id = ?",
                        (canonical_curriculum, build_id),
                    )

    def test_content_build_replay_requires_exact_immutable_thirty_item_set(self):
        mutable = self._create("cp2-replay-mutable")
        mutable_build_id = str(mutable["build"]["id"])
        with self.repository.transaction() as conn:
            claimed = self.repository.claim_next_content_item(
                conn,
                build_id=mutable_build_id,
                now=10_000,
                lease_ms=60_000,
            )
        self.assertIsNotNone(claimed)
        replay = self._create("cp2-replay-mutable")
        self.assertFalse(replay["created"])

        missing = self._create("cp2-replay-missing")
        missing_build_id = str(missing["build"]["id"])
        with self.repository.transaction() as conn:
            conn.execute(
                "DELETE FROM learning_catalog_build_items "
                "WHERE build_job_id = ? ORDER BY id LIMIT 1",
                (missing_build_id,),
            )
        with self.assertRaises(ApiError) as missing_error:
            self._create("cp2-replay-missing")
        self.assertEqual(missing_error.exception.status_code, 409)

        extra = self._create("cp2-replay-extra")
        extra_build_id = str(extra["build"]["id"])
        extra_release_id = str(extra["release"]["id"])
        with self.repository.transaction() as conn:
            conn.execute(
                """
                INSERT INTO learning_catalog_build_items(
                  id, build_job_id, release_id, grade_code, subject, skill_id,
                  curriculum_version, boundary_version, variant_ordinal,
                  status, attempt_count, generation_request_id,
                  execution_mode_snapshot, content_manifest_version_snapshot,
                  subject_ordinal, boundary_ordinal, content_phase,
                  content_gate_status, content_gate_attempt_count,
                  created_at, updated_at
                ) VALUES ('catalog_build_item_extra', ?, ?, 'primary_1', 'math',
                  'extra_skill', ?, 'extra.boundary.v1', 99, 'pending', 0,
                  'catalog_gen_extra', 'content_only', ?, 99, 99,
                  'not_started', 'not_started', 0, 10000, 10000)
                """,
                (
                    extra_build_id,
                    extra_release_id,
                    self.target["curriculumVersion"],
                    self.target["schemaVersion"],
                ),
            )
        with self.assertRaises(ApiError) as extra_error:
            self._create("cp2-replay-extra")
        self.assertEqual(extra_error.exception.status_code, 409)

        rogue = self.service.create(
            {
                "requestId": "cp2-replay-rogue-owner",
                "grades": ["primary_3"],
                "subjects": ["math"],
                "variantsPerBoundary": 1,
                "allowPartial": True,
            }
        )
        rogue_build_id = str(rogue["build"]["id"])
        rogue_release_id = str(rogue["release"]["id"])
        drift = self._create("cp2-replay-immutable-drift")
        drift_build_id = str(drift["build"]["id"])
        _build, _release, drift_items = self._rows(drift_build_id)
        item_id = str(drift_items[0]["id"])
        with self.repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET execution_mode_snapshot = 'full_pipeline',
                  content_phase = 'legacy_full_pipeline',
                  content_gate_status = 'not_applicable'
                WHERE id = ?
                """,
                (item_id,),
            )
        with self.assertRaises(ApiError) as mode_drift_error:
            self._create("cp2-replay-immutable-drift")
        self.assertEqual(mode_drift_error.exception.status_code, 409)
        with self.repository.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET execution_mode_snapshot = 'content_only',
                  content_phase = 'not_started',
                  content_gate_status = 'not_started'
                WHERE id = ?
                """,
                (item_id,),
            )
        immutable_mutations = (
            ("id", f"{item_id}_drift"),
            ("generation_request_id", "catalog_gen_drift"),
            ("build_job_id", rogue_build_id),
            ("release_id", rogue_release_id),
            ("grade_code", "primary_2"),
            ("subject", "drift_subject"),
            ("skill_id", "drift_skill"),
            ("curriculum_version", "drift.curriculum"),
            ("boundary_version", "drift.boundary"),
            ("variant_ordinal", 99),
            ("content_manifest_version_snapshot", "drift.manifest"),
            ("subject_ordinal", 99),
            ("boundary_ordinal", 99),
        )
        for column, value in immutable_mutations:
            with self.subTest(column=column):
                original_id = item_id
                with self.repository.transaction() as conn:
                    conn.execute(
                        f"UPDATE learning_catalog_build_items SET `{column}` = ? "
                        "WHERE id = ?",
                        (value, original_id),
                    )
                with self.assertRaises(ApiError) as drift_error:
                    self._create("cp2-replay-immutable-drift")
                self.assertEqual(drift_error.exception.status_code, 409)
                with self.repository.transaction() as conn:
                    if column == "id":
                        conn.execute(
                            "UPDATE learning_catalog_build_items SET id = ? "
                            "WHERE id = ?",
                            (item_id, value),
                        )
                    else:
                        conn.execute(
                            f"UPDATE learning_catalog_build_items SET `{column}` = ? "
                            "WHERE id = ?",
                            (drift_items[0][column], item_id),
                        )

    def test_release_item_pollution_blocks_content_create_replay_and_claim(self):
        request_id = "cp2-polluted-first-create"
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
        release_id = f"catalog_release_{digest}"
        self._insert_release_item_pollution(
            release_id=release_id,
            curriculum_version=str(self.target["curriculumVersion"]),
        )
        with self.assertRaises(ApiError) as create_error:
            self._create(request_id)
        self.assertEqual(create_error.exception.status_code, 409)

        replay = self._create("cp2-polluted-replay")
        replay_build_id = str(replay["build"]["id"])
        replay_release_id = str(replay["release"]["id"])
        self._insert_release_item_pollution(
            release_id=replay_release_id,
            curriculum_version=str(self.target["curriculumVersion"]),
        )
        with self.assertRaises(ApiError) as replay_error:
            self._create("cp2-polluted-replay")
        self.assertEqual(replay_error.exception.status_code, 409)
        with self.repository.transaction() as conn:
            claimed = self.repository.claim_next_content_item(
                conn,
                build_id=replay_build_id,
                now=20_000,
                lease_ms=1_000,
            )
        self.assertIsNone(claimed)

    def test_content_build_forced_overlap_and_existing_mutations_lock_in_order(self):
        request_id = "cp2-content-create-converge"
        absent_barrier = Barrier(2)
        winner_inserted = Event()
        loser_returned = Event()
        allow_winner_commit = Event()
        connection_ids: list[int] = []

        class PausingRepository(LearningCatalogRepository):
            def create_or_get_content_build(self, conn, **kwargs):
                result = super().create_or_get_content_build(conn, **kwargs)
                if result[1]:
                    winner_inserted.set()
                    if not allow_winner_commit.wait(timeout=10):
                        raise AssertionError("winner commit was not released")
                else:
                    loser_returned.set()
                return result

        def create_once():
            repository = PausingRepository(Database(self.database_url))
            with repository.transaction() as conn:
                connection_ids.append(
                    int(conn.execute("SELECT CONNECTION_ID() AS id").fetchone()["id"])
                )
                absent = repository.get_build_by_request(
                    conn,
                    request_id=request_id,
                )
                if absent is not None:
                    raise AssertionError("both creators must observe the absent hint")
                absent_barrier.wait(timeout=10)
                build, created = repository.create_or_get_content_build(
                    conn,
                    request_id=request_id,
                    curriculum_version=str(self.target["curriculumVersion"]),
                    title="Mira 一年级正式内容候选",
                    target_spec=self.target,
                    target_fingerprint=self.fingerprint,
                    now=10_000,
                )
                release = repository.get_release(
                    conn,
                    release_id=str(build["release_id"]),
                    for_update=True,
                )
                items = repository.list_build_items(
                    conn,
                    build_id=str(build["id"]),
                    for_update=True,
                )
            return build, release, items, created

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(create_once)
            second = executor.submit(create_once)
            self.assertTrue(winner_inserted.wait(timeout=10))
            self.assertFalse(loser_returned.wait(timeout=0.25))
            allow_winner_commit.set()
            results = [first.result(timeout=10), second.result(timeout=10)]
        self.assertEqual(sorted(result[3] for result in results), [False, True])
        self.assertEqual(results[0][0]["id"], results[1][0]["id"])
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertTrue(all(len(result[2]) == 30 for result in results))
        self.assertEqual(len(set(connection_ids)), 2)
        build_id = str(results[0][0]["id"])
        _build, _release, items = self._rows(build_id)
        self.assertEqual(len(items), 30)

        replay = self._create(request_id)
        self.assertFalse(replay["created"])
        self.assertEqual(replay["build"]["id"], build_id)

        other = self._create("cp2-content-other-request")
        self.assertNotEqual(other["build"]["id"], build_id)
        self.assertEqual(
            build_id,
            "catalog_build_"
            + hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24],
        )

        with self.assertRaises(LearningCatalogBuildConflict):
            with self.repository.transaction() as conn:
                self.repository.create_or_get_content_build(
                    conn,
                    request_id=request_id,
                    curriculum_version=str(self.target["curriculumVersion"]),
                    title="changed immutable title",
                    target_spec=self.target,
                    target_fingerprint=self.fingerprint,
                    now=20_000,
                )

        class RecordingConnection:
            def __init__(self, conn):
                self.conn = conn
                self.statements: list[str] = []

            def execute(self, sql, params=()):
                self.statements.append(" ".join(str(sql).upper().split()))
                return self.conn.execute(sql, params)

        with self.repository.transaction() as conn:
            recorded = RecordingConnection(conn)
            replay_build, replay_created = self.repository.create_or_get_content_build(
                recorded,
                request_id=request_id,
                curriculum_version=str(self.target["curriculumVersion"]),
                title="Mira 一年级正式内容候选",
                target_spec=self.target,
                target_fingerprint=self.fingerprint,
                now=30_000,
            )
        self.assertFalse(replay_created)
        mutation_or_lock = [
            sql
            for sql in recorded.statements
            if (
                "LEARNING_CATALOG_BUILD_JOBS" in sql
                or "LEARNING_CATALOG_RELEASES" in sql
                or "LEARNING_CATALOG_BUILD_ITEMS" in sql
            )
            and (" FOR UPDATE" in sql or sql.startswith(("INSERT", "UPDATE")))
        ]
        self.assertIn("FROM LEARNING_CATALOG_RELEASES", mutation_or_lock[0])
        self.assertIn("FOR UPDATE", mutation_or_lock[0])
        self.assertIn("FROM LEARNING_CATALOG_BUILD_JOBS", mutation_or_lock[1])
        self.assertIn("FOR UPDATE", mutation_or_lock[1])
        self.assertIn("FROM LEARNING_CATALOG_BUILD_ITEMS", mutation_or_lock[2])
        self.assertIn("FOR UPDATE", mutation_or_lock[2])
        self.assertFalse(
            any(sql.startswith(("INSERT", "UPDATE")) for sql in mutation_or_lock)
        )
        self.assertEqual(str(replay_build["id"]), build_id)

        legacy = self.service.create(
            {
                "requestId": "cp2-activation-item-locks",
                "grades": ["primary_1"],
                "subjects": ["chinese", "math", "english"],
                "variantsPerBoundary": 1,
                "allowPartial": True,
            }
        )
        legacy_build_id = str(legacy["build"]["id"])
        legacy_release_id = str(legacy["release"]["id"])
        with self.repository.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_jobs SET status = 'completed' "
                "WHERE id = ?",
                (legacy_build_id,),
            )
            conn.execute(
                "UPDATE learning_catalog_build_items SET status = 'ready' "
                "WHERE build_job_id = ?",
                (legacy_build_id,),
            )
        with self.assertRaises(LearningCatalogActivationError):
            with self.repository.transaction() as conn:
                activation_recorded = RecordingConnection(conn)
                self.repository.activate_release(
                    activation_recorded,
                    release_id=legacy_release_id,
                    expected_boundary_versions={
                        str(boundary["boundaryVersion"])
                        for boundary in self.target["boundaries"]
                    },
                    allow_partial=False,
                    now=40_000,
                )
        activation_locks = [
            sql
            for sql in activation_recorded.statements
            if " FOR UPDATE" in sql
            and (
                "LEARNING_CATALOG_BUILD_JOBS" in sql
                or "LEARNING_CATALOG_RELEASES" in sql
                or "LEARNING_CATALOG_BUILD_ITEMS" in sql
            )
        ]
        build_lock_index = next(
            index
            for index, sql in enumerate(activation_locks)
            if "FROM LEARNING_CATALOG_BUILD_JOBS" in sql
        )
        release_lock_index = next(
            index
            for index, sql in enumerate(activation_locks)
            if "FROM LEARNING_CATALOG_RELEASES WHERE ID = ?" in sql
        )
        item_lock_index = next(
            index
            for index, sql in enumerate(activation_locks)
            if "FROM LEARNING_CATALOG_BUILD_ITEMS" in sql
        )
        self.assertLess(release_lock_index, build_lock_index)
        self.assertLess(build_lock_index, item_lock_index)

        class TrackingActivationRepository(LearningCatalogRepository):
            def __init__(self, database):
                super().__init__(database)
                self.item_lock_flags: list[bool] = []

            def list_build_items(self, conn, *, build_id, for_update=False):
                self.item_lock_flags.append(bool(for_update))
                return super().list_build_items(
                    conn,
                    build_id=build_id,
                    for_update=for_update,
                )

        tracking = TrackingActivationRepository(Database(self.database_url))
        activation_service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=_UnexpectedDynamicGenerationService(),
            lesson_package_service=_UnexpectedLessonPackageService(),
        )
        activation_service.repository = tracking
        with self.assertRaises(ApiError):
            activation_service.activate(legacy_release_id)
        self.assertTrue(tracking.item_lock_flags)
        self.assertTrue(all(tracking.item_lock_flags))

    def test_full_and_content_existing_replay_lock_release_build_items_without_dml(self):
        content_request_id = "cp2-content-replay-release-mutex"
        self._create(content_request_id)

        full_request_id = "cp2-full-replay-release-mutex"
        full_targets = [
            boundary.to_catalog_payload()
            for boundary in PRIMARY_SKILL_BOUNDARIES
            if boundary.grade_code == "primary_1"
        ]
        full_target_spec = {
            "schemaVersion": "mira.learning.catalog-build-target.v1",
            "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
            "grades": ["primary_1"],
            "subjects": ["chinese", "math", "english"],
            "variantsPerBoundary": 1,
            "allowPartial": True,
            "boundaryVersions": [
                str(target["boundaryVersion"]) for target in full_targets
            ],
        }
        self.service.create(
            {
                "requestId": full_request_id,
                "grades": ["primary_1"],
                "subjects": ["chinese", "math", "english"],
                "variantsPerBoundary": 1,
                "allowPartial": True,
                "title": "full replay mutex",
            }
        )

        class RecordingConnection:
            def __init__(self, conn):
                self.conn = conn
                self.statements: list[str] = []

            def execute(self, sql, params=()):
                self.statements.append(" ".join(str(sql).upper().split()))
                return self.conn.execute(sql, params)

        traces: dict[str, list[str]] = {}
        with self.repository.transaction() as conn:
            recorded = RecordingConnection(conn)
            _build, created = self.repository.create_or_get_content_build(
                recorded,
                request_id=content_request_id,
                curriculum_version=str(self.target["curriculumVersion"]),
                title="Mira 一年级正式内容候选",
                target_spec=self.target,
                target_fingerprint=self.fingerprint,
                now=50_000,
            )
            self.assertFalse(created)
            traces["content"] = recorded.statements
        with self.repository.transaction() as conn:
            recorded = RecordingConnection(conn)
            _build, created = self.repository.create_or_get_build(
                recorded,
                request_id=full_request_id,
                curriculum_version=PRIMARY_CURRICULUM_VERSION,
                title="full replay mutex",
                target_spec=full_target_spec,
                targets=full_targets,
                variants_per_boundary=1,
                now=50_000,
            )
            self.assertFalse(created)
            traces["full"] = recorded.statements

        for mode, statements in traces.items():
            with self.subTest(mode=mode):
                authority = [
                    sql
                    for sql in statements
                    if (
                        "LEARNING_CATALOG_RELEASES" in sql
                        or "LEARNING_CATALOG_BUILD_JOBS" in sql
                        or "LEARNING_CATALOG_BUILD_ITEMS" in sql
                    )
                    and (
                        " FOR UPDATE" in sql
                        or sql.startswith(("INSERT", "UPDATE"))
                    )
                ]
                self.assertGreaterEqual(len(authority), 3)
                self.assertIn("FROM LEARNING_CATALOG_RELEASES", authority[0])
                self.assertIn("FOR UPDATE", authority[0])
                self.assertIn("FROM LEARNING_CATALOG_BUILD_JOBS", authority[1])
                self.assertIn("FOR UPDATE", authority[1])
                self.assertIn("FROM LEARNING_CATALOG_BUILD_ITEMS", authority[2])
                self.assertIn("FOR UPDATE", authority[2])
                self.assertFalse(
                    any(sql.startswith(("INSERT", "UPDATE")) for sql in authority)
                )

    def test_expired_content_work_or_outer_deadline_is_never_reclaimed(self):
        first_build = str(self._create("cp2-expired-work")["build"]["id"])
        with self.repository.transaction() as conn:
            first = self.repository.claim_next_content_item(
                conn,
                build_id=first_build,
                now=1_000,
                lease_ms=10,
            )
        with self.repository.transaction() as conn:
            expired_work = self.repository.claim_next_content_item(
                conn,
                build_id=first_build,
                now=int(first["content_work_unit_deadline_at"]) + 1,
                lease_ms=10,
            )
        self.assertIsNone(expired_work)

        second_build = str(self._create("cp2-expired-outer")["build"]["id"])
        with self.repository.transaction() as conn:
            second = self.repository.claim_next_content_item(
                conn,
                build_id=second_build,
                now=2_000,
                lease_ms=10,
            )
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET content_work_unit_deadline_at =
                    content_provider_attempt_hard_deadline_at
                WHERE id = ?
                """,
                (second["id"],),
            )
        with self.repository.transaction() as conn:
            expired_outer = self.repository.claim_next_content_item(
                conn,
                build_id=second_build,
                now=int(second["content_provider_attempt_hard_deadline_at"]) + 1,
                lease_ms=10,
            )
        self.assertIsNone(expired_outer)

    def test_all_legacy_course_package_and_activation_paths_isolate_content_build(self):
        created = self._create("cp2-legacy-isolation")
        build_id = str(created["build"]["id"])
        release_id = str(created["release"]["id"])

        with self.assertRaises(ApiError) as run_error:
            self.service.run(build_id, {"maxItems": 1})
        self.assertEqual(run_error.exception.status_code, 409)

        with self.repository.transaction() as conn:
            old_claim = self.repository.claim_next_item(
                conn,
                build_id=build_id,
                now=10_000,
                retry_failed=True,
                stale_before=9_000,
            )
        self.assertIsNone(old_claim)

        _build, _release, items = self._rows(build_id)
        with self.repository.transaction() as conn:
            package_claim = self.repository.claim_package_for_item(
                conn,
                item_id=str(items[0]["id"]),
                now=10_000,
            )
        self.assertIsNone(package_claim)

        with self.assertRaises(LearningCatalogActivationError):
            with self.repository.transaction() as conn:
                self.repository.activate_release(
                    conn,
                    release_id=release_id,
                    expected_boundary_versions={
                        str(item["boundaryVersion"])
                        for item in self.target["boundaries"]
                    },
                    allow_partial=False,
                    now=10_000,
                )

        with self.assertRaises(ApiError) as activate_error:
            self.service.activate(release_id)
        self.assertEqual(activate_error.exception.status_code, 409)
        self.assertEqual(self.dynamic.calls, [])
        self.assertEqual(self.lesson.calls, [])
        self.assertEqual(self.validator.calls, [])
        with self.repository.transaction() as conn:
            release = self.repository.get_release(conn, release_id=release_id)
            release_item_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_catalog_release_items "
                "WHERE release_id = ?",
                (release_id,),
            ).fetchone()["count"]
        self.assertEqual(release["status"], "draft")
        self.assertEqual(int(release_item_count), 0)


if __name__ == "__main__":
    unittest.main()
