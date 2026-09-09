import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';

void main() {
  test(
    'parent repository uses read-only learning API request contract',
    () async {
      final recorder = _LearningContractInterceptor();
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
        ..interceptors.add(recorder);
      final repository = LearningRepository(apiClient: ApiClient(dio));

      await repository.today('child-1');
      await repository.latestReport('child-1');

      expect(recorder.requests, hasLength(2));
      expect(recorder.requests[0].path, '/learning/overview');
      expect(recorder.requests[0].queryParameters['childId'], 'child-1');
      expect(recorder.requests[0].queryParameters['date'], isNotEmpty);
      expect(
        recorder.requests[0].headers,
        isNot(contains('X-Mira-Preparation-Schema')),
      );
      expect(recorder.requests[1].path, '/learning/reports/latest');
      expect(recorder.requests[1].queryParameters, {'childId': 'child-1'});
    },
  );

  test(
    'parent today provider keeps a ready recommendation read-only for Student Web',
    () async {
      final recorder = _LearningContractInterceptor();
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
        ..interceptors.add(recorder);
      final repository = LearningRepository(apiClient: ApiClient(dio));
      final container = ProviderContainer(
        overrides: [learningRepositoryProvider.overrideWithValue(repository)],
      );
      addTearDown(container.dispose);
      final provider = todayLearningProvider((
        childId: 'child-auto',
        gradeCode: 'primary_1',
      ));
      final subscription = container.listen(provider, (_, _) {});
      addTearDown(subscription.close);

      final first = await container.read(provider.future);
      final cached = await container.read(provider.future);

      expect(first.state, LearningTodayState.recommended);
      expect(cached.state, LearningTodayState.recommended);
      expect(recorder.requests, hasLength(1));
      expect(recorder.requests[0].path, '/learning/overview');
    },
  );

  test(
    'same child with two grade codes issues independent Today requests',
    () async {
      final gateway = _CountingLearningGateway();
      final container = ProviderContainer(
        overrides: [learningRepositoryProvider.overrideWithValue(gateway)],
      );
      addTearDown(container.dispose);

      await container.read(
        todayLearningProvider((
          childId: 'child-auto',
          gradeCode: 'primary_1',
        )).future,
      );
      await container.read(
        todayLearningProvider((
          childId: 'child-auto',
          gradeCode: 'primary_2',
        )).future,
      );

      expect(gateway.todayCalls, 2);
    },
  );

  test('Today does not depend on a preparation plan state', () async {
    final learning = _CountingLearningGateway();
    final container = ProviderContainer(
      overrides: [learningRepositoryProvider.overrideWithValue(learning)],
    );
    addTearDown(container.dispose);

    await container.read(
      todayLearningProvider((
        childId: 'child-auto',
        gradeCode: 'primary_1',
      )).future,
    );

    expect(learning.todayCalls, 1);
  });
}

class _CountingLearningGateway implements LearningGateway {
  var todayCalls = 0;

  @override
  Future<LearningToday> today(String childId) async {
    todayCalls += 1;
    return const LearningToday(state: LearningTodayState.unavailable);
  }

  @override
  Future<LearningReport?> latestReport(String childId, {String? subject}) =>
      throw UnimplementedError();
}

class _LearningContractInterceptor extends Interceptor {
  final requests = <RequestOptions>[];

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    requests.add(options);
    final data = switch (options.path) {
      '/learning/overview' => {
        'ok': true,
        'recommendation': {
          'courseId': 'course-1',
          'title': '今日课程',
          'objective': '完成能力巩固',
        },
        'task': null,
        'session': null,
        'latestReport': null,
      },
      '/learning/reports/latest' => {
        'ok': true,
        'report': {
          'id': 'report-1',
          'summary': '完成',
          'correctCount': 1,
          'totalQuestions': 1,
        },
      },
      _ => <String, dynamic>{},
    };
    handler.resolve(
      Response<dynamic>(requestOptions: options, statusCode: 200, data: data),
    );
  }
}
