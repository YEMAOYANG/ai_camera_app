import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';

typedef RealtimeSocketConnector = Future<WebSocket> Function(Uri uri);

final realtimeSocketConnectorProvider = Provider<RealtimeSocketConnector>((
  ref,
) {
  return (uri) =>
      WebSocket.connect(uri.toString()).timeout(const Duration(seconds: 8));
});

final appRealtimeControllerProvider = Provider<AppRealtimeController>((ref) {
  final controller = AppRealtimeController(
    environment: ref.watch(appEnvironmentProvider),
    sessionStore: ref.watch(authSessionStoreProvider),
    connectSocket: ref.watch(realtimeSocketConnectorProvider),
  )..start();
  ref.onDispose(controller.dispose);
  return controller;
});

final taskRealtimeProvider = StreamProvider<TaskRealtimeEvent>((ref) {
  final controller = ref.watch(appRealtimeControllerProvider);
  return controller.events;
});

final appRealtimeStatusProvider = Provider<AppRealtimeStatus>((ref) {
  final controller = ref.watch(appRealtimeControllerProvider);
  return controller.status.value;
});

enum AppRealtimeConnectionPhase {
  idle,
  connecting,
  connected,
  reconnecting,
  disconnected,
}

class AppRealtimeStatus {
  const AppRealtimeStatus({
    required this.phase,
    this.lastEventType = '',
    this.lastEventSentAt = 0,
  });

  final AppRealtimeConnectionPhase phase;
  final String lastEventType;
  final int lastEventSentAt;

  AppRealtimeStatus copyWith({
    AppRealtimeConnectionPhase? phase,
    String? lastEventType,
    int? lastEventSentAt,
  }) {
    return AppRealtimeStatus(
      phase: phase ?? this.phase,
      lastEventType: lastEventType ?? this.lastEventType,
      lastEventSentAt: lastEventSentAt ?? this.lastEventSentAt,
    );
  }
}

class AppRealtimeController with WidgetsBindingObserver {
  AppRealtimeController({
    required this.environment,
    required this.sessionStore,
    required this.connectSocket,
  });

  final AppEnvironment environment;
  final AuthSessionStore sessionStore;
  final RealtimeSocketConnector connectSocket;
  final _events = StreamController<TaskRealtimeEvent>.broadcast();

  final ValueNotifier<AppRealtimeStatus> status = ValueNotifier(
    const AppRealtimeStatus(phase: AppRealtimeConnectionPhase.idle),
  );

  Stream<TaskRealtimeEvent> get events => _events.stream;

  WebSocket? _socket;
  Timer? _reconnectTimer;
  String _activeToken = '';
  int _generation = 0;
  bool _started = false;
  bool _connecting = false;
  bool _disposed = false;

  void start() {
    if (_started || _disposed) return;
    _started = true;
    WidgetsBinding.instance.addObserver(this);
    sessionStore.addListener(_syncWithSession);
    scheduleMicrotask(_syncWithSession);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_disposed) return;
    if (state == AppLifecycleState.resumed) {
      _syncWithSession(forceReconnectIfDisconnected: true);
    }
  }

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _generation++;
    WidgetsBinding.instance.removeObserver(this);
    sessionStore.removeListener(_syncWithSession);
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    final socket = _socket;
    _socket = null;
    unawaited(socket?.close());
    status.value = status.value.copyWith(
      phase: AppRealtimeConnectionPhase.idle,
    );
    unawaited(_events.close());
    status.dispose();
  }

  void _syncWithSession({bool forceReconnectIfDisconnected = false}) {
    if (_disposed) return;
    final token = sessionStore.currentSession?.accessToken ?? '';
    final disconnected = _socket == null && !_connecting;
    if (token == _activeToken &&
        !(forceReconnectIfDisconnected && token.isNotEmpty && disconnected)) {
      return;
    }
    _generation++;
    _activeToken = token;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    final socket = _socket;
    _socket = null;
    _connecting = false;
    unawaited(socket?.close());

    if (token.isEmpty) {
      status.value = status.value.copyWith(
        phase: AppRealtimeConnectionPhase.idle,
      );
      return;
    }
    unawaited(_connect(_generation, token));
  }

  Future<void> _connect(int generation, String token) async {
    if (_disposed || _connecting) return;
    final uri = taskRealtimeUri(environment, token);
    if (uri == null) return;
    _connecting = true;
    status.value = status.value.copyWith(
      phase: _socket == null
          ? AppRealtimeConnectionPhase.connecting
          : AppRealtimeConnectionPhase.reconnecting,
    );
    WebSocket? socket;
    try {
      socket = await connectSocket(uri);
      if (!_isCurrent(generation, token)) {
        unawaited(socket.close());
        return;
      }
      _socket = socket;
      _connecting = false;
      socket.pingInterval = const Duration(seconds: 25);
      status.value = status.value.copyWith(
        phase: AppRealtimeConnectionPhase.connected,
      );
      await for (final message in socket) {
        if (!_isCurrent(generation, token)) break;
        if (message is! String) continue;
        final decoded = jsonDecode(message);
        if (decoded is! Map) continue;
        final event = TaskRealtimeEvent.fromJson(
          Map<String, dynamic>.from(decoded),
        );
        status.value = status.value.copyWith(
          lastEventType: event.type,
          lastEventSentAt: event.sentAt,
        );
        _events.add(event);
      }
    } catch (_) {
      if (!_isCurrent(generation, token)) return;
    } finally {
      _connecting = false;
      if (identical(_socket, socket)) {
        _socket = null;
      }
      unawaited(socket?.close());
    }

    if (_isCurrent(generation, token)) {
      status.value = status.value.copyWith(
        phase: AppRealtimeConnectionPhase.disconnected,
      );
      _scheduleReconnect(generation, token);
    }
  }

  void _scheduleReconnect(int generation, String token) {
    if (_disposed || token.isEmpty) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (!_isCurrent(generation, token) || _connecting || _socket != null) {
        return;
      }
      status.value = status.value.copyWith(
        phase: AppRealtimeConnectionPhase.reconnecting,
      );
      unawaited(_connect(generation, token));
    });
  }

  bool _isCurrent(int generation, String token) {
    return !_disposed && generation == _generation && token == _activeToken;
  }
}

