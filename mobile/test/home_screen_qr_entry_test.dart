import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/home/presentation/home_screen.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';

void main() {
  testWidgets('real Home top QR entry receives taps above the scroll view', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final router = GoRouter(
      initialLocation: '/home',
      routes: [
        GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
        GoRoute(
          path: studentAccessQrPath,
          builder: (_, _) => const Scaffold(body: Text('扫码目标页')),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _primaryProfile),
          currentLearningPreparationProvider.overrideWith(
            (ref, childId) async => _readyPreparation(childId),
          ),
          currentLearningAvailabilityProvider.overrideWith(
            (ref, childId) async => _availability(
              hasActiveRelease: false,
              canAccessWorkspace: true,
            ),
          ),
          todayTasksProvider.overrideWith((ref) async => const []),
          rewardRedemptionsProvider.overrideWith((ref) async => const []),
          primaryDeviceOverviewProvider.overrideWith((ref) async => null),
          cameraHealthProvider.overrideWith(
            (ref) async => CameraHealth.fromJson(const {}),
          ),
          cameraStatusProvider.overrideWith(
            (ref) async => CameraStatus.fromJson(const {}),
          ),
          cameraMonitorDisplayProvider.overrideWith(
            (ref) => AsyncValue.data(CameraMonitorStatus.fromJson(const {})),
          ),
          dailyReportProvider.overrideWith(
            (ref) async => ReportData.fromJson(const {}),
          ),
          weeklyReportProvider.overrideWith(
            (ref) async => ReportData.fromJson(const {}),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final entry = find.byKey(const ValueKey('homeStudentQrScanButton'));
    expect(entry, findsOneWidget);
    expect(tester.getSize(entry), const Size(48, 48));
    await tester.tap(entry);
    await tester.pumpAndSettle();

    expect(find.text('扫码目标页'), findsOneWidget);
  });

  for (final gateCase
      in <
        ({
          String name,
          Future<LearningAvailability> Function(String childId) load,
          String message,
        })
      >[
        (
          name: 'no workspace permission',
          load: (childId) async => _availability(hasActiveRelease: false),
          message: '当前暂不能登录学习空间',
        ),
        (
          name: 'availability network error',
          load: (childId) async => throw StateError('offline'),
          message: '学习空间权限加载失败',
        ),
      ]) {
    testWidgets('Home top QR stays closed for ${gateCase.name}', (
      tester,
    ) async {
      await _pumpHomeGate(tester, loadAvailability: gateCase.load);

      await tester.tap(find.byKey(const ValueKey('homeStudentQrScanButton')));
      await tester.pumpAndSettle();

      expect(find.text('扫码目标页'), findsNothing);
      expect(find.text(gateCase.message), findsOneWidget);
    });
  }

  testWidgets('Home QR action rechecks availability before navigation', (
    tester,
  ) async {
    var current = _availability();
    await _pumpHomeGate(tester, loadAvailability: (childId) async => current);
    final container = ProviderScope.containerOf(
      tester.element(find.byType(HomeScreen)),
    );
    current = _availability(hasActiveRelease: false);
    container.invalidate(currentLearningAvailabilityProvider('child-1'));

    await tester.tap(find.byKey(const ValueKey('homeStudentQrScanButton')));
    await tester.pumpAndSettle();

    expect(find.text('扫码目标页'), findsNothing);
    expect(find.text('正在确认学习空间权限'), findsOneWidget);
  });

  testWidgets(
    'scheduled course has no duplicate QR action and top QR still opens pairing',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final learning = _ScheduledLearningGateway();
      final router = GoRouter(
        initialLocation: '/home',
        routes: [
          GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
          GoRoute(
            path: studentAccessQrPath,
            builder: (_, _) => const Scaffold(body: Text('扫码目标页')),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileSummaryProvider.overrideWith((ref) async => _primaryProfile),
            learningPreparationRepositoryProvider.overrideWithValue(
              _ReadyPreparationGateway(),
            ),
            currentLearningAvailabilityProvider.overrideWith(
              (ref, childId) async => _availability(),
            ),
            learningRepositoryProvider.overrideWithValue(learning),
            todayTasksProvider.overrideWith((ref) async => const []),
            rewardRedemptionsProvider.overrideWith((ref) async => const []),
            primaryDeviceOverviewProvider.overrideWith((ref) async => null),
            cameraHealthProvider.overrideWith(
              (ref) async => CameraHealth.fromJson(const {}),
            ),
            cameraStatusProvider.overrideWith(
              (ref) async => CameraStatus.fromJson(const {}),
            ),
            cameraMonitorDisplayProvider.overrideWith(
              (ref) => AsyncValue.data(CameraMonitorStatus.fromJson(const {})),
            ),
            dailyReportProvider.overrideWith(
              (ref) async => ReportData.fromJson(const {}),
            ),
            weeklyReportProvider.overrideWith(
              (ref) async => ReportData.fromJson(const {}),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('扫码登录学生网页'), findsNothing);
      expect(
        find.byKey(const ValueKey('learningPrimaryAction_main')),
        findsNothing,
      );
      await tester.tap(find.byKey(const ValueKey('homeStudentQrScanButton')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      expect(find.text('扫码目标页'), findsOneWidget);
    },
  );

  testWidgets(
    'primary grade without workspace permission shows preparation and QR stays closed',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final router = GoRouter(
        initialLocation: '/home',
        routes: [
          GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
          GoRoute(
            path: studentAccessQrPath,
            builder: (_, _) => const Scaffold(body: Text('扫码目标页')),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileSummaryProvider.overrideWith(
              (ref) async => _primaryTwoProfile,
            ),
            currentLearningAvailabilityProvider.overrideWith(
              (ref, childId) async => _availability(
                gradeCode: 'primary_2',
                hasActiveRelease: false,
              ),
            ),
            currentLearningPreparationProvider.overrideWith(
              (ref, childId) async => _queuedPreparation(
                childId,
                gradeCode: 'primary_2',
                gradeLabel: '二年级',
              ),
            ),
            todayTasksProvider.overrideWith((ref) async => const []),
            rewardRedemptionsProvider.overrideWith((ref) async => const []),
            primaryDeviceOverviewProvider.overrideWith((ref) async => null),
            cameraHealthProvider.overrideWith(
              (ref) async => CameraHealth.fromJson(const {}),
            ),
            cameraStatusProvider.overrideWith(
              (ref) async => CameraStatus.fromJson(const {}),
            ),
            cameraMonitorDisplayProvider.overrideWith(
              (ref) => AsyncValue.data(CameraMonitorStatus.fromJson(const {})),
            ),
            dailyReportProvider.overrideWith(
              (ref) async => ReportData.fromJson(const {}),
            ),
            weeklyReportProvider.overrideWith(
              (ref) async => ReportData.fromJson(const {}),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('首门课程准备好就能学'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('primaryLearningPreview')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const ValueKey('homeStudentQrScanButton')));
      await tester.pump();

      expect(find.text('扫码目标页'), findsNothing);
      expect(find.text('当前暂不能登录学习空间'), findsOneWidget);
    },
  );
}

Future<void> _pumpHomeGate(
  WidgetTester tester, {
  required Future<LearningAvailability> Function(String childId)
  loadAvailability,
}) async {
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(path: '/home', builder: (_, _) => const HomeScreen()),
      GoRoute(
        path: studentAccessQrPath,
        builder: (_, _) => const Scaffold(body: Text('扫码目标页')),
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        profileSummaryProvider.overrideWith((ref) async => _primaryProfile),
        currentLearningPreparationProvider.overrideWith(
          (ref, childId) async => _queuedPreparation(childId),
        ),
        currentLearningAvailabilityProvider.overrideWith(
          (ref, childId) => loadAvailability(childId),
        ),
        todayTasksProvider.overrideWith((ref) async => const []),
        rewardRedemptionsProvider.overrideWith((ref) async => const []),
        primaryDeviceOverviewProvider.overrideWith((ref) async => null),
        cameraHealthProvider.overrideWith(
          (ref) async => CameraHealth.fromJson(const {}),
        ),
        cameraStatusProvider.overrideWith(
          (ref) async => CameraStatus.fromJson(const {}),
        ),
        cameraMonitorDisplayProvider.overrideWith(
          (ref) => AsyncValue.data(CameraMonitorStatus.fromJson(const {})),
        ),
        dailyReportProvider.overrideWith(
          (ref) async => ReportData.fromJson(const {}),
        ),
        weeklyReportProvider.overrideWith(
          (ref) async => ReportData.fromJson(const {}),
        ),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

final _primaryProfile = ProfileSummary(
  spaceTitle: '乐乐家',
  familyId: 'family-1',
  familyName: '乐乐家',
  displayName: '妈妈',
  phone: '13800000000',
  relationship: '妈妈',
  relationshipKey: 'mom',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: const ['manage_child_profile'],
  avatarPersona: '',
  memberCount: 2,
  deviceCount: 0,
  pendingItemCount: 0,
  child: ChildProfile.fromJson({
    'id': 'child-1',
    'name': '乐乐',
    'nickname': '乐乐',
    'educationStage': '小学',
    'grade': '一年级',
    'gradeCode': 'primary_1',
    'contentMode': 'primary_learning',
  }),
);

final _primaryTwoProfile = ProfileSummary(
  spaceTitle: '安安家',
  familyId: 'family-2',
  familyName: '安安家',
  displayName: '妈妈',
  phone: '13800000001',
  relationship: '妈妈',
  relationshipKey: 'mom',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: const ['manage_child_profile'],
  avatarPersona: '',
  memberCount: 2,
  deviceCount: 0,
  pendingItemCount: 0,
  child: ChildProfile.fromJson({
    'id': 'child-2',
    'name': '安安',
    'nickname': '安安',
    'educationStage': '小学',
    'grade': '二年级',
    'gradeCode': 'primary_2',
    'contentMode': 'primary_learning',
  }),
);

class _ReadyPreparationGateway implements LearningPreparationGateway {
  @override
  Future<LearningPreparation?> current(String childId) async =>
      _readyPreparation(childId);

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) => throw UnimplementedError();
}

LearningPreparation _readyPreparation(String childId) =>
    LearningPreparation.fromJson({
      'schemaVersion': 'mira.learning.preparation.v1',
      'id': 'plan-ready',
      'childId': childId,
      'gradeCode': 'primary_1',
      'gradeLabel': '一年级',
      'subjects': const [
        {
          'code': 'chinese',
          'label': '语文',
          'readyCourseCount': 10,
          'failedCourseCount': 0,
          'totalCourseCount': 10,
        },
        {
          'code': 'math',
          'label': '数学',
          'readyCourseCount': 10,
          'failedCourseCount': 0,
          'totalCourseCount': 10,
        },
        {
          'code': 'english',
          'label': '英语',
          'readyCourseCount': 8,
          'failedCourseCount': 0,
          'totalCourseCount': 8,
        },
      ],
      'status': 'ready',
      'stage': 'completed',
      'progressPercent': 100,
      'totalCourseCount': 28,
      'readyCourseCount': 28,
      'failedCourseCount': 0,
      'attempt': 1,
      'canRetry': false,
      'retryAfterMs': null,
      'message': '课程已就绪',
      'lastProgressAt': 1787200000000,
      'updatedAt': 1787200000000,
      'completedAt': 1787200000000,
      'error': null,
    });

LearningPreparation _queuedPreparation(
  String childId, {
  String gradeCode = 'primary_1',
  String gradeLabel = '一年级',
}) => LearningPreparation.fromJson({
  'schemaVersion': 'mira.learning.preparation.v1',
  'id': 'plan-queued',
  'childId': childId,
  'gradeCode': gradeCode,
  'gradeLabel': gradeLabel,
  'subjects': const [
    {
      'code': 'chinese',
      'label': '语文',
      'readyCourseCount': 0,
      'failedCourseCount': 0,
      'totalCourseCount': 12,
    },
    {
      'code': 'math',
      'label': '数学',
      'readyCourseCount': 0,
      'failedCourseCount': 0,
      'totalCourseCount': 9,
    },
    {
      'code': 'english',
      'label': '英语',
      'readyCourseCount': 0,
      'failedCourseCount': 0,
      'totalCourseCount': 9,
    },
  ],
  'status': 'queued',
  'stage': 'queued',
  'progressPercent': 0,
  'totalCourseCount': 30,
  'readyCourseCount': 0,
  'failedCourseCount': 0,
  'attempt': 1,
  'canRetry': false,
  'retryAfterMs': 2500,
  'message': '已进入备课队列',
  'lastProgressAt': 1787200000000,
  'updatedAt': 1787200000000,
  'completedAt': null,
  'error': null,
});

LearningAvailability _availability({
  bool? canAccessWorkspace,
  String gradeCode = 'primary_1',
  bool hasActiveRelease = true,
  int? availableCourseCount,
}) {
  final count = availableCourseCount ?? (hasActiveRelease ? 30 : 0);
  return LearningAvailability(
    gradeCode: gradeCode,
    hasActiveRelease: hasActiveRelease,
    availableCourseCount: count,
    canLearnNow: hasActiveRelease || count > 0,
    canAccessWorkspace: canAccessWorkspace ?? (hasActiveRelease || count > 0),
  );
}

class _ScheduledLearningGateway implements LearningGateway {
  @override
  Future<LearningToday> today(String childId) async => const LearningToday(
    state: LearningTodayState.scheduled,
    lesson: LearningLesson(
      id: 'lesson-1',
      title: '数量变一变',
      subject: '数学',
      subjectCode: 'math',
      skill: '理解数量变化',
      gradeLabel: '一年级',
      estimatedMinutes: 10,
      questionCount: 5,
      introduction: '今天的课程',
    ),
    task: LearningTask(
      id: 'task-1',
      status: 'scheduled',
      scheduledStart: '19:30',
    ),
  );

  @override
  Future<LearningReport?> latestReport(
    String childId, {
    String? subject,
  }) async => null;
}
