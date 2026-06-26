import 'package:flutter/widgets.dart';
import 'package:warm_sight/src/bootstrap.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await bootstrap(await AppEnvironment.load());
}
