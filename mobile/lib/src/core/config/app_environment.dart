import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppFlavor { development, staging, production, test }

class AppEnvironment {
  const AppEnvironment({
    required this.flavor,
    required this.apiBaseUrl,
    required this.useMockData,
  });

  factory AppEnvironment.development() {
    return const AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      useMockData: false,
    );
  }

  factory AppEnvironment.localBackend() {
    return const AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      useMockData: false,
    );
  }

  factory AppEnvironment.staging() {
    return AppEnvironment(
      flavor: AppFlavor.staging,
      apiBaseUrl: _requiredApiBaseUrl(AppFlavor.staging),
      useMockData: false,
    );
  }

  factory AppEnvironment.production() {
    return AppEnvironment(
      flavor: AppFlavor.production,
      apiBaseUrl: _requiredApiBaseUrl(AppFlavor.production),
      useMockData: false,
    );
  }

  factory AppEnvironment.mock() {
    return const AppEnvironment(
      flavor: AppFlavor.test,
      apiBaseUrl: 'mock://local/api',
      useMockData: true,
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
    const useMockData = bool.fromEnvironment(
      'USE_MOCK_DATA',
      defaultValue: false,
    );
    final flavor = switch (flavorName) {
      'production' => AppFlavor.production,
      'staging' => AppFlavor.staging,
      'test' => AppFlavor.test,
      _ => AppFlavor.development,
    };
    if (flavor == AppFlavor.production && useMockData) {
      throw UnsupportedError('USE_MOCK_DATA cannot be true in production.');
    }
    if (flavor == AppFlavor.production && apiBaseUrl.trim().isEmpty) {
      throw UnsupportedError('API_BASE_URL is required in production.');
    }
    return AppEnvironment(
      flavor: flavor,
      apiBaseUrl: apiBaseUrl,
      useMockData: useMockData,
    );
  }

  final AppFlavor flavor;
  final String apiBaseUrl;
  final bool useMockData;
}

String _requiredApiBaseUrl(AppFlavor flavor) {
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  if (apiBaseUrl.trim().isEmpty) {
    throw UnsupportedError('API_BASE_URL is required for $flavor.');
  }
  return apiBaseUrl;
}

final appEnvironmentProvider = Provider<AppEnvironment>((ref) {
  throw UnimplementedError('AppEnvironment must be provided at bootstrap.');
});
