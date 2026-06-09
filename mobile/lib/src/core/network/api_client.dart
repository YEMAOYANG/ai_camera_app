import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/core/storage/auth_session_store.dart';

final rawDioProvider = Provider<Dio>((ref) {
  return _buildDio(ref.watch(appEnvironmentProvider));
});

final dioProvider = Provider<Dio>((ref) {
  final environment = ref.watch(appEnvironmentProvider);
  final dio = _buildDio(environment);
  dio.interceptors.add(
    AuthTokenInterceptor(
      sessionStore: ref.watch(authSessionStoreProvider),
      refreshDio: ref.watch(rawDioProvider),
      dio: dio,
    ),
  );
  return dio;
});

Dio _buildDio(AppEnvironment environment) {
  return Dio(
    BaseOptions(
      baseUrl: environment.apiBaseUrl,
      connectTimeout: const Duration(seconds: 8),
      receiveTimeout: const Duration(seconds: 12),
      sendTimeout: const Duration(seconds: 8),
      headers: {'Accept': 'application/json'},
    ),
  );
}

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(ref.watch(dioProvider));
});

class ApiClient {
  const ApiClient(this._dio);

  final Dio _dio;

  Future<Response<dynamic>> get(
    String path, {
    Map<String, Object?>? queryParameters,
  }) {
    return _dio.get<dynamic>(path, queryParameters: queryParameters);
  }

  Future<Response<dynamic>> post(String path, {Object? data}) {
    return _dio.post<dynamic>(path, data: data);
  }

  Future<Response<dynamic>> patch(String path, {Object? data}) {
    return _dio.patch<dynamic>(path, data: data);
  }

  Future<Response<dynamic>> delete(String path, {Object? data}) {
    return _dio.delete<dynamic>(path, data: data);
  }
}

class AuthTokenInterceptor extends Interceptor {
  AuthTokenInterceptor({
    required AuthSessionStore sessionStore,
    required Dio refreshDio,
    required Dio dio,
  }) : _sessionStore = sessionStore,
       _refreshDio = refreshDio,
       _dio = dio;

  final AuthSessionStore _sessionStore;
  final Dio _refreshDio;
  final Dio _dio;
  Future<AuthSession?>? _refreshing;

  static const _retryKey = 'authRetry';

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    try {
      if (_isAuthPath(options.path)) {
        handler.next(options);
        return;
      }

      final session = await _sessionForRequest();
      if (session?.accessToken.isNotEmpty ?? false) {
        options.headers['Authorization'] = 'Bearer ${session!.accessToken}';
      }
      handler.next(options);
    } catch (_) {
      handler.next(options);
    }
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final request = err.requestOptions;
    final shouldRetry =
        err.response?.statusCode == 401 &&
        request.extra[_retryKey] != true &&
        !_isAuthPath(request.path);

    if (!shouldRetry) {
      handler.next(err);
      return;
    }

    final refreshed = await _refreshSession();
    if (refreshed == null) {
      handler.next(err);
      return;
    }

    try {
      final retryOptions = request
        ..extra[_retryKey] = true
        ..headers['Authorization'] = 'Bearer ${refreshed.accessToken}';
      handler.resolve(await _dio.fetch<dynamic>(retryOptions));
    } catch (_) {
      handler.next(err);
    }
  }

  Future<AuthSession?> _sessionForRequest() async {
    final session = _sessionStore.currentSession;
    if (session == null) return null;
    if (session.hasAccessToken) return session;
    if (!session.canRefresh) {
      await _sessionStore.clear();
      return null;
    }
    return _refreshSession();
  }

  Future<AuthSession?> _refreshSession() {
    final active = _refreshing;
    if (active != null) return active;

    final future = _doRefreshSession();
    _refreshing = future;
    return future.whenComplete(() => _refreshing = null);
  }

  Future<AuthSession?> _doRefreshSession() async {
    final session = _sessionStore.currentSession;
    if (session == null || !session.canRefresh) {
      await _sessionStore.clear();
      return null;
    }

    try {
      final response = await _refreshDio.post<dynamic>(
        '/auth/token/refresh',
        data: {
          'refreshToken': session.refreshToken,
          'clientDevice': _clientDevicePayload(),
        },
      );
      final refreshed = _parseRemoteSession(response.data);
      await _sessionStore.save(refreshed);
      return refreshed;
    } on DioException {
      await _sessionStore.clear();
      return null;
    }
  }

  AuthSession _parseRemoteSession(dynamic data) {
    final map = _asMap(data);
    final user = _asMap(map['user']);
    final tokens = _asMap(map['tokens']);
    return AuthSession(
      accessToken: _asString(tokens['accessToken']),
      refreshToken: _asString(tokens['refreshToken']),
      accessTokenExpiresAt: _asDateTime(tokens['accessTokenExpiresAt']),
      refreshTokenExpiresAt: _asDateTime(tokens['refreshTokenExpiresAt']),
      userId: _asString(user['id']),
      phone: _asString(user['phone']),
    );
  }

  bool _isAuthPath(String path) {
    return path.startsWith('/auth/sms/') ||
        path.startsWith('/auth/token/refresh') ||
        path.startsWith('/auth/logout');
  }
}

Map<String, String> _clientDevicePayload() {
  final platform = defaultTargetPlatform.name.toLowerCase();
  final isPhone =
      defaultTargetPlatform == TargetPlatform.iOS ||
      defaultTargetPlatform == TargetPlatform.android;
  final label = switch (defaultTargetPlatform) {
    TargetPlatform.iOS => '本机 iPhone',
    TargetPlatform.android => 'Android 手机',
    TargetPlatform.macOS => 'Mac 设备',
    TargetPlatform.windows => 'Windows 设备',
    TargetPlatform.linux => 'Linux 设备',
    TargetPlatform.fuchsia => '已登录设备',
  };
  return {
    'label': label,
    'type': isPhone ? 'phone' : 'desktop',
    'platform': platform,
  };
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String _asString(dynamic value) {
  return value is String ? value : '';
}

DateTime _asDateTime(dynamic value) {
  if (value is int) return DateTime.fromMillisecondsSinceEpoch(value);
  if (value is num) return DateTime.fromMillisecondsSinceEpoch(value.toInt());
  if (value is String) {
    final epoch = int.tryParse(value);
    if (epoch != null) return DateTime.fromMillisecondsSinceEpoch(epoch);
    final parsed = DateTime.tryParse(value);
    if (parsed != null) return parsed;
  }
  return DateTime.now();
}
