import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';
import 'package:warm_sight/src/features/auth/application/auth_repository.dart';

import 'support/fake_auth_token_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  for (final switchAccount in [false, true]) {
    test('logout revokes a delayed refresh and never resumes its request'
        '${switchAccount ? ' after another account signs in' : ''}', () async {
      final fixture = await _Fixture.create();
      await fixture.store.save(_session('a', expired: true));
      final response = Completer<void>();
      final started = Completer<void>();
      final logoutTokens = <String>[];
      fixture.raw.interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) async {
            if (request.path == '/auth/token/refresh') {
              started.complete();
              await response.future;
              handler.resolve(_response(request, _session('a-refreshed')));
            } else {
              logoutTokens.add(request.data['refreshToken'] as String);
              handler.resolve(Response(requestOptions: request, data: {}));
            }
          },
        ),
      );
      var businessRequests = 0;
      fixture.api.interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) {
            businessRequests++;
            handler.resolve(Response(requestOptions: request, data: {}));
          },
        ),
      );

      final request = fixture.api.get<dynamic>('/profile/summary');
      final rejected = expectLater(request, throwsA(isA<DioException>()));
      await started.future;
      final logout = fixture.auth.logout();
      expect(fixture.store.currentSession, isNull);
      if (switchAccount) await fixture.store.save(_session('b'));
      response.complete();
      await logout;
      await rejected;

      expect(businessRequests, 0);
      expect(logoutTokens, ['refresh-a', 'refresh-a-refreshed']);
      expect(fixture.store.currentSession?.userId, switchAccount ? 'b' : null);
      expect(
        fixture.storage.envelope == null
            ? null
            : jsonDecode(fixture.storage.envelope!)['userId'],
        switchAccount ? 'b' : null,
      );
    });
  }

  test(
    'an old account 401 never retries its business request as the new user',
    () async {
      final fixture = await _Fixture.create();
      await fixture.store.save(_session('a'));
      final started = Completer<void>();
      final response = Completer<void>();
      final seenTokens = <Object?>[];
      var refreshRequests = 0;
      fixture.raw.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            refreshRequests++;
            h.resolve(_response(r, _session('b-refreshed')));
          },
        ),
      );
      fixture.api.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) async {
            seenTokens.add(r.headers['Authorization']);
            started.complete();
            await response.future;
            h.reject(
              DioException(
                requestOptions: r,
                response: Response(requestOptions: r, statusCode: 401),
              ),
              true,
            );
          },
        ),
      );
      final request = fixture.api.post<dynamic>(
        '/tasks',
        data: {'title': 'A task'},
      );
      final rejected = expectLater(request, throwsA(isA<DioException>()));
      await started.future;
      await fixture.store.clear();
      await fixture.store.save(_session('b'));
      response.complete();
      await rejected;
      expect(seenTokens, ['Bearer access-a']);
      expect(refreshRequests, 0);
      expect(fixture.store.currentSession?.userId, 'b');
    },
  );

  test('a failed old refresh cannot clear a newer account', () async {
    final fixture = await _Fixture.create();
    await fixture.store.save(_session('a', expired: true));
    final started = Completer<void>();
    final response = Completer<void>();
    fixture.raw.interceptors.add(
      InterceptorsWrapper(
        onRequest: (r, h) async {
          started.complete();
          await response.future;
          h.reject(
            DioException(
              requestOptions: r,
              type: DioExceptionType.connectionTimeout,
            ),
          );
        },
      ),
    );
    final refresh = fixture.auth.refreshSession();
    final rejected = expectLater(refresh, throwsA(isA<AuthException>()));
    await started.future;
    await fixture.store.clear();
    await fixture.store.save(_session('b'));
    response.complete();
    await rejected;
    expect(fixture.store.currentSession?.userId, 'b');
    expect(jsonDecode(fixture.storage.envelope!)['userId'], 'b');
  });

  test(
    'a delayed SMS login after logout is revoked without reclaiming setup',
    () async {
      final fixture = await _Fixture.create();
      final started = Completer<void>();
      final response = Completer<void>();
      final revoked = <String>[];
      fixture.raw.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) async {
            if (r.path == '/auth/sms/login') {
              started.complete();
              await response.future;
              h.resolve(_response(r, _session('a')));
            } else {
              revoked.add(r.data['refreshToken'] as String);
              h.resolve(Response(requestOptions: r, data: {}));
            }
          },
        ),
      );
      final login = fixture.auth.loginWithSms(
        phone: '13800138000',
        code: '123456',
      );
      final rejected = expectLater(
        login,
        throwsA(
          isA<AuthException>().having(
            (error) => error.code,
            'code',
            'session_changed',
          ),
        ),
      );
      await started.future;
      await fixture.auth.logout();
      response.complete();
      await rejected;
      expect(fixture.store.currentSession, isNull);
      expect(fixture.storage.envelope, isNull);
      expect(fixture.setup.pendingOwnerUserId, isEmpty);
      expect(revoked, ['refresh-a']);
    },
  );

  test('repository and API requests share one refresh operation', () async {
    final fixture = await _Fixture.create();
    await fixture.store.save(_session('a', expired: true));
    final started = Completer<void>();
    final response = Completer<void>();
    var refreshRequests = 0;
    fixture.raw.interceptors.add(
      InterceptorsWrapper(
        onRequest: (r, h) async {
          refreshRequests++;
          started.complete();
          await response.future;
          h.resolve(_response(r, _session('a-refreshed')));
        },
      ),
    );
    fixture.api.interceptors.add(
      InterceptorsWrapper(
        onRequest: (r, h) {
          expect(r.headers['Authorization'], 'Bearer access-a-refreshed');
          h.resolve(Response(requestOptions: r, data: {'ok': true}));
        },
      ),
    );
    final refresh = fixture.auth.refreshSession();
    await started.future;
    final business = fixture.api.get<dynamic>('/profile/summary');
    response.complete();
    expect((await refresh)?.accessToken, 'access-a-refreshed');
    expect((await business).data, {'ok': true});
    expect(refreshRequests, 1);
  });

  test('clear wins over a refresh already writing secure storage', () async {
    final storage = _DelayedStorage();
    final fixture = await _Fixture.create(storage: storage);
    await fixture.store.save(_session('a', expired: true));
    storage.blockWrite = true;
    final published = <String?>[];
    fixture.store.addListener(
      () => published.add(fixture.store.currentSession?.userId),
    );
    final discarded = <String>[];
    final refresh = fixture.store.refreshSession(
      load: (_) async => _session('a-refreshed'),
      discard: (session) async {
        discarded.add(session.userId);
      },
    );
    await storage.writeStarted.future;
    final clearing = fixture.store.clear();
    expect(fixture.store.currentSession, isNull);
    storage.writeRelease.complete();
    expect(await refresh, isNull);
    await clearing;
    expect(storage.envelope, isNull);
    expect(published, isNot(contains('a-refreshed')));
    expect(discarded, ['a-refreshed']);
  });

  test(
    'a slow clear cannot erase a later sign-in from secure storage',
    () async {
      final storage = _DelayedStorage();
      final fixture = await _Fixture.create(storage: storage);
      await fixture.store.save(_session('a'));
      storage.blockDelete = true;
      final clearing = fixture.store.clear();
      await storage.deleteStarted.future;
      final saving = fixture.store.save(_session('b'));
      expect(fixture.store.currentSession, isNull);
      storage.deleteRelease.complete();
      await clearing;
      expect(await saving, isTrue);
      expect(fixture.store.currentSession?.userId, 'b');
      expect(jsonDecode(storage.envelope!)['userId'], 'b');
    },
  );

  test('initial session restoration cannot overtake logout', () async {
    final storage = _DelayedStorage();
    final fixture = await _Fixture.create(storage: storage);
    await fixture.store.save(_session('a'));
    storage.blockRead = true;
    final restoring = AuthSessionStore(
      fixture.preferences,
      secureStorage: storage,
    );
    final initialization = restoring.initialize();
    await storage.readStarted.future;
    final clearing = restoring.clear();
    storage.readRelease.complete();
    await initialization;
    await clearing;
    expect(restoring.currentSession, isNull);
    expect(storage.envelope, isNull);
  });

  test(
    'setup logout blocks old requests immediately and serializes draft cleanup before the next login',
    () async {
      SharedPreferences.setMockInitialValues({});
      final preferences = await SharedPreferences.getInstance();
      final setup = _DelayedSetupStore(preferences);
      final fixture = _Fixture(
        preferences,
        FakeAuthSecureSessionStorage(),
        setupStore: setup,
      );
      await fixture.store.save(_session('a'));
      await setup.claimPendingOwner('a');
      await setup.savePendingChildNickname('A child');
      setup.blockClear = true;
      fixture.raw.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            h.resolve(
              r.path == '/auth/sms/login'
                  ? _response(r, _session('b'))
                  : Response(requestOptions: r, data: {}),
            );
          },
        ),
      );
      final logout = fixture.auth.logout(clearSetupDraft: true);
      expect(fixture.store.currentSession, isNull);
      await setup.clearStarted.future;
      await expectLater(
        fixture.api.get<dynamic>('/profile/summary'),
        throwsA(isA<DioException>()),
      );
      final login = fixture.auth.loginWithSms(
        phone: '13800138000',
        code: '123456',
      );
      // Let the immediate SMS response enqueue B's save while A's draft
      // deletion is still blocked, instead of releasing cleanup first.
      await Future<void>.delayed(Duration.zero);
      expect(fixture.store.currentSession, isNull);
      expect(setup.pendingOwnerUserId, 'a');
      setup.clearRelease.complete();
      await logout;
      await login;
      await setup.savePendingChildNickname('B child');
      expect(setup.pendingOwnerUserId, 'b');
      expect(setup.pendingChildNickname, 'B child');
      expect(fixture.store.currentSession?.userId, 'b');
      expect(jsonDecode(fixture.storage.envelope!)['userId'], 'b');
    },
  );

  test(
    'a refreshed token that cannot be persisted is remotely revoked',
    () async {
      final storage = _DelayedStorage();
      final fixture = await _Fixture.create(storage: storage);
      await fixture.store.save(_session('a'));
      storage.failWrite = true;
      final discarded = <String>[];
      await expectLater(
        fixture.store.refreshSession(
          load: (_) async => _session('a-refreshed'),
          discard: (session) async {
            discarded.add(session.refreshToken);
          },
        ),
        throwsStateError,
      );
      expect(discarded, ['refresh-a-refreshed']);
      expect(fixture.store.currentSession?.userId, 'a');
      expect(jsonDecode(storage.envelope!)['userId'], 'a');
      storage.failWrite = false;
      expect(await fixture.store.save(_session('b')), isTrue);
    },
  );

  for (final refresh in [false, true]) {
    test(
      'legacy cleanup failure preserves the committed ${refresh ? 'refresh' : 'login'} identity',
      () async {
        SharedPreferences.setMockInitialValues({});
        final preferences = _FailingLegacyPreferences(
          await SharedPreferences.getInstance(),
        );
        final storage = FakeAuthSecureSessionStorage();
        final store = AuthSessionStore(preferences, secureStorage: storage);
        await store.save(_session('a'));
        preferences.failRemoves = true;
        final discarded = <String>[];
        if (refresh) {
          expect(
            (await store.refreshSession(
              load: (_) async => _session('b'),
              discard: (session) async {
                discarded.add(session.userId);
              },
            ))?.userId,
            'b',
          );
        } else {
          expect(await store.save(_session('b')), isTrue);
        }
        expect(store.currentSession?.userId, 'b');
        expect(jsonDecode(storage.envelope!)['userId'], 'b');
        expect(discarded, isEmpty);
        final restored = AuthSessionStore(preferences, secureStorage: storage);
        await restored.initialize();
        expect(restored.currentSession?.userId, 'b');
      },
    );
  }

  test(
    'login persistence failure revokes new tokens and returns a handled auth error',
    () async {
      final storage = _DelayedStorage()..failWrite = true;
      final fixture = await _Fixture.create(storage: storage);
      final revoked = <String>[];
      fixture.raw.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            if (r.path == '/auth/sms/login') {
              h.resolve(_response(r, _session('a')));
            } else {
              revoked.add(r.data['refreshToken'] as String);
              h.resolve(Response(requestOptions: r, data: {}));
            }
          },
        ),
      );
      await expectLater(
        fixture.auth.loginWithSms(phone: '13800138000', code: '123456'),
        throwsA(
          isA<AuthException>().having(
            (e) => e.code,
            'code',
            'auth_storage_unavailable',
          ),
        ),
      );
      expect(fixture.store.currentSession, isNull);
      expect(storage.envelope, isNull);
      expect(revoked, ['refresh-a']);
    },
  );

  for (final expiredAccess in [true, false]) {
    test(
      'secure storage failure completes the API request with a non-auth error ${expiredAccess ? 'before sending' : 'after a business 401'}',
      () async {
        final storage = _DelayedStorage();
        final fixture = await _Fixture.create(storage: storage);
        await fixture.store.save(_session('a', expired: expiredAccess));
        final originalEnvelope = storage.envelope;
        storage.failWrite = true;
        final revoked = <String>[];
        fixture.raw.interceptors.add(
          InterceptorsWrapper(
            onRequest: (r, h) {
              if (r.path == '/auth/token/refresh') {
                h.resolve(_response(r, _session('a-refreshed')));
              } else {
                revoked.add(r.data['refreshToken'] as String);
                h.resolve(Response(requestOptions: r, data: {}));
              }
            },
          ),
        );
        fixture.api.interceptors.add(
          InterceptorsWrapper(
            onRequest: (r, h) {
              h.reject(
                DioException(
                  requestOptions: r,
                  response: Response(requestOptions: r, statusCode: 401),
                ),
                true,
              );
            },
          ),
        );
        await expectLater(
          fixture.api
              .get<dynamic>('/profile/summary')
              .timeout(const Duration(seconds: 2)),
          throwsA(
            isA<DioException>()
                .having((e) => e.type, 'type', DioExceptionType.unknown)
                .having(
                  (e) => e.error,
                  'original storage error',
                  isA<StateError>(),
                )
                .having((e) => e.response?.statusCode, 'status', isNull),
          ),
        );
        expect(revoked, ['refresh-a-refreshed']);
        expect(fixture.store.currentSession?.userId, 'a');
        expect(storage.envelope, originalEnvelope);
      },
    );
  }

  for (final expiredAccess in [true, false]) {
    for (final serverError in [false, true]) {
      test(
        'refresh ${serverError ? '503' : 'timeout'} keeps the session and recovers ${expiredAccess ? 'before a request' : 'after a business 401'}',
        () async {
          final fixture = await _Fixture.create();
          await fixture.store.save(_session('a', expired: expiredAccess));
          final originalEnvelope = fixture.storage.envelope;
          var failing = true;
          fixture.raw.interceptors.add(
            InterceptorsWrapper(
              onRequest: (r, h) {
                if (failing) {
                  h.reject(
                    DioException(
                      requestOptions: r,
                      type: serverError
                          ? DioExceptionType.badResponse
                          : DioExceptionType.connectionTimeout,
                      response: serverError
                          ? Response(requestOptions: r, statusCode: 503)
                          : null,
                    ),
                  );
                } else {
                  h.resolve(_response(r, _session('a-refreshed')));
                }
              },
            ),
          );
          fixture.api.interceptors.add(
            InterceptorsWrapper(
              onRequest: (r, h) {
                if (r.headers['Authorization'] == 'Bearer access-a') {
                  h.reject(
                    DioException(
                      requestOptions: r,
                      response: Response(requestOptions: r, statusCode: 401),
                    ),
                    true,
                  );
                } else {
                  h.resolve(Response(requestOptions: r, data: {'ok': true}));
                }
              },
            ),
          );
          await expectLater(
            fixture.api.get<dynamic>('/profile/summary'),
            throwsA(
              isA<DioException>()
                  .having(
                    (e) => e.response?.statusCode,
                    'status',
                    serverError ? 503 : null,
                  )
                  .having(
                    (e) => e.type,
                    'type',
                    serverError
                        ? DioExceptionType.badResponse
                        : DioExceptionType.connectionTimeout,
                  ),
            ),
          );
          expect(fixture.store.currentSession?.userId, 'a');
          expect(fixture.storage.envelope, originalEnvelope);
          failing = false;
          expect((await fixture.api.get<dynamic>('/profile/summary')).data, {
            'ok': true,
          });
          expect(
            fixture.store.currentSession?.accessToken,
            'access-a-refreshed',
          );
        },
      );
    }
  }

  test(
    'a failed business retry keeps its real error after successful authentication refresh',
    () async {
      final fixture = await _Fixture.create();
      await fixture.store.save(_session('a'));
      fixture.raw.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            h.resolve(_response(r, _session('a-refreshed')));
          },
        ),
      );
      fixture.api.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            final status = r.headers['Authorization'] == 'Bearer access-a'
                ? 401
                : 503;
            h.reject(
              DioException(
                requestOptions: r,
                type: DioExceptionType.badResponse,
                response: Response(requestOptions: r, statusCode: status),
              ),
              true,
            );
          },
        ),
      );
      await expectLater(
        fixture.api.get<dynamic>('/profile/summary'),
        throwsA(
          isA<DioException>().having(
            (e) => e.response?.statusCode,
            'status',
            503,
          ),
        ),
      );
      expect(fixture.store.currentSession?.accessToken, 'access-a-refreshed');
    },
  );

  for (final status in [401, 403]) {
    test(
      'explicit refresh rejection $status clears unusable credentials',
      () async {
        final fixture = await _Fixture.create();
        await fixture.store.save(_session('a', expired: true));
        fixture.raw.interceptors.add(
          InterceptorsWrapper(
            onRequest: (r, h) {
              h.reject(
                DioException(
                  requestOptions: r,
                  response: Response(requestOptions: r, statusCode: status),
                ),
              );
            },
          ),
        );
        expect(await fixture.auth.refreshSession(), isNull);
        expect(fixture.store.currentSession, isNull);
        expect(fixture.storage.envelope, isNull);
      },
    );
  }
}

