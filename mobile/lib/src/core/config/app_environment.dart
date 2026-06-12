import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppFlavor { development, staging, production, test }

const _defaultDevelopmentApiBaseUrl = 'http://192.168.228.95:8000/api';
const _defaultLocalApiBaseUrl = 'http://127.0.0.1:8000/api';
const _defaultLocalTaskWebSocketBaseUrl = 'ws://127.0.0.1:8001/api';

class AppEnvironment {
  const AppEnvironment({
    required this.flavor,
    required this.apiBaseUrl,
    this.taskWebSocketBaseUrl = '',
  });

  factory AppEnvironment.development() {
    return const AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: _defaultDevelopmentApiBaseUrl,
      taskWebSocketBaseUrl: 'ws://192.168.228.95:8001/api',
    );
  }

  factory AppEnvironment.localBackend() {
    return const AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: _defaultLocalApiBaseUrl,
      taskWebSocketBaseUrl: _defaultLocalTaskWebSocketBaseUrl,
    );
  }

  factory AppEnvironment.staging() {
    final apiBaseUrl = _requiredApiBaseUrl(AppFlavor.staging);
    return AppEnvironment(
      flavor: AppFlavor.staging,
      apiBaseUrl: apiBaseUrl,
      taskWebSocketBaseUrl: _defaultTaskWebSocketBaseUrl(
        apiBaseUrl,
        AppFlavor.staging,
      ),
    );
  }

  factory AppEnvironment.production() {
    final apiBaseUrl = _requiredApiBaseUrl(AppFlavor.production);
    return AppEnvironment(
      flavor: AppFlavor.production,
      apiBaseUrl: apiBaseUrl,
      taskWebSocketBaseUrl: _defaultTaskWebSocketBaseUrl(
        apiBaseUrl,
        AppFlavor.production,
      ),
    );
  }

  factory AppEnvironment.fromDartDefines() {
    const flavorName = String.fromEnvironment(
      'APP_FLAVOR',
      defaultValue: 'development',
    );
    const definedApiBaseUrl = String.fromEnvironment('API_BASE_URL');
    const taskWsBaseUrl = String.fromEnvironment('TASK_WS_BASE_URL');
    final flavor = switch (flavorName) {
      'production' => AppFlavor.production,
      'staging' => AppFlavor.staging,
      'test' => AppFlavor.test,
      _ => AppFlavor.development,
    };
    final apiBaseUrl = definedApiBaseUrl.trim().isEmpty
        ? _defaultApiBaseUrlFor(flavor)
        : definedApiBaseUrl.trim();
    if (flavor == AppFlavor.production && apiBaseUrl.trim().isEmpty) {
      throw UnsupportedError('API_BASE_URL is required in production.');
    }
    return AppEnvironment(
      flavor: flavor,
      apiBaseUrl: apiBaseUrl,
      taskWebSocketBaseUrl: taskWsBaseUrl.trim().isEmpty
          ? _defaultTaskWebSocketBaseUrl(apiBaseUrl, flavor)
          : taskWsBaseUrl,
    );
  }

  final AppFlavor flavor;
  final String apiBaseUrl;
  final String taskWebSocketBaseUrl;
}

String _defaultApiBaseUrlFor(AppFlavor flavor) {
  return switch (flavor) {
    AppFlavor.development => _defaultDevelopmentApiBaseUrl,
    AppFlavor.test => _defaultLocalApiBaseUrl,
    AppFlavor.staging || AppFlavor.production => '',
  };
}

String _requiredApiBaseUrl(AppFlavor flavor) {
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  if (apiBaseUrl.trim().isEmpty) {
    throw UnsupportedError('API_BASE_URL is required for $flavor.');
  }
  return apiBaseUrl;
}

String _defaultTaskWebSocketBaseUrl(String apiBaseUrl, AppFlavor flavor) {
  final uri = Uri.tryParse(apiBaseUrl);
  if (uri == null || uri.host.isEmpty) return '';
  final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
  if (flavor == AppFlavor.development) {
    return uri
        .replace(scheme: scheme, port: 8001, path: '/api', query: '')
        .toString();
  }
  return uri.replace(scheme: scheme).toString();
}

final appEnvironmentProvider = Provider<AppEnvironment>((ref) {
  throw UnimplementedError('AppEnvironment must be provided at bootstrap.');
});
