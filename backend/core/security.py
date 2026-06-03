from __future__ import annotations

import hashlib
import secrets
import time


def now_ms() -> int:
    return int(time.time() * 1000)


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"
