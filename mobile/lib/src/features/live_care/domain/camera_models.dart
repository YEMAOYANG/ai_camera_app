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
      serviceLabel: _asString(data['service'], fallback: 'camera runtime'),
      message: reachable
          ? '摄像头服务在线'
          : error.isNotEmpty
          ? error
          : '摄像头运行服务暂时不可用',
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
    if (!reachable) return '运行状态不可用';
    if (voiceRunning) return '语音观察运行中';
    return switch (voiceState) {
      'idle' => '安静观察中',
      'running' => '观察处理中',
      'paused' => '已暂停',
      _ => voiceState.isNotEmpty ? voiceState : '基础看护在线',
    };
  }

  String get summary {
    if (!reachable) return message;
    if (voiceRunning) return '设备正在处理语音/看护运行状态，家长可稍后刷新查看。';
    return '设备运行正常，基础看护状态已同步。';
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
          ? '运行状态已同步'
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
    message: '真实快照暂不可用',
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
      _ => '状态同步中',
    };
  }

  String get summary {
    if (message.isNotEmpty) return message;
    return isOnline ? '摄像头在线，最新状态已同步。' : '摄像头暂时离线，任务仍会按计划记录。';
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
  });

  final bool running;
  final String status;
  final String message;
  final String lastObservation;
  final String lastReminder;

  String get label => running ? '观察中' : '未观察';

  StatusTone get tone => running ? StatusTone.success : StatusTone.neutral;

  static CameraMonitorStatus fromJson(Map<String, dynamic> json) {
    final monitor = _asMap(json['monitor']);
    return CameraMonitorStatus(
      running: monitor['running'] == true,
      status: _asString(monitor['status'], fallback: 'idle'),
      message: _asString(monitor['message']),
      lastObservation: _observationSummary(monitor['lastObservation']),
      lastReminder: _asString(monitor['lastReminder']),
    );
  }
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
    return isAvailable ? '实时看护状态正常。' : '实时画面暂时不可用。';
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
    required this.status,
    required this.toneKey,
    required this.createdAt,
  });

  final String id;
  final String source;
  final String eventType;
  final String title;
  final String message;
  final String status;
  final String toneKey;
  final int createdAt;

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

String _observationSummary(dynamic value) {
  if (value is String && value.isNotEmpty) return value;
  final data = _asMap(value);
  if (data.isEmpty) return '';
  final activity = _asString(data['activity']);
  final hasPerson = data['has_person'] == true;
  if (activity.isNotEmpty && hasPerson) return '画面记录到孩子正在进行：$activity';
  if (activity.isNotEmpty) return '画面记录到：$activity';
  if (hasPerson) return '画面记录到孩子在看护区域内。';
  return '';
}

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
