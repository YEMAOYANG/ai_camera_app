import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/storage/auth_session_store.dart';

final taskRealtimeProvider = StreamProvider.autoDispose<TaskRealtimeEvent>((
  ref,
) async* {
  final environment = ref.watch(appEnvironmentProvider);
  if (environment.useMockData) return;

  final session = ref.watch(authSessionStoreProvider).currentSession;
  final token = session?.accessToken ?? '';
  if (token.isEmpty) return;

  final uri = taskRealtimeUri(environment, token);
  if (uri == null) return;

  var disposed = false;
  WebSocket? activeSocket;
  ref.onDispose(() {
    disposed = true;
    unawaited(activeSocket?.close());
  });

  while (!disposed) {
    WebSocket? socket;
    try {
      socket = await WebSocket.connect(
        uri.toString(),
      ).timeout(const Duration(seconds: 8));
      activeSocket = socket;
      socket.pingInterval = const Duration(seconds: 25);

      await for (final message in socket) {
        if (disposed) break;
        if (message is! String) continue;
        final decoded = jsonDecode(message);
        if (decoded is Map) {
          yield TaskRealtimeEvent.fromJson(Map<String, dynamic>.from(decoded));
        }
      }
    } catch (_) {
      if (disposed) break;
    } finally {
      activeSocket = null;
      unawaited(socket?.close());
    }

    if (!disposed) {
      await Future<void>.delayed(const Duration(seconds: 3));
    }
  }
});

class TaskRealtimeEvent {
  const TaskRealtimeEvent({
    required this.type,
    required this.taskIds,
    required this.sentAt,
    this.source = '',
  });

  final String type;
  final String source;
  final List<String> taskIds;
  final int sentAt;

  bool get isTaskUpdate => type == 'task.updated' && taskIds.isNotEmpty;

  static TaskRealtimeEvent fromJson(Map<String, dynamic> json) {
    final rawTaskIds = json['taskIds'];
    return TaskRealtimeEvent(
      type: _asString(json['type']),
      source: _asString(json['source']),
      taskIds: rawTaskIds is List
          ? rawTaskIds.map(_asString).where((id) => id.isNotEmpty).toList()
          : const [],
      sentAt: _asInt(json['sentAt']),
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
