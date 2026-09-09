import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_learning_preview.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/learning_preparation_card.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_pages.dart';

import 'support/learning_preparation_v2_fixtures.dart';

const _goldenTestFontPath = 'test/assets/fonts/NotoSansCJKsc-Regular.otf';

void main() {
  setUpAll(() async {
    final bytes = await File(_goldenTestFontPath).readAsBytes();
    final loader = FontLoader(AppTypography.systemFont)
      ..addFont(
        Future<ByteData>.value(
          ByteData.view(bytes.buffer, bytes.offsetInBytes, bytes.lengthInBytes),
        ),
      );
    await loader.load();
  });

  test('golden CJK font is a repository-owned relative test asset', () {
    expect(
      File(_goldenTestFontPath).path,
      isNot(File(_goldenTestFontPath).absolute.path),
    );
    expect(_goldenTestFontPath, startsWith('test/assets/fonts/'));
  });

  testWidgets(
    'queued card exposes actual progress without internal batch counts',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await _pumpCard(tester, LearningPreparationCard(preparation: _queued()));

      expect(find.text('首门课程准备好就能学'), findsOneWidget);
      expect(find.text('后台准备中'), findsOneWidget);
      expect(find.text('${_queued().progressPercent}%'), findsOneWidget);
      expect(find.textContaining('30'), findsNothing);
      expect(find.textContaining('门已就绪'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      expect(find.bySemanticsLabel('课程状态，后台准备中'), findsOneWidget);
      semantics.dispose();
    },
  );

  testWidgets(
    'shared supply pause keeps actual percentage and explains the wait',
    (tester) async {
      final payload = preparationV2Payload(progressPercent: 35);
      payload['courseSupply'] = {
        'schemaVersion': 'learning.course-supply-summary.v1',
        'version': 'v1',
        'requestedCount': 3,
        'readyCount': 0,
        'paused': true,
        'lastProgressAt': 1,
        'retryAfterMs': 30000,
        'message': '新课正在调整，准备好会自动出现。',
      };
      await _pumpCard(
        tester,
        LearningPreparationCard(
          preparation: LearningPreparation.fromJson(payload),
        ),
      );
      expect(find.text('新课准备暂时停在这里'), findsOneWidget);
      expect(find.text('等待恢复'), findsOneWidget);
      expect(find.text('35%'), findsOneWidget);
      expect(find.text('新课正在调整，准备好会自动出现。'), findsOneWidget);
    },
  );

  testWidgets(
    'retryable failed card keeps provider details hidden and restarts safely',
    (tester) async {
      final semantics = tester.ensureSemantics();
      var retryCalls = 0;
      var refreshCalls = 0;
      await _pumpCard(
        tester,
        LearningPreparationCard(
          preparation: _failed(),
          onRetry: () => retryCalls += 1,
          onRefresh: () => refreshCalls += 1,
        ),
      );

      expect(find.text('课程准备需要重新启动'), findsOneWidget);
      expect(find.text('本次准备已安全停止，可以重新发起课程准备。'), findsOneWidget);
      expect(find.text('重新准备课程'), findsOneWidget);
      expect(find.textContaining('系统校验'), findsNothing);
      expect(find.textContaining('30'), findsNothing);
      expect(
        tester.getSemantics(find.bySemanticsLabel('重新准备课程')),
        isSemantics(
          label: '重新准备课程',
          isButton: true,
          hasEnabledState: true,
          isEnabled: true,
          hasTapAction: true,
        ),
      );

      await tester.tap(find.text('重新准备课程'));
      await tester.pump();
      expect(retryCalls, 1);
      expect(refreshCalls, 0);
      semantics.dispose();
    },
  );

  testWidgets('non-retryable failed card explains the safe stop', (
    tester,
  ) async {
    var refreshCalls = 0;
    await _pumpCard(
      tester,
      LearningPreparationCard(
        preparation: _failed(canRetry: false),
        onRefresh: () => refreshCalls += 1,
      ),
    );

    expect(find.text('本次课程准备已暂停'), findsOneWidget);
    expect(find.textContaining('为避免重复生成'), findsOneWidget);
    expect(find.text('检查状态'), findsOneWidget);

    await tester.tap(find.text('检查状态'));
    await tester.pump();
    expect(refreshCalls, 1);
  });

  testWidgets('notice card exposes its refresh action to accessibility', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    var refreshCalls = 0;
    await _pumpCard(
      tester,
      LearningPreparationMissingCard(onRefresh: () => refreshCalls += 1),
    );

    final action = find.bySemanticsLabel('检查课程状态');
    expect(action, findsOneWidget);
    expect(
      tester.getSemantics(action),
      isSemantics(
        label: '检查课程状态',
        isButton: true,
        hasEnabledState: true,
        isEnabled: true,
        hasTapAction: true,
      ),
    );
    await tester.tap(find.text('检查状态'));
    await tester.pump();
    expect(refreshCalls, 1);
    semantics.dispose();
  });

  testWidgets('zero-total card omits determinate progress', (tester) async {
    await _pumpCard(tester, LearningPreparationCard(preparation: _zeroTotal()));

    expect(find.byType(LinearProgressIndicator), findsOneWidget);
  });

  testWidgets('ready content awaiting formal release stays in preparation', (
    tester,
  ) async {
    await _pumpCard(
      tester,
      LearningPreparationCard(preparation: _ready(), awaitingPublication: true),
    );

    expect(find.text('正在发布今日课程'), findsOneWidget);
    expect(find.text('正式发布校验中'), findsOneWidget);
    expect(find.text('99%'), findsOneWidget);
    expect(find.text('100%'), findsNothing);
    expect(find.text('学习空间已准备'), findsNothing);
  });

  testWidgets(
    'v2 displays preparation percentage without internal candidate counts',
    (tester) async {
      final semantics = tester.ensureSemantics();
      await _pumpCard(
        tester,
        LearningPreparationCard(preparation: _v2Partial()),
      );

      expect(find.text('首门课程准备好就能学'), findsOneWidget);
      expect(find.textContaining('3/30'), findsNothing);
      expect(find.textContaining('内容已通过'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
      expect(find.bySemanticsLabel('课程状态，后台准备中'), findsOneWidget);
      semantics.dispose();
    },
  );

  testWidgets('v2 handoff does not expose internal generation phases', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    final preparation = _v2Handoff();
    expect(preparation.isReady, isFalse);
    await _pumpCard(tester, LearningPreparationCard(preparation: preparation));

    expect(find.text('首门课程准备好就能学'), findsOneWidget);
    expect(find.textContaining('互动课件'), findsNothing);
    expect(find.textContaining('30'), findsNothing);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    expect(find.bySemanticsLabel('课程状态，后台准备中'), findsOneWidget);
    semantics.dispose();
  });

  for (final contentCase in [
    (name: '3 of 30', preparation: _v2Partial()),
    (name: '30 of 30', preparation: _v2Handoff()),
  ]) {
    testWidgets('v2 ${contentCase.name} card fits 320x760 at text scale 2', (
      tester,
    ) async {
      await _setViewport(tester, const Size(320, 760));
      await _pumpCard(
        tester,
        SingleChildScrollView(
          child: LearningPreparationCard(preparation: contentCase.preparation),
        ),
        textScale: 2,
      );

      expect(tester.takeException(), isNull);
    });
  }

  for (final size in const [Size(320, 760), Size(390, 844)]) {
    testWidgets(
      'preparation cards fit ${size.width.toInt()} px at text scale 2',
      (tester) async {
        await _setViewport(tester, size);
        await _pumpCard(
          tester,
          SingleChildScrollView(
            child: Column(
              children: [
                LearningPreparationCard(preparation: _failed(), onRetry: () {}),
                const SizedBox(height: 12),
                LearningPreparationMissingCard(onRefresh: () {}),
                const SizedBox(height: 12),
                LearningPreparationNetworkErrorCard(onRetry: () {}),
              ],
            ),
          ),
          textScale: 2,
        );

        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets('queued Home preparation golden at fixed phone surface', (
    tester,
  ) async {
    await _setViewport(tester, const Size(390, 844));
    final preparation = _GoldenPreparationGateway(_queued());
    final learning = _GoldenLearningGateway();
    await _pumpHomeGolden(tester, preparation: preparation, learning: learning);
    await tester.pumpAndSettle();

    expect(find.byType(HomePrimaryLearningPreview), findsOneWidget);
    expect(find.textContaining('语文、数学、英语智能轮换'), findsNothing);
    expect(learning.todayCalls, 0);

    await expectLater(
      find.byKey(const ValueKey('goldenSurface')),
      matchesGoldenFile('goldens/learning_preparation_home_queued.png'),
    );
  });

  testWidgets('failed Profile preparation golden at fixed phone surface', (
    tester,
  ) async {
    await _setViewport(tester, const Size(390, 844));
    await _pumpProfileGolden(
      tester,
      preparation: _GoldenPreparationGateway(_failed()),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text('课程准备需要重新启动'),
      260,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();

    expect(find.byType(ChildProfilePage), findsOneWidget);

    await expectLater(
      find.byKey(const ValueKey('goldenSurface')),
      matchesGoldenFile('goldens/learning_preparation_profile_failed.png'),
    );
  });
}

Future<void> _pumpCard(
  WidgetTester tester,
  Widget child, {
  double textScale = 1,
}) {
  return tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light,
      builder: (context, appChild) => MediaQuery(
        data: MediaQuery.of(
          context,
        ).copyWith(textScaler: TextScaler.linear(textScale)),
        child: appChild!,
      ),
      home: Scaffold(
        body: SafeArea(
          child: Padding(padding: const EdgeInsets.all(16), child: child),
        ),
      ),
    ),
  );
}

Future<void> _pumpHomeGolden(
  WidgetTester tester, {
  required _GoldenPreparationGateway preparation,
  required _GoldenLearningGateway learning,
}) {
  return tester.pumpWidget(
    ProviderScope(
      overrides: [
        profileSummaryProvider.overrideWith((ref) async => _goldenProfile),
        currentLearningAvailabilityProvider.overrideWith(
          (ref, childId) async => const LearningAvailability(
            gradeCode: 'primary_1',
            hasActiveRelease: false,
            availableCourseCount: 0,
            canLearnNow: false,
          ),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
        learningRepositoryProvider.overrideWithValue(learning),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: RepaintBoundary(
          key: const ValueKey('goldenSurface'),
          child: Scaffold(
            body: SafeArea(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(20, 28, 20, 20),
                child: const HomePrimaryLearningPreview(child: _goldenChild),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}

Future<void> _pumpProfileGolden(
  WidgetTester tester, {
  required _GoldenPreparationGateway preparation,
}) {
  return tester.pumpWidget(
    ProviderScope(
      overrides: [
        currentChildProvider.overrideWith((ref) async => _goldenChild),
        accountProfileProvider.overrideWith((ref) async => _goldenAdmin),
        currentLearningAvailabilityProvider.overrideWith(
          (ref, childId) async => const LearningAvailability(
            gradeCode: 'primary_1',
            hasActiveRelease: false,
            availableCourseCount: 0,
            canLearnNow: false,
            canAccessWorkspace: true,
          ),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: const RepaintBoundary(
          key: ValueKey('goldenSurface'),
          child: ChildProfilePage(),
        ),
      ),
    ),
  );
}

Future<void> _setViewport(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _GoldenPreparationGateway implements LearningPreparationGateway {
  _GoldenPreparationGateway(this.value);

  final LearningPreparation value;

  @override
  Future<LearningPreparation?> current(String childId) async => value;

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) async => value;
}

class _GoldenLearningGateway implements LearningGateway {
  var todayCalls = 0;

  @override
  Future<LearningToday> today(String childId) async {
    todayCalls += 1;
    return const LearningToday(state: LearningTodayState.unavailable);
  }

  @override
  Future<LearningReport?> latestReport(String childId, {String? subject}) =>
      throw UnimplementedError();
}

const _goldenChild = ChildProfile(
  id: 'child-1',
  name: '乐乐',
  nickname: '乐乐',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '21:00',
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

const _goldenProfile = ProfileSummary(
  spaceTitle: '乐乐家',
  familyId: 'family-1',
  familyName: '乐乐家',
  displayName: '妈妈',
  phone: '13800000000',
  relationship: '妈妈',
  relationshipKey: 'mother',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: ['manage_child_profile'],
  avatarPersona: '',
  memberCount: 2,
  deviceCount: 0,
  pendingItemCount: 0,
  child: _goldenChild,
);

const _goldenAdmin = AccountProfile(
  userId: 'parent-1',
  phone: '13800000000',
  displayName: '妈妈',
  familyName: '乐乐家',
  relationship: '妈妈',
  relationshipKey: 'mother',
  role: 'admin',
  roleLabel: '管理员',
  capabilities: ['manage_child_profile'],
  avatarPersona: '',
  gender: '',
  ageGroup: '',
);

LearningPreparation _queued() => LearningPreparation.fromJson(
  _payload(status: 'queued', stage: 'queued', message: '已进入备课队列'),
);

LearningPreparation _ready() => LearningPreparation.fromJson(
  _payload(
    status: 'ready',
    stage: 'completed',
    progressPercent: 100,
    readyCourseCount: 30,
    retryAfterMs: null,
    message: '课程已就绪',
    subjects: const [
      {
        'code': 'chinese',
        'label': '语文',
        'readyCourseCount': 12,
        'failedCourseCount': 0,
        'totalCourseCount': 12,
      },
      {
        'code': 'math',
        'label': '数学',
        'readyCourseCount': 9,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
      {
        'code': 'english',
        'label': '英语',
        'readyCourseCount': 9,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
    ],
  ),
);

LearningPreparation _failed({bool canRetry = true}) =>
    LearningPreparation.fromJson(
      _payload(
        status: 'failed',
        stage: 'completed',
        progressPercent: 36,
        readyCourseCount: 11,
        failedCourseCount: 1,
        canRetry: canRetry,
        retryAfterMs: null,
        subjects: const [
          {
            'code': 'chinese',
            'label': '语文',
            'readyCourseCount': 5,
            'failedCourseCount': 0,
            'totalCourseCount': 12,
          },
          {
            'code': 'math',
            'label': '数学',
            'readyCourseCount': 4,
            'failedCourseCount': 1,
            'totalCourseCount': 9,
          },
          {
            'code': 'english',
            'label': '英语',
            'readyCourseCount': 2,
            'failedCourseCount': 0,
            'totalCourseCount': 9,
          },
        ],
        message: '课程准备未完成',
        error: const {
          'code': 'preparation_validation_failed',
          'message': '部分课程未通过系统校验，请重新准备',
        },
      ),
    );

LearningPreparation _zeroTotal() => LearningPreparation.fromJson(
  _payload(
    status: 'running',
    stage: 'planning',
    totalCourseCount: 0,
    subjects: const [
      {
        'code': 'chinese',
        'label': '语文',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 0,
      },
      {
        'code': 'math',
        'label': '数学',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 0,
      },
      {
        'code': 'english',
        'label': '英语',
        'readyCourseCount': 0,
        'failedCourseCount': 0,
        'totalCourseCount': 0,
      },
    ],
  ),
);

LearningPreparation _v2Partial() => LearningPreparation.fromJson(
  preparationV2Payload(
    id: 'plan-v2-partial',
    candidateCount: 3,
    subjectCandidates: const [1, 1, 1],
    stage: 'generating_content',
    progressPercent: 8,
  ),
);

LearningPreparation _v2Handoff() => LearningPreparation.fromJson(
  preparationV2Payload(
    id: 'plan-v2-handoff',
    candidateCount: 30,
    stage: 'building_classrooms',
    progressPercent: 35,
  ),
);

Map<String, dynamic> _payload({
  String status = 'running',
  String stage = 'planning',
  int progressPercent = 0,
  int totalCourseCount = 30,
  int readyCourseCount = 0,
  int failedCourseCount = 0,
  bool canRetry = false,
  int? retryAfterMs = 2500,
  String message = '正在准备课程',
  List<Map<String, dynamic>>? subjects,
  Map<String, dynamic>? error,
}) {
  return {
    'schemaVersion': 'mira.learning.preparation.v1',
    'id': 'plan-1',
    'childId': 'child-1',
    'gradeCode': 'primary_1',
    'gradeLabel': '一年级',
    'subjects':
        subjects ??
        const [
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
    'status': status,
    'stage': stage,
    'progressPercent': progressPercent,
    'totalCourseCount': totalCourseCount,
    'readyCourseCount': readyCourseCount,
    'failedCourseCount': failedCourseCount,
    'attempt': 1,
    'canRetry': canRetry,
    'retryAfterMs': retryAfterMs,
    'message': message,
    'lastProgressAt': 1787200000000,
    'updatedAt': 1787200000000,
    'completedAt': status == 'failed' ? 1787200001000 : null,
    'error': error,
  };
}
