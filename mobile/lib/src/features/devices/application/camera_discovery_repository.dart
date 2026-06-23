import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/features/devices/application/camera_discovery_adapter.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';

final cameraDiscoveryRepositoryProvider = Provider<CameraDiscoveryRepository>((
  ref,
) {
  return CameraDiscoveryRepository(ref.watch(cameraDiscoveryAdapterProvider));
});

/// Boundary for nearby-camera discovery.
///
/// V1 still uses a development discovery adapter. Future BLE discovery and
/// provisioning should replace the adapter behind this repository without
/// moving connection-state logic back into the widget tree.
class CameraDiscoveryRepository {
  const CameraDiscoveryRepository(this._adapter);

  final CameraDiscoveryAdapter _adapter;

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
    return _adapter.startScan();
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
}
