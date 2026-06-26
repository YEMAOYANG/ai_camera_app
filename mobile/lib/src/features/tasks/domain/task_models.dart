import 'package:warm_sight/src/shared/widgets/status_chip.dart';

enum GuardianTaskStatus {
  scheduled('scheduled', '待开始', StatusTone.neutral),
  pending('pending', '待开始', StatusTone.neutral),
  reminderSent('reminder_sent', '即将开始', StatusTone.neutral),
  inProgress('in_progress', '进行中', StatusTone.success),
  delayed('delayed', '需要提醒', StatusTone.warning),
  completed('completed', '已完成', StatusTone.success),
  awaitingParentConfirmation(
    'awaiting_parent_confirmation',
    '待确认',
    StatusTone.warning,
  ),
  confirmed('confirmed', '已确认', StatusTone.success),
  rejected('rejected', '已驳回', StatusTone.danger),
  missed('missed', '未完成', StatusTone.danger),
  expired('expired', '已过期', StatusTone.danger),
  cancelled('cancelled', '已取消', StatusTone.neutral);

  const GuardianTaskStatus(this.value, this.label, this.tone);

  final String value;
  final String label;
  final StatusTone tone;

  bool get canComplete {
    return this == GuardianTaskStatus.scheduled ||
        this == GuardianTaskStatus.pending ||
        this == GuardianTaskStatus.reminderSent ||
        this == GuardianTaskStatus.inProgress ||
        this == GuardianTaskStatus.delayed;
  }

  bool get awaitsParent =>
      this == GuardianTaskStatus.awaitingParentConfirmation;

  bool get isDone {
    return this == GuardianTaskStatus.completed ||
        this == GuardianTaskStatus.confirmed ||
        this == GuardianTaskStatus.rejected;
  }

  bool get needsCare {
    return this == GuardianTaskStatus.awaitingParentConfirmation ||
        this == GuardianTaskStatus.delayed ||
        this == GuardianTaskStatus.missed ||
        this == GuardianTaskStatus.expired;
  }

  static GuardianTaskStatus fromValue(String value) {
    return GuardianTaskStatus.values.firstWhere(
      (status) => status.value == value,
      orElse: () => GuardianTaskStatus.pending,
    );
  }
}

class GuardianTaskDraft {
  const GuardianTaskDraft({
    required this.childId,
    required this.title,
    required this.taskType,
    required this.date,
    required this.startTime,
    required this.dueTime,
    required this.rewardPoints,
    required this.requiresParentConfirmation,
    this.description = '',
    this.scheduleType = 'one_time',
    this.repeatRule,
    this.priority = 3,
  });

  final String childId;
  final String title;
  final String description;
  final String taskType;
  final DateTime date;
  final String startTime;
  final String dueTime;
  final String scheduleType;
  final Object? repeatRule;
  final int priority;
  final int rewardPoints;
  final bool requiresParentConfirmation;

