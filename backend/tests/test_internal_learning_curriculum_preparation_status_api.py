from __future__ import annotations

from contextlib import contextmanager
import subprocess
import unittest
from unittest.mock import patch

from app import create_app
from core.config import ConfigError, validate_flask_config
from core.database import Database
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import (
    learning_curriculum_preparation_runner,
)
from tests.support import fresh_test_config


STATUS_PATH = "/internal/learning/curriculum-preparations/runner/status"


class InternalLearningCurriculumPreparationStatusApiTest(unittest.TestCase):
    def setUp(self):
        self.token = "task9-internal-status-token"
        self.app = create_app(fresh_test_config(INTERNAL_API_TOKEN=self.token))
        self.client = self.app.test_client()
        self.headers = {
            "X-Mira-Internal-Token": self.token,
            "X-Mira-Internal-Source": "task9-observer",
        }

    def test_authentication_precedes_query_and_every_status_read(self):
        with patch.object(
            learning_curriculum_preparation_runner,
            "read_only_status",
            side_effect=AssertionError("status read before internal auth"),
        ) as status:
            unauthorized = self.client.get(
                STATUS_PATH,
                query_string={"unexpected": "secret"},
            )

        self.assertEqual(unauthorized.status_code, 401, unauthorized.json)
        self.assertEqual(status.call_count, 0)

        authenticated = self.client.get(
            STATUS_PATH,
            query_string={"unexpected": "value"},
            headers=self.headers,
        )
        self.assertEqual(authenticated.status_code, 400, authenticated.json)

    def test_invalid_runtime_config_returns_stable_503_before_status_read(self):
        self.app.config[
            "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST"
        ] = ("primary_1",)
        with patch.object(
            learning_curriculum_preparation_runner,
            "read_only_status",
            side_effect=AssertionError("status read with invalid config"),
        ) as status:
            response = self.client.get(STATUS_PATH, headers=self.headers)

        self.assertEqual(response.status_code, 503, response.json)
        self.assertEqual(
            response.json["error"],
            "learning_preparation_runner_config_invalid",
        )
        self.assertEqual(status.call_count, 0)

    def test_authorized_status_has_exact_whitelist_and_no_run_route(self):
        observed = {
            "lastRunAt": None,
            "lastResultCode": None,
            "lastStage": None,
            "lastErrorCode": None,
            "claimablePlanCount": 0,
            "runningPlanCount": 0,
            "expiredLeaseCount": 0,
        }
        with patch.object(
            learning_curriculum_preparation_runner,
            "read_only_status",
            return_value=observed,
        ) as status:
            response = self.client.get(STATUS_PATH, headers=self.headers)

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(status.call_count, 1)
        self.assertEqual(
            set(response.json),
            {"ok", "schemaVersion", "internal", "runner"},
        )
        self.assertEqual(
            response.json["schemaVersion"],
            "mira.learning.preparation-runner-status.v1",
        )
        self.assertEqual(set(response.json["internal"]), {"auditId"})
        self.assertEqual(
            set(response.json["runner"]),
            {
                "enabled",
                "contentGenerationEnabled",
                "gradeAllowlist",
                "maxProviderSubcallsPerTick",
                "observationScope",
                *observed.keys(),
            },
        )
        self.assertFalse(response.json["runner"]["enabled"])
        self.assertFalse(response.json["runner"]["contentGenerationEnabled"])
        self.assertEqual(response.json["runner"]["gradeAllowlist"], ["primary_1"])
        self.assertEqual(response.json["runner"]["maxProviderSubcallsPerTick"], 1)
        self.assertEqual(response.json["runner"]["observationScope"], "process")

        self.assertEqual(
            self.client.post(
                "/internal/learning/curriculum-preparations/runner/run",
                headers=self.headers,
            ).status_code,
            404,
        )

    def test_real_status_is_select_only_and_guard_audit_is_the_only_write(self):
        business_tables = (
            "learning_curriculum_preparation_plans",
            "learning_curriculum_preparation_events",
            "learning_catalog_releases",
            "learning_catalog_build_jobs",
            "learning_catalog_build_items",
            "learning_catalog_release_items",
            "learning_course_provider_dispatches",
        )
        database = Database(self.app.config["DATABASE_URL"])

        def snapshot_business_rows():
            with database.transaction() as conn:
                return {
                    table: tuple(conn.execute(f"SELECT * FROM `{table}`").fetchall())
                    for table in business_tables
                }

        sql: list[str] = []

        class _RecordingConnection:
            def __init__(self, conn):
                self._conn = conn

            def execute(self, statement, params=()):
                sql.append(statement)
                return self._conn.execute(statement, params)

        class _RecordingDatabase:
            @contextmanager
            def transaction(self):
                with database.transaction() as conn:
                    yield _RecordingConnection(conn)

        repository = LearningCurriculumPreparationRepository(_RecordingDatabase())
        original_repository = learning_curriculum_preparation_runner.repository
        learning_curriculum_preparation_runner.repository = repository
        before = snapshot_business_rows()
        try:
            with patch(
                "services.service_factory.learning_curriculum_preparation_checkpoint_adapter",
                side_effect=AssertionError("status resolved execution adapter"),
            ), patch(
                "services.service_factory._checkpoint_question_phase_profile",
                side_effect=AssertionError("status resolved Provider profile"),
            ), patch.object(
                learning_curriculum_preparation_runner,
                "run_once",
                side_effect=AssertionError("status ran preparation work"),
            ), patch.object(
                subprocess,
                "Popen",
                side_effect=AssertionError("status started a process"),
            ):
                response = self.client.get(STATUS_PATH, headers=self.headers)
        finally:
            learning_curriculum_preparation_runner.repository = original_repository

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(before, snapshot_business_rows())
        self.assertEqual(len(sql), 3)
        for statement in sql:
            normalized = " ".join(statement.split()).upper()
            self.assertTrue(normalized.startswith("SELECT COUNT(*) AS COUNT"))
            self.assertNotIn("FOR UPDATE", normalized)
            self.assertIn("GRADE_CODE =", normalized)
            self.assertIn("TARGET_FINGERPRINT =", normalized)
        with database.transaction() as conn:
            audit_rows = conn.execute("SELECT * FROM audit_events").fetchall()
        self.assertEqual(len(audit_rows), 1)
        self.assertEqual(audit_rows[0]["accepted"], 1)
        self.assertEqual(
            audit_rows[0]["route"],
            "/internal/learning/curriculum-preparations/runner/status",
        )
        self.assertEqual(audit_rows[0]["reason"], "ok")
        self.assertIsNone(audit_rows[0]["payload_ref"])

    def test_frozen_defaults_and_status_count_use_exact_primary_one_scope(self):
        self.assertFalse(
            self.app.config[
                "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED"
            ]
        )
        self.assertEqual(
            self.app.config["LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST"],
            ["primary_1"],
        )
        self.assertEqual(
            self.app.config[
                "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK"
            ],
            1,
        )
        self.assertEqual(
            self.app.config[
                "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD"
            ],
            1,
        )
        self.assertTrue(
            self.app.config["LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED"]
        )
        self.assertTrue(
            self.app.config[
                "LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND"
            ]
        )
        self.assertFalse(
            self.app.config[
                "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED"
            ]
        )

        strict_mutations = (
            ("LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED", "0"),
            ("LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED", 0),
            ("LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST", ("primary_1",)),
            (
                "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK",
                True,
            ),
            ("LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD", True),
            ("LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED", 1),
            ("LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND", "1"),
            ("LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED", 0),
        )
        for key, value in strict_mutations:
            with self.subTest(key=key, value=value):
                mutated = dict(self.app.config)
                mutated[key] = value
                with self.assertRaises(ConfigError):
                    validate_flask_config(mutated)

        class _Repository:
            class _Transaction:
                def __enter__(self):
                    return object()

                def __exit__(self, *_args):
                    return False

            def __init__(self):
                self.kwargs = None

            def transaction(self):
                return self._Transaction()

            def count_runner_scope(self, _conn, **kwargs):
                self.kwargs = kwargs
                return {
                    "claimablePlanCount": 0,
                    "runningPlanCount": 0,
                    "expiredLeaseCount": 0,
                }

        repository = _Repository()
        original_repository = learning_curriculum_preparation_runner.repository
        learning_curriculum_preparation_runner.repository = repository
        try:
            learning_curriculum_preparation_runner.read_only_status(
                self.app,
                now_ms=1234,
            )
        finally:
            learning_curriculum_preparation_runner.repository = original_repository
        self.assertEqual(repository.kwargs["grade_code"], "primary_1")
        self.assertEqual(
            repository.kwargs["target_fingerprint"],
            preparation_target_fingerprint(build_preparation_target("primary_1")),
        )


if __name__ == "__main__":
    unittest.main()
