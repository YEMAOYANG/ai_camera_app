import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppFlavor { development, staging, production, test }

class AppEnvironment {
  const AppEnvironment({
    required this.flavor,
    required this.apiBaseUrl,
    this.taskWebSocketBaseUrl = '',
  });

  factory AppEnvironment.development() {
    return const AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      taskWebSocketBaseUrl: 'ws://127.0.0.1:8001/api',
    );
  }

  factory AppEnvironment.localBackend() {
    return const AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      taskWebSocketBaseUrl: 'ws://127.0.0.1:8001/api',
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
    const apiBaseUrl = String.fromEnvironment(
      'API_BASE_URL',
      defaultValue: 'http://127.0.0.1:8000/api',
    );
    const taskWsBaseUrl = String.fromEnvironment('TASK_WS_BASE_URL');
    final flavor = switch (flavorName) {
      'production' => AppFlavor.production,
      'staging' => AppFlavor.staging,
      'test' => AppFlavor.test,
      _ => AppFlavor.development,
    };
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

String _requiredApiBaseUrl(AppFlavor flavor) {
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  if (apiBaseUrl.trim().isEmpty) {
    throw UnsupportedError('API_BASE_URL is required for $flavor.');
  }
  return apiBaseUrl;
}

String _defaultTaskWebSocketBaseUrl(String apiBaseUrl, AppFlavor flavor) {
  if (flavor == AppFlavor.development) {
    return 'ws://127.0.0.1:8001/api';
  }
  final uri = Uri.tryParse(apiBaseUrl);
  if (uri == null || uri.host.isEmpty) return '';
  final scheme = uri.scheme == 'https' ? 'wss' : 'ws';
  return uri.replace(scheme: scheme).toString();
}

final appEnvironmentProvider = Provider<AppEnvironment>((ref) {
  throw UnimplementedError('AppEnvironment must be provided at bootstrap.');
});
