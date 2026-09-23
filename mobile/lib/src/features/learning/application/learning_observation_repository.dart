import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/domain/learning_observation_models.dart';

abstract interface class ParentObservationGateway {
  Future<List<ParentObservationLesson>> pending(String childId);
  Future<void> confirm({
    required String childId,
    required ParentObservationLesson lesson,
    required bool confirmed,
  });
}

final parentObservationRepositoryProvider = Provider<ParentObservationGateway>((
  ref,
) {
  return ParentObservationRepository(apiClient: ref.watch(apiClientProvider));
});

final pendingLearningObservationsProvider = FutureProvider.autoDispose
    .family<List<ParentObservationLesson>, String>((ref, childId) {
      return ref.watch(parentObservationRepositoryProvider).pending(childId);
    });

class ParentObservationRepository implements ParentObservationGateway {
  const ParentObservationRepository({required this.apiClient});
  final ApiClient apiClient;

  @override
  Future<List<ParentObservationLesson>> pending(String childId) async {
    if (childId.trim().isEmpty) {
      throw const ParentObservationException('请先选择孩子');
    }
    try {
      final groups = await Future.wait([
        for (final subject in ['chinese', 'math', 'english'])
          apiClient
              .get(
                '/learning/path',
                queryParameters: {'childId': childId, 'subject': subject},
              )
              .then(
                (response) => ParentObservationLesson.fromPath(
                  response.data,
                  subject: subject,
                ),
              ),
      ]);
      return [for (final group in groups) ...group];
    } on DioException catch (error) {
      throw ParentObservationException.fromDio(error);
    } on FormatException catch (error) {
      throw ParentObservationException(error.message);
    }
  }

  @override
  Future<void> confirm({
    required String childId,
    required ParentObservationLesson lesson,
    required bool confirmed,
  }) async {
    try {
      // The shared parent ApiClient owns authentication. The opaque server id
      // stays the same on a retry, so a network retry cannot add another record.
      final response = await apiClient.post(
        '/learning/path/observations',
        data: {
          'childId': childId,
          'lessonId': lesson.lessonId,
          'confirmationId': lesson.confirmationId,
          'confirmed': confirmed,
        },
      );
      if (response.data is! Map || response.data['ok'] != true) {
        throw const ParentObservationException('确认结果暂时未返回，请刷新后查看');
      }
    } on DioException catch (error) {
      throw ParentObservationException.fromDio(error);
    }
  }
}

class ParentObservationException implements Exception {
  const ParentObservationException(this.message);
  final String message;

  factory ParentObservationException.fromDio(DioException error) {
    if (error.response?.statusCode == 401 ||
        error.response?.statusCode == 403) {
      return const ParentObservationException('请使用家长身份登录后确认');
    }
    if (error.response?.statusCode == 409) {
      return const ParentObservationException('这节课的确认状态已变化，请刷新后再查看');
    }
    return const ParentObservationException('暂时没有连接上，请稍后重试');
  }

  @override
  String toString() => message;
}
