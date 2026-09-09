import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';

abstract interface class LearningPreparationGateway {
  Future<LearningPreparation?> current(String childId);

  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  });
}

abstract interface class LearningPreparationStateGateway {
  Future<LearningPreparationCurrentState> currentState(String childId);
}

final Provider<LearningPreparationGateway>
learningPreparationRepositoryProvider = Provider<LearningPreparationGateway>((
  ref,
) {
  return LearningPreparationRepository(apiClient: ref.watch(apiClientProvider));
});

final currentLearningPreparationProvider = FutureProvider.autoDispose
    .family<LearningPreparation?, String>(
      (ref, childId) =>
          ref.watch(learningPreparationRepositoryProvider).current(childId),
    );

final currentLearningPreparationStateProvider = FutureProvider.autoDispose
    .family<LearningPreparationCurrentState, String>((ref, childId) async {
      final gateway = ref.watch(learningPreparationRepositoryProvider);
      if (gateway is LearningPreparationStateGateway) {
        return (gateway as LearningPreparationStateGateway).currentState(
          childId,
        );
      }
      final preparation = await gateway.current(childId);
      return LearningPreparationCurrentState.fromPreparation(preparation);
    });

class LearningPreparationRepository
    implements LearningPreparationGateway, LearningPreparationStateGateway {
  const LearningPreparationRepository({required ApiClient apiClient})
    : this._(apiClient);

  const LearningPreparationRepository._(this._apiClient);

  final ApiClient _apiClient;

  static const _v2Headers = <String, String>{
    'X-Mira-Preparation-Schema': LearningPreparation.schemaV2,
  };

  @override
  Future<LearningPreparation?> current(String childId) async {
    return (await currentState(childId)).preparation;
  }

  @override
  Future<LearningPreparationCurrentState> currentState(String childId) async {
    try {
      final response = await _apiClient.get(
        '/learning/preparations/current',
        queryParameters: {'childId': childId},
        options: Options(headers: _v2Headers),
      );
      final state = _parseEnvelope(response.data);
      final preparation = state.preparation;
      if (preparation != null && preparation.childId != childId) {
        throw const LearningPreparationFormatException(
          'preparation childId does not match the request',
        );
      }
      return state;
    } on DioException catch (error) {
      throw LearningPreparationException.fromDio(error);
    }
  }

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) async {
    try {
      final response = await _apiClient.post(
        '/learning/preparations/${Uri.encodeComponent(planId)}/retry',
        data: {'requestId': requestId},
        options: Options(headers: _v2Headers),
      );
      final state = _parseEnvelope(response.data);
      final preparation = state.preparation;
      if (preparation == null) {
        throw const LearningPreparationFormatException(
          'retry response preparation must not be null',
        );
      }
      return preparation;
    } on DioException catch (error) {
      throw LearningPreparationException.fromDio(error);
    }
  }
}

class LearningPreparationException implements Exception {
  const LearningPreparationException({
    required this.code,
    required this.message,
    required this.isTransportFailure,
  });

  final String code;
  final String message;
  final bool isTransportFailure;

  factory LearningPreparationException.fromDio(DioException error) {
    final response = error.response;
    if (response == null) {
      return const LearningPreparationException(
        code: 'learning_preparation_transport_error',
        message: '网络异常，请稍后重试',
        isTransportFailure: true,
      );
    }

    final data = response.data;
    if (data is Map) {
      final code = data['error'] ?? data['code'];
      final message = data['message'];
      return LearningPreparationException(
        code: code is String ? code : 'learning_preparation_error',
        message: message is String ? message : '课程准备状态获取失败，请稍后重试',
        isTransportFailure: false,
      );
    }
    return const LearningPreparationException(
      code: 'learning_preparation_error',
      message: '课程准备状态获取失败，请稍后重试',
      isTransportFailure: false,
    );
  }

  @override
  String toString() => message;
}

LearningPreparationCurrentState _parseEnvelope(Object? value) =>
    LearningPreparationCurrentState.fromJson(value);
