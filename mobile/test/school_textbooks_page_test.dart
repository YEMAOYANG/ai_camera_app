import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/learning/presentation/school_textbooks_page.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/textbook_learning_summary.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/setup/application/setup_repository.dart';
import 'package:warm_sight/src/features/setup/presentation/setup_flow_screens.dart';

import 'support/parent_textbook_visual_capture.dart';

const _subjects = ['chinese', 'math', 'english', 'science'];

SchoolTextbook _book(
  String subject, {
  bool selected = false,
  String volume = 'upper',
}) => SchoolTextbook(
  editionId: '$subject-g3-$volume',
  revisionId: 'review-1',
  title:
      '${{'chinese': '语文', 'math': '数学', 'english': '英语', 'science': '科学'}[subject]}三年级${volume == 'upper' ? '上册' : '下册'}',
  publisher: '人民教育出版社',
  editionLabel: '${subject == 'chinese' ? '统编版' : '人教版'} · 根据2022年版课程标准修订',
  subject: subject,
  volume: volume,
  schoolSystem: 'six_year',
  partial: false,
  indexOnly: true,
  lessonCount: 0,
  selected: selected,
  selectionRevision: selected ? 8 : 7,
);

class _Gateway implements TextbookGateway {
  final selected = <String>{};
  bool fail = false;
  bool commitThenFail = false;
  bool missingEnglish = false;
  bool realCatalog = false;
  bool includeFltrp = true;
  List<SchoolTextbook>? reviewedBooks;
  int reads = 0, writes = 0;
  List<SchoolTextbook> submitted = [];
  Map<String, dynamic>? childSubmitted;
  String? manualSemester;
  int contextRevision = 0;
  int contextWrites = 0;
  bool contextCommitThenFail = false;
  @override
  Future<void> updateContext(
    String childId,
    SchoolTextbookCatalog catalog, {
    required String? semester,
  }) async {
    contextWrites++;
    if (fail) throw const TextbookException('学期设置未保存');
    manualSemester = semester;
    contextRevision++;
    if (contextCommitThenFail) throw const TextbookException('响应超时');
  }

  @override
  Future<SchoolTextbookCatalog> catalog(String childId) async {
    reads++;
    if (reviewedBooks != null) {
      return SchoolTextbookCatalog(
        year: 2026,
        semester: 'upper',
        books: reviewedBooks!,
      );
    }
    if (realCatalog) {
      final files = [
        File('../backend/content/textbooks/pep-chinese-g3-upper.index.v1.json'),
        ...Directory('../backend/content/textbooks/math-english-v1')
            .listSync()
            .whereType<File>()
            .where((file) => file.path.endsWith('-g3-upper.index.v1.json')),
        ...Directory('../backend/content/textbooks/math-english-v2')
            .listSync()
            .whereType<File>()
            .where((file) => file.path.endsWith('.json'))
            .where((file) {
              final data = jsonDecode(file.readAsStringSync()) as Map;
              return data['gradeCode'] == 'primary_3' &&
                  data['volume'] == 'upper';
            }),
        ...Directory('../backend/content/textbooks/science-v1')
            .listSync()
            .whereType<File>()
            .where((file) => file.path.contains('.directory-'))
            .where((file) {
              final data = jsonDecode(file.readAsStringSync()) as Map;
              return data['gradeCode'] == 'primary_3' &&
                  data['volume'] == 'upper';
            }),
        if (includeFltrp)
          ...Directory('../backend/content/textbooks/official-directories-v1')
              .listSync()
              .whereType<File>()
              .where((file) => file.path.endsWith('.json'))
              .where((file) {
                final data = jsonDecode(file.readAsStringSync()) as Map;
                return data['gradeCode'] == 'primary_3' &&
                    data['volume'] == 'upper' &&
                    (data['editionLabel'] as String).contains('陈琳');
              }),
      ];
      return SchoolTextbookCatalog(
        year: 2026,
        semester: manualSemester ?? 'upper',
        termSource: manualSemester == null ? 'calendar' : 'parent',
        contextRevision: contextRevision,
        books: [
          for (final file in files)
            SchoolTextbook.fromJson({
              ...jsonDecode(file.readAsStringSync()) as Map<String, dynamic>,
              'lessonCount':
                  ((jsonDecode(file.readAsStringSync()) as Map)['units']
                          as List)
                      .fold<int>(
                        0,
                        (count, unit) =>
                            count + (unit['lessons'] as List).length,
                      ),
              'selected': selected.contains(
                (jsonDecode(file.readAsStringSync()) as Map)['subject'],
              ),
              'selectionRevision': 7,
            }),
        ],
      );
    }
    return SchoolTextbookCatalog(
      year: 2026,
      semester: manualSemester ?? 'upper',
      termSource: manualSemester == null ? 'calendar' : 'parent',
      contextRevision: contextRevision,
      books: [
        for (final subject in _subjects)
          if (!missingEnglish || subject != 'english')
            _book(subject, selected: selected.contains(subject)),
        _book('math', volume: 'lower'),
      ],
    );
  }

