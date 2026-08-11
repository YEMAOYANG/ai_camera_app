import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/state/async_value_ui.dart';
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
final cameraMonitorOverrideProvider = StateProvider<CameraMonitorStatus?>((
  ref,
) {
  // 切换摄像头后不能继续展示上一台设备的即时观察结果。
  ref.watch(selectedDeviceChangeEpochProvider);
  return null;
});

final cameraMonitorDisplayProvider = Provider<AsyncValue<CameraMonitorStatus>>((
  ref,
) {
  final remote = ref.watch(cameraMonitorStatusProvider);
  final override = ref.watch(cameraMonitorOverrideProvider);
  if (override == null) return remote;

  return remote.when(
    data: (server) =>
        AsyncValue.data(preferredCameraMonitorStatus(server, override)),
    loading: () => AsyncValue.data(override),
    error: (_, _) => AsyncValue.data(override),
  );
});

CameraMonitorStatus preferredCameraMonitorStatus(
  CameraMonitorStatus server,
  CameraMonitorStatus override,
) {
  if (override.hasRefreshError) {
    final serverAt = server.lastObservationObservedAt ?? 0;
    final overrideAt = override.lastObservationObservedAt ?? 0;
    if (server.hasCurrentReliableObservation && serverAt > overrideAt) {
      return server;
    }
    return override;
  }
  final serverHasFormalObservation = _hasFormalObservation(server);
  final overrideHasFormalObservation = _hasFormalObservation(override);
  if (!overrideHasFormalObservation && serverHasFormalObservation) {
    return server;
  }
  if (overrideHasFormalObservation && !serverHasFormalObservation) {
    return override;
  }
  final serverAt = server.lastObservationObservedAt ?? 0;
  final overrideAt = override.lastObservationObservedAt ?? 0;
  if (overrideAt > serverAt) return override;
  if (overrideAt < serverAt) return server;
  if (override.lastObservationReliable && !server.lastObservationReliable) {
    return override;
  }
  return server;
}

bool _hasFormalObservation(CameraMonitorStatus status) {
  if (status.lastObservation.trim().isEmpty) return false;
  return status.lastObservationFreshness == CameraObservationFreshness.fresh ||
      status.lastObservationFreshness == CameraObservationFreshness.stale;
}

final cameraSnapshotProvider = FutureProvider<CameraSnapshotFrame>((ref) async {
  final device = await ref.watch(selectedDeviceProvider.future);
  return ref.watch(cameraRepositoryProvider).snapshot(deviceId: device?.id);
});

final cameraEventsProvider =
    AsyncNotifierProvider<CameraEventsController, CameraEventsState>(
      CameraEventsController.new,
    );

class CameraEventsController extends AsyncNotifier<CameraEventsState> {
  String? _deviceId;
  static const _pageSize = 10;

  @override
  Future<CameraEventsState> build() async {
    final device = await ref.watch(selectedDeviceProvider.future);
    _deviceId = device?.id;
    final page = await _fetchPage(offset: 0);
    return CameraEventsState(
      items: _mergeCameraEvents(page.events),
      hasMore: page.hasMore,
      loadedCount: page.events.length,
    );
  }

  Future<void> refresh({bool keepPrevious = true}) async {
    final previous = state.asData?.value;
    if (!keepPrevious || previous == null) {
      state = const AsyncLoading();
    }
    try {
      final page = await _fetchPage(offset: 0);
      state = AsyncData(
        CameraEventsState(
          items: _mergeCameraEvents(page.events),
          hasMore: page.hasMore,
          loadedCount: page.events.length,
        ),
      );
    } catch (error, stackTrace) {
      if (previous != null && keepPrevious) {
        state = AsyncData(previous);
        return;
      }
      state = AsyncError(error, stackTrace);
    }
  }

  Future<bool> loadMore() async {
    final current = state.asData?.value;
    if (current == null || !current.hasMore || current.isLoadingMore) {
      return current?.hasMore ?? false;
    }
    state = AsyncData(current.copyWith(isLoadingMore: true));
    try {
      final page = await _fetchPage(offset: current.loadedCount);
      final merged = _mergeCameraEvents([...current.items, ...page.events]);
      state = AsyncData(
        CameraEventsState(
          items: merged,
          hasMore: page.hasMore,
          isLoadingMore: false,
          loadedCount: current.loadedCount + page.events.length,
        ),
      );
      return page.hasMore;
    } catch (_) {
      state = AsyncData(current.copyWith(isLoadingMore: false));
      return current.hasMore;
    }
  }

