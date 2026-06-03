from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


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


class MockSmsProvider:
    def __init__(self, code: str = "0426", template_id: str = "mock-login-code"):
        self.code = code
        self.template_id = template_id

    def issue_verification_code(self, phone: str) -> SmsDelivery:
        return SmsDelivery(
            code=self.code,
            provider="mock",
            template_id=self.template_id,
            delivery_status="delivered",
            debug_code=self.code,
        )
