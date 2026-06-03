from __future__ import annotations


REWARD_ACTIVE = "active"
REWARD_ARCHIVED = "archived"

REWARD_STATUSES = {REWARD_ACTIVE, REWARD_ARCHIVED}

REDEMPTION_REDEEMED = "redeemed"
REDEMPTION_FULFILLED = "fulfilled"
REDEMPTION_CANCELLED = "cancelled"

REDEMPTION_STATUSES = {
    REDEMPTION_REDEEMED,
    REDEMPTION_FULFILLED,
    REDEMPTION_CANCELLED,
    "requested",
    "pending_parent_approval",
    "approved",
    "rejected",
}
