import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_pages.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';
import 'package:warm_sight/src/features/student_access/presentation/student_access_pairing_page.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';

void main() {
  testWidgets(
    'existing student access page exposes parent linkage management',
    (tester) async {
      await _usePhoneViewport(tester);
      final repository = _FakeStudentAccessRepository(
        onCreate: ({required childId, required pin}) async =>
            _pairing(expiresAfter: const Duration(minutes: 10)),
      );

      await _pumpPage(tester, repository: repository);

      expect(
        find.byKey(const ValueKey('openStudentAccessManagement')),
        findsOneWidget,
      );
      expect(find.text('设备授权与学习报告'), findsOneWidget);
    },
  );

  testWidgets('validates PIN and renders real pairing response at 390x844', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    final repository = _FakeStudentAccessRepository(
      onCreate: ({required childId, required pin}) async {
        expect(childId, 'child-primary');
        expect(pin, '2468');
        return _pairing(expiresAfter: const Duration(minutes: 10));
      },
    );
    await _pumpPage(tester, repository: repository);

    expect(_primaryButton(tester).onTap, isNull);
    await _enterPin(tester, pin: '2468', confirmation: '2469');
    expect(find.text('两次输入的 PIN 不一致'), findsOneWidget);
    expect(_primaryButton(tester).onTap, isNull);

    await _enterPin(tester, pin: '2468', confirmation: '2468');
    expect(_primaryButton(tester).onTap, isNotNull);
    await tester.tap(find.byKey(const ValueKey('createStudentPairingCode')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('studentPairingResult')), findsOneWidget);
    expect(find.byKey(const ValueKey('studentPairingCode')), findsOneWidget);
    expect(find.text('配对码已准备好'), findsOneWidget);
    expect(find.text('http://student.example.test'), findsOneWidget);
    expect(find.textContaining('09:'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('shows loading, API error, and allows a safe retry', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    final pending = Completer<StudentPairingCode>();
    var calls = 0;
    final repository = _FakeStudentAccessRepository(
      onCreate: ({required childId, required pin}) {
        calls += 1;
        if (calls == 1) return pending.future;
        return Future.value(
          _pairing(expiresAfter: const Duration(minutes: 10)),
        );
      },
    );
    await _pumpPage(tester, repository: repository);
    await _enterPin(tester, pin: '1357', confirmation: '1357');

    await tester.tap(find.byKey(const ValueKey('createStudentPairingCode')));
    await tester.pump();
    expect(find.text('正在创建'), findsOneWidget);
    expect(_primaryButton(tester).onTap, isNull);

    pending.completeError(const StudentAccessException('当前网络不可用，请稍后再试'));
    await tester.pumpAndSettle();
    expect(find.text('当前网络不可用，请稍后再试'), findsOneWidget);
    expect(_primaryButton(tester).onTap, isNotNull);

    await tester.tap(find.byKey(const ValueKey('createStudentPairingCode')));
    await tester.pumpAndSettle();
    expect(find.text('配对码已准备好'), findsOneWidget);
  });

  testWidgets('countdown expires and regeneration invalidation is explained', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    var now = DateTime(2026, 8, 13, 12);
    final repository = _FakeStudentAccessRepository(
      onCreate: ({required childId, required pin}) async {
        return _pairing(expiresAfter: const Duration(seconds: 2), now: now);
      },
    );
    await _pumpPage(tester, repository: repository, clock: () => now);
    await _enterPin(tester, pin: '8642', confirmation: '8642');
    await tester.tap(find.byKey(const ValueKey('createStudentPairingCode')));
    await tester.pump();

    now = now.add(const Duration(seconds: 3));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('配对码已过期'), findsOneWidget);
    expect(find.text('已失效'), findsOneWidget);
    final copy = tester.widget<AppSecondaryButton>(
      find.byKey(const ValueKey('copyStudentPairingCode')),
    );
    expect(copy.onTap, isNull);

    await tester.tap(find.byKey(const ValueKey('restartStudentPairing')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('studentPinSetup')), findsOneWidget);
    expect(find.textContaining('上一个未使用的配对码会立即失效'), findsOneWidget);
    expect(find.byKey(const ValueKey('studentPairingResult')), findsNothing);
  });

  testWidgets('kindergarten profile cannot create a student web pairing code', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          currentChildProvider.overrideWith((ref) async => _kindergartenChild),
          accountProfileProvider.overrideWith((ref) async => _adminAccount),
          currentLearningPreparationProvider.overrideWith(
            (ref, childId) async => null,
          ),
          appEnvironmentProvider.overrideWithValue(_environment),
        ],
        child: const MaterialApp(home: StudentAccessPairingPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('当前年级暂不支持学生学习空间'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('createStudentPairingCode')),
      findsNothing,
    );
  });

  testWidgets('unopened primary grade cannot enter student pairing', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          currentChildProvider.overrideWith((ref) async => _primaryTwoChild),
          accountProfileProvider.overrideWith((ref) async => _adminAccount),
          currentLearningPreparationProvider.overrideWith(
            (ref, childId) async => null,
          ),
          studentAccessAvailabilityProvider.overrideWith(
            (ref, childId) async =>
                _availability(gradeCode: 'primary_2', hasActiveRelease: false),
          ),
          appEnvironmentProvider.overrideWithValue(_environment),
        ],
        child: const MaterialApp(home: StudentAccessPairingPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('当前暂不能登录学习空间'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('createStudentPairingCode')),
      findsNothing,
    );
  });

  testWidgets(
    'direct pairing route fails closed without child profile permission',
    (tester) async {
      await _usePhoneViewport(tester);
      var createPairingCalls = 0;
      final repository = _FakeStudentAccessRepository(
        onCreate: ({required childId, required pin}) async {
          createPairingCalls += 1;
          return _pairing(expiresAfter: const Duration(minutes: 10));
        },
      );
      final router = GoRouter(
        initialLocation: profileStudentAccessPath,
        routes: [
          GoRoute(
            path: profileStudentAccessPath,
            builder: (_, _) => const StudentAccessPairingPage(),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            currentChildProvider.overrideWith((ref) async => _primaryChild),
            accountProfileProvider.overrideWith((ref) async => _viewerAccount),
            currentLearningPreparationProvider.overrideWith(
              (ref, childId) async => null,
            ),
            appEnvironmentProvider.overrideWithValue(_environment),
            studentAccessRepositoryProvider.overrideWithValue(repository),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('需要家庭管理员授权'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('createStudentPairingCode')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('openStudentAccessManagement')),
        findsNothing,
      );
      expect(createPairingCalls, 0);
    },
  );

  for (final gateCase
      in <
        ({
          String name,
          Future<LearningAvailability> Function() load,
          String title,
        })
      >[
        (
          name: 'loading availability',
          load: () => Completer<LearningAvailability>().future,
          title: '正在确认学习空间权限',
        ),
        (
          name: 'no workspace permission',
          load: () async => _availability(hasActiveRelease: false),
          title: '当前暂不能登录学习空间',
        ),
        (
          name: 'availability network error',
          load: () async => throw StateError('offline'),
          title: '学习空间权限暂时无法同步',
        ),
      ]) {
    testWidgets('direct pairing route fails closed for ${gateCase.name}', (
      tester,
    ) async {
      await _usePhoneViewport(tester);
      var createPairingCalls = 0;
      final repository = _FakeStudentAccessRepository(
        onCreate: ({required childId, required pin}) async {
          createPairingCalls += 1;
          return _pairing(expiresAfter: const Duration(minutes: 10));
        },
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            currentChildProvider.overrideWith((ref) async => _primaryChild),
            accountProfileProvider.overrideWith((ref) async => _adminAccount),
            studentAccessAvailabilityProvider.overrideWith(
              (ref, childId) => gateCase.load(),
            ),
            appEnvironmentProvider.overrideWithValue(_environment),
            studentAccessRepositoryProvider.overrideWithValue(repository),
          ],
          child: const MaterialApp(home: StudentAccessPairingPage()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(gateCase.title), findsOneWidget);
      expect(
        find.byKey(const ValueKey('createStudentPairingCode')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('openStudentAccessManagement')),
        findsNothing,
      );
      expect(createPairingCalls, 0);
    });
  }

  testWidgets('primary child profile opens the student learning space entry', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    final router = GoRouter(
      initialLocation: profileChildPath,
      routes: [
        GoRoute(
          path: profileChildPath,
          builder: (_, _) => const ChildProfilePage(),
        ),
        GoRoute(
          path: profileStudentAccessPath,
          builder: (_, _) => const Scaffold(body: Text('学生配对目标页')),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          currentChildProvider.overrideWith((ref) async => _primaryChild),
          accountProfileProvider.overrideWith((ref) async => _adminAccount),
          currentLearningPreparationProvider.overrideWith(
            (ref, childId) async => _readyPreparation(childId),
          ),
          currentLearningAvailabilityProvider.overrideWith(
            (ref, childId) async => _availability(
              hasActiveRelease: false,
              canAccessWorkspace: true,
            ),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final entry = find.text('学生学习空间');
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('studentLearningSpaceEntry')),
      360,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -140));
    await tester.pumpAndSettle();
    await tester.tap(entry);
    await tester.pumpAndSettle();

    expect(find.text('学生配对目标页'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'child profile keeps student learning space disabled without workspace permission',
    (tester) async {
      await _usePhoneViewport(tester);
      final router = GoRouter(
        initialLocation: profileChildPath,
        routes: [
          GoRoute(
            path: profileChildPath,
            builder: (_, _) => const ChildProfilePage(),
          ),
          GoRoute(
            path: profileStudentAccessPath,
            builder: (_, _) => const Scaffold(body: Text('学生配对目标页')),
          ),
        ],
      );
      addTearDown(router.dispose);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            currentChildProvider.overrideWith((ref) async => _primaryChild),
            accountProfileProvider.overrideWith((ref) async => _adminAccount),
            currentLearningPreparationProvider.overrideWith(
              (ref, childId) async => _preparation(
                childId: childId,
                status: 'queued',
                stage: 'queued',
              ),
            ),
            currentLearningAvailabilityProvider.overrideWith(
              (ref, childId) async => _availability(hasActiveRelease: false),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('studentLearningSpaceEntry')),
        360,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(find.text('请确认已选择开放年级并完成设置'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('studentLearningSpaceEntry')));
      await tester.pumpAndSettle();

      expect(find.text('学生配对目标页'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}

Future<void> _pumpPage(
  WidgetTester tester, {
  required StudentAccessRepository repository,
  StudentAccessClock? clock,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        currentChildProvider.overrideWith((ref) async => _primaryChild),
        accountProfileProvider.overrideWith((ref) async => _adminAccount),
        currentLearningPreparationProvider.overrideWith(
          (ref, childId) async => _readyPreparation(childId),
        ),
        studentAccessAvailabilityProvider.overrideWith(
          (ref, childId) async =>
              _availability(hasActiveRelease: false, canAccessWorkspace: true),
        ),
        appEnvironmentProvider.overrideWithValue(_environment),
        studentAccessRepositoryProvider.overrideWithValue(repository),
        if (clock != null) studentAccessClockProvider.overrideWithValue(clock),
      ],
      child: const MaterialApp(home: StudentAccessPairingPage()),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _enterPin(
  WidgetTester tester, {
  required String pin,
  required String confirmation,
}) async {
  final pinField = find.descendant(
    of: find.byKey(const ValueKey('studentPinField')),
    matching: find.byType(TextField),
  );
  final confirmationField = find.descendant(
    of: find.byKey(const ValueKey('studentPinConfirmField')),
    matching: find.byType(TextField),
  );
  await tester.enterText(pinField, pin);
  await tester.enterText(confirmationField, confirmation);
  await tester.pump();
}

AppPrimaryButton _primaryButton(WidgetTester tester) {
  return tester.widget<AppPrimaryButton>(
    find.byKey(const ValueKey('createStudentPairingCode')),
  );
}

Future<void> _usePhoneViewport(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
}

StudentPairingCode _pairing({required Duration expiresAfter, DateTime? now}) {
  return StudentPairingCode(
    code: 'ABCD2345',
    expiresAt: (now ?? DateTime.now()).add(expiresAfter),
    child: const StudentPairingChild(
      id: 'child-primary',
      name: '乐乐',
      nickname: '乐乐',
    ),
  );
}

LearningPreparation _readyPreparation(String childId) => _preparation(
  childId: childId,
  status: 'ready',
  stage: 'completed',
  progress: 100,
  ready: 30,
  subjectsReady: true,
  retryAfterMs: null,
);

LearningPreparation _preparation({
  String childId = 'child-primary',
  required String status,
  required String stage,
  int progress = 0,
  int ready = 0,
  int failed = 0,
  bool subjectsReady = false,
  int? retryAfterMs = 2500,
}) => LearningPreparation.fromJson({
  'schemaVersion': 'mira.learning.preparation.v1',
  'id': 'plan-$status',
  'childId': childId,
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
  'canRetry': status == 'failed',
  'retryAfterMs': retryAfterMs,
  'message': status == 'failed' ? '课程准备未完成' : '正在准备课程',
  'lastProgressAt': 1787200000000,
  'updatedAt': 1787200000000,
  'completedAt': stage == 'completed' ? 1787200000000 : null,
  'error': status == 'failed'
      ? const {'code': 'failed', 'message': '课程校验未通过'}
      : null,
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

final _environment = AppEnvironment(
  flavor: AppFlavor.test,
  apiBaseUrl: 'https://api.example.test/api',
  taskWebSocketBaseUrl: 'wss://api.example.test/api',
  studentWebBaseUrl: 'http://student.example.test',
);

final _primaryChild = ChildProfile.fromJson({
  'id': 'child-primary',
  'name': '乐乐',
  'nickname': '乐乐',
  'educationStage': '小学',
  'grade': '一年级',
  'gradeCode': 'primary_1',
});

final _primaryTwoChild = ChildProfile.fromJson({
  'id': 'child-primary-two',
  'name': '安安',
  'nickname': '安安',
  'educationStage': '小学',
  'grade': '二年级',
  'gradeCode': 'primary_2',
  'contentMode': 'primary_learning',
});

final _kindergartenChild = ChildProfile.fromJson({
  'id': 'child-kindergarten',
  'name': '安安',
  'educationStage': '幼儿园',
  'grade': '中班',
  'gradeCode': 'kindergarten_middle',
});

const _adminAccount = AccountProfile(
  userId: 'user-admin',
  phone: '13800000000',
  displayName: '妈妈',
  familyName: '乐乐家',
  relationship: '妈妈',
  relationshipKey: 'mom',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: ['manage_child_profile'],
  avatarPersona: '',
  gender: '',
  ageGroup: '',
);

const _viewerAccount = AccountProfile(
  userId: 'user-viewer',
  phone: '13900000000',
  displayName: '奶奶',
  familyName: '乐乐家',
  relationship: '奶奶',
  relationshipKey: 'grandma',
  role: 'viewer',
  roleLabel: '仅查看',
  capabilities: [],
  avatarPersona: '',
  gender: '',
  ageGroup: '',
);

typedef _CreateHandler =
    Future<StudentPairingCode> Function({
      required String childId,
      required String pin,
    });

class _FakeStudentAccessRepository extends StudentAccessRepository {
  _FakeStudentAccessRepository({required this.onCreate})
    : super(
        apiClient: ApiClient(Dio(BaseOptions(baseUrl: 'https://unused.test'))),
      );

  final _CreateHandler onCreate;

  @override
  Future<StudentPairingCode> createPairingCode({
    required String childId,
    required String pin,
  }) {
    return onCreate(childId: childId, pin: pin);
  }
}
