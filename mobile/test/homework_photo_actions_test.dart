import 'dart:convert';
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
import 'package:warm_sight/src/features/homework/presentation/homework_detail_page.dart';
import 'support/parent_textbook_visual_capture.dart';

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  const page = {'id': 'page_1', 'width': 400, 'height': 200, 'rotation': 0};
  final png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC',
  );
  Map<String, dynamic> detail({
    bool available = false,
    int revision = 1,
    List<Object?> pages = const [page],
  }) => {
    'submission': {
      'id': 'hw_1',
      'childId': 'child_1',
      'title': '数学作业',
      'status': 'received',
      'revision': revision,
      'analysisAvailable': available,
      'processing': false,
      'retryAllowed': false,
      'availabilityReason': '照片已保存，AI分析尚未启用',
      'pages': pages,
      'items': [],
    },
  };
  Future<SharedPreferences> pump(
    WidgetTester tester,
    Dio dio, {
    Map<String, Object> pending = const {},
  }) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues(pending);
    final preferences = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeworkRepositoryProvider.overrideWithValue(
            HomeworkRepository(ApiClient(dio)),
          ),
          homeworkPhotoPickerProvider.overrideWithValue(
            HomeworkPhotoPicker(ImagePicker(), preferences, () => 'parent_a'),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const RepaintBoundary(
            key: parentTextbookPreviewKey,
            child: HomeworkDetailPage(submissionId: 'hw_1'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return preferences;
  }

  Dio server(Object Function(RequestOptions) handler) {
    final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (r, h) {
          if (r.responseType == ResponseType.bytes) {
            h.resolve(Response(requestOptions: r, data: png));
          } else {
            h.resolve(Response(requestOptions: r, data: handler(r)));
          }
        },
      ),
    );
    return dio;
  }

  testWidgets(
    'deleting the last photo immediately shows an empty draft and clears pending recovery',
    (tester) async {
      final writes = <RequestOptions>[];
      var reads = 0;
      final dio = server((r) {
        if (r.method == 'PATCH') {
          writes.add(r);
          return detail(revision: 2, pages: []);
        }
        reads++;
        return detail();
      });
      final preferences = await pump(
        tester,
        dio,
        pending: {
          'homework.pending.parent_a': jsonEncode({
            'hw_1': [
              {'path': 'synthetic-photo', 'key': 'pending-1'},
            ],
          }),
          'homework.capture.parent_a': jsonEncode({
            'submissionId': 'hw_1',
            'childId': 'child_1',
          }),
        },
      );
      await tester.ensureVisible(find.byTooltip('删除这一页'));
      await tester.tap(find.byTooltip('删除这一页'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('删除页面'));
      await tester.pumpAndSettle();
      expect(writes.single.data, {'revision': 1, 'pages': []});
      expect(
        reads,
        1,
      ); // Mutation response is enough; no delayed GET is needed.
      expect(find.byTooltip('删除这一页'), findsNothing);
      expect(find.textContaining('还没有照片'), findsOneWidget);
      expect(find.text('继续上传'), findsNothing);
      expect(preferences.getString('homework.capture.parent_a'), isNull);
      expect(
        jsonDecode(preferences.getString('homework.pending.parent_a')!),
        isEmpty,
      );
      expect(tester.takeException(), isNull);
      await captureParentTextbookPreview(tester, 'homework-deleted-photo');
    },
  );
  testWidgets(
    'deleting one page preserves the remaining page and never deletes the submission',
    (tester) async {
      final second = {...page, 'id': 'page_2'};
      final writes = <RequestOptions>[];
      final dio = server((r) {
        if (r.method == 'PATCH') {
          writes.add(r);
          return detail(revision: 2, pages: [second]);
        }
        return detail(pages: [page, second]);
      });
      await pump(tester, dio);
      await tester.tap(find.byTooltip('删除这一页'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('删除页面'));
      await tester.pumpAndSettle();
      expect((writes.single.data['pages'] as List).single['id'], 'page_2');
      expect(find.text('第 1 / 1 页'), findsOneWidget);
      expect(find.textContaining('还没有照片'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'paused analysis has an explicit read-only refresh action and becomes submittable after enablement',
    (tester) async {
      final requests = <RequestOptions>[];
      var available = false;
      final dio = server((r) {
        requests.add(r);
        return detail(available: available);
      });
      await pump(tester, dio);
      expect(find.text('照片已保存 · AI 分析尚未启用'), findsOneWidget);
      expect(find.text('提交分析'), findsNothing);
      await captureParentTextbookPreview(tester, 'homework-analysis-paused');
      await tester.ensureVisible(find.text('刷新分析状态'));
      await tester.tap(find.text('刷新分析状态'));
      await tester.pumpAndSettle();
      expect(requests.map((r) => r.method), ['GET', 'GET']);
      expect(find.text('提交分析'), findsNothing);
      available = true;
      await tester.tap(find.text('刷新分析状态'));
      await tester.pumpAndSettle();
      expect(find.text('提交分析'), findsOneWidget);
      expect(find.text('刷新分析状态'), findsNothing);
      expect(requests.map((r) => r.method), ['GET', 'GET', 'GET']);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'parent report is read only and never asks parent to correct recognition or answer',
    (tester) async {
      final requests = <RequestOptions>[];
      final response = {
        'submission': {
          'id': 'hw_1',
          'childId': 'child_1',
          'title': '数学作业',
          'status': 'ready',
          'revision': 3,
          'processing': false,
          'pages': [page],
          'summary': {'total': 1, 'incorrect': 1},
          'items': [
            {
              'id': 'item_1',
              'pageId': 'page_1',
              'revision': 2,
              'prompt': '1 + 2 = ?',
              'studentAnswer': '6',
              'expectedAnswer': '3',
              'status': 'incorrect',
              'readyForStudent': true,
              'correctionStatus': 'pending',
            },
          ],
        },
      };
      final dio = server((r) {
        requests.add(r);
        return response;
      });
      await pump(tester, dio);
      expect(requests.map((r) => r.method), ['GET']);
      expect(find.text('孩子已订正 0 / 1 题'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      await tester.ensureVisible(find.text('1. 1 + 2 = ?'));
      await tester.tap(find.text('1. 1 + 2 = ?'));
      await tester.pumpAndSettle();
      expect(find.text('孩子原作答：6'), findsOneWidget);
      expect(find.text('正确答案：3'), findsOneWidget);
      expect(find.text('核对识别内容（可选）'), findsNothing);
      expect(find.text('保存识别内容'), findsNothing);
      expect(find.byType(TextField), findsNothing);
      expect(requests.map((r) => r.method), ['GET']);
      expect(find.text('孩子已订正 0 / 1 题'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'Tencent paper feedback is visible while verified ability remains uncertain',
    (tester) async {
      final methods = <String>[];
      final dio = server((request) {
        methods.add(request.method);
        return {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '语文作业',
            'revision': 3,
            'status': 'needs_confirmation',
            'processing': false,
            'tutorAvailable': true,
            'pages': [page],
            'summary': {'total': 1, 'pending': 1, 'correct': 0},
            'originalPaperSummary': {
              'total': 1,
              'incorrect': 1,
              'correct': 0,
              'unknown': 0,
            },
            'items': [
              {
                'id': 'item_1',
                'pageId': 'page_1',
                'revision': 1,
                'prompt': '选词填空',
                'studentAnswer': '己',
                'status': 'pending',
                'tutorEnabled': true,
                'sourceHierarchy': {'answerIndex': 2, 'answerCount': 3},
                'gradingReference': {
                  'provider': 'tencent',
                  'status': 'incorrect',
                  'studentQuality': {
                    'status': 'verified',
                    'countsForAbility': false,
                  },
                  'referenceAnswer': '已',
                  'analysis': '这里表示已经完成。',
                  'knowledgePoints': ['形近字辨析'],
                  'geometryVerified': false,
                  'countsForAbility': false,
                },
              },
            ],
          },
        };
      });
      await pump(tester, dio);
      expect(find.textContaining('批改正确 0 · 建议订正 1'), findsOneWidget);
      expect(find.text('腾讯批改建议订正'), findsOneWidget);
      await tester.ensureVisible(find.text('1. 选词填空'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('1. 选词填空'));
      await tester.pumpAndSettle();
      expect(find.text('孩子原作答：己'), findsOneWidget);
      expect(find.text('腾讯参考答案：已'), findsOneWidget);
      expect(find.text('知识点：形近字辨析'), findsOneWidget);
      expect(find.text('这里表示已经完成。'), findsOneWidget);
      expect(find.text('这道题的第 2 / 3 个作答位置'), findsOneWidget);
      await captureParentTextbookPreview(
        tester,
        'homework-report-student-correction',
      );
      expect(find.byType(TextField), findsNothing);
      expect(find.text('核对识别内容（可选）'), findsNothing);
      expect(methods, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'unready item distinguishes supported media from unsupported teacher correction',
    (tester) async {
      final dio = server(
        (r) => {
          'submission': {
            'id': 'hw_1',
            'childId': 'child_1',
            'title': '数学作业',
            'status': 'ready',
            'revision': 3,
            'processing': false,
            'pages': [page],
            'summary': {'total': 2, 'incorrect': 2},
            'items': [
              {
                'id': 'item_1',
                'pageId': 'page_1',
                'prompt': '1 + 2 = ?',
                'status': 'incorrect',
                'readyForStudent': false,
                'answerMode': 'picture_choice',
              },
              {
                'id': 'item_2',
                'pageId': 'page_1',
                'prompt': '99 + 99 = ?',
                'status': 'incorrect',
                'readyForStudent': false,
              },
            ],
          },
        },
      );
      await pump(tester, dio);
      await tester.ensureVisible(find.text('1. 1 + 2 = ?'));
      await tester.tap(find.text('1. 1 + 2 = ?'));
      await tester.pumpAndSettle();
      expect(find.text('这道题的图片和语音尚未准备好，准备好后孩子可在学生端订正。'), findsOneWidget);
      await tester.ensureVisible(find.text('2. 99 + 99 = ?'));
      await tester.tap(find.text('2. 99 + 99 = ?'));
      await tester.pumpAndSettle();
      expect(find.text('这道题暂不支持学生端自动讲解，已保留分析记录。'), findsOneWidget);
      expect(find.textContaining('正在准备图片或讲解'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
