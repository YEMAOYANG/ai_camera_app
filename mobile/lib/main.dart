import 'package:flutter/widgets.dart';
import 'package:guardian_parent_app/src/bootstrap.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await bootstrap(await AppEnvironment.load());
}