  Map<String, dynamic> toJson() {
    final dateText = _dateText(date);
    return {
      'childId': childId,
      'title': title,
      'description': description,
      'taskType': taskType,
      'scheduledDate': dateText,
      'scheduledStart': startTime,
      'scheduledEnd': dueTime,
      'startAt': _dateTimeText(dateText, startTime),
      'dueAt': _dateTimeText(dateText, dueTime),
      'scheduleType': scheduleType,
      'repeatRule': repeatRule,
      'priority': priority,
      'rewardPoints': rewardPoints,
      'requiresParentConfirmation': requiresParentConfirmation,
    };
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
    required this.scheduleType,
    required this.startAt,
    required this.dueAt,
    required this.repeatRule,
    required this.status,
    required this.priority,
    required this.scheduledDate,
    required this.scheduledStart,
    required this.scheduledEnd,
    required this.rewardPoints,
    required this.requiresParentConfirmation,
    required this.completionSource,
    required this.evidence,
    required this.evidenceSummary,
    required this.aiObservationSummary,
    required this.rejectionReason,
    required this.createdBy,
    required this.createdAt,
    required this.updatedAt,
    required this.completedAt,
    required this.startedAt,
    required this.endedAt,
    required this.missedAt,
    required this.delayedAt,
    required this.lastReminderAt,
    required this.nextReminderAt,
    required this.delayReminderCount,
    required this.reminderMinutesBefore,
    required this.reminderStatus,
    required this.cameraObservationStatus,
    required this.deviceId,
    required this.timezone,
    required this.confirmedAt,
    required this.rejectedAt,
    required this.pointsGrantedAt,
    this.parentActions = const [],
  });

  final String id;
  final String familyId;
  final String childId;
  final String title;
  final String description;
  final String type;
  final String scheduleType;
  final String startAt;
  final String dueAt;
  final Object? repeatRule;
  final GuardianTaskStatus status;
  final int priority;
  final String scheduledDate;
  final String scheduledStart;
  final String scheduledEnd;
  final int rewardPoints;
  final bool requiresParentConfirmation;
  final String completionSource;
  final Map<String, dynamic> evidence;
  final String evidenceSummary;
  final String aiObservationSummary;
  final String rejectionReason;
  final String createdBy;
  final int createdAt;
  final int updatedAt;
  final int? completedAt;
  final int? startedAt;
  final int? endedAt;
  final int? missedAt;
  final int? delayedAt;
  final int? lastReminderAt;
  final int? nextReminderAt;
  final int delayReminderCount;
  final int reminderMinutesBefore;
  final String reminderStatus;
  final String cameraObservationStatus;
  final String deviceId;
  final String timezone;
  final int? confirmedAt;
  final int? rejectedAt;
  final int? pointsGrantedAt;
  final List<String> parentActions;

  bool hasParentAction(String value) => parentActions.contains(value);

  String get typeLabel {
    return switch (type) {
      'learning' => '学习',
      'life' => '生活习惯',
      'housework' => '收纳整理',
      'sleep' => '午睡/睡眠',
      'schoolbag' => '物品准备',
      'reading_interest' => '阅读/亲子',
      'sports_outdoor' => '运动/户外',
      'custom' => '自定义',
      'checkin' => '用餐',
      'parent_confirmation' => '家长确认',
      'ai_observed' => '看护记录',
      _ => '安排',
    };
  }

  String get scheduleLabel {
    return switch (scheduleType) {
      'daily' => '每天重复',
      'weekly' => '每周重复',
      'weekday' => '工作日',
      _ => '单次任务',
    };
  }

  String get timeLabel {
    if (scheduledStart.isNotEmpty && scheduledEnd.isNotEmpty) {
      return '$scheduledStart - $scheduledEnd';
    }
    if (scheduledStart.isNotEmpty) return scheduledStart;
    if (scheduledEnd.isNotEmpty) return '截止 $scheduledEnd';
    return scheduledDate;
  }

  String get durationLabel {
    if (description.isNotEmpty) return description;
    return scheduledEnd.isNotEmpty ? '按计划执行' : '当天安排';
  }

  String get parentDecisionLabel {
    if (status.awaitsParent) return '等待你确认完成情况';
    if (status == GuardianTaskStatus.confirmed) {
      return rewardPoints > 0 ? '积分已发放' : '已确认';
    }
    if (status == GuardianTaskStatus.rejected) {
      return rewardPoints > 0 ? '未发放积分' : '已驳回';
    }
    if (status == GuardianTaskStatus.delayed) return '需要温和提醒';
    if (status == GuardianTaskStatus.missed) return '未完成';
    if (status == GuardianTaskStatus.completed) {
      return pointsGrantedAt != null && rewardPoints > 0 ? '积分已发放' : '已完成';
    }
    if (!requiresParentConfirmation) return '完成后自动记录';
    return '需要家长确认';
  }

  String get evidenceText {
    if (evidenceSummary.isNotEmpty) return evidenceSummary;
    final summary = evidence['summary'];
    if (summary is String && summary.isNotEmpty) return summary;
    if (status.awaitsParent) {
      return rewardPoints > 0 ? '请确认是否完成，再决定是否发放积分。' : '请确认这次是否完成。';
    }
    if (status == GuardianTaskStatus.missed) {
      return '这次没有看到完成结果，可以重新安排或手动记录。';
    }
    return '完成后会在这里显示观察记录和处理结果。';
  }

  String get observationText {
    if (aiObservationSummary.isNotEmpty) return aiObservationSummary;
    return evidenceText;
  }

  String get aiAdvice {
    if (status.awaitsParent) {
      return rewardPoints > 0 ? '建议先核对证据，再确认是否发放积分。' : '建议先核对记录，再确认是否完成。';
    }
    if (status == GuardianTaskStatus.confirmed) {
      return rewardPoints > 0 ? '任务已经确认，奖励积分已写入流水。' : '任务已经确认，已进入记录。';
    }
    if (status == GuardianTaskStatus.inProgress) {
      return '任务进行中，保持低打扰提醒。';
    }
    if (status == GuardianTaskStatus.delayed) {
      return '孩子还没有开始，系统会继续温和提醒。';
    }
    if (status == GuardianTaskStatus.missed) {
      return '这项安排没有看到完成结果，可以重新安排、手动记录或不处理。';
    }
    if (status == GuardianTaskStatus.rejected) {
      return rejectionReason.isNotEmpty
          ? '原因：$rejectionReason'
          : '本次任务未通过确认，未发放积分。';
    }
    return '按孩子当前节奏推进，不为了积分打断任务本身。';
  }

  String get nextStep {
    if (status.awaitsParent) return '等待你处理任务证据。';
    if (status == GuardianTaskStatus.scheduled ||
        status == GuardianTaskStatus.pending) {
      return '到点后提醒孩子开始。';
    }
    if (status == GuardianTaskStatus.reminderSent) return '已经提醒，等待开始。';
    if (status == GuardianTaskStatus.inProgress) return '完成后进入家长确认。';
    if (status == GuardianTaskStatus.delayed) return '系统会继续温和提醒。';
    if (status == GuardianTaskStatus.missed) return '本次未记录完成。';
    if (status == GuardianTaskStatus.rejected) {
      return '本次任务未通过确认，未发放积分。';
    }
    if (status == GuardianTaskStatus.cancelled) return '任务已取消。';
    return '已进入任务记录。';
  }

  GuardianTask copyWith({
    String? title,
    String? description,
    String? type,
    String? scheduleType,
    String? startAt,
    String? dueAt,
    Object? repeatRule,
    GuardianTaskStatus? status,
    int? priority,
    String? scheduledDate,
    String? scheduledStart,
    String? scheduledEnd,
    int? rewardPoints,
    bool? requiresParentConfirmation,
    String? completionSource,
    Map<String, dynamic>? evidence,
    String? evidenceSummary,
    String? aiObservationSummary,
    String? rejectionReason,
    int? completedAt,
    int? startedAt,
    int? endedAt,
    int? missedAt,
    int? delayedAt,
    int? lastReminderAt,
    int? nextReminderAt,
    int? delayReminderCount,
    int? reminderMinutesBefore,
    String? reminderStatus,
    String? cameraObservationStatus,
    String? deviceId,
    String? timezone,
    int? confirmedAt,
    int? rejectedAt,
    int? pointsGrantedAt,
    List<String>? parentActions,
  }) {
    return GuardianTask(
      id: id,
      familyId: familyId,
      childId: childId,
      title: title ?? this.title,
      description: description ?? this.description,
      type: type ?? this.type,
      scheduleType: scheduleType ?? this.scheduleType,
      startAt: startAt ?? this.startAt,
      dueAt: dueAt ?? this.dueAt,
      repeatRule: repeatRule ?? this.repeatRule,
      status: status ?? this.status,
      priority: priority ?? this.priority,
      scheduledDate: scheduledDate ?? this.scheduledDate,
      scheduledStart: scheduledStart ?? this.scheduledStart,
      scheduledEnd: scheduledEnd ?? this.scheduledEnd,
      rewardPoints: rewardPoints ?? this.rewardPoints,
      requiresParentConfirmation:
          requiresParentConfirmation ?? this.requiresParentConfirmation,
      completionSource: completionSource ?? this.completionSource,
      evidence: evidence ?? this.evidence,
      evidenceSummary: evidenceSummary ?? this.evidenceSummary,
      aiObservationSummary: aiObservationSummary ?? this.aiObservationSummary,
      rejectionReason: rejectionReason == null
          ? this.rejectionReason
          : _normalizeRejectionReason(rejectionReason),
      createdBy: createdBy,
      createdAt: createdAt,
      updatedAt: updatedAt,
      completedAt: completedAt ?? this.completedAt,
      startedAt: startedAt ?? this.startedAt,
      endedAt: endedAt ?? this.endedAt,
      missedAt: missedAt ?? this.missedAt,
      delayedAt: delayedAt ?? this.delayedAt,
      lastReminderAt: lastReminderAt ?? this.lastReminderAt,
      nextReminderAt: nextReminderAt ?? this.nextReminderAt,
      delayReminderCount: delayReminderCount ?? this.delayReminderCount,
      reminderMinutesBefore:
          reminderMinutesBefore ?? this.reminderMinutesBefore,
      reminderStatus: reminderStatus ?? this.reminderStatus,
      cameraObservationStatus:
          cameraObservationStatus ?? this.cameraObservationStatus,
      deviceId: deviceId ?? this.deviceId,
      timezone: timezone ?? this.timezone,
      confirmedAt: confirmedAt ?? this.confirmedAt,
      rejectedAt: rejectedAt ?? this.rejectedAt,
      pointsGrantedAt: pointsGrantedAt ?? this.pointsGrantedAt,
      parentActions: parentActions ?? this.parentActions,
    );
  }

  static GuardianTask fromJson(Map<String, dynamic> json) {
    final scheduledDate = _asString(json['scheduledDate']);
    final scheduledStart = _asString(json['scheduledStart']);
    final scheduledEnd = _asString(json['scheduledEnd']);
    return GuardianTask(
      id: _asString(json['taskId'], fallback: _asString(json['id'])),
      familyId: _asString(json['familyId']),
      childId: _asString(json['childId']),
      title: _asString(json['title'], fallback: '未命名任务'),
      description: _asString(json['description']),
      type: _asString(
        json['taskType'],
        fallback: _asString(json['type'], fallback: 'learning'),
      ),
      scheduleType: _asString(json['scheduleType'], fallback: 'one_time'),
      startAt: _asString(
        json['startAt'],
        fallback: _dateTimeText(scheduledDate, scheduledStart),
      ),
      dueAt: _asString(
        json['dueAt'],
        fallback: _dateTimeText(scheduledDate, scheduledEnd),
      ),
      repeatRule: json['repeatRule'],
      status: GuardianTaskStatus.fromValue(_asString(json['status'])),
      priority: _asInt(json['priority'], fallback: 3),
      scheduledDate: scheduledDate,
      scheduledStart: scheduledStart,
      scheduledEnd: scheduledEnd,
      rewardPoints: _asInt(json['rewardPoints']),
      requiresParentConfirmation: json['requiresParentConfirmation'] is bool
          ? json['requiresParentConfirmation'] as bool
          : true,
      completionSource: _asString(json['completionSource']),
      evidence: _asMap(json['evidence']),
      evidenceSummary: _asString(json['evidenceSummary']),
      aiObservationSummary: _asString(json['aiObservationSummary']),
      rejectionReason: _normalizeRejectionReason(
        _asString(json['rejectionReason']),
      ),
      createdBy: _asString(json['createdBy']),
      createdAt: _asInt(json['createdAt']),
      updatedAt: _asInt(json['updatedAt']),
      completedAt: _asNullableInt(json['completedAt']),
      startedAt: _asNullableInt(json['startedAt']),
      endedAt: _asNullableInt(json['endedAt']),
      missedAt: _asNullableInt(json['missedAt']),
      delayedAt: _asNullableInt(json['delayedAt']),
      lastReminderAt: _asNullableInt(json['lastReminderAt']),
      nextReminderAt: _asNullableInt(json['nextReminderAt']),
      delayReminderCount: _asInt(json['delayReminderCount']),
      reminderMinutesBefore: _asInt(json['reminderMinutesBefore'], fallback: 5),
      reminderStatus: _asString(json['reminderStatus'], fallback: 'pending'),
      cameraObservationStatus: _asString(
        json['cameraObservationStatus'],
        fallback: 'unknown',
      ),
      deviceId: _asString(json['deviceId']),
      timezone: _asString(json['timezone'], fallback: 'Asia/Shanghai'),
      confirmedAt: _asNullableInt(json['confirmedAt']),
      rejectedAt: _asNullableInt(json['rejectedAt']),
      pointsGrantedAt: _asNullableInt(json['pointsGrantedAt']),
      parentActions: _parentActionValues(json['parentActions']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'taskId': id,
      'familyId': familyId,
      'childId': childId,
      'title': title,
      'description': description,
      'type': type,
      'taskType': type,
      'scheduleType': scheduleType,
      'startAt': startAt,
      'dueAt': dueAt,
      'repeatRule': repeatRule,
      'status': status.value,
      'priority': priority,
      'scheduledDate': scheduledDate,
      'scheduledStart': scheduledStart,
      'scheduledEnd': scheduledEnd,
      'rewardPoints': rewardPoints,
      'requiresParentConfirmation': requiresParentConfirmation,
      'completionSource': completionSource,
      'evidence': evidence,
      'evidenceSummary': evidenceSummary,
      'aiObservationSummary': aiObservationSummary,
      'rejectionReason': rejectionReason,
      'createdBy': createdBy,
      'createdAt': createdAt,
      'updatedAt': updatedAt,
      'completedAt': completedAt,
      'startedAt': startedAt,
      'endedAt': endedAt,
      'missedAt': missedAt,
      'delayedAt': delayedAt,
      'lastReminderAt': lastReminderAt,
      'nextReminderAt': nextReminderAt,
      'delayReminderCount': delayReminderCount,
      'reminderMinutesBefore': reminderMinutesBefore,
      'reminderStatus': reminderStatus,
      'cameraObservationStatus': cameraObservationStatus,
      'deviceId': deviceId,
      'timezone': timezone,
      'confirmedAt': confirmedAt,
      'rejectedAt': rejectedAt,
      'pointsGrantedAt': pointsGrantedAt,
      'parentActions': parentActions,
    };
  }
}

