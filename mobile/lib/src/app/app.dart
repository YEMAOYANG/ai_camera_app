import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/app/router/app_router.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/auth/application/account_security_realtime_repository.dart';
import 'package:warm_sight/src/features/auth/application/session_data_invalidation.dart';

class GuardianApp extends ConsumerWidget {
  const GuardianApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);

    return _AccountSecurityRealtimeGate(
      child: MaterialApp.router(
        title: '暖瞳',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        routerConfig: router,
      ),
    );
  }
}

class _AccountSecurityRealtimeGate extends ConsumerStatefulWidget {
  const _AccountSecurityRealtimeGate({required this.child});

  final Widget child;

  @override
  ConsumerState<_AccountSecurityRealtimeGate> createState() {
    return _AccountSecurityRealtimeGateState();
  }
}

class _AccountSecurityRealtimeGateState
    extends ConsumerState<_AccountSecurityRealtimeGate> {
  AuthSessionStore? _sessionStore;
  WebSocket? _socket;
  Timer? _reconnectTimer;
  String _activeToken = '';
  int _generation = 0;

  @override
  Widget build(BuildContext context) {
    final sessionStore = ref.watch(authSessionStoreProvider);
    if (!identical(_sessionStore, sessionStore)) {
      _sessionStore?.removeListener(_syncWithSession);
      _sessionStore = sessionStore..addListener(_syncWithSession);
      scheduleMicrotask(_syncWithSession);
    }
    return widget.child;
  }

  @override
  void dispose() {
    _generation++;
    _sessionStore?.removeListener(_syncWithSession);
    _reconnectTimer?.cancel();
    unawaited(_socket?.close());
    super.dispose();
  }

  void _syncWithSession() {
    final token = _sessionStore?.currentSession?.accessToken ?? '';
    if (token == _activeToken) return;

    _generation++;
    _activeToken = token;
    _reconnectTimer?.cancel();
    final socket = _socket;
    _socket = null;
    unawaited(socket?.close());

    if (token.isNotEmpty) {
      unawaited(_connect(_generation, token));
    }
  }

  Future<void> _connect(int generation, String token) async {
    final uri = accountSecurityRealtimeUri(
      ref.read(appEnvironmentProvider),
      token,
    );
    if (uri == null) return;

    WebSocket? socket;
    try {
      socket = await WebSocket.connect(
        uri.toString(),
      ).timeout(const Duration(seconds: 8));
      if (!_isCurrent(generation, token)) {
        unawaited(socket.close());
        return;
      }
      _socket = socket;
      socket.pingInterval = const Duration(seconds: 25);
      await for (final message in socket) {
        if (!_isCurrent(generation, token)) break;
        final event = AccountSecurityRealtimeEvent.tryParse(message);
        if (event?.isSessionRevoked ?? false) {
          await _handleSessionRevoked();
          break;
        }
      }
    } catch (_) {
      if (!_isCurrent(generation, token)) return;
    } finally {
      if (identical(_socket, socket)) {
        _socket = null;
      }
      unawaited(socket?.close());
    }

    if (_isCurrent(generation, token)) {
      _scheduleReconnect(generation, token);
    }
  }

  Future<void> _handleSessionRevoked() async {
    await ref.read(authSessionStoreProvider).clear();
    invalidateAuthenticatedSessionData(ref);
  }

  void _scheduleReconnect(int generation, String token) {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), () {
      if (_isCurrent(generation, token)) {
        unawaited(_connect(generation, token));
      }
    });
  }

  bool _isCurrent(int generation, String token) {
    return mounted && generation == _generation && token == _activeToken;
  }
}
