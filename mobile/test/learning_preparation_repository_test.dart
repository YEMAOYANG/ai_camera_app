import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';

void main() {
  test(
    'repository provider exposes the gateway interface for fake overrides',
    () {
      final Provider<LearningPreparationGateway> provider =
          learningPreparationRepositoryProvider;
      expect(provider, same(learningPreparationRepositoryProvider));
    },
  );

  test(
    'current uses query parameters and requires matching child provenance',
    () async {
      final recorder = _PreparationRecorder((options) {
        return _response(options, {
          'ok': true,
          'preparation': _payload(childId: ' child / 1 '),
        });
      });
      final repository = _repository(recorder);

      final result = await repository.current(' child / 1 ');

      expect(result?.childId, ' child / 1 ');
      expect(recorder.requests.single.method, 'GET');
      expect(recorder.requests.single.path, '/learning/preparations/current');
      expect(recorder.requests.single.queryParameters, {
        'childId': ' child / 1 ',
      });
      expect(
        recorder.requests.single.headers['X-Mira-Preparation-Schema'],
        'mira.learning.preparation.v2',
      );

      recorder.handler = (options) => _response(options, {
        'ok': true,
        'preparation': _payload(childId: 'another-child'),
      });
      await expectLater(
        repository.current('child-1'),
        throwsA(isA<LearningPreparationFormatException>()),
      );
    },
  );

  test(
    'current state preserves primary_2 unavailable availability without error',
    () async {
      final recorder = _PreparationRecorder(
        (options) => _response(options, {
          'ok': true,
          'preparation': null,
          'learningPreparationAvailability': const {
            'status': 'unavailable',
            'gradeCode': 'primary_2',
            'message': '该年级正式课程尚未开放',
          },
        }),
      );
      final repository = _repository(recorder);

      final state = await repository.currentState('child-2');

      expect(state.preparation, isNull);
      expect(state.learningPreparationAvailability?.gradeCode, 'primary_2');
      expect(state.learningPreparationAvailability?.message, '该年级正式课程尚未开放');
      expect(await repository.current('child-2'), isNull);
    },
  );

  test(
    'current state provider remains compatible with legacy gateways',
    () async {
      final preparation = LearningPreparation.fromJson(_payload());
      final container = ProviderContainer(
        overrides: [
          learningPreparationRepositoryProvider.overrideWithValue(
            _LegacyPreparationGateway(preparation),
          ),
        ],
      );
      addTearDown(container.dispose);

      final state = await container.read(
        currentLearningPreparationStateProvider('child-1').future,
      );

      expect(state.preparation, same(preparation));
      expect(state.learningPreparationAvailability, isNull);
    },
  );

  test(
    'current state provider retains availability from state gateways',
    () async {
      final recorder = _PreparationRecorder(
        (options) => _response(options, {
          'ok': true,
          'preparation': null,
          'learningPreparationAvailability': const {
            'status': 'unavailable',
            'gradeCode': 'primary_6',
            'message': '六年级正式课程尚未开放',
          },
        }),
      );
      final container = ProviderContainer(
        overrides: [
          learningPreparationRepositoryProvider.overrideWithValue(
            _repository(recorder),
          ),
        ],
      );
      addTearDown(container.dispose);

      final state = await container.read(
        currentLearningPreparationStateProvider('child-6').future,
      );

      expect(state.preparation, isNull);
      expect(state.learningPreparationAvailability?.gradeCode, 'primary_6');
      expect(state.learningPreparationAvailability?.message, '六年级正式课程尚未开放');
      expect(recorder.requests, hasLength(1));
    },
  );

  test('only an explicit preparation null envelope returns null', () async {
    final recorder = _PreparationRecorder(
      (options) => _response(options, {'ok': true, 'preparation': null}),
    );
    final repository = _repository(recorder);

    expect(await repository.current('child-1'), isNull);

    for (final body in <Object?>[
      null,
      [],
      {'ok': true},
      {'preparation': null},
      {'ok': false, 'preparation': null},
      {'ok': true, 'preparation': null, 'extra': true},
      {'ok': true, 'preparation': []},
      {
        'ok': true,
        'preparation': {'schemaVersion': 'wrong'},
      },
    ]) {
      recorder.handler = (options) => _response(options, body);
      await expectLater(
        repository.current('child-1'),
        throwsA(isA<LearningPreparationFormatException>()),
        reason: body.toString(),
      );
    }
  });

  test(
    'retry encodes the plan path and posts the exact untrimmed body',
    () async {
      final recorder = _PreparationRecorder((options) {
        return _response(options, {
          'ok': true,
          'preparation': _payload(
            id: 'successor',
            status: 'queued',
            stage: 'queued',
          ),
        });
      });
      final repository = _repository(recorder);

      final result = await repository.retry(
        planId: ' plan/one?#% ',
        requestId: ' request-id ',
      );

      expect(result.id, 'successor');
      expect(recorder.requests.single.method, 'POST');
      expect(
        recorder.requests.single.path,
        '/learning/preparations/%20plan%2Fone%3F%23%25%20/retry',
      );
      expect(recorder.requests.single.data, {'requestId': ' request-id '});
      expect(
        recorder.requests.single.headers['X-Mira-Preparation-Schema'],
        'mira.learning.preparation.v2',
      );
    },
  );

  test('v2 negotiation is local to current and retry requests', () async {
    final recorder = _PreparationRecorder(
      (options) => _response(options, {'ok': true, 'preparation': _payload()}),
    );
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
      ..interceptors.add(recorder);
    final apiClient = ApiClient(dio);
    final repository = LearningPreparationRepository(apiClient: apiClient);

    expect(dio.options.headers, isNot(contains('X-Mira-Preparation-Schema')));
    await repository.current('child-1');
    await apiClient.get('/setup/status');
    await apiClient.get('/profile/summary');

    expect(
      recorder.requests.first.headers['X-Mira-Preparation-Schema'],
      'mira.learning.preparation.v2',
    );
    expect(
      recorder.requests.skip(1).map((request) => request.headers),
      everyElement(isNot(contains('X-Mira-Preparation-Schema'))),
    );
    expect(dio.options.headers, isNot(contains('X-Mira-Preparation-Schema')));
  });

  test('HTTP errors preserve backend code and message including 404', () async {
    final recorder = _PreparationRecorder((options) {
      throw DioException(
        requestOptions: options,
        response: Response<dynamic>(
          requestOptions: options,
          statusCode: 404,
          data: const {
            'error': 'learning_preparation_not_found',
            'message': '课程准备计划不存在',
          },
        ),
        type: DioExceptionType.badResponse,
      );
    });
    final repository = _repository(recorder);

    await expectLater(
      repository.current('child-1'),
      throwsA(
        isA<LearningPreparationException>()
            .having(
              (error) => error.code,
              'code',
              'learning_preparation_not_found',
            )
            .having((error) => error.message, 'message', '课程准备计划不存在')
            .having((error) => error.isTransportFailure, 'transport', isFalse),
      ),
    );
  });

  test(
    'transport errors remain separate from safe generation errors',
    () async {
      final recorder = _PreparationRecorder((options) {
        throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
          message: 'socket unavailable',
        );
      });
      final repository = _repository(recorder);

      await expectLater(
        repository.current('child-1'),
        throwsA(
          isA<LearningPreparationException>()
              .having(
                (error) => error.code,
                'code',
                'learning_preparation_transport_error',
              )
              .having((error) => error.isTransportFailure, 'transport', isTrue)
              .having(
                (error) => error.message,
                'message',
                isNot('课程准备暂时失败，请稍后重试'),
              ),
        ),
      );
    },
  );

  test('non-Dio parser failures are not rewritten as network errors', () async {
    final recorder = _PreparationRecorder(
      (options) => _response(options, {'ok': true, 'preparation': []}),
    );
    final repository = _repository(recorder);

    await expectLater(
      repository.current('child-1'),
      throwsA(isA<LearningPreparationFormatException>()),
    );
  });
}

