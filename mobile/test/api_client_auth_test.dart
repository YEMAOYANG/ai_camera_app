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
