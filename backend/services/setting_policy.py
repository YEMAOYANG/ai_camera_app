from __future__ import annotations

import json


SETTING_MANAGE_CAPABILITIES = {
    "ai-care-rules": "manage_child_settings",
    "notifications": "manage_child_settings",
    "conversation": "manage_child_settings",
    "education": "manage_child_settings",
    "privacy": "manage_privacy",
}

SETTING_DEFAULTS = {
    "ai-care-rules": {
        "taskObservationEnabled": True,
        "voiceReminderEnabled": True,
        "delayReminderEnabled": True,
        "cameraObservationStrategy": "balanced",
        "evidenceReviewEnabled": True,
    },
    "notifications": {
        "taskReminder": True,
        "parentActionReminder": True,
        "taskEndReminder": True,
        "deviceOfflineReminder": True,
        "pointsRewardReminder": True,
        "dailySummary": False,
        "quietHoursEnabled": False,
        "quietHoursStart": "21:30",
        "quietHoursEnd": "07:00",
    },
    "privacy": {
        "cameraCollectionAuthorized": False,
        "voiceBroadcastAuthorized": False,
        "childPrivacyAuthorized": False,
        "remoteViewingNoticeEnabled": True,
        "storeEventSnapshotsOnly": True,
        "detailedConversationLogEnabled": False,
        "dataRetentionDays": 30,
    },
    "conversation": {
        "wakeName": "小暖",
        "voiceStyle": "温柔女声，语速偏慢",
        "boundaryLevel": "balanced",
        "freeChatEnabled": True,
        "freeChatSingleMinutes": 8,
        "freeChatDailyMinutes": 25,
        "homeworkModeRestricted": True,
        "bedtimeQuietEnabled": True,
        "detailedTranscriptEnabled": False,
    },
    "education": {
        "schoolbagEnabled": True,
        "schoolStage": "primary",
        "courseScheduleEnabled": False,
        "partnerContentEnabled": False,
        "learningDiagnosisEnabled": False,
        "notes": "",
    },
}


def setting_value(row, key: str) -> dict:
    defaults = dict(SETTING_DEFAULTS[key])
    if row is None:
        return defaults
    try:
        stored = json.loads(row["value"])
    except (TypeError, ValueError, json.JSONDecodeError):
        stored = {}
    if not isinstance(stored, dict):
        return defaults
    for item_key in defaults:
        if item_key in stored:
            defaults[item_key] = stored[item_key]
    return defaults
