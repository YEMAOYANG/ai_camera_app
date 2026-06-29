import 'dart:typed_data';

import 'package:warm_sight/src/features/tasks/domain/task_models.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class CameraHealth {
  const CameraHealth({
    required this.ok,
    required this.reachable,
    required this.adapter,
    required this.serviceLabel,
    required this.message,
  });

  final bool ok;
  final bool reachable;
  final String adapter;
  final String serviceLabel;
  final String message;

  StatusTone get tone {
    if (reachable) return StatusTone.success;
    return StatusTone.danger;
  }

  String get label => reachable ? '摄像头服务在线' : '摄像头服务不可用';

  static CameraHealth fromJson(Map<String, dynamic> json) {
    final runtime = _asMap(json['cameraRuntime']);
    final data = _asMap(runtime['data']);
    final reachable = runtime['reachable'] == true;
    final error = _asString(runtime['error']);
    return CameraHealth(
      ok: json['ok'] == true,
      reachable: reachable,
      adapter: _asString(runtime['adapter']),
      serviceLabel: _asString(data['service'], fallback: '摄像头服务'),
      message: reachable
          ? '摄像头服务在线'
          : error.isNotEmpty
          ? error
          : '摄像头暂时不可用',
    );
  }
}

class CameraRuntime {
  const CameraRuntime({
    required this.ok,
    required this.reachable,
    required this.adapter,
    required this.voiceState,
    required this.voiceRunning,
    required this.message,
  });

  final bool ok;
  final bool reachable;
  final String adapter;
  final String voiceState;
  final bool voiceRunning;
  final String message;

  String get stateLabel {
    if (!reachable) return '摄像头状态不可用';
    if (voiceRunning) return '语音提醒处理中';
    return switch (voiceState) {
      'idle' => '安静观察中',
      'running' => '看护提醒处理中',
      'paused' => '已暂停',
      _ => voiceState.isNotEmpty ? voiceState : '基础看护在线',
    };
  }

  String get summary {
    if (!reachable) return message;
    if (voiceRunning) return '设备正在处理语音/看护运行状态，家长可稍后刷新查看。';
    return '设备可用，基础看护可以继续。';
  }

  static CameraRuntime fromJson(Map<String, dynamic> json) {
    final runtime = _asMap(json['cameraRuntime']);
    final data = _asMap(runtime['data']);
    final voice = _asMap(data['voice']);
    final reachable = runtime['reachable'] == true;
    final error = _asString(runtime['error']);
    return CameraRuntime(
      ok: json['ok'] == true,
      reachable: reachable,
      adapter: _asString(runtime['adapter']),
      voiceState: _asString(voice['state']),
      voiceRunning: voice['running'] == true,
      message: reachable
          ? '运行状态可查看'
          : error.isNotEmpty
          ? error
          : '摄像头运行状态暂时不可用',
    );
  }
}

class CameraSnapshotFrame {
  const CameraSnapshotFrame({
    required this.available,
    required this.bytes,
    required this.contentType,
    required this.message,
  });

  final bool available;
  final Uint8List? bytes;
  final String contentType;
  final String message;

  static const unavailable = CameraSnapshotFrame(
    available: false,
    bytes: null,
    contentType: '',
    message: '实时画面暂时不可用',
  );
}

class CameraWebRtcSession {
  const CameraWebRtcSession({
    required this.signalingUrl,
    required this.message,
  });

  final String signalingUrl;
  final String message;

  static CameraWebRtcSession fromJson(Map<String, dynamic> json) {
    final session = _asMap(json['session']);
    return CameraWebRtcSession(
      signalingUrl: _asString(session['signalingUrl']),
      message: _asString(session['message'], fallback: '实时画面连接已准备好。'),
    );
  }

  CameraWebRtcSession normalizedForApiBase(String apiBaseUrl) {
    final signalingUri = Uri.tryParse(signalingUrl);
    final apiUri = Uri.tryParse(apiBaseUrl);
    if (signalingUri == null ||
        apiUri == null ||
        signalingUri.host.isEmpty ||
        apiUri.host.isEmpty ||
        !_isLoopbackHost(signalingUri.host) ||
        _isLoopbackHost(apiUri.host)) {
      return this;
    }
    final scheme = apiUri.scheme == 'https' ? 'wss' : 'ws';
    return CameraWebRtcSession(
      signalingUrl: signalingUri
          .replace(scheme: scheme, host: apiUri.host)
          .toString(),
      message: message,
    );
  }
}

