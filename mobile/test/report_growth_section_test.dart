import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/widgets/report_growth_section.dart';
import 'support/parent_textbook_visual_capture.dart';

List<ReportSkillMap> fixture() => [
  for (final child in ['甲', '乙'])
    ReportSkillMap.fromJson({
      'childId': child,
      'childName': '孩子$child',
      'scope': '分数是本期已有证据的表现比例，不是综合能力测评；无证据不计分。',
      'skills': [
        for (final dim in [
          ['self_care', '自理表现'],
          ['order', '整理习惯'],
          ['movement', '运动参与'],
          ['focus', '专注表现'],
          ['initiative', '主动开始'],
          ['independence', '独立作答'],
          ['comprehension', '情境理解'],
          ['retention', '复习保持'],
        ])
          {
            'key': dim[0],
            'label': dim[1],
            'score': child == '甲'
                ? {
                    'order': 100,
                    'independence': 67,
                    'comprehension': 83,
                  }[dim[0]]
                : null,
            'maxScore': 100,
            'detail': '只计算本期直接证据。',
            'evidence': child == '甲' && dim[0] == 'independence'
                ? [
                    {
                      'label': '课件作答',
                      'correct': 4,
                      'total': 6,
                      'recordDate': '2026-09-29',
                      'detail': '《天地人》：提示或家长帮助不计独立答对。',
                    },
                  ]
                : [],
          },
      ],
    }),
];

void main() {
  setUpAll(loadParentTextbookPreviewFont);

  test('missing scores stay unknown and a measured zero stays measured', () {
    final unknown = ReportSkill.fromJson({'score': null});
    final zero = ReportSkill.fromJson({'score': 0});
    expect(unknown.observed, isFalse);
    expect(unknown.scoreLabel, '待观察');
    expect(zero.observed, isTrue);
    expect(zero.scoreLabel, '0');
    expect(ReportData.fromJson({}).skillMaps, isEmpty);
    final report = ReportData.fromJson({
      'skillMaps': [
        {
          'childId': 'a',
          'skills': [
            {'score': null},
          ],
        },
      ],
    });
    expect(report.skillMaps.single.skills.single.score, isNull);
  });

  testWidgets(
    'camera and lesson dimensions share a map with separate children',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        RepaintBoundary(
          key: parentTextbookPreviewKey,
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            theme: AppTheme.light,
            home: Scaffold(
              body: SafeArea(
                child: SingleChildScrollView(
                  child: ReportGrowthSection(maps: fixture()),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('本期有 3 项表现记录'), findsOneWidget);
      expect(find.text('67'), findsOneWidget);
      expect(find.text('待观察'), findsNWidgets(5));
      await captureParentTextbookPreview(tester, 'growth-evidence-map');
      await tester.ensureVisible(find.text('查看评分依据'));
      await tester.tap(find.text('查看评分依据'));
      await tester.pumpAndSettle();
      expect(find.text('2026-09-29 · 课件作答 · 4/6'), findsOneWidget);
      await tester.ensureVisible(find.text('孩子乙'));
      await tester.tap(find.text('孩子乙'));
      await tester.pumpAndSettle();
      expect(find.text('等待第一份直接证据'), findsOneWidget);
      expect(find.text('67'), findsNothing);
      expect(find.text('2026-09-29 · 课件作答 · 4/6'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('narrow screen with large text keeps score evidence readable', (
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
            child: ReportGrowthSection(maps: fixture()),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('查看评分依据'));
    await tester.tap(find.text('查看评分依据'));
    await tester.pumpAndSettle();
    expect(find.textContaining('提示或家长帮助不计独立答对'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
