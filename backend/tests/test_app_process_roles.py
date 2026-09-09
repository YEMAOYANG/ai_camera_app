from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import app as app_module
from tests.support import fresh_test_config


class AppProcessRoleOwnershipTest(unittest.TestCase):
    def test_curriculum_worker_owns_runtime_generation_reconciliation(self):
        with patch.dict(
            os.environ,
            {"MIRA_PROCESS_ROLE": "curriculum-worker"},
        ), patch.object(
            app_module, "start_openmaic_runtime_generation"
        ) as start_runtime:
            app_module.create_app(fresh_test_config())

        start_runtime.assert_called_once()

    def test_api_process_does_not_duplicate_runtime_generation_worker(self):
        with patch.dict(
            os.environ,
            {"MIRA_PROCESS_ROLE": "api"},
        ), patch.object(
            app_module, "start_openmaic_runtime_generation"
        ) as start_runtime:
            app_module.create_app(fresh_test_config())

        start_runtime.assert_not_called()


if __name__ == "__main__":
    unittest.main()