  @override
  Future<void> select(
    String childId,
    SchoolTextbookCatalog catalog,
    SchoolTextbook book,
  ) => throw StateError('The screen must use one atomic batch.');
  @override
  Future<void> selectMany(
    String childId,
    SchoolTextbookCatalog catalog,
    List<SchoolTextbook> books,
  ) async {
    writes++;
    submitted = books;
    if (commitThenFail) selected.addAll(books.map((book) => book.subject));
    if (fail || commitThenFail) {
      throw const TextbookException('教材选择已更新，请刷新后重新确认');
    }
    selected.addAll(books.map((book) => book.subject));
  }
}

const _child = ChildProfile(
  id: 'child-a',
  name: '乐乐',
  nickname: '乐乐',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '21:00',
  ageStage: '小学 三年级',
  educationStage: '小学',
  grade: '三年级',
  gradeCode: 'primary_3',
  educationStageCode: 'primary',
  contentMode: 'primary_learning',
  schoolYearStartYear: 2026,
  schoolName: '',
  interests: [],
  taskPreferences: {},
);

AccountProfile _account(bool admin) => AccountProfile(
  userId: 'parent-a',
  phone: '',
  displayName: '家长',
  familyName: '测试家庭',
  relationship: '妈妈',
  relationshipKey: 'mother',
  role: admin ? 'admin' : 'viewer',
  roleLabel: admin ? '管理员' : '查看者',
  capabilities: admin ? ['manage_child_profile'] : [],
  avatarPersona: '',
  gender: '',
  ageGroup: '',
);

