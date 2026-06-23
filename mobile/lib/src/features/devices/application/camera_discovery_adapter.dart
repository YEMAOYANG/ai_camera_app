import 'dart:async';
import 'dart:io' show Platform;

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';
import 'package:permission_handler/permission_handler.dart';

final cameraDiscoveryPermissionProbeProvider =
    Provider<CameraDiscoveryPermissionProbe>((ref) {
      return PermissionHandlerCameraDiscoveryPermissionProbe();
    });

final cameraDiscoveryAdapterProvider = Provider<CameraDiscoveryAdapter>((ref) {
  return MockCameraDiscoveryAdapter(
    deviceRepository: ref.watch(deviceRepositoryProvider),
    cameraRepository: ref.watch(cameraRepositoryProvider),
    permissionProbe: ref.watch(cameraDiscoveryPermissionProbeProvider),
  );
});

abstract class CameraDiscoveryPermissionProbe {
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus();

  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions();

  Future<bool> isBluetoothAvailable();

  Future<void> openSystemSettings();
}

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
    unawaited(stopScan());
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
    final controller = _scanController;
    _scanController = null;
    if (controller != null && !controller.isClosed) {
      await controller.close();
    }
  }

  @override
  Future<GuardianDevice> connectCandidate(DiscoveredCameraCandidate candidate) {
    if (!candidate.isConnectable) {
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
}
