import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/app/app.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> bootstrap(AppEnvironment environment) async {
  final sharedPreferences = await SharedPreferences.getInstance();
  final authSessionStore = AuthSessionStore(sharedPreferences);
  await authSessionStore.initialize();
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SystemChrome.setSystemUIOverlayStyle(AppSystemUi.light());

  runApp(
    ProviderScope(
      overrides: [
        appEnvironmentProvider.overrideWithValue(environment),
        sharedPreferencesProvider.overrideWithValue(sharedPreferences),
        authSessionStoreProvider.overrideWithValue(authSessionStore),
      ],
      child: const GuardianApp(),
    ),
  );
}
