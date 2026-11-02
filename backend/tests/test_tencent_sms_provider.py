from __future__ import annotations

import logging
import unittest

from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from core.errors import AuthError
from integrations.sms.tencent_cloud import (
    TencentCloudSmsProvider,
    TencentSmsConfigurationError,
)
from services.sms_provider import DevelopmentSmsProvider


class FakeRequest:
    pass


class FakeStatus:
    def __init__(self, code="Ok", serial_no="serial-1"):
        self.Code = code
        self.SerialNo = serial_no


class FakeResponse:
    def __init__(self, *, code="Ok", request_id="request-1", statuses=None):
        self.RequestId = request_id
        self.SendStatusSet = [FakeStatus(code)] if statuses is None else statuses


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.requests = []

    def SendSms(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def provider(client):
    return TencentCloudSmsProvider(
        secret_id="secret-id",
        secret_key="secret-key",
        sdk_app_id="1400000000",
        sign_name="米拉守护",
        template_id="1234567",
        region="ap-guangzhou",
        code_ttl_seconds=300,
        timeout_seconds=10,
        client=client,
        request_factory=FakeRequest,
    )


class TencentCloudSmsProviderTest(unittest.TestCase):
    def test_success_uses_current_request_shape_and_returns_bounded_receipt(self):
        client = FakeClient()

        delivery = provider(client).send_verification_code("13800138000", "042731")

        self.assertEqual(delivery.provider, "tencent")
        self.assertEqual(delivery.template_id, "1234567")
        self.assertEqual(delivery.delivery_status, "accepted")
        self.assertEqual(delivery.provider_request_id, "request-1")
        self.assertEqual(delivery.provider_serial_no, "serial-1")
        self.assertIsNone(delivery.debug_code)
        request = client.requests[0]
        self.assertEqual(request.SmsSdkAppId, "1400000000")
        self.assertEqual(request.SignName, "米拉守护")
        self.assertEqual(request.TemplateId, "1234567")
        self.assertEqual(request.TemplateParamSet, ["042731", "5"])
        self.assertEqual(request.PhoneNumberSet, ["+8613800138000"])
        self.assertEqual(request.SessionContext, "")
        self.assertEqual(request.ExtendCode, "")
        self.assertEqual(request.SenderId, "")

    def test_development_provider_only_echoes_caller_generated_code(self):
        delivery = DevelopmentSmsProvider().send_verification_code(
            "13800138000", "042731"
        )
        self.assertEqual(delivery.debug_code, "042731")
        self.assertEqual(delivery.delivery_status, "delivered")

    def test_provider_rate_limit_has_stable_public_error(self):
        client = FakeClient(FakeResponse(code="LimitExceeded.PhoneNumberThirtySecondLimit"))
        with self.assertLogs("integrations.sms.tencent_cloud", level="WARNING") as logs:
            with self.assertRaises(AuthError) as caught:
                provider(client).send_verification_code("13800138000", "042731")
        self.assertEqual(caught.exception.code, "sms_rate_limited")
        self.assertEqual(caught.exception.status_code, 429)
        joined = "\n".join(logs.output)
        self.assertNotIn("13800138000", joined)
        self.assertNotIn("042731", joined)
        self.assertNotIn("secret-key", joined)

    def test_configuration_rejection_is_not_exposed_to_client(self):
        client = FakeClient(
            FakeResponse(code="FailedOperation.TemplateIncorrectOrUnapproved")
        )
        with self.assertLogs("integrations.sms.tencent_cloud", level="WARNING"):
            with self.assertRaises(AuthError) as caught:
                provider(client).send_verification_code("13800138000", "042731")
        self.assertEqual(caught.exception.code, "sms_provider_misconfigured")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("Template", caught.exception.message)

    def test_known_non_configuration_rejection_is_bad_gateway(self):
        client = FakeClient(FakeResponse(code="FailedOperation.PhoneNumberInBlacklist"))
        with self.assertLogs("integrations.sms.tencent_cloud", level="WARNING"):
            with self.assertRaises(AuthError) as caught:
                provider(client).send_verification_code("13800138000", "042731")
        self.assertEqual(caught.exception.code, "sms_provider_rejected")
        self.assertEqual(caught.exception.status_code, 502)

    def test_timeout_is_not_retried_and_is_reported_as_unknown(self):
        client = FakeClient(error=TimeoutError("contains 042731"))
        with self.assertLogs("integrations.sms.tencent_cloud", level="WARNING") as logs:
            with self.assertRaises(AuthError) as caught:
                provider(client).send_verification_code("13800138000", "042731")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(caught.exception.code, "sms_provider_unavailable")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("042731", "\n".join(logs.output))

    def test_sdk_wrapped_network_error_is_unknown_and_never_retried(self):
        client = FakeClient(
            error=TencentCloudSDKException(
                "ClientNetworkError",
                "connection failed after sending request containing 042731",
                "request-network-1",
            )
        )
        with self.assertLogs("integrations.sms.tencent_cloud", level="WARNING") as logs:
            with self.assertRaises(AuthError) as caught:
                provider(client).send_verification_code("13800138000", "042731")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(caught.exception.code, "sms_provider_unavailable")
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("042731", "\n".join(logs.output))

    def test_sdk_debug_logging_is_raised_above_sensitive_request_bodies(self):
        sdk_logger = logging.getLogger("tencentcloud_sdk_common")
        sdk_logger.setLevel(logging.DEBUG)

        provider(FakeClient())

        self.assertGreaterEqual(sdk_logger.getEffectiveLevel(), logging.WARNING)

    def test_invalid_provider_response_is_unavailable(self):
        client = FakeClient(FakeResponse(statuses=[]))
        with self.assertLogs("integrations.sms.tencent_cloud", level="WARNING"):
            with self.assertRaises(AuthError) as caught:
                provider(client).send_verification_code("13800138000", "042731")
        self.assertEqual(caught.exception.code, "sms_provider_unavailable")
        self.assertEqual(caught.exception.status_code, 503)

    def test_phone_and_code_are_validated_before_dispatch(self):
        client = FakeClient()
        with self.assertRaises(AuthError) as phone_error:
            provider(client).send_verification_code("+8613800138000", "042731")
        self.assertEqual(phone_error.exception.code, "invalid_phone")
        with self.assertRaises(AuthError) as code_error:
            provider(client).send_verification_code("13800138000", "42731")
        self.assertEqual(code_error.exception.code, "invalid_sms_code_format")
        self.assertEqual(client.requests, [])

    def test_configuration_validation_is_fail_fast(self):
        values = dict(
            secret_id="secret-id",
            secret_key="secret-key",
            sdk_app_id="1400000000",
            sign_name="米拉守护",
            template_id="1234567",
            region="ap-guangzhou",
            code_ttl_seconds=300,
            timeout_seconds=10,
            client=FakeClient(),
            request_factory=FakeRequest,
        )
        for key, value in (
            ("secret_key", "line\nbreak"),
            ("region", "Guangzhou"),
            ("code_ttl_seconds", 301),
            ("timeout_seconds", 0),
        ):
            with self.subTest(key=key), self.assertRaises(TencentSmsConfigurationError):
                TencentCloudSmsProvider(**{**values, key: value})


if __name__ == "__main__":
    unittest.main()
