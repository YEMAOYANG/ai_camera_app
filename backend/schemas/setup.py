from __future__ import annotations

from core.database import DatabaseRow

from models.setup import SETUP_DONE, SetupProgress


def setup_progress_from_row(row: DatabaseRow) -> SetupProgress:
    return SetupProgress(
        family_id=row["family_id"],
        completed=bool(row["completed"]),
        parent_identity=row["parent_identity_status"],
        device_binding=row["device_binding_status"],
        wifi=row["wifi_status"],
        child_profile=row["child_profile_status"],
        contacts=row["contacts_status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
    )


def next_setup_step(progress: SetupProgress) -> str:
    if progress.completed:
        return "home"
    if progress.parent_identity != SETUP_DONE:
        return "parentIdentity"
    if progress.device_binding != SETUP_DONE:
        return "device"
    if progress.wifi != SETUP_DONE:
        return "wifi"
    if progress.child_profile != SETUP_DONE:
        return "child"
    if progress.contacts != SETUP_DONE:
        return "contacts"
    return "complete"


def setup_payload(progress: SetupProgress) -> dict:
    return {
        "completed": progress.completed,
        "parentIdentity": progress.parent_identity,
        "deviceBinding": progress.device_binding,
        "wifi": progress.wifi,
        "childProfile": progress.child_profile,
        "contacts": progress.contacts,
        "nextStep": next_setup_step(progress),
        "updatedAt": progress.updated_at,
        "completedAt": progress.completed_at,
    }
