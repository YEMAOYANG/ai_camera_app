import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_learning_preview.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';

void main() {
  testWidgets(
    'empty grade shows no progress and stops stale preparation polling',
    (tester) async {
      final gateway = _FakeLearningGateway();
      final preparation = _FailingPollPreparationGateway();
      final availability = _EmptyAvailabilityGateway();
      final child = ChildProfile.fromJson({
        'id': 'child-1',
        'name': '小雨',
        'nickname': '小雨',
        'educationStage': '小学',
        'grade': '六年级',
        'gradeCode': 'primary_6',
        'contentMode': 'primary_learning',
      });
      await tester.pumpWidget(
        ProviderScope(
          overrides: _overrides(
            gateway,
            preparationGateway: preparation,
            availabilityGateway: availability,
          ),
          child: MaterialApp(
            home: Scaffold(body: HomePrimaryLearningPreview(child: child)),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('暂无课程'), findsOneWidget);
      expect(find.textContaining('扫码进入学习空间'), findsOneWidget);
      expect(find.textContaining('未开放'), findsNothing);
      expect(find.textContaining('备课'), findsNothing);
      expect(find.textContaining('准备中'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsNothing);
      expect(gateway.todayCalls, 0);
      expect(preparation.calls, 1);
      expect(availability.calls, 1);
      await tester.pump(const Duration(minutes: 2));
      expect(preparation.calls, 1);
      expect(availability.calls, 1);
      expect(find.textContaining('%'), findsNothing);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('student completion updates silently and pauses in background', (
    tester,
  ) async {
    final gateway = _FakeLearningGateway(startAssigned: true);
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(gateway),
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: HomePrimaryLearningPreview(child: _primaryChild),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('今日课程已准备'), findsOneWidget);
    expect(gateway.todayCalls, 1);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    gateway.todayCompleted = true;
    await tester.pump(const Duration(seconds: 60));
    expect(gateway.todayCalls, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text('已完成'), findsOneWidget);
    expect(find.text('查看学习报告'), findsOneWidget);

    gateway.todayCompleted = false;
    await tester.pump(const Duration(seconds: 30));
    await tester.pumpAndSettle();
    expect(find.text('今日课程已准备'), findsOneWidget);
    expect(find.text('今日课程加载失败'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
    'renders all three daily slots without repeated Student Web actions',
    (tester) async {
      final gateway = _FakeLearningGateway(twoItems: true, startAssigned: true);
      await tester.pumpWidget(
        ProviderScope(
          overrides: _overrides(gateway),
          child: MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: HomePrimaryLearningPreview(child: _primaryChild),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      expect(find.text('今日第 1 课 · 数学'), findsOneWidget);
      expect(find.text('今日第 2 课 · 英语'), findsOneWidget);
      expect(find.text('今日第 3 课 · 语文'), findsOneWidget);
      expect(find.text('真实课程：三位数加法'), findsOneWidget);
      expect(find.text('Everyday English'), findsOneWidget);
      expect(find.text('扫码登录学生网页'), findsNothing);
      expect(
        find.byKey(const ValueKey('learningPrimaryAction_rotation')),
        findsNothing,
      );
      expect(find.text('课程在学生学习空间完成；家长端只展示准备状态与学习结果。'), findsNWidgets(3));
      expect(find.byKey(const ValueKey('learningAnswerField')), findsNothing);
    },
  );

  testWidgets(
    'active lesson stays status-only and never resumes in parent app',
    (tester) async {
      final gateway = _FakeLearningGateway(
        startAssigned: true,
        todayInProgress: true,
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: _overrides(gateway),
          child: MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: HomePrimaryLearningPreview(child: _primaryChild),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      expect(find.text('学习中'), findsOneWidget);
      expect(find.text('扫码登录学生网页'), findsNothing);
      expect(find.byType(AppPrimaryButton), findsNothing);
      expect(find.byKey(const ValueKey('learningTeachStage')), findsNothing);
      expect(find.byKey(const ValueKey('learningAnswerField')), findsNothing);
      expect(find.byKey(const ValueKey('learningSubmitAnswer')), findsNothing);
    },
  );

  testWidgets(
    'completed lesson report is read-only and never starts a session',
    (tester) async {
      final gateway = _FakeLearningGateway(
        startAssigned: true,
        todayCompleted: true,
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: _overrides(gateway),
          child: const MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: HomePrimaryLearningPreview(child: _primaryChild),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      await tester.tap(find.text('查看学习报告'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      expect(find.byKey(const ValueKey('learningRecap')), findsNothing);
      expect(find.byKey(const ValueKey('learningReport')), findsOneWidget);
    },
  );

  testWidgets('today learning renders loading, error and retry states', (
    tester,
  ) async {
    final gateway = _FakeLearningGateway(failToday: true);
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(gateway),
        child: MaterialApp(
          home: Scaffold(
            body: HomePrimaryLearningPreview(child: _primaryChild),
          ),
        ),
      ),
    );

    expect(find.text('正在获取课程准备状态…'), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.text('今日课程加载失败'), findsOneWidget);
    expect(find.text('网络不可用'), findsOneWidget);

    gateway.failToday = false;
    await tester.tap(find.text('重试').last);
    await tester.pumpAndSettle();
    expect(find.text('课程已就绪'), findsOneWidget);
    expect(find.text('扫码登录学生网页'), findsNothing);
    expect(find.byType(AppPrimaryButton), findsNothing);
    expect(find.text('安排今日课程'), findsNothing);
  });

  testWidgets('ready recommendation stays informational in the parent app', (
    tester,
  ) async {
    final gateway = _FakeLearningGateway();
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(gateway),
        child: MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: HomePrimaryLearningPreview(child: _primaryChild),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('真实课程：三位数加法'), findsOneWidget);
    expect(find.text('课程已就绪'), findsOneWidget);
    expect(find.text('扫码登录学生网页'), findsNothing);
    expect(find.byType(AppPrimaryButton), findsNothing);
    expect(find.text('安排今日课程'), findsNothing);
  });

  testWidgets('active release stays visible while new lessons build', (
    tester,
  ) async {
    final gateway = _FakeLearningGateway(startAssigned: true);
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(
          gateway,
          preparationGateway: _RunningPreparationGateway(),
        ),
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: HomePrimaryLearningPreview(child: _primaryChild),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));

    expect(find.text('真实课程：三位数加法'), findsOneWidget);
    expect(find.textContaining('新课准备好后会自动出现'), findsOneWidget);
    expect(find.text('正在准备今日课程'), findsNothing);
    expect(find.text('35%'), findsNothing);
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  testWidgets('first progressively published course opens learning now', (
    tester,
  ) async {
    final gateway = _FakeLearningGateway(
      startAssigned: true,
      progressiveSlots: true,
    );
    final availability = _ProgressiveAvailabilityGateway(availableCount: 0);
    await tester.pumpWidget(
      ProviderScope(
        overrides: _overrides(
          gateway,
          preparationGateway: _RunningPreparationGateway(),
          availabilityGateway: availability,
        ),
        child: const MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: HomePrimaryLearningPreview(child: _primaryChild),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('35%'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    expect(gateway.todayCalls, 0);

    availability.availableCount = 1;
    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();

    expect(find.text('真实课程：三位数加法'), findsOneWidget);
    expect(find.text('今日第 2 课 · 准备中'), findsOneWidget);
    expect(find.text('今日第 3 课 · 准备中'), findsOneWidget);
    expect(find.textContaining('已就绪 1 门课程，新课准备好后会自动出现'), findsOneWidget);
    expect(find.text('正在准备今日课程'), findsNothing);
    expect(find.text('35%'), findsNothing);
    expect(find.byType(LinearProgressIndicator), findsNothing);
  });

  testWidgets(
    'an available course stops preparation polling without an error banner',
    (tester) async {
      final gateway = _FakeLearningGateway(startAssigned: true);
      await tester.pumpWidget(
        ProviderScope(
          overrides: _overrides(
            gateway,
            preparationGateway: _FailingPollPreparationGateway(),
          ),
          child: const MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: HomePrimaryLearningPreview(child: _primaryChild),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.pump(const Duration(milliseconds: 2100));
      await tester.pump();

      expect(find.text('真实课程：三位数加法'), findsOneWidget);
      expect(find.text('现有课程可正常使用，进度同步稍慢，已保留上次结果'), findsNothing);
      expect(find.text('课程状态暂时无法同步'), findsNothing);
      expect(find.text('35%'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsNothing);
    },
  );
}

dynamic _overrides(
  _FakeLearningGateway gateway, {
  LearningPreparationGateway? preparationGateway,
  LearningAvailabilityGateway? availabilityGateway,
}) => [
  learningRepositoryProvider.overrideWithValue(gateway),
  learningAvailabilityRepositoryProvider.overrideWithValue(
    availabilityGateway ?? _ActiveAvailabilityGateway(),
  ),
  learningPreparationRepositoryProvider.overrideWithValue(
    preparationGateway ?? _ReadyPreparationGateway(),
  ),
];

class _ActiveAvailabilityGateway implements LearningAvailabilityGateway {
  @override
  Future<LearningAvailability> current(String childId) async {
    return const LearningAvailability(
      gradeCode: 'primary_1',
      hasActiveRelease: true,
      availableCourseCount: 30,
      canLearnNow: true,
    );
  }
}

class _EmptyAvailabilityGateway implements LearningAvailabilityGateway {
  var calls = 0;

  @override
  Future<LearningAvailability> current(String childId) async {
    calls += 1;
    return const LearningAvailability(
      gradeCode: 'primary_6',
      hasActiveRelease: false,
      availableCourseCount: 0,
      canLearnNow: false,
      canAccessWorkspace: true,
      learningState: LearningAvailabilityState(
        status: 'empty',
        availableCourseCount: 0,
        newCourseCount: 0,
        reviewCourseCount: 0,
        message: '可以扫码进入学习空间，当前暂无课程。',
      ),
    );
  }
}

class _ProgressiveAvailabilityGateway implements LearningAvailabilityGateway {
  _ProgressiveAvailabilityGateway({this.availableCount = 1});

  int availableCount;

  @override
  Future<LearningAvailability> current(String childId) async {
    return LearningAvailability(
      gradeCode: 'primary_1',
      hasActiveRelease: false,
      availableCourseCount: availableCount,
      canLearnNow: availableCount > 0,
    );
  }
}

class _ReadyPreparationGateway implements LearningPreparationGateway {
  @override
  Future<LearningPreparation?> current(String childId) async =>
      _readyPreparation();

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) async => _readyPreparation();
}

class _RunningPreparationGateway extends _ReadyPreparationGateway {
  @override
  Future<LearningPreparation?> current(String childId) async =>
      _runningPreparation();
}

class _FailingPollPreparationGateway extends _RunningPreparationGateway {
  var calls = 0;

  @override
  Future<LearningPreparation?> current(String childId) async {
    calls += 1;
    if (calls > 1) throw StateError('offline');
    return _runningPreparation();
  }
}

LearningPreparation _readyPreparation() => LearningPreparation.fromJson({
  'schemaVersion': 'mira.learning.preparation.v1',
  'id': 'plan-ready',
  'childId': 'child-1',
  'gradeCode': 'primary_1',
  'gradeLabel': '一年级',
  'subjects': const [
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
  'status': 'ready',
  'stage': 'completed',
  'progressPercent': 100,
  'totalCourseCount': 30,
  'readyCourseCount': 30,
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

LearningPreparation _runningPreparation() => LearningPreparation.fromJson({
  'schemaVersion': 'mira.learning.preparation.v1',
  'id': 'plan-running',
  'childId': 'child-1',
  'gradeCode': 'primary_1',
  'gradeLabel': '一年级',
  'subjects': const [],
  'status': 'running',
  'stage': 'building_classrooms',
  'progressPercent': 35,
  'totalCourseCount': 30,
  'readyCourseCount': 0,
  'failedCourseCount': 0,
  'attempt': 1,
  'canRetry': false,
  'retryAfterMs': 2000,
  'message': '正在生成新课',
  'lastProgressAt': 1787200000000,
  'updatedAt': 1787200000000,
  'completedAt': null,
  'error': null,
});

class _FakeLearningGateway implements LearningGateway {
  _FakeLearningGateway({
    this.failToday = false,
    bool startAssigned = false,
    this.twoItems = false,
    this.progressiveSlots = false,
    this.todayInProgress = false,
    this.todayCompleted = false,
  }) : assigned = startAssigned;

  bool failToday;
  bool assigned;
  final bool twoItems;
  final bool progressiveSlots;
  final bool todayInProgress;
  bool todayCompleted;
  int todayCalls = 0;

  @override
  Future<LearningToday> today(String childId) async {
    todayCalls++;
    if (failToday) {
      throw const LearningException('网络不可用', code: 'offline');
    }
    final first = LearningToday(
      state: todayCompleted
          ? LearningTodayState.completed
          : todayInProgress
          ? LearningTodayState.inProgress
          : assigned
          ? LearningTodayState.scheduled
          : LearningTodayState.recommended,
      lesson: _lesson,
      task: assigned || todayCompleted ? _task : null,
      session: todayInProgress
          ? _session(question: _question1, index: 0)
          : null,
      report: todayCompleted ? _report : null,
    );
    if (progressiveSlots) {
      return LearningToday(
        state: first.state,
        lesson: first.lesson,
        task: first.task,
        items: [
          first,
          const LearningToday(
            state: LearningTodayState.preparing,
            slot: 'rotation',
            message: '数学课程正在完成发布校验。',
          ),
          const LearningToday(
            state: LearningTodayState.preparing,
            slot: 'extension',
            message: '英语课程正在完成发布校验。',
          ),
        ],
      );
    }
    if (!twoItems) return first;
    return LearningToday(
      state: first.state,
      lesson: first.lesson,
      task: first.task,
      items: [
        first,
        const LearningToday(
          state: LearningTodayState.scheduled,
          slot: 'rotation',
          lesson: _englishLesson,
          task: _englishTask,
        ),
        const LearningToday(
          state: LearningTodayState.scheduled,
          slot: 'extension',
          lesson: _chineseLesson,
          task: _chineseTask,
        ),
      ],
    );
  }

  @override
  Future<LearningReport?> latestReport(
    String childId, {
    String? subject,
  }) async => _report;
}

LearningSession _session({
  required LearningQuestion? question,
  required int index,
  String taskId = 'task-1',
}) {
  return LearningSession(
    id: 'session-1',
    taskId: taskId,
    status: 'in_progress',
    currentIndex: index,
    totalQuestions: 2,
    correctCount: 0,
    hintCount: 0,
    currentQuestion: question,
  );
}

const _lesson = LearningLesson(
  id: 'course-1',
  title: '真实课程：三位数加法',
  subject: '数学',
  skill: '掌握连续进位',
  gradeLabel: '一年级',
  estimatedMinutes: 10,
  questionCount: 2,
  introduction: '从位值理解进位。',
);

const _task = LearningTask(
  id: 'task-1',
  status: 'scheduled',
  scheduledStart: '19:30',
  lesson: _lesson,
);

const _englishLesson = LearningLesson(
  id: 'course-english-1',
  title: 'Everyday English',
  subject: 'english',
  subjectCode: 'english',
  skill: '认识日常问候语',
  gradeLabel: '一年级',
  estimatedMinutes: 8,
  questionCount: 5,
  introduction: '用简短对话练习问候。',
);

const _englishTask = LearningTask(
  id: 'task-2',
  status: 'scheduled',
  scheduledStart: '19:45',
  lesson: _englishLesson,
);

const _chineseLesson = LearningLesson(
  id: 'course-chinese-1',
  title: '识字与表达',
  subject: '语文',
  subjectCode: 'chinese',
  skill: '认识常用汉字',
  gradeLabel: '一年级',
  estimatedMinutes: 8,
  questionCount: 5,
  introduction: '从图画理解汉字含义。',
);

const _chineseTask = LearningTask(
  id: 'task-3',
  status: 'scheduled',
  scheduledStart: '20:00',
  lesson: _chineseLesson,
);

const _question1 = LearningQuestion(
  id: 'q-1',
  prompt: '325 + 168 等于多少？',
  options: [],
);

const _report = LearningReport(
  id: 'report-1',
  summary: '已掌握三位数加法的进位方法。',
  totalQuestions: 2,
  correctCount: 2,
  independentCorrectCount: 1,
  hintCount: 1,
  masteryLabel: '已掌握',
  nextSuggestion: '明天复习一道连续进位题。',
);

const _primaryChild = ChildProfile(
  id: 'child-1',
  name: '小雨',
  nickname: '小雨',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '',
  ageStage: '',
  educationStage: '小学',
  grade: '一年级',
  gradeCode: 'primary_1',
  educationStageCode: 'primary',
  contentMode: 'primary_learning',
  schoolName: '',
  interests: [],
  taskPreferences: {},
);