LearningPreparationRepository _repository(_PreparationRecorder recorder) {
  final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
    ..interceptors.add(recorder);
  return LearningPreparationRepository(apiClient: ApiClient(dio));
}

Response<dynamic> _response(RequestOptions options, Object? data) {
  return Response<dynamic>(
    requestOptions: options,
    statusCode: 200,
    data: data,
  );
}

class _PreparationRecorder extends Interceptor {
  _PreparationRecorder(this.handler);

  Response<dynamic> Function(RequestOptions options) handler;
  final requests = <RequestOptions>[];

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler next) {
    requests.add(options);
    try {
      next.resolve(handler(options));
    } on DioException catch (error) {
      next.reject(error);
    }
  }
}

class _LegacyPreparationGateway implements LearningPreparationGateway {
  const _LegacyPreparationGateway(this.preparation);

  final LearningPreparation preparation;

  @override
  Future<LearningPreparation?> current(String childId) async => preparation;

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) async => preparation;
}

Map<String, dynamic> _payload({
  String id = 'lcp-1',
  String childId = 'child-1',
  String status = 'running',
  String stage = 'planning',
}) {
  return <String, dynamic>{
    'schemaVersion': 'mira.learning.preparation.v1',
    'id': id,
    'childId': childId,
    'gradeCode': 'primary_1',
    'gradeLabel': '一年级',
    'subjects': const [
      {
        'code': 'chinese',
        'label': '语文',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 12,
      },
      {
        'code': 'math',
        'label': '数学',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
      {
        'code': 'english',
        'label': '英语',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
    ],
    'status': status,
    'stage': stage,
    'progressPercent': 0,
    'totalCourseCount': 30,
    'readyCourseCount': 0,
    'failedCourseCount': 0,
    'attempt': 1,
    'canRetry': false,
    'retryAfterMs': 2500,
    'message': '正在规划课程',
    'lastProgressAt': 1787200000000,
    'updatedAt': 1787200000000,
    'completedAt': null,
    'error': null,
  };
}
