import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/devices/application/selected_device_controller.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';

final cameraRepositoryProvider = Provider<CameraRepository>((ref) {
  return CameraRepository(
    apiClient: ref.watch(apiClientProvider),
    dio: ref.watch(dioProvider),
  );
});

final cameraHealthProvider = FutureProvider<CameraHealth>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).health(deviceId: device?.id);
});

final cameraRuntimeProvider = FutureProvider<CameraRuntime>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).runtime(deviceId: device?.id);
});

final cameraStatusProvider = FutureProvider<CameraStatus>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).status(deviceId: device?.id);
});

final cameraMonitorStatusProvider = FutureProvider<CameraMonitorStatus>((
  ref,
) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref
      .watch(cameraRepositoryProvider)
      .monitorStatus(deviceId: device?.id);
});

final cameraSnapshotProvider = FutureProvider<CameraSnapshotFrame>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).snapshot(deviceId: device?.id);
});

final cameraEventsProvider = FutureProvider<List<LiveCareEvent>>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).events(deviceId: device?.id);
});

final liveCareStatusProvider = FutureProvider<LiveCareStatus>((ref) async {
  final repository = ref.watch(cameraRepositoryProvider);
  final device = await ref.watch(selectedDeviceProvider.future);
  final deviceId = device?.id;
  final health = await repository.health(deviceId: deviceId);
  final runtime = await repository.runtime(deviceId: deviceId);
  final status = await repository.status(deviceId: deviceId);
  final monitor = await repository.monitorStatus(deviceId: deviceId);
  return LiveCareStatus(
    health: health,
    runtime: runtime,
    cameraStatus: status,
    monitorStatus: monitor,
  );
});

class CameraRepository {
  const CameraRepository({required this._apiClient, required this._dio});

  final ApiClient _apiClient;
  final Dio _dio;

  Future<CameraHealth> health({String? deviceId}) async {
    try {
      final response = await _apiClient.get(
        '/camera/health',
        queryParameters: _deviceQuery(deviceId),
      );
      return CameraHealth.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) return CameraHealth.fromJson(_asMap(data));
      throw _fromDio(error, fallback: '摄像头健康状态暂时不可用。');
    }
  }

  Future<CameraRuntime> runtime({String? deviceId}) async {
    try {
      final response = await _apiClient.get(
        '/camera/runtime',
        queryParameters: _deviceQuery(deviceId),
      );
      return CameraRuntime.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) return CameraRuntime.fromJson(_asMap(data));
      throw _fromDio(error, fallback: '摄像头运行状态暂时不可用。');
    }
  }

  Future<CameraStatus> status({String? deviceId}) async {
    try {
      final response = await _apiClient.get(
        '/camera/status',
        queryParameters: _deviceQuery(deviceId),
      );
      return CameraStatus.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) return CameraStatus.fromJson(_asMap(data));
      throw _fromDio(error, fallback: '摄像头状态暂时不可用。');
    }
  }

  Future<CameraMonitorStatus> monitorStatus({String? deviceId}) async {
    try {
      final response = await _apiClient.get(
        '/camera/monitor/status',
        queryParameters: _deviceQuery(deviceId),
      );
      return CameraMonitorStatus.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) return CameraMonitorStatus.fromJson(_asMap(data));
      throw _fromDio(error, fallback: '观察状态暂时不可用。');
    }
  }

  Future<CameraSnapshotFrame> snapshot({String? deviceId}) async {
    try {
      final response = await _dio.get<List<int>>(
        '/camera/snapshot',
        queryParameters: _deviceQuery(deviceId),
        options: Options(responseType: ResponseType.bytes),
      );
      final bytes = response.data;
      if (bytes == null || bytes.isEmpty) {
        final message = response.headers.value('x-mira-snapshot-message');
        return CameraSnapshotFrame(
          available: false,
          bytes: null,
          contentType: '',
          message: _snapshotUnavailableMessage(message),
        );
      }
      return CameraSnapshotFrame(
        available: true,
        bytes: Uint8List.fromList(bytes),
        contentType: response.headers.value('content-type') ?? 'image/jpeg',
        message: '快照已更新',
      );
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) {
        final message = data['message'];
        return CameraSnapshotFrame(
          available: false,
          bytes: null,
          contentType: '',
          message: message is String && message.isNotEmpty
              ? message
              : '实时画面暂时不可用',
        );
      }
      return const CameraSnapshotFrame(
        available: false,
        bytes: null,
        contentType: '',
        message: '实时画面暂时不可用',
      );
    }
  }

  Future<CameraWebRtcSession> createWebRtcSession({String? deviceId}) async {
    try {
      final response = await _apiClient.get(
        '/camera/webrtc/session',
        queryParameters: _deviceQuery(deviceId),
      );
      return CameraWebRtcSession.fromJson(
        _asMap(response.data),
      ).normalizedForApiBase(_dio.options.baseUrl);
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '实时画面暂时无法连接，请稍后再试。');
    }
  }

  Future<void> speak(String text, {String? taskId, String? deviceId}) async {
    try {
      await _apiClient.post(
        '/camera/commands/speak',
        data: {
          'text': text,
          if (taskId != null && taskId.isNotEmpty) 'taskId': taskId,
          if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        },
      );
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '暂时没能发出提醒，请稍后再试。');
    }
  }

  Future<void> movePtz(
    String direction, {
    int step = 1,
    String? deviceId,
  }) async {
    try {
      await _apiClient.post(
        '/camera/commands/ptz',
        data: {
          'direction': direction,
          'step': step,
          if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        },
      );
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '暂时无法控制摄像头方向。');
    }
  }

  Future<List<LiveCareEvent>> events({String? deviceId}) async {
    try {
      final response = await _apiClient.get(
        '/camera/events',
        queryParameters: _deviceQuery(deviceId),
      );
      final raw = _asMap(response.data)['events'];
      if (raw is! List) return const [];
      return raw.map((event) => LiveCareEvent.fromJson(_asMap(event))).toList();
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '暂时拿不到看护事件。');
    }
  }

  CameraException _fromDio(DioException error, {required String fallback}) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return CameraException(
          message,
          code: code is String ? code : 'camera_error',
        );
      }
    }
    return CameraException(fallback, code: 'network_error');
  }
}

Map<String, String> _deviceQuery(String? deviceId) {
  final value = deviceId?.trim();
  if (value == null || value.isEmpty) return const {};
  return {'deviceId': value};
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String _snapshotUnavailableMessage(String? headerValue) {
  final value = (headerValue ?? '').trim();
  if (value == 'snapshot_unavailable') return '实时画面暂时不可用';
  if (value.isNotEmpty) return value;
  return '暂时没有可用快照';
}
