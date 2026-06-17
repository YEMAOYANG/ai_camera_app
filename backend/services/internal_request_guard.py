from __future__ import annotations

from pathlib import Path
from typing import Mapping

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.care import AUDIT_DOMAIN_INTERNAL_API
from repositories.care_repository import CareRepository


class InternalRequestGuard:
    def __init__(
        self,
        database_url: str | Path,
        *,
        token: str,
        allowed_sources: list[str] | None = None,
    ):
        self.repository = CareRepository(Database(database_url))
        self.token = str(token or "").strip()
        self.allowed_sources = {item.strip() for item in (allowed_sources or []) if item.strip()}

    def authorize(
        self,
        *,
        route: str,
        headers: Mapping[str, str],
        source_ip: str | None,
        payload_ref: str | None = None,
    ) -> dict:
        source_name = str(headers.get("X-Mira-Internal-Source") or "").strip()[:128]
        presented = self._presented_token(headers)
        source_allowed = self._source_allowed(source_ip)
        accepted = False
        reason = "ok"
        status_code = 401
        if not self.token:
            reason = "internal_token_unconfigured"
            status_code = 503
        elif not presented:
            reason = "missing_internal_token"
        elif not _constant_timeish_equal(presented, self.token):
            reason = "invalid_internal_token"
        elif not source_allowed:
            reason = "source_not_allowed"
            status_code = 403
        else:
            accepted = True

        audit_id = self._audit(
            route=route,
            source_ip=source_ip,
            source_name=source_name,
            accepted=accepted,
            reason=reason,
            payload_ref=payload_ref,
        )
        if not accepted:
            raise ApiError(reason, "内部调用未通过校验。", status_code)
        return {"auditId": audit_id, "sourceName": source_name, "sourceIp": source_ip or ""}

    def _presented_token(self, headers: Mapping[str, str]) -> str:
        header_token = str(headers.get("X-Mira-Internal-Token") or "").strip()
        if header_token:
            return header_token
        authorization = str(headers.get("Authorization") or "").strip()
        prefix = "Bearer "
        return authorization[len(prefix) :].strip() if authorization.startswith(prefix) else ""

    def _source_allowed(self, source_ip: str | None) -> bool:
        if not self.allowed_sources:
            return True
        return str(source_ip or "").strip() in self.allowed_sources

    def _audit(
        self,
        *,
        route: str,
        source_ip: str | None,
        source_name: str | None,
        accepted: bool,
        reason: str,
        payload_ref: str | None,
    ) -> str:
        with self.repository.transaction() as conn:
            row = self.repository.create_internal_audit_event(
                conn,
                audit_domain=AUDIT_DOMAIN_INTERNAL_API,
                actor_type="internal_service",
                actor_id=source_name or None,
                route=route,
                source_ip=source_ip,
                source_name=source_name,
                accepted=accepted,
                reason=reason,
                payload_ref=payload_ref,
                now=now_ms(),
            )
        return str(row["id"])


def _constant_timeish_equal(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    diff = 0
    for a, b in zip(left.encode("utf-8"), right.encode("utf-8")):
        diff |= a ^ b
    return diff == 0
