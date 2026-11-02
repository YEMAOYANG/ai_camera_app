from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.errors import AuthError


@dataclass(frozen=True)
class SmsDelivery:
    provider: str
    template_id: str
    delivery_status: str
    debug_code: str | None = None
    provider_request_id: str | None = None
    provider_serial_no: str | None = None


class SmsProvider(Protocol):
    def send_verification_code(self, phone: str, code: str) -> SmsDelivery:
        """Send a caller-generated verification code to a normalized phone number."""


class DevelopmentSmsProvider:
    def __init__(self, template_id: str = "development-login-code"):
        self.template_id = template_id

    def send_verification_code(self, phone: str, code: str) -> SmsDelivery:
        return SmsDelivery(
            provider="development",
            template_id=self.template_id,
            delivery_status="delivered",
            debug_code=code,
        )


class UnavailableSmsProvider:
    def __init__(self, provider: str = "unconfigured"):
        self.provider = provider or "unconfigured"

    def send_verification_code(self, phone: str, code: str) -> SmsDelivery:
        raise AuthError(
            "sms_provider_not_configured",
            "短信服务尚未配置，请先配置正式短信供应商。",
            503,
        )
