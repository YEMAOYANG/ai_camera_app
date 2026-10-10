import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';
import 'package:warm_sight/src/features/homework/application/homework_repository.dart';
import 'package:warm_sight/src/features/homework/presentation/homework_create_page.dart';
import 'package:warm_sight/src/features/homework/presentation/homework_detail_page.dart';
import 'package:warm_sight/src/features/learning_review/application/learning_review_repository.dart';
import 'package:warm_sight/src/features/learning_review/presentation/learning_center_page.dart';
import 'package:warm_sight/src/features/learning_review/presentation/review_detail_page.dart';
import 'package:warm_sight/src/features/learning_review/presentation/review_preferences_page.dart';
import 'support/parent_textbook_visual_capture.dart';

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  Future<void> pump(WidgetTester tester, Widget page, Dio dio) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeworkRepositoryProvider.overrideWithValue(
            HomeworkRepository(ApiClient(dio)),
          ),
          learningReviewRepositoryProvider.overrideWithValue(
            LearningReviewRepository(ApiClient(dio)),
          ),
          homeworkPhotoPickerProvider.overrideWithValue(
            HomeworkPhotoPicker(ImagePicker(), prefs, () => 'test-parent'),
          ),
          homeworkPhotoRecoveryProvider.overrideWith(
            (ref, childId) async => null,
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: RepaintBoundary(key: parentTextbookPreviewKey, child: page),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
  }

  Dio server(Object Function(RequestOptions) handler) {
    final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (r, h) =>
            h.resolve(Response(requestOptions: r, data: handler(r))),
      ),
    );
    return dio;
  }

  testWidgets(
    'learning center shows honest empty evidence and both workflows at phone width',
    (tester) async {
      final dio = server(
        (r) => {'reviews': [], 'submissions': [], 'weaknesses': []},
      );
      await pump(tester, const LearningCenterPage(childId: 'child_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text('拍作业或试卷'), findsOneWidget);
      expect(find.text('周末小复习'), findsOneWidget);
      expect(find.text('本周还没有复习安排。系统会根据已完成课程的作答记录准备短复习。'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await captureParentTextbookPreview(tester, 'learning-center-empty');
    },
  );
  testWidgets(
    'upload requires explicit consent before creating server record',
    (tester) async {
      var creates = 0;
      final dio = server((r) {
        if (r.method == 'POST') creates++;
        return {};
      });
      await pump(tester, const HomeworkCreatePage(childId: 'child_1'), dio);
      await tester.pumpAndSettle();
      expect(find.textContaining('家长无需输入正确答案'), findsOneWidget);
      await tester.ensureVisible(find.text('创建并添加照片'));
      await tester.tap(find.text('创建并添加照片'));
      await tester.pump();
      expect(creates, 0);
      await tester.ensureVisible(find.byType(CheckboxListTile));
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pump();
      expect(tester.takeException(), isNull);
      await captureParentTextbookPreview(tester, 'homework-create');
    },
  );
  testWidgets(
    'AI tutor availability explains general questions without claiming verified mastery',
    (tester) async {
      final dio = server(
        (r) => {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '语文阅读练习',
            'status': 'ready',
            'revision': 3,
            'processing': false,
            'pages': [],
            'summary': {'total': 1, 'pending': 1, 'unsupported': 1},
            'tutorAvailable': true,
            'tutorSummary': {'readyTurnCount': 2},
            'items': [
              {
                'id': 'item_1',
                'revision': 1,
                'prompt': '为什么小鸟飞走了？',
                'status': 'pending',
                'tutorEnabled': true,
              },
            ],
          },
        },
      );
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.textContaining('用语音连续提问'), findsOneWidget);
      expect(find.textContaining('AI 老师已完成 2 次指导'), findsOneWidget);
      expect(find.textContaining('不计为已验证的独立掌握成绩'), findsOneWidget);
      expect(find.textContaining('这些题暂不进入学生端订正'), findsNothing);
      expect(find.textContaining('不会直接计为错题'), findsOneWidget);
      expect(find.textContaining('无需填写题目或答案'), findsOneWidget);
      expect(find.text('核对识别内容（可选）'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'parent result directs child to teacher with accurate ready and corrected counts',
    (tester) async {
      final methods = <String>[];
      final dio = server((r) {
        methods.add(r.method);
        return {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '周三数学练习',
            'revision': 3,
            'status': 'ready',
            'processing': false,
            'pages': [],
            'summary': {'incorrect': 3, 'pending': 1},
            'items': [
              {
                'id': 'ready',
                'status': 'incorrect',
                'readyForStudent': true,
                'correctionStatus': 'pending',
              },
              {
                'id': 'done',
                'status': 'incorrect',
                'readyForStudent': true,
                'correctionStatus': 'corrected',
              },
              {
                'id': 'preparing',
                'status': 'incorrect',
                'answerMode': 'picture_choice',
                'readyForStudent': false,
                'correctionStatus': 'pending',
              },
              {'id': 'uncertain', 'status': 'pending'},
            ],
          },
        };
      });
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text('学生端跟老师订正'), findsOneWidget);
      expect(find.text('孩子已订正 1 / 3 题'), findsOneWidget);
      expect(find.text('有 1 道错题可以跟老师订正。'), findsOneWidget);
      expect(find.text('还有 1 道错题的图片和语音尚未准备好。'), findsOneWidget);
      expect(find.text('在孩子的学生端打开“作业与试卷”，选择“周三数学练习”。'), findsOneWidget);
      expect(find.textContaining('家长不需要输入正确答案'), findsOneWidget);
      expect(find.textContaining('无需家长填写答案'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      await tester.pump(const Duration(seconds: 8));
      expect(methods, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'parent result does not claim student activities ready before voice media is ready',
    (tester) async {
      final dio = server(
        (r) => {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'status': 'media_preparing',
            'processing': false,
            'pages': [],
            'summary': {'incorrect': 1},
            'items': [
              {
                'id': 'item_1',
                'status': 'incorrect',
                'answerMode': 'picture_choice',
                'readyForStudent': false,
              },
            ],
          },
        },
      );
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text('孩子已订正 0 / 1 题'), findsOneWidget);
      expect(find.text('还有 1 道错题的图片和语音尚未准备好。'), findsOneWidget);
      expect(find.textContaining('可以跟老师订正。'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'unsupported correction does not promise automatic teacher activity or ask parent to teach',
    (tester) async {
      final dio = server(
        (r) => {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'status': 'ready',
            'processing': false,
            'pages': [],
            'summary': {'incorrect': 1},
            'studentSummary': {
              'ready': 0,
              'awaitingMedia': 0,
              'unsupportedCorrection': 1,
              'corrected': 0,
            },
            'items': [
              {'id': 'item_1', 'status': 'incorrect', 'readyForStudent': false},
            ],
          },
        },
      );
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text('有 1 道错题暂不支持学生端自动讲解，已保留分析记录。'), findsOneWidget);
      expect(find.textContaining('图片和语音尚未准备好'), findsNothing);
      expect(find.textContaining('AI 老师会讲解'), findsNothing);
      expect(find.byType(TextField), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'unknown provider outcome only refreshes on request and never retries or polls',
    (tester) async {
      final methods = <String>[];
      final dio = server((r) {
        methods.add(r.method);
        return {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'revision': 2,
            'status': 'provider_unknown',
            'processing': true,
            'retryAllowed': true,
            'pages': [],
            'items': [],
          },
        };
      });
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text('处理结果尚未确认'), findsOneWidget);
      expect(find.textContaining('上次分析未能确认结果，照片已保存'), findsOneWidget);
      expect(find.textContaining('正在核实'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsNothing);
      expect(find.text('拍一页'), findsNothing);
      expect(find.text('从相册选多页'), findsNothing);
      expect(find.text('重试分析'), findsNothing);
      expect(find.text('重新分析'), findsNothing);
      await tester.pump(const Duration(seconds: 8));
      expect(methods, ['GET']);
      await tester.ensureVisible(find.text('刷新状态'));
      await tester.tap(find.text('刷新状态'));
      await tester.pumpAndSettle();
      expect(methods, ['GET', 'GET']);
      expect(find.text('处理结果尚未确认'), findsOneWidget);
      await tester.pump(const Duration(seconds: 8));
      expect(methods, ['GET', 'GET']);
      await tester.tap(find.byTooltip('删除作业'));
      await tester.pumpAndSettle();
      expect(find.text('删除这份作业？'), findsOneWidget);
      await tester.tap(find.text('取消'));
      await tester.pumpAndSettle();
      expect(methods, ['GET', 'GET']);
      expect(tester.takeException(), isNull);
    },
  );
  for (final issue in [
    (
      name: 'recognition unknown',
      status: 'provider_unknown',
      field: 'error',
      code: 'homework_provider_unknown',
      label: '识别结果暂未确认',
      detail: '题目识别结果暂未确认',
    ),
    (
      name: 'teacher voice unknown',
      status: 'provider_unknown',
      field: 'errorCode',
      code: 'homework_audio_unknown',
      label: '教师语音暂未准备好',
      detail: '作业识别结果和照片已保存',
    ),
    (
      name: 'incomplete saved recognition result',
      status: 'failed',
      field: 'error',
      code: 'homework_recognition_truncated',
      label: '识别结果需要处理',
      detail: '这次返回的识别结果不完整',
    ),
  ]) {
    testWidgets('${issue.name} offers read-only refresh without resending', (
      tester,
    ) async {
      final methods = <String>[];
      final dio = server((r) {
        methods.add(r.method);
        return {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'revision': 2,
            'status': issue.status,
            issue.field: issue.code,
            'processing': false,
            'retryAllowed': true,
            'pages': [],
            'items': [],
          },
        };
      });
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text(issue.label), findsOneWidget);
      expect(find.textContaining(issue.detail), findsOneWidget);
      expect(find.textContaining('不需要重新上传'), findsOneWidget);
      expect(find.textContaining('需要人工检查处理'), findsOneWidget);
      expect(find.text('处理结果尚未确认'), findsNothing);
      expect(find.text('提交分析'), findsNothing);
      expect(find.text('重试分析'), findsNothing);
      expect(find.text('拍一页'), findsNothing);
      expect(find.byType(LinearProgressIndicator), findsNothing);
      await tester.pump(const Duration(seconds: 8));
      expect(methods, ['GET']);
      await tester.ensureVisible(find.text('刷新状态'));
      await tester.tap(find.text('刷新状态'));
      await tester.pumpAndSettle();
      expect(methods, ['GET', 'GET']);
      await tester.pump(const Duration(seconds: 8));
      expect(methods, ['GET', 'GET']);
      expect(tester.takeException(), isNull);
    });
  }
  testWidgets(
    'paused analysis explains availability and leaves upload usable without polling',
    (tester) async {
      final methods = <String>[];
      final dio = server((r) {
        methods.add(r.method);
        return {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'revision': 1,
            'status': 'received',
            'analysisAvailable': false,
            'availabilityReason': '照片已保存，AI分析尚未启用',
            'processing': false,
            'retryAllowed': false,
            'pages': [],
            'items': [],
          },
        };
      });
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      await tester.pumpAndSettle();
      expect(find.text('AI 分析尚未启用'), findsOneWidget);
      expect(find.text('拍一页'), findsOneWidget);
      expect(find.text('从相册选多页'), findsOneWidget);
      expect(find.text('提交分析'), findsNothing);
      await tester.pump(const Duration(seconds: 8));
      expect(methods, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'active homework polls once then pauses in background and resumes with fresh read',
    (tester) async {
      var reads = 0;
      final dio = server((r) {
        reads++;
        return {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'revision': 2,
            'status': 'recognizing',
            'pages': [],
            'items': [],
          },
        };
      });
      await pump(tester, const HomeworkDetailPage(submissionId: 'hw_1'), dio);
      expect(reads, 1);
      await tester.pump(const Duration(seconds: 4));
      await tester.pump();
      expect(reads, 2);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump(const Duration(seconds: 12));
      expect(reads, 2);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));
      expect(reads, 3);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets('skipping review is explicit and preserves optimistic revision', (
    tester,
  ) async {
    final writes = <dynamic>[];
    final dio = server((r) {
      if (r.method == 'POST') writes.add(r.data);
      return {
        'review': {
          'id': 'review_1',
          'title': '周末小复习',
          'status': 'scheduled',
          'appointmentRevision': 9,
          'totalQuestions': 6,
          'estimatedMinutes': 6,
        },
        'report': {'notParticipated': true},
      };
    });
    await pump(
      tester,
      const ReviewDetailPage(childId: 'child_1', reviewId: 'review_1'),
      dio,
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('本周跳过'));
    await tester.pumpAndSettle();
    expect(writes, isEmpty);
    expect(find.text('会记录为本周未参加，不会记作答错，也不影响已有学习成果。'), findsOneWidget);
    await tester.tap(find.text('跳过本周'));
    await tester.pumpAndSettle();
    expect(writes.single['appointmentRevision'], 9);
    expect(writes.single['action'], 'skip');
    expect(writes.single['requestId'], isNotEmpty);
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'preferences keep a failed revision without silent automatic retry',
    (tester) async {
      var puts = 0;
      final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (r, h) {
            if (r.method == 'PUT') {
              puts++;
              h.reject(
                DioException(
                  requestOptions: r,
                  response: Response(
                    requestOptions: r,
                    statusCode: 409,
                    data: {'message': '家人已更新，请重新读取。'},
                  ),
                ),
              );
            } else {
              h.resolve(
                Response(
                  requestOptions: r,
                  data: {
                    'preferences': {
                      'weekday': 6,
                      'time': '10:00',
                      'timezone': 'Asia/Shanghai',
                      'enabled': true,
                      'reminderEnabled': true,
                      'dailyReminderLimit': 2,
                      'allowedStart': '09:00',
                      'allowedEnd': '20:00',
                      'pausedUntil': null,
                      'revision': 4,
                    },
                  },
                ),
              );
            }
          },
        ),
      );
      await pump(tester, const ReviewPreferencesPage(childId: 'child_1'), dio);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('保存安排'));
      await tester.tap(find.text('保存安排'));
      await tester.pumpAndSettle();
      expect(puts, 1);
      expect(find.text('家人已更新，请重新读取。'), findsOneWidget);
      expect(find.text('重新读取最新安排'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
