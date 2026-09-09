import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';

final studentAccessRepositoryProvider = Provider<StudentAccessRepository>((
  ref,
) {
  return StudentAccessRepository(apiClient: ref.watch(apiClientProvider));
});

class StudentAccessRepository {
  const StudentAccessRepository({required this.apiClient});

  final ApiClient apiClient;

  Future<StudentPairingCode> createPairingCode({
    required String childId,
    required String pin,
  }) async {
    try {
      final response = await apiClient.post(
        '/v2/parent/children/$childId/student-access/pairing-codes',
        data: {'pin': pin},
      );
      return StudentPairingCode.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(error);
    } on FormatException {
      throw const StudentAccessException('配对信息格式异常，请稍后重试。');
    }
  }

  Future<StudentQrChallenge> getQrChallenge({
    required String challengeId,
    required String childId,
  }) async {
    try {
      final response = await apiClient.get(
        '/v2/parent/student-access/qr-challenges/$challengeId',
        queryParameters: {'childId': childId},
      );
      final data = _asMap(response.data);
      final challenge = _asMap(data['challenge']);
      return StudentQrChallenge.fromJson(challenge.isEmpty ? data : challenge);
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(
        error,
        fallbackMessage: '暂时无法读取登录请求，请检查网络后重试。',
      );
    } on FormatException {
      throw const StudentAccessException('登录请求格式异常，请重新扫码。');
    }
  }

  Future<StudentQrApproval> approveQrChallenge({
    required String challengeId,
    required String childId,
    String? pin,
  }) async {
    try {
      final normalizedPin = pin?.trim() ?? '';
      final response = await apiClient.post(
        '/v2/parent/student-access/qr-challenges/$challengeId/approve',
        data: {
          'childId': childId,
          if (normalizedPin.isNotEmpty) 'pin': normalizedPin,
        },
      );
      return StudentQrApproval.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(
        error,
        fallbackMessage: '暂时无法确认登录，请检查网络后重试。',
      );
    } on FormatException {
      throw const StudentAccessException('登录确认结果异常，请重新扫码。');
    }
  }

  Future<StudentQrRejection> rejectQrChallenge({
    required String challengeId,
    required String childId,
  }) async {
    try {
      final response = await apiClient.post(
        '/v2/parent/student-access/qr-challenges/$challengeId/reject',
        data: {'childId': childId},
      );
      return StudentQrRejection.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(
        error,
        fallbackMessage: '暂时无法取消这次登录请求。',
      );
    } on FormatException {
      throw const StudentAccessException('取消登录结果异常。');
    }
  }

  Future<StudentAuthorizationList> listAuthorizations(String childId) async {
    try {
      final response = await apiClient.get(
        '/v2/parent/children/${Uri.encodeComponent(childId)}/student-access/authorizations',
      );
      return StudentAuthorizationList.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(
        error,
        fallbackMessage: '暂时无法读取已授权设备，请稍后重试。',
      );
    } on FormatException {
      throw const StudentAccessException('设备授权信息格式异常。');
    }
  }

  Future<StudentAuthorizationRevocation> revokeAuthorization({
    required String childId,
    required String authorizationId,
  }) async {
    try {
      final response = await apiClient.delete(
        '/v2/parent/children/${Uri.encodeComponent(childId)}/student-access/authorizations/${Uri.encodeComponent(authorizationId)}',
      );
      return StudentAuthorizationRevocation.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(
        error,
        fallbackMessage: '暂时无法撤销这台设备，请稍后重试。',
      );
    } on FormatException {
      throw const StudentAccessException('设备撤销结果异常。');
    }
  }

  Future<StudentPinResetResult> resetPin({
    required String childId,
    required String pin,
  }) async {
    try {
      final response = await apiClient.post(
        '/v2/parent/children/${Uri.encodeComponent(childId)}/student-access/pin/reset',
        data: {'pin': pin},
      );
      return StudentPinResetResult.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw StudentAccessException.fromDio(
        error,
        fallbackMessage: '暂时无法重置学习 PIN，请稍后重试。',
      );
    } on FormatException {
      throw const StudentAccessException('PIN 重置结果异常。');
    }
  }
}

class StudentAccessException implements Exception {
  const StudentAccessException(
    this.message, {
    this.code = 'student_access_error',
  });

  final String message;
  final String code;

  static StudentAccessException fromDio(
    DioException error, {
    String fallbackMessage = '暂时无法创建配对码，请检查网络后重试。',
  }) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.trim().isNotEmpty) {
        return StudentAccessException(
          message.trim(),
          code: code is String && code.isNotEmpty
              ? code
              : 'student_access_error',
        );
      }
    }
    return StudentAccessException(fallbackMessage);
  }

  @override
  String toString() => message;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
