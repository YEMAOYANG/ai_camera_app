import 'package:flutter_test/flutter_test.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/features/tasks/application/task_realtime_repository.dart';

void main() {
  test('task realtime uri uses configured websocket base url', () {
    const environment = AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      taskWebSocketBaseUrl: 'ws://127.0.0.1:8001/api',
      useMockData: false,
    );

    final uri = taskRealtimeUri(environment, 'access_token');

    expect(
      uri.toString(),
      'ws://127.0.0.1:8001/api/tasks/stream?token=access_token',
    );
  });

  test('task realtime uri can derive websocket scheme from api url', () {
    const environment = AppEnvironment(
      flavor: AppFlavor.staging,
      apiBaseUrl: 'https://app.example.com/api',
      useMockData: false,
    );

    final uri = taskRealtimeUri(environment, 'access_token');

    expect(
      uri.toString(),
      'wss://app.example.com/api/tasks/stream?token=access_token',
    );
  });
}
