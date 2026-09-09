import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_helpers.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/home/presentation/home_screen.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_learning_preview.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';

import 'support/learning_preparation_v2_fixtures.dart';

void main() {
  testWidgets('queued preparation is visible and Today stays unmounted', (
    tester,
  ) async {
    final preparation = _PreparationGateway(_queued());
    final learning = _CountingLearningGateway();
    await _pumpPreview(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();

    expect(find.text('首门课程准备好就能学'), findsOneWidget);
    expect(find.text('后台准备中'), findsOneWidget);
    expect(learning.todayCalls, 0);
  });

  testWidgets('missing and network error fail closed without retry POST', (
    tester,
  ) async {
    final preparation = _PreparationGateway(null);
    final learning = _CountingLearningGateway();
    await _pumpPreview(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();
    expect(find.text('正在同步年级课程'), findsOneWidget);
    expect(learning.todayCalls, 0);

    preparation.error = StateError('offline');
    final scope = ProviderScope.containerOf(
      tester.element(find.byType(HomePrimaryLearningPreview)),
    );
    scope.invalidate(currentLearningPreparationProvider('child-1'));
    await tester.pumpAndSettle();
    expect(find.text('课程状态暂时无法同步'), findsOneWidget);
    await tester.tap(find.text('重新获取状态'));
    await tester.pumpAndSettle();
    expect(preparation.retryCalls, 0);
    expect(learning.todayCalls, 0);
  });

  testWidgets('ready A stays usable while queued B builds, then refreshes', (
    tester,
  ) async {
    final preparation = _PreparationGateway(_ready('plan-a'));
    final learning = _CountingLearningGateway(
      responses: [_today('一年级 A 课程'), _today('一年级 B 课程')],
    );
    await _pumpPreview(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();
    final scope = ProviderScope.containerOf(
      tester.element(find.byType(HomePrimaryLearningPreview)),
    );
    expect(find.text('一年级 A 课程'), findsOneWidget);

    preparation.value = _queued(id: 'plan-b');
    scope.invalidate(currentLearningPreparationProvider('child-1'));
    await tester.pumpAndSettle();
    expect(learning.todayCalls, 1);
    expect(find.text('一年级 A 课程'), findsOneWidget);
    expect(find.textContaining('新课准备好后会自动出现'), findsOneWidget);

    preparation.value = _ready('plan-b');
    scope.invalidate(currentLearningPreparationProvider('child-1'));
    await tester.pumpAndSettle();
    expect(learning.todayCalls, 2);
    expect(find.text('一年级 A 课程'), findsNothing);
    expect(find.text('一年级 B 课程'), findsOneWidget);
  });

  testWidgets('pending preparation refresh preserves active ready Today', (
    tester,
  ) async {
    final refresh = Completer<LearningPreparation?>();
    final ready = _ready('plan-ready');
    final preparation = _PreparationGateway(
      ready,
      currentOverride: (call) =>
          call == 1 ? Future.value(ready) : refresh.future,
    );
    final learning = _CountingLearningGateway(responses: [_today('一年级课程')]);
    await _pumpPreview(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();
    expect(find.text('一年级课程'), findsOneWidget);
    expect(find.text('扫码登录学生网页'), findsNothing);

    final scope = ProviderScope.containerOf(
      tester.element(find.byType(HomePrimaryLearningPreview)),
    );
    scope.invalidate(currentLearningPreparationProvider('child-1'));
    await tester.pump(const Duration(milliseconds: 1));

    expect(find.text('正在获取课程准备状态…'), findsNothing);
    expect(find.text('一年级课程'), findsOneWidget);
    expect(find.text('扫码登录学生网页'), findsNothing);

    refresh.complete(ready);
    await tester.pumpAndSettle();
    expect(find.text('一年级课程'), findsOneWidget);
    expect(find.text('扫码登录学生网页'), findsNothing);
  });

  testWidgets(
    'direct ready plan replacement preserves the active Today cache',
    (tester) async {
      final preparation = _PreparationGateway(_ready('plan-a'));
      final learning = _CountingLearningGateway(
        responses: [_today('A 课程'), _today('B 课程')],
      );
      await _pumpPreview(tester, preparation: preparation, learning: learning);
      await tester.pumpAndSettle();
      final scope = ProviderScope.containerOf(
        tester.element(find.byType(HomePrimaryLearningPreview)),
      );

      preparation.value = _ready('plan-b');
      scope.invalidate(currentLearningPreparationProvider('child-1'));
      await tester.pumpAndSettle();

      expect(learning.todayCalls, 1);
      expect(find.text('A 课程'), findsOneWidget);
      expect(find.text('B 课程'), findsNothing);
    },
  );

  testWidgets('retryable failed state creates one retry successor', (
    tester,
  ) async {
    final preparation = _PreparationGateway(_failed());
    final learning = _CountingLearningGateway();
    await _pumpPreview(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();

    await tester.tap(find.text('重新准备课程'));
    await tester.pumpAndSettle();
    expect(preparation.retryCalls, 1);
    expect(preparation.currentCalls, 2);
    expect(learning.todayCalls, 0);
  });

  testWidgets('poll stops after a fresh terminal result', (tester) async {
    final preparation = _PreparationGateway(_queued());
    final learning = _CountingLearningGateway();
    await _pumpPreview(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();
    expect(preparation.currentCalls, 1);

    preparation.value = _ready('plan-ready');
    await tester.pump(const Duration(milliseconds: 2600));
    await tester.pump();
    expect(preparation.currentCalls, 2);
    await tester.pump(const Duration(seconds: 4));
    expect(preparation.currentCalls, 2);
  });

  testWidgets('background poll keeps queued progress visible while pending', (
    tester,
  ) async {
    final pendingPoll = Completer<LearningPreparation?>();
    final queued = _queued();
    final preparation = _PreparationGateway(
      queued,
      currentOverride: (call) =>
          call == 1 ? Future.value(queued) : pendingPoll.future,
    );
    await _pumpPreview(
      tester,
      preparation: preparation,
      learning: _CountingLearningGateway(),
    );
    await tester.pumpAndSettle();

    await tester.pump(const Duration(milliseconds: 2600));
    await tester.pump();

    expect(preparation.currentCalls, 2);
    expect(find.text('首门课程准备好就能学'), findsOneWidget);
    expect(find.text('正在获取课程准备状态…'), findsNothing);

    pendingPoll.complete(_failed());
    await tester.pumpAndSettle();
  });

  testWidgets('active poll timer cancels immediately when refresh fails', (
    tester,
  ) async {
    final preparation = _PreparationGateway(_queued());
    await _pumpPreview(
      tester,
      preparation: preparation,
      learning: _CountingLearningGateway(),
    );
    await tester.pumpAndSettle();
    final scope = ProviderScope.containerOf(
      tester.element(find.byType(HomePrimaryLearningPreview)),
    );

    preparation.value = _failed();
    scope.invalidate(currentLearningPreparationProvider('child-1'));
    await tester.pumpAndSettle();
    expect(preparation.currentCalls, 2);
    expect(find.text('课程准备需要重新启动'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    expect(preparation.currentCalls, 2);
  });

  testWidgets('active poll timer cancels immediately on preparation error', (
    tester,
  ) async {
    final preparation = _PreparationGateway(_queued());
    await _pumpPreview(
      tester,
      preparation: preparation,
      learning: _CountingLearningGateway(),
    );
    await tester.pumpAndSettle();
    final scope = ProviderScope.containerOf(
      tester.element(find.byType(HomePrimaryLearningPreview)),
    );

    preparation.error = StateError('offline');
    scope.invalidate(currentLearningPreparationProvider('child-1'));
    await tester.pumpAndSettle();
    expect(preparation.currentCalls, 2);
    expect(find.text('课程状态暂时无法同步'), findsOneWidget);

    await tester.pump(const Duration(seconds: 3));
    expect(preparation.currentCalls, 2);
  });

  for (final state in const [
    AppLifecycleState.paused,
    AppLifecycleState.inactive,
    AppLifecycleState.hidden,
    AppLifecycleState.detached,
  ]) {
    testWidgets('poll stops immediately for lifecycle $state', (tester) async {
      final preparation = _PreparationGateway(_queued());
      await _pumpPreview(
        tester,
        preparation: preparation,
        learning: _CountingLearningGateway(),
      );
      await tester.pumpAndSettle();

      tester.binding.handleAppLifecycleStateChanged(state);
      await tester.pump(const Duration(seconds: 3));
      expect(preparation.currentCalls, 1);
    });
  }

  testWidgets('widget disposal cancels preparation polling', (tester) async {
    final preparation = _PreparationGateway(_queued());
    await _pumpPreview(
      tester,
      preparation: preparation,
      learning: _CountingLearningGateway(),
    );
    await tester.pumpAndSettle();
    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    await tester.pump(const Duration(seconds: 3));
    expect(preparation.currentCalls, 1);
  });

  test(
    'concurrent home refreshes share one profile, preparation and Today request',
    () async {
      var profileCalls = 0;
      var preparationCalls = 0;
      var availabilityCalls = 0;
      final learning = _CountingLearningGateway();
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async {
            profileCalls += 1;
            return _profile;
          }),
          currentLearningPreparationProvider.overrideWith((ref, childId) async {
            preparationCalls += 1;
            return _ready('plan-ready');
          }),
          currentLearningAvailabilityProvider.overrideWith((
            ref,
            childId,
          ) async {
            availabilityCalls += 1;
            return const LearningAvailability(
              gradeCode: 'primary_1',
              hasActiveRelease: true,
              availableCourseCount: 30,
              canLearnNow: true,
            );
          }),
          learningRepositoryProvider.overrideWithValue(learning),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);

      await Future.wait([
        refreshHomeDataSilently(container),
        refreshHomeDataSilently(container),
        refreshHomeDataSilently(container),
      ]);

      expect(profileCalls, 1);
      expect(preparationCalls, 1);
      expect(availabilityCalls, 1);
      expect(learning.todayCalls, 1);
    },
  );

  for (final gateCase
      in <
        ({
          String name,
          LearningPreparation? value,
          Object? error,
          int todayCalls,
        })
      >[
        (name: 'missing', value: null, error: null, todayCalls: 0),
        (name: 'queued', value: _queued(), error: null, todayCalls: 0),
        (name: 'failed', value: _failed(), error: null, todayCalls: 0),
        (
          name: 'future stage',
          value: _preparation(
            id: 'plan-future',
            status: 'running',
            stage: 'future_stage',
          ),
          error: null,
          todayCalls: 0,
        ),
        (
          name: 'inconsistent ready',
          value: _preparation(
            id: 'plan-inconsistent',
            status: 'ready',
            stage: 'completed',
            progress: 100,
            ready: 30,
            subjectsReady: false,
            retryAfterMs: null,
          ),
          error: null,
          todayCalls: 0,
        ),
        (
          name: 'v2 content 3 of 30',
          value: _v2Preparation(candidateCount: 3),
          error: null,
          todayCalls: 0,
        ),
        (
          name: 'v2 content 30 of 30 handoff',
          value: _v2Preparation(
            candidateCount: 30,
            stage: 'building_classrooms',
            progress: 35,
          ),
          error: null,
          todayCalls: 0,
        ),
        (
          name: 'empty id',
          value: null,
          error: const LearningPreparationFormatException(
            'id must not be empty',
          ),
          todayCalls: 0,
        ),
        (
          name: 'network error',
          value: null,
          error: StateError('offline'),
          todayCalls: 0,
        ),
        (
          name: 'ready',
          value: _ready('plan-ready'),
          error: null,
          todayCalls: 1,
        ),
      ]) {
    test('home refresh gate: ${gateCase.name}', () async {
      final learning = _CountingLearningGateway();
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _profile),
          currentLearningPreparationProvider.overrideWith((ref, childId) async {
            if (gateCase.error != null) throw gateCase.error!;
            return gateCase.value;
          }),
          currentLearningAvailabilityProvider.overrideWith((
            ref,
            childId,
          ) async {
            return LearningAvailability(
              gradeCode: 'primary_1',
              hasActiveRelease: gateCase.todayCalls == 1,
              availableCourseCount: gateCase.todayCalls == 1 ? 30 : 0,
              canLearnNow: gateCase.todayCalls == 1,
            );
          }),
          learningRepositoryProvider.overrideWithValue(learning),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);

      await refreshHomeDataSilently(container);

      expect(learning.todayCalls, gateCase.todayCalls);
    });
  }

  for (final malformed in malformedPreparationV2Payloads()) {
    test('home refresh malformed v2 ${malformed.name} stays closed', () async {
      final learning = _CountingLearningGateway();
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _profile),
          currentLearningPreparationProvider.overrideWith((ref, childId) async {
            return LearningPreparation.fromJson(malformed.payload);
          }),
          currentLearningAvailabilityProvider.overrideWith((
            ref,
            childId,
          ) async {
            return const LearningAvailability(
              gradeCode: 'primary_1',
              hasActiveRelease: false,
              availableCourseCount: 0,
              canLearnNow: false,
            );
          }),
          learningRepositoryProvider.overrideWithValue(learning),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);

      await refreshHomeDataSilently(container);

      expect(learning.todayCalls, 0, reason: malformed.name);
    });
  }

  test('failed fresh profile skips preparation and Today', () async {
    var preparationCalls = 0;
    final learning = _CountingLearningGateway();
    final container = ProviderContainer(
      overrides: [
        profileSummaryProvider.overrideWith(
          (ref) async => throw StateError('offline'),
        ),
        currentLearningPreparationProvider.overrideWith((ref, childId) async {
          preparationCalls += 1;
          return _ready('plan-stale');
        }),
        learningRepositoryProvider.overrideWithValue(learning),
        ..._quietHomeOverrides(),
      ],
    );
    addTearDown(container.dispose);

    await refreshHomeDataSilently(container);

    expect(preparationCalls, 0);
    expect(learning.todayCalls, 0);
  });

  testWidgets('slow profile refresh cancels the old 2.5 second poll timer', (
    tester,
  ) async {
    final slowProfile = Completer<ProfileSummary>();
    var profileCalls = 0;
    final preparation = _PreparationGateway(_queued());
    final container = ProviderContainer(
      overrides: [
        profileSummaryProvider.overrideWith((ref) {
          profileCalls += 1;
          return profileCalls == 1
              ? Future.value(_profile)
              : slowProfile.future;
        }),
        learningAvailabilityRepositoryProvider.overrideWithValue(
          const _AvailabilityGateway(false),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
        learningRepositoryProvider.overrideWithValue(
          _CountingLearningGateway(),
        ),
        ..._quietHomeOverrides(),
      ],
    );
    addTearDown(container.dispose);
    await _pumpPreviewWithContainer(tester, container);
    await tester.pumpAndSettle();

    final refresh = refreshHomeDataSilently(container);
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    expect(preparation.currentCalls, 1);
    slowProfile.complete(_profile);
    await refresh;
    expect(preparation.currentCalls, 2);
  });

  testWidgets('slow preparation refresh cancels the old poll timer', (
    tester,
  ) async {
    final slowPreparation = Completer<LearningPreparation?>();
    final preparation = _PreparationGateway(
      _queued(),
      currentOverride: (call) =>
          call == 1 ? Future.value(_queued()) : slowPreparation.future,
    );
    final container = ProviderContainer(
      overrides: [
        profileSummaryProvider.overrideWith((ref) async => _profile),
        learningAvailabilityRepositoryProvider.overrideWithValue(
          _AvailabilityGateway(preparation.value?.isReady == true),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
        learningRepositoryProvider.overrideWithValue(
          _CountingLearningGateway(),
        ),
        ..._quietHomeOverrides(),
      ],
    );
    addTearDown(container.dispose);
    await _pumpPreviewWithContainer(tester, container);
    await tester.pumpAndSettle();

    final refresh = refreshHomeDataSilently(container);
    await tester.pump();
    await tester.pump(const Duration(seconds: 3));
    expect(preparation.currentCalls, 2);
    slowPreparation.complete(_queued(updatedAt: 1787200005000));
    await refresh;
    expect(preparation.currentCalls, 2);
  });

  testWidgets(
    'actual Home resume keeps old timer cancelled until fresh data reschedules',
    (tester) async {
      final slowPreparation = Completer<LearningPreparation?>();
      final initial = _queued();
      final fresh = _queued(updatedAt: 1787200005000);
      final preparation = _PreparationGateway(
        initial,
        currentOverride: (call) {
          if (call == 1) return Future.value(initial);
          if (call == 2) return slowPreparation.future;
          return Future.value(fresh);
        },
      );
      var profileCalls = 0;
      final container = ProviderContainer(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async {
            profileCalls += 1;
            return _profile;
          }),
          learningAvailabilityRepositoryProvider.overrideWithValue(
            const _AvailabilityGateway(false),
          ),
          learningPreparationRepositoryProvider.overrideWithValue(preparation),
          learningRepositoryProvider.overrideWithValue(
            _CountingLearningGateway(),
          ),
          ..._quietHomeOverrides(),
        ],
      );
      addTearDown(container.dispose);
      await _pumpHomeWithContainer(tester, container);
      await tester.pumpAndSettle();
      expect(profileCalls, 1);
      expect(preparation.currentCalls, 1);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(profileCalls, 2);
      expect(preparation.currentCalls, 2);

      await tester.pump(const Duration(seconds: 3));
      expect(preparation.currentCalls, 2);

      slowPreparation.complete(fresh);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 2400));
      expect(preparation.currentCalls, 2);
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(preparation.currentCalls, 3);
    },
  );
}

