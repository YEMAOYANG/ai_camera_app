import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/app/app.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/core/storage/onboarding_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> bootstrap(AppEnvironment environment) async {
  final sharedPreferences = await SharedPreferences.getInstance();

  runApp(
    ProviderScope(
      overrides: [
        appEnvironmentProvider.overrideWithValue(environment),
        sharedPreferencesProvider.overrideWithValue(sharedPreferences),
      ],
      child: const GuardianApp(),
    ),
  );
}
