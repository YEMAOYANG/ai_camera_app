import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/core/storage/auth_session_store.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
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
  const AuthRepository({required this._dio, required this._sessionStore});

  final Dio _dio;
  final AuthSessionStore _sessionStore;

  Future<void> requestSmsCode(String phone) async {
    try {
      await _dio.post<dynamic>('/auth/sms/request', data: {'phone': phone});
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<AuthLoginResult> loginWithSms({
    required String phone,
    required String code,
  }) async {
    try {
      final response = await _dio.post<dynamic>(
        '/auth/sms/login',
        data: {'phone': phone, 'code': code},
      );
      final session = _parseSession(response.data);
      await _sessionStore.save(session);
      return AuthLoginResult(
        session: session,
        pendingJoins: _parsePendingJoins(response.data),
      );
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
    if (session != null) {
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

  List<PendingFamilyJoin> _parsePendingJoins(dynamic data) {
    final raw = _asMap(data)['pendingJoins'];
    if (raw is! List) return const [];
    return raw.map((item) => PendingFamilyJoin.fromJson(_asMap(item))).toList();
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

class AuthLoginResult {
  const AuthLoginResult({required this.session, required this.pendingJoins});

  final AuthSession session;
  final List<PendingFamilyJoin> pendingJoins;
}

class PendingFamilyJoin {
  const PendingFamilyJoin({
    required this.id,
    required this.familyId,
    required this.familyName,
    required this.name,
    required this.phone,
    required this.role,
    required this.roleLabel,
    required this.status,
    this.expiresAt,
  });

  final String id;
  final String familyId;
  final String familyName;
  final String name;
  final String phone;
  final String role;
  final String roleLabel;
  final String status;
  final int? expiresAt;

  static PendingFamilyJoin fromJson(Map<String, dynamic> json) {
    return PendingFamilyJoin(
      id: _asString(json['id']),
      familyId: _asString(json['familyId']),
      familyName: _asString(json['familyName']),
      name: _asString(json['name']),
      phone: _asString(json['phone']),
      role: _asString(json['role']),
      roleLabel: _asString(json['roleLabel']),
      status: _asString(json['status']),
      expiresAt: _asNullableInt(json['expiresAt']),
    );
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

int? _asNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
