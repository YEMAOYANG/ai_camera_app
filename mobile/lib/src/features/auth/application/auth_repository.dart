import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/core/storage/auth_session_store.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
    environment: ref.watch(appEnvironmentProvider),
    dio: ref.watch(rawDioProvider),
    sessionStore: ref.watch(authSessionStoreProvider),
  );
});

class AuthException implements Exception {
  const AuthException(this.message, {this.code = 'auth_error'});

  final String message;
  final String code;
}

class AuthRepository {
  const AuthRepository({
    required AppEnvironment environment,
    required Dio dio,
    required AuthSessionStore sessionStore,
  }) : _environment = environment,
       _dio = dio,
       _sessionStore = sessionStore;

  final AppEnvironment _environment;
  final Dio _dio;
  final AuthSessionStore _sessionStore;

  Future<void> requestSmsCode(String phone) async {
    if (_environment.useMockData) {
      await Future<void>.delayed(const Duration(milliseconds: 120));
      return;
    }

    try {
      await _dio.post<dynamic>('/auth/sms/request', data: {'phone': phone});
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<AuthSession> loginWithSms({
    required String phone,
    required String code,
  }) async {
    if (_environment.useMockData) {
      await Future<void>.delayed(const Duration(milliseconds: 420));
      if (!RegExp(r'^\d{4,6}$').hasMatch(code.trim())) {
        throw const AuthException('验证码不正确，请重新输入', code: 'invalid_code');
      }
      final session = _mockSession(phone);
      await _sessionStore.save(session);
      return session;
    }

    try {
      final response = await _dio.post<dynamic>(
        '/auth/sms/login',
        data: {'phone': phone, 'code': code},
      );
      final session = _parseSession(response.data);
      await _sessionStore.save(session);
      return session;
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<AuthSession?> refreshSession() async {
    final session = _sessionStore.currentSession;
    if (session == null || !session.canRefresh) {
      await _sessionStore.clear();
      return null;
    }

    if (_environment.useMockData) {
      final refreshed = _mockSession(session.phone, userId: session.userId);
      await _sessionStore.save(refreshed);
      return refreshed;
    }

    try {
      final response = await _dio.post<dynamic>(
        '/auth/token/refresh',
        data: {'refreshToken': session.refreshToken},
      );
      final refreshed = _parseSession(response.data);
      await _sessionStore.save(refreshed);
      return refreshed;
    } on DioException {
      await _sessionStore.clear();
      return null;
    }
  }

  Future<void> logout() async {
    final session = _sessionStore.currentSession;
    if (session != null && !_environment.useMockData) {
      try {
        await _dio.post<dynamic>(
          '/auth/logout',
          data: {'refreshToken': session.refreshToken},
          options: Options(
            headers: {'Authorization': 'Bearer ${session.accessToken}'},
          ),
        );
      } on DioException {
        // Local logout should still complete even if the backend is unreachable.
      }
    }
    await _sessionStore.clear();
  }

  AuthSession _mockSession(String phone, {String? userId}) {
    final now = DateTime.now();
    final stamp = now.millisecondsSinceEpoch;
    return AuthSession(
      accessToken: 'mock_access_$stamp',
      refreshToken: 'mock_refresh_$stamp',
      accessTokenExpiresAt: now.add(const Duration(minutes: 15)),
      refreshTokenExpiresAt: now.add(const Duration(days: 30)),
      userId: userId ?? 'mock_parent_$phone',
      phone: phone,
    );
  }

  AuthSession _parseSession(dynamic data) {
    final map = _asMap(data);
    final tokens = _asMap(map['tokens']);
    final user = _asMap(map['user']);
    return AuthSession(
      accessToken: _asString(tokens['accessToken']),
      refreshToken: _asString(tokens['refreshToken']),
      accessTokenExpiresAt: _asDateTime(tokens['accessTokenExpiresAt']),
      refreshTokenExpiresAt: _asDateTime(tokens['refreshTokenExpiresAt']),
      userId: _asString(user['id']),
      phone: _asString(user['phone']),
    );
  }

  AuthException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return AuthException(
          message,
          code: code is String ? code : 'auth_error',
        );
      }
    }
    return const AuthException('网络异常，请稍后重试', code: 'network_error');
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