  void handleRealtimeEvent(TaskRealtimeEvent event) {
    if (event.event != null) {
      final item = LiveCareEvent.fromJson(event.event!);
      if (!item.isCareRecord) return;
      final current = state.asData?.value ?? const CameraEventsState();
      if (current.items.any((existing) => existing.id == item.id)) return;
      final dedupeKey = _realtimeDedupeKey(item);
      if (current.items.any(
        (existing) => _realtimeDedupeKey(existing) == dedupeKey,
      )) {
        return;
      }
      state = AsyncData(
        current.copyWith(items: _mergeCameraEvents([item, ...current.items])),
      );
      return;
    }
    if (event.isCameraObservationUpdated || event.isCameraEventCreated) {
      unawaited(refresh());
    }
  }

  Future<CameraEventsPage> _fetchPage({required int offset}) {
    return ref
        .read(cameraRepositoryProvider)
        .eventsPage(deviceId: _deviceId, limit: _pageSize, offset: offset);
  }
}

final liveCareStatusProvider = Provider<AsyncValue<LiveCareStatus>>((ref) {
  final health = ref.watch(cameraHealthProvider);
  final runtime = ref.watch(cameraRuntimeProvider);
  final status = ref.watch(cameraStatusProvider);
  final monitor = ref.watch(cameraMonitorDisplayProvider);
  final parts = [health, runtime, status, monitor];

  if (parts.every((part) => part.hasValue)) {
    return AsyncValue.data(
      LiveCareStatus(
        health: health.requireValue,
        runtime: runtime.requireValue,
        cameraStatus: status.requireValue,
        monitorStatus: monitor.requireValue,
      ),
    );
  }

  if (parts.any((part) => isInitialAsyncLoad(part))) {
    return const AsyncValue.loading();
  }

  for (final part in parts) {
    if (part.hasError) {
      return AsyncValue.error(part.error!, part.stackTrace!);
    }
  }

  return const AsyncValue.loading();
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
        options: Options(
          responseType: ResponseType.bytes,
          headers: const {'Accept': 'image/jpeg,*/*'},
          validateStatus: (status) =>
              status != null && status >= 200 && status < 300,
        ),
      );
      final statusCode = response.statusCode ?? 200;
      if (statusCode == 204) {
        final message = response.headers.value('x-mira-snapshot-message');
        return CameraSnapshotFrame(
          available: false,
          bytes: null,
          contentType: '',
          message: _snapshotUnavailableMessage(message),
        );
      }
      final rawBytes = response.data;
      final bytes = rawBytes is Uint8List
          ? rawBytes
          : rawBytes == null
          ? null
          : Uint8List.fromList(rawBytes);
      if (bytes == null || bytes.isEmpty || !_looksLikeJpeg(bytes)) {
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
        bytes: bytes,
        contentType: response.headers.value('content-type') ?? 'image/jpeg',
        message: '快照已更新',
      );
    } on DioException catch (error) {
      if (error.response?.statusCode == 204) {
        final message = error.response?.headers.value(
          'x-mira-snapshot-message',
        );
        return CameraSnapshotFrame(
          available: false,
          bytes: null,
          contentType: '',
          message: _snapshotUnavailableMessage(message),
        );
      }
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

  Future<CameraEventsPage> eventsPage({
    String? deviceId,
    int limit = 10,
    int offset = 0,
  }) async {
    try {
      final response = await _apiClient.get(
        '/camera/events',
        queryParameters: {
          ..._deviceQuery(deviceId),
          'limit': limit,
          'offset': offset,
        },
      );
      final body = _asMap(response.data);
      final raw = body['events'];
      if (raw is! List) {
        return const CameraEventsPage(events: [], hasMore: false);
      }
      final events = raw
          .map((event) => LiveCareEvent.fromJson(_asMap(event)))
          .where((event) => event.isCareRecord)
          .toList();
      final hasMore = body['hasMore'] == true;
      return CameraEventsPage(events: events, hasMore: hasMore);
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '暂时拿不到看护事件。');
    }
  }

  Future<List<LiveCareEvent>> events({String? deviceId}) async {
    final page = await eventsPage(deviceId: deviceId, limit: 30, offset: 0);
    return page.events;
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

bool _looksLikeJpeg(Uint8List bytes) {
  return bytes.length >= 3 &&
      bytes[0] == 0xFF &&
      bytes[1] == 0xD8 &&
      bytes[2] == 0xFF;
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

List<LiveCareEvent> _mergeCameraEvents(Iterable<LiveCareEvent> events) {
  final byId = <String, LiveCareEvent>{};
  for (final event in events) {
    if (event.id.isEmpty) continue;
    byId[event.id] = event;
  }
  final merged = byId.values.toList()
    ..sort((a, b) {
      final time = b.createdAt.compareTo(a.createdAt);
      if (time != 0) return time;
      return b.id.compareTo(a.id);
    });
  return merged;
}
