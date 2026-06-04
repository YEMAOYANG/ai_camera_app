import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/network/api_client.dart';
import 'package:mira_guardian_app/src/features/devices/domain/device_models.dart';

final deviceRepositoryProvider = Provider<DeviceRepository>((ref) {
  return DeviceRepository(
    environment: ref.watch(appEnvironmentProvider),
    apiClient: ref.watch(apiClientProvider),
  );
});

final devicesProvider = FutureProvider<List<GuardianDevice>>((ref) {
  return ref.watch(deviceRepositoryProvider).devices();
});

final primaryDeviceOverviewProvider = FutureProvider<DeviceOverview?>((ref) {
  return ref.watch(deviceRepositoryProvider).primaryOverview();
});

final deviceOverviewProvider = FutureProvider.family<DeviceOverview, String>((
  ref,
  deviceId,
) {
  return ref.watch(deviceRepositoryProvider).overview(deviceId);
});

class DeviceRepository {
  const DeviceRepository({
    required AppEnvironment environment,
    required ApiClient apiClient,
  }) : _environment = environment,
       _apiClient = apiClient;

  final AppEnvironment _environment;
  final ApiClient _apiClient;

  Future<List<GuardianDevice>> devices() async {
    if (_environment.useMockData) return _mockDevices;

    try {
      final response = await _apiClient.get('/devices');
      final raw = _asMap(response.data)['devices'];
      if (raw is! List) return const [];
      return raw
          .map((device) => GuardianDevice.fromJson(_asMap(device)))
          .toList();
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<DeviceOverview?> primaryOverview() async {
    final list = await devices();
    if (list.isEmpty) return null;
    return overview(list.first.id, fallback: list.first);
  }

  Future<DeviceOverview> overview(
    String deviceId, {
    GuardianDevice? fallback,
  }) async {
    if (_environment.useMockData) {
      final device = fallback ?? _mockDevices.first;
      return DeviceOverview(device: device, status: _mockDeviceStatus);
    }

    try {
      final response = await _apiClient.get('/devices/$deviceId/status');
      final map = _asMap(response.data);
      return DeviceOverview(
        device: GuardianDevice.fromJson(_asMap(map['device'])),
        status: GuardianDeviceStatus.fromJson(_asMap(map['status'])),
      );
    } on DioException catch (error) {
      if (fallback != null) {
        return DeviceOverview(device: fallback, status: null);
      }
      throw _fromDio(error);
    }
  }

  DeviceException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return DeviceException(
          message,
          code: code is String ? code : 'device_error',
        );
      }
    }
    return const DeviceException('设备状态暂时不可用，请稍后重试。', code: 'network_error');
  }
}

final _mockDevices = [
  GuardianDevice(
    id: 'mock_device_living_room',
    familyId: 'mock_family',
    bindingCode: 'MIRA-MOCK-DISCOVERY',
    name: '客厅米拉',
    location: '客厅书桌区',
    status: 'bound',
    createdAt: DateTime.now().millisecondsSinceEpoch,
    updatedAt: DateTime.now().millisecondsSinceEpoch,
  ),
];

const _mockDeviceStatus = GuardianDeviceStatus(
  deviceId: 'mock_device_living_room',
  connectionStatus: 'online',
  privacyMode: false,
  firmwareVersion: '0.1.0-dev',
  networkType: 'wifi',
  networkQuality: 'good',
  snapshotSupported: true,
  streamSupported: true,
  twoWayAudioSupported: false,
  monitorSupported: true,
  otaSupported: false,
  adapter: 'mock_hardware_device',
  lastSeenAt: null,
  message: '设备在线，状态已同步。',
);

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
