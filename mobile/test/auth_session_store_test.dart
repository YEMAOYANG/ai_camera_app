import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/storage/auth_token_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('save, read, and clear use one versioned secure envelope', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final secureStorage = _MemoryAuthSecureSessionStorage();
    final store = AuthSessionStore(preferences, secureStorage: secureStorage);
    final session = _session();

    await store.save(session);

    expect(secureStorage.writeCalls, 1);
    expect(_decodeEnvelope(secureStorage.envelope), {
      'schema': 'mira.auth.session',
      'version': 1,
      'accessToken': session.accessToken,
      'refreshToken': session.refreshToken,
      'accessTokenExpiresAt':
          session.accessTokenExpiresAt.millisecondsSinceEpoch,
      'refreshTokenExpiresAt':
          session.refreshTokenExpiresAt.millisecondsSinceEpoch,
      'userId': session.userId,
      'phone': session.phone,
    });
    _expectNoLegacySession(preferences);

    final restoredStore = AuthSessionStore(
      preferences,
      secureStorage: secureStorage,
    );
    await restoredStore.initialize();
    expect(secureStorage.readCalls, 1);
    _expectSession(restoredStore.currentSession, session);

    for (final entry in _legacyValues(session).entries) {
      final value = entry.value;
      if (value is int) {
        await preferences.setInt(entry.key, value);
      } else {
        await preferences.setString(entry.key, value as String);
      }
    }
    await restoredStore.clear();

    expect(secureStorage.deleteCalls, 1);
    expect(secureStorage.envelope, isNull);
    expect(restoredStore.currentSession, isNull);
    _expectNoLegacySession(preferences);
  });

  test(
    'valid secure envelope is wholly authoritative over legacy data',
    () async {
      final secureSession = _session(
        accessToken: 'secure-access',
        refreshToken: 'secure-refresh',
        userId: 'secure-user',
        phone: '13900000000',
        accessExpiresAt: DateTime(2027, 1, 1),
        refreshExpiresAt: DateTime(2027, 2, 1),
      );
      final legacySession = _session(
        accessToken: 'legacy-access',
        refreshToken: 'legacy-refresh',
        userId: 'legacy-user',
        phone: '13700000000',
        accessExpiresAt: DateTime(2030, 1, 1),
        refreshExpiresAt: DateTime(2030, 2, 1),
      );
      SharedPreferences.setMockInitialValues(_legacyValues(legacySession));
      final preferences = await SharedPreferences.getInstance();
      final secureStorage = _MemoryAuthSecureSessionStorage(
        envelope: _encodeEnvelope(secureSession),
      );
      final store = AuthSessionStore(preferences, secureStorage: secureStorage);

      await store.initialize();

      expect(secureStorage.readCalls, 1);
      expect(secureStorage.writeCalls, 0);
      _expectSession(store.currentSession, secureSession);
      _expectNoLegacySession(preferences);
    },
  );

  test('complete legacy v0 session migrates with one secure write', () async {
    final session = _session();
    SharedPreferences.setMockInitialValues(_legacyValues(session));
    final preferences = await SharedPreferences.getInstance();
    final secureStorage = _MemoryAuthSecureSessionStorage();
    final store = AuthSessionStore(preferences, secureStorage: secureStorage);

    await store.initialize();

    expect(secureStorage.readCalls, 1);
    expect(secureStorage.writeCalls, 1);
    _expectSession(store.currentSession, session);
    expect(_decodeEnvelope(secureStorage.envelope)['userId'], session.userId);
    _expectNoLegacySession(preferences);
  });

  test(
    'legacy migration write failure retains all v0 data and session',
    () async {
      final session = _session();
      final legacy = _legacyValues(session);
      SharedPreferences.setMockInitialValues(legacy);
      final preferences = await SharedPreferences.getInstance();
      final secureStorage = _MemoryAuthSecureSessionStorage(failWrites: true);
      final store = AuthSessionStore(preferences, secureStorage: secureStorage);

      await store.initialize();

      expect(secureStorage.writeCalls, 1);
      expect(secureStorage.envelope, isNull);
      _expectSession(store.currentSession, session);
      _expectLegacySession(preferences, legacy);
    },
  );

  test(
    'failed save leaves the running session and secure envelope unchanged',
    () async {
      final original = _session(
        accessToken: 'original-access',
        refreshToken: 'original-refresh',
        userId: 'original-user',
      );
      final replacement = _session(
        accessToken: 'replacement-access',
        refreshToken: 'replacement-refresh',
        userId: 'replacement-user',
      );
      SharedPreferences.setMockInitialValues(const {});
      final preferences = await SharedPreferences.getInstance();
      final originalEnvelope = _encodeEnvelope(original);
      final secureStorage = _MemoryAuthSecureSessionStorage(
        envelope: originalEnvelope,
      );
      final store = AuthSessionStore(preferences, secureStorage: secureStorage);
      await store.initialize();
      secureStorage.failWrites = true;

      await expectLater(store.save(replacement), throwsStateError);

      expect(secureStorage.writeCalls, 1);
      expect(secureStorage.envelope, originalEnvelope);
      _expectSession(store.currentSession, original);
      _expectNoLegacySession(preferences);
    },
  );

  final invalidEnvelopes = <String, String>{
    'malformed JSON': '{not-json',
    'unknown version': jsonEncode({..._envelopeMap(_session()), 'version': 2}),
    'missing phone': jsonEncode(
      Map<String, Object>.from(_envelopeMap(_session()))..remove('phone'),
    ),
    'wrong expiry type': jsonEncode({
      ..._envelopeMap(_session()),
      'accessTokenExpiresAt': 'tomorrow',
    }),
    'empty refresh token': jsonEncode({
      ..._envelopeMap(_session()),
      'refreshToken': '',
    }),
    'unexpected field': jsonEncode({
      ..._envelopeMap(_session()),
      'unexpected': true,
    }),
  };
  for (final fixture in invalidEnvelopes.entries) {
    test('${fixture.key} secure envelope fails closed', () async {
      final legacySession = _session(userId: 'legacy-must-not-resume');
      final legacy = _legacyValues(legacySession);
      SharedPreferences.setMockInitialValues(legacy);
      final preferences = await SharedPreferences.getInstance();
      final secureStorage = _MemoryAuthSecureSessionStorage(
        envelope: fixture.value,
      );
      final store = AuthSessionStore(preferences, secureStorage: secureStorage);

      await store.initialize();

      expect(store.currentSession, isNull);
      expect(secureStorage.writeCalls, 0);
      _expectLegacySession(preferences, legacy);
    });
  }

  test('incomplete legacy v0 session is not migrated or deleted', () async {
    final session = _session();
    final legacy = _legacyValues(session)..remove(authPhoneKey);
    SharedPreferences.setMockInitialValues(legacy);
    final preferences = await SharedPreferences.getInstance();
    final secureStorage = _MemoryAuthSecureSessionStorage();
    final store = AuthSessionStore(preferences, secureStorage: secureStorage);

    await store.initialize();

    expect(store.currentSession, isNull);
    expect(secureStorage.writeCalls, 0);
    _expectLegacySession(preferences, legacy);
  });

  test(
    'no secure or legacy session stays signed out without writing',
    () async {
      SharedPreferences.setMockInitialValues(const {});
      final preferences = await SharedPreferences.getInstance();
      final secureStorage = _MemoryAuthSecureSessionStorage();
      final store = AuthSessionStore(preferences, secureStorage: secureStorage);

      await store.initialize();

      expect(secureStorage.readCalls, 1);
      expect(secureStorage.writeCalls, 0);
      expect(store.currentSession, isNull);
    },
  );

  test('mobile platforms enable secure-storage production safeguards', () {
    final androidManifest = File(
      'android/app/src/main/AndroidManifest.xml',
    ).readAsStringSync();
    final iosEntitlements = File(
      'ios/Runner/Runner.entitlements',
    ).readAsStringSync();

    expect(androidManifest, contains('android:allowBackup="false"'));
    expect(iosEntitlements, contains('keychain-access-groups'));
  });

  test('Android secure-storage errors never erase sessions automatically', () {
    const secureStorage = FlutterSecureAuthSessionStorage();

    expect(secureStorage.storage.aOptions.toMap()['resetOnError'], 'false');
  });
}

