import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

const authAccessTokenKey = 'auth.accessToken';
const authRefreshTokenKey = 'auth.refreshToken';
const authAccessTokenExpiresAtKey = 'auth.accessTokenExpiresAt';
const authRefreshTokenExpiresAtKey = 'auth.refreshTokenExpiresAt';
const authUserIdKey = 'auth.userId';
const authPhoneKey = 'auth.phone';

final authSessionStoreProvider = Provider<AuthSessionStore>((ref) {
  final store = AuthSessionStore(ref.watch(sharedPreferencesProvider));
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
  AuthSessionStore(this._preferences);

  final SharedPreferences _preferences;

  AuthSession? get currentSession {
    final accessToken = _preferences.getString(authAccessTokenKey) ?? '';
    final refreshToken = _preferences.getString(authRefreshTokenKey) ?? '';
    final accessExpiresAt = _preferences.getInt(authAccessTokenExpiresAtKey);
    final refreshExpiresAt = _preferences.getInt(authRefreshTokenExpiresAtKey);
    final userId = _preferences.getString(authUserIdKey) ?? '';
    final phone = _preferences.getString(authPhoneKey) ?? '';

    if (refreshToken.isEmpty ||
        accessExpiresAt == null ||
        refreshExpiresAt == null ||
        userId.isEmpty) {
      return null;
    }

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
  }

  bool get hasUsableSession {
    return currentSession?.canRefresh ?? false;
  }

  Future<void> save(AuthSession session) async {
    await _preferences.setString(authAccessTokenKey, session.accessToken);
    await _preferences.setString(authRefreshTokenKey, session.refreshToken);
    await _preferences.setInt(
      authAccessTokenExpiresAtKey,
      session.accessTokenExpiresAt.millisecondsSinceEpoch,
    );
    await _preferences.setInt(
      authRefreshTokenExpiresAtKey,
      session.refreshTokenExpiresAt.millisecondsSinceEpoch,
    );
    await _preferences.setString(authUserIdKey, session.userId);
    await _preferences.setString(authPhoneKey, session.phone);
    notifyListeners();
  }

  Future<void> clear() async {
    await _preferences.remove(authAccessTokenKey);
    await _preferences.remove(authRefreshTokenKey);
    await _preferences.remove(authAccessTokenExpiresAtKey);
    await _preferences.remove(authRefreshTokenExpiresAtKey);
    await _preferences.remove(authUserIdKey);
    await _preferences.remove(authPhoneKey);
    notifyListeners();
  }

  // Development reset if needed:
  // await ref.read(authSessionStoreProvider).clear();
}