bool _isLoopbackHost(String host) {
  final normalized = host.toLowerCase();
  return normalized == '127.0.0.1' ||
      normalized == 'localhost' ||
      normalized == '::1';
}

class CameraStatus {
  const CameraStatus({
    required this.connectionStatus,
    required this.streamAvailable,
    required this.snapshotAvailable,
    required this.speakerAvailable,
    required this.monitorAvailable,
    required this.ptzAvailable,
    required this.lastSeenAt,
    required this.runtimeProvider,
    required this.message,
    this.currentTask,
  });

  final String connectionStatus;
  final bool streamAvailable;
  final bool snapshotAvailable;
  final bool speakerAvailable;
  final bool monitorAvailable;
  final bool ptzAvailable;
  final int? lastSeenAt;
  final String runtimeProvider;
  final String message;
  final GuardianTask? currentTask;

  bool get isOnline => connectionStatus == 'online';

  StatusTone get tone {
    return switch (connectionStatus) {
      'online' => StatusTone.success,
      'connecting' => StatusTone.warning,
      'error' || 'offline' => StatusTone.danger,
      _ => StatusTone.neutral,
    };
  }

  String get label {
    return switch (connectionStatus) {
      'online' => '摄像头在线',
      'connecting' => '正在连接',
      'error' => '连接异常',
      'offline' => '摄像头离线',
      _ => '状态检查中',
    };
  }

  String get summary {
    if (message.isNotEmpty) return message;
    return isOnline ? '摄像头在线，可以查看画面。' : '摄像头暂时离线，任务仍会按计划记录。';
  }

  static CameraStatus fromJson(Map<String, dynamic> json) {
    final status = _asMap(json['status']);
    final task = _asMap(status['currentTask']);
    return CameraStatus(
      connectionStatus: _asString(
        status['connectionStatus'],
        fallback: 'offline',
      ),
      streamAvailable: status['streamAvailable'] == true,
      snapshotAvailable: status['snapshotAvailable'] == true,
      speakerAvailable: status['speakerAvailable'] == true,
      monitorAvailable: status['monitorAvailable'] == true,
      ptzAvailable: status['ptzAvailable'] == true,
      lastSeenAt: _asNullableInt(status['lastSeenAt']),
      runtimeProvider: _asString(status['runtimeProvider']),
      message: _asString(status['message']),
      currentTask: task.isEmpty ? null : GuardianTask.fromJson(task),
    );
  }
}

class CameraMonitorStatus {
  const CameraMonitorStatus({
    required this.running,
    required this.status,
    required this.message,
    required this.lastObservation,
    required this.lastReminder,
    this.lastObservationObservedAt,
    this.lastObservationReliable = false,
    this.lastObservationHasPerson,
    this.lastObservationActivity = '',
    this.lastObservationDescription = '',
    this.lastObservationDecisionReason = '',
    this.lastObservationConfidence,
    this.lastObservationThumbnailUrl = '',
    this.lastObservationFreshness = CameraObservationFreshness.unknown,
  });

  final bool running;
  final String status;
  final String message;
  final String lastObservation;
  final String lastReminder;
  final int? lastObservationObservedAt;
  final bool lastObservationReliable;
  final bool? lastObservationHasPerson;
  final String lastObservationActivity;
  final String lastObservationDescription;
  final String lastObservationDecisionReason;
  final double? lastObservationConfidence;
  final String lastObservationThumbnailUrl;
  final CameraObservationFreshness lastObservationFreshness;

  String get label => running ? '观察中' : '未观察';

  StatusTone get tone => running ? StatusTone.success : StatusTone.neutral;

  bool get hasFreshObservation =>
      lastObservationFreshness == CameraObservationFreshness.fresh;

