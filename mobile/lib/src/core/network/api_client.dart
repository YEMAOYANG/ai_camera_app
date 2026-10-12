import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/platform/client_device_info.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';

final rawDioProvider = Provider<Dio>((ref) {
  final dio = _buildDio(ref.watch(appEnvironmentProvider));
  dio.interceptors.add(
    ClientDeviceHeaderInterceptor(
      loadDeviceInfo: () => ref.read(clientDeviceInfoProvider.future),
    ),
  );
  return dio;
});

final dioProvider = Provider<Dio>((ref) {
  final environment = ref.watch(appEnvironmentProvider);
  final dio = _buildDio(environment);
  dio.interceptors.add(
    ClientDeviceHeaderInterceptor(
      loadDeviceInfo: () => ref.read(clientDeviceInfoProvider.future),
    ),
  );
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
    Options? options,
  }) {
    return _dio.get<dynamic>(
      path,
      queryParameters: queryParameters,
      options: options,
    );
  }

  Future<Response<dynamic>> post(
    String path, {
    Object? data,
    Map<String, Object?>? queryParameters,
    Options? options,
  }) {
    return _dio.post<dynamic>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
    );
  }

  Future<Response<dynamic>> patch(String path, {Object? data}) {
    return _dio.patch<dynamic>(path, data: data);
  }

  Future<Response<dynamic>> put(String path, {Object? data}) {
    return _dio.put<dynamic>(path, data: data);
  }

  Future<Response<dynamic>> delete(String path, {Object? data}) {
    return _dio.delete<dynamic>(path, data: data);
  }
}

class ClientDeviceHeaderInterceptor extends Interceptor {
  ClientDeviceHeaderInterceptor({required this._loadDeviceInfo});

  final Future<ClientDeviceInfo> Function() _loadDeviceInfo;
  ClientDeviceInfo? _cachedInfo;
  Future<void>? _warmUp;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final cached = _cachedInfo;
    if (cached != null) {
      options.headers.addAll(cached.headers);
      handler.next(options);
      return;
    }

    // Never block API calls while device metadata loads on first launch.
    handler.next(options);
    _warmUp ??= _loadDeviceInfo()
        .timeout(const Duration(seconds: 2))
        .then((info) {
          _cachedInfo = info;
        })
        .catchError((_) {});
  }
}

class AuthTokenInterceptor extends Interceptor {
  AuthTokenInterceptor({
    required this._sessionStore,
    required this._refreshDio,
    required this._dio,
  });

  final AuthSessionStore _sessionStore;
  final Dio _refreshDio;
  final Dio _dio;
  static const _retryKey = 'authRetry';
  static const _generationKey = 'authSessionGeneration';

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
      if (_isPublicPath(options.path)) {
        handler.next(options);
        return;
      }

      final generation = _sessionStore.generation;
      final requestGeneration = options.extra[_generationKey];
      if (requestGeneration != null && requestGeneration != generation) {
        _rejectMissingSession(options, handler);
        return;
      }
      options.extra[_generationKey] = generation;
      final session = await _sessionForRequest();
      if (session == null || !_sessionStore.isCurrent(session, generation)) {
        _rejectMissingSession(options, handler);
        return;
      }
      if (session.accessToken.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer ${session.accessToken}';
      }
      handler.next(options);
    } on DioException catch (error) {
      handler.reject(error.copyWith(requestOptions: options));
    } catch (error, stackTrace) {
      handler.reject(_sessionFailure(options, error, stackTrace));
    }
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final request = err.requestOptions;
    final shouldRetry =
        err.response?.statusCode == 401 &&
        request.extra[_retryKey] != true &&
        request.extra[_generationKey] == _sessionStore.generation &&
        !_isAuthPath(request.path);

    if (!shouldRetry) {
      handler.next(err);
      return;
    }

    final generation = _sessionStore.generation;
    final current = _sessionStore.currentSession;
    final AuthSession? refreshed;
    try {
      refreshed =
          current != null &&
              current.hasAccessToken &&
              request.headers['Authorization'] !=
                  'Bearer ${current.accessToken}'
          ? current
          : await _refreshSession();
    } on DioException catch (error) {
      handler.next(error.copyWith(requestOptions: request));
      return;
    } catch (error, stackTrace) {
      handler.next(_sessionFailure(request, error, stackTrace));
      return;
    }
    if (refreshed == null || !_sessionStore.isCurrent(refreshed, generation)) {
      handler.next(err);
      return;
    }

    try {
      // Multipart streams have been finalized by the first request. Clone the
      // body for the single authenticated retry; the upload key stays intact.
      if (request.data is FormData) {
        request.data = (request.data as FormData).clone();
      }
      final retryOptions = request
        ..extra[_retryKey] = true
        ..headers['Authorization'] = 'Bearer ${refreshed.accessToken}';
      handler.resolve(await _dio.fetch<dynamic>(retryOptions));
    } on DioException catch (error) {
      handler.next(error);
    } catch (error, stackTrace) {
      handler.next(_sessionFailure(request, error, stackTrace));
    }
  }

  Future<AuthSession?> _sessionForRequest() async {
    final session = _sessionStore.currentSession;
    if (session == null) return null;
    if (session.hasAccessToken) return session;
    if (!session.canRefresh) {
      await _sessionStore.clearIfCurrent(session, _sessionStore.generation);
      return null;
    }
    return _refreshSession();
  }

  Future<AuthSession?> _refreshSession() async {
    final session = _sessionStore.currentSession;
    if (session == null) return null;
    final generation = _sessionStore.generation;
    if (!session.canRefresh) {
      await _sessionStore.clearIfCurrent(session, generation);
      return null;
    }

    try {
      return await _sessionStore.refreshSession(
        load: (session) async {
          final response = await _refreshDio.post<dynamic>(
            '/auth/token/refresh',
            data: {'refreshToken': session.refreshToken},
          );
          return _parseRemoteSession(response.data);
        },
        discard: (session) => revokeRemoteAuthSession(_refreshDio, session),
      );
    } on DioException catch (error) {
      if (error.response?.statusCode == 401 ||
          error.response?.statusCode == 403) {
        await _sessionStore.clearIfCurrent(session, generation);
        return null;
      }
      rethrow;
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

  bool _isPublicPath(String path) {
    return path.startsWith('/legal/') || path.startsWith('/app/about');
  }

  DioException _sessionFailure(
    RequestOptions request,
    Object error,
    StackTrace stackTrace,
  ) => DioException(
    requestOptions: request,
    type: DioExceptionType.unknown,
    error: error,
    stackTrace: stackTrace,
    message: '登录状态暂时无法更新，请稍后重试。',
  );

  void _rejectMissingSession(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) {
    handler.reject(
      DioException(
        requestOptions: options,
        response: Response<dynamic>(
          requestOptions: options,
          statusCode: 401,
          data: const {'error': 'auth_session_missing', 'message': '请先登录'},
        ),
        type: DioExceptionType.badResponse,
      ),
    );
  }
}

Future<void> revokeRemoteAuthSession(Dio dio, AuthSession session) async {
  try {
    await dio.post<dynamic>(
      '/auth/logout',
      data: {'refreshToken': session.refreshToken},
      options: Options(
        headers: {'Authorization': 'Bearer ${session.accessToken}'},
      ),
    );
  } on DioException {
    // Local logout must still complete when the server is unreachable.
  }
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
