import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/learning/presentation/school_textbooks_page.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';

SchoolTextbook _book({bool selected = false, bool indexOnly = false}) => SchoolTextbook(
  editionId: 'pep-g1',
  revisionId: 'review-1',
  title: '语文 一年级上册',
  publisher: '人民教育出版社',
  editionLabel: '根据2022年版课程标准修订；出版版次待核验',
  subject: 'chinese',
  volume: 'upper',
  schoolSystem: 'six_year',
  partial: true,
  indexOnly: indexOnly,
  lessonCount: indexOnly ? 0 : 6,
  selected: selected,
  selectionRevision: selected ? 8 : 7,
);

class _Gateway implements TextbookGateway {
  bool selected = false;
  bool fail = false;
  bool indexOnly = false;
  int reads = 0;
  int writes = 0;
  int? expectedRevision;
  @override
  Future<SchoolTextbookCatalog> catalog(String childId) async {
    reads++;
    return SchoolTextbookCatalog(
      year: 2026,
      semester: 'upper',
      books: [_book(selected: selected, indexOnly: indexOnly)],
    );
  }

  @override
  Future<void> select(
    String childId,
    SchoolTextbookCatalog catalog,
    SchoolTextbook book,
  ) async {
    writes++;
    expectedRevision = book.selectionRevision;
    if (fail) throw const TextbookException('教材选择已更新，请刷新后重新确认');
    selected = true;
  }
}

const _child = ChildProfile(
  id: 'child-a',
  name: '乐乐',
  nickname: '乐乐',
  gender: 'unspecified',
  birthday: '',
  sleepTime: '21:00',
  ageStage: '小学 一年级',
  educationStage: '小学',
  grade: '一年级',
  gradeCode: 'primary_1',
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
}) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        currentChildProvider.overrideWith((ref) async => _child),
        accountProfileProvider.overrideWith((ref) async => _account(admin)),
        textbookRepositoryProvider.overrideWithValue(gateway),
      ],
      child: const MaterialApp(home: SchoolTextbooksPage()),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('an indexed book can be confirmed without claiming lessons are ready', (tester) async {
    final gateway = _Gateway()..indexOnly = true;
    await _mount(tester, gateway);
    expect(find.text('版本已收录，单元与课次目录正在核对'), findsOneWidget);
    expect(find.textContaining('目录已整理'), findsNothing);
    await tester.ensureVisible(find.text('使用这本教材'));
    await tester.tap(find.text('使用这本教材'));
    await tester.pumpAndSettle();
    expect(gateway.writes, 1);
    expect(find.text('已确认使用'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'parent confirms exact book and refreshes once without layout overflow',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway);
      expect(find.text('语文 一年级上册'), findsOneWidget);
      expect(find.textContaining('部分目录'), findsOneWidget);
      await tester.ensureVisible(find.text('使用这本教材'));
      await tester.tap(find.text('使用这本教材'));
      await tester.pumpAndSettle();
      expect(gateway.writes, 1);
      expect(gateway.expectedRevision, 7);
      expect(gateway.reads, 2);
      expect(find.text('已确认使用'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'stale selection refreshes for review without automatic write replay',
    (tester) async {
      final gateway = _Gateway()..fail = true;
      await _mount(tester, gateway);
      await tester.ensureVisible(find.text('使用这本教材'));
      await tester.tap(find.text('使用这本教材'));
      await tester.pumpAndSettle();
      expect(find.text('教材选择已更新，请刷新后重新确认'), findsOneWidget);
      expect(gateway.writes, 1);
      expect(gateway.reads, 2);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'viewer cannot read administrator selection endpoint or confirm',
    (tester) async {
      final gateway = _Gateway();
      await _mount(tester, gateway, admin: false);
      expect(find.text('请家庭管理员确认教材'), findsOneWidget);
      expect(gateway.reads, 0);
      expect(gateway.writes, 0);
    },
  );
}