class GuardianTaskEvent {
  const GuardianTaskEvent({
    required this.id,
    required this.taskId,
    required this.eventType,
    required this.message,
    required this.payload,
    required this.createdAt,
  });

  final String id;
  final String taskId;
  final String eventType;
  final String message;
  final Map<String, dynamic> payload;
  final int createdAt;

  String get title {
    return switch (eventType) {
      'task_created' => '任务已创建',
      'task_updated' => '任务已更新',
      'manual_started' => '任务已开始',
      'reminder_due' => '准备提醒',
      'reminder_sent' => '已提醒孩子',
      'reminder_failed' => '提醒未送达',
      'start_reminder_sent' || 'manual_start_reminder_sent' => '已提醒开始',
      'start_reminder_failed' || 'manual_start_reminder_failed' => '开始提醒未送达',
      'manual_prepare_reminder_sent' => '已提醒准备',
      'manual_prepare_reminder_failed' => '准备提醒未送达',
      'manual_reminder_sent' => '已提醒孩子',
      'manual_reminder_failed' => '提醒未送达',
      'wrap_up_reminder_sent' => '已提醒收尾',
      'wrap_up_reminder_failed' => '收尾提醒未送达',
      'finish_reminder_sent' || 'manual_finish_reminder_sent' => '已提醒结束',
      'finish_reminder_failed' || 'manual_finish_reminder_failed' => '结束提醒未送达',
      'auto_started' => '任务自动开始',
      'observation_unavailable' => '观察暂不可用',
      'child_not_ready' => '还没开始',
      'delayed' => '需要提醒',
      'delay_reminder_sent' => '已再次提醒',
      'delay_reminder_failed' => '再次提醒未送达',
      'monitor_started' => '开始观察',
      'monitor_failed' => '观察暂不可用',
      'monitor_not_required' => '无需摄像头观察',
      'camera_monitor_started' => '摄像头开始观察',
      'camera_command_failed' => '摄像头暂时离线',
      'ended' || 'auto_finished' => '时间已到',
      'awaiting_parent_confirmation' => '等待确认',
      'completed' => '已完成',
      'missed' => '任务未完成',
      'points_awarded' => '积分已发放',
      'points_award_skipped' => '未发放积分',
      'task_completed' => '已完成',
      'parent_confirmed' => '家长已确认',
      'confirmation_rejected' || 'parent_rejected' => '家长驳回确认',
      _ => message.isNotEmpty ? message : '任务记录',
    };
  }