  bool get hasStaleObservation =>
      lastObservationFreshness == CameraObservationFreshness.stale &&
      lastObservation.isNotEmpty;

  bool get hasCurrentReliableObservation =>
      lastObservationFreshness == CameraObservationFreshness.fresh &&
      lastObservationReliable &&
      lastObservation.isNotEmpty;

  String displayObservationTitle({DateTime? now}) {
    return parentFacingObservationWithFreshness(
      freshness: lastObservationFreshness,
      summary: lastObservation,
      observedAt: lastObservationObservedAt,
      now: now ?? DateTime.now(),
    );
  }

  static CameraMonitorStatus fromJson(Map<String, dynamic> json) {
    final monitor = _asMap(json['monitor']);
    final observation = _observationSnapshot(monitor['lastObservation']);
    return CameraMonitorStatus(
      running: monitor['running'] == true,
      status: _asString(monitor['status'], fallback: 'idle'),
      message: _asString(monitor['message']),
      lastObservation: observation.summary,
      lastReminder: _asString(monitor['lastReminder']),
      lastObservationObservedAt: observation.observedAt,
      lastObservationReliable: observation.isReliable,
      lastObservationHasPerson: observation.hasPerson,
      lastObservationActivity: observation.activity,
      lastObservationDescription: observation.description,
      lastObservationDecisionReason: observation.decisionReason,
      lastObservationConfidence: observation.confidence,
      lastObservationThumbnailUrl: observation.thumbnailUrl,
      lastObservationFreshness: observation.freshness,
    );
  }
}

const cameraObservationFreshness = Duration(seconds: 300);

enum CameraObservationFreshness {
  fresh,
  stale,
  prefilterOnly,
  unknown;

  static CameraObservationFreshness fromApi(String? value) {
    switch (value?.trim().toLowerCase()) {
      case 'fresh':
        return CameraObservationFreshness.fresh;
      case 'stale':
        return CameraObservationFreshness.stale;
      case 'prefilter_only':
        return CameraObservationFreshness.prefilterOnly;
      default:
        return CameraObservationFreshness.unknown;
    }
  }
}

int? staleObservationAgeMinutes(int? observedAt, {required DateTime now}) {
  if (observedAt == null || observedAt <= 0) return null;
  final ageMs = now.millisecondsSinceEpoch - observedAt;
  if (ageMs < 0) return null;
  return (ageMs / 60000).ceil().clamp(1, 9999);
}

String parentFacingObservationWithFreshness({
  required CameraObservationFreshness freshness,
  required String summary,
  required int? observedAt,
  required DateTime now,
}) {
  if (freshness == CameraObservationFreshness.prefilterOnly) {
    return '画面已更新，正在整理观察结果';
  }
  final cleaned = summary.trim();
  if (cleaned.isEmpty) return '';
  if (freshness != CameraObservationFreshness.stale) {
    return cleaned;
  }
  final minutes = staleObservationAgeMinutes(observedAt, now: now);
  final detail = _staleObservationDetail(cleaned);
  if (minutes != null) {
    return '约 $minutes 分钟前观察到$detail';
  }
  return '较早观察到$detail';
}

String _staleObservationDetail(String summary) {
  if (summary.startsWith('孩子正在')) {
    return summary.replaceFirst('孩子正在', '');
  }
  if (summary.startsWith('看到孩子在')) {
    return summary.replaceFirst('看到孩子在', '');
  }
  return summary;
}

class _CameraObservationSnapshot {
  const _CameraObservationSnapshot({
    required this.summary,
    required this.isReliable,
    required this.hasPerson,
    required this.activity,
    required this.description,
    required this.decisionReason,
    required this.thumbnailUrl,
    required this.freshness,
    this.confidence,
    this.observedAt,
  });

  final String summary;
  final bool isReliable;
  final bool? hasPerson;
  final String activity;
  final String description;
  final String decisionReason;
  final String thumbnailUrl;
  final double? confidence;
  final int? observedAt;
  final CameraObservationFreshness freshness;
}

class LiveCareStatus {
  const LiveCareStatus({
    required this.health,
    required this.runtime,
    this.cameraStatus,
    this.monitorStatus,
  });

