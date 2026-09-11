import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';

abstract interface class LearningAvailabilityGateway {
  Future<LearningAvailability> current(String childId);
}

final learningAvailabilityRepositoryProvider =
    Provider<LearningAvailabilityGateway>((ref) {
      return LearningAvailabilityRepository(
        apiClient: ref.watch(apiClientProvider),
      );
    });

final currentLearningAvailabilityProvider = FutureProvider.autoDispose
    .family<LearningAvailability, String>((ref, childId) {
      return ref.watch(learningAvailabilityRepositoryProvider).current(childId);
    });

class LearningAvailabilityRepository implements LearningAvailabilityGateway {
  const LearningAvailabilityRepository({required this.apiClient});

  final ApiClient apiClient;

  @override
  Future<LearningAvailability> current(String childId) async {
    final normalizedChildId = childId.trim();
    if (normalizedChildId.isEmpty) {
      throw const LearningAvailabilityException(
        code: 'invalid_child_id',
        message: '孩子资料无效，请重新同步',
        isTransportFailure: false,
      );
    }
    try {
      final response = await apiClient.get(
        '/learning/availability',
        queryParameters: {
          'childId': normalizedChildId,
          'includeWorkspaceAccess': 'true',
          'includeLearningState': 'true',
        },
      );
      return LearningAvailability.fromJson(response.data);
    } on DioException catch (error) {
      throw LearningAvailabilityException.fromDio(error);
    }
  }
}

class LearningAvailabilityException implements Exception {
  const LearningAvailabilityException({
    required this.code,
    required this.message,
    required this.isTransportFailure,
  });

  final String code;
  final String message;
  final bool isTransportFailure;

  factory LearningAvailabilityException.fromDio(DioException error) {
    final response = error.response;
    if (response == null) {
      return const LearningAvailabilityException(
        code: 'learning_availability_transport_error',
        message: '网络异常，请稍后重试',
        isTransportFailure: true,
      );
    }
    final data = response.data;
    if (data is Map) {
      final code = data['error'] ?? data['code'];
      final message = data['message'];
      return LearningAvailabilityException(
        code: code is String ? code : 'learning_availability_error',
        message: message is String ? message : '课程可用状态获取失败，请稍后重试',
        isTransportFailure: false,
      );
    }
    return const LearningAvailabilityException(
      code: 'learning_availability_error',
      message: '课程可用状态获取失败，请稍后重试',
      isTransportFailure: false,
    );
  }

  @override
  String toString() => message;
}
