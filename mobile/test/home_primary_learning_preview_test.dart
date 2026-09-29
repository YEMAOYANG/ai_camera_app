import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_learning_preview.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'support/fixed_textbook_fixtures.dart';
import 'support/parent_textbook_visual_capture.dart';

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  testWidgets(
    'all four subjects appear in grade one without generation or daily assignment reads',
    (tester) async {
      var legacyReads = 0;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            schoolTextbooksProvider.overrideWith(
              (ref, id) async => fixtureCatalog(),
            ),
            currentLearningPreparationProvider.overrideWith((ref, id) async {
              legacyReads++;
              throw StateError('legacy');
            }),
            todayLearningProvider.overrideWith((ref, id) async {
              legacyReads++;
              throw StateError('legacy');
            }),
          ],
          child: const MaterialApp(
            home: Scaffold(
              body: HomePrimaryLearningPreview(child: _primaryChild),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('语文'), findsOneWidget);
      expect(find.text('数学'), findsOneWidget);
      expect(find.text('英语'), findsOneWidget);
      expect(find.text('科学'), findsOneWidget);
      expect(find.text('待选择学校教材'), findsNWidgets(4));
      expect(find.byType(LinearProgressIndicator), findsNothing);
      await tester.pump(const Duration(minutes: 2));
      expect(legacyReads, 0);
    },
  );

  testWidgets('selected metadata is never shown as a published course', (
    tester,
  ) async {
    await _mount(tester, () async => fixtureCatalog(selected: true));
    expect(find.text('课程待上架'), findsNWidgets(4));
    expect(find.textContaining('已开放'), findsNothing);
    expect(find.textContaining('准备中'), findsNothing);
  });

  testWidgets('published and completed lesson counts come from the server', (
    tester,
  ) async {
    final value = SchoolTextbookCatalog(
      year: 2026,
      semester: 'upper',
      books: [
        fixtureBook(
          'chinese',
          learningStatus: const TextbookLearningStatus(
            status: 'ready',
            available: 7,
            completed: 2,
          ),
        ),
        fixtureBook(
          'math',
          learningStatus: const TextbookLearningStatus(status: 'locked'),
        ),
      ],
      subjects: const [
        TextbookSubject('english', 'unavailable'),
        TextbookSubject('science', 'unavailable'),
      ],
    );
    await _mount(tester, () async => value);
    await captureParentTextbookPreview(tester, 'home-textbook-courses');
    expect(find.text('已开放 7 课 · 已学 2 课'), findsOneWidget);
    expect(find.text('完成前序课程后开放'), findsOneWidget);
    expect(find.text('本年级教材暂未收录'), findsNWidgets(2));
    expect(find.text('重新准备课程'), findsNothing);
  });

  testWidgets('read failure is retryable without mutating course state', (
    tester,
  ) async {
    var calls = 0;
    await _mount(tester, () async {
      if (++calls == 1) throw StateError('offline');
      return fixtureCatalog();
    });
    expect(find.text('课本状态暂时无法读取'), findsOneWidget);
    await tester.tap(find.text('重试'));
    await tester.pumpAndSettle();
    expect(find.text('待选择学校教材'), findsNWidgets(4));
    expect(calls, 2);
  });

  testWidgets(
    'semester and completion refresh without retaining stale book status',
    (tester) async {
      var value = fixtureCatalog(selected: true);
      await _mount(tester, () async => value);
      final container = ProviderScope.containerOf(
        tester.element(find.byType(HomePrimaryLearningPreview)),
      );
      value = const SchoolTextbookCatalog(
        year: 2026,
        semester: 'lower',
        books: [],
        subjects: [
          TextbookSubject('chinese', 'selection_required'),
          TextbookSubject('math', 'selection_required'),
          TextbookSubject('english', 'selection_required'),
          TextbookSubject('science', 'selection_required'),
        ],
      );
      container.invalidate(schoolTextbooksProvider(_primaryChild.id));
      await tester.pumpAndSettle();
      expect(find.text('2026—2027 学年 · 下学期'), findsOneWidget);
      expect(find.text('课程待上架'), findsNothing);
      expect(find.text('待选择学校教材'), findsNWidgets(4));
    },
  );

  testWidgets('compact summary fits a narrow screen with large text', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await _mount(tester, () async => fixtureCatalog(selected: true), scale: 2);
    expect(tester.takeException(), isNull);
    expect(find.text('英语'), findsOneWidget);
    expect(find.text('科学'), findsOneWidget);
  });
}

Future<void> _mount(
  WidgetTester tester,
  Future<SchoolTextbookCatalog> Function() load, {
  double scale = 1,
}) async {
  if (captureParentTextbooks && scale == 1) {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }
  await tester.pumpWidget(
    ProviderScope(
      overrides: [schoolTextbooksProvider.overrideWith((ref, id) => load())],
      child: MaterialApp(
        theme: AppTheme.light,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(
            context,
          ).copyWith(textScaler: TextScaler.linear(scale)),
          child: RepaintBoundary(key: parentTextbookPreviewKey, child: child!),
        ),
        home: const Scaffold(
          body: SingleChildScrollView(
            padding: EdgeInsets.all(16),
            child: HomePrimaryLearningPreview(child: _primaryChild),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

const _primaryChild = ChildProfile(
  id: 'child-1',
  name: '小雨',
  nickname: '小雨',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '',
  ageStage: '',
  educationStage: '小学',
  grade: '一年级',
  gradeCode: 'primary_1',
  educationStageCode: 'primary',
  contentMode: 'primary_learning',
  schoolName: '',
  interests: [],
  taskPreferences: {},
);