  String get displayMessage {
    if (message.isNotEmpty) return message;
    return title;
  }

  StatusTone get tone {
    return switch (eventType) {
      'reminder_failed' ||
      'start_reminder_failed' ||
      'manual_start_reminder_failed' ||
      'manual_prepare_reminder_failed' ||
      'manual_reminder_failed' ||
      'wrap_up_reminder_failed' ||
      'finish_reminder_failed' ||
      'manual_finish_reminder_failed' ||
      'delay_reminder_failed' ||
      'monitor_failed' ||
      'child_not_ready' ||
      'delayed' ||
      'camera_command_failed' ||
      'confirmation_rejected' ||
      'parent_rejected' => StatusTone.danger,
      'parent_confirmed' ||
      'task_completed' ||
      'points_awarded' ||
      'completed' ||
      'auto_started' ||
      'start_reminder_sent' ||
      'manual_start_reminder_sent' ||
      'manual_prepare_reminder_sent' ||
      'manual_reminder_sent' ||
      'wrap_up_reminder_sent' ||
      'finish_reminder_sent' ||
      'manual_finish_reminder_sent' ||
      'camera_monitor_started' ||
      'monitor_started' => StatusTone.success,
      _ => StatusTone.neutral,
    };
  }

  static GuardianTaskEvent fromJson(Map<String, dynamic> json) {
    return GuardianTaskEvent(
      id: _asString(json['id']),
      taskId: _asString(json['taskId']),
      eventType: _asString(json['eventType']),
      message: _asString(json['message']),
      payload: _asMap(json['payload']),
      createdAt: _asInt(json['createdAt']),
    );
  }
}

