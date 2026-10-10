import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'support/fake_auth_token_storage.dart';

void main() {
  test(
    'protected requests are rejected locally when session is missing',
    () async {
      SharedPreferences.setMockInitialValues(const {});
      final preferences = await SharedPreferences.getInstance();
      final sessionStore = AuthSessionStore(
        preferences,
        secureStorage: FakeAuthSecureSessionStorage(),
      );
      final dio = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
      final refreshDio = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
      var downstreamRequests = 0;

      dio.interceptors.add(
        AuthTokenInterceptor(
          sessionStore: sessionStore,
          refreshDio: refreshDio,
          dio: dio,
        ),
      );
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            downstreamRequests += 1;
            handler.resolve(
              Response<dynamic>(requestOptions: options, data: {}),
            );
          },
        ),
      );

      await expectLater(
        dio.get<dynamic>('/profile/summary'),
        throwsA(
          isA<DioException>().having(
            (error) => error.response?.data,
            'error body',
            containsPair('error', 'auth_session_missing'),
          ),
        ),
      );
      expect(downstreamRequests, 0);
    },
  );

  test(
    'one token refresh clones a finalized multipart upload and keeps its key',
    () async {
      SharedPreferences.setMockInitialValues(const {});
      final preferences = await SharedPreferences.getInstance();
      final sessionStore = AuthSessionStore(
        preferences,
        secureStorage: FakeAuthSecureSessionStorage(),
      );
      final now = DateTime.now();
      await sessionStore.save(
        AuthSession(
          accessToken: 'test-access-before',
          refreshToken: 'test-refresh',
          accessTokenExpiresAt: now.add(const Duration(minutes: 30)),
          refreshTokenExpiresAt: now.add(const Duration(days: 1)),
          userId: 'test-parent',
          phone: 'test-phone',
        ),
      );
      final dio = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
      final refresh = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
      refresh.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) => h.resolve(
            Response(
              requestOptions: r,
              data: {
                'user': {'id': 'test-parent', 'phone': 'test-phone'},
                'tokens': {
                  'accessToken': 'test-access-after',
                  'refreshToken': 'test-refresh-after',
                  'accessTokenExpiresAt': now
                      .add(const Duration(minutes: 30))
                      .millisecondsSinceEpoch,
                  'refreshTokenExpiresAt': now
                      .add(const Duration(days: 1))
                      .millisecondsSinceEpoch,
                },
              },
            ),
          ),
        ),
      );
      dio.interceptors.add(
        AuthTokenInterceptor(
          sessionStore: sessionStore,
          refreshDio: refresh,
          dio: dio,
        ),
      );
      var calls = 0;
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) async {
            calls++;
            final body = r.data as FormData;
            expect(body.isFinalized, isFalse);
            expect(
              Map.fromEntries(body.fields)['idempotencyKey'],
              'stable-upload',
            );
            if (calls == 1) {
              await body.finalize().drain<void>();
              h.reject(
                DioException(
                  requestOptions: r,
                  response: Response(requestOptions: r, statusCode: 401),
                ),
                true,
              );
            } else {
              expect(r.headers['Authorization'], 'Bearer test-access-after');
              h.resolve(Response(requestOptions: r, data: {'ok': true}));
            }
          },
        ),
      );
      final response = await dio.post<dynamic>(
        '/homework-submissions/test/pages',
        data: FormData.fromMap({
          'idempotencyKey': 'stable-upload',
          'file': MultipartFile.fromBytes([1, 2, 3], filename: 'test.png'),
        }),
      );
      expect(response.data, {'ok': true});
      expect(calls, 2);
    },
  );

  test('public documents can load without a session', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final sessionStore = AuthSessionStore(
      preferences,
      secureStorage: FakeAuthSecureSessionStorage(),
    );
    final dio = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
    var downstreamRequests = 0;

    dio.interceptors.add(
      AuthTokenInterceptor(
        sessionStore: sessionStore,
        refreshDio: Dio(BaseOptions(baseUrl: 'http://test.local/api')),
        dio: dio,
      ),
    );
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          downstreamRequests += 1;
          handler.resolve(
            Response<dynamic>(requestOptions: options, data: {'ok': true}),
          );
        },
      ),
    );

    final response = await dio.get<dynamic>('/legal/user-agreement');
    expect(response.data, {'ok': true});
    expect(downstreamRequests, 1);
  });
}
