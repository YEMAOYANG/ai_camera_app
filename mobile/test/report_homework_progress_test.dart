import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/domain/report_learning_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_pages.dart';
import 'package:warm_sight/src/features/profile/presentation/widgets/report_learning_section.dart';

Map<String, dynamic> progressFixture() => {
  'schemaVersion': 'mira.report.homework-progress.v1',
  'scope': 'current_same_question_correction',
  'periodSelection': 'uploaded_or_latest_answer_in_period',
  'submissionCount': 1,
  'total': 3,
  'corrected': 1,
  'inProgress': 1,
  'notStarted': 1,
  'needsReview': 1,
  'assisted': 2,
  'independent': null,
  'countsForAbility': false,
  'entries': [
    {
      'submissionId': 'owned-paper',
      'childId': 'owned-child',
      'childName': '孩子',
      'title': '数学作业',
      'total': 3,
      'corrected': 1,
      'needsReview': 1,
    },
  ],
};

ReportData reportFixture({bool weekly = false}) => ReportData.fromJson({
  'title': weekly ? '周报' : '今日报告',
  'periodLabel': weekly ? '2026-09-28 至 2026-10-04' : '2026-09-29',
  'learning': {'homeworkProgress': progressFixture()},
});

void main() {
  test(
    'additive homework report preserves old reports and rejects mastery claims',
    () {
      expect(ReportLearningSummary.fromJson({}).homeworkProgress, isNull);
      final learning = reportFixture().learning;
      expect(learning.lessonCount, 0);
      expect(learning.homeworkProgress!.corrected, 1);
      expect(learning.homeworkProgress!.selfReportedCompleted, 0);
      expect(
        learning.homeworkProgress!.entries.single.selfReportedCompleted,
        0,
      );
      expect(
        learning.homeworkProgress!.entries.single.submissionId,
        'owned-paper',
      );
      for (final invalid in [
        {...progressFixture(), 'countsForAbility': true},
        {...progressFixture(), 'independent': true},
        {...progressFixture(), 'scope': 'independent_mastery'},
        {...progressFixture(), 'schemaVersion': 'unknown'},
      ]) {
        expect(ReportHomeworkProgress.fromJson(invalid), isNull);
      }
    },
  );

  testWidgets(
    'daily and weekly show same-question progress separately from course evidence',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var reads = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            dailyReportProvider.overrideWith((ref) async {
              reads++;
              return reportFixture();
            }),
            weeklyReportProvider.overrideWith((ref) async {
              reads++;
              return reportFixture(weekly: true);
            }),
          ],
          child: MaterialApp(
            theme: AppTheme.light,
            home: const ReportsHubPage(),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('作业订正 · 1 份'), findsOneWidget);
      expect(find.text('需订正 3 题 · 已订正 1 题'), findsOneWidget);
      expect(find.text('正在订正 1 题 · 尚未开始 1 题'), findsOneWidget);
      expect(find.text('有 2 题已查看提示、解析或老师指导'), findsOneWidget);
      expect(find.text('另有 1 题批改待核实，未计为错题'), findsOneWidget);
      expect(find.textContaining('不能证明独立掌握'), findsOneWidget);
      expect(find.textContaining('不回填为本期完成成绩'), findsOneWidget);
      expect(find.text('孩子 · 数学作业'), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      await tester.tap(find.text('周报'));
      await tester.pumpAndSettle();
      expect(find.text('作业订正 · 1 份'), findsOneWidget);
      final before = reads;
      await tester.tap(find.text('刷新报告'));
      await tester.pumpAndSettle();
      expect(reads, greaterThan(before));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('owned detail entry navigates at narrow width with large text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final router = GoRouter(
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => Scaffold(
            body: SingleChildScrollView(
              child: ReportLearningSection(learning: reportFixture().learning),
            ),
          ),
        ),
        GoRoute(
          path: '$homeworkDetailPath/:submissionId',
          builder: (_, state) => Scaffold(
            body: Text('打开作业：${state.pathParameters['submissionId']}'),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      MaterialApp.router(
        theme: AppTheme.light,
        routerConfig: router,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: const TextScaler.linear(1.5)),
          child: child!,
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('孩子 · 数学作业'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('孩子 · 数学作业'));
    await tester.pumpAndSettle();
    expect(find.text('打开作业：owned-paper'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'unjudged homework never displays a zero-over-zero correction result',
    (tester) async {
      final value = progressFixture();
      value.addAll({
        'total': 0,
        'corrected': 0,
        'inProgress': 0,
        'notStarted': 0,
        'assisted': 0,
      });
      value['entries'] = [
        {
          'submissionId': 'owned-paper',
          'title': '待核实作业',
          'total': 0,
          'corrected': 0,
          'needsReview': 1,
        },
      ];
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          home: Scaffold(
            body: SingleChildScrollView(
              child: ReportLearningSection(
                learning: ReportLearningSummary.fromJson({
                  'homeworkProgress': value,
                }),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('批改待核实 1 题'), findsOneWidget);
      expect(find.textContaining('已订正 0/0'), findsNothing);
      expect(find.textContaining('暂无已确认需订正'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'self-reported homework stays separate from tested correction totals',
    (tester) async {
      tester.view.physicalSize = const Size(320, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final value = progressFixture();
      value['selfReportedCompleted'] = 1;
      value['notStarted'] = 0;
      (value['entries'] as List).single['selfReportedCompleted'] = 1;
      final learning = ReportLearningSummary.fromJson({
        'homeworkProgress': value,
      });
      expect(learning.homeworkProgress!.corrected, 1);
      expect(learning.homeworkProgress!.selfReportedCompleted, 1);
      expect(
        learning.homeworkProgress!.entries.single.selfReportedCompleted,
        1,
      );
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          home: Scaffold(
            body: SingleChildScrollView(
              child: ReportLearningSection(learning: learning),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('需订正 3 题 · 已订正 1 题'), findsOneWidget);
      expect(find.text('自行完成，未复测 1 题'), findsOneWidget);
      expect(find.text('已订正 1/3 题 · 自行完成，未复测 1 题 · 待核实 1 题'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
