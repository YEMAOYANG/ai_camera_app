from __future__ import annotations


TASK_PENDING = "pending"
TASK_IN_PROGRESS = "in_progress"
TASK_COMPLETED = "completed"
TASK_AWAITING_PARENT_CONFIRMATION = "awaiting_parent_confirmation"
TASK_CONFIRMED = "confirmed"
TASK_REJECTED = "rejected"
TASK_EXPIRED = "expired"
TASK_CANCELLED = "cancelled"

TASK_STATUSES = {
    TASK_PENDING,
    TASK_IN_PROGRESS,
    TASK_COMPLETED,
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_CONFIRMED,
    TASK_REJECTED,
    TASK_EXPIRED,
    TASK_CANCELLED,
}

TASK_TYPES = {
    "learning",
    "life",
    "housework",
    "sleep",
    "schoolbag",
    "reading_interest",
    "sports_outdoor",
    "custom",
    "checkin",
    "parent_confirmation",
    "ai_observed",
}
