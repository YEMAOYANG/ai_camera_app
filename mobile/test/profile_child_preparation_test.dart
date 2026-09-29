import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_pages.dart';

import 'support/parent_textbook_visual_capture.dart';
import 'support/fixed_textbook_fixtures.dart';

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  testWidgets('child profile hides gender and birthday fields', (tester) async {
    final preparation = _ProfilePreparationGateway(value: _queued());
    final save = await _pumpProfile(
      tester,
      preparation: preparation,
      child: _child(gender: 'female', birthday: '2018-05-20'),
    );
    await tester.pumpAndSettle();

    await captureParentTextbookPreview(tester, 'child-profile-edit');

    expect(find.text('孩子称呼'), findsOneWidget);
    expect(find.text('学段'), findsOneWidget);
    expect(find.text('幼儿园'), findsNothing);
    expect(find.text('小学'), findsOneWidget);
    expect(find.text('性别'), findsNothing);
    expect(find.text('出生日期'), findsNothing);
    expect(find.textContaining('性别和生日'), findsNothing);

    await tester.enterText(find.byType(TextField).first, '乐乐新称呼');
    await tester.tap(find.text('保存资料'));
    await tester.pumpAndSettle();

    expect(save.lastBody?['gender'], 'female');
    expect(save.lastBody?['birthday'], '2018-05-20');
  });

  testWidgets(
    'fixed textbook status replaces the generation queue without polling',
    (tester) async {
      final preparation = _ProfilePreparationGateway(value: _queued());
      await _pumpProfile(tester, preparation: preparation);
      await tester.pumpAndSettle();

      await _scrollTo(tester, find.text('教材与课程'));
      expect(find.text('待选择学校教材'), findsNWidgets(4));
      expect(find.text('后台准备中'), findsNothing);
      expect(preparation.currentCalls, 0);
      await tester.pump(const Duration(seconds: 4));
      expect(preparation.currentCalls, 0);
    },
  );

  testWidgets(
    'grade disclosure changes the saved grade and asks for matching books',
    (tester) async {
      final preparation = _ProfilePreparationGateway(value: _queued());
      await _pumpProfile(tester, preparation: preparation);
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('gradeOption_primary_2')), findsNothing);
      await tester.tap(find.byKey(const ValueKey('childGradeDisclosure')));
      await tester.pump();
      await tester.tap(find.byKey(const ValueKey('gradeOption_primary_2')));
      await tester.pump();
      await tester.tap(find.text('保存资料'));
      await tester.pumpAndSettle();

      expect(find.text('年级已保存，请确认对应教材'), findsOneWidget);
      expect(preparation.currentCalls, 0);
    },
  );

  testWidgets(
    'nickname-only save preserves the grade and does not request generation',
    (tester) async {
      final preparation = _ProfilePreparationGateway(value: _queued());
      await _pumpProfile(tester, preparation: preparation);
      await tester.pumpAndSettle();

      final nickname = find.byType(TextField).first;
      await tester.enterText(nickname, '乐乐新称呼');
      await tester.tap(find.text('保存资料'));
      await tester.pumpAndSettle();

      expect(find.text('孩子资料已保存'), findsOneWidget);
      expect(find.text('年级已保存，请确认对应教材'), findsNothing);
      expect(preparation.currentCalls, 0);
    },
  );

  testWidgets('newly persisted legacy school year counts as grade change', (
    tester,
  ) async {
    final preparation = _ProfilePreparationGateway(value: _queued());
    await _pumpProfile(
      tester,
      preparation: preparation,
      child: _child(schoolYearStartYear: null),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('保存资料'));
    await tester.pumpAndSettle();

    expect(find.text('年级已保存，请确认对应教材'), findsOneWidget);
    expect(preparation.currentCalls, 0);
  });

  testWidgets('profile textbook read retry never invokes generation retry', (
    tester,
  ) async {
    final preparation = _ProfilePreparationGateway(
      error: StateError('offline'),
    );
    await _pumpProfile(tester, preparation: preparation);
    await tester.pumpAndSettle();

    await _scrollTo(tester, find.text('重试'));
    await tester.tap(find.text('重试'));
    await tester.pumpAndSettle();

    expect(preparation.currentCalls, 0);
    expect(preparation.retryCalls, 0);
  });
}

Future<_ProfileSaveInterceptor> _pumpProfile(
  WidgetTester tester, {
  required _ProfilePreparationGateway preparation,
  ChildProfile? child,
}) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  final initialChild = child ?? _child();
  final interceptor = _ProfileSaveInterceptor(initialChild);
  final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
    ..interceptors.add(interceptor);
  final repository = ProfileRepository(apiClient: ApiClient(dio));

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        profileRepositoryProvider.overrideWithValue(repository),
        currentChildProvider.overrideWith((ref) async => initialChild),
        accountProfileProvider.overrideWith((ref) async => _admin),
        studentAccessAvailabilityProvider.overrideWith(
          (ref, childId) async => const LearningAvailability(
            gradeCode: 'primary_1',
            hasActiveRelease: false,
            availableCourseCount: 0,
            canLearnNow: false,
          ),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
        schoolTextbooksProvider.overrideWith((ref, childId) async {
          if (preparation.error != null) throw preparation.error!;
          return fixtureCatalog();
        }),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        builder: (context, child) =>
            RepaintBoundary(key: parentTextbookPreviewKey, child: child!),
        home: const ChildProfilePage(),
      ),
    ),
  );
  return interceptor;
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    300,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

class _ProfilePreparationGateway implements LearningPreparationGateway {
  _ProfilePreparationGateway({this.value, this.error});

  LearningPreparation? value;
  Object? error;
  var currentCalls = 0;
  var retryCalls = 0;

  @override
  Future<LearningPreparation?> current(String childId) async {
    currentCalls += 1;
    if (error != null) throw error!;
    return value;
  }

  @override
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  }) async {
    retryCalls += 1;
    return value!;
  }
}

class _ProfileSaveInterceptor extends Interceptor {
  _ProfileSaveInterceptor(this.initial);

  final ChildProfile initial;
  Map<String, dynamic>? lastBody;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final body = Map<String, dynamic>.from(options.data as Map);
    lastBody = body;
    final child = {
      'id': initial.id,
      ...body,
      'educationStageCode': 'primary',
      'contentMode': 'primary_learning',
      'gradeConfirmedAt': 1787200000000,
    };
    handler.resolve(
      Response<dynamic>(
        requestOptions: options,
        statusCode: 200,
        data: {'ok': true, 'child': child},
      ),
    );
  }
}

LearningPreparation _queued() => LearningPreparation.fromJson({
  'schemaVersion': 'mira.learning.preparation.v1',
  'id': 'plan-queued',
  'childId': 'child-1',
  'gradeCode': 'primary_1',
  'gradeLabel': '一年级',
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

ChildProfile _child({
  int? schoolYearStartYear = 2026,
  String gender = 'unspecified',
  String birthday = '',
}) => ChildProfile(
  id: 'child-1',
  name: '乐乐',
  nickname: '乐乐',
  gender: gender,
  birthday: birthday,
  sleepTime: '21:00',
  ageStage: '小学 一年级',
  educationStage: '小学',
  grade: '一年级',
  gradeCode: 'primary_1',
  educationStageCode: 'primary',
  contentMode: 'primary_learning',
  schoolYearStartYear: schoolYearStartYear,
  schoolName: '',
  interests: const [],
  taskPreferences: const {},
);

const _admin = AccountProfile(
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
