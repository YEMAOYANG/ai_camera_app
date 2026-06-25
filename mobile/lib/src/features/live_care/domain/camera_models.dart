import 'dart:typed_data';

import 'package:guardian_parent_app/src/features/tasks/domain/task_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

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

  String get label => running ? '观察中' : '未观察';

  StatusTone get tone => running ? StatusTone.success : StatusTone.neutral;

  bool get hasFreshObservation {
    final observedAt = lastObservationObservedAt;
    if (observedAt == null || observedAt <= 0) {
      return lastObservation.isNotEmpty;
    }
    final age = DateTime.now().millisecondsSinceEpoch - observedAt;
    return age >= 0 && age <= cameraObservationFreshness.inMilliseconds;
  }

  bool get hasCurrentReliableObservation =>
      lastObservationReliable &&
      hasFreshObservation &&
      lastObservation.isNotEmpty;

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
    );
  }
}

const cameraObservationFreshness = Duration(seconds: 120);

class _CameraObservationSnapshot {
  const _CameraObservationSnapshot({
    required this.summary,
    required this.isReliable,
    required this.hasPerson,
    required this.activity,
    this.observedAt,
  });

  final String summary;
  final bool isReliable;
  final bool? hasPerson;
  final String activity;
  final int? observedAt;
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

  bool get isCareRecord {
    return switch (category) {
      'camera_observation' ||
      'child_presence' ||
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
    return LiveCareEvent(
      id: _asString(json['id']),
      source: _asString(json['source']),
      eventType: _asString(json['eventType']),
      title: _asString(json['title'], fallback: '看护事件'),
      message: _asString(json['message']),
      displayTitle: _asString(
        json['displayTitle'],
        fallback: _asString(json['title'], fallback: '看护记录'),
      ),
      displayMessage: _asString(
        json['displayMessage'],
        fallback: _asString(json['message']),
      ),
      category: _asString(json['category'], fallback: 'care_record'),
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
    );
  }
  final data = _asMap(value);
  if (data.isEmpty) {
    return const _CameraObservationSnapshot(
      summary: '',
      isReliable: false,
      hasPerson: null,
      activity: '',
    );
  }
  final activity = _normalizeActivityLabel(
    _asString(data['activity'] ?? data['raw_activity']),
  );
  final hasPersonValue = data['has_person'] ?? data['hasPerson'];
  final hasPerson = hasPersonValue == true;
  final observedAt = _asNullableInt(
    data['observedAt'] ?? data['observed_at'] ?? data['timestamp'],
  );
  final isFresh = _isFreshObservation(observedAt);
  final isReliable = data['isReliable'] == true && isFresh;
  if (!isReliable) {
    return _CameraObservationSnapshot(
      summary: '',
      isReliable: false,
      hasPerson: hasPersonValue == true
          ? true
          : hasPersonValue == false
          ? false
          : null,
      activity: activity,
      observedAt: observedAt,
    );
  }
  final summary = _sanitizeObservationText(_asString(data['summary']));
  if (summary.isNotEmpty) {
    return _CameraObservationSnapshot(
      summary: summary,
      isReliable: true,
      hasPerson: hasPersonValue == false ? false : hasPerson,
      activity: activity,
      observedAt: observedAt,
    );
  }
  if (activity.isNotEmpty && hasPerson) {
    return _CameraObservationSnapshot(
      summary: activity == '玩玩具' ? '孩子正在玩玩具' : '孩子正在$activity',
      isReliable: true,
      hasPerson: true,
      activity: activity,
      observedAt: observedAt,
    );
  }
  if (hasPersonValue == false) {
    return _CameraObservationSnapshot(
      summary: '暂未看到孩子',
      isReliable: true,
      hasPerson: false,
      activity: activity,
      observedAt: observedAt,
    );
  }
  if (hasPersonValue == true) {
    return _CameraObservationSnapshot(
      summary: '看到孩子在画面里',
      isReliable: true,
      hasPerson: true,
      activity: activity,
      observedAt: observedAt,
    );
  }
  return _CameraObservationSnapshot(
    summary: '',
    isReliable: false,
    hasPerson: null,
    activity: activity,
    observedAt: observedAt,
  );
}

bool _isFreshObservation(int? observedAt) {
  if (observedAt == null || observedAt <= 0) return false;
  final age = DateTime.now().millisecondsSinceEpoch - observedAt;
  return age >= 0 && age <= cameraObservationFreshness.inMilliseconds;
}

const _genericActivityLabels = {'其他', '未知', '无明显活动', 'other', 'unknown'};

String _normalizeActivityLabel(String activity) {
  final trimmed = activity.trim();
  if (trimmed.isEmpty) return '';
  if (_genericActivityLabels.contains(trimmed)) return '';
  if (_genericActivityLabels.contains(trimmed.toLowerCase())) return '';
  return trimmed;
}

String _sanitizeObservationText(String text) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return '';
  if (_weakPresenceObservationTexts.contains(trimmed)) return '';
  for (final generic in _genericActivityLabels) {
    if (trimmed.endsWith('：$generic') || trimmed.endsWith(': $generic')) {
      return '';
    }
  }
  if (trimmed.startsWith('画面记录到孩子正在进行：')) {
    final activity = trimmed.replaceFirst('画面记录到孩子正在进行：', '');
    final normalized = _normalizeActivityLabel(activity);
    if (normalized.isEmpty) return '';
    return '看到孩子在$normalized。';
  }
  return trimmed;
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