  final CameraHealth health;
  final CameraRuntime runtime;
  final CameraStatus? cameraStatus;
  final CameraMonitorStatus? monitorStatus;

  bool get isAvailable =>
      cameraStatus?.isOnline ?? (health.reachable && runtime.reachable);

  StatusTone get tone =>
      cameraStatus?.tone ??
      (isAvailable ? StatusTone.success : StatusTone.danger);

  String get label =>
      cameraStatus?.label ?? (isAvailable ? '在线看护可用' : '看护服务降级');

  GuardianTask? get currentTask => cameraStatus?.currentTask;

  bool get ptzAvailable => cameraStatus?.ptzAvailable ?? false;

  String get title {
    return isAvailable ? '实时看护可用。' : '实时画面暂时不可用。';
  }

  String get detail {
    if (cameraStatus != null) return cameraStatus!.summary;
    return isAvailable ? runtime.summary : '我们暂时拿不到实时画面。请确认设备电源和家庭网络后再刷新。';
  }
}

class CameraEventsPage {
  const CameraEventsPage({required this.events, required this.hasMore});

  final List<LiveCareEvent> events;
  final bool hasMore;
}

class CameraEventsState {
  const CameraEventsState({
    this.items = const [],
    this.hasMore = false,
    this.isLoadingMore = false,
    this.loadedCount = 0,
  });

  final List<LiveCareEvent> items;
  final bool hasMore;
  final bool isLoadingMore;
  final int loadedCount;

  CameraEventsState copyWith({
    List<LiveCareEvent>? items,
    bool? hasMore,
    bool? isLoadingMore,
    int? loadedCount,
  }) {
    return CameraEventsState(
      items: items ?? this.items,
      hasMore: hasMore ?? this.hasMore,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      loadedCount: loadedCount ?? this.loadedCount,
    );
  }
}

class LiveCareEvent {
  const LiveCareEvent({
    required this.id,
    required this.source,
    required this.eventType,
    required this.title,
    required this.message,
    required this.displayTitle,
    required this.displayMessage,
    required this.category,
    required this.severity,
    required this.taskTitle,
    required this.evidenceSummary,
    required this.hasReplay,
    required this.status,
    required this.toneKey,
    required this.createdAt,
    this.recordKind = '',
  });

  final String id;
  final String source;
  final String eventType;
  final String title;
  final String message;
  final String displayTitle;
  final String displayMessage;
  final String category;
  final String severity;
  final String taskTitle;
  final String evidenceSummary;
  final bool hasReplay;
  final String status;
  final String toneKey;
  final int createdAt;
  final String recordKind;

  bool get isRoutineRecord => recordKind == 'routine';

  bool get isVisionRecord => recordKind == 'vision';

  bool get isReminderRecord => recordKind == 'reminder';

  bool get isCareRecord {
    return switch (category) {
      'camera_observation' ||
      'child_presence' ||
      'care_reminder' ||
      'snapshot' ||
      'camera_status' => true,
      _ => false,
    };
  }

  StatusTone get tone {
    return switch (toneKey) {
      'success' => StatusTone.success,
      'warning' => StatusTone.warning,
      'danger' => StatusTone.danger,
      'info' => StatusTone.neutral,
      _ => StatusTone.neutral,
    };
  }

  String get timeLabel {
    if (createdAt <= 0) return '刚刚';
    final time = DateTime.fromMillisecondsSinceEpoch(createdAt);
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final day = DateTime(time.year, time.month, time.day);
    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    if (day == today) return '今天 $hour:$minute';
    if (day == today.subtract(const Duration(days: 1))) {
      return '昨天 $hour:$minute';
    }
    return '${time.month}月${time.day}日 $hour:$minute';
  }

