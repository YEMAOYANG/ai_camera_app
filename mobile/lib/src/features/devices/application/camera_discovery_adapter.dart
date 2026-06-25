import 'dart:async';
import 'dart:io' show Platform;

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart' as reactive;
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';
import 'package:permission_handler/permission_handler.dart';

final cameraDiscoveryPermissionProbeProvider =
    Provider<CameraDiscoveryPermissionProbe>((ref) {
      return PermissionHandlerCameraDiscoveryPermissionProbe();
    });

final cameraDiscoveryConfigProvider = Provider<CameraDiscoveryConfig>((ref) {
  return CameraDiscoveryConfig.fromEnvironment(
    ref.watch(appEnvironmentProvider),
  );
});

final reactiveBleClientProvider = Provider<ReactiveBleClient>((ref) {
  return FlutterReactiveBleClient(reactive.FlutterReactiveBle());
});

final cameraDiscoveryAdapterProvider = Provider<CameraDiscoveryAdapter>((ref) {
  final permissionProbe = ref.watch(cameraDiscoveryPermissionProbeProvider);
  final mockAdapter = MockCameraDiscoveryAdapter(
    deviceRepository: ref.watch(deviceRepositoryProvider),
    cameraRepository: ref.watch(cameraRepositoryProvider),
    permissionProbe: permissionProbe,
  );
  final bleAdapter = BleCameraDiscoveryAdapter(
    permissionProbe: permissionProbe,
    bleClient: ref.watch(reactiveBleClientProvider),
    scanConfig: CameraBleScanConfig.fromEnvironment(),
  );
  return CameraDiscoveryAdapterFactory(
    mockAdapter: mockAdapter,
    bleAdapter: bleAdapter,
  ).create(ref.watch(cameraDiscoveryConfigProvider));
});

class CameraDiscoveryConfig {
  const CameraDiscoveryConfig({
    required this.backend,
    required this.allowBleFallbackToMock,
  });

  factory CameraDiscoveryConfig.fromEnvironment(AppEnvironment environment) {
    const backendName = String.fromEnvironment(
      'CAMERA_DISCOVERY_BACKEND',
      // defaultValue: 'mock',
      defaultValue: 'ble',
    );
    final backend = CameraDiscoveryBackend.fromName(backendName);
    return CameraDiscoveryConfig(
      backend: backend,
      allowBleFallbackToMock: false,
    );
  }

  final CameraDiscoveryBackend backend;
  final bool allowBleFallbackToMock;
}

class CameraDiscoveryAdapterFactory {
  const CameraDiscoveryAdapterFactory({
    required this.mockAdapter,
    required this.bleAdapter,
  });

  final CameraDiscoveryAdapter mockAdapter;
  final CameraDiscoveryAdapter bleAdapter;

  CameraDiscoveryAdapter create(CameraDiscoveryConfig config) {
    return switch (config.backend) {
      CameraDiscoveryBackend.mock => mockAdapter,
      CameraDiscoveryBackend.ble => bleAdapter,
    };
  }
}

class CameraBleScanConfig {
  const CameraBleScanConfig({
    required this.serviceUuids,
    required this.namePrefixes,
    required this.manufacturerId,
    required this.scanTimeout,
  });

  factory CameraBleScanConfig.fromEnvironment() {
    const serviceUuidText = String.fromEnvironment(
      'CAMERA_BLE_SERVICE_UUIDS',
      defaultValue: '',
    );
    const namePrefixText = String.fromEnvironment(
      'CAMERA_BLE_NAME_PREFIXES',
      defaultValue: '',
    );
    const manufacturerIdText = String.fromEnvironment(
      'CAMERA_BLE_MANUFACTURER_ID',
      defaultValue: '',
    );
    const timeoutSeconds = int.fromEnvironment(
      'CAMERA_BLE_SCAN_TIMEOUT_SECONDS',
      defaultValue: 12,
    );
    return CameraBleScanConfig(
      serviceUuids: _splitConfigList(serviceUuidText),
      namePrefixes: _splitConfigList(namePrefixText),
      manufacturerId: _parseManufacturerId(manufacturerIdText),
      scanTimeout: Duration(seconds: timeoutSeconds.clamp(4, 30)),
    );
  }

  final List<String> serviceUuids;
  final List<String> namePrefixes;
  final int? manufacturerId;
  final Duration scanTimeout;

