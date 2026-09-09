import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';

final learningRepositoryProvider = Provider<LearningGateway>((ref) {
  return LearningRepository(apiClient: ref.watch(apiClientProvider));
});

final parentLearningReportsRepositoryProvider =
    Provider<ParentLearningReportsGateway>((ref) {
      return LearningRepository(apiClient: ref.watch(apiClientProvider));
    });

typedef LearningTodayRequestKey = ({String childId, String gradeCode});

final todayLearningProvider = FutureProvider.autoDispose
    .family<LearningToday, LearningTodayRequestKey>((ref, key) async {
      if (key.childId.trim().isEmpty || key.gradeCode.trim().isEmpty) {
        return const LearningToday(
          state: LearningTodayState.unavailable,
          message: '课程可用状态无效，请重新获取',
        );
      }

      final repository = ref.watch(learningRepositoryProvider);
      return repository.today(key.childId);
    });

final latestLearningReportProvider =
    FutureProvider.family<LearningReport?, String>((ref, childId) {
      return ref.watch(learningRepositoryProvider).latestReport(childId);
    });

abstract interface class LearningGateway {
  Future<LearningToday> today(String childId);

  Future<LearningReport?> latestReport(String childId, {String? subject});
}

abstract interface class ParentLearningReportsGateway {
  Future<LearningReportPage> reports({
    required String childId,
    String? subject,
    String? cursor,
    int limit = 20,
  });

  Future<LearningReport> reportDetail({
    required String childId,
    required String reportId,
  });
}

class LearningRepository
    implements LearningGateway, ParentLearningReportsGateway {
  const LearningRepository({required this._apiClient});

  final ApiClient _apiClient;

  @override
  Future<LearningToday> today(String childId) async {
    try {
      final response = await _apiClient.get(
        '/learning/overview',
        options: Options(receiveTimeout: const Duration(minutes: 3)),
        queryParameters: {
          'childId': childId,
          'date': DateFormat('yyyy-MM-dd').format(DateTime.now()),
        },
      );
      return LearningToday.fromJson(learningResponseMap(response.data));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  @override
  Future<LearningReport?> latestReport(
    String childId, {
    String? subject,
  }) async {
    try {
      final response = await _apiClient.get(
        '/learning/reports/latest',
        queryParameters: {
          'childId': childId,
          if (subject != null && subject.isNotEmpty) 'subject': subject,
        },
      );
      final root = learningResponseMap(response.data);
      final data = learningResponseMap(root['data']);
      final source = data.isEmpty ? root : data;
      final report = learningResponseMap(
        source['latestReport'] ?? source['report'],
      );
      if (report.isEmpty) return null;
      return LearningReport.fromJson(report);
    } on DioException catch (error) {
      if (error.response?.statusCode == 404) return null;
      throw _fromDio(error);
    }
  }

  @override
  Future<LearningReportPage> reports({
    required String childId,
    String? subject,
    String? cursor,
    int limit = 20,
  }) async {
    try {
      final response = await _apiClient.get(
        '/learning/reports',
        queryParameters: {
          'childId': childId,
          if (subject != null && subject.isNotEmpty) 'subject': subject,
          if (cursor != null && cursor.isNotEmpty) 'cursor': cursor,
          'limit': limit,
        },
      );
      return LearningReportPage.fromJson(learningResponseMap(response.data));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  @override
  Future<LearningReport> reportDetail({
    required String childId,
    required String reportId,
  }) async {
    try {
      final response = await _apiClient.get(
        '/learning/reports/${Uri.encodeComponent(reportId)}',
        queryParameters: {'childId': childId},
      );
      final root = learningResponseMap(response.data);
      final report = learningResponseMap(root['report']);
      if (report.isEmpty) {
        throw const FormatException('Missing learning report detail.');
      }
      return LearningReport.fromJson(report);
    } on DioException catch (error) {
      throw _fromDio(error);
    } on FormatException {
      throw const LearningException(
        '学习报告格式异常，请稍后重试',
        code: 'invalid_learning_report',
      );
    }
  }

  LearningException _fromDio(DioException error) {
    final data = learningResponseMap(error.response?.data);
    return LearningException(
      data['message']?.toString() ?? '学习服务暂时不可用，请稍后再试',
      code:
          data['code']?.toString() ??
          data['error']?.toString() ??
          'learning_error',
    );
  }
}

class LearningException implements Exception {
  const LearningException(this.message, {required this.code});

  final String message;
  final String code;

  @override
  String toString() => message;
}