class TaskTemplateCatalog {
  const TaskTemplateCatalog({
    required this.templates,
    required this.tags,
    required this.grades,
    required this.dayTypes,
    required this.recommendedGrade,
    required this.recommendedGradeLabel,
  });

  final List<TaskTemplate> templates;
  final List<TaskTemplateOption> tags;
  final List<TaskTemplateOption> grades;
  final List<TaskTemplateOption> dayTypes;
  final String recommendedGrade;
  final String recommendedGradeLabel;

  static TaskTemplateCatalog fromJson(Map<String, dynamic> json) {
    return TaskTemplateCatalog(
      templates: _asList(
        json['templates'],
      ).map((item) => TaskTemplate.fromJson(_asMap(item))).toList(),
      tags: _asList(
        json['tags'],
      ).map((item) => TaskTemplateOption.fromJson(_asMap(item))).toList(),
      grades: _asList(
        json['grades'],
      ).map((item) => TaskTemplateOption.fromJson(_asMap(item))).toList(),
      dayTypes: _asList(
        json['dayTypes'],
      ).map((item) => TaskTemplateOption.fromJson(_asMap(item))).toList(),
      recommendedGrade: _asString(json['recommendedGrade'], fallback: 'small'),
      recommendedGradeLabel: _asString(
        json['recommendedGradeLabel'],
        fallback: '小班',
      ),
    );
  }
}

