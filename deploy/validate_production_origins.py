#!/usr/bin/env python3
"""Fail closed unless all public production endpoints are HTTPS root origins."""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit


ORIGIN_NAMES = (
    "MIRA_STUDENT_ORIGIN",
    "MIRA_CLASSROOM_ORIGIN",
    "MIRA_API_ORIGIN",
    "MIRA_STUDENT_WEB_ORIGIN",
    "MIRA_RUNTIME_PUBLIC_ORIGIN",
)


def normalized_https_origin(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be a credential-free HTTPS root origin")
    return f"https://{parsed.netloc}"


def main() -> int:
    try:
        origins = {name: normalized_https_origin(name) for name in ORIGIN_NAMES}
        if origins["MIRA_STUDENT_ORIGIN"] != origins["MIRA_STUDENT_WEB_ORIGIN"]:
            raise ValueError(
                "MIRA_STUDENT_WEB_ORIGIN must match MIRA_STUDENT_ORIGIN"
            )
        if origins["MIRA_CLASSROOM_ORIGIN"] != origins["MIRA_RUNTIME_PUBLIC_ORIGIN"]:
            raise ValueError(
                "MIRA_RUNTIME_PUBLIC_ORIGIN must match MIRA_CLASSROOM_ORIGIN"
            )
    except ValueError as error:
        print(f"production origin validation failed: {error}", file=sys.stderr)
        return 2
    print("production origins are valid HTTPS root origins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
