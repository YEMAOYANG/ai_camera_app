import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

enum GuardianTaskStatus {
  pending('pending', '待开始', StatusTone.neutral),
  inProgress('in_progress', '进行中', StatusTone.success),
  completed('completed', '已完成', StatusTone.success),
  awaitingParentConfirmation(
    'awaiting_parent_confirmation',
    '待确认',
    StatusTone.warning,
  ),
  confirmed('confirmed', '已确认', StatusTone.success),
  rejected('rejected', '已驳回', StatusTone.danger),
  expired('expired', '已过期', StatusTone.danger),
  cancelled('cancelled', '已取消', StatusTone.neutral);

  const GuardianTaskStatus(this.value, this.label, this.tone);

  final String value;
  final String label;
  final StatusTone tone;

  bool get canComplete {
    return this == GuardianTaskStatus.pending ||
        this == GuardianTaskStatus.inProgress ||
        this == GuardianTaskStatus.rejected;
  }

  bool get awaitsParent {
    return this == GuardianTaskStatus.awaitingParentConfirmation;
  }

  static GuardianTaskStatus fromValue(String value) {
    return GuardianTaskStatus.values.firstWhere(
      (status) => status.value == value,
      orElse: () => GuardianTaskStatus.pending,
    );
  }
}

class GuardianTask {
  const GuardianTask({
    required this.id,
    required this.familyId,
    required this.childId,
    required this.title,
    required this.description,
    required this.type,
    required this.status,
    required this.scheduledDate,
    required this.scheduledStart,
    required this.scheduledEnd,
    required this.rewardPoints,
    required this.requiresParentConfirmation,
    required this.evidenceSummary,
    required this.rejectionReason,
    required this.completedAt,
    required this.confirmedAt,
    required this.pointsGrantedAt,
  });

  final String id;
  final String familyId;
  final String childId;
  final String title;
  final String description;
  final String type;
  final GuardianTaskStatus status;
  final String scheduledDate;
  final String scheduledStart;
  final String scheduledEnd;
  final int rewardPoints;
  final bool requiresParentConfirmation;
  final String evidenceSummary;
  final String rejectionReason;
  final int? completedAt;
  final int? confirmedAt;
  final int? pointsGrantedAt;

  String get typeLabel {
    return switch (type) {
      'learning' => '学习',
      'life' => '生活',
      'housework' => '家务',
      'sleep' => '作息',
      'schoolbag' => '小书包',
      'checkin' => '记录',
      'parent_confirmation' => '家长确认',
      'ai_observed' => 'AI 观察',
      _ => '任务',
    };
  }

  String get timeLabel {
    if (scheduledStart.isNotEmpty && scheduledEnd.isNotEmpty) {
      return '$scheduledStart - $scheduledEnd';
    }
    if (scheduledStart.isNotEmpty) return scheduledStart;
    return scheduledDate;
  }

  String get durationLabel {
    if (description.isNotEmpty) return description;
    return scheduledEnd.isNotEmpty ? '按计划执行' : '今日安排';
  }

  String get parentDecisionLabel {
    if (status.awaitsParent) return '待家长确认';
    if (status == GuardianTaskStatus.confirmed) return '家长已确认';
    if (status == GuardianTaskStatus.rejected) return '已驳回';
    if (status == GuardianTaskStatus.completed) return '已完成';
    return '未确认';
  }

  String get evidenceText {
    if (evidenceSummary.isNotEmpty) return evidenceSummary;
    if (status.awaitsParent) return '任务已完成，等待家长确认后写入积分流水。';
    return '暂无证据摘要，完成任务后会在这里显示 AI 观察和家长确认记录。';
  }

  String get aiAdvice {
    if (status.awaitsParent) {
      return '建议核对任务证据后再确认积分，必要时可以驳回并让孩子补充完成。';
    }
    if (status == GuardianTaskStatus.confirmed) {
      return '任务已经确认，奖励积分已写入流水。';
    }
    if (status == GuardianTaskStatus.inProgress) {
      return '任务正在进行，保持低打扰观察，完成后再进入家长确认。';
    }
    return '按孩子当前节奏推进，避免为了积分打断任务本身。';
  }

  String get nextStep {
    if (status.awaitsParent) return '等待家长处理任务证据。';
    if (status == GuardianTaskStatus.pending) return '到点后提醒孩子开始。';
    if (status == GuardianTaskStatus.inProgress) return '完成后进入家长确认。';
    if (status == GuardianTaskStatus.rejected) return rejectionReason;
    return '已进入任务记录。';
  }

  GuardianTask copyWith({
    GuardianTaskStatus? status,
    String? evidenceSummary,
    String? rejectionReason,
    int? completedAt,
    int? confirmedAt,
    int? pointsGrantedAt,
  }) {
    return GuardianTask(
      id: id,
      familyId: familyId,
      childId: childId,
      title: title,
      description: description,
      type: type,
      status: status ?? this.status,
      scheduledDate: scheduledDate,
      scheduledStart: scheduledStart,
      scheduledEnd: scheduledEnd,
      rewardPoints: rewardPoints,
      requiresParentConfirmation: requiresParentConfirmation,
      evidenceSummary: evidenceSummary ?? this.evidenceSummary,
      rejectionReason: rejectionReason ?? this.rejectionReason,
      completedAt: completedAt ?? this.completedAt,
      confirmedAt: confirmedAt ?? this.confirmedAt,
      pointsGrantedAt: pointsGrantedAt ?? this.pointsGrantedAt,
    );
  }

  static GuardianTask fromJson(Map<String, dynamic> json) {
    return GuardianTask(
      id: _asString(json['id']),
      familyId: _asString(json['familyId']),
      childId: _asString(json['childId']),
      title: _asString(json['title'], fallback: '未命名任务'),
      description: _asString(json['description']),
      type: _asString(json['type'], fallback: 'learning'),
      status: GuardianTaskStatus.fromValue(_asString(json['status'])),
      scheduledDate: _asString(json['scheduledDate']),
      scheduledStart: _asString(json['scheduledStart']),
      scheduledEnd: _asString(json['scheduledEnd']),
      rewardPoints: _asInt(json['rewardPoints']),
      requiresParentConfirmation:
          json['requiresParentConfirmation'] is bool
          ? json['requiresParentConfirmation'] as bool
          : true,
      evidenceSummary: _asString(json['evidenceSummary']),
      rejectionReason: _asString(json['rejectionReason']),
      completedAt: _asNullableInt(json['completedAt']),
      confirmedAt: _asNullableInt(json['confirmedAt']),
      pointsGrantedAt: _asNullableInt(json['pointsGrantedAt']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'familyId': familyId,
      'childId': childId,
      'title': title,
      'description': description,
      'type': type,
      'status': status.value,
      'scheduledDate': scheduledDate,
      'scheduledStart': scheduledStart,
      'scheduledEnd': scheduledEnd,
      'rewardPoints': rewardPoints,
      'requiresParentConfirmation': requiresParentConfirmation,
      'evidenceSummary': evidenceSummary,
      'rejectionReason': rejectionReason,
      'completedAt': completedAt,
      'confirmedAt': confirmedAt,
      'pointsGrantedAt': pointsGrantedAt,
    };
  }
}

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
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
