import 'package:flutter/widgets.dart';
import 'package:warm_sight/src/bootstrap.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/shared/widgets/app_glass_surface.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeAppGlass();

  await bootstrap(await AppEnvironment.load());
}
