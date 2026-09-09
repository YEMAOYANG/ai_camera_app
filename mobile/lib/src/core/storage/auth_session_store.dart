import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/storage/auth_token_storage.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';

const authAccessTokenKey = 'auth.accessToken';
const authRefreshTokenKey = 'auth.refreshToken';
const authAccessTokenExpiresAtKey = 'auth.accessTokenExpiresAt';
const authRefreshTokenExpiresAtKey = 'auth.refreshTokenExpiresAt';
const authUserIdKey = 'auth.userId';
const authPhoneKey = 'auth.phone';

const authSessionEnvelopeSchema = 'mira.auth.session';
const authSessionEnvelopeVersion = 1;

final authSecureSessionStorageProvider = Provider<AuthSecureSessionStorage>((
  ref,
) {
  return const FlutterSecureAuthSessionStorage();
});

final authSessionStoreProvider = Provider<AuthSessionStore>((ref) {
  final store = AuthSessionStore(
    ref.watch(sharedPreferencesProvider),
    secureStorage: ref.watch(authSecureSessionStorageProvider),
  );
  ref.onDispose(store.dispose);
  return store;
});

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.accessTokenExpiresAt,
    required this.refreshTokenExpiresAt,
    required this.userId,
    required this.phone,
  });

  final String accessToken;
  final String refreshToken;
  final DateTime accessTokenExpiresAt;
  final DateTime refreshTokenExpiresAt;
  final String userId;
  final String phone;

  bool get hasAccessToken {
    return accessToken.isNotEmpty &&
        accessTokenExpiresAt.isAfter(
          DateTime.now().add(const Duration(seconds: 20)),
        );
  }

  bool get canRefresh {
    return refreshToken.isNotEmpty &&
        refreshTokenExpiresAt.isAfter(
          DateTime.now().add(const Duration(minutes: 1)),
        );
  }

  AuthSession copyWith({
    String? accessToken,
    String? refreshToken,
    DateTime? accessTokenExpiresAt,
    DateTime? refreshTokenExpiresAt,
    String? userId,
    String? phone,
  }) {
    return AuthSession(
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      accessTokenExpiresAt: accessTokenExpiresAt ?? this.accessTokenExpiresAt,
      refreshTokenExpiresAt:
          refreshTokenExpiresAt ?? this.refreshTokenExpiresAt,
      userId: userId ?? this.userId,
      phone: phone ?? this.phone,
    );
  }
}

class AuthSessionStore extends ChangeNotifier {
  AuthSessionStore(
    this._preferences, {
    this.secureStorage = const FlutterSecureAuthSessionStorage(),
  });

  final SharedPreferences _preferences;
  final AuthSecureSessionStorage secureStorage;
  AuthSession? _currentSession;
  Future<void>? _initialization;

  AuthSession? get currentSession => _currentSession;

  bool get hasUsableSession => _currentSession?.canRefresh ?? false;

  Future<void> initialize() {
    return _initialization ??= _initialize();
  }

  Future<void> _initialize() async {
    String? secureEnvelope;
    try {
      secureEnvelope = await secureStorage.read();
    } catch (_) {
      _currentSession = _readCompleteLegacySession();
      return;
    }

    if (secureEnvelope != null) {
      final secureSession = _decodeEnvelope(secureEnvelope);
      if (secureSession == null) {
        // A present but invalid secure record must not be combined with or
        // replaced by replayable legacy fields.
        _currentSession = null;
        return;
      }
      _currentSession = secureSession;
      await _removeLegacySession();
      return;
    }

    final legacySession = _readCompleteLegacySession();
    if (legacySession == null) {
      _currentSession = null;
      return;
    }

    // Keep the complete legacy v0 session in memory until its one secure write
    // succeeds. A Keychain/Keystore write failure must not sign out the family
    // or remove the only recoverable copy.
    _currentSession = legacySession;
    try {
      await secureStorage.write(_encodeEnvelope(legacySession));
    } catch (_) {
      return;
    }
    await _removeLegacySession();
  }

  Future<void> save(AuthSession session) async {
    final envelope = _encodeEnvelope(session);
    await secureStorage.write(envelope);

    // Publish only after the single atomic secure write has succeeded.
    _currentSession = session;
    try {
      await _removeLegacySession();
    } finally {
      notifyListeners();
    }
  }

  Future<void> clear() async {
    Object? secureStorageError;
    StackTrace? secureStorageStackTrace;
    try {
      await secureStorage.delete();
    } catch (error, stackTrace) {
      secureStorageError = error;
      secureStorageStackTrace = stackTrace;
    }

    await _removeLegacySession();
    _currentSession = null;
    notifyListeners();

    if (secureStorageError != null) {
      Error.throwWithStackTrace(secureStorageError, secureStorageStackTrace!);
    }
  }

