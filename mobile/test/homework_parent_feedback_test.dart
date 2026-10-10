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
import 'package:warm_sight/src/features/homework/domain/homework_models.dart';
import 'package:warm_sight/src/features/homework/presentation/homework_detail_page.dart';

Map<String, dynamic> parentItem({bool referenceAvailable = true}) => {
  'id': 'item_1',
  'pageId': 'page_1',
  'revision': 1,
  'prompt': '观察第2棵树',
  'studentAnswer': '1',
  'status': referenceAvailable ? 'incorrect' : 'pending',
  'tutorEnabled': true,
  'correctionStatus': 'corrected',
  'gradingReference': {
    'provider': 'tencent',
    'status': referenceAvailable ? 'incorrect' : 'unknown',
    'answerState': 'written',
    'geometryVerified': true,
    'answerRegion': {'x': .1, 'y': .1, 'width': .3, 'height': .2},
    'referenceGate': {
      'available': referenceAvailable,
      'status': referenceAvailable ? 'provider_consistent' : 'needs_review',
      'method': 'tencent_source_reference.v1',
    },
    'studentQuality': {'status': 'needs_review', 'countsForAbility': false},
    'referenceAnswer': '3',
    'analysis': '树上有3个果子，当前位置应填写3。',
    'knowledgePoints': ['看图数数'],
  },
  'studentCorrection': {
    'lastAnswer': '3',
    'attempts': 2,
    'correct': true,
    'updatedAt': 1790730000000,
    'hintViewed': true,
    'explanationViewed': true,
    'tutorViewed': true,
    'independent': null,
    'scope': 'same_question_correction',
  },
  'latestTutorTeacherText': '我们一起逐个数果子，一、二、三。',
  'latestTutorTeachingQuality': {
    'status': 'guidance',
    'countsForAbility': false,
  },
};

Map<String, dynamic> parentSubmission(List<Map<String, dynamic>> items) => {
  'id': 'hw_1',
  'childId': 'child_1',
  'title': '数学作业',
  'revision': 1,
  'status': 'ready',
  'processing': false,
  'analysisAvailable': true,
  'retryAllowed': false,
  'tutorAvailable': true,
  'pages': [
    {'id': 'page_1', 'width': 400, 'height': 200, 'rotation': 0},
  ],
  'items': items,
  'originalPaperSummary': {
    'total': items.length,
    'correct': 0,
    'incorrect': 1,
    'unknown': 0,
  },
};

