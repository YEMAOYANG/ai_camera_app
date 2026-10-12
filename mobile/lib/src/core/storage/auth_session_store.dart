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
  Future<void> _persistence = Future<void>.value();
  Future<AuthSession?>? _refreshing;
  int? _refreshGeneration;
  int? _pendingSessionGeneration;
  int _generation = 0;

  AuthSession? get currentSession =>
      _pendingSessionGeneration == _generation ? null : _currentSession;
  int get generation => _generation;
  Future<AuthSession?>? get pendingRefresh => _refreshing;

  bool isCurrent(AuthSession session, int generation) =>
      generation == _generation && identical(session, currentSession);

  bool get hasUsableSession => currentSession?.canRefresh ?? false;

  Future<void> initialize() {
    final generation = _generation;
    return _initialization ??= _serialize(() => _initialize(generation));
  }

  Future<void> _initialize(int generation) async {
    if (generation != _generation) return;
    String? secureEnvelope;
    try {
      secureEnvelope = await secureStorage.read();
    } catch (_) {
      if (generation == _generation) {
        _currentSession = _readCompleteLegacySession();
      }
      return;
    }
    if (generation != _generation) return;

    if (secureEnvelope != null) {
      final secureSession = _decodeEnvelope(secureEnvelope);
      if (secureSession == null) {
        // A present but invalid secure record must not be combined with or
        // replaced by replayable legacy fields.
        _currentSession = null;
        return;
      }
      _currentSession = secureSession;
      await _removeLegacySessionAfterCommit();
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
    await _removeLegacySessionAfterCommit();
  }

  Future<bool> save(
    AuthSession session, {
    int? expectedGeneration,
    Future<void> Function()? beforeSave,
  }) {
    final envelope = _encodeEnvelope(session);
    if (expectedGeneration != null && expectedGeneration != _generation) {
      return Future<bool>.value(false);
    }
    final generation = ++_generation;
    _pendingSessionGeneration = generation;
    return _serialize(() async {
      try {
        if (generation != _generation) return false;
        await beforeSave?.call();
        if (generation != _generation) return false;
        await secureStorage.write(envelope);
        // A later clear/save is queued behind this write. Never publish its
        // superseded account, even while that next disk operation is pending.
        if (generation == _generation) {
          _currentSession = session;
          _pendingSessionGeneration = null;
          notifyListeners();
        }
        await _removeLegacySessionAfterCommit();
        return isCurrent(session, generation);
      } finally {
        if (_pendingSessionGeneration == generation) {
          _pendingSessionGeneration = null;
          if (generation == _generation) notifyListeners();
        }
      }
    });
  }

  Future<void> clear({Future<void> Function()? clearAccountDraft}) {
    // Stop authenticated work immediately; slow Keychain/Keystore operations
    // must not leave the old account available to requests or refresh replies.
    _generation++;
    _pendingSessionGeneration = null;
    _currentSession = null;
    notifyListeners();
    return _serialize(() async {
      try {
        await secureStorage.delete();
      } finally {
        try {
          await _removeLegacySession();
        } finally {
          await clearAccountDraft?.call();
        }
      }
    });
  }

  Future<void> clearIfCurrent(AuthSession session, int generation) {
    return isCurrent(session, generation) ? clear() : Future<void>.value();
  }

  /// All refresh entry points share one request per signed-in generation.
  /// Discarded credentials still need remote revocation: the server may have
  /// already rotated the session before logout reached it with the old token.
  Future<AuthSession?> refreshSession({
    required Future<AuthSession> Function(AuthSession session) load,
    required Future<void> Function(AuthSession session) discard,
  }) {
    final session = currentSession;
    if (session == null) return Future<AuthSession?>.value();
    final generation = _generation;
    final pending = _refreshing;
    if (pending != null && _refreshGeneration == generation) return pending;

    late final Future<AuthSession?> future;
    future =
        () async {
          final refreshed = await load(session);
          final bool saved;
          try {
            saved = await _serialize(() async {
              if (!isCurrent(session, generation)) return false;
              await secureStorage.write(_encodeEnvelope(refreshed));
              if (!isCurrent(session, generation)) return false;
              _currentSession = refreshed;
              notifyListeners();
              await _removeLegacySessionAfterCommit();
              return isCurrent(refreshed, generation);
            });
          } catch (_) {
            await discard(refreshed);
            rethrow;
          }
          if (!saved) {
            await discard(refreshed);
            return null;
          }
          return refreshed;
        }().whenComplete(() {
          if (identical(_refreshing, future)) {
            _refreshing = null;
            _refreshGeneration = null;
          }
        });
    _refreshGeneration = generation;
    _refreshing = future;
    return future;
  }

  Future<T> _serialize<T>(Future<T> Function() operation) {
    final result = _persistence.then((_) => operation());
    // Keep the queue usable after a failed platform storage operation while
    // preserving that error for the caller that owns the failed operation.
    _persistence = result.then<void>(
      (_) {},
      onError: (Object _, StackTrace _) {},
    );
    return result;
  }

  @override
  void dispose() {
    _generation++;
    super.dispose();
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

  Future<void> _removeLegacySessionAfterCommit() async {
    try {
      await _removeLegacySession();
    } catch (_) {
      // The secure envelope is already authoritative. Failing to remove old
      // preferences must not roll back or revoke that committed session.
      debugPrint('Legacy session metadata cleanup is pending.');
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
