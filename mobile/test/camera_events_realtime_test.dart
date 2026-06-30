import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_helpers.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_scope.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/care/application/parent_review_realtime.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/live_care/presentation/live_care_screen.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';

void main() {
  test(
    'camera events provider inserts observation.updated event immediately',
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

      final state = container.read(cameraEventsProvider).value;
      expect(state?.items.length, 1);
      expect(state!.items.first.displayTitle, '孩子正在玩手机');
      expect(state.items.first.displayMessage, '孩子在玩手机，注意休息。');
    },
  );

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

      expect(
        (await container.read(cameraEventsProvider.future)).items,
        isEmpty,
      );

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

      final state = container.read(cameraEventsProvider).value;
      expect(state?.items.length, 1);
      expect(state!.items.first.id, 'evt_1');
      expect(state.items.first.displayMessage, '孩子在看屏幕，注意用眼距离。');
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

    expect((await container.read(cameraEventsProvider.future)).items, isEmpty);
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

    final state = container.read(cameraEventsProvider).value;
    expect(state?.items.map((item) => item.id), ['evt_2']);
  });

  test('camera events loadMore appends next page', () async {
    final events = List<LiveCareEvent>.generate(
      12,
      (index) => LiveCareEvent(
        id: 'evt_$index',
        source: 'camera_observation',
        eventType: 'camera_observation',
        title: '记录 $index',
        message: '记录 $index',
        displayTitle: '记录 $index',
        displayMessage: '记录 $index',
        category: 'camera_observation',
        severity: 'info',
        taskTitle: '',
        evidenceSummary: '',
        hasReplay: false,
        status: 'ok',
        toneKey: 'info',
        createdAt: index,
      ),
    );
    final repository = _FakeCameraRepository(events);
    final container = ProviderContainer(
      overrides: [
        selectedDeviceProvider.overrideWith((ref) async => null),
        cameraRepositoryProvider.overrideWithValue(repository),
      ],
    );
    addTearDown(container.dispose);

    final firstPage = await container.read(cameraEventsProvider.future);
    expect(firstPage.items.length, 10);
    expect(firstPage.hasMore, isTrue);

    await container.read(cameraEventsProvider.notifier).loadMore();
    final merged = container.read(cameraEventsProvider).value!;
    expect(merged.items.length, 12);
    expect(merged.hasMore, isFalse);
  });

  test(
    'camera events loadMore merges duplicate ids from realtime inserts',
    () async {
      final events = List<LiveCareEvent>.generate(
        12,
        (index) => LiveCareEvent(
          id: 'evt_$index',
          source: 'camera_observation',
          eventType: 'camera_observation',
          title: '记录 $index',
          message: '记录 $index',
          displayTitle: '记录 $index',
          displayMessage: '记录 $index',
          category: 'camera_observation',
          severity: 'info',
          taskTitle: '',
          evidenceSummary: '',
          hasReplay: false,
          status: 'ok',
          toneKey: 'info',
          createdAt: 1000 - index,
        ),
      );
      final repository = _FakeCameraRepository(events);
      final container = ProviderContainer(
        overrides: [
          selectedDeviceProvider.overrideWith((ref) async => null),
          cameraRepositoryProvider.overrideWithValue(repository),
        ],
      );
      addTearDown(container.dispose);

      final firstPage = await container.read(cameraEventsProvider.future);
      expect(firstPage.items.length, 10);
      container
          .read(cameraEventsProvider.notifier)
          .handleRealtimeEvent(
            TaskRealtimeEvent.fromJson({
              'type': 'camera_event.created',
              'event': {
                'id': 'evt_10',
                'source': 'camera_observation',
                'eventType': 'camera_observation',
                'displayTitle': '记录 10',
                'displayMessage': '记录 10',
                'category': 'camera_observation',
                'severity': 'info',
                'tone': 'info',
                'createdAt': 990,
              },
              'sentAt': 1,
            }),
          );

      await container.read(cameraEventsProvider.notifier).loadMore();
      final merged = container.read(cameraEventsProvider).value!;

      expect(
        merged.items.map((item) => item.id).toSet().length,
        merged.items.length,
      );
      expect(merged.items.where((item) => item.id == 'evt_10'), hasLength(1));
      expect(merged.items.map((item) => item.id), contains('evt_11'));
    },
  );

  test(
    'camera events refresh replaces previous page instead of merging',
    () async {
      final repository = _FakeCameraRepository([_event('evt_old', 10)]);
      final container = ProviderContainer(
        overrides: [
          selectedDeviceProvider.overrideWith((ref) async => null),
          cameraRepositoryProvider.overrideWithValue(repository),
        ],
      );
      addTearDown(container.dispose);

      expect(
        (await container.read(cameraEventsProvider.future)).items.single.id,
        'evt_old',
      );

      repository.eventItems = [_event('evt_new', 100)];
      await container.read(cameraEventsProvider.notifier).refresh();
      final refreshed = container.read(cameraEventsProvider).value!;

      expect(refreshed.items.length, 1);
      expect(refreshed.items.single.id, 'evt_new');
    },
  );

  test(
    'camera events refresh can restore hasMore after a no-more state',
    () async {
      final repository = _FakeCameraRepository([
        _event('evt_0', 30),
        _event('evt_1', 20),
      ]);
      final container = ProviderContainer(
        overrides: [
          selectedDeviceProvider.overrideWith((ref) async => null),
          cameraRepositoryProvider.overrideWithValue(repository),
        ],
      );
      addTearDown(container.dispose);

      final firstPage = await container.read(cameraEventsProvider.future);
      expect(firstPage.hasMore, isFalse);

      repository.eventItems = List<LiveCareEvent>.generate(
        12,
        (index) => _event('evt_$index', 100 - index),
      );
      await container.read(cameraEventsProvider.notifier).refresh();
      final refreshed = container.read(cameraEventsProvider).value!;
      expect(refreshed.hasMore, isTrue);

      final hasMoreAfterLoad = await container
          .read(cameraEventsProvider.notifier)
          .loadMore();
      expect(hasMoreAfterLoad, isFalse);
      expect(container.read(cameraEventsProvider).value?.items.length, 12);
    },
  );

  test(
    'coordinator observation update does not invalidate camera events list',
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

      expect(
        (await container.read(cameraEventsProvider.future)).items,
        isEmpty,
      );
      final coordinator = container.read(
        appRealtimeInvalidationCoordinatorProvider,
      );
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

      final state = container.read(cameraEventsProvider).value;
      expect(state?.items.length, 1);
      expect(state!.items.first.id, 'evt_live');

      await Future<void>.delayed(const Duration(milliseconds: 300));

      final after = container.read(cameraEventsProvider);
      expect(after.hasValue, isTrue);
      expect(after.value?.items.length, 1);
      expect(after.value?.items.first.id, 'evt_live');
    },
  );

  test(
    'reminder_decision with reviewItem inserts optimistic parent review',
    () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      applyReminderDecisionRealtimeEvent(
        container,
        TaskRealtimeEvent.fromJson({
          'type': 'reminder_decision.created',
          'event': {
            'id': 'rev_1',
            'status': 'pending',
            'summary': '需要家长确认',
            'reviewType': 'bedtime',
            'createdAt': 1,
          },
          'sentAt': 1,
        }),
      );

      final items = container.read(pendingParentReviewsOverrideProvider);
      expect(items.length, 1);
      expect(items.first.id, 'rev_1');
    },
  );

  test(
    'coordinator reminder_decision.created schedules care refresh without clearing events',
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

      expect(
        (await container.read(cameraEventsProvider.future)).items,
        isEmpty,
      );
      final coordinator = container.read(
        appRealtimeInvalidationCoordinatorProvider,
      );
      coordinator.handle(
        TaskRealtimeEvent.fromJson({
          'type': 'reminder_decision.created',
          'sentAt': 1,
        }),
      );

      await Future<void>.delayed(const Duration(milliseconds: 300));

      final after = container.read(cameraEventsProvider);
      expect(after.hasValue, isTrue);
      expect(after.value?.items, isEmpty);
    },
  );

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
    expect(event.recordCategoryLabel, '作息提醒');
  });

  test('LiveCareEvent classifies care record labels by recordKind and scenario', () {
    final vision = LiveCareEvent.fromJson({
      'id': 'evt_vision',
      'eventType': 'camera_observation',
      'displayTitle': '看到孩子在书桌前',
      'displayMessage': '画面里看到孩子。',
      'category': 'camera_observation',
      'recordKind': 'vision',
      'createdAt': DateTime.now().millisecondsSinceEpoch,
    });
    expect(vision.recordCategoryLabel, '画面观察');

    final capabilityReminder = LiveCareEvent.fromJson({
      'id': 'evt_posture',
      'eventType': 'speak',
      'displayTitle': '坐姿提醒',
      'displayMessage': '请坐直一点。',
      'category': 'care_reminder',
      'recordKind': 'reminder',
      'payload': {
        'request': {'scenario': 'posture', 'source': 'care_reminder'},
      },
      'createdAt': DateTime.now().millisecondsSinceEpoch,
    });
    expect(capabilityReminder.recordCategoryLabel, '能力提醒');

    final screenUseReminder = LiveCareEvent.fromJson({
      'id': 'evt_screen_use',
      'eventType': 'speak',
      'displayTitle': '屏幕使用提醒',
      'displayMessage': '眼睛离屏幕远一点，休息一下吧。',
      'category': 'care_reminder',
      'recordKind': 'reminder',
      'payload': {
        'request': {'scenario': 'screen_use', 'source': 'care_reminder'},
      },
      'createdAt': DateTime.now().millisecondsSinceEpoch,
    });
    expect(screenUseReminder.recordCategoryLabel, '能力提醒');

    final routineReminder = LiveCareEvent.fromJson({
      'id': 'evt_wake',
      'eventType': 'speak',
      'displayTitle': '起床提醒',
      'displayMessage': '该起床啦。',
      'category': 'care_reminder',
      'recordKind': 'reminder',
      'payload': {
        'request': {'scenario': 'wake_up', 'source': 'care_reminder'},
      },
      'createdAt': DateTime.now().millisecondsSinceEpoch,
    });
    expect(routineReminder.recordCategoryLabel, '作息提醒');

    final unknownReminder = LiveCareEvent.fromJson({
      'id': 'evt_unknown',
      'eventType': 'speak',
      'displayTitle': '看护提醒',
      'displayMessage': '已轻声提醒。',
      'category': 'care_reminder',
      'recordKind': 'reminder',
      'createdAt': DateTime.now().millisecondsSinceEpoch,
    });
    expect(unknownReminder.recordCategoryLabel, '看护提醒');
  });

  test(
    'refreshMonitor returns unavailable status when snapshot fails',
    () async {
      final dio = Dio(BaseOptions(baseUrl: 'http://test/api'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            handler.reject(
              DioException(
                requestOptions: options,
                response: Response<dynamic>(
                  requestOptions: options,
                  statusCode: 502,
                  data: {
                    'ok': false,
                    'error': 'camera_snapshot_failed',
                    'message': '摄像头画面暂不可用，请稍后再试。',
                  },
                ),
                type: DioExceptionType.badResponse,
              ),
            );
          },
        ),
      );
      final repository = CameraRepository(apiClient: ApiClient(dio), dio: dio);

      final status = await repository.refreshMonitor(deviceId: 'dev_1');

      expect(status.status, 'unavailable');
      expect(status.message, contains('摄像头画面暂不可用'));
    },
  );

  testWidgets('LiveEventsScreen empty state keeps refresh provider active', (
    tester,
  ) async {
    final repository = _FakeCameraRepository(const []);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          selectedDeviceProvider.overrideWith((ref) async => null),
          cameraRepositoryProvider.overrideWithValue(repository),
        ],
        child: const MaterialApp(home: LiveEventsScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('还没有可靠的画面记录'), findsOneWidget);
    final callsBefore = repository.eventsPageCallCount;
    final container = ProviderScope.containerOf(
      tester.element(find.byType(LiveEventsScreen)),
    );

    await container.read(cameraEventsProvider.notifier).refresh();
    await tester.pumpAndSettle();

    expect(repository.eventsPageCallCount, greaterThan(callsBefore));
    expect(find.text('还没有可靠的画面记录'), findsOneWidget);
  });
}

class _FakeCameraRepository extends CameraRepository {
  _FakeCameraRepository(this.eventItems)
    : super(apiClient: ApiClient(Dio()), dio: Dio());

  List<LiveCareEvent> eventItems;
  bool failEvents = false;
  int eventsPageCallCount = 0;

  @override
  Future<CameraEventsPage> eventsPage({
    String? deviceId,
    int limit = 10,
    int offset = 0,
  }) async {
    if (failEvents) {
      throw const CameraException('暂时拿不到看护事件。');
    }
    eventsPageCallCount += 1;
    final slice = eventItems.skip(offset).take(limit).toList();
    final hasMore = offset + slice.length < eventItems.length;
    return CameraEventsPage(events: slice, hasMore: hasMore);
  }
}

LiveCareEvent _event(String id, int createdAt) {
  return LiveCareEvent(
    id: id,
    source: 'camera_observation',
    eventType: 'camera_observation',
    title: id,
    message: id,
    displayTitle: id,
    displayMessage: id,
    category: 'camera_observation',
    severity: 'info',
    taskTitle: '',
    evidenceSummary: '',
    hasReplay: false,
    status: 'ok',
    toneKey: 'info',
    createdAt: createdAt,
  );
}
