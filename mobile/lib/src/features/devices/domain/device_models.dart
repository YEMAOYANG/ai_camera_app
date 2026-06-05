import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class GuardianDevice {
  const GuardianDevice({
    required this.id,
    required this.familyId,
    required this.bindingCode,
    required this.name,
    required this.location,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
    this.unboundAt,
  });

  final String id;
  final String familyId;
  final String bindingCode;
  final String name;
  final String location;
  final String status;
  final int createdAt;
  final int updatedAt;
  final int? unboundAt;

  bool get isOnlineLike => status == 'bound' || status == 'online';

  String get displayName => name.isNotEmpty ? name : '家庭设备';

  String get displayLocation => location.isNotEmpty ? location : '家庭空间';

  static GuardianDevice fromJson(Map<String, dynamic> json) {
    return GuardianDevice(
      id: _asString(json['id']),
      familyId: _asString(json['familyId']),
      bindingCode: _asString(json['bindingCode']),
      name: _asString(json['name']),
      location: _asString(json['location']),
      status: _asString(json['status']),
      createdAt: _asInt(json['createdAt']),
      updatedAt: _asInt(json['updatedAt']),
      unboundAt: _asNullableInt(json['unboundAt']),
    );
  }
}

class GuardianDeviceStatus {
  const GuardianDeviceStatus({
    required this.deviceId,
    required this.connectionStatus,
    required this.privacyMode,
    required this.firmwareVersion,
    required this.networkType,
    required this.networkQuality,
    required this.snapshotSupported,
    required this.streamSupported,
    required this.twoWayAudioSupported,
    required this.monitorSupported,
    required this.otaSupported,
    required this.adapter,
    required this.lastSeenAt,
    required this.message,
  });

  final String deviceId;
  final String connectionStatus;
  final bool privacyMode;
  final String firmwareVersion;
  final String networkType;
  final String networkQuality;
  final bool snapshotSupported;
  final bool streamSupported;
  final bool twoWayAudioSupported;
  final bool monitorSupported;
  final bool otaSupported;
  final String adapter;
  final int? lastSeenAt;
  final String message;

  bool get isOnline => connectionStatus == 'online';

  String get connectionLabel {
    return switch (connectionStatus) {
      'online' => '在线',
      'connecting' => '连接中',
      'error' => '异常',
      'offline' => '离线',
      _ => connectionStatus.isNotEmpty ? connectionStatus : '未知',
    };
  }

  StatusTone get tone {
    return switch (connectionStatus) {
      'online' => StatusTone.success,
      'connecting' => StatusTone.warning,
      'error' => StatusTone.danger,
      'offline' => StatusTone.danger,
      _ => StatusTone.neutral,
    };
  }

  String get networkLabel {
    final type = switch (networkType) {
      'wifi' => 'Wi-Fi',
      'cellular' => '蜂窝网络',
      _ => networkType.isNotEmpty ? networkType : '网络',
    };
    final quality = switch (networkQuality) {
      'good' => '信号良好',
      'poor' => '信号较弱',
      'unknown' => '信号未知',
      _ => networkQuality.isNotEmpty ? networkQuality : '信号未知',
    };
    return '$type · $quality';
  }

  static GuardianDeviceStatus fromJson(Map<String, dynamic> json) {
    final network = _asMap(json['network']);
    final capabilities = _asMap(json['capabilities']);
    return GuardianDeviceStatus(
      deviceId: _asString(json['deviceId']),
      connectionStatus: _asString(json['connectionStatus']),
      privacyMode: json['privacyMode'] == true,
      firmwareVersion: _asString(json['firmwareVersion']),
      networkType: _asString(network['type']),
      networkQuality: _asString(network['quality']),
      snapshotSupported: capabilities['snapshot'] == true,
      streamSupported: capabilities['stream'] == true,
      twoWayAudioSupported: capabilities['twoWayAudio'] == true,
      monitorSupported: capabilities['monitor'] == true,
      otaSupported: capabilities['ota'] == true,
      adapter: _asString(json['adapter']),
      lastSeenAt: _asNullableInt(json['lastSeenAt']),
      message: _asString(json['message']),
    );
  }
}

class DeviceOverview {
  const DeviceOverview({required this.device, required this.status});

  final GuardianDevice device;
  final GuardianDeviceStatus? status;

  bool get isOnline => status?.isOnline ?? device.isOnlineLike;

  String get connectionLabel {
    return status?.connectionLabel ?? (device.isOnlineLike ? '在线' : '离线');
  }

  StatusTone get tone {
    return status?.tone ??
        (device.isOnlineLike ? StatusTone.success : StatusTone.danger);
  }

  String get subtitle {
    final network = status?.networkLabel;
    if (network != null && network.isNotEmpty) {
      return '${device.displayLocation} · $network';
    }
    return device.displayLocation;
  }

  String get capabilitySummary {
    final current = status;
    if (current == null) return '等待设备状态同步';
    final parts = <String>[
      if (current.snapshotSupported) '快照',
      if (current.streamSupported) '实时画面',
      if (current.twoWayAudioSupported) '双向语音',
      if (current.monitorSupported) '任务观察',
    ];
    if (parts.isEmpty) return '基础状态可查看';
    return parts.join(' / ');
  }
}

class DeviceException implements Exception {
  const DeviceException(this.message, {this.code = 'device_error'});

  final String message;
  final String code;
}

String _asString(dynamic value) {
  return value is String ? value : '';
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

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