  static LiveCareEvent fromJson(Map<String, dynamic> json) {
    final category = _asString(json['category'], fallback: 'care_record');
    final rawDisplayTitle = _asString(
      json['displayTitle'],
      fallback: _asString(json['title'], fallback: '看护记录'),
    );
    final rawDisplayMessage = _asString(
      json['displayMessage'],
      fallback: _asString(json['message']),
    );
    final shouldNormalizeObservationCopy =
        category == 'camera_observation' ||
        category == 'child_presence' ||
        category == 'snapshot';
    final displayTitle = shouldNormalizeObservationCopy
        ? _parentFacingObservationTitle(rawDisplayTitle)
        : rawDisplayTitle;
    final displayMessage = shouldNormalizeObservationCopy
        ? parentFacingCameraObservationText(rawDisplayMessage, maxLength: 72)
        : rawDisplayMessage;
    return LiveCareEvent(
      id: _asString(json['id']),
      source: _asString(json['source']),
      eventType: _asString(json['eventType']),
      title: _asString(json['title'], fallback: '看护事件'),
      message: _asString(json['message']),
      displayTitle: displayTitle.isNotEmpty ? displayTitle : '看护记录',
      displayMessage: displayMessage,
      category: category,
      severity: _asString(
        json['severity'],
        fallback: _asString(json['tone'], fallback: 'info'),
      ),
      taskTitle: _asString(json['taskTitle']),
      evidenceSummary: _asString(json['evidenceSummary']),
      hasReplay: json['hasReplay'] == true,
      status: _asString(json['status']),
      toneKey: _asString(json['tone']),
      createdAt: _asNullableInt(json['createdAt']) ?? 0,
      recordKind: _asString(json['recordKind']),
    );
  }
}

class CameraException implements Exception {
  const CameraException(this.message, {this.code = 'camera_error'});

  final String message;
  final String code;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
}

_CameraObservationSnapshot _observationSnapshot(dynamic value) {
  if (value is String && value.isNotEmpty) {
    final summary = _sanitizeObservationText(value);
    return _CameraObservationSnapshot(
      summary: summary,
      isReliable: summary.isNotEmpty,
      hasPerson: null,
      activity: '',
      description: '',
      decisionReason: '',
      thumbnailUrl: '',
      freshness: CameraObservationFreshness.unknown,
    );
  }
  final data = _asMap(value);
  if (data.isEmpty) {
    return const _CameraObservationSnapshot(
      summary: '',
      isReliable: false,
      hasPerson: null,
      activity: '',
      description: '',
      decisionReason: '',
      thumbnailUrl: '',
      freshness: CameraObservationFreshness.unknown,
    );
  }
  final rawDescription = _asString(data['description']);
  final description = parentFacingCameraObservationText(
    rawDescription,
    maxLength: 72,
  );
  final activity = _normalizeActivityLabel(
    _asString(data['activity'] ?? data['raw_activity']),
    description: rawDescription,
  );
  final hasPersonValue = data['has_person'] ?? data['hasPerson'];
  final hasPerson = hasPersonValue == true;
  final observedAt = _asNullableInt(
    data['observedAt'] ?? data['observed_at'] ?? data['timestamp'],
  );
  final decisionReason = parentFacingCameraObservationText(
    _asString(data['decisionReason'] ?? data['decision_reason']),
    maxLength: 72,
  );
  final thumbnailUrl = _asString(
    data['thumbnailUrl'] ?? data['thumbnail_url'] ?? data['snapshotUrl'],
  );
  final confidence = _asNullableDouble(data['confidence']);
  final freshness = _resolveObservationFreshness(data, observedAt: observedAt);
  final isReliable =
      data['isReliable'] == true &&
      freshness == CameraObservationFreshness.fresh;
  final hasPersonResolved = hasPersonValue == true
      ? true
      : hasPersonValue == false
      ? false
      : null;

  if (freshness == CameraObservationFreshness.prefilterOnly) {
    return _CameraObservationSnapshot(
      summary: '',
      isReliable: false,
      hasPerson: hasPersonResolved,
      activity: activity,
      description: description,
      decisionReason: decisionReason,
      thumbnailUrl: thumbnailUrl,
      confidence: confidence,
      observedAt: observedAt,
      freshness: freshness,
    );
  }

  final summary = _buildObservationSummary(
    data: data,
    rawDescription: rawDescription,
    activity: activity,
    hasPerson: hasPerson,
    hasPersonValue: hasPersonValue,
  );
  final displaySummary =
      freshness == CameraObservationFreshness.stale &&
          !_staleObservationIsMeaningful(summary)
      ? ''
      : summary;

  if (!isReliable && freshness != CameraObservationFreshness.stale) {
    return _CameraObservationSnapshot(
      summary: '',
      isReliable: false,
      hasPerson: hasPersonResolved,
      activity: activity,
      description: description,
      decisionReason: decisionReason,
      thumbnailUrl: thumbnailUrl,
      confidence: confidence,
      observedAt: observedAt,
      freshness: freshness,
    );
  }

  return _CameraObservationSnapshot(
    summary: displaySummary,
    isReliable: isReliable,
    hasPerson: hasPersonValue == false ? false : hasPerson,
    activity: activity,
    description: description,
    decisionReason: decisionReason,
    thumbnailUrl: thumbnailUrl,
    confidence: confidence,
    observedAt: observedAt,
    freshness: freshness,
  );
}

