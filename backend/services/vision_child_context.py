from __future__ import annotations

from pathlib import Path

from core.database import Database
from repositories.profile_repository import ProfileRepository
from schemas.profile import child_profile_payload
from services.parent_facing_copy import build_child_vision_context


def load_child_vision_context(
    database_url: str | Path,
    *,
    family_id: str | None = None,
    child_id: str | None = None,
) -> dict[str, str]:
    url = str(database_url or "").strip()
    if not url:
        return build_child_vision_context(None)
    family = str(family_id or "").strip()
    child = str(child_id or "").strip()
    if not family and not child:
        return build_child_vision_context(None)
    repository = ProfileRepository(Database(url))
    with repository.transaction() as conn:
        row = None
        if family and child:
            row = repository.get_child(conn, family_id=family, child_id=child)
        elif family:
            row = repository.current_child(conn, family_id=family)
    return build_child_vision_context(child_profile_payload(row))
