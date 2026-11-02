import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';
import 'package:warm_sight/src/features/auth/application/auth_repository.dart';
import 'package:warm_sight/src/features/auth/presentation/login_screen.dart';

import 'support/fake_auth_token_storage.dart';

void main() {
  testWidgets('SMS request disables repeated taps and uses server countdown', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    final dio = _DelayedSmsDio();
    final repository = AuthRepository(
      dio: dio,
      sessionStore: AuthSessionStore(
        preferences,
        secureStorage: FakeAuthSecureSessionStorage(),
      ),
      setupStore: SetupStore(preferences),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWithValue(repository),
          appEnvironmentProvider.overrideWithValue(
            AppEnvironment(flavor: AppFlavor.test, apiBaseUrl: ''),
          ),
        ],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pump();

    await tester.enterText(find.byType(EditableText).first, '13800138000');
    await tester.tap(find.text('获取验证码'));
    await tester.pump();

    expect(find.text('发送中'), findsOneWidget);
    expect(dio.requestCount, 1);
    await tester.tap(find.text('发送中'));
    await tester.pump();
    expect(dio.requestCount, 1);

    dio.release();
    await tester.pump();
    await tester.pump();

    expect(find.text('75 秒'), findsOneWidget);
    expect(dio.requestCount, 1);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpWidget(const SizedBox.shrink());
  });
}

class _DelayedSmsDio extends DioMixin {
  _DelayedSmsDio() {
    options = BaseOptions(baseUrl: 'http://test.local/api');
  }

  final _release = Completer<void>();
  var requestCount = 0;

  void release() => _release.complete();

  @override
  Future<Response<T>> post<T>(
    String path, {
    Object? data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
    ProgressCallback? onSendProgress,
    ProgressCallback? onReceiveProgress,
  }) async {
    requestCount += 1;
    await _release.future;
    return Response<T>(
      requestOptions: RequestOptions(path: path),
      statusCode: 200,
      data:
          const {
                'ok': true,
                'codeSent': true,
                'debugCode': '123456',
                'retryAfterSeconds': 75,
                'message': '验证码已发送',
              }
              as T,
    );
  }
}
