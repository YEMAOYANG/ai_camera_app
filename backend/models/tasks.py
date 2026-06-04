from __future__ import annotations


TASK_SCHEDULED = "scheduled"
TASK_PENDING = "pending"
TASK_REMINDER_SENT = "reminder_sent"
TASK_IN_PROGRESS = "in_progress"
TASK_DELAYED = "delayed"
TASK_COMPLETED = "completed"
TASK_AWAITING_PARENT_CONFIRMATION = "awaiting_parent_confirmation"
TASK_CONFIRMED = "confirmed"
TASK_REJECTED = "rejected"
TASK_MISSED = "missed"
TASK_EXPIRED = "expired"
TASK_CANCELLED = "cancelled"

TASK_ACTIVE_SCHEDULED_STATUSES = {
    TASK_SCHEDULED,
    TASK_PENDING,
    TASK_REMINDER_SENT,
}

TASK_TERMINAL_STATUSES = {
    TASK_COMPLETED,
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_CONFIRMED,
    TASK_REJECTED,
    TASK_MISSED,
    TASK_EXPIRED,
    TASK_CANCELLED,
}

TASK_STATUSES = {
    TASK_SCHEDULED,
    TASK_PENDING,
    TASK_REMINDER_SENT,
    TASK_IN_PROGRESS,
    TASK_DELAYED,
    TASK_COMPLETED,
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_CONFIRMED,
    TASK_REJECTED,
    TASK_MISSED,
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