class _MemoryAuthSecureSessionStorage implements AuthSecureSessionStorage {
  _MemoryAuthSecureSessionStorage({this.envelope, this.failWrites = false});

  String? envelope;
  bool failWrites;
  var readCalls = 0;
  var writeCalls = 0;
  var deleteCalls = 0;

  @override
  Future<void> delete() async {
    deleteCalls += 1;
    envelope = null;
  }

  @override
  Future<String?> read() async {
    readCalls += 1;
    return envelope;
  }

  @override
  Future<void> write(String envelope) async {
    writeCalls += 1;
    if (failWrites) throw StateError('secure write failed');
    this.envelope = envelope;
  }
}

Map<String, dynamic> _decodeEnvelope(String? envelope) {
  return Map<String, dynamic>.from(jsonDecode(envelope!) as Map);
}

String _encodeEnvelope(AuthSession session) =>
    jsonEncode(_envelopeMap(session));

Map<String, Object> _envelopeMap(AuthSession session) {
  return {
    'schema': 'mira.auth.session',
    'version': 1,
    'accessToken': session.accessToken,
    'refreshToken': session.refreshToken,
    'accessTokenExpiresAt': session.accessTokenExpiresAt.millisecondsSinceEpoch,
    'refreshTokenExpiresAt':
        session.refreshTokenExpiresAt.millisecondsSinceEpoch,
    'userId': session.userId,
    'phone': session.phone,
  };
}

