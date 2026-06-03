from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    access_expires_at: int
    refresh_expires_at: int