Future<void> _pumpPreview(
  WidgetTester tester, {
  required _PreparationGateway preparation,
  required _CountingLearningGateway learning,
}) {
  return tester.pumpWidget(
    ProviderScope(
      overrides: [
        profileSummaryProvider.overrideWith((ref) async => _profile),
        learningAvailabilityRepositoryProvider.overrideWithValue(
          _AvailabilityGateway(preparation.value?.isReady == true),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
        learningRepositoryProvider.overrideWithValue(learning),
      ],
      child: const MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            padding: EdgeInsets.all(16),
            child: HomePrimaryLearningPreview(child: _child),
          ),
        ),
      ),
    ),
  );
}

Future<void> _pumpPreviewWithContainer(
  WidgetTester tester,
  ProviderContainer container,
) {
  return tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(
        home: Scaffold(body: HomePrimaryLearningPreview(child: _child)),
      ),
    ),
  );
}

Future<void> _pumpHomeWithContainer(
  WidgetTester tester,
  ProviderContainer container,
) {
  return tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: HomeScreen()),
    ),
  );
}

dynamic _quietHomeOverrides() => [
  primaryDeviceOverviewProvider.overrideWith(
    (ref) async => throw StateError('quiet'),
  ),
  todayTasksProvider.overrideWith((ref) async => throw StateError('quiet')),
  rewardRedemptionsProvider.overrideWith(
    (ref) async => throw StateError('quiet'),
  ),
  cameraHealthProvider.overrideWith((ref) async => throw StateError('quiet')),
  cameraStatusProvider.overrideWith((ref) async => throw StateError('quiet')),
  cameraMonitorStatusProvider.overrideWith(
    (ref) async => throw StateError('quiet'),
  ),
  careSummaryProvider.overrideWith(
    (ref, childId) async => throw StateError('quiet'),
  ),
];

