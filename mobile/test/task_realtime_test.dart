import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/features/auth/application/account_security_realtime_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';

void main() {
  test('task realtime uri uses configured websocket base url', () {
    final environment = AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      taskWebSocketBaseUrl: 'ws://127.0.0.1:8001/api',
    );

    final uri = taskRealtimeUri(environment, 'access_token');

    expect(
      uri.toString(),
      'ws://127.0.0.1:8001/api/tasks/stream?token=access_token',
    );
  });

  test('task realtime uri can derive websocket scheme from api url', () {
    final environment = AppEnvironment(
      flavor: AppFlavor.staging,
      apiBaseUrl: 'https://app.example.com/api',
    );

    final uri = taskRealtimeUri(environment, 'access_token');

    expect(
      uri.toString(),
      'wss://app.example.com/api/tasks/stream?token=access_token',
    );
  });

  test('account security realtime uri uses configured websocket base url', () {
    final environment = AppEnvironment(
      flavor: AppFlavor.development,
      apiBaseUrl: 'http://127.0.0.1:8000/api',
      taskWebSocketBaseUrl: 'ws://127.0.0.1:8001/api',
    );

    final uri = accountSecurityRealtimeUri(environment, 'access_token');

    expect(
      uri.toString(),
      'ws://127.0.0.1:8001/api/account/security/stream?token=access_token',
    );
  });

  test('account security realtime parses revoked session event', () {
    final event = AccountSecurityRealtimeEvent.tryParse(
      '{"type":"session_revoked","reason":"device_removed","message":"已移除","sentAt":123}',
    );

    expect(event?.isSessionRevoked, isTrue);
    expect(event?.reason, 'device_removed');
    expect(event?.message, '已移除');
    expect(event?.sentAt, 123);
  });
}
