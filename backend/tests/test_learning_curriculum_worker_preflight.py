from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from workers import learning_curriculum_preparation_worker as worker


class LearningCurriculumWorkerPreflightTest(unittest.TestCase):
    def test_progress_ticks_continue_quickly_without_changing_idle_polling(self):
        self.assertEqual(
            worker._wait_seconds_after_tick(
                {"claimed": 1, "resultCode": "progressed"}, 15
            ),
            2,
        )
        self.assertEqual(
            worker._wait_seconds_after_tick({"claimed": 0}, 15),
            15,
        )
        self.assertEqual(
            worker._wait_seconds_after_tick({"claimed": 0}, 2),
            5,
        )

    def test_openmaic_preflight_does_not_require_camera_kimi_configuration(self):
        config = {
            "OPENMAIC_FULL_RUNTIME_ENABLED": True,
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED": True,
            "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED": True,
            "OPENMAIC_FULL_RUNTIME_INTERNAL_URL": "http://127.0.0.1:3100",
            "AI_MODEL": "",
            "AI_BASE_URL": "",
            "AI_API_KEY": "",
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"available": True}),
            stderr="",
        )
        with patch.object(
            worker,
            "learning_curriculum_preparation_config_projection",
            return_value=SimpleNamespace(
                runner_enabled=True,
                content_generation_enabled=True,
            ),
        ), patch.dict(worker.app.config, config), patch.dict(
            os.environ,
            {"INTERNAL_API_TOKEN": "openmaic-private-token"},
            clear=True,
        ), patch.object(worker.shutil, "which", return_value="/usr/bin/node"), patch.object(
            worker, "SIDECAR_CLI", Path(__file__)
        ), patch.object(worker.subprocess, "run", return_value=completed) as run:
            worker._preflight()

        run.assert_called_once()

    def test_camera_kimi_cannot_replace_the_openmaic_internal_token(self):
        config = {
            "OPENMAIC_FULL_RUNTIME_ENABLED": True,
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED": True,
            "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED": True,
            "OPENMAIC_FULL_RUNTIME_INTERNAL_URL": "http://127.0.0.1:3100",
            "AI_MODEL": "kimi-k2.6",
            "AI_BASE_URL": "https://api.moonshot.cn/v1",
            "AI_API_KEY": "camera-only-key",
        }
        with patch.object(
            worker,
            "learning_curriculum_preparation_config_projection",
            return_value=SimpleNamespace(
                runner_enabled=True,
                content_generation_enabled=True,
            ),
        ), patch.dict(worker.app.config, config), patch.dict(
            os.environ,
            {"APP_AI_API_KEY": "camera-only-key"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "INTERNAL_API_TOKEN"):
                worker._preflight()


if __name__ == "__main__":
    unittest.main()