class _PreparationGateway implements LearningPreparationGateway {
  _PreparationGateway(this.value, {this.currentOverride});

  LearningPreparation? value;
  Object? error;
  final Future<LearningPreparation?> Function(int call)? currentOverride;
  var currentCalls = 0;
  var retryCalls = 0;

  @override
  Future<LearningPreparation?> current(String childId) {
    currentCalls += 1;
    final override = currentOverride;
    if (override != null) return override(currentCalls);
    if (error != null) return Future.error(error!);
    return Future.value(value);
  }

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) {
    retryCalls += 1;
    return Future.value(_queued(id: 'plan-successor'));
  }
}

class _AvailabilityGateway implements LearningAvailabilityGateway {
  const _AvailabilityGateway(this.hasActiveRelease);

  final bool hasActiveRelease;

  @override
  Future<LearningAvailability> current(String childId) async {
    return LearningAvailability(
      gradeCode: 'primary_1',
      hasActiveRelease: hasActiveRelease,
      availableCourseCount: hasActiveRelease ? 30 : 0,
      canLearnNow: hasActiveRelease,
    );
  }
}

class _CountingLearningGateway implements LearningGateway {
  _CountingLearningGateway({List<LearningToday>? responses})
    : responses =
          responses ??
          [const LearningToday(state: LearningTodayState.unavailable)];

