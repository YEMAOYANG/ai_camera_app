import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';

void main() {
  test(
    'repository creates pairing code with frozen parent API contract',
    () async {
      late RequestOptions captured;
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
        ..interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              captured = options;
              handler.resolve(
                Response<dynamic>(
                  requestOptions: options,
                  statusCode: 200,
                  data: {
                    'ok': true,
                    'pairingCode': 'ABCD2345',
                    'expiresAt': 1786598400000,
                    'child': {'id': 'child-1', 'name': '乐乐', 'nickname': '小乐'},
                  },
                ),
              );
            },
          ),
        );
      final repository = StudentAccessRepository(apiClient: ApiClient(dio));

      final result = await repository.createPairingCode(
        childId: 'child-1',
        pin: '2468',
      );

      expect(
        captured.path,
        '/v2/parent/children/child-1/student-access/pairing-codes',
      );
      expect(captured.method, 'POST');
      expect(captured.data, {'pin': '2468'});
      expect(result.code, 'ABCD2345');
      expect(result.child.displayName, '小乐');
      expect(result.expiresAt.millisecondsSinceEpoch, 1786598400000);
    },
  );

  test('repository exposes backend error message for parent UI', () async {
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
      ..interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            handler.reject(
              DioException(
                requestOptions: options,
                response: Response<dynamic>(
                  requestOptions: options,
                  statusCode: 403,
                  data: {'error': 'forbidden', 'message': '当前家庭成员不能创建学生配对码'},
                ),
                type: DioExceptionType.badResponse,
              ),
            );
          },
        ),
      );
    final repository = StudentAccessRepository(apiClient: ApiClient(dio));

    await expectLater(
      repository.createPairingCode(childId: 'child-1', pin: '2468'),
      throwsA(
        isA<StudentAccessException>()
            .having((error) => error.code, 'code', 'forbidden')
            .having((error) => error.message, 'message', '当前家庭成员不能创建学生配对码'),
      ),
    );
  });

  test(
    'repository previews and approves a QR challenge with child scope',
    () async {
      final requests = <RequestOptions>[];
      final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
        ..interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) {
              requests.add(options);
              if (options.method == 'GET') {
                handler.resolve(
                  Response<dynamic>(
                    requestOptions: options,
                    statusCode: 200,
                    data: {
                      'ok': true,
                      'challengeId':
                          'msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
                      'status': 'pending',
                      'displayCode': '3816',
                      'requiresPin': true,
                      'pinConfigured': false,
                      'requestedAt': 1786598000000,
                      'expiresAt': 1786598600000,
                      'clientDevice': {
                        'label': 'Chrome 浏览器',
                        'type': 'browser',
                        'platform': 'macOS',
                        'osVersion': '15.0',
                        'browserName': 'Chrome',
                        'osName': 'macOS',
                      },
                    },
                  ),
                );
                return;
              }
              handler.resolve(
                Response<dynamic>(
                  requestOptions: options,
                  statusCode: 200,
                  data: {
                    'ok': true,
                    'challengeId':
                        'msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
                    'status': 'approved',
                    'approvedExpiresAt': 1786598600000,
                  },
                ),
              );
            },
          ),
        );
      final repository = StudentAccessRepository(apiClient: ApiClient(dio));

      final challenge = await repository.getQrChallenge(
        challengeId: 'msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
        childId: 'child-1',
      );
      final approval = await repository.approveQrChallenge(
        challengeId: challenge.id,
        childId: 'child-1',
        pin: '2468',
      );

      expect(
        requests[0].path,
        '/v2/parent/student-access/qr-challenges/msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
      );
      expect(requests[0].queryParameters, {'childId': 'child-1'});
      expect(requests[0].method, 'GET');
      expect(
        requests[1].path,
        '/v2/parent/student-access/qr-challenges/msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd/approve',
      );
      expect(requests[1].data, {'childId': 'child-1', 'pin': '2468'});
      expect(challenge.requiresPin, isTrue);
      expect(challenge.clientDevice.systemLabel, 'macOS 15.0');
      expect(approval.status, 'approved');
    },
  );

  test('approval omits a blank PIN so an existing PIN is preserved', () async {
    late RequestOptions captured;
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
      ..interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            captured = options;
            handler.resolve(
              Response<dynamic>(
                requestOptions: options,
                statusCode: 200,
                data: {
                  'challengeId': 'msc_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn',
                  'status': 'approved',
                  'approvalExpiresAt': 1786598600000,
                },
              ),
            );
          },
        ),
      );
    final repository = StudentAccessRepository(apiClient: ApiClient(dio));

    await repository.approveQrChallenge(
      challengeId: 'msc_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn',
      childId: 'child-1',
      pin: '   ',
    );

    expect(captured.data, {'childId': 'child-1'});
  });
}