CameraObservationFreshness _resolveObservationFreshness(
  Map<String, dynamic> data, {
  required int? observedAt,
}) {
  final explicit = CameraObservationFreshness.fromApi(_asString(data['freshness']));
  if (explicit != CameraObservationFreshness.unknown) {
    return explicit;
  }
  if (observedAt != null && observedAt > 0) {
    return _isFreshObservation(observedAt)
        ? CameraObservationFreshness.fresh
        : CameraObservationFreshness.stale;
  }
  if (data['isReliable'] != true) {
    return CameraObservationFreshness.prefilterOnly;
  }
  return CameraObservationFreshness.unknown;
}

String _buildObservationSummary({
  required Map<String, dynamic> data,
  required String rawDescription,
  required String activity,
  required bool hasPerson,
  required Object? hasPersonValue,
}) {
  final summary = _sanitizeObservationText(
    _asString(data['summary']),
    description: rawDescription,
  );
  if (summary.isNotEmpty) return summary;
  if (activity.isNotEmpty && hasPerson) {
    return activity == '玩玩具' ? '孩子正在玩玩具' : '孩子正在$activity';
  }
  if (hasPersonValue == false) {
    return '暂未看到孩子';
  }
  if (hasPersonValue == true) {
    return '画面暂时无法判断';
  }
  return '';
}

bool _staleObservationIsMeaningful(String summary) {
  const ignored = {'暂未看到孩子', '画面暂时无法判断'};
  return summary.isNotEmpty && !ignored.contains(summary);
}

bool _isFreshObservation(int? observedAt) {
  if (observedAt == null || observedAt <= 0) return false;
  final age = DateTime.now().millisecondsSinceEpoch - observedAt;
  return age >= 0 && age <= cameraObservationFreshness.inMilliseconds;
}

const _genericActivityLabels = {'其他', '未知', '无明显活动', 'other', 'unknown'};

String _normalizeActivityLabel(String activity, {String description = ''}) {
  final trimmed = activity.trim();
  if (trimmed.isEmpty) return '';
  if (_genericActivityLabels.contains(trimmed)) return '';
  if (_genericActivityLabels.contains(trimmed.toLowerCase())) return '';
  if (trimmed == '玩玩具' && _containsNegatedToy(description)) return '';
  return trimmed;
}

String _sanitizeObservationText(String text, {String description = ''}) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return '';
  if (trimmed.contains('玩玩具') && _containsNegatedToy(description)) return '';
  if (_weakPresenceObservationTexts.contains(trimmed)) return '';
  for (final generic in _genericActivityLabels) {
    if (trimmed.endsWith('：$generic') || trimmed.endsWith(': $generic')) {
      return '';
    }
  }
  if (trimmed.startsWith('画面记录到孩子正在进行：')) {
    final activity = trimmed.replaceFirst('画面记录到孩子正在进行：', '');
    final normalized = _normalizeActivityLabel(
      activity,
      description: description,
    );
    if (normalized.isEmpty) return '';
    return '看到孩子在$normalized。';
  }
  return trimmed;
}

