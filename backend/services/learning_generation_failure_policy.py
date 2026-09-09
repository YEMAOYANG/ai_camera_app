from __future__ import annotations

import re


_TRANSIENT_CODES = frozenset(
    {
        "generation_failed",
        "dynamic_generation_failed",
        "openmaic_unavailable",
    }
)

_TRANSIENT_MESSAGE = re.compile(
    r"(?:"
    r"HTTP\s+(?:408|425|429|5\d\d)\b|"
    r"exceeded[_\s-]*current[_\s-]*quota|"
    r"quota|rate\s*limit|too\s+many\s+requests|"
    r"timed?\s*out|timeout|"
    r"connection\s+(?:reset|refused|aborted|closed)|"
    r"temporar(?:y|ily)\s+unavailable|service\s+unavailable|"
    r"bad\s+gateway|gateway\s+timeout|"
    r"name\s+or\s+service\s+not\s+known|"
    r"name\s+resolution|dns"
    r")",
    re.IGNORECASE,
)


def is_transient_generation_failure(code: object, message: object) -> bool:
    """Return True only for transport/provider failures that can be replayed.

    Model JSON/schema/verification/content failures intentionally stay outside
    this policy: they consume a bounded content attempt.  A transient replay
    must reuse the same catalog attempt and downstream request id.
    """

    normalized_code = re.sub(r"[^a-z0-9_.-]", "_", str(code or "").lower())
    if normalized_code not in _TRANSIENT_CODES:
        return False
    return _TRANSIENT_MESSAGE.search(str(message or "")) is not None

