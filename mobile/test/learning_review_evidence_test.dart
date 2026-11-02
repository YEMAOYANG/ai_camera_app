import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/learning_review/application/learning_review_repository.dart';
import 'package:warm_sight/src/features/learning_review/domain/learning_review_models.dart';
import 'package:warm_sight/src/features/learning_review/presentation/review_detail_page.dart';
import 'package:warm_sight/src/features/learning_review/presentation/learning_support_widgets.dart';

Json evidenceFixture() => {
  'answeredCount': 4,
  'totalQuestions': 4,
  'independentFirstCount': 1,
  'independentFirstCorrect': 1,
  'repeatedPracticeCount': 1,
  'assessmentScope': '只记录实际作答；图片点选不能推断发音或纸笔书写。',
  'parentAction': '先看需要帮助的具体一步。',
  'items': [
    {
      'knowledgeLabel': '时间词理解',
      'correct': true,
      'independent': true,
      'courseTitle': '语文园地四',
      'prompt': '点早晨的图片。',
    },
    {
      'knowledgeLabel': '偏旁与字义',
      'correct': false,
      'independent': false,
      'hintUsed': true,
      'adultHelpKnown': false,
      'systemUnaided': false,
      'independenceStatus': 'assisted_or_repeated',
    },
    {
      'knowledgeLabel': '拼音与词义',
      'correct': true,
      'independent': true,
      'assessmentMode': 'pinyin_picture',
      'target': 'xiě zì',
      'adultHelpKnown': false,
      'systemUnaided': true,
      'independenceStatus': 'adult_help_unknown',
      'sourceIdentity': {
        'title': '语文园地四',
        'contentKey': 'source-content',
        'releaseSha256': 'actual-frozen-release',
      },
      'evidenceClaim': {
        'observed': ['选择写字的图片'],
        'supports': ['拼音与词义对应'],
        'doesNotSupport': ['独立发音或规范书写'],
      },
      'prompt': '看看拼音，点一幅图。',
      'answerLabel': '第一幅',
      'correctAnswerLabel': '第一幅',
      'explanation': '图中的孩子手握笔，笔尖接着纸。',
    },
    {
      'knowledgeLabel': '复练图义',
      'correct': true,
      'independent': true,
      'evidenceMode': 'repeated_practice',
    },
  ],
};

void main() {
  test(
    'assistance, repetition and unknown adult help override legacy independent flags',
    () {
      final items = jsonList(
        evidenceFixture()['items'],
      ).map(ReviewEvidenceItem.new).toList();
      expect(items[0].supportLabel, '首次独立作答');
      expect(items[1].supportLabel, '已使用提示 · 家长帮助未知');
      expect(items[2].supportLabel, '未用系统提示，家长帮助未知');
      expect(items[2].assessmentLabel, '拼音配图');
      expect(items[2].sourceIdentity['releaseSha256'], 'actual-frozen-release');
      expect(items[3].supportLabel, '原题复练');
      expect(const ReviewEvidenceItem({}).resultLabel, '结果待核实');
      expect(const ReviewEvidenceItem({}).supportLabel, '独立性未确认');
    },
  );

  testWidgets(
    'detail shows actual target, supported evidence and unmeasured boundaries at 390px',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      const keyValue = (childId: 'child-one', reviewId: 'review-one');
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            reviewDetailProvider(keyValue).overrideWith(
              (ref) async => ReviewDetail({
                'review': {
                  'id': 'review-one',
                  'title': '本周课后测评',
                  'status': 'completed',
                  'totalQuestions': 4,
                  'estimatedMinutes': 6,
                },
                'report': evidenceFixture(),
              }),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: const ReviewDetailPage(
              childId: 'child-one',
              reviewId: 'review-one',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('已答 4 / 4 题'), findsOneWidget);
      expect(find.text('首次独立答对 1 / 1 题'), findsOneWidget);
      expect(find.textContaining('口语、发音、背诵和纸笔书写未直接测评'), findsOneWidget);
      expect(find.textContaining('未用系统提示，家长帮助未知'), findsOneWidget);
      expect(find.textContaining('目标字音：xiě zì'), findsOneWidget);
      await tester.ensureVisible(find.text('拼音与词义'));
      await tester.tap(find.text('拼音与词义'));
      await tester.pumpAndSettle();
      expect(find.text('对应课件：语文园地四'), findsWidgets);
      expect(find.text('本题可记录：拼音与词义对应'), findsOneWidget);
      expect(find.text('尚不能据此判断：独立发音或规范书写'), findsOneWidget);
      expect(find.text('非独立新题证据'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'narrow large text keeps unknown ability and legacy reports readable',
    (tester) async {
      tester.view.physicalSize = const Size(320, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: const TextScaler.linear(1.5)),
            child: child!,
          ),
          home: Scaffold(
            body: SingleChildScrollView(
              child: ReviewReportEvidence(
                report: {
                  ...evidenceFixture(),
                  'independentFirstCount': 0,
                  'independentFirstCorrect': 0,
                },
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('暂无可确认的首次独立作答证据。'), findsOneWidget);
      expect(find.textContaining('首次独立答对 0 / 0'), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ReviewReportEvidence(
              report: {
                'notParticipated': true,
                'assessmentScope': '没有参加不代表不会。',
              },
            ),
          ),
        ),
      );
      expect(find.text('孩子尚未参加。没有作答记录不代表不会。'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
