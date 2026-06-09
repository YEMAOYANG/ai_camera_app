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
    camera_name: str
    camera_name_intro: str
    camera_name_intro_at: int | None
    contacts: str
    created_at: int
    updated_at: int
    completed_at: int | None