class TaskTemplate {
  const TaskTemplate({
    required this.id,
    required this.templateKey,
    required this.title,
    required this.subtitle,
    required this.grade,
    required this.gradeLabel,
    required this.ageGroups,
    required this.scheduleType,
    required this.dayType,
    required this.dayTypeLabel,
    required this.tags,
    required this.tagLabels,
    required this.rows,
  });

  final String id;
  final String templateKey;
  final String title;
  final String subtitle;
  final String grade;
  final String gradeLabel;
  final List<String> ageGroups;
  final String scheduleType;
  final String dayType;
  final String dayTypeLabel;
  final List<String> tags;
  final List<String> tagLabels;
  final List<TaskTemplateRow> rows;

  static TaskTemplate fromJson(Map<String, dynamic> json) {
    return TaskTemplate(
      id: _asString(json['id']),
      templateKey: _asString(json['templateKey']),
      title: _asString(json['title']),
      subtitle: _asString(json['subtitle']),
      grade: _asString(json['grade']),
      gradeLabel: _asString(json['gradeLabel']),
      ageGroups: _stringList(json['ageGroups']),
      scheduleType: _asString(json['scheduleType'], fallback: 'one_time'),
      dayType: _asString(json['dayType']),
      dayTypeLabel: _asString(json['dayTypeLabel']),
      tags: _stringList(json['tags']),
      tagLabels: _stringList(json['tagLabels']),
      rows: _asList(
        json['rows'],
      ).map((item) => TaskTemplateRow.fromJson(_asMap(item))).toList(),
    );
  }
}

