import 'package:flutter/widgets.dart';
import 'package:mira_guardian_app/src/bootstrap.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await bootstrap(AppEnvironment.development());
}
