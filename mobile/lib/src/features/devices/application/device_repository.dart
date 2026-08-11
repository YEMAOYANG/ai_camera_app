import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';

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
          .where((device) => device.status != 'unbound')
          .toList();
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<DiscoveredCameraCandidate>>
  discoverNearbyCameraCandidates() async {
    await Future<void>.delayed(const Duration(milliseconds: 220));
    return const [
      DiscoveredCameraCandidate(
        id: 'nearby-child-room',
        displayName: '儿童房摄像头',
        bindingCode: 'AI-CARE-NEARBY-KINDERGARTEN-V1-CHILD',
        signalStrength: 92,
        status: 'ready',
        roomHint: '儿童房',
        source: CameraDiscoveryCandidateSource.mock,
      ),
      DiscoveredCameraCandidate(
        id: 'nearby-living-room',
        displayName: '客厅摄像头',
        bindingCode: 'AI-CARE-NEARBY-KINDERGARTEN-V1-LIVING',
        signalStrength: 76,
        status: 'ready',
        roomHint: '客厅',
        source: CameraDiscoveryCandidateSource.mock,
      ),
      DiscoveredCameraCandidate(
        id: 'nearby-dining-room',
        displayName: '餐厅摄像头',
        bindingCode: 'AI-CARE-NEARBY-KINDERGARTEN-V1-DINING',
        signalStrength: 61,
        status: 'ready',
        roomHint: '餐厅',
        source: CameraDiscoveryCandidateSource.mock,
      ),
    ];
  }

  Future<List<DiscoveredCameraCandidate>> discoveryStatuses(
    List<DiscoveredCameraCandidate> candidates,
  ) async {
    if (candidates.isEmpty) return candidates;
    final identifiable = candidates
        .where((candidate) => !_usesEphemeralBleIdentifier(candidate))
        .toList(growable: false);
    if (identifiable.isEmpty) return candidates;
    try {
      final response = await _apiClient.post(
        '/devices/discovery-status',
        data: {
          'candidates': [
            for (final candidate in identifiable)
              {'id': candidate.id, 'bindingCode': candidate.bindingCode},
          ],
        },
      );
      final raw = _asMap(response.data)['candidates'];
      if (raw is! List) return candidates;
      final statuses = <String, Map<String, dynamic>>{};
      for (final item in raw) {
        final map = _asMap(item);
        final id = _string(map['id']);
        final bindingCode = _string(map['bindingCode']);
        if (id.isNotEmpty) statuses[id] = map;
        if (bindingCode.isNotEmpty) statuses[bindingCode] = map;
      }
      return [
        for (final candidate in candidates)
          _mergeDiscoveryStatus(
            candidate,
            statuses[candidate.id] ?? statuses[candidate.bindingCode],
          ),
      ];
    } on DioException {
      return candidates;
    }
  }

  Future<List<OnvifDiscoveryCandidate>> discoverOnvifDevices({
    String? targetIp,
  }) async {
    final normalizedTarget = targetIp?.trim() ?? '';
    try {
      final response = await _apiClient.post(
        '/devices/discovery/onvif',
        data: {
          'timeoutMs': 2500,
          if (normalizedTarget.isNotEmpty) 'targetIp': normalizedTarget,
        },
      );
      final raw = _asMap(response.data)['candidates'];
      if (raw is! List) return const [];
      return raw
          .map(
            (candidate) => OnvifDiscoveryCandidate.fromJson(_asMap(candidate)),
          )
          .where(
            (candidate) =>
                candidate.id.isNotEmpty &&
                candidate.discoveryToken.isNotEmpty &&
                !candidate.isExpired,
          )
          .toList(growable: false);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<OnvifPairResult> pairOnvifDevice({
    required String discoveryToken,
    String? name,
    String? location,
    bool setAsDefault = false,
  }) async {
    final normalizedName = name?.trim() ?? '';
    final normalizedLocation = location?.trim() ?? '';
    try {
      final response = await _apiClient.post(
        '/devices/pair/onvif',
        data: {
          'discoveryToken': discoveryToken,
          if (normalizedName.isNotEmpty) 'name': normalizedName,
          if (normalizedLocation.isNotEmpty) 'location': normalizedLocation,
          'setAsDefault': setAsDefault,
        },
      );
      return OnvifPairResult.fromJson(_asMap(response.data));
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

  Future<DeviceUnbindResult> unbindDevice(String deviceId) async {
    try {
      final response = await _apiClient.post('/devices/$deviceId/unbind');
      final map = _asMap(response.data);
      final defaultRaw = map['defaultDevice'];
      return DeviceUnbindResult(
        device: GuardianDevice.fromJson(_asMap(map['device'])),
        defaultDevice: defaultRaw == null
            ? null
            : GuardianDevice.fromJson(_asMap(defaultRaw)),
      );
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

String _string(dynamic value) => value is String ? value : '';

bool _usesEphemeralBleIdentifier(DiscoveredCameraCandidate candidate) {
  return candidate.source == CameraDiscoveryCandidateSource.ble &&
      candidate.bindingCode.startsWith('ble:');
}

DiscoveredCameraCandidate _mergeDiscoveryStatus(
  DiscoveredCameraCandidate candidate,
  Map<String, dynamic>? status,
) {
  if (status == null) return candidate;
  final bindingState = _bindingStateFromString(_string(status['bindingState']));
  final isConnectable = status['isConnectable'];
  final disabledReason = _string(status['disabledReason']);
  return candidate.copyWith(
    status: bindingState == CameraCandidateBindingState.boundToAnotherFamily
        ? 'bound_to_other_family'
        : candidate.status,
    bindingState: bindingState,
    isConnectable: isConnectable is bool
        ? isConnectable
        : candidate.isConnectable,
    unavailableReason: disabledReason.isNotEmpty
        ? disabledReason
        : candidate.unavailableReason,
    ownerHint: _string(status['ownerHint']).isEmpty
        ? candidate.ownerHint
        : _string(status['ownerHint']),
  );
}

CameraCandidateBindingState _bindingStateFromString(String value) {
  return switch (value) {
    'available' => CameraCandidateBindingState.available,
    'boundToCurrentFamily' ||
    'bound_to_current_family' => CameraCandidateBindingState.boundToThisFamily,
    'boundToAnotherFamily' || 'bound_to_another_family' =>
      CameraCandidateBindingState.boundToAnotherFamily,
    _ => CameraCandidateBindingState.unknown,
  };
}