Map<String, Object> _legacyValues(AuthSession session) {
  return {
    authAccessTokenKey: session.accessToken,
    authRefreshTokenKey: session.refreshToken,
    authAccessTokenExpiresAtKey:
        session.accessTokenExpiresAt.millisecondsSinceEpoch,
    authRefreshTokenExpiresAtKey:
        session.refreshTokenExpiresAt.millisecondsSinceEpoch,
    authUserIdKey: session.userId,
    authPhoneKey: session.phone,
  };
}

void _expectNoLegacySession(SharedPreferences preferences) {
  for (final key in _legacyKeys) {
    expect(preferences.get(key), isNull, reason: key);
  }
}

void _expectLegacySession(
  SharedPreferences preferences,
  Map<String, Object> expected,
) {
  for (final entry in expected.entries) {
    expect(preferences.get(entry.key), entry.value, reason: entry.key);
  }
}

void _expectSession(AuthSession? actual, AuthSession expected) {
  expect(actual, isNotNull);
  expect(actual!.accessToken, expected.accessToken);
  expect(actual.refreshToken, expected.refreshToken);
  expect(
    actual.accessTokenExpiresAt.millisecondsSinceEpoch,
    expected.accessTokenExpiresAt.millisecondsSinceEpoch,
  );
  expect(
    actual.refreshTokenExpiresAt.millisecondsSinceEpoch,
    expected.refreshTokenExpiresAt.millisecondsSinceEpoch,
  );
  expect(actual.userId, expected.userId);
  expect(actual.phone, expected.phone);
}

AuthSession _session({
  String accessToken = 'access-secret',
  String refreshToken = 'refresh-secret',
  String userId = 'user-1',
  String phone = '13800000000',
  DateTime? accessExpiresAt,
  DateTime? refreshExpiresAt,
}) {
  final now = DateTime.now();
  return AuthSession(
    accessToken: accessToken,
    refreshToken: refreshToken,
    accessTokenExpiresAt:
        accessExpiresAt ?? now.add(const Duration(minutes: 30)),
    refreshTokenExpiresAt:
        refreshExpiresAt ?? now.add(const Duration(days: 30)),
    userId: userId,
    phone: phone,
  );
}

const _legacyKeys = [
  authAccessTokenKey,
  authRefreshTokenKey,
  authAccessTokenExpiresAtKey,
  authRefreshTokenExpiresAtKey,
  authUserIdKey,
  authPhoneKey,
];
