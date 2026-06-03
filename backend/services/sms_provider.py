from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Protocol

from core.errors import AuthError


@dataclass(frozen=True)
class SmsDelivery:
    code: str
    provider: str
    template_id: str
    delivery_status: str
    debug_code: str | None = None


class SmsProvider(Protocol):
    def issue_verification_code(self, phone: str) -> SmsDelivery:
        """Create and send a verification code for a phone number."""


class DevelopmentSmsProvider:
    def __init__(self, template_id: str = "development-login-code"):
        self.template_id = template_id

    def issue_verification_code(self, phone: str) -> SmsDelivery:
        code = f"{secrets.randbelow(1_000_000):06d}"
        return SmsDelivery(
            code=code,
            provider="development",
            template_id=self.template_id,
            delivery_status="delivered",
            debug_code=code,
        )


class UnavailableSmsProvider:
    def __init__(self, provider: str = "unconfigured"):
        self.provider = provider or "unconfigured"

    def issue_verification_code(self, phone: str) -> SmsDelivery:
        raise AuthError(
            "sms_provider_not_configured",
            "短信服务尚未配置，请先配置正式短信供应商。",
            503,
        )
