import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_pages.dart';

void main() {
  testWidgets('child profile hides gender and birthday fields', (tester) async {
    final preparation = _ProfilePreparationGateway(value: _queued());
    final save = await _pumpProfile(
      tester,
      preparation: preparation,
      child: _child(gender: 'female', birthday: '2018-05-20'),
    );
    await tester.pumpAndSettle();

    expect(find.text('孩子称呼'), findsOneWidget);
    expect(find.text('就读阶段'), findsOneWidget);
    expect(find.text('幼儿园'), findsOneWidget);
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
    'queued preparation is visible in child profile without polling',
    (tester) async {
      final preparation = _ProfilePreparationGateway(value: _queued());
      await _pumpProfile(tester, preparation: preparation);
      await tester.pumpAndSettle();

      await _scrollTo(tester, find.text('首门课程准备好就能学'));
      expect(find.text('后台准备中'), findsOneWidget);
      expect(preparation.currentCalls, 1);
      await tester.pump(const Duration(seconds: 4));
      expect(preparation.currentCalls, 1);
    },
  );

  testWidgets(
    'persisted primary grade stays selectable and starts background preparation',
    (tester) async {
      final preparation = _ProfilePreparationGateway(value: _queued());
      await _pumpProfile(tester, preparation: preparation);
      await tester.pumpAndSettle();

      await _scrollTo(tester, find.text('二年级'));
      await tester.tap(find.text('二年级'));
      await tester.pump();
      await tester.tap(find.text('保存资料'));
      await tester.pumpAndSettle();

      expect(find.text('年级已保存，课程将在后台准备'), findsOneWidget);
      expect(preparation.currentCalls, 2);
    },
  );

  testWidgets('nickname-only save keeps old toast and preparation authority', (
    tester,
  ) async {
    final preparation = _ProfilePreparationGateway(value: _queued());
    await _pumpProfile(tester, preparation: preparation);
    await tester.pumpAndSettle();

    final nickname = find.byType(TextField).first;
    await tester.enterText(nickname, '乐乐新称呼');
    await tester.tap(find.text('保存资料'));
    await tester.pumpAndSettle();

    expect(find.text('孩子资料已保存'), findsOneWidget);
    expect(find.text('年级已保存，课程将在后台准备'), findsNothing);
    expect(preparation.currentCalls, 1);
  });

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

    expect(find.text('年级已保存，课程将在后台准备'), findsOneWidget);
    expect(preparation.currentCalls, 2);
  });

  testWidgets('profile network status refresh never invokes generation retry', (
    tester,
  ) async {
    final preparation = _ProfilePreparationGateway(
      error: StateError('offline'),
    );
    await _pumpProfile(tester, preparation: preparation);
    await tester.pumpAndSettle();

    await _scrollTo(tester, find.text('重新获取状态'));
    await tester.tap(find.text('重新获取状态'));
    await tester.pumpAndSettle();

    expect(preparation.currentCalls, 2);
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
        currentLearningAvailabilityProvider.overrideWith(
          (ref, childId) async => const LearningAvailability(
            gradeCode: 'primary_1',
            hasActiveRelease: false,
            availableCourseCount: 0,
            canLearnNow: false,
          ),
        ),
        learningPreparationRepositoryProvider.overrideWithValue(preparation),
      ],
      child: const MaterialApp(home: ChildProfilePage()),
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
