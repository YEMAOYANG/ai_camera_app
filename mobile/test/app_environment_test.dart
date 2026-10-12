import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'bootstrap honors explicit development and staging URLs and guards production debug',
    () async {
      final environment = await AppEnvironment.load();
      const definedFlavor = String.fromEnvironment('APP_FLAVOR');
      const definedApiUrl = String.fromEnvironment('API_BASE_URL');
      const definedWsUrl = String.fromEnvironment('TASK_WS_BASE_URL');
      const definedStudentUrl = String.fromEnvironment('STUDENT_WEB_BASE_URL');
      const allowProduction = bool.fromEnvironment(
        'APP_ALLOW_PRODUCTION_IN_DEBUG',
      );
      final ignoredProduction =
          definedFlavor == 'production' && !allowProduction;
      if (definedApiUrl.isNotEmpty && !ignoredProduction) {
        expect(environment.apiBaseUrl, definedApiUrl);
        expect(environment.taskWebSocketBaseUrl, definedWsUrl);
        expect(environment.studentWebBaseUrl, definedStudentUrl);
        expect(
          environment.flavor.name,
          definedFlavor.isEmpty ? 'development' : definedFlavor,
        );
      } else {
        expect(environment.flavor, AppFlavor.development);
        if (ignoredProduction) {
          expect(environment.apiBaseUrl, isNot(definedApiUrl));
        }
      }
      expect(environment.apiBaseUrl, startsWith('http'));
      expect(environment.taskWebSocketBaseUrl, startsWith('ws'));
      expect(environment.studentWebBaseUrl, startsWith('http'));
    },
  );

  test('production rejects plaintext API transport', () {
    expect(
      () => AppEnvironment(
        flavor: AppFlavor.production,
        apiBaseUrl: 'http://api.miraguardian.com/api',
        taskWebSocketBaseUrl: 'wss://realtime.miraguardian.com/api',
        studentWebBaseUrl: 'https://student.miraguardian.com',
      ),
      throwsA(isA<UnsupportedError>()),
    );
  });

  test('production rejects plaintext WebSocket and student web', () {
    for (final values in [
      (
        taskUrl: 'ws://realtime.miraguardian.com/api',
        studentUrl: 'https://student.miraguardian.com',
      ),
      (
        taskUrl: 'wss://realtime.miraguardian.com/api',
        studentUrl: 'http://student.miraguardian.com',
      ),
    ]) {
      expect(
        () => AppEnvironment(
          flavor: AppFlavor.production,
          apiBaseUrl: 'https://api.miraguardian.com/api',
          taskWebSocketBaseUrl: values.taskUrl,
          studentWebBaseUrl: values.studentUrl,
        ),
        throwsA(isA<UnsupportedError>()),
      );
    }
  });

  test(
    'production accepts HTTPS and WSS while development allows LAN HTTP',
    () {
      final production = AppEnvironment(
        flavor: AppFlavor.production,
        apiBaseUrl: 'https://api.miraguardian.com/api',
        taskWebSocketBaseUrl: 'wss://realtime.miraguardian.com/api',
        studentWebBaseUrl: 'https://student.miraguardian.com',
      );
      final development = AppEnvironment(
        flavor: AppFlavor.development,
        apiBaseUrl: 'http://192.168.1.8:8000/api',
        taskWebSocketBaseUrl: 'ws://192.168.1.8:8001/api',
        studentWebBaseUrl: 'http://192.168.1.8:3000',
      );

      expect(production.apiBaseUrl, startsWith('https://'));
      expect(development.studentWebBaseUrl, startsWith('http://'));
    },
  );

  test('production rejects non-public and obvious test hosts', () {
    const blockedAuthorities = [
      'api.example.invalid',
      'localhost',
      'localhost.',
      '127.0.0.1',
      '[::1]',
      'api.example.test',
      'test.miraguardian.com',
      'student.example.com',
      '10.0.0.8',
      '172.20.0.8',
      '192.168.1.8',
      '[fd00::8]',
    ];

    for (final authority in blockedAuthorities) {
      for (final service in ['api', 'websocket', 'student']) {
        final apiBaseUrl = service == 'api'
            ? 'https://$authority/api'
            : 'https://api.miraguardian.com/api';
        final taskWebSocketBaseUrl = service == 'websocket'
            ? 'wss://$authority/api'
            : 'wss://realtime.miraguardian.com/api';
        final studentWebBaseUrl = service == 'student'
            ? 'https://$authority'
            : 'https://student.miraguardian.com';

        expect(
          () => AppEnvironment(
            flavor: AppFlavor.production,
            apiBaseUrl: apiBaseUrl,
            taskWebSocketBaseUrl: taskWebSocketBaseUrl,
            studentWebBaseUrl: studentWebBaseUrl,
          ),
          throwsA(isA<UnsupportedError>()),
          reason: '$service must reject $authority in production',
        );
      }
    }
  });

  test('development continues to allow local and placeholder hosts', () {
    final development = AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://localhost:8000/api',
      taskWebSocketBaseUrl: 'ws://192.168.1.8:8001/api',
      studentWebBaseUrl: 'http://student.example.invalid:3000',
    );

    expect(development.apiBaseUrl, 'http://localhost:8000/api');
    expect(development.taskWebSocketBaseUrl, 'ws://192.168.1.8:8001/api');
    expect(
      development.studentWebBaseUrl,
      'http://student.example.invalid:3000',
    );
  });
}
