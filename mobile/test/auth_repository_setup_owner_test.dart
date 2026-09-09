import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';
import 'package:warm_sight/src/features/auth/application/auth_repository.dart';
import 'support/fake_auth_token_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'login claims pending setup before publishing another account',
    () async {
      SharedPreferences.setMockInitialValues(const {});
      final preferences = await SharedPreferences.getInstance();
      final setupStore = SetupStore(preferences);
      await setupStore.claimPendingOwner('user-a');
      await setupStore.savePendingChildNickname('乐乐');
      await setupStore.savePendingGrade(
        gradeCode: 'primary_3',
        schoolYearStartYear: 2026,
      );

      final sessionStore = AuthSessionStore(
        preferences,
        secureStorage: FakeAuthSecureSessionStorage(),
      );
      final dio = _authDio(userId: 'user-b');
      final repository = AuthRepository(
        dio: dio,
        sessionStore: sessionStore,
        setupStore: setupStore,
      );

      final result = await repository.loginWithSms(
        phone: '13800138000',
        code: '123456',
      );

      expect(result.session.userId, 'user-b');
      expect(sessionStore.currentSession?.userId, 'user-b');
      expect(setupStore.pendingOwnerUserId, 'user-b');
      expect(setupStore.pendingChildNickname, isEmpty);
      expect(setupStore.pendingGradeCode, isEmpty);
    },
  );

  test('login preserves pending setup for the same account', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final setupStore = SetupStore(preferences);
    await setupStore.claimPendingOwner('user-a');
    await setupStore.savePendingChildNickname('乐乐');
    await setupStore.savePendingGrade(
      gradeCode: 'primary_3',
      schoolYearStartYear: 2026,
    );

    final sessionStore = AuthSessionStore(
      preferences,
      secureStorage: FakeAuthSecureSessionStorage(),
    );
    final repository = AuthRepository(
      dio: _authDio(userId: 'user-a'),
      sessionStore: sessionStore,
      setupStore: setupStore,
    );

    await repository.loginWithSms(phone: '13800138000', code: '123456');

    expect(setupStore.pendingOwnerUserId, 'user-a');
    expect(setupStore.pendingChildNickname, '乐乐');
    expect(setupStore.pendingGradeCode, 'primary_3');
    expect(setupStore.pendingSchoolYearStartYear, 2026);
  });

  test('session refresh restores pending setup for the same account', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final setupStore = SetupStore(preferences);
    await setupStore.claimPendingOwner('user-a');
    await setupStore.savePendingChildNickname('乐乐');
    await setupStore.savePendingGrade(
      gradeCode: 'primary_3',
      schoolYearStartYear: 2026,
    );

    final sessionStore = AuthSessionStore(
      preferences,
      secureStorage: FakeAuthSecureSessionStorage(),
    );
    await sessionStore.save(
      AuthSession(
        accessToken: 'expired-access-user-a',
        refreshToken: 'refresh-user-a',
        accessTokenExpiresAt: DateTime.now().subtract(
          const Duration(minutes: 1),
        ),
        refreshTokenExpiresAt: DateTime.now().add(const Duration(days: 30)),
        userId: 'user-a',
        phone: '13800138000',
      ),
    );
    final repository = AuthRepository(
      dio: _authDio(userId: 'user-a'),
      sessionStore: sessionStore,
      setupStore: setupStore,
    );

    final refreshed = await repository.refreshSession();

    expect(refreshed?.userId, 'user-a');
    expect(setupStore.pendingOwnerUserId, 'user-a');
    expect(setupStore.pendingChildNickname, '乐乐');
    expect(setupStore.pendingGradeCode, 'primary_3');
    expect(setupStore.pendingSchoolYearStartYear, 2026);
  });
}

Dio _authDio({required String userId}) {
  final dio = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) {
        handler.resolve(
          Response<dynamic>(
            requestOptions: options,
            statusCode: 200,
            data: {
              'tokens': {
                'accessToken': 'access-$userId',
                'refreshToken': 'refresh-$userId',
                'accessTokenExpiresAt': DateTime.now()
                    .add(const Duration(hours: 1))
                    .millisecondsSinceEpoch,
                'refreshTokenExpiresAt': DateTime.now()
                    .add(const Duration(days: 30))
                    .millisecondsSinceEpoch,
              },
              'user': {'id': userId, 'phone': '13800138000'},
              'pendingJoins': <Object>[],
            },
          ),
        );
      },
    ),
  );
  return dio;
}
