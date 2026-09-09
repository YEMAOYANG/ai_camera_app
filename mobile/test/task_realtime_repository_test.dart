import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';
import 'support/fake_auth_token_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('parses camera observation realtime event as lightweight payload', () {
    final event = TaskRealtimeEvent.fromJson({
      'type': 'camera_observation.updated',
      'deviceId': 'dev_1',
      'observationId': 'obs_1',
      'isReliable': true,
      'source': 'camera_monitor',
      'sentAt': 1780000000000,
      'image': 'should-not-be-used',
    });

    expect(event.isCameraObservationUpdated, isTrue);
    expect(event.deviceId, 'dev_1');
    expect(event.observationId, 'obs_1');
    expect(event.isReliable, isTrue);
    expect(event.isTaskUpdate, isFalse);
  });

  test('parses task status change and camera status change events', () {
    final taskEvent = TaskRealtimeEvent.fromJson({
      'type': 'task_status.changed',
      'taskIds': ['task_1'],
      'eventIds': ['event_1'],
      'sentAt': 1780000000000,
    });
    final cameraStatusEvent = TaskRealtimeEvent.fromJson({
      'type': 'camera_status.changed',
      'deviceId': 'dev_1',
      'sentAt': 1780000000001,
    });

    expect(taskEvent.isTaskStatusChanged, isTrue);
    expect(taskEvent.taskIds, ['task_1']);
    expect(taskEvent.eventIds, ['event_1']);
    expect(cameraStatusEvent.isCameraStatusChanged, isTrue);
  });

  test('unknown realtime event is ignored by typed helpers', () {
    final event = TaskRealtimeEvent.fromJson({
      'type': 'unknown.event',
      'sentAt': 1780000000000,
    });

    expect(event.isTaskUpdate, isFalse);
    expect(event.isTaskStatusChanged, isFalse);
    expect(event.isCameraObservationUpdated, isFalse);
    expect(event.isCameraEventCreated, isFalse);
    expect(event.isCameraStatusChanged, isFalse);
  });

  test('parses lightweight camera event payload', () {
    final event = TaskRealtimeEvent.fromJson({
      'type': 'camera_event.created',
      'deviceId': 'dev_1',
      'eventIds': ['evt_1'],
      'event': {
        'id': 'evt_1',
        'displayTitle': '孩子在看屏幕',
        'displayMessage': '孩子在看屏幕，注意用眼距离。',
        'category': 'camera_observation',
        'createdAt': 1780000000000,
      },
      'sentAt': 1780000000001,
      'base64': 'should-not-be-used',
    });

    expect(event.isCameraEventCreated, isTrue);
    expect(event.event?['id'], 'evt_1');
    expect(event.event?['displayMessage'], contains('注意用眼距离'));
    expect(event.event?.containsKey('base64'), isFalse);
  });

  test('global realtime controller follows session lifecycle once', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final sessionStore = AuthSessionStore(
      preferences,
      secureStorage: FakeAuthSecureSessionStorage(),
    );
    final sockets = <_FakeWebSocket>[];
    final controller = AppRealtimeController(
      environment: AppEnvironment(
        flavor: AppFlavor.development,
        apiBaseUrl: 'http://127.0.0.1:8000/api',
        taskWebSocketBaseUrl: 'ws://127.0.0.1:8001/api',
      ),
      sessionStore: sessionStore,
      connectSocket: (uri) async {
        final socket = _FakeWebSocket();
        sockets.add(socket);
        return socket;
      },
    );

    controller.start();
    await Future<void>.delayed(Duration.zero);
    expect(sockets, isEmpty);

    final firstSession = _session('token_a');
    await sessionStore.save(firstSession);
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(sockets.length, 1);

    final subA = controller.events.listen((_) {});
    final subB = controller.events.listen((_) {});
    await Future<void>.delayed(Duration.zero);
    expect(sockets.length, 1);

    await sessionStore.save(_session('token_b'));
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    expect(sockets.length, 2);
    expect(sockets.first.closeCount, greaterThanOrEqualTo(1));

    await sessionStore.clear();
    await Future<void>.delayed(Duration.zero);
    expect(sockets.last.closeCount, greaterThanOrEqualTo(1));

    await subA.cancel();
    await subB.cancel();
    controller.dispose();
  });
}

AuthSession _session(String token) {
  final now = DateTime.now();
  return AuthSession(
    accessToken: token,
    refreshToken: 'refresh_$token',
    accessTokenExpiresAt: now.add(const Duration(minutes: 30)),
    refreshTokenExpiresAt: now.add(const Duration(days: 7)),
    userId: 'user_$token',
    phone: '13800000000',
  );
}

class _FakeWebSocket extends Stream<dynamic> implements WebSocket {
  final _controller = StreamController<dynamic>();
  var closeCount = 0;

  @override
  Duration? pingInterval;

  @override
  Future close([int? code, String? reason]) {
    closeCount += 1;
    if (!_controller.isClosed) {
      return _controller.close();
    }
    return Future<void>.value();
  }

  @override
  StreamSubscription<dynamic> listen(
    void Function(dynamic event)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return _controller.stream.listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
