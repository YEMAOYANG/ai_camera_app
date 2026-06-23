class CareCapability {
  const CareCapability({
    required this.id,
    required this.childId,
    required this.deviceId,
    required this.scenario,
    required this.label,
    required this.enabled,
    required this.dayTypes,
    required this.timeWindows,
    required this.minObservationSeconds,
    required this.observationThreshold,
    required this.cooldownSeconds,
    required this.dailyLimit,
    required this.parentNotifyThreshold,
    required this.allowSpeaker,
    required this.recordOnly,
    required this.lastRemindedAt,
    required this.dailyReminderCount,
  });

  final String id;
  final String childId;
  final String deviceId;
  final String scenario;
  final String label;
  final bool enabled;
  final List<String> dayTypes;
  final List<String> timeWindows;
  final int minObservationSeconds;
  final double observationThreshold;
  final int cooldownSeconds;
  final int dailyLimit;
  final int parentNotifyThreshold;
  final bool allowSpeaker;
  final bool recordOnly;
  final int? lastRemindedAt;
  final int dailyReminderCount;

  static CareCapability fromJson(Map<String, dynamic> json) {
    return CareCapability(
      id: _asString(json['id']),
      childId: _asString(json['childId']),
      deviceId: _asString(json['deviceId']),
      scenario: _asString(json['scenario']),
      label: _asString(json['label']),
      enabled: json['enabled'] == true,
      dayTypes: _asStringList(json['dayTypes']),
      timeWindows: _asStringList(json['timeWindows']),
      minObservationSeconds: _asInt(json['minObservationSeconds']),
      observationThreshold: _asDouble(json['observationThreshold']),
      cooldownSeconds: _asInt(json['cooldownSeconds']),
      dailyLimit: _asInt(json['dailyLimit']),
      parentNotifyThreshold: _asInt(json['parentNotifyThreshold']),
      allowSpeaker: json['allowSpeaker'] == true,
      recordOnly: json['recordOnly'] == true,
      lastRemindedAt: _asNullableInt(json['lastRemindedAt']),
      dailyReminderCount: _asInt(json['dailyReminderCount']),
    );
  }
}

class RoutineWindow {
  const RoutineWindow({
    required this.id,
    required this.childId,
    required this.dayType,
    required this.windowType,
    required this.startTime,
    required this.endTime,
    required this.enabled,
    required this.timezone,
  });

  final String id;
  final String childId;
  final String dayType;
  final String windowType;
  final String startTime;
  final String endTime;
  final bool enabled;
  final String timezone;

  RoutineWindow copyWith({
    String? startTime,
    String? endTime,
    bool? enabled,
    String? timezone,
  }) {
    return RoutineWindow(
      id: id,
      childId: childId,
      dayType: dayType,
      windowType: windowType,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      enabled: enabled ?? this.enabled,
      timezone: timezone ?? this.timezone,
    );
  }

  Map<String, Object?> toJson() {
    return {
      'dayType': dayType,
      'windowType': windowType,
      'startTime': startTime,
      'endTime': endTime,
      'enabled': enabled,
      'timezone': timezone,
    };
  }

  static RoutineWindow fromJson(Map<String, dynamic> json) {
    return RoutineWindow(
      id: _asString(json['id']),
      childId: _asString(json['childId']),
      dayType: _asString(json['dayType']),
      windowType: _asString(json['windowType']),
      startTime: _asString(json['startTime']),
      endTime: _asString(json['endTime']),
      enabled: json['enabled'] == true,
      timezone: _asString(json['timezone'], fallback: 'Asia/Shanghai'),
    );
  }
}

class CareSummary {
  const CareSummary({
    required this.childId,
    required this.dayType,
    required this.currentStage,
    required this.todayReminderCount,
    required this.capabilities,
    required this.needsParentReview,
    required this.observationSuggestion,
    this.nextReminder,
  });

