from __future__ import annotations


DAY_TYPE_SCHOOL_DAY = "school_day"
DAY_TYPE_WEEKEND = "weekend"
DAY_TYPE_HOLIDAY = "holiday"
DAY_TYPE_CUSTOM = "custom"

DAY_TYPES = {
    DAY_TYPE_SCHOOL_DAY,
    DAY_TYPE_WEEKEND,
    DAY_TYPE_HOLIDAY,
    DAY_TYPE_CUSTOM,
}

CARE_SCENARIO_POSTURE = "posture"
CARE_SCENARIO_TOY_CLEANUP = "toy_cleanup"
CARE_SCENARIO_MEAL_START = "meal_start"
CARE_SCENARIO_MEAL_HABIT = "meal_habit"
CARE_SCENARIO_NAP_TIME = "nap_time"
CARE_SCENARIO_BEDTIME = "bedtime"
CARE_SCENARIO_WAKE_UP = "wake_up"
CARE_SCENARIO_TRANSITION = "transition"
CARE_SCENARIO_SCREEN_USE = "screen_use"

CARE_SCENARIOS = {
    CARE_SCENARIO_POSTURE,
    CARE_SCENARIO_TOY_CLEANUP,
    CARE_SCENARIO_MEAL_START,
    CARE_SCENARIO_MEAL_HABIT,
    CARE_SCENARIO_NAP_TIME,
    CARE_SCENARIO_BEDTIME,
    CARE_SCENARIO_WAKE_UP,
    CARE_SCENARIO_TRANSITION,
    CARE_SCENARIO_SCREEN_USE,
}

REMINDER_DECISION_PENDING = "pending"
REMINDER_DECISION_ALLOWED = "allowed"
REMINDER_DECISION_SKIPPED_DISABLED = "skipped_disabled"
REMINDER_DECISION_SKIPPED_LOW_CONFIDENCE = "skipped_low_confidence"
REMINDER_DECISION_SKIPPED_CONTINUITY = "skipped_continuity"
REMINDER_DECISION_SKIPPED_COOLDOWN = "skipped_cooldown"
REMINDER_DECISION_SKIPPED_DAILY_LIMIT = "skipped_daily_limit"
REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW = "skipped_out_of_routine_window"
REMINDER_DECISION_RECORD_ONLY = "record_only"
REMINDER_DECISION_PARENT_NOTIFY = "parent_notify"

REMINDER_DECISIONS = {
    REMINDER_DECISION_PENDING,
    REMINDER_DECISION_ALLOWED,
    REMINDER_DECISION_SKIPPED_DISABLED,
    REMINDER_DECISION_SKIPPED_LOW_CONFIDENCE,
    REMINDER_DECISION_SKIPPED_CONTINUITY,
    REMINDER_DECISION_SKIPPED_COOLDOWN,
    REMINDER_DECISION_SKIPPED_DAILY_LIMIT,
    REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
    REMINDER_DECISION_RECORD_ONLY,
    REMINDER_DECISION_PARENT_NOTIFY,
}

REMINDER_STATUS_GENERATED = "generated"
REMINDER_STATUS_TEST_GENERATED = "test_generated"
REMINDER_STATUS_COMMAND_CREATED = "command_created"
REMINDER_STATUS_COMMAND_SENT = "command_sent"
REMINDER_STATUS_DELIVERED = "delivered"
REMINDER_STATUS_SKIPPED = "skipped"
REMINDER_STATUS_FALLBACK_USED = "fallback_used"
REMINDER_STATUS_FAILED = "failed"
REMINDER_STATUS_PARENT_NOTIFIED = "parent_notified"

REMINDER_DELIVERY_STATUSES = {
    REMINDER_STATUS_GENERATED,
    REMINDER_STATUS_TEST_GENERATED,
    REMINDER_STATUS_COMMAND_CREATED,
    REMINDER_STATUS_COMMAND_SENT,
    REMINDER_STATUS_DELIVERED,
    REMINDER_STATUS_SKIPPED,
    REMINDER_STATUS_FALLBACK_USED,
    REMINDER_STATUS_FAILED,
    REMINDER_STATUS_PARENT_NOTIFIED,
}

REMINDER_EVENT_SOURCE_CARE_POLICY = "care_policy"
REMINDER_EVENT_SOURCE_TEST = "test"
REMINDER_EVENT_SOURCE_DRY_RUN = "dry_run"
REMINDER_EVENT_SOURCE_INTERNAL = "internal"