String _parentFacingObservationTitle(String text) {
  final cleaned = text.trim();
  if (cleaned.isEmpty) return '';
  if (cleaned.startsWith('孩子正在') ||
      cleaned.startsWith('暂未看到') ||
      cleaned.startsWith('画面暂时')) {
    return cleaned.length <= 28 ? cleaned : '${cleaned.substring(0, 28)}…';
  }
  return parentFacingCameraObservationText(
    cleaned,
    maxLength: 28,
    ensureSentenceEnd: false,
  );
}

String parentFacingCameraObservationText(
  String text, {
  int maxLength = 64,
  bool ensureSentenceEnd = true,
}) {
  var cleaned = text.trim();
  if (cleaned.isEmpty) return '';
  cleaned = cleaned
      .replaceAll(RegExp(r'\s+'), ' ')
      .replaceAll(RegExp(r'[。；;]\s*'), '，')
      .replaceAll(RegExp(r'，{2,}'), '，')
      .trim();
  cleaned = cleaned
      .replaceFirst(RegExp(r'^画面中有一个人'), '孩子')
      .replaceFirst(RegExp(r'^画面里有一个人'), '孩子')
      .replaceFirst(RegExp(r'^镜头里有一个人'), '孩子')
      .replaceFirst(RegExp(r'^一个人'), '孩子')
      .replaceFirst(RegExp(r'^有人'), '孩子')
      .replaceFirst(RegExp(r'^一名儿童'), '孩子')
      .replaceFirst(RegExp(r'^一名孩子'), '孩子')
      .replaceFirst(RegExp(r'^一个小孩'), '孩子')
      .replaceFirst(RegExp(r'^一名小孩'), '孩子');
  cleaned = cleaned
      .replaceAll(RegExp(r'画面[中里]?可见一个人的'), '画面中可见孩子的')
      .replaceAll(RegExp(r'可见一个人的'), '可见孩子的')
      .replaceAll(RegExp(r'一个人的'), '孩子的')
      .replaceAll('小孩', '孩子')
      .replaceAll('儿童', '孩子')
      .replaceAll('似乎', '可能');

  final postureRisk = RegExp(
    r'(头部距离桌面很近|头.*桌面.*近|趴在桌|趴桌|头部埋|埋在双臂|坐姿)',
  ).hasMatch(cleaned);
  if (postureRisk) {
    return '孩子低头靠近桌面，注意坐姿。';
  }
  if (RegExp(r'(玩手机|看手机|操作手机)').hasMatch(cleaned)) {
    return '孩子在玩手机，注意休息。';
  }
  final screenFocus =
      RegExp(r'(电视|电脑|平板|屏幕|看屏幕)').hasMatch(cleaned) &&
      RegExp(r'(低头|操作|观看|看|玩)').hasMatch(cleaned);
  if (screenFocus) {
    return '孩子在看屏幕，注意用眼距离。';
  }

  final clauses = cleaned
      .split(RegExp(r'[，,]'))
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .where((item) => !_isLowValueSceneInventory(item))
      .take(2)
      .toList();
  final compact = clauses.isEmpty ? cleaned : clauses.join('，');
  if (compact.length <= maxLength) {
    return ensureSentenceEnd ? _ensureSentenceEnd(compact) : compact;
  }
  return '${compact.substring(0, maxLength)}…';
}

bool _isLowValueSceneInventory(String text) {
  return RegExp(
    r'^(桌上有|桌面有|面前有|旁边有|周围有|左侧有|右侧有|背景有|地上有|画面中有|画面里有)',
  ).hasMatch(text);
}

String _ensureSentenceEnd(String text) {
  if (text.isEmpty || text.endsWith('。') || text.endsWith('…')) {
    return text;
  }
  return '$text。';
}

bool _containsNegatedToy(String text) {
  if (text.trim().isEmpty) return false;
  return RegExp(
    r'(没有|没|未|未见|看不到|没有看到)[^，。,.]{0,18}(玩具|积木|toy|toys)',
  ).hasMatch(text.toLowerCase());
}

const _weakPresenceObservationTexts = {
  '看到孩子在画面里。',
  '看到孩子在画面里',
  '画面里看到孩子。',
  '画面里看到孩子',
};

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

double? _asNullableDouble(dynamic value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  if (value is String) return double.tryParse(value);
  return null;
}