  AuthSession? _readCompleteLegacySession() {
    final accessToken = _preferences.get(authAccessTokenKey);
    final refreshToken = _preferences.get(authRefreshTokenKey);
    final accessExpiresAt = _preferences.get(authAccessTokenExpiresAtKey);
    final refreshExpiresAt = _preferences.get(authRefreshTokenExpiresAtKey);
    final userId = _preferences.get(authUserIdKey);
    final phone = _preferences.get(authPhoneKey);

    if (accessToken is! String ||
        accessToken.isEmpty ||
        refreshToken is! String ||
        refreshToken.isEmpty ||
        accessExpiresAt is! int ||
        accessExpiresAt <= 0 ||
        refreshExpiresAt is! int ||
        refreshExpiresAt <= 0 ||
        userId is! String ||
        userId.isEmpty ||
        phone is! String ||
        phone.isEmpty) {
      return null;
    }

    try {
      return AuthSession(
        accessToken: accessToken,
        refreshToken: refreshToken,
        accessTokenExpiresAt: DateTime.fromMillisecondsSinceEpoch(
          accessExpiresAt,
        ),
        refreshTokenExpiresAt: DateTime.fromMillisecondsSinceEpoch(
          refreshExpiresAt,
        ),
        userId: userId,
        phone: phone,
      );
    } on ArgumentError {
      return null;
    }
  }

  String _encodeEnvelope(AuthSession session) {
    final accessExpiresAt = session.accessTokenExpiresAt.millisecondsSinceEpoch;
    final refreshExpiresAt =
        session.refreshTokenExpiresAt.millisecondsSinceEpoch;
    if (session.accessToken.isEmpty ||
        session.refreshToken.isEmpty ||
        accessExpiresAt <= 0 ||
        refreshExpiresAt <= 0 ||
        session.userId.isEmpty ||
        session.phone.isEmpty) {
      throw ArgumentError('Auth session envelope fields must be complete.');
    }

    return jsonEncode({
      'schema': authSessionEnvelopeSchema,
      'version': authSessionEnvelopeVersion,
      'accessToken': session.accessToken,
      'refreshToken': session.refreshToken,
      'accessTokenExpiresAt': accessExpiresAt,
      'refreshTokenExpiresAt': refreshExpiresAt,
      'userId': session.userId,
      'phone': session.phone,
    });
  }

  AuthSession? _decodeEnvelope(String envelope) {
    dynamic decoded;
    try {
      decoded = jsonDecode(envelope);
    } on FormatException {
      return null;
    }
    if (decoded is! Map<String, dynamic>) return null;
    if (decoded.length != _envelopeFields.length ||
        !_envelopeFields.every(decoded.containsKey)) {
      return null;
    }
    if (decoded['schema'] != authSessionEnvelopeSchema ||
        decoded['version'] != authSessionEnvelopeVersion) {
      return null;
    }

    final accessToken = decoded['accessToken'];
    final refreshToken = decoded['refreshToken'];
    final accessExpiresAt = decoded['accessTokenExpiresAt'];
    final refreshExpiresAt = decoded['refreshTokenExpiresAt'];
    final userId = decoded['userId'];
    final phone = decoded['phone'];
    if (accessToken is! String ||
        accessToken.isEmpty ||
        refreshToken is! String ||
        refreshToken.isEmpty ||
        accessExpiresAt is! int ||
        accessExpiresAt <= 0 ||
        refreshExpiresAt is! int ||
        refreshExpiresAt <= 0 ||
        userId is! String ||
        userId.isEmpty ||
        phone is! String ||
        phone.isEmpty) {
      return null;
    }

    try {
      return AuthSession(
        accessToken: accessToken,
        refreshToken: refreshToken,
        accessTokenExpiresAt: DateTime.fromMillisecondsSinceEpoch(
          accessExpiresAt,
        ),
        refreshTokenExpiresAt: DateTime.fromMillisecondsSinceEpoch(
          refreshExpiresAt,
        ),
        userId: userId,
        phone: phone,
      );
    } on ArgumentError {
      return null;
    }
  }

  Future<void> _removeLegacySession() async {
    for (final key in _legacySessionKeys) {
      await _preferences.remove(key);
    }
  }

  // Development reset if needed:
  // await ref.read(authSessionStoreProvider).clear();
}

const _envelopeFields = {
  'schema',
  'version',
  'accessToken',
  'refreshToken',
  'accessTokenExpiresAt',
  'refreshTokenExpiresAt',
  'userId',
  'phone',
};

const _legacySessionKeys = [
  authAccessTokenKey,
  authRefreshTokenKey,
  authAccessTokenExpiresAtKey,
  authRefreshTokenExpiresAtKey,
  authUserIdKey,
  authPhoneKey,
];