class TaskTemplateRow {
  const TaskTemplateRow({
    required this.startTime,
    required this.endTime,
    required this.taskType,
    required this.title,
    required this.rewardPoints,
    required this.requiresParentConfirmation,
  });

  final String startTime;
  final String endTime;
  final String taskType;
  final String title;
  final int rewardPoints;
  final bool requiresParentConfirmation;

  static TaskTemplateRow fromJson(Map<String, dynamic> json) {
    return TaskTemplateRow(
      startTime: _asString(json['startTime']),
      endTime: _asString(json['endTime']),
      taskType: _asString(json['taskType']),
      title: _asString(json['title']),
      rewardPoints: _asInt(json['rewardPoints']),
      requiresParentConfirmation: json['requiresParentConfirmation'] is bool
          ? json['requiresParentConfirmation'] as bool
          : false,
    );
  }
}

class TaskTemplateOption {
  const TaskTemplateOption({required this.value, required this.label});

  final String value;
  final String label;

  static TaskTemplateOption fromJson(Map<String, dynamic> json) {
    return TaskTemplateOption(
      value: _asString(json['value']),
      label: _asString(json['label']),
    );
  }
}

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
}

int _asInt(dynamic value, {int fallback = 0}) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? fallback;
  return fallback;
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

List<dynamic> _asList(dynamic value) {
  return value is List ? value : const [];
}

List<String> _stringList(dynamic value) {
  return _asList(
    value,
  ).whereType<String>().where((item) => item.isNotEmpty).toList();
}

List<String> _parentActionValues(dynamic value) {
  return _asList(value)
      .map((item) {
        if (item is String) return item;
        if (item is Map) return _asString(item['value']);
        return '';
      })
      .where((item) => item.isNotEmpty)
      .toList();
}

String _dateText(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

String _dateTimeText(String date, String time) {
  if (date.isEmpty || time.isEmpty) return '';
  return '${date}T$time:00';
}

String _normalizeRejectionReason(String value) {
  if (value.isEmpty) return value;
  const legacyPhrases = ['等待孩子补充完成', '等待补充完成', '孩子补充', '补充完成'];
  if (legacyPhrases.any((phrase) => value.contains(phrase))) {
    return '证据不足，未通过家长确认。';
  }
  return value;
}