  bool get hasMatchCriteria =>
      serviceUuids.isNotEmpty ||
      namePrefixes.isNotEmpty ||
      manufacturerId != null;

  List<reactive.Uuid> get reactiveServiceUuids {
    final parsed = <reactive.Uuid>[];
    for (final value in serviceUuids) {
      try {
        parsed.add(reactive.Uuid.parse(value));
      } catch (_) {
        // Invalid build-time UUIDs are ignored so discovery can fail safely
        // with "not found" instead of crashing the connection sheet.
      }
    }
    return parsed;
  }
}

List<String> _splitConfigList(String text) {
  return text
      .split(RegExp(r'[,;\s]+'))
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

int? _parseManufacturerId(String raw) {
  final value = raw.trim();
  if (value.isEmpty) return null;
  final hasHexPrefix = value.toLowerCase().startsWith('0x');
  final normalized = hasHexPrefix ? value.substring(2) : value;
  return int.tryParse(
    normalized,
    radix: hasHexPrefix || RegExp(r'[a-fA-F]').hasMatch(normalized) ? 16 : 10,
  );
}

abstract class ReactiveBleClient {
  reactive.BleStatus get status;

  Stream<reactive.BleStatus> get statusStream;

  Stream<reactive.DiscoveredDevice> scanForDevices({
    required List<reactive.Uuid> withServices,
    required reactive.ScanMode scanMode,
    required bool requireLocationServicesEnabled,
  });
}

class FlutterReactiveBleClient implements ReactiveBleClient {
  const FlutterReactiveBleClient(this._ble);

  final reactive.FlutterReactiveBle _ble;

  @override
  reactive.BleStatus get status => _ble.status;

  @override
  Stream<reactive.BleStatus> get statusStream => _ble.statusStream;

  @override
  Stream<reactive.DiscoveredDevice> scanForDevices({
    required List<reactive.Uuid> withServices,
    required reactive.ScanMode scanMode,
    required bool requireLocationServicesEnabled,
  }) {
    return _ble.scanForDevices(
      withServices: withServices,
      scanMode: scanMode,
      requireLocationServicesEnabled: requireLocationServicesEnabled,
    );
  }
}

abstract class CameraDiscoveryPermissionProbe {
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus();

  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions();

  Future<bool> isBluetoothAvailable();

  Future<void> openSystemSettings();

  Future<void> openBluetoothSettings();
}

const _systemSettingsChannel = MethodChannel('ai_camera_app/system_settings');

/// Permission probing boundary for the future BLE adapter.
///
/// The current discovery adapter remains development-backed, but permission
/// status is already queried through the same contract the real BLE adapter will
/// use. Local-network permission is represented in the model, but iOS exposes it
/// only when a Bonjour/hotspot/local connection is attempted, so the real
/// hardware stage should provide a stronger probe at that point.
class PermissionHandlerCameraDiscoveryPermissionProbe
    implements CameraDiscoveryPermissionProbe {
  PermissionHandlerCameraDiscoveryPermissionProbe({
    DeviceInfoPlugin? deviceInfo,
  }) : _deviceInfo = deviceInfo ?? DeviceInfoPlugin();

  final DeviceInfoPlugin _deviceInfo;

  @override
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus() async {
    if (!Platform.isAndroid && !Platform.isIOS) {
      return CameraDiscoveryPermissionStatus.ready;
    }
    final bluetoothAvailable = await isBluetoothAvailable();
    if (!bluetoothAvailable) {
      return CameraDiscoveryPermissionStatus.bluetoothOff;
    }
    if (Platform.isAndroid) return _androidPermissionStatus(request: false);
    return _iosPermissionStatus(request: false);
  }

  @override
  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions() async {
    if (!Platform.isAndroid && !Platform.isIOS) {
      return CameraDiscoveryPermissionStatus.ready;
    }
    if (Platform.isAndroid) return _androidPermissionStatus(request: true);
    return _iosPermissionStatus(request: true);
  }

  @override
  Future<bool> isBluetoothAvailable() async {
    if (!Platform.isAndroid && !Platform.isIOS) return true;
    final status = await Permission.bluetooth.serviceStatus;
    return status != ServiceStatus.disabled;
  }

  @override
  Future<void> openSystemSettings() async {
    await openAppSettings();
  }

  @override
  Future<void> openBluetoothSettings() async {
    if (!Platform.isAndroid) {
      await openAppSettings();
      return;
    }
    try {
      await _systemSettingsChannel.invokeMethod<void>('openBluetoothSettings');
    } catch (_) {
      await openAppSettings();
    }
  }

  Future<CameraDiscoveryPermissionStatus> _iosPermissionStatus({
    required bool request,
  }) async {
    final status = request
        ? await Permission.bluetooth.request()
        : await Permission.bluetooth.status;
    return _mapBluetoothPermission(status);
  }

  Future<CameraDiscoveryPermissionStatus> _androidPermissionStatus({
    required bool request,
  }) async {
    final info = await _deviceInfo.androidInfo;
    final permissions = info.version.sdkInt >= 31
        ? const [Permission.bluetoothScan, Permission.bluetoothConnect]
        : const [Permission.locationWhenInUse];
    final statuses = <PermissionStatus>[];
    for (final permission in permissions) {
      statuses.add(
        request ? await permission.request() : await permission.status,
      );
    }
    if (statuses.any((status) => status.isPermanentlyDenied)) {
      return CameraDiscoveryPermissionStatus
          .bluetoothPermissionPermanentlyDenied;
    }
    if (statuses.any((status) => status.isDenied || status.isRestricted)) {
      return request
          ? CameraDiscoveryPermissionStatus.bluetoothPermissionDenied
          : CameraDiscoveryPermissionStatus.bluetoothPermissionRequired;
    }
    return CameraDiscoveryPermissionStatus.ready;
  }

  CameraDiscoveryPermissionStatus _mapBluetoothPermission(
    PermissionStatus status,
  ) {
    if (status.isPermanentlyDenied) {
      return CameraDiscoveryPermissionStatus
          .bluetoothPermissionPermanentlyDenied;
    }
    if (status.isDenied || status.isRestricted) {
      return CameraDiscoveryPermissionStatus.bluetoothPermissionRequired;
    }
    if (status.isLimited || status.isGranted || status.isProvisional) {
      return CameraDiscoveryPermissionStatus.ready;
    }
    return CameraDiscoveryPermissionStatus.unknown;
  }
}

abstract class CameraDiscoveryAdapter {
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus();

  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions();

  Future<bool> isBluetoothAvailable();

  Stream<CameraDiscoveryResult> startScan();

  Future<void> stopScan();

  Future<GuardianDevice> connectCandidate(DiscoveredCameraCandidate candidate);

  Future<CameraReadinessResult> checkReadiness(String deviceId);

  Future<void> openSystemSettings();

  Future<void> openBluetoothSettings();
}

class MockCameraDiscoveryAdapter implements CameraDiscoveryAdapter {
  MockCameraDiscoveryAdapter({
    required DeviceRepository deviceRepository,
    required CameraRepository cameraRepository,
    required CameraDiscoveryPermissionProbe permissionProbe,
    Duration scanDelay = const Duration(milliseconds: 1450),
  }) : this._(deviceRepository, cameraRepository, permissionProbe, scanDelay);

  MockCameraDiscoveryAdapter._(
    this._deviceRepository,
    this._cameraRepository,
    this._permissionProbe,
    this._scanDelay,
  );

  final DeviceRepository _deviceRepository;
  final CameraRepository _cameraRepository;
  final CameraDiscoveryPermissionProbe _permissionProbe;
  final Duration _scanDelay;
  StreamController<CameraDiscoveryResult>? _scanController;

  @override
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus() {
    return _permissionProbe.getPermissionStatus();
  }

  @override
  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions() {
    return _permissionProbe.requestRequiredPermissions();
  }

  @override
  Future<bool> isBluetoothAvailable() {
    return _permissionProbe.isBluetoothAvailable();
  }

  @override
  Stream<CameraDiscoveryResult> startScan() {
    _stopCurrentScan();
    final controller = StreamController<CameraDiscoveryResult>();
    _scanController = controller;
    unawaited(_emitDevelopmentDiscovery(controller));
    return controller.stream;
  }

  Future<void> _emitDevelopmentDiscovery(
    StreamController<CameraDiscoveryResult> controller,
  ) async {
    await Future<void>.delayed(_scanDelay);
    if (controller.isClosed) return;
    final candidates = await _deviceRepository.discoverNearbyCameraCandidates();
    if (controller.isClosed) return;
    controller.add(
      CameraDiscoveryResult(
        phase: candidates.isEmpty
            ? CameraDiscoveryPhase.notFound
            : CameraDiscoveryPhase.found,
        candidates: candidates,
        failureReason: candidates.isEmpty
            ? AddCameraFailureReason.timeout
            : null,
      ),
    );
    await controller.close();
  }

  @override
  Future<void> stopScan() async {
    await _stopCurrentScan();
  }

  Future<void> _stopCurrentScan() async {
    final controller = _scanController;
    _scanController = null;
    if (controller != null && !controller.isClosed) {
      await controller.close();
    }
  }

  @override
  Future<GuardianDevice> connectCandidate(DiscoveredCameraCandidate candidate) {
    if (!candidate.canSelect) {
      throw DeviceException(
        candidate.unavailableReason ?? '这台摄像头暂时无法连接，请重新搜索。',
        code: 'candidate_unavailable',
      );
    }
    return _deviceRepository.bindDevice(
      bindingCode: candidate.bindingCode,
      name: candidate.displayName,
      location: candidate.roomHint,
      setAsDefault: true,
    );
  }

  @override
  Future<CameraReadinessResult> checkReadiness(String deviceId) async {
    final results = await Future.wait<Object?>([
      _safeCameraProbe(_cameraRepository.health(deviceId: deviceId)),
      _safeCameraProbe(_cameraRepository.status(deviceId: deviceId)),
      _safeCameraProbe(_cameraRepository.snapshot(deviceId: deviceId)),
    ]);
    final health = results[0];
    final status = results[1];
    final snapshot = results[2];
    final healthReady = health is CameraHealth && health.reachable;
    final statusReady =
        status is CameraStatus &&
        (status.isOnline || status.streamAvailable || status.snapshotAvailable);
    final snapshotReady = snapshot is CameraSnapshotFrame && snapshot.available;
    final ready = healthReady && (statusReady || snapshotReady);
    return CameraReadinessResult(
      livePreviewAvailable: ready,
      message: ready ? '实时看护已准备好' : '实时画面暂时不可用',
    );
  }

  Future<Object?> _safeCameraProbe<T>(Future<T> future) async {
    try {
      return await future;
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> openSystemSettings() {
    return _permissionProbe.openSystemSettings();
  }

  @override
  Future<void> openBluetoothSettings() {
    return _permissionProbe.openBluetoothSettings();
  }
}

class BleCameraDiscoveryAdapter implements CameraDiscoveryAdapter {
  BleCameraDiscoveryAdapter({
    required CameraDiscoveryPermissionProbe permissionProbe,
    required ReactiveBleClient bleClient,
    required CameraBleScanConfig scanConfig,
    bool? isSupportedPlatform,
  }) : this._(
         permissionProbe,
         bleClient,
         scanConfig,
         isSupportedPlatform ?? (Platform.isAndroid || Platform.isIOS),
       );

  BleCameraDiscoveryAdapter._(
    this._permissionProbe,
    this._bleClient,
    this._scanConfig,
    this._isSupportedPlatform,
  );

  final CameraDiscoveryPermissionProbe _permissionProbe;
  final ReactiveBleClient _bleClient;
  final CameraBleScanConfig _scanConfig;
  final bool _isSupportedPlatform;
  StreamController<CameraDiscoveryResult>? _scanController;
  StreamSubscription<reactive.DiscoveredDevice>? _bleScanSubscription;
  Timer? _scanTimeoutTimer;
  final _discoveredCandidates = <String, DiscoveredCameraCandidate>{};

  @override
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus() async {
    if (!_isSupportedPlatform) {
      return CameraDiscoveryPermissionStatus.unsupported;
    }
    final permission = await _permissionProbe.getPermissionStatus();
    if (!permission.canStartDiscovery) return permission;
    return _permissionStatusFromBleStatus(
      _bleClient.status,
      fallbackReady: true,
    );
  }

  @override
  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions() async {
    if (!_isSupportedPlatform) {
      return CameraDiscoveryPermissionStatus.unsupported;
    }
    final permission = await _permissionProbe.requestRequiredPermissions();
    if (!permission.canStartDiscovery) return permission;
    return _permissionStatusFromBleStatus(
      _bleClient.status,
      fallbackReady: true,
    );
  }

  @override
  Future<bool> isBluetoothAvailable() async {
    if (!_isSupportedPlatform) return false;
    final status = _permissionStatusFromBleStatus(
      _bleClient.status,
      fallbackReady: true,
    );
    if (status == CameraDiscoveryPermissionStatus.bluetoothOff ||
        status == CameraDiscoveryPermissionStatus.unsupported) {
      return false;
    }
    return _permissionProbe.isBluetoothAvailable();
  }

  @override
  Stream<CameraDiscoveryResult> startScan() {
    _stopActiveScan();
    final controller = StreamController<CameraDiscoveryResult>();
    _scanController = controller;
    _discoveredCandidates.clear();
    unawaited(_startBleScan(controller));
    return controller.stream;
  }

  Future<void> _startBleScan(
    StreamController<CameraDiscoveryResult> controller,
  ) async {
    if (!_isSupportedPlatform) {
      await _emitAndClose(
        controller,
        const CameraDiscoveryResult(
          phase: CameraDiscoveryPhase.connectionFailed,
          candidates: [],
          failureReason: AddCameraFailureReason.unsupported,
        ),
      );
      return;
    }
    final status = _permissionStatusFromBleStatus(
      _bleClient.status,
      fallbackReady: true,
    );
    if (!status.canStartDiscovery) {
      await _emitAndClose(
        controller,
        CameraDiscoveryResult(
          phase: status == CameraDiscoveryPermissionStatus.bluetoothOff
              ? CameraDiscoveryPhase.bluetoothOff
              : CameraDiscoveryPhase.permissionRequired,
          candidates: const [],
          failureReason: _failureReasonForStatus(status),
        ),
      );
      return;
    }

    _scanTimeoutTimer = Timer(_scanConfig.scanTimeout, () {
      if (controller.isClosed) return;
      controller.add(
        const CameraDiscoveryResult(
          phase: CameraDiscoveryPhase.notFound,
          candidates: [],
          failureReason: AddCameraFailureReason.timeout,
        ),
      );
      unawaited(stopScan());
    });

    if (!_scanConfig.hasMatchCriteria) {
      return;
    }

    _bleScanSubscription = _bleClient
        .scanForDevices(
          withServices: _scanConfig.reactiveServiceUuids,
          scanMode: reactive.ScanMode.lowLatency,
          requireLocationServicesEnabled: false,
        )
        .listen(
          (device) {
            if (controller.isClosed || !_matchesCameraDevice(device)) return;
            final candidate = _candidateFromBleDevice(device);
            _discoveredCandidates[candidate.id] = candidate;
            controller.add(
              CameraDiscoveryResult(
                phase: CameraDiscoveryPhase.found,
                candidates: _sortedBleCandidates(),
              ),
            );
          },
          onError: (_) {
            if (controller.isClosed) return;
            controller.add(
              const CameraDiscoveryResult(
                phase: CameraDiscoveryPhase.notFound,
                candidates: [],
                failureReason: AddCameraFailureReason.timeout,
              ),
            );
            unawaited(stopScan());
          },
        );
  }

  Future<void> _emitAndClose(
    StreamController<CameraDiscoveryResult> controller,
    CameraDiscoveryResult result,
  ) async {
    if (!controller.isClosed) controller.add(result);
    if (!controller.isClosed) await controller.close();
  }

  CameraDiscoveryPermissionStatus _permissionStatusFromBleStatus(
    reactive.BleStatus status, {
    required bool fallbackReady,
  }) {
    return switch (status) {
      reactive.BleStatus.ready => CameraDiscoveryPermissionStatus.ready,
      reactive.BleStatus.poweredOff =>
        CameraDiscoveryPermissionStatus.bluetoothOff,
      reactive.BleStatus.unauthorized =>
        CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied,
      reactive.BleStatus.unsupported =>
        CameraDiscoveryPermissionStatus.unsupported,
      reactive.BleStatus.locationServicesDisabled =>
        CameraDiscoveryPermissionStatus.bluetoothPermissionRequired,
      reactive.BleStatus.unknown =>
        fallbackReady
            ? CameraDiscoveryPermissionStatus.ready
            : CameraDiscoveryPermissionStatus.unknown,
    };
  }

  AddCameraFailureReason _failureReasonForStatus(
    CameraDiscoveryPermissionStatus status,
  ) {
    return switch (status) {
      CameraDiscoveryPermissionStatus.bluetoothOff =>
        AddCameraFailureReason.bluetoothUnavailable,
      CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied =>
        AddCameraFailureReason.permissionPermanentlyDenied,
      CameraDiscoveryPermissionStatus.unsupported =>
        AddCameraFailureReason.unsupported,
      _ => AddCameraFailureReason.permissionDenied,
    };
  }

  bool _matchesCameraDevice(reactive.DiscoveredDevice device) {
    if (!_scanConfig.hasMatchCriteria) return false;
    final serviceMatch =
        _scanConfig.serviceUuids.isNotEmpty &&
        device.serviceUuids.any(
          (uuid) => _scanConfig.serviceUuids.any(
            (expected) => _uuidEquals(uuid.toString(), expected),
          ),
        );
    final normalizedName = device.name.trim().toLowerCase();
    final nameMatch =
        _scanConfig.namePrefixes.isNotEmpty &&
        normalizedName.isNotEmpty &&
        _scanConfig.namePrefixes.any(
          (prefix) => normalizedName.startsWith(prefix.toLowerCase()),
        );
    final manufacturerMatch =
        _scanConfig.manufacturerId != null &&
        _manufacturerIdMatches(
          device.manufacturerData,
          _scanConfig.manufacturerId!,
        );
    return serviceMatch || nameMatch || manufacturerMatch;
  }

  bool _uuidEquals(String actual, String expected) {
    try {
      return reactive.Uuid.parse(actual) == reactive.Uuid.parse(expected);
    } catch (_) {
      return actual.toLowerCase() == expected.toLowerCase();
    }
  }

  bool _manufacturerIdMatches(Uint8List data, int expected) {
    if (data.length < 2) return false;
    final littleEndian = data[0] | (data[1] << 8);
    final bigEndian = (data[0] << 8) | data[1];
    return littleEndian == expected || bigEndian == expected;
  }

  DiscoveredCameraCandidate _candidateFromBleDevice(
    reactive.DiscoveredDevice device,
  ) {
    return DiscoveredCameraCandidate(
      id: 'ble_${device.id}',
      displayName: '暖瞳摄像头',
      bindingCode: 'ble:${device.id}',
      signalStrength: _signalStrengthFromRssi(device.rssi),
      status: 'ready',
      source: CameraDiscoveryCandidateSource.ble,
      isConnectable: device.connectable != reactive.Connectable.unavailable,
      unavailableReason: device.connectable == reactive.Connectable.unavailable
          ? '这台摄像头暂时无法连接，请重新搜索。'
          : null,
    );
  }

  int _signalStrengthFromRssi(int rssi) {
    return (((rssi + 95) / 55) * 100).round().clamp(1, 100);
  }

  List<DiscoveredCameraCandidate> _sortedBleCandidates() {
    final candidates = _discoveredCandidates.values.toList()
      ..sort((a, b) => b.signalStrength.compareTo(a.signalStrength));
    return candidates;
  }

  @override
  Future<void> stopScan() async {
    await _stopActiveScan();
  }

  Future<void> _stopActiveScan() async {
    _scanTimeoutTimer?.cancel();
    _scanTimeoutTimer = null;
    final subscription = _bleScanSubscription;
    _bleScanSubscription = null;
    final controller = _scanController;
    _scanController = null;
    await subscription?.cancel();
    if (controller != null && !controller.isClosed) {
      await controller.close();
    }
  }

  @override
  Future<GuardianDevice> connectCandidate(
    DiscoveredCameraCandidate candidate,
  ) async {
    throw const DeviceException(
      '暂时无法完成连接，设备协议还未接入。',
      code: 'ble_protocol_unavailable',
    );
  }

  @override
  Future<CameraReadinessResult> checkReadiness(String deviceId) async {
    return const CameraReadinessResult(
      livePreviewAvailable: false,
      message: '实时画面暂时不可用',
    );
  }

  @override
  Future<void> openSystemSettings() {
    return _permissionProbe.openSystemSettings();
  }

  @override
  Future<void> openBluetoothSettings() {
    return _permissionProbe.openBluetoothSettings();
  }
}