class _Fixture {
  _Fixture(this.preferences, this.storage, {SetupStore? setupStore}) {
    store = AuthSessionStore(preferences, secureStorage: storage);
    setup = setupStore ?? SetupStore(preferences);
    auth = AuthRepository(dio: raw, sessionStore: store, setupStore: setup);
    api.interceptors.add(
      AuthTokenInterceptor(sessionStore: store, refreshDio: raw, dio: api),
    );
  }

  final SharedPreferences preferences;
  final FakeAuthSecureSessionStorage storage;
  final raw = Dio();
  final api = Dio();
  late final AuthSessionStore store;
  late final SetupStore setup;
  late final AuthRepository auth;

  static Future<_Fixture> create({
    FakeAuthSecureSessionStorage? storage,
  }) async {
    SharedPreferences.setMockInitialValues({});
    return _Fixture(
      await SharedPreferences.getInstance(),
      storage ?? FakeAuthSecureSessionStorage(),
    );
  }
}

class _DelayedStorage extends FakeAuthSecureSessionStorage {
  bool failWrite = false;
  bool blockWrite = false;
  bool blockDelete = false;
  bool blockRead = false;
  final writeStarted = Completer<void>();
  final writeRelease = Completer<void>();
  final deleteStarted = Completer<void>();
  final deleteRelease = Completer<void>();
  final readStarted = Completer<void>();
  final readRelease = Completer<void>();

