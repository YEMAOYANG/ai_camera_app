import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_scope.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';

void main() {
  test('camera events provider inserts observation.updated event immediately', () async {
    final container = ProviderContainer(
      overrides: [
        selectedDeviceProvider.overrideWith((ref) async => null),
        cameraRepositoryProvider.overrideWithValue(
          _FakeCameraRepository(const []),
        ),
      ],
    );
    addTearDown(container.dispose);

    final event = TaskRealtimeEvent.fromJson({
      'type': 'camera_observation.updated',
      'observationId': 'obs_1',
      'event': {
        'id': 'evt_phone',
        'source': 'camera_observation',
        'eventType': 'camera_observation',
        'displayTitle': '孩子正在玩手机',
        'displayMessage': '孩子在玩手机，注意休息。',
        'category': 'camera_observation',
        'severity': 'info',
        'tone': 'info',
        'createdAt': 1,
      },
      'sentAt': 2,
    });

    final notifier = container.read(cameraEventsProvider.notifier);
    notifier.handleRealtimeEvent(event);

    final items = container.read(cameraEventsProvider).value ?? const [];
    expect(items.length, 1);
    expect(items.first.displayTitle, '孩子正在玩手机');
    expect(items.first.displayMessage, '孩子在玩手机，注意休息。');
  });

  test(
    'camera events provider inserts realtime event without duplicates',
    () async {
      final container = ProviderContainer(
        overrides: [
          selectedDeviceProvider.overrideWith((ref) async => null),
          cameraRepositoryProvider.overrideWithValue(
            _FakeCameraRepository(const []),
          ),
        ],
      );
      addTearDown(container.dispose);

      expect(await container.read(cameraEventsProvider.future), isEmpty);

      final event = TaskRealtimeEvent.fromJson({
        'type': 'camera_event.created',
        'eventIds': ['evt_1'],
        'event': {
          'id': 'evt_1',
          'source': 'camera_observation',
          'eventType': 'camera_observation',
          'displayTitle': '孩子在看屏幕',
          'displayMessage': '孩子在看屏幕，注意用眼距离。',
          'category': 'camera_observation',
          'severity': 'info',
          'tone': 'info',
          'createdAt': 1,
        },
        'sentAt': 2,
      });

      final notifier = container.read(cameraEventsProvider.notifier);
      notifier.handleRealtimeEvent(event);
      notifier.handleRealtimeEvent(event);

      final items = container.read(cameraEventsProvider).value ?? const [];
      expect(items.length, 1);
      expect(items.first.id, 'evt_1');
      expect(items.first.displayMessage, '孩子在看屏幕，注意用眼距离。');
    },
  );

  test('camera events refresh failure keeps existing realtime list', () async {
    final repository = _FakeCameraRepository(const []);
    final container = ProviderContainer(
      overrides: [
        selectedDeviceProvider.overrideWith((ref) async => null),
        cameraRepositoryProvider.overrideWithValue(repository),
      ],
    );
    addTearDown(container.dispose);

    expect(await container.read(cameraEventsProvider.future), isEmpty);
    final notifier = container.read(cameraEventsProvider.notifier);
    notifier.handleRealtimeEvent(
      TaskRealtimeEvent.fromJson({
        'type': 'camera_event.created',
        'event': {
          'id': 'evt_2',
          'source': 'camera_observation',
          'eventType': 'camera_observation',
          'displayTitle': '画面暂时看不清',
          'displayMessage': '这次画面还不能判断孩子状态。',
          'category': 'camera_observation',
          'severity': 'warning',
          'tone': 'warning',
          'createdAt': 2,
        },
        'sentAt': 3,
      }),
    );

    repository.failEvents = true;
    await notifier.refresh();

    final items = container.read(cameraEventsProvider).value ?? const [];
    expect(items.map((item) => item.id), ['evt_2']);
  });

  test('coordinator observation update does not invalidate camera events list', () async {
    final container = ProviderContainer(
      overrides: [
        selectedDeviceProvider.overrideWith((ref) async => null),
        cameraRepositoryProvider.overrideWithValue(
          _FakeCameraRepository(const []),
        ),
      ],
    );
    addTearDown(container.dispose);

    expect(await container.read(cameraEventsProvider.future), isEmpty);
    final coordinator = container.read(appRealtimeInvalidationCoordinatorProvider);
    coordinator.handle(
      TaskRealtimeEvent.fromJson({
        'type': 'camera_observation.updated',
        'observationId': 'obs_2',
        'event': {
          'id': 'evt_live',
          'source': 'camera_observation',
          'eventType': 'camera_observation',
          'displayTitle': '孩子正在看书',
          'displayMessage': '孩子正在安静看书。',
          'category': 'camera_observation',
          'severity': 'info',
          'tone': 'info',
          'createdAt': 3,
        },
        'sentAt': 4,
      }),
    );

    final items = container.read(cameraEventsProvider).value ?? const [];
    expect(items.length, 1);
    expect(items.first.id, 'evt_live');

    await Future<void>.delayed(const Duration(milliseconds: 300));

    final after = container.read(cameraEventsProvider);
    expect(after.hasValue, isTrue);
    expect(after.value?.length, 1);
    expect(after.value?.first.id, 'evt_live');
  });

  test('LiveCareEvent parses recordKind for routine observations', () {
    final event = LiveCareEvent.fromJson({
      'id': 'evt_routine',
      'source': 'camera_command',
      'eventType': 'camera_observation',
      'displayTitle': '到晚餐时间',
      'displayMessage': '到晚餐时间，按家庭作息生成提醒。',
      'category': 'camera_observation',
      'severity': 'info',
      'tone': 'info',
      'recordKind': 'routine',
      'createdAt': DateTime.now().millisecondsSinceEpoch,
    });

    expect(event.isRoutineRecord, isTrue);
    expect(event.isVisionRecord, isFalse);
  });
}

class _FakeCameraRepository extends CameraRepository {
  _FakeCameraRepository(this._events)
    : super(apiClient: ApiClient(Dio()), dio: Dio());

  final List<LiveCareEvent> _events;
  bool failEvents = false;

  @override
  Future<List<LiveCareEvent>> events({String? deviceId}) async {
    if (failEvents) {
      throw const CameraException('暂时拿不到看护事件。');
    }
    return _events;
  }
}
