import 'dart:convert';

import 'package:warm_sight/src/core/config/app_environment.dart';

class AccountSecurityRealtimeEvent {
  const AccountSecurityRealtimeEvent({
    required this.type,
    required this.sentAt,
    this.reason = '',
    this.message = '',
  });

  final String type;
  final String reason;
  final String message;
  final int sentAt;

  bool get isSessionRevoked => type == 'session_revoked';

  static AccountSecurityRealtimeEvent? tryParse(Object? message) {
    if (message is! String) return null;
    try {
      final decoded = jsonDecode(message);
      if (decoded is! Map) return null;
      final json = Map<String, dynamic>.from(decoded);
      return AccountSecurityRealtimeEvent(
        type: _asString(json['type']),
        reason: _asString(json['reason']),
        message: _asString(json['message']),
        sentAt: _asInt(json['sentAt']),
      );
    } catch (_) {
      return null;
    }
  }
}

Uri? accountSecurityRealtimeUri(AppEnvironment environment, String token) {
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
    path: '$normalizedBasePath/account/security/stream',
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
