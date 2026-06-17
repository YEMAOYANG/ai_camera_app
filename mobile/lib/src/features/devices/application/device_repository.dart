import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';

final deviceRepositoryProvider = Provider<DeviceRepository>((ref) {
  return DeviceRepository(apiClient: ref.watch(apiClientProvider));
});

final devicesProvider = FutureProvider<List<GuardianDevice>>((ref) {
  return ref.watch(deviceRepositoryProvider).devices();
});

final primaryDeviceOverviewProvider = FutureProvider<DeviceOverview?>((ref) {
  return ref.watch(deviceRepositoryProvider).primaryOverview();
});

final primaryFirmwareStatusProvider = FutureProvider<DeviceFirmwareStatus?>((
  ref,
) async {
  final repository = ref.watch(deviceRepositoryProvider);
  final device = await repository.defaultDevice();
  if (device == null) return null;
  return repository.firmwareStatus(device.id);
});

final deviceOverviewProvider = FutureProvider.family<DeviceOverview, String>((
  ref,
  deviceId,
) {
  return ref.watch(deviceRepositoryProvider).overview(deviceId);
});

class DeviceRepository {
  const DeviceRepository({required this._apiClient});

  final ApiClient _apiClient;

  Future<List<GuardianDevice>> devices() async {
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
    final device = await defaultDevice();
    if (device == null) return null;
    return overview(device.id, fallback: device);
  }

  Future<GuardianDevice?> defaultDevice() async {
    try {
      final response = await _apiClient.get('/devices/default');
      final raw = _asMap(response.data)['device'];
      if (raw == null) return null;
      return GuardianDevice.fromJson(_asMap(raw));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianDevice> bindDevice({
    required String bindingCode,
    required String name,
    String? location,
    bool setAsDefault = false,
  }) async {
    try {
      final response = await _apiClient.post(
        '/devices',
        data: {
          'bindingCode': bindingCode,
          'name': name,
          if (location != null && location.isNotEmpty) 'location': location,
          'setAsDefault': setAsDefault,
        },
      );
      return GuardianDevice.fromJson(_asMap(_asMap(response.data)['device']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianDevice> setDefaultDevice(String deviceId) async {
    try {
      final response = await _apiClient.post('/devices/$deviceId/set-default');
      return GuardianDevice.fromJson(_asMap(_asMap(response.data)['device']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<DeviceOverview> overview(
    String deviceId, {
    GuardianDevice? fallback,
  }) async {
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

  Future<GuardianDevice> updateDevice({
    required String deviceId,
    String? name,
    String? location,
  }) async {
    try {
      final response = await _apiClient.patch(
        '/devices/$deviceId',
        data: {'name': name, 'location': location},
      );
      return GuardianDevice.fromJson(_asMap(_asMap(response.data)['device']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianDevice> renameDevice(String deviceId, String name) async {
    try {
      final response = await _apiClient.post(
        '/devices/$deviceId/rename',
        data: {'name': name},
      );
      return GuardianDevice.fromJson(_asMap(_asMap(response.data)['device']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianDevice> unbindDevice(String deviceId) async {
    try {
      final response = await _apiClient.post('/devices/$deviceId/unbind');
      return GuardianDevice.fromJson(_asMap(_asMap(response.data)['device']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<DeviceFirmwareStatus> firmwareStatus(String deviceId) async {
    try {
      final response = await _apiClient.get(
        '/firmware/devices/$deviceId/status',
      );
      return DeviceFirmwareStatus.fromJson(_asMap(response.data));
    } on DioException catch (error) {
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

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
