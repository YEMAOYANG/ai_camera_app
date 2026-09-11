import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';

void main() {
  test('strict availability model accepts the published contract', () {
    final availability = LearningAvailability.fromJson({
      'ok': true,
      'availability': {
        'gradeCode': 'primary_2',
        'hasActiveRelease': false,
        'availableCourseCount': 1,
        'canAccessWorkspace': true,
        'canLearnNow': true,
      },
    });

    expect(availability.gradeCode, 'primary_2');
    expect(availability.hasActiveRelease, isFalse);
    expect(availability.availableCourseCount, 1);
    expect(availability.canLearnNow, isTrue);
  });

  test('workspace access does not imply a playable course', () {
    final availability = LearningAvailability.fromJson({
      'ok': true,
      'availability': {
        'gradeCode': 'primary_1',
        'hasActiveRelease': false,
        'availableCourseCount': 0,
        'canLearnNow': false,
        'canAccessWorkspace': true,
      },
    });
    expect(availability.canAccessWorkspace, isTrue);
    expect(availability.canLearnNow, isFalse);
  });

  test(
    'empty primary grades keep workspace access without preparation polling',
    () {
      for (var grade = 2; grade <= 6; grade++) {
        final availability = LearningAvailability.fromJson({
          'ok': true,
          'availability': {
            'gradeCode': 'primary_$grade',
            'hasActiveRelease': false,
            'availableCourseCount': 0,
            'canLearnNow': false,
            'canAccessWorkspace': true,
            'learningState': {
              'schemaVersion': 'mira.learning.availability-state.v1',
              'availabilityStatus': 'empty',
              'availableCourseCount': 0,
              'newCourseCount': 0,
              'reviewCourseCount': 0,
              'publishedCourseCount': 0,
              'message': '可以扫码进入学习空间，当前暂无课程。',
            },
          },
        });
        expect(availability.canAccessWorkspace, isTrue);
        expect(availability.canLearnNow, isFalse);
        expect(availability.learningState?.status, 'empty');
        expect(availability.learningState?.isTerminal, isTrue);
      }
    },
  );

  for (final payload in <Object?>[
    {
      'ok': true,
      'availability': {'gradeCode': 'primary_1'},
    },
    {
      'ok': true,
      'availability': {
        'gradeCode': 'primary_1',
        'hasActiveRelease': 1,
        'availableCourseCount': 0,
        'canAccessWorkspace': true,
        'canLearnNow': false,
      },
    },
    {
      'ok': true,
      'availability': {
        'gradeCode': 'primary_1',
        'hasActiveRelease': true,
        'availableCourseCount': 30,
        'canAccessWorkspace': true,
        'canLearnNow': true,
        'preparationReady': true,
      },
    },
    {
      'ok': false,
      'availability': {
        'gradeCode': 'primary_1',
        'hasActiveRelease': true,
        'availableCourseCount': 30,
        'canAccessWorkspace': true,
        'canLearnNow': true,
      },
    },
    {
      'ok': true,
      'availability': {
        'gradeCode': 'primary_1',
        'hasActiveRelease': false,
        'availableCourseCount': 1,
        'canAccessWorkspace': true,
        'canLearnNow': false,
      },
    },
  ]) {
    test('strict availability model rejects malformed payload $payload', () {
      expect(
        () => LearningAvailability.fromJson(payload),
        throwsA(isA<LearningAvailabilityFormatException>()),
      );
    });
  }

  test('repository calls the dedicated child-scoped endpoint', () async {
    final interceptor = _AvailabilityInterceptor();
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
      ..interceptors.add(interceptor);
    final repository = LearningAvailabilityRepository(
      apiClient: ApiClient(dio),
    );

    final availability = await repository.current(' child-1 ');

    expect(interceptor.request?.path, '/learning/availability');
    expect(interceptor.request?.queryParameters, {
      'childId': 'child-1',
      'includeWorkspaceAccess': 'true',
      'includeLearningState': 'true',
    });
    expect(availability.hasActiveRelease, isTrue);
  });

  test('repository rejects an empty child id before transport', () async {
    final repository = LearningAvailabilityRepository(
      apiClient: ApiClient(Dio(BaseOptions(baseUrl: 'https://example.test'))),
    );

    await expectLater(
      repository.current('  '),
      throwsA(
        isA<LearningAvailabilityException>().having(
          (error) => error.code,
          'code',
          'invalid_child_id',
        ),
      ),
    );
  });
}

class _AvailabilityInterceptor extends Interceptor {
  RequestOptions? request;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    request = options;
    handler.resolve(
      Response<dynamic>(
        requestOptions: options,
        statusCode: 200,
        data: {
          'ok': true,
          'availability': {
            'gradeCode': 'primary_1',
            'hasActiveRelease': true,
            'availableCourseCount': 30,
            'canAccessWorkspace': true,
            'canLearnNow': true,
          },
        },
      ),
    );
  }
}
