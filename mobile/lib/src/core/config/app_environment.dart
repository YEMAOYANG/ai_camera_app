import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';

enum AppFlavor { development, staging, production, test }

class AppEnvironment {
  const AppEnvironment({
    required this.flavor,
    required this.apiBaseUrl,
    this.taskWebSocketBaseUrl = '',
  });

  static Future<AppEnvironment> load() async {
    // Debug/Profile builds should read the bundled env file. Xcode runs do not
    // pass --dart-define-from-file, but ios/Flutter/Generated.xcconfig can keep
    // stale release DART_DEFINES and point the app at production URLs.
    if (!kReleaseMode) {
      return _loadFromBundledAsset(_flavorFromDartDefineOrBuildMode());
    }

    final fromDefines = _fromOptionalDartDefines();
    if (fromDefines != null) return fromDefines;

    return _loadFromBundledAsset(AppFlavor.production);
  }

  static Future<AppEnvironment> _loadFromBundledAsset(AppFlavor fileFlavor) async {
    final assetPath = _envAssetPathFor(fileFlavor);
    final values = _parseEnvFile(await rootBundle.loadString(assetPath));
    final flavor = _flavorFromName(values['APP_FLAVOR']) ?? fileFlavor;
    return AppEnvironment(
      flavor: flavor,
      apiBaseUrl: _requiredUrlFromValues(
        values,
        'API_BASE_URL',
        flavor,
        assetPath,
        validSchemes: const {'http', 'https'},
      ),
      taskWebSocketBaseUrl: _requiredUrlFromValues(
        values,
        'TASK_WS_BASE_URL',
        flavor,
        assetPath,
        validSchemes: const {'ws', 'wss'},
      ),
    );
  }

  factory AppEnvironment.staging() {
    return _fromRequiredDartDefines(AppFlavor.staging);
  }

  factory AppEnvironment.production() {
    return _fromRequiredDartDefines(AppFlavor.production);
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
    final apiBaseUrl = _requiredApiBaseUrl(definedApiBaseUrl, flavor);
    final taskWebSocketBaseUrl = _requiredTaskWebSocketBaseUrl(
      taskWsBaseUrl,
      flavor,
    );
    return AppEnvironment(
      flavor: flavor,
      apiBaseUrl: apiBaseUrl,
      taskWebSocketBaseUrl: taskWebSocketBaseUrl,
    );
  }

  final AppFlavor flavor;
  final String apiBaseUrl;
  final String taskWebSocketBaseUrl;
}

AppEnvironment? _fromOptionalDartDefines() {
  const definedApiBaseUrl = String.fromEnvironment('API_BASE_URL');
  const taskWsBaseUrl = String.fromEnvironment('TASK_WS_BASE_URL');
  if (definedApiBaseUrl.trim().isEmpty && taskWsBaseUrl.trim().isEmpty) {
    return null;
  }
  final flavor = _flavorFromDartDefineOrBuildMode();
  return AppEnvironment(
    flavor: flavor,
    apiBaseUrl: _requiredApiBaseUrl(definedApiBaseUrl, flavor),
    taskWebSocketBaseUrl: _requiredTaskWebSocketBaseUrl(taskWsBaseUrl, flavor),
  );
}

AppEnvironment _fromRequiredDartDefines(AppFlavor flavor) {
  const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  const taskWsBaseUrl = String.fromEnvironment('TASK_WS_BASE_URL');
  return AppEnvironment(
    flavor: flavor,
    apiBaseUrl: _requiredApiBaseUrl(apiBaseUrl, flavor),
    taskWebSocketBaseUrl: _requiredTaskWebSocketBaseUrl(taskWsBaseUrl, flavor),
  );
}

String _requiredApiBaseUrl(String value, AppFlavor flavor) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) {
    throw UnsupportedError(
      'API_BASE_URL is required for $flavor. Run with '
      '--dart-define-from-file=.env.development for development or '
      '--dart-define-from-file=.env.product for production.',
    );
  }
  final uri = Uri.tryParse(trimmed);
  if (uri == null ||
      uri.host.isEmpty ||
      (uri.scheme != 'http' && uri.scheme != 'https')) {
    throw UnsupportedError('API_BASE_URL must be an http(s) URL for $flavor.');
  }
  return trimmed;
}

String _requiredTaskWebSocketBaseUrl(String value, AppFlavor flavor) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) {
    throw UnsupportedError(
      'TASK_WS_BASE_URL is required for $flavor. Run with '
      '--dart-define-from-file=.env.development for development or '
      '--dart-define-from-file=.env.product for production.',
    );
  }
  final uri = Uri.tryParse(trimmed);
  if (uri == null ||
      uri.host.isEmpty ||
      (uri.scheme != 'ws' && uri.scheme != 'wss')) {
    throw UnsupportedError('TASK_WS_BASE_URL must be a ws(s) URL for $flavor.');
  }
  return trimmed;
}

AppFlavor _flavorFromDartDefineOrBuildMode() {
  const flavorName = String.fromEnvironment('APP_FLAVOR');
  return _flavorFromName(flavorName) ??
      (kReleaseMode ? AppFlavor.production : AppFlavor.development);
}

AppFlavor? _flavorFromName(String? value) {
  return switch (value?.trim().toLowerCase()) {
    'development' => AppFlavor.development,
    'staging' => AppFlavor.staging,
    'production' => AppFlavor.production,
    'test' => AppFlavor.test,
    _ => null,
  };
}

String _envAssetPathFor(AppFlavor flavor) {
  return switch (flavor) {
    AppFlavor.production => '.env.product',
    AppFlavor.development || AppFlavor.test => '.env.development',
    AppFlavor.staging => throw UnsupportedError(
      'No bundled env file is configured for $flavor. Use '
      '--dart-define-from-file with a staging env file.',
    ),
  };
}

Map<String, String> _parseEnvFile(String source) {
  final values = <String, String>{};
  for (final line in source.split('\n')) {
    final trimmed = line.trim();
    if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
    final separator = trimmed.indexOf('=');
    if (separator <= 0) continue;
    final key = trimmed.substring(0, separator).trim();
    var value = trimmed.substring(separator + 1).trim();
    if (value.length >= 2 &&
        ((value.startsWith('"') && value.endsWith('"')) ||
            (value.startsWith("'") && value.endsWith("'")))) {
      value = value.substring(1, value.length - 1);
    }
    values[key] = value;
  }
  return values;
}

String _requiredUrlFromValues(
  Map<String, String> values,
  String key,
  AppFlavor flavor,
  String assetPath, {
  required Set<String> validSchemes,
}) {
  final value = values[key]?.trim() ?? '';
  if (value.isEmpty) {
    throw UnsupportedError('$key is required in $assetPath for $flavor.');
  }
  final uri = Uri.tryParse(value);
  if (uri == null || uri.host.isEmpty || !validSchemes.contains(uri.scheme)) {
    throw UnsupportedError(
      '$key in $assetPath must use one of these URL schemes: '
      '${validSchemes.join(', ')}.',
    );
  }
  return value;
}

final appEnvironmentProvider = Provider<AppEnvironment>((ref) {
  throw UnimplementedError('AppEnvironment must be provided at bootstrap.');
});