class TaskRealtimeEvent {
  const TaskRealtimeEvent({
    required this.type,
    required this.taskIds,
    required this.sentAt,
    this.eventIds = const [],
    this.source = '',
    this.deviceId = '',
    this.observationId = '',
    this.isReliable,
    this.event,
  });

  final String type;
  final String source;
  final String deviceId;
  final List<String> taskIds;
  final List<String> eventIds;
  final String observationId;
  final bool? isReliable;
  final int sentAt;
  final Map<String, dynamic>? event;

  bool get isTaskUpdate => type == 'task.updated' && taskIds.isNotEmpty;
  bool get isTaskStatusChanged => type == 'task_status.changed';
  bool get isCameraObservationUpdated =>
      type == 'camera_observation.updated' ||
      type == 'camera_monitor.refreshed';
  bool get isCameraEventCreated => type == 'camera_event.created';
  bool get isCameraStatusChanged => type == 'camera_status.changed';
  bool get isReminderEventCreated => type == 'reminder_event.created';
  bool get isReminderDecisionCreated => type == 'reminder_decision.created';
  bool get isCameraCommandCreated => type == 'camera_command.created';
  bool get isSessionRevoked => type == 'session_revoked';

  static TaskRealtimeEvent fromJson(Map<String, dynamic> json) {
    final rawTaskIds = json['taskIds'];
    final rawEventIds = json['eventIds'];
    final rawEvent = json['event'];
    return TaskRealtimeEvent(
      type: _asString(json['type']),
      source: _asString(json['source']),
      deviceId: _asString(json['deviceId']),
      taskIds: rawTaskIds is List
          ? rawTaskIds.map(_asString).where((id) => id.isNotEmpty).toList()
          : const [],
      eventIds: rawEventIds is List
          ? rawEventIds.map(_asString).where((id) => id.isNotEmpty).toList()
          : const [],
      observationId: _asString(json['observationId']),
      isReliable: json['isReliable'] is bool
          ? json['isReliable'] as bool
          : null,
      sentAt: _asInt(json['sentAt']),
      event: rawEvent is Map ? Map<String, dynamic>.from(rawEvent) : null,
    );
  }
}

Uri? taskRealtimeUri(AppEnvironment environment, String token) {
  final base = environment.taskWebSocketBaseUrl.trim().isNotEmpty
      ? environment.taskWebSocketBaseUrl.trim()
      : _webSocketBaseFromApi(environment.apiBaseUrl);
  if (base.isEmpty || token.isEmpty) return null;
  final baseUri = Uri.tryParse(base);
  if (baseUri == null || baseUri.host.isEmpty) return null;
  final normalizedBasePath = baseUri.path.endsWith('/')
      ? baseUri.path.substring(0, baseUri.path.length - 1)
      : baseUri.path;
  return baseUri.replace(
    path: '$normalizedBasePath/tasks/stream',
    queryParameters: {...baseUri.queryParameters, 'token': token},
  );
}

String _webSocketBaseFromApi(String apiBaseUrl) {
  final uri = Uri.tryParse(apiBaseUrl);
  if (uri == null || uri.host.isEmpty) return '';
  final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
  return uri.replace(scheme: scheme).toString();
}

String _asString(Object? value) => value is String ? value : '';

int _asInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}
