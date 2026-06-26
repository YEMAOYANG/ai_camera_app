import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/features/devices/application/camera_discovery_adapter.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';

final cameraDiscoveryRepositoryProvider = Provider<CameraDiscoveryRepository>((
  ref,
) {
  return CameraDiscoveryRepository(
    adapter: ref.watch(cameraDiscoveryAdapterProvider),
    deviceRepository: ref.watch(deviceRepositoryProvider),
  );
});

/// Boundary for nearby-camera discovery.
///
/// V1 still uses a development discovery adapter. Future BLE discovery and
/// provisioning should replace the adapter behind this repository without
/// moving connection-state logic back into the widget tree.
class CameraDiscoveryRepository {
  factory CameraDiscoveryRepository({
    required CameraDiscoveryAdapter adapter,
    DeviceRepository? deviceRepository,
  }) {
    return CameraDiscoveryRepository._(adapter, deviceRepository);
  }

  const CameraDiscoveryRepository._(this._adapter, this._deviceRepository);

  final CameraDiscoveryAdapter _adapter;
  final DeviceRepository? _deviceRepository;

  Future<CameraDiscoveryPermissionStatus> getPermissionStatus() {
    return _adapter.getPermissionStatus();
  }

  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions() {
    return _adapter.requestRequiredPermissions();
  }

  Future<bool> isBluetoothAvailable() {
    return _adapter.isBluetoothAvailable();
  }

  Stream<CameraDiscoveryResult> startScan() {
    return _adapter.startScan().asyncMap((result) async {
      if (result.candidates.isEmpty ||
          result.phase != CameraDiscoveryPhase.found) {
        return result;
      }
      final deviceRepository = _deviceRepository;
      if (deviceRepository == null) return result;
      final candidates = await deviceRepository.discoveryStatuses(
        result.candidates,
      );
      return CameraDiscoveryResult(
        phase: result.phase,
        candidates: candidates,
        failureReason: result.failureReason,
      );
    });
  }

  Future<void> stopScan() {
    return _adapter.stopScan();
  }

  Future<GuardianDevice> connectDiscoveredCamera(
    DiscoveredCameraCandidate candidate,
  ) {
    return _adapter.connectCandidate(candidate);
  }

  Future<CameraReadinessResult> checkCameraReadiness(String deviceId) {
    return _adapter.checkReadiness(deviceId);
  }

  Future<void> openSystemSettings() {
    return _adapter.openSystemSettings();
  }

  Future<void> openBluetoothSettings() {
    return _adapter.openBluetoothSettings();
  }
}
