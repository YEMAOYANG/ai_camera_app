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

Map<String, dynamic> item(
  String status, {
  Object? verdict,
  bool verified = false,
}) => {
  'id': 'item_1',
  'pageId': 'page_1',
  'revision': 1,
  'prompt': '原题作答位置',
  'status': 'pending',
  'studentAnswer': '4',
  'tutorEnabled': true,
  'gradingReference': {
    'provider': 'tencent',
    'status': verified ? status : 'unknown',
    'answerState': 'written',
    'studentQuality': {
      'status': verified ? 'verified' : 'needs_review',
      'countsForAbility': false,
    },
    'geometryVerified': true,
    'answerRegion': {'x': 0.1, 'y': 0.1, 'width': 0.2, 'height': 0.2},
    'providerVerdict': ?verdict,
  },
};

Map<String, Object?> verdict(String status) => {
  'status': status,
  'source': 'tencent',
  'provisional': true,
  'countsForAbility': false,
};

void main() {
  test(
    'provisional verdict is only a display signal, never a correction grade',
    () {
      for (final status in ['correct', 'incorrect']) {
        final data = item(status, verdict: verdict(status));
        final question = HomeworkItem(data);
        expect(question.status, 'pending');
        expect(question.paperStatus, 'pending');
        expect(question.displayPaperStatus, status);
        expect(question.hasProvisionalVerdict, isTrue);
        expect(question.referenceVerified, isFalse);
        final submission = HomeworkSubmission({
          'items': [data],
          'originalPaperSummary': {'incorrect': 1, 'total': 1},
        });
        expect(submission.studentCorrectionCount, 0);
        expect(submission.studentReadyCount, 0);
        expect(submission.originalPaperSummary['incorrect'], 0);
        expect(submission.originalPaperSummary['unknown'], 1);
      }
    },
  );

  test('verified reference wins over a contradictory initial verdict', () {
    final question = HomeworkItem(
      item('correct', verified: true, verdict: verdict('incorrect')),
    );
    expect(question.paperStatus, 'correct');
    expect(question.displayPaperStatus, 'correct');
    expect(question.hasProvisionalVerdict, isFalse);
    expect(question.referenceVerified, isTrue);
  });

  test('old or malformed verdicts stay unjudged and cannot reveal answers', () {
    final invalid = <Object?>[
      null,
      {'status': 'incorrect'},
      {...verdict('incorrect'), 'source': 'other'},
      {...verdict('incorrect'), 'provisional': false},
      {...verdict('incorrect'), 'countsForAbility': true},
      {...verdict('incorrect'), 'countsForAbility': null},
      verdict('unknown'),
      'incorrect',
    ];
    for (final value in invalid) {
      final question = HomeworkItem(item('incorrect', verdict: value));
      expect(question.hasProvisionalVerdict, isFalse);
      expect(question.displayPaperStatus, 'pending');
      expect(question.referenceVerified, isFalse);
      expect(question.statusLabel, '待老师看原图');
    }
    final old = HomeworkItem({
      ...item('incorrect'),
      'status': 'incorrect',
      'gradingReference': {
        'provider': 'tencent',
        'status': 'incorrect',
        'referenceAnswer': '2',
      },
    });
    expect(old.paperStatus, 'pending');
    expect(old.referenceVerified, isFalse);
    expect(old.hasProvisionalVerdict, isFalse);
  });

  test('a blank answer has no provisional right or wrong marker', () {
    final data = item('incorrect', verdict: verdict('incorrect'));
    (data['gradingReference'] as Map<String, dynamic>)['answerState'] = 'blank';
    final question = HomeworkItem(data);
    expect(question.paperStatus, 'blank');
    expect(question.hasProvisionalVerdict, isFalse);
    expect(question.statusLabel, '空白未作答');
  });

  test('provisional statistics must explicitly exclude ability scoring', () {
    expect(
      HomeworkSubmission({
        'provisionalPaperSummary': {'incorrect': 8},
      }).provisionalPaperSummary,
      isEmpty,
    );
    expect(
      HomeworkSubmission({
        'provisionalPaperSummary': {'incorrect': 8, 'countsForAbility': true},
      }).provisionalPaperSummary,
      isEmpty,
    );
    expect(
      HomeworkSubmission({
        'provisionalPaperSummary': {'incorrect': 8, 'countsForAbility': false},
      }).provisionalPaperSummary['incorrect'],
      8,
    );
  });

  testWidgets(
    'parent paper distinguishes initial markers and hides withheld answer and analysis',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final questions = [
        item('correct', verdict: verdict('correct')),
        item('incorrect', verdict: verdict('incorrect')),
        item('unknown'),
        item('correct', verified: true, verdict: verdict('incorrect')),
      ];
      for (var i = 0; i < questions.length; i++) {
        questions[i]['id'] = 'item_$i';
        questions[i]['prompt'] = '原题 ${i + 1}';
        final grading =
            questions[i]['gradingReference'] as Map<String, dynamic>;
        grading['answerRegion'] = {
          'x': 0.05 + i * 0.22,
          'y': 0.1,
          'width': 0.2,
          'height': 0.2,
        };
        if (i == 1) {
          grading['referenceAnswer'] = '不应显示的参考答案';
          grading['analysis'] = '不应显示的解析';
          questions[i]['expectedAnswer'] = '不应回退的答案';
          questions[i]['explanation'] = '不应回退的讲解';
          questions[i]['latestTutorTeacherText'] = '不应显示的旧指导';
        }
        if (i == 3) {
          grading['referenceAnswer'] = '4';
          grading['analysis'] = '已核验的解析';
        }
      }
      final png = base64Decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC',
      );
      final methods = <String>[];
      final dio = Dio(BaseOptions(baseUrl: 'https://unit-test.invalid/api'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (request, handler) {
            if (request.responseType == ResponseType.bytes) {
              handler.resolve(Response(requestOptions: request, data: png));
              return;
            }
            methods.add(request.method);
            handler.resolve(
              Response(
                requestOptions: request,
                data: {
                  'submission': {
                    'id': 'hw_1',
                    'childId': 'child_1',
                    'title': '原卷批改',
                    'revision': 3,
                    'status': 'needs_confirmation',
                    'processing': false,
                    'tutorAvailable': true,
                    'pages': [
                      {
                        'id': 'page_1',
                        'width': 400,
                        'height': 200,
                        'rotation': 0,
                      },
                    ],
                    'items': questions,
                    'originalPaperSummary': {
                      'total': 4,
                      'correct': 1,
                      'incorrect': 0,
                      'unknown': 3,
                      'blank': 0,
                    },
                    'provisionalPaperSummary': {
                      'total': 3,
                      'correct': 1,
                      'incorrect': 1,
                      'unknown': 1,
                      'blank': 0,
                      'countsForAbility': false,
                    },
                  },
                },
              ),
            );
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
      expect(find.text('1 ✓ 初判'), findsOneWidget);
      expect(find.text('2 ? 再看'), findsOneWidget);
      expect(find.text('3 ?'), findsOneWidget);
      expect(find.text('4 ✓'), findsOneWidget);
      expect(find.text('腾讯初判正确'), findsOneWidget);
      expect(find.text('腾讯初判建议再看'), findsOneWidget);
      expect(find.textContaining('腾讯初判：正确 1 · 建议再看 1 · 待核验 1'), findsOneWidget);
      expect(find.textContaining('批改正确 1 · 建议订正 0'), findsOneWidget);
      await tester.ensureVisible(find.text('2. 原题 2'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('2. 原题 2'));
      await tester.pumpAndSettle();
      expect(find.textContaining('这是腾讯初判，尚未核验'), findsOneWidget);
      for (final hidden in [
        '不应显示的参考答案',
        '不应显示的解析',
        '不应回退的答案',
        '不应回退的讲解',
        '不应显示的旧指导',
      ]) {
        expect(find.textContaining(hidden), findsNothing);
      }
      expect(find.byType(TextField), findsNothing);
      expect(methods, ['GET']);
      expect(tester.takeException(), isNull);
    },
  );
}
