import 'dart:math';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import '../domain/learning_review_models.dart';

String learningRequestId() => List.generate(
  16,
  (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
).join();
String learningError(Object error) {
  if (error is DioException) {
    final data = jsonMap(error.response?.data);
    if (data['message'] is String) return data['message'] as String;
    if (error.response?.statusCode == 403) return '当前身份没有操作权限，请联系家庭管理员。';
    return '连接暂时中断，已保存的记录仍会保留，请重新加载。';
  }
  return '暂时无法完成，请稍后重试。';
}

final learningReviewRepositoryProvider = Provider(
  (ref) => LearningReviewRepository(ref.watch(apiClientProvider)),
);
final reviewListProvider = FutureProvider.autoDispose
    .family<List<ReviewRun>, String>(
      (ref, id) => ref.watch(learningReviewRepositoryProvider).list(id),
    );
final reviewPreferencesProvider = FutureProvider.autoDispose
    .family<ReviewPreferences, String>(
      (ref, id) => ref.watch(learningReviewRepositoryProvider).preferences(id),
    );
final learningWeaknessesProvider = FutureProvider.autoDispose
    .family<List<LearningWeakness>, String>(
      (ref, id) => ref.watch(learningReviewRepositoryProvider).weaknesses(id),
    );
final reviewDetailProvider = FutureProvider.autoDispose
    .family<ReviewDetail, ({String childId, String reviewId})>(
      (ref, key) => ref
          .watch(learningReviewRepositoryProvider)
          .detail(key.childId, key.reviewId),
    );

class LearningReviewRepository {
  const LearningReviewRepository(this.api);
  final ApiClient api;
  Future<List<ReviewRun>> list(String childId) async => jsonList(
    jsonMap(
      (await api.get(
        '/learning/reviews',
        queryParameters: {'childId': childId},
      )).data,
    )['reviews'],
  ).map(ReviewRun.new).toList();
  Future<List<LearningWeakness>> weaknesses(String childId) async => jsonList(
    jsonMap(
      (await api.get(
        '/reports/learning/weaknesses',
        queryParameters: {'childId': childId},
      )).data,
    )['weaknesses'],
  ).map(LearningWeakness.new).toList();
  Future<ReviewDetail> detail(String childId, String reviewId) async =>
      ReviewDetail(
        jsonMap(
          (await api.get(
            '/learning/reviews/${Uri.encodeComponent(reviewId)}',
            queryParameters: {'childId': childId},
          )).data,
        ),
      );
  Future<ReviewPreferences> preferences(String childId) async =>
      ReviewPreferences(
        jsonMap(
          jsonMap(
            (await api.get(
              '/children/${Uri.encodeComponent(childId)}/review-preferences',
            )).data,
          )['preferences'],
        ),
      );
  Future<ReviewPreferences> savePreferences(
    String childId,
    Json values,
  ) async => ReviewPreferences(
    jsonMap(
      jsonMap(
        (await api.put(
          '/children/${Uri.encodeComponent(childId)}/review-preferences',
          data: values,
        )).data,
      )['preferences'],
    ),
  );
  Future<void> schedule(
    String childId,
    ReviewRun run,
    String action, {
    DateTime? scheduledAt,
    required String requestId,
  }) async {
    await api.post(
      '/learning/reviews/${Uri.encodeComponent(run.id)}/schedule-actions',
      data: {
        'childId': childId,
        'action': action,
        'appointmentRevision': run.appointmentRevision,
        'requestId': requestId,
        if (scheduledAt != null)
          'scheduledAt': scheduledAt.millisecondsSinceEpoch,
      },
    );
  }
}
