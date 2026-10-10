import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_pages.dart';
import 'package:warm_sight/src/features/profile/presentation/widgets/report_learning_section.dart';
import 'package:warm_sight/src/features/profile/presentation/widgets/report_growth_section.dart';
import 'support/parent_textbook_visual_capture.dart';

ReportData reportFixture({bool weekly = false, bool support = true}) =>
    ReportData.fromJson({
      'title': weekly ? '周报' : '今日报告',
      'periodLabel': weekly ? '2026-09-23 至 2026-09-29' : '2026-09-29',
      'headline': '今天有 1 节课程的学习记录。',
      'body': '课程表现来自实际作答、提示使用和独立复核。',
      'skillMaps': [
        {
          'childId': 'child',
          'childName': '孩子',
          'scope': '只计算已有证据。',
          'skills': [
            {
              'key': 'independence',
              'label': '独立作答',
              'score': 67,
              'maxScore': 100,
            },
          ],
        },
      ],
      'learning': {
        'lessonCount': 1,
        'needsSupportCount': support ? 1 : 0,
        'reviewCount': weekly ? 1 : 0,
        'lessons': [
          {
            'kind': 'textbook',
            'courseTitle': '天地人',
            'childName': '孩子',
            'statusLabel': support ? '需要家长留意' : '本轮独立通过',
            'needsSupport': support,
            'evidenceLabel': '图片支持下的情境理解',
            'recordDate': '2026-09-29',
            'baseline': {'correct': 4, 'total': 6, 'hints': 1, 'adultHelp': 1},
            'verification': {'correct': support ? 5 : 6, 'total': 6},
            'remainingSkills': support ? ['你'] : [],
            'diagnoses': support ? ['你：说话、听话和谈到的人还需区分'] : [],
            'nextStep': support
                ? '请在孩子休息后陪同确认题意，再进入课堂完成短练习。'
                : '已安排下次短复习，暂时不需要家长辅导。',
            'reviewDueAt': support
                ? null
                : DateTime.utc(2026, 9, 30, 4).millisecondsSinceEpoch,
          },
        ],
      },
    });

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  test('old reports remain compatible and new evidence retains its scope', () {
    expect(ReportData.fromJson({}).learning.lessons, isEmpty);
    final lesson = reportFixture(support: false).learning.lessons.single;
    expect(lesson.baselineLabel, '前测独立答对 4/6');
    expect(lesson.helpLabel, '前测提示 1 题 · 家长帮助 1 题');
    expect(lesson.reviewDueAt!.hour, 12);
  });

  testWidgets('daily and weekly report pages show learning and can refresh', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var dailyReads = 0, weeklyReads = 0;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          dailyReportProvider.overrideWith((ref) async {
            dailyReads++;
            return reportFixture();
          }),
          weeklyReportProvider.overrideWith((ref) async {
            weeklyReads++;
            return reportFixture(weekly: true, support: false);
          }),
        ],
        child: RepaintBoundary(
          key: parentTextbookPreviewKey,
          child: MaterialApp(
            theme: AppTheme.light,
            home: const ReportsHubPage(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(ReportLearningSection), findsOneWidget);
    expect(find.byType(ReportGrowthSection), findsOneWidget);
    expect(find.text('新情境独立通过 5/6'), findsOneWidget);
    expect(find.textContaining('看图理解不等于独立识字'), findsOneWidget);
    final before = dailyReads;
    await tester.tap(find.text('刷新报告'));
    await tester.pumpAndSettle();
    expect(dailyReads, greaterThan(before));
    await tester.ensureVisible(find.text('课程学习 · 1 节'));
    await tester.pumpAndSettle();
    await captureParentTextbookPreview(tester, 'daily-learning-report');
    expect(tester.takeException(), isNull);
    // Return above the fixed header before tapping the report tab.
    final scroll = tester.state<ScrollableState>(find.byType(Scrollable).first);
    scroll.position.jumpTo(0);
    await tester.pumpAndSettle();
    await tester.tap(find.text('周报'));
    await tester.pumpAndSettle();
    expect(weeklyReads, greaterThan(0));
    expect(find.byType(ReportGrowthSection), findsOneWidget);
    expect(find.text('本期完成 1 次间隔复习'), findsOneWidget);
    expect(find.text('新情境独立通过 6/6'), findsOneWidget);
    await tester.ensureVisible(find.text('课程学习 · 1 节'));
    await captureParentTextbookPreview(tester, 'weekly-learning-report');
    expect(tester.takeException(), isNull);
  });

  testWidgets('large text on a narrow screen keeps the evidence readable', (
    tester,
  ) async {
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
            child: ReportLearningSection(learning: reportFixture().learning),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('待巩固或继续验证：你'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
