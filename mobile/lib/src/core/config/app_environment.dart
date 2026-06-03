import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppFlavor { development, staging, production }

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
      useMockData: true,
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
    return const AppEnvironment(
      flavor: AppFlavor.staging,
      apiBaseUrl: 'https://staging-api.miraguardian.com/api',
      useMockData: false,
    );
  }

  factory AppEnvironment.production() {
    return const AppEnvironment(
      flavor: AppFlavor.production,
      apiBaseUrl: 'https://api.miraguardian.com/api',
      useMockData: false,
    );
  }

  final AppFlavor flavor;
  final String apiBaseUrl;
  final bool useMockData;
}

final appEnvironmentProvider = Provider<AppEnvironment>((ref) {
  throw UnimplementedError('AppEnvironment must be provided at bootstrap.');
});
