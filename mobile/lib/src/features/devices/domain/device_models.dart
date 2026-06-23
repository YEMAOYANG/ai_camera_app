import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

enum CameraDiscoveryPhase {
  preparing,
  permissionRequired,
  bluetoothOff,
  searching,
  found,
  connecting,
  connected,
  connectedWithoutLivePreview,
  notFound,
  connectionFailed,
  alreadyBoundToAnotherFamily,
  networkSetupFailed,
  cancelled,
}

enum AddCameraFailureReason {
  permissionDenied,
  permissionPermanentlyDenied,
  bluetoothUnavailable,
  timeout,
  connectionLost,
  alreadyBound,
  networkSetupFailed,
  localNetworkPermissionDenied,
  livePreviewUnavailable,
  unsupported,
  unknown,
}

enum CameraDiscoveryPermissionStatus {
  unknown,
  ready,
  bluetoothPermissionRequired,
  bluetoothPermissionDenied,
  bluetoothPermissionPermanentlyDenied,
  bluetoothOff,
  localNetworkPermissionRequired,
  localNetworkPermissionDenied,
  unsupported,
}

enum CameraDiscoveryPermissionIssue {
  bluetoothPermission,
  bluetoothPower,
  localNetwork,
  nearbyDevices,
  locationForLegacyAndroid,
  unsupportedDevice,
}

extension CameraDiscoveryPermissionStatusX on CameraDiscoveryPermissionStatus {
  bool get canStartDiscovery => this == CameraDiscoveryPermissionStatus.ready;

  bool get requiresUserPermission {
    return switch (this) {
      CameraDiscoveryPermissionStatus.bluetoothPermissionRequired ||
      CameraDiscoveryPermissionStatus.bluetoothPermissionDenied ||
      CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied ||
      CameraDiscoveryPermissionStatus.localNetworkPermissionRequired ||
      CameraDiscoveryPermissionStatus.localNetworkPermissionDenied => true,
      _ => false,
    };
  }

  bool get isPermanentlyDenied {
    return this ==
        CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied;
  }

  CameraDiscoveryPermissionIssue? get issue {
    return switch (this) {
      CameraDiscoveryPermissionStatus.bluetoothPermissionRequired ||
      CameraDiscoveryPermissionStatus.bluetoothPermissionDenied ||
      CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied =>
        CameraDiscoveryPermissionIssue.bluetoothPermission,
      CameraDiscoveryPermissionStatus.bluetoothOff =>
        CameraDiscoveryPermissionIssue.bluetoothPower,
      CameraDiscoveryPermissionStatus.localNetworkPermissionRequired ||
      CameraDiscoveryPermissionStatus.localNetworkPermissionDenied =>
        CameraDiscoveryPermissionIssue.localNetwork,
      CameraDiscoveryPermissionStatus.unsupported =>
        CameraDiscoveryPermissionIssue.unsupportedDevice,
      _ => null,
    };
  }
}

class CameraDiscoveryResult {
  const CameraDiscoveryResult({
    required this.phase,
    required this.candidates,
    this.failureReason,
  });

  final CameraDiscoveryPhase phase;
  final List<DiscoveredCameraCandidate> candidates;
  final AddCameraFailureReason? failureReason;
}

class CameraReadinessResult {
  const CameraReadinessResult({
    required this.livePreviewAvailable,
    required this.message,
  });

  final bool livePreviewAvailable;
  final String message;
}

class DiscoveredCameraCandidate {
  const DiscoveredCameraCandidate({
    required this.id,
    required this.displayName,
    required this.bindingCode,
    required this.signalStrength,
    required this.status,
    this.roomHint,
    this.isConnectable = true,
    this.unavailableReason,
  });

  final String id;
  final String displayName;
  final String bindingCode;
  final int signalStrength;
  final String status;
  final String? roomHint;
  final bool isConnectable;
  final String? unavailableReason;

  int get signalBars => (signalStrength / 25).ceil().clamp(1, 4);

  String get signalLabel {
    if (signalStrength >= 80) return '信号很好';
    if (signalStrength >= 58) return '信号良好';
    return '信号一般';
  }
}

