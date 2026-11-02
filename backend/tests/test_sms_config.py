from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from flask import Flask

from core.config import (
    AppConfig,
    ConfigError,
    _validate_sms_config,
    validate_flask_config,
)
from services import service_factory


class SmsConfigTest(unittest.TestCase):
    def valid_tencent(self) -> dict:
        return {
            "app_env": "production",
            "dev_adapters_enabled": False,
            "provider": "tencent",
            "template_id": "123456",
            "secret_id": "AKID-sms-fixture",
            "secret_key": "private-sms-fixture",
            "sdk_app_id": "1400006666",
            "sign_name": "米拉守护",
            "region": "ap-guangzhou",
            "timeout_seconds": 10,
            "code_ttl_seconds": 300,
            "resend_cooldown_seconds": 60,
            "hourly_send_limit": 300,
            "source_window_seconds": 600,
            "source_send_limit": 10,
            "max_attempts": 5,
            "code_pepper": "private-sms-code-pepper-value-1234567890",
        }

    def test_environment_loads_dedicated_sms_configuration(self):
        values = {
            "APP_ENV": "test",
            "APP_SMS_PROVIDER": "tencent",
            "APP_SMS_TENCENT_SECRET_ID": "AKID-sms-fixture",
            "APP_SMS_TENCENT_SECRET_KEY": "private-sms-fixture",
            "APP_SMS_TENCENT_SDK_APP_ID": "1400006666",
            "APP_SMS_TENCENT_SIGN_NAME": "米拉守护",
            "APP_SMS_TEMPLATE_ID": "123456",
            "APP_SMS_TENCENT_REGION": "ap-nanjing",
            "APP_SMS_TENCENT_TIMEOUT_SECONDS": "8.5",
            "APP_SMS_CODE_PEPPER": "private-sms-code-pepper-value-1234567890",
        }
        with patch.dict(os.environ, values, clear=True):
            config = AppConfig.from_env()

        self.assertEqual(config.SMS_PROVIDER, "tencent")
        self.assertEqual(config.SMS_TENCENT_SECRET_ID, "AKID-sms-fixture")
        self.assertEqual(config.SMS_TENCENT_SECRET_KEY, "private-sms-fixture")
        self.assertEqual(config.SMS_TENCENT_SDK_APP_ID, "1400006666")
        self.assertEqual(config.SMS_TENCENT_SIGN_NAME, "米拉守护")
        self.assertEqual(config.SMS_TEMPLATE_ID, "123456")
        self.assertEqual(config.SMS_TENCENT_REGION, "ap-nanjing")
        self.assertEqual(config.SMS_TENCENT_TIMEOUT_SECONDS, 8.5)
        self.assertEqual(
            config.SMS_CODE_PEPPER,
            "private-sms-code-pepper-value-1234567890",
        )

    def test_tencent_provider_requires_every_runtime_value(self):
        valid = self.valid_tencent()
        fields = {
            "template_id": "APP_SMS_TEMPLATE_ID",
            "secret_id": "APP_SMS_TENCENT_SECRET_ID",
            "secret_key": "APP_SMS_TENCENT_SECRET_KEY",
            "sdk_app_id": "APP_SMS_TENCENT_SDK_APP_ID",
            "sign_name": "APP_SMS_TENCENT_SIGN_NAME",
            "region": "APP_SMS_TENCENT_REGION",
        }
        for field, env_name in fields.items():
            with self.subTest(field=field), self.assertRaisesRegex(ConfigError, env_name):
                _validate_sms_config(**{**valid, field: ""})

    def test_production_accepts_only_tencent_and_dev_provider_stays_local(self):
        valid = self.valid_tencent()
        _validate_sms_config(**valid)
        with self.assertRaisesRegex(ConfigError, "required in production"):
            _validate_sms_config(**{**valid, "provider": ""})
        with self.assertRaisesRegex(ConfigError, "development/test"):
            _validate_sms_config(**{**valid, "provider": "development"})
        _validate_sms_config(
            **{
                **valid,
                "app_env": "test",
                "dev_adapters_enabled": True,
                "provider": "development",
            }
        )

    def test_production_startup_accepts_complete_tencent_config_and_rejects_missing(self):
        config = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://user:pass@db.example/mira",
            "STUDENT_AUTH_PEPPER": "private-production-student-auth-pepper",
            "DEV_ADAPTERS_ENABLED": False,
            "SMS_PROVIDER": "tencent",
            "SMS_TENCENT_SECRET_ID": "AKID-sms-fixture",
            "SMS_TENCENT_SECRET_KEY": "private-sms-fixture",
            "SMS_TENCENT_SDK_APP_ID": "1400006666",
            "SMS_TENCENT_SIGN_NAME": "米拉守护",
            "SMS_TEMPLATE_ID": "123456",
            "SMS_TENCENT_REGION": "ap-guangzhou",
            "SMS_TENCENT_TIMEOUT_SECONDS": 10,
            "SMS_CODE_TTL_SECONDS": 300,
            "SMS_RESEND_COOLDOWN_SECONDS": 60,
            "SMS_HOURLY_SEND_LIMIT": 300,
            "SMS_SOURCE_WINDOW_SECONDS": 600,
            "SMS_SOURCE_SEND_LIMIT": 10,
            "SMS_MAX_ATTEMPTS": 5,
            "SMS_CODE_PEPPER": "private-sms-code-pepper-value-1234567890",
            "CAMERA_RUNTIME_PROVIDER": "disabled",
            "INTERNAL_API_TOKEN": "internal-test-token",
            "CORS_ORIGINS": ["https://parent.example.com"],
        }

        validate_flask_config(config)
        with self.assertRaisesRegex(ConfigError, "APP_SMS_TENCENT_SECRET_KEY"):
            validate_flask_config({**config, "SMS_TENCENT_SECRET_KEY": ""})

    def test_tencent_ids_timeout_and_template_ttl_are_validated(self):
        valid = self.valid_tencent()
        invalid = (
            ("sdk_app_id", "not-numeric", "SDK_APP_ID"),
            ("template_id", "login-code", "TEMPLATE_ID"),
            ("timeout_seconds", 31, "TIMEOUT_SECONDS"),
            ("code_ttl_seconds", 301, "CODE_TTL_SECONDS"),
            ("region", "Guangzhou", "REGION"),
            ("resend_cooldown_seconds", 0, "RESEND_COOLDOWN_SECONDS"),
            ("hourly_send_limit", 0, "HOURLY_SEND_LIMIT"),
            ("source_window_seconds", 30, "SOURCE_WINDOW_SECONDS"),
            ("source_send_limit", 301, "SOURCE_SEND_LIMIT"),
            ("max_attempts", 2, "MAX_ATTEMPTS"),
            ("code_pepper", "short", "CODE_PEPPER"),
        )
        for field, value, message in invalid:
            with self.subTest(field=field), self.assertRaisesRegex(ConfigError, message):
                _validate_sms_config(**{**valid, field: value})

    def test_service_factory_passes_only_server_configuration_to_adapter(self):
        app = Flask(__name__)
        app.config.update(
            SMS_PROVIDER="tencent",
            SMS_TENCENT_SECRET_ID="AKID-sms-fixture",
            SMS_TENCENT_SECRET_KEY="private-sms-fixture",
            SMS_TENCENT_SDK_APP_ID="1400006666",
            SMS_TENCENT_SIGN_NAME="米拉守护",
            SMS_TEMPLATE_ID="123456",
            SMS_TENCENT_REGION="ap-guangzhou",
            SMS_CODE_TTL_SECONDS=300,
            SMS_TENCENT_TIMEOUT_SECONDS=10.0,
        )
        with app.app_context(), patch.object(
            service_factory, "TencentCloudSmsProvider"
        ) as provider:
            self.assertIs(service_factory.sms_provider(), provider.return_value)
        provider.assert_called_once_with(
            secret_id="AKID-sms-fixture",
            secret_key="private-sms-fixture",
            sdk_app_id="1400006666",
            sign_name="米拉守护",
            template_id="123456",
            region="ap-guangzhou",
            code_ttl_seconds=300,
            timeout_seconds=10.0,
        )


if __name__ == "__main__":
    unittest.main()
