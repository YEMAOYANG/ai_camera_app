from __future__ import annotations

from dataclasses import dataclass


SETUP_PENDING = "pending"
SETUP_DONE = "done"


@dataclass(frozen=True)
class SetupProgress:
    family_id: str
    completed: bool
    parent_identity: str
    device_binding: str
    wifi: str
    child_profile: str
    contacts: str
    created_at: int
    updated_at: int
    completed_at: int | None
