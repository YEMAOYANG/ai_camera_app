import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';

void main() {
  test(
    'parent manages owned student authorizations without secret fields',
    () async {
      final requests = <RequestOptions>[];
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
        ..interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              requests.add(options);
              final data = switch ((options.method, options.path)) {
                (
                  'GET',
                  '/v2/parent/children/child-1/student-access/authorizations',
                ) =>
                  {
                    'ok': true,
                    'childId': 'child-1',
                    'authorizations': [
                      {
                        'id': 'device-1',
                        'displayName': '客厅学习平板',
                        'deviceType': 'tablet',
                        'platform': 'android',
                        'status': 'active',
                        'trustedUntil': 1787600000000,
                        'lastUsedAt': 1787500000000,
                        'createdAt': 1787400000000,
                        'sessions': [
                          {
                            'id': 'session-1',
                            'status': 'active',
                            'lastUsedAt': 1787500000000,
                            'createdAt': 1787490000000,
                          },
                        ],
                      },
                    ],
                  },
                (
                  'DELETE',
                  '/v2/parent/children/child-1/student-access/authorizations/device-1',
                ) =>
                  {
                    'ok': true,
                    'childId': 'child-1',
                    'authorizationId': 'device-1',
                    'status': 'revoked',
                    'alreadyRevoked': false,
                    'revokedSessionCount': 1,
                    'revokedAt': 1787501000000,
                  },
                (
                  'POST',
                  '/v2/parent/children/child-1/student-access/pin/reset',
                ) =>
                  {
                    'ok': true,
                    'childId': 'child-1',
                    'pinUpdatedAt': 1787502000000,
                    'revokedSessionCount': 1,
                    'trustedDeviceCount': 1,
                    'existingDevicesRemainTrusted': true,
                    'requiresUnlockWithNewPin': true,
                  },
                _ => <String, dynamic>{},
              };
              handler.resolve(
                Response<dynamic>(
                  requestOptions: options,
                  statusCode: 200,
                  data: data,
                ),
              );
            },
          ),
        );
      final repository = StudentAccessRepository(apiClient: ApiClient(dio));

      final authorizations = await repository.listAuthorizations('child-1');
      final revoked = await repository.revokeAuthorization(
        childId: 'child-1',
        authorizationId: 'device-1',
      );
      final reset = await repository.resetPin(childId: 'child-1', pin: '2468');

      expect(authorizations.items.single.displayName, '客厅学习平板');
      expect(authorizations.items.single.sessions.single.id, 'session-1');
      expect(revoked.alreadyRevoked, isFalse);
      expect(revoked.revokedSessionCount, 1);
      expect(reset.existingDevicesRemainTrusted, isTrue);
      expect(reset.requiresUnlockWithNewPin, isTrue);
      expect(requests[0].method, 'GET');
      expect(requests[1].method, 'DELETE');
      expect(requests[2].method, 'POST');
      expect(requests[2].data, {'pin': '2468'});
    },
  );

  test(
    'parent report repository uses paginated list and owned detail contract',
    () async {
      final requests = <RequestOptions>[];
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
        ..interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              requests.add(options);
              final report = {
                'id': 'report-1',
                'childId': 'child-1',
                'taskId': 'task-1',
                'sessionId': 'session-1',
                'courseId': 'course-1',
                'courseVersion': '1.0.0',
                'courseTitle': '20 以内加减法',
                'date': '2026-08-25',
                'createdAt': 1787500000000,
                'gradeCode': 'primary_1',
                'subject': 'math',
                'subjectLabel': '数学',
                'score': 100,
                'correctCount': 4,
                'independentCorrectCount': 2,
                'hintCount': 0,
                'totalQuestions': 4,
                'masteryLevel': 'mastered',
                'summary': '独立检查全部正确。',
                'strengths': ['计算准确'],
                'nextStep': '继续下一能力点。',
              };
              final data = options.path == '/learning/reports'
                  ? {
                      'ok': true,
                      'childId': 'child-1',
                      'subject': 'math',
                      'items': [report],
                      'nextCursor': 'next-page',
                    }
                  : {'ok': true, 'childId': 'child-1', 'report': report};
              handler.resolve(
                Response<dynamic>(
                  requestOptions: options,
                  statusCode: 200,
                  data: data,
                ),
              );
            },
          ),
        );
      final repository = LearningRepository(apiClient: ApiClient(dio));

      final page = await repository.reports(
        childId: 'child-1',
        subject: 'math',
        cursor: 'cursor-0',
        limit: 10,
      );
      final detail = await repository.reportDetail(
        childId: 'child-1',
        reportId: 'report-1',
      );

      expect(page.items.single.courseTitle, '20 以内加减法');
      expect(page.items.single.sessionId, 'session-1');
      expect(page.nextCursor, 'next-page');
      expect(detail.strengths, ['计算准确']);
      expect(detail.score, 100);
      expect(requests[0].path, '/learning/reports');
      expect(requests[0].queryParameters, {
        'childId': 'child-1',
        'subject': 'math',
        'cursor': 'cursor-0',
        'limit': 10,
      });
      expect(requests[1].path, '/learning/reports/report-1');
      expect(requests[1].queryParameters, {'childId': 'child-1'});
    },
  );
}