  final List<LearningToday> responses;
  var todayCalls = 0;

  @override
  Future<LearningToday> today(String childId) async {
    final index = todayCalls.clamp(0, responses.length - 1);
    todayCalls += 1;
    return responses[index];
  }

  @override
  Future<LearningReport?> latestReport(String childId, {String? subject}) =>
      throw UnimplementedError();
}

LearningToday _today(String title) => LearningToday(
  state: LearningTodayState.scheduled,
  lesson: LearningLesson(
    id: 'lesson-$title',
    title: title,
    subject: '数学',
    skill: '数感',
    gradeLabel: '一年级',
    estimatedMinutes: 10,
    questionCount: 5,
    introduction: '今日练习',
  ),
  task: LearningTask(
    id: 'task-$title',
    status: 'scheduled',
    scheduledStart: '19:30',
  ),
);

LearningPreparation _queued({
  String id = 'plan-queued',
  int updatedAt = 1787200000000,
}) => _preparation(
  id: id,
  status: 'queued',
  stage: 'queued',
  updatedAt: updatedAt,
);

LearningPreparation _ready(String id) => _preparation(
  id: id,
  status: 'ready',
  stage: 'completed',
  progress: 100,
  ready: 30,
  subjectsReady: true,
  retryAfterMs: null,
);

