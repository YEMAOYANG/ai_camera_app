"""Tencent Cloud SMS delivery adapter for parent verification codes.

The application service owns code generation, persistence, cooldowns and
verification. This adapter performs one non-retried SendSms submission and
returns only bounded delivery metadata. It never logs credentials, codes or
phone numbers.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Callable

from core.errors import AuthError
from services.sms_provider import SmsDelivery

try:  # Imported lazily enough for unit tests to inject a fake SDK client.
    from tencentcloud.common import credential as _credential
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
        TencentCloudSDKException as _TencentCloudSDKException,
    )
    from tencentcloud.common.profile.client_profile import ClientProfile as _ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile as _HttpProfile
    from tencentcloud.sms.v20210111 import models as _sms_models
    from tencentcloud.sms.v20210111 import sms_client as _sms_client
except ImportError:  # pragma: no cover - production images install the pinned SDK.
    _credential = None
    _TencentCloudSDKException = None
    _ClientProfile = None
    _HttpProfile = None
    _sms_models = None
    _sms_client = None


LOGGER = logging.getLogger(__name__)
SDK_LOGGER = logging.getLogger("tencentcloud_sdk_common")
ENDPOINT = "sms.tencentcloudapi.com"
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
CODE_PATTERN = re.compile(r"^\d{6}$")
REGION_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")


class TencentSmsConfigurationError(ValueError):
    """Raised at startup when the Tencent SMS adapter is not safely configured."""


class TencentCloudSmsProvider:
    provider_name = "tencent"

    def __init__(
        self,
        *,
        secret_id: str,
        secret_key: str,
        sdk_app_id: str,
        sign_name: str,
        template_id: str,
        region: str,
        code_ttl_seconds: int,
        timeout_seconds: float,
        client=None,
        request_factory: Callable[[], object] | None = None,
    ):
        # Tencent's SDK logs the complete request body (including phone number
        # and OTP) at DEBUG. Keep that logger above DEBUG even if an operator
        # temporarily increases the application's root log verbosity.
        SDK_LOGGER.setLevel(logging.WARNING)
        self._secret_id = _required_value(secret_id, "secret_id")
        self._secret_key = _required_value(secret_key, "secret_key")
        self.sdk_app_id = _required_value(sdk_app_id, "sdk_app_id")
        self.sign_name = _required_value(sign_name, "sign_name")
        self.template_id = _required_value(template_id, "template_id")
        self.region = _required_value(region, "region")
        if not REGION_PATTERN.fullmatch(self.region):
            raise TencentSmsConfigurationError("region is invalid")

        try:
            ttl_seconds = int(code_ttl_seconds)
        except (TypeError, ValueError):
            raise TencentSmsConfigurationError("code_ttl_seconds must be an integer") from None
        if ttl_seconds < 60 or ttl_seconds > 3600 or ttl_seconds % 60:
            raise TencentSmsConfigurationError(
                "code_ttl_seconds must be a whole number of minutes between 60 and 3600"
            )
        self.code_ttl_seconds = ttl_seconds
        self.code_ttl_minutes = ttl_seconds // 60

        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            raise TencentSmsConfigurationError("timeout_seconds must be numeric") from None
        if not math.isfinite(timeout) or not 1 <= timeout <= 60:
            raise TencentSmsConfigurationError("timeout_seconds must be between 1 and 60")
        self.timeout_seconds = timeout

        if client is None:
            if any(
                value is None
                for value in (
                    _credential,
                    _ClientProfile,
                    _HttpProfile,
                    _sms_client,
                    _sms_models,
                )
            ):
                raise TencentSmsConfigurationError(
                    "Tencent Cloud SMS SDK is not installed"
                )
            http_profile = _HttpProfile()
            http_profile.reqMethod = "POST"
            http_profile.reqTimeout = timeout
            http_profile.endpoint = ENDPOINT
            client_profile = _ClientProfile()
            client_profile.signMethod = "TC3-HMAC-SHA256"
            client_profile.httpProfile = http_profile
            # Do not enable the SDK retryer: a timeout can mean an accepted SMS.
            credentials = _credential.Credential(self._secret_id, self._secret_key)
            client = _sms_client.SmsClient(credentials, self.region, client_profile)

        if request_factory is None:
            if _sms_models is None:
                raise TencentSmsConfigurationError(
                    "Tencent Cloud SMS request factory is unavailable"
                )
            request_factory = _sms_models.SendSmsRequest
        self._client = client
        self._request_factory = request_factory

    def send_verification_code(self, phone: str, code: str) -> SmsDelivery:
        normalized_phone = str(phone or "").strip()
        normalized_code = str(code or "").strip()
        if not PHONE_PATTERN.fullmatch(normalized_phone):
            raise AuthError("invalid_phone", "请输入正确的 11 位手机号")
        if not CODE_PATTERN.fullmatch(normalized_code):
            raise AuthError("invalid_sms_code_format", "验证码格式不正确", 500)

        request = self._request_factory()
        request.SmsSdkAppId = self.sdk_app_id
        request.SignName = self.sign_name
        request.TemplateId = self.template_id
        request.TemplateParamSet = [normalized_code, str(self.code_ttl_minutes)]
        request.PhoneNumberSet = [f"+86{normalized_phone}"]
        request.SessionContext = ""
        request.ExtendCode = ""
        request.SenderId = ""

        try:
            response = self._client.SendSms(request)
        except (TimeoutError, ConnectionError, OSError) as exc:
            LOGGER.warning(
                "Tencent SMS submission result unknown exception_type=%s",
                type(exc).__name__,
            )
            raise AuthError(
                "sms_provider_unavailable",
                "短信服务暂时不可用，请稍后再试。",
                503,
            ) from None
        except Exception as exc:
            if _TencentCloudSDKException is None or not isinstance(
                exc, _TencentCloudSDKException
            ):
                raise
            provider_code = _safe_provider_field(getattr(exc, "code", None))
            request_id = _safe_provider_field(
                getattr(exc, "requestId", None) or getattr(exc, "request_id", None)
            )
            _raise_provider_error(provider_code, request_id=request_id)

        request_id = _safe_provider_field(getattr(response, "RequestId", None))
        statuses = getattr(response, "SendStatusSet", None)
        if not isinstance(statuses, (list, tuple)) or len(statuses) != 1:
            LOGGER.warning(
                "Tencent SMS returned an invalid status set request_id=%s",
                request_id or "missing",
            )
            raise AuthError(
                "sms_provider_unavailable",
                "短信服务暂时不可用，请稍后再试。",
                503,
            )

        status = statuses[0]
        provider_code = _safe_provider_field(getattr(status, "Code", None))
        serial_no = _safe_provider_field(getattr(status, "SerialNo", None))
        if provider_code != "Ok":
            _raise_provider_error(
                provider_code,
                request_id=request_id,
                serial_no=serial_no,
            )

        return SmsDelivery(
            provider=self.provider_name,
            template_id=self.template_id,
            delivery_status="accepted",
            provider_request_id=request_id or None,
            provider_serial_no=serial_no or None,
        )


def _required_value(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TencentSmsConfigurationError(f"{field} is required")
    normalized = value.strip()
    if any(character in normalized for character in "\r\n\x00"):
        raise TencentSmsConfigurationError(f"{field} contains invalid characters")
    return normalized


def _safe_provider_field(value) -> str:
    value = str(value or "").strip()
    return value[:256] if re.fullmatch(r"[A-Za-z0-9._:\-]*", value) else ""


def _raise_provider_error(
    provider_code: str,
    *,
    request_id: str = "",
    serial_no: str = "",
) -> None:
    provider_code = provider_code or "UnknownProviderResponse"
    LOGGER.warning(
        "Tencent SMS rejected submission code=%s request_id=%s serial_no=%s",
        provider_code,
        request_id or "missing",
        serial_no or "missing",
    )
    lowered = provider_code.lower()
    if (
        provider_code.startswith("LimitExceeded.")
        or provider_code.startswith("RequestLimitExceeded")
        or "frequency" in lowered
    ):
        raise AuthError(
            "sms_rate_limited",
            "验证码发送过于频繁，请稍后再试。",
            429,
        )
    if (
        lowered.startswith("clientnetworkerror")
        or lowered.startswith("servernetworkerror")
        or lowered.startswith("internalerror")
    ):
        # The official SDK wraps transport failures in
        # TencentCloudSDKException. Treat these as an unknown submission
        # result and never retry automatically: Tencent may already have
        # accepted the message before the connection failed.
        raise AuthError(
            "sms_provider_unavailable",
            "短信服务暂时不可用，请稍后再试。",
            503,
        )
    configuration_markers = (
        "authfailure",
        "unauthorizedoperation",
        "secretid",
        "signature",
        "template",
        "smssdkappid",
        "insufficientbalance",
        "package",
        "arrears",
    )
    if any(marker in lowered for marker in configuration_markers):
        raise AuthError(
            "sms_provider_misconfigured",
            "短信服务暂时不可用，请稍后再试。",
            503,
        )
    raise AuthError(
        "sms_provider_rejected",
        "验证码发送失败，请稍后再试。",
        502,
    )