class GuardianDevice {
  const GuardianDevice({
    required this.id,
    required this.familyId,
    required this.bindingCode,
    required this.name,
    required this.wakeName,
    required this.location,
    required this.status,
    required this.isDefault,
    required this.createdAt,
    required this.updatedAt,
    this.unboundAt,
  });

  final String id;
  final String familyId;
  final String bindingCode;
  final String name;
  final String wakeName;
  final String location;
  final String status;
  final bool isDefault;
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
      wakeName: _asString(json['wakeName']),
      location: _asString(json['location']),
      status: _asString(json['status']),
      isDefault: json['isDefault'] == true,
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
      if (current.monitorSupported) '看护记录',
    ];
    if (parts.isEmpty) return '基础状态可查看';
    return parts.join(' / ');
  }
}

class DeviceFirmwareStatus {
  const DeviceFirmwareStatus({
    required this.device,
    required this.currentVersion,
    required this.updateAvailable,
    required this.execution,
    this.latestPackage,
    this.lastJob,
  });

  final GuardianDevice device;
  final String currentVersion;
  final bool updateAvailable;
  final String execution;
  final FirmwarePackage? latestPackage;
  final FirmwareJob? lastJob;

  String get statusLabel {
    if (lastJob != null) return lastJob!.statusLabel;
    if (updateAvailable) return '有可用固件';
    if (execution == 'not_configured') return '暂无升级任务';
    return '已是最新';
  }

  StatusTone get tone {
    if (lastJob != null) return lastJob!.tone;
    return updateAvailable ? StatusTone.warning : StatusTone.success;
  }

  String get versionLine {
    final current = currentVersion.isNotEmpty ? currentVersion : '待同步';
    if (latestPackage != null && updateAvailable) {
      return '当前 $current · 可升级到 ${latestPackage!.version}';
    }
    return '当前 $current';
  }

  static DeviceFirmwareStatus fromJson(Map<String, dynamic> json) {
    final firmware = _asMap(json['firmware']);
    final latestPackage = _asMap(firmware['latestPackage']);
    final lastJob = _asMap(firmware['lastJob']);
    return DeviceFirmwareStatus(
      device: GuardianDevice.fromJson(_asMap(json['device'])),
      currentVersion: _asString(firmware['currentVersion']),
      updateAvailable: firmware['updateAvailable'] == true,
      execution: _asString(firmware['execution']).isNotEmpty
          ? _asString(firmware['execution'])
          : 'not_configured',
      latestPackage: latestPackage.isEmpty
          ? null
          : FirmwarePackage.fromJson(latestPackage),
      lastJob: lastJob.isEmpty ? null : FirmwareJob.fromJson(lastJob),
    );
  }
}

class FirmwarePackage {
  const FirmwarePackage({
    required this.id,
    required this.version,
    required this.channel,
    required this.status,
    required this.notes,
    required this.createdAt,
  });

  final String id;
  final String version;
  final String channel;
  final String status;
  final String notes;
  final int createdAt;

  static FirmwarePackage fromJson(Map<String, dynamic> json) {
    return FirmwarePackage(
      id: _asString(json['id']),
      version: _asString(json['version']),
      channel: _asString(json['channel']),
      status: _asString(json['status']),
      notes: _asString(json['notes']),
      createdAt: _asInt(json['createdAt']),
    );
  }
}

class FirmwareJob {
  const FirmwareJob({
    required this.id,
    required this.deviceId,
    required this.packageId,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String deviceId;
  final String packageId;
  final String status;
  final int createdAt;
  final int updatedAt;

  String get statusLabel {
    return switch (status) {
      'scheduled' => '等待设备升级',
      'running' => '升级中',
      'succeeded' => '升级完成',
      'failed' => '升级失败',
      _ => status.isNotEmpty ? status : '升级任务',
    };
  }

  StatusTone get tone {
    return switch (status) {
      'succeeded' => StatusTone.success,
      'failed' => StatusTone.danger,
      'running' || 'scheduled' => StatusTone.warning,
      _ => StatusTone.neutral,
    };
  }

  static FirmwareJob fromJson(Map<String, dynamic> json) {
    return FirmwareJob(
      id: _asString(json['id']),
      deviceId: _asString(json['deviceId']),
      packageId: _asString(json['packageId']),
      status: _asString(json['status']),
      createdAt: _asInt(json['createdAt']),
      updatedAt: _asInt(json['updatedAt']),
    );
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