Future<void> _mount(
  WidgetTester tester,
  _Gateway gateway, {
  bool admin = true,
  bool setup = false,
  bool startWithChild = false,
  bool startWithSummary = false,
  double width = 390,
  double textScale = 1,
}) async {
  tester.view.physicalSize = Size(width, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  SharedPreferences.setMockInitialValues({});
  final preferences = await SharedPreferences.getInstance();
  final dio = Dio(BaseOptions(baseUrl: 'https://example.test/api'))
    ..interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          if (options.path != '/setup/child') {
            handler.reject(DioException(requestOptions: options));
            return;
          }
          gateway.childSubmitted = Map<String, dynamic>.from(
            options.data as Map,
          );
          handler.resolve(
            Response(
              requestOptions: options,
              statusCode: 200,
              data: {
                'ok': true,
                'setup': {
                  'completed': true,
                  'parentIdentity': 'done',
                  'childProfile': 'done',
                  'nextStep': 'home',
                },
                'child': gateway.childSubmitted,
              },
            ),
          );
        },
      ),
    );
  final router = GoRouter(
    initialLocation: startWithSummary
        ? profileChildPath
        : startWithChild
        ? setupChildProfilePath
        : setup
        ? setupSchoolTextbooksPath
        : profileSchoolTextbooksPath,
    routes: [
      GoRoute(
        path: setupChildProfilePath,
        builder: (_, _) => const ChildProfileSetupScreen(),
      ),
      GoRoute(
        path: AppRoute.home.path,
        builder: (_, _) => const Scaffold(body: Text('测试首页')),
      ),
      GoRoute(
        path: profileChildPath,
        builder: (context, _) => startWithSummary
            ? Scaffold(
                body: SingleChildScrollView(
                  child: TextbookLearningSummary(
                    childId: _child.id,
                    onManage: () => context.push(profileSchoolTextbooksPath),
                  ),
                ),
              )
            : const Scaffold(body: Text('测试孩子资料')),
      ),
      GoRoute(
        path: profileSchoolTextbooksPath,
        builder: (_, _) => const SchoolTextbooksPage(),
      ),
      GoRoute(
        path: setupSchoolTextbooksPath,
        builder: (_, _) => const SchoolTextbooksPage(setupMode: true),
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(preferences),
        setupRepositoryProvider.overrideWithValue(
          SetupRepository(
            apiClient: ApiClient(dio),
            setupStore: SetupStore(preferences),
          ),
        ),
        currentChildProvider.overrideWith((ref) async => _child),
        accountProfileProvider.overrideWith((ref) async => _account(admin)),
        textbookRepositoryProvider.overrideWithValue(gateway),
      ],
      child: MaterialApp.router(
        theme: AppTheme.light,
        routerConfig: router,
        builder: (context, child) => RepaintBoundary(
          key: parentTextbookPreviewKey,
          child: MediaQuery(
            data: MediaQuery.of(
              context,
            ).copyWith(textScaler: TextScaler.linear(textScale)),
            child: child!,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _pick(
  WidgetTester tester,
  String subject, {
  String volume = 'upper',
}) async {
  final row = find.byKey(ValueKey('textbookSubject_$subject'));
  await tester.ensureVisible(row);
  await tester.tap(row);
  await tester.pumpAndSettle();
  final option = find.byKey(
    ValueKey('textbookOption_$subject-g3-$volume:review-1'),
  );
  await tester.ensureVisible(option);
  await tester.tap(option);
  await tester.pumpAndSettle();
}

void main() {
  setUpAll(loadParentTextbookPreviewFont);
  testWidgets('reviewed FLTRP editions show starting grade and curriculum', (
    tester,
  ) async {
    final books =
        [
              ...Directory(
                '../backend/content/textbooks/fltrp-reviewed-v1',
              ).listSync(),
              ...Directory(
                '../backend/content/textbooks/math-english-v2',
              ).listSync(),
            ]
            .whereType<File>()
            .where((file) => file.path.endsWith('.json'))
            .where((file) => !file.path.contains('.20260928-index-1.'))
            .where(
              (file) =>
                  file.path.contains('fltrp-reviewed-v1') ||
                  !file.readAsStringSync().contains('外研社'),
            )
            .map(
              (file) =>
                  jsonDecode(file.readAsStringSync()) as Map<String, dynamic>,
            )
            .where(
              (data) =>
                  data['gradeCode'] == 'primary_3' &&
                  data['volume'] == 'upper' &&
                  data['subject'] == 'english',
            )
            .map(
              (data) => SchoolTextbook.fromJson({
                ...data,
                'lessonCount': (data['units'] as List).fold<int>(
                  0,
                  (count, unit) => count + (unit['lessons'] as List).length,
                ),
                'selected': false,
                'selectionRevision': 0,
              }),
            )
            .toList();
    final gateway = _Gateway()..reviewedBooks = books;
    await _mount(tester, gateway);
    await tester.ensureVisible(
      find.byKey(const ValueKey('textbookSubject_english')),
    );
    await tester.tap(find.byKey(const ValueKey('textbookSubject_english')));
    await tester.pumpAndSettle();
    final search = find.byKey(const ValueKey('textbookVersionSearch'));
    await tester.enterText(search, '陈琳');
    await tester.pumpAndSettle();
    expect(find.text('外研社版（一年级起点，陈琳主编）'), findsOneWidget);
    expect(find.text('外研社版（三年级起点，陈琳主编）'), findsOneWidget);
    expect(find.text('2011课标版'), findsNWidgets(2));
    await captureParentTextbookPreview(tester, 'fltrp-starting-grade-options');
    await tester.enterText(search, '孙有中');
    await tester.pumpAndSettle();
    expect(find.text('外研社版（三年级起点，孙有中主编）'), findsOneWidget);
    expect(find.text('2022课标修订版'), findsOneWidget);
    await captureParentTextbookPreview(tester, 'fltrp-new-edition');
    expect(gateway.writes, 0);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'opening picker refreshes a catalog kept alive by the child summary',
    (tester) async {
      final gateway = _Gateway()
        ..realCatalog = true
        ..includeFltrp = false;
      await _mount(tester, gateway, startWithSummary: true);
      expect(gateway.reads, 1);

      // A catalog import happens while the profile page retains the old read.
      gateway.includeFltrp = true;
      await tester.tap(find.text('选教材'));
      await tester.pumpAndSettle();
      expect(gateway.reads, 2);
      await tester.ensureVisible(
        find.byKey(const ValueKey('textbookSubject_english')),
      );
      await tester.tap(find.byKey(const ValueKey('textbookSubject_english')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('textbookVersionSearch')),
        '陈琳',
      );
      await tester.pumpAndSettle();
      expect(find.text('外研社版（一年级起点，陈琳主编）'), findsOneWidget);
      await captureParentTextbookPreview(tester, 'chenlin-grade3-available');
      expect(gateway.writes, 0);
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'saving primary child information opens optional subject selection',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway, startWithChild: true);
      await tester.enterText(
        find.byKey(const ValueKey('setupInput_孩子称呼')),
        '乐乐',
      );
      await tester.tap(find.byKey(const ValueKey('gradeOption_primary_3')));
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'child-profile-setup');
      await tester.tap(find.text('下一步，选择教材'));
      await tester.pumpAndSettle();
      expect(gateway.childSubmitted?['gradeCode'], 'primary_3');
      expect(gateway.childSubmitted?['nickname'], '乐乐');
      expect(find.text('稍后设置'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('textbookSubject_math')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('textbookSubject_english')),
        findsOneWidget,
      );
      expect(gateway.writes, 0);
    },
  );

  testWidgets(
    'kindergarten registration goes home without a primary textbook step',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway, startWithChild: true);
      await tester.enterText(
        find.byKey(const ValueKey('setupInput_孩子称呼')),
        '乐乐',
      );
      await tester.tap(find.text('幼儿园'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(const ValueKey('gradeOption_kindergarten_small')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('完成设置'));
      await tester.pumpAndSettle();
      expect(find.text('测试首页'), findsOneWidget);
      expect(gateway.reads, 0);
      expect(gateway.writes, 0);
    },
  );
  testWidgets(
    'visual review uses repository textbook metadata at phone size',
    (tester) async {
      final gateway = _Gateway()..realCatalog = true;
      await _mount(tester, gateway, setup: true);
      await captureParentTextbookPreview(tester, 'setup-textbooks');
      await tester.tap(find.byKey(const ValueKey('textbookSubject_math')));
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'math-versions');
      await tester.enterText(
        find.byKey(const ValueKey('textbookVersionSearch')),
        '北师大',
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(
          const ValueKey(
            'textbookOption_bnu-math-g3-upper-2022-standard:20260928-index-1',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('textbookSubject_english')));
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'english-versions');
      await tester.enterText(
        find.byKey(const ValueKey('textbookVersionSearch')),
        '吴欣',
      );
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(
          const ValueKey(
            'textbookOption_pep-wuxin-english-g3-upper-2022-standard:20260928-index-1',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('textbookSubject_science')));
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'science-versions');
      final science = (await gateway.catalog('child-a')).books.firstWhere(
        (book) => book.subject == 'science' && book.versionLabel == '教科版',
      );
      await tester.enterText(
        find.byKey(const ValueKey('textbookVersionSearch')),
        '教科版',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(ValueKey('textbookOption_${science.key}')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('textbookSubject_chinese')));
      await tester.pumpAndSettle();
      await tester.tap(
        find.byKey(
          const ValueKey(
            'textbookOption_pep-chinese-g3-upper-2022-standard:20260923-index-1',
          ),
        ),
      );
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'subjects-selected');
      await tester.ensureVisible(
        find.byKey(const ValueKey('textbookSubject_english')),
      );
      await tester.tap(find.byKey(const ValueKey('textbookSubject_english')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const ValueKey('textbookVersionSearch')),
        '吴欣',
      );
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'english-selected');
      expect(gateway.writes, 0);
      expect(tester.takeException(), isNull);
    },
    skip: !captureParentTextbooks,
  );

  testWidgets('four subjects are staged then confirmed with one atomic save', (
    tester,
  ) async {
    final gateway = _Gateway();
    await _mount(tester, gateway);
    for (final subject in _subjects) {
      await _pick(tester, subject);
    }
    expect(gateway.writes, 0);
    expect(find.text('待保存'), findsNWidgets(4));
    await tester.tap(find.text('保存教材'));
    await tester.pumpAndSettle();
    expect(gateway.writes, 1);
    expect(gateway.submitted.map((book) => book.subject), _subjects);
    expect(gateway.submitted.map((book) => book.selectionRevision), [
      7,
      7,
      7,
      7,
    ]);
    expect(gateway.reads, 2);
    expect(find.text('已确认'), findsNWidgets(4));
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'picker filters term and makes unprepared course status explicit',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway);
      await tester.tap(find.byKey(const ValueKey('textbookSubject_math')));
      await tester.pumpAndSettle();
      expect(find.text('选择后统一保存，课程以学生端实际开放为准。'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('textbookOption_math-g3-lower:review-1')),
        findsNothing,
      );
      expect(find.textContaining('课程已就绪'), findsNothing);
      expect(gateway.writes, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'conflict retains all choices and reads back without replaying a write',
    (tester) async {
      final gateway = _Gateway()..fail = true;
      await _mount(tester, gateway);
      await _pick(tester, 'math');
      await _pick(tester, 'english');
      await tester.tap(find.text('保存教材'));
      await tester.pumpAndSettle();
      expect(find.text('教材选择已更新，请刷新后重新确认'), findsWidgets);
      expect(find.text('待保存'), findsNWidgets(2));
      expect(gateway.writes, 1);
      expect(gateway.reads, 2);
      await tester.pump(const Duration(seconds: 5));
      expect(gateway.writes, 1);
    },
  );

  testWidgets(
    'a timed-out successful write is read back without a duplicate save',
    (tester) async {
      final gateway = _Gateway()..commitThenFail = true;
      await _mount(tester, gateway);
      await _pick(tester, 'math');
      await tester.tap(find.text('保存教材'));
      await tester.pumpAndSettle();
      expect(find.text('已确认'), findsOneWidget);
      expect(find.text('待保存'), findsNothing);
      await tester.tap(find.text('保存教材'));
      await tester.pumpAndSettle();
      expect(gateway.writes, 1);
    },
  );

  testWidgets(
    'missing subject gives an honest empty state and other subjects can save',
    (tester) async {
      final gateway = _Gateway()..missingEnglish = true;
      await _mount(tester, gateway);
      await tester.tap(find.byKey(const ValueKey('textbookSubject_english')));
      await tester.pumpAndSettle();
      expect(find.text('这科教材正在整理'), findsOneWidget);
      await tester.tap(find.byTooltip('关闭'));
      await tester.pumpAndSettle();
      await _pick(tester, 'chinese');
      await tester.tap(find.text('保存教材'));
      await tester.pumpAndSettle();
      expect(gateway.submitted.single.subject, 'chinese');
    },
  );

  testWidgets('optional onboarding can be skipped without writing', (
    tester,
  ) async {
    final gateway = _Gateway();
    await _mount(tester, gateway, setup: true);
    await tester.tap(find.text('稍后设置'));
    await tester.pumpAndSettle();
    expect(find.text('测试首页'), findsOneWidget);
    expect(gateway.writes, 0);
  });

  testWidgets('leaving a draft asks once and can continue or discard', (
    tester,
  ) async {
    final gateway = _Gateway();
    await _mount(tester, gateway, setup: true);
    await _pick(tester, 'math');
    await tester.tap(find.text('稍后设置'));
    await tester.pumpAndSettle();
    expect(find.text('教材还未保存'), findsOneWidget);
    await tester.tap(find.text('继续选择'));
    await tester.pumpAndSettle();
    expect(find.text('待保存'), findsOneWidget);
    await tester.tap(find.text('稍后设置'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('暂不保存'));
    await tester.pumpAndSettle();
    expect(find.text('测试首页'), findsOneWidget);
    expect(gateway.writes, 0);
  });

  testWidgets('setup saves selected subjects then reaches home', (
    tester,
  ) async {
    final gateway = _Gateway();
    await _mount(tester, gateway, setup: true);
    await _pick(tester, 'math');
    await tester.tap(find.text('保存并进入首页'));
    await tester.pumpAndSettle();
    expect(find.text('测试首页'), findsOneWidget);
    expect(gateway.writes, 1);
  });

  testWidgets(
    'small screen and enlarged text remain scrollable without overflow',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway, width: 320, textScale: 1.5);
      for (final subject in _subjects) {
        await _pick(tester, subject);
      }
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('保存教材'));
      await tester.pumpAndSettle();
      expect(gateway.writes, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'official catalog searches editors and keeps school systems separate',
    (tester) async {
      final gateway = _Gateway()..realCatalog = true;
      await _mount(tester, gateway, width: 320, textScale: 1.5);
      await tester.ensureVisible(
        find.byKey(const ValueKey('textbookSubject_english')),
      );
      await tester.tap(find.byKey(const ValueKey('textbookSubject_english')));
      await tester.pumpAndSettle();
      tester.view.viewInsets = const FakeViewPadding(bottom: 280);
      addTearDown(tester.view.resetViewInsets);
      await tester.enterText(
        find.byKey(const ValueKey('textbookVersionSearch')),
        '吴欣',
      );
      await tester.pumpAndSettle();
      expect(find.text('人教版（主编：吴欣）'), findsOneWidget);
      expect(find.text('人教版（主编：苗兴伟）'), findsNothing);
      expect(tester.takeException(), isNull);
      tester.view.resetViewInsets();
      await tester.tap(find.byTooltip('清除搜索'));
      await tester.pumpAndSettle();
      expect(find.byTooltip('清除搜索'), findsNothing);
      await tester.tap(find.text('五四学制'));
      await tester.pumpAndSettle();
      expect(find.text('人教版（主编：吴欣）'), findsNothing);
      final catalog = await gateway.catalog('child-a');
      final book = catalog.books.firstWhere(
        (b) => b.subject == 'english' && b.schoolSystem == 'five_four',
      );
      final option = find.byKey(ValueKey('textbookOption_${book.key}'));
      await tester.ensureVisible(option);
      await tester.tap(option);
      await tester.pumpAndSettle();
      expect(find.text('五四制 · 上册'), findsOneWidget);
      expect(gateway.writes, 0);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'compact identity form can collapse and reopen grades at large text sizes',
    (tester) async {
      await _mount(
        tester,
        _Gateway(),
        startWithChild: true,
        width: 320,
        textScale: 1.5,
      );
      await tester.enterText(
        find.byKey(const ValueKey('setupInput_孩子称呼')),
        '乐乐',
      );
      tester.view.viewInsets = const FakeViewPadding(bottom: 280);
      addTearDown(tester.view.resetViewInsets);
      await tester.pumpAndSettle();
      final grade = find.byKey(const ValueKey('gradeOption_primary_3'));
      await tester.ensureVisible(grade);
      await tester.tap(grade);
      await tester.pumpAndSettle();
      final disclosure = find.byKey(const ValueKey('childGradeDisclosure'));
      await tester.ensureVisible(disclosure);
      expect(grade, findsNothing);
      await tester.tap(disclosure);
      await tester.pumpAndSettle();
      expect(grade, findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'parent can change the current term and restore calendar defaults',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway);
      await tester.tap(find.text('修改学期'));
      await tester.pumpAndSettle();
      await captureParentTextbookPreview(tester, 'semester-picker');
      await tester.tap(find.text('下学期'));
      await tester.pumpAndSettle();
      expect(gateway.manualSemester, 'lower');
      expect(gateway.contextWrites, 1);
      expect(find.textContaining('下学期'), findsWidgets);
      await _pick(tester, 'math', volume: 'lower');
      expect(find.textContaining('下册'), findsWidgets);
      expect(gateway.writes, 0);
      await tester.tap(find.text('修改学期'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('按日期自动判断'));
      await tester.pumpAndSettle();
      expect(find.text('教材还未保存'), findsOneWidget);
      await tester.tap(find.text('继续修改'));
      await tester.pumpAndSettle();
      expect(gateway.manualSemester, isNull);
      expect(gateway.contextWrites, 2);
      expect(find.text('待保存'), findsNothing);
    },
  );

  testWidgets(
    'a failed term write preserves drafts and never replays the write',
    (tester) async {
      final gateway = _Gateway()..fail = true;
      await _mount(tester, gateway);
      await _pick(tester, 'math');
      await tester.tap(find.text('修改学期'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('下学期'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('继续修改'));
      await tester.pumpAndSettle();
      expect(find.text('待保存'), findsOneWidget);
      expect(find.text('学期设置未保存'), findsOneWidget);
      expect(gateway.contextWrites, 1);
      expect(gateway.manualSemester, isNull);
    },
  );

  testWidgets(
    'a lost term response is reconciled by a read without a second write',
    (tester) async {
      final gateway = _Gateway()..contextCommitThenFail = true;
      await _mount(tester, gateway);
      await tester.tap(find.text('修改学期'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('下学期'));
      await tester.pumpAndSettle();
      expect(gateway.contextWrites, 1);
      expect(find.textContaining('下学期'), findsWidgets);
      expect(find.text('响应超时'), findsNothing);
    },
  );

  testWidgets('viewer never calls the parent selection endpoint', (
    tester,
  ) async {
    final gateway = _Gateway();
    await _mount(tester, gateway, admin: false);
    expect(find.text('请家庭管理员确认教材'), findsOneWidget);
    expect(gateway.reads, 0);
    expect(gateway.writes, 0);
  });
}
