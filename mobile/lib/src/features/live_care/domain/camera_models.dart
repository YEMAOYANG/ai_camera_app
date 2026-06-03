import 'dart:typed_data';

import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

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

  static const mock = CameraHealth(
    ok: true,
    reachable: true,
    adapter: 'mock_camera_runtime',
    serviceLabel: 'Mira Camera Runtime',
    message: '摄像头服务在线',
  );
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

  static const mock = CameraRuntime(
    ok: true,
    reachable: true,
    adapter: 'mock_camera_runtime',
    voiceState: 'idle',
    voiceRunning: false,
    message: '运行状态已同步',
  );
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

class LiveCareStatus {
  const LiveCareStatus({required this.health, required this.runtime});

  final CameraHealth health;
  final CameraRuntime runtime;

  bool get isAvailable => health.reachable && runtime.reachable;

  StatusTone get tone => isAvailable ? StatusTone.success : StatusTone.danger;

  String get label => isAvailable ? '在线看护可用' : '看护服务降级';

  String get title {
    return isAvailable ? '实时看护状态正常。' : '实时画面暂时不可用。';
  }

  String get detail {
    return isAvailable ? runtime.summary : '我们暂时拿不到实时画面。请确认设备电源和家庭网络后再刷新。';
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