LearningPreparation _failed() => _preparation(
  id: 'plan-failed',
  status: 'failed',
  stage: 'completed',
  progress: 30,
  ready: 9,
  failed: 1,
  canRetry: true,
  retryAfterMs: null,
  error: const {'code': 'failed', 'message': '课程校验未通过'},
);

LearningPreparation _v2Preparation({
  required int candidateCount,
  String stage = 'generating_content',
  int progress = 8,
}) => LearningPreparation.fromJson(
  preparationV2Payload(
    id: 'plan-v2-$candidateCount',
    childId: 'child-1',
    candidateCount: candidateCount,
    stage: stage,
    progressPercent: progress,
  ),
);

LearningPreparation _preparation({
  required String id,
  required String status,
  required String stage,
  int progress = 0,
  int ready = 0,
  int failed = 0,
  bool subjectsReady = false,
  bool canRetry = false,
  int? retryAfterMs = 2500,
  int updatedAt = 1787200000000,
  Map<String, dynamic>? error,
}) => LearningPreparation.fromJson({
  'schemaVersion': 'mira.learning.preparation.v1',
  'id': id,
  'childId': 'child-1',
  'gradeCode': 'primary_1',
  'gradeLabel': '一年级',
  'subjects': [
    {
      'code': 'chinese',
      'label': '语文',
      'readyCourseCount': subjectsReady ? 12 : 0,
      'failedCourseCount': 0,
      'totalCourseCount': 12,
    },
    {
      'code': 'math',
      'label': '数学',
      'readyCourseCount': subjectsReady ? 9 : 0,
      'failedCourseCount': 0,
      'totalCourseCount': 9,
    },
    {
      'code': 'english',
      'label': '英语',
      'readyCourseCount': subjectsReady ? 9 : 0,
      'failedCourseCount': 0,
      'totalCourseCount': 9,
    },
  ],
  'status': status,
  'stage': stage,
  'progressPercent': progress,
  'totalCourseCount': 30,
  'readyCourseCount': ready,
  'failedCourseCount': failed,
  'attempt': 1,
  'canRetry': canRetry,
  'retryAfterMs': retryAfterMs,
  'message': status == 'failed' ? '课程准备未完成' : '正在准备课程',
  'lastProgressAt': updatedAt,
  'updatedAt': updatedAt,
  'completedAt': stage == 'completed' ? updatedAt : null,
  'error': error,
});

const _child = ChildProfile(
  id: 'child-1',
  name: '乐乐',
  nickname: '乐乐',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '',
  ageStage: '小学 一年级',
  educationStage: '小学',
  grade: '一年级',
  gradeCode: 'primary_1',
  educationStageCode: 'primary',
  contentMode: 'primary_learning',
  schoolYearStartYear: 2026,
  schoolName: '',
  interests: [],
  taskPreferences: {},
);

const _profile = ProfileSummary(
  spaceTitle: '家庭',
  familyId: 'family-1',
  familyName: '家庭',
  displayName: '妈妈',
  phone: '13800000000',
  relationship: '妈妈',
  relationshipKey: 'mother',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: [],
  avatarPersona: '',
  memberCount: 1,
  deviceCount: 0,
  pendingItemCount: 0,
  child: _child,
);
