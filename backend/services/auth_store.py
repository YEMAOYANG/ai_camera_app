from __future__ import annotations

from core.errors import AuthError
from services.auth_service import AuthService


# Compatibility alias for older tests/imports. New code should use AuthService.
AuthStore = AuthService
