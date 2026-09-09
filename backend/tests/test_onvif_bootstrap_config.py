from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import (
    AppConfig,
    ConfigError,
    apply_test_defaults,
    validate_flask_config,
)


class OnvifBootstrapConfigTest(unittest.TestCase):
    def test_curriculum_preparation_runner_defaults_disabled_in_tests(self):
        config = apply_test_defaults({"TESTING": True})
        self.assertFalse(config["LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED"])
        self.assertEqual(
            config["LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS"],
            240,
        )

    def test_curriculum_preparation_environment_default_has_v71_lease_budget(self):
        with patch.dict(os.environ, {"APP_ENV": "test"}, clear=True):
            config = AppConfig.from_env()

        self.assertEqual(
            config.LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS,
            240,
        )

    def test_curriculum_preparation_runner_interval_and_lease_are_bounded(self):
        base = {
            "APP_ENV": "test",
            "DATABASE_URL": "mysql+pymysql://test:test@127.0.0.1:3306/ai_camera_app_test",
            "DEV_ADAPTERS_ENABLED": True,
            "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED": False,
        }
        with self.assertRaisesRegex(ConfigError, "INTERVAL_SECONDS"):
            validate_flask_config(
                {
                    **base,
                    "LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS": 4,
                    "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS": 90,
                }
            )
        with self.assertRaisesRegex(ConfigError, "LEASE_SECONDS"):
            validate_flask_config(
                {
                    **base,
                    "LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS": 5,
                    "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS": 239,
                }
            )
        validate_flask_config(
            {
                **base,
                "LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS": 5,
                "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS": 240,
            }
        )
    def test_app_config_requires_explicit_engineering_switch(self):
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "development",
                "APP_ENABLE_DEV_ADAPTERS": "1",
                "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED": "0",
                "ONVIF_BOOTSTRAP_USERNAME": "admin",
                "ONVIF_BOOTSTRAP_PASSWORD": "camera-password",
            },
        ):
            with self.assertRaisesRegex(
                ConfigError,
                "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED",
            ):
                AppConfig.from_env().validate()

    def test_enabled_engineering_credentials_require_both_values(self):
        config = {
            "APP_ENV": "test",
            "DEV_ADAPTERS_ENABLED": True,
            "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED": True,
            "ONVIF_BOOTSTRAP_USERNAME": "admin",
            "ONVIF_BOOTSTRAP_PASSWORD": "",
        }

        with self.assertRaisesRegex(ConfigError, "must be set together"):
            validate_flask_config(config)

    def test_production_rejects_engineering_credentials(self):
        config = {
            "APP_ENV": "production",
            "DEV_ADAPTERS_ENABLED": False,
            "STUDENT_AUTH_PEPPER": "private-production-student-auth-pepper",
            "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED": True,
            "ONVIF_BOOTSTRAP_USERNAME": "admin",
            "ONVIF_BOOTSTRAP_PASSWORD": "camera-password",
        }

        with self.assertRaisesRegex(ConfigError, "development/test only"):
            validate_flask_config(config)


if __name__ == "__main__":
    unittest.main()