REMINDER_EVENT_SOURCES = {
    REMINDER_EVENT_SOURCE_CARE_POLICY,
    REMINDER_EVENT_SOURCE_TEST,
    REMINDER_EVENT_SOURCE_DRY_RUN,
    REMINDER_EVENT_SOURCE_INTERNAL,
}

REVIEW_DOMAIN_CARE = "care"
AUDIT_DOMAIN_INTERNAL_API = "internal_api"

ROUTINE_WINDOW_TYPES = {
    "wake_up",
    "breakfast",
    "lunch",
    "nap",
    "dinner",
    "meal",
    "bedtime",
    "toy_cleanup",
    "cleanup",
    "posture",
    "study",
    "reading",
    "transition",
}

DEFAULT_DAY_TYPES = [DAY_TYPE_SCHOOL_DAY, DAY_TYPE_WEEKEND, DAY_TYPE_HOLIDAY]

CARE_SCENARIO_LABELS = {
    CARE_SCENARIO_POSTURE: "坐姿",
    CARE_SCENARIO_TOY_CLEANUP: "收纳",
    CARE_SCENARIO_MEAL_START: "用餐开始",
    CARE_SCENARIO_MEAL_HABIT: "用餐习惯",
    CARE_SCENARIO_NAP_TIME: "午睡",
    CARE_SCENARIO_BEDTIME: "晚间入睡",
    CARE_SCENARIO_WAKE_UP: "起床",
    CARE_SCENARIO_TRANSITION: "转场提醒",
    CARE_SCENARIO_SCREEN_USE: "屏幕使用",
}

DEFAULT_FALLBACK_TEMPLATES = {
    CARE_SCENARIO_TOY_CLEANUP: [
        "玩具玩好啦，把它们送回家吧。",
        "收好玩具后，房间会更舒服哦。",
        "我们来完成一个小收纳任务吧。",
    ],
    CARE_SCENARIO_POSTURE: [
        "我们把小背挺一挺。",
        "眼睛离桌面远一点，坐舒服些。",
        "小身体坐稳一点。",
    ],
    CARE_SCENARIO_MEAL_START: [
        "可以坐好，慢慢开始吃饭啦。",
        "吃饭时间到，先坐稳再慢慢吃。",
        "我们准备好好吃饭啦。",
    ],
    CARE_SCENARIO_MEAL_HABIT: [
        "慢慢吃，身体坐稳一点。",
        "先坐好，再一口一口吃。",
        "吃饭时我们把注意力放回餐桌。",
    ],
    CARE_SCENARIO_NAP_TIME: [
        "午睡时间到，身体轻轻躺好。",
        "我们安静下来，准备休息。",
        "小身体休息一会儿吧。",
    ],
    CARE_SCENARIO_BEDTIME: [
        "夜里安静下来，准备睡觉。",
        "小身体躺好，慢慢休息。",
        "睡觉时间到，我们轻轻闭上眼。",
    ],
    CARE_SCENARIO_WAKE_UP: [
        "早上好，可以慢慢醒来啦。",
        "小身体醒一醒，准备起床。",
        "新的一天开始啦，慢慢坐起来。",
    ],
    CARE_SCENARIO_TRANSITION: [
        "我们准备换到下一件事啦。",
        "收好当前的小事情，准备下一步。",
        "现在慢慢准备出发。",
    ],
    CARE_SCENARIO_SCREEN_USE: [
        "眼睛离屏幕远一点，我们休息一下吧。",
        "看屏幕久了，眼睛需要歇一歇哦。",
        "我们把手机放下，活动一下小身体吧。",
    ],
}

