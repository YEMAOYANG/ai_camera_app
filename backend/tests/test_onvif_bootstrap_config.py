from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import AppConfig, ConfigError, validate_flask_config


class OnvifBootstrapConfigTest(unittest.TestCase):
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
            "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED": True,
            "ONVIF_BOOTSTRAP_USERNAME": "admin",
            "ONVIF_BOOTSTRAP_PASSWORD": "camera-password",
        }

        with self.assertRaisesRegex(ConfigError, "development/test only"):
            validate_flask_config(config)


if __name__ == "__main__":
    unittest.main()