  final String childId;
  final String dayType;
  final String currentStage;
  final int todayReminderCount;
  final List<CareCapability> capabilities;
  final List<ParentReviewItem> needsParentReview;
  final String observationSuggestion;
  final NextCareReminder? nextReminder;

  static CareSummary fromJson(Map<String, dynamic> json) {
    final summary = _asMap(json['summary']);
    final capabilities = summary['capabilities'];
    final reviews = summary['needsParentReview'];
    final next = _asMap(summary['nextReminder']);
    return CareSummary(
      childId: _asString(summary['childId']),
      dayType: _asString(summary['dayType']),
      currentStage: _asString(summary['currentStage'], fallback: '安静观察'),
      todayReminderCount: _asInt(summary['todayReminderCount']),
      capabilities: capabilities is List
          ? capabilities
                .map((item) => CareCapability.fromJson(_asMap(item)))
                .toList()
          : const [],
      needsParentReview: reviews is List
          ? reviews
                .map((item) => ParentReviewItem.fromJson(_asMap(item)))
                .toList()
          : const [],
      observationSuggestion: _asString(summary['observationSuggestion']),
      nextReminder: next.isEmpty ? null : NextCareReminder.fromJson(next),
    );
  }
}

class NextCareReminder {
  const NextCareReminder({
    required this.windowType,
    required this.label,
    required this.startTime,
    required this.endTime,
  });

  final String windowType;
  final String label;
  final String startTime;
  final String endTime;

  static NextCareReminder fromJson(Map<String, dynamic> json) {
    return NextCareReminder(
      windowType: _asString(json['windowType']),
      label: _asString(json['label']),
      startTime: _asString(json['startTime']),
      endTime: _asString(json['endTime']),
    );
  }
}

class CareReminderEvent {
  const CareReminderEvent({
    required this.id,
    required this.childId,
    required this.deviceId,
    required this.scenario,
    required this.text,
    required this.tone,
    required this.textSource,
    required this.deliveryStatus,
    required this.fallbackUsed,
    required this.generatedAt,
  });

  final String id;
  final String childId;
  final String deviceId;
  final String scenario;
  final String text;
  final String tone;
  final String textSource;
  final String deliveryStatus;
  final bool fallbackUsed;
  final int generatedAt;

  static CareReminderEvent fromJson(Map<String, dynamic> json) {
    return CareReminderEvent(
      id: _asString(json['id']),
      childId: _asString(json['childId']),
      deviceId: _asString(json['deviceId']),
      scenario: _asString(json['scenario']),
      text: _asString(json['text']),
      tone: _asString(json['tone']),
      textSource: _asString(json['textSource']),
      deliveryStatus: _asString(json['deliveryStatus']),
      fallbackUsed: json['fallbackUsed'] == true,
      generatedAt: _asInt(json['generatedAt']),
    );
  }
}

class ParentReviewItem {
  const ParentReviewItem({
    required this.id,
    required this.childId,
    required this.scenario,
    required this.reviewType,
    required this.status,
    required this.summary,
    required this.createdAt,
  });

  final String id;
  final String childId;
  final String scenario;
  final String reviewType;
  final String status;
  final String summary;
  final int createdAt;

  static ParentReviewItem fromJson(Map<String, dynamic> json) {
    return ParentReviewItem(
      id: _asString(json['id']),
      childId: _asString(json['childId']),
      scenario: _asString(json['scenario']),
      reviewType: _asString(json['reviewType']),
      status: _asString(json['status']),
      summary: _asString(json['summary']),
      createdAt: _asInt(json['createdAt']),
    );
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String _asString(dynamic value, {String fallback = ''}) {
  if (value is String && value.isNotEmpty) return value;
  return fallback;
}

int _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

double _asDouble(dynamic value) {
  if (value is double) return value;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value) ?? 0;
  return 0;
}

List<String> _asStringList(dynamic value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.isNotEmpty)
      .toList();
}