DEFAULT_CAPABILITY_CONFIGS = [
    {
        "scenario": CARE_SCENARIO_POSTURE,
        "minObservationSeconds": 30,
        "confidenceThreshold": 0.68,
        "cooldownSeconds": 1200,
        "dailyLimit": 4,
        "parentNotifyThreshold": 3,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.posture",
        "timeWindows": ["posture"],
    },
    {
        "scenario": CARE_SCENARIO_TOY_CLEANUP,
        "minObservationSeconds": 180,
        "confidenceThreshold": 0.72,
        "cooldownSeconds": 1800,
        "dailyLimit": 3,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.toy_cleanup",
        "timeWindows": [],
    },
    {
        "scenario": CARE_SCENARIO_MEAL_START,
        "minObservationSeconds": 30,
        "confidenceThreshold": 0.72,
        "cooldownSeconds": 1200,
        "dailyLimit": 3,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.meal_start",
        "timeWindows": ["breakfast", "lunch", "dinner"],
    },
    {
        "scenario": CARE_SCENARIO_MEAL_HABIT,
        "minObservationSeconds": 45,
        "confidenceThreshold": 0.74,
        "cooldownSeconds": 1500,
        "dailyLimit": 3,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.meal_habit",
        "timeWindows": ["breakfast", "lunch", "dinner"],
    },
    {
        "scenario": CARE_SCENARIO_NAP_TIME,
        "minObservationSeconds": 60,
        "confidenceThreshold": 0.76,
        "cooldownSeconds": 1800,
        "dailyLimit": 2,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.nap_time",
        "timeWindows": ["nap"],
    },
    {
        "scenario": CARE_SCENARIO_BEDTIME,
        "minObservationSeconds": 60,
        "confidenceThreshold": 0.76,
        "cooldownSeconds": 2400,
        "dailyLimit": 2,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.bedtime",
        "timeWindows": ["bedtime"],
    },
    {
        "scenario": CARE_SCENARIO_WAKE_UP,
        "minObservationSeconds": 45,
        "confidenceThreshold": 0.74,
        "cooldownSeconds": 1800,
        "dailyLimit": 2,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.wake_up",
        "timeWindows": ["wake_up"],
    },
    {
        "scenario": CARE_SCENARIO_TRANSITION,
        "minObservationSeconds": 30,
        "confidenceThreshold": 0.72,
        "cooldownSeconds": 1200,
        "dailyLimit": 4,
        "parentNotifyThreshold": 3,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.transition",
        "timeWindows": ["transition", "bedtime"],
    },
    {
        "scenario": CARE_SCENARIO_SCREEN_USE,
        "minObservationSeconds": 90,
        "confidenceThreshold": 0.72,
        "cooldownSeconds": 1800,
        "dailyLimit": 3,
        "parentNotifyThreshold": 2,
        "allowSpeaker": True,
        "recordOnly": False,
        "promptId": "reminder.screen_use",
        "timeWindows": [],
    },
]

DEFAULT_ROUTINE_WINDOWS = [
    {
        "dayType": DAY_TYPE_SCHOOL_DAY,
        "windowType": "wake_up",
        "startTime": "07:00",
        "endTime": "08:00",
    },
    {
        "dayType": DAY_TYPE_SCHOOL_DAY,
        "windowType": "breakfast",
        "startTime": "07:20",
        "endTime": "08:20",
    },
    {
        "dayType": DAY_TYPE_SCHOOL_DAY,
        "windowType": "lunch",
        "startTime": "11:30",
        "endTime": "12:30",
    },
    {
        "dayType": DAY_TYPE_SCHOOL_DAY,
        "windowType": "nap",
        "startTime": "12:40",
        "endTime": "14:20",
    },
    {
        "dayType": DAY_TYPE_SCHOOL_DAY,
        "windowType": "dinner",
        "startTime": "17:30",
        "endTime": "18:40",
    },
    {
        "dayType": DAY_TYPE_SCHOOL_DAY,
        "windowType": "bedtime",
        "startTime": "20:30",
        "endTime": "21:20",
    },
    {
        "dayType": DAY_TYPE_WEEKEND,
        "windowType": "wake_up",
        "startTime": "08:00",
        "endTime": "09:10",
    },
    {
        "dayType": DAY_TYPE_WEEKEND,
        "windowType": "breakfast",
        "startTime": "08:20",
        "endTime": "09:20",
    },
    {
        "dayType": DAY_TYPE_WEEKEND,
        "windowType": "lunch",
        "startTime": "11:40",
        "endTime": "12:50",
    },
    {
        "dayType": DAY_TYPE_WEEKEND,
        "windowType": "nap",
        "startTime": "13:00",
        "endTime": "14:30",
    },
    {
        "dayType": DAY_TYPE_WEEKEND,
        "windowType": "dinner",
        "startTime": "17:40",
        "endTime": "18:50",
    },
    {
        "dayType": DAY_TYPE_WEEKEND,
        "windowType": "bedtime",
        "startTime": "20:40",
        "endTime": "21:30",
    },
]
