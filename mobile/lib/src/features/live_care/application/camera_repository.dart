import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';

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

/// 下拉 refresh 后优先展示的最新观察（避免 status 仍读 DB 旧时间戳）。
final cameraMonitorOverrideProvider = StateProvider<CameraMonitorStatus?>(
  (ref) => null,
);

final cameraMonitorDisplayProvider = Provider<AsyncValue<CameraMonitorStatus>>((
  ref,
) {
  final override = ref.watch(cameraMonitorOverrideProvider);
  if (override != null) {
    return AsyncValue.data(override);
  }
  return ref.watch(cameraMonitorStatusProvider);
});

final cameraSnapshotProvider = FutureProvider<CameraSnapshotFrame>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).snapshot(deviceId: device?.id);
});

final cameraEventsProvider =
    AsyncNotifierProvider<CameraEventsController, List<LiveCareEvent>>(
      CameraEventsController.new,
    );

class CameraEventsController extends AsyncNotifier<List<LiveCareEvent>> {
  String? _deviceId;

  @override
  Future<List<LiveCareEvent>> build() async {
    final device = await ref.watch(selectedDeviceProvider.future);
    _deviceId = device?.id;
    return _fetch();
  }

  Future<void> refresh({bool keepPrevious = true}) async {
    final previous = state.asData?.value;
    if (!keepPrevious || previous == null) {
      state = const AsyncLoading();
    }
    try {
      final events = await _fetch();
      state = AsyncData(events);
    } catch (error, stackTrace) {
      if (previous != null && keepPrevious) {
        state = AsyncData(previous);
        return;
      }
      state = AsyncError(error, stackTrace);
    }
  }

  void handleRealtimeEvent(TaskRealtimeEvent event) {
    if (event.event != null) {
      final item = LiveCareEvent.fromJson(event.event!);
      if (!item.isCareRecord) return;
      final current = state.asData?.value ?? const <LiveCareEvent>[];
      if (current.any((existing) => existing.id == item.id)) return;
      final dedupeKey = _realtimeDedupeKey(item);
      if (current.any((existing) => _realtimeDedupeKey(existing) == dedupeKey)) {
        return;
      }
      state = AsyncData([item, ...current]);
      return;
    }
    if (event.isCameraObservationUpdated || event.isCameraEventCreated) {
      unawaited(refresh());
    }
  }

  Future<List<LiveCareEvent>> _fetch() {
    return ref.read(cameraRepositoryProvider).events(deviceId: _deviceId);
  }
}

final liveCareStatusProvider = FutureProvider<LiveCareStatus>((ref) async {
  final health = await ref.watch(cameraHealthProvider.future);
  final runtime = await ref.watch(cameraRuntimeProvider.future);
  final status = await ref.watch(cameraStatusProvider.future);
  final monitor = await ref.watch(cameraMonitorStatusProvider.future);
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

  Future<CameraMonitorStatus> refreshMonitor({String? deviceId}) async {
    try {
      final response = await _apiClient.post(
        '/camera/monitor/refresh',
        queryParameters: _deviceQuery(deviceId),
      );
      return CameraMonitorStatus.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) {
        if (data['monitor'] != null) {
          return CameraMonitorStatus.fromJson(_asMap(data));
        }
        final message = data['message'];
        if (message is String && message.isNotEmpty) {
          return CameraMonitorStatus(
            running: false,
            status: 'unavailable',
            message: message,
            lastObservation: '',
            lastReminder: '',
          );
        }
      }
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
      return raw
          .map((event) => LiveCareEvent.fromJson(_asMap(event)))
          .where((event) => event.isCareRecord)
          .toList();
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

String _realtimeDedupeKey(LiveCareEvent event) {
  final bucket = event.createdAt ~/ 600000;
  final title = event.displayTitle.trim();
  return '${event.category}:$title:$bucket';
}