void main() {
  Future<void> open(
    WidgetTester tester,
    Map<String, dynamic> submission,
    List<String> requests,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final png = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC',
    );
    final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (request, handler) {
          if (request.responseType == ResponseType.bytes) {
            handler.resolve(Response(requestOptions: request, data: png));
          } else {
            requests.add(request.method);
            handler.resolve(
              Response(
                requestOptions: request,
                data: {'submission': submission},
              ),
            );
          }
        },
      ),
    );
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          homeworkRepositoryProvider.overrideWithValue(
            HomeworkRepository(ApiClient(dio)),
          ),
          homeworkPhotoPickerProvider.overrideWithValue(
            HomeworkPhotoPicker(ImagePicker(), prefs, () => 'parent-test'),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const HomeworkDetailPage(submissionId: 'hw_1'),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> expand(WidgetTester tester) async {
    await tester.ensureVisible(find.text('1. 观察第2棵树'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('1. 观察第2棵树'));
    await tester.pumpAndSettle();
  }

  test(
    'source-consistent reference is available without claiming human verification',
    () {
      final question = HomeworkItem(parentItem());
      expect(question.referenceAvailable, isTrue);
      expect(question.referenceVerified, isFalse);
      expect(question.paperStatus, 'incorrect');
      expect(question.statusLabel, '腾讯批改建议订正');
      expect(question.correction.lastAnswer, '3');
      expect(question.correction.attempts, 2);
      expect(question.correction.explanationViewed, isTrue);
      expect(
        HomeworkSubmission({
          ...parentSubmission([parentItem()]),
          'provisionalPaperSummary': {
            'correct': 0,
            'incorrect': 1,
            'countsForAbility': false,
          },
        }).provisionalPaperSummary,
        isEmpty,
      );
      final blocked = HomeworkItem(parentItem(referenceAvailable: false));
      expect(blocked.referenceAvailable, isFalse);
      expect(blocked.paperStatus, 'pending');
      expect(blocked.latestTutorGuidance, isNotEmpty);
      for (final quality in [
        null,
        {'status': 'needs_review', 'countsForAbility': false},
        {'status': 'guidance', 'countsForAbility': true},
      ]) {
        expect(
          HomeworkItem({
            ...parentItem(),
            'latestTutorTeachingQuality': quality,
          }).latestTutorGuidance,
          isEmpty,
        );
      }
    },
  );

  testWidgets(
    'parent sees source analysis and correction history without editing answers',
    (tester) async {
      final requests = <String>[];
      await open(tester, parentSubmission([parentItem()]), requests);
      await expand(tester);
      expect(find.text('孩子原作答：1'), findsOneWidget);
      expect(find.text('腾讯参考答案：3'), findsOneWidget);
      expect(find.text('树上有3个果子，当前位置应填写3。'), findsOneWidget);
      expect(find.text('最近回答：3 · 本次答对'), findsOneWidget);
      expect(find.text('已作答 2 次'), findsOneWidget);
      expect(find.text('已看提示 · 已展开解析 · 已查看老师指导'), findsOneWidget);
      expect(find.textContaining('老师最近指导：我们一起逐个数果子'), findsOneWidget);
      expect(find.textContaining('不代表已独立掌握'), findsOneWidget);
      expect(find.text('在孩子的学生端打开“作业与试卷”，选择“数学作业”。'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      expect(find.text('重试分析'), findsNothing);
      expect(find.text('提交分析'), findsNothing);
      expect(requests, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'safe guidance remains visible when the formal paper reference is withheld',
    (tester) async {
      final requests = <String>[];
      await open(
        tester,
        parentSubmission([parentItem(referenceAvailable: false)]),
        requests,
      );
      await expand(tester);
      expect(find.text('腾讯参考答案：3'), findsNothing);
      expect(find.text('树上有3个果子，当前位置应填写3。'), findsNothing);
      expect(find.textContaining('老师最近指导：我们一起逐个数果子'), findsOneWidget);
      expect(find.text('讲解与原卷批改分开记录，听过讲解不代表独立订正或掌握。'), findsOneWidget);
      expect(requests, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );

  test(
    'paper completion remains separate from tested answers and expires on a new answer',
    () {
      final data = {
        ...parentItem(),
        'correctionStatus': 'self_reported',
        'readyForStudent': true,
        'studentCorrection': {
          'status': 'self_reported',
          'selfReportedCompleted': true,
          'selfReportedCompletedAt': 1790730000000,
          'lastAnswer': '',
          'attempts': 0,
          'correct': null,
        },
      };
      final model = HomeworkSubmission(parentSubmission([data]));
      expect(model.studentSelfReportedCompletedCount, 1);
      expect(model.studentCorrectedCount, 0);
      expect(model.studentReadyCount, 0);
      final correction = model.items.single.correction;
      expect(correction.hasActivity, isTrue);
      expect(correction.attempts, 0);
      expect(correction.correct, isNull);
      expect(correction.selfReportedCompletedAt, 1790730000000);
      for (final status in ['in_progress', 'corrected']) {
        final updated = HomeworkItem({
          ...data,
          'studentCorrection': {
            ...correction.data,
            'status': status,
            'correct': status == 'corrected',
          },
        });
        expect(updated.correction.selfReportedCompleted, isFalse);
      }
      expect(
        HomeworkItem({
          ...data,
          'studentCorrection': {...correction.data, 'correct': true},
        }).correction.selfReportedCompleted,
        isFalse,
      );
    },
  );

  testWidgets(
    'paper completion is shown as untested without inventing an answer or attempt',
    (tester) async {
      final requests = <String>[];
      final data = {
        ...parentItem(),
        'correctionStatus': 'self_reported',
        'studentCorrection': {
          'status': 'self_reported',
          'selfReportedCompleted': true,
          'selfReportedCompletedAt': 1790730000000,
          'lastAnswer': '',
          'attempts': 0,
          'correct': null,
        },
      };
      await open(tester, parentSubmission([data]), requests);
      expect(find.text('孩子已订正 0 / 1 题'), findsOneWidget);
      expect(find.text('另有 1 题自行完成，未复测'), findsOneWidget);
      await expand(tester);
      expect(find.textContaining('未记为答对'), findsOneWidget);
      expect(find.text('最近回答：3 · 本次答对'), findsNothing);
      expect(find.text('已作答 1 次'), findsNothing);
      expect(find.textContaining('孩子已订正'), findsOneWidget);
      expect(requests, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'uncertain paid receipt only offers one read action despite stale retry flags',
    (tester) async {
      final requests = <String>[];
      final data = {
        ...parentSubmission([]),
        'status': 'failed',
        'errorCode': 'homework_audio_unknown',
        'analysisAvailable': false,
        'retryAllowed': true,
        'processing': true,
      };
      final model = HomeworkSubmission(data);
      expect(model.retryAllowed, isFalse);
      expect(model.canAnalyze, isFalse);
      expect(model.active, isFalse);
      expect(model.canEditPages, isFalse);
      expect(
        HomeworkSubmission({...data, 'status': 'received'}).canUpload,
        isFalse,
      );
      await open(tester, data, requests);
      expect(find.text('刷新状态'), findsOneWidget);
      expect(find.text('刷新分析状态'), findsNothing);
      expect(find.text('重试分析'), findsNothing);
      expect(find.textContaining('可以继续整理照片'), findsNothing);
      expect(
        tester
            .widget<TextButton>(find.widgetWithText(TextButton, '旋转 / 裁剪'))
            .onPressed,
        isNull,
      );
      expect(
        tester
            .widget<IconButton>(
              find.byWidgetPredicate(
                (widget) => widget is IconButton && widget.tooltip == '删除这一页',
              ),
            )
            .onPressed,
        isNull,
      );
      await tester.ensureVisible(find.text('刷新状态'));
      await tester.tap(find.text('刷新状态'));
      await tester.pumpAndSettle();
      expect(requests, ['GET', 'GET']);
      expect(tester.takeException(), isNull);
    },
  );
}