  @override
  Future<void> write(String envelope) async {
    if (failWrite) throw StateError('Synthetic secure storage write failure');
    if (blockWrite) {
      writeStarted.complete();
      await writeRelease.future;
    }
    await super.write(envelope);
  }

  @override
  Future<void> delete() async {
    if (blockDelete) {
      deleteStarted.complete();
      await deleteRelease.future;
    }
    await super.delete();
  }

  @override
  Future<String?> read() async {
    final value = envelope;
    if (blockRead) {
      readStarted.complete();
      await readRelease.future;
    }
    return value;
  }
}

class _FailingLegacyPreferences implements SharedPreferences {
  _FailingLegacyPreferences(this.delegate);
  final SharedPreferences delegate;
  bool failRemoves = false;

  @override
  Future<bool> remove(String key) {
    if (failRemoves) {
      throw StateError('Synthetic legacy metadata cleanup failure');
    }
    return delegate.remove(key);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _DelayedSetupStore extends SetupStore {
  _DelayedSetupStore(super.preferences);

  bool blockClear = false;
  final clearStarted = Completer<void>();
  final clearRelease = Completer<void>();

  @override
  Future<void> clearPendingChildProfile() async {
    if (blockClear) {
      blockClear = false;
      clearStarted.complete();
      await clearRelease.future;
    }
    await super.clearPendingChildProfile();
  }
}

AuthSession _session(String id, {bool expired = false}) => AuthSession(
  accessToken: 'access-$id',
  refreshToken: 'refresh-$id',
  accessTokenExpiresAt: DateTime.now().add(
    Duration(minutes: expired ? -1 : 30),
  ),
  refreshTokenExpiresAt: DateTime.now().add(const Duration(days: 20)),
  userId: id,
  phone: '13800138000',
);

Response<dynamic> _response(RequestOptions request, AuthSession session) =>
    Response(
      requestOptions: request,
      data: {
        'user': {'id': session.userId, 'phone': session.phone},
        'tokens': {
          'accessToken': session.accessToken,
          'refreshToken': session.refreshToken,
          'accessTokenExpiresAt':
              session.accessTokenExpiresAt.millisecondsSinceEpoch,
          'refreshTokenExpiresAt':
              session.refreshTokenExpiresAt.millisecondsSinceEpoch,
        },
      },
    );
