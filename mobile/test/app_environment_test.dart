import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'loads development environment from bundled env file by default',
    () async {
      final environment = await AppEnvironment.load();

      expect(environment.flavor, AppFlavor.development);
      expect(environment.apiBaseUrl, startsWith('http'));
      expect(environment.taskWebSocketBaseUrl, startsWith('ws'));
    },
  );
}
