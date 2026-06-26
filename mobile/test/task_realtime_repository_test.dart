import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';

void main() {
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
}
