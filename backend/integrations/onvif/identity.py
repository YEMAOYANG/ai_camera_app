from __future__ import annotations

import hashlib


def onvif_binding_code(identity: str) -> str:
    """Return the stable, non-reversible binding code used for ONVIF devices."""

    normalized = str(identity or "").strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"ONVIF-{digest[:40]}"
