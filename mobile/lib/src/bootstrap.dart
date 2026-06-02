import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/app/app.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';

Future<void> bootstrap(AppEnvironment environment) async {
  runApp(
    ProviderScope(
      overrides: [appEnvironmentProvider.overrideWithValue(environment)],
      child: const MiraGuardianApp(),
    ),
  );
}
