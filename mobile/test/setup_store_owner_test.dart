import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('same account can resume its unfinished child setup', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final store = SetupStore(preferences);

    await store.claimPendingOwner('user-a');
    await store.savePendingChildNickname('乐乐');
    await store.savePendingGrade(
      gradeCode: 'primary_3',
      schoolYearStartYear: 2026,
    );

    await store.claimPendingOwner(' user-a ');

    expect(store.pendingOwnerUserId, 'user-a');
    expect(store.pendingChildNickname, '乐乐');
    expect(store.pendingGradeCode, 'primary_3');
    expect(store.pendingSchoolYearStartYear, 2026);
  });

  test('different account cannot inherit unfinished child setup', () async {
    SharedPreferences.setMockInitialValues(const {});
    final preferences = await SharedPreferences.getInstance();
    final store = SetupStore(preferences);

    await store.claimPendingOwner('user-a');
    await store.savePendingChildNickname('乐乐');
    await store.savePendingGrade(
      gradeCode: 'primary_3',
      schoolYearStartYear: 2026,
    );

    await store.claimPendingOwner('user-b');

    expect(store.pendingOwnerUserId, 'user-b');
    expect(store.pendingChildNickname, isEmpty);
    expect(store.pendingGradeCode, isEmpty);
    expect(store.pendingSchoolYearStartYear, isNull);
  });

  test('first owner discards legacy unowned pending fields', () async {
    SharedPreferences.setMockInitialValues(const {
      pendingSetupChildNicknameKey: '旧称呼',
      pendingSetupGradeCodeKey: 'primary_6',
      pendingSetupSchoolYearStartKey: 2026,
    });
    final preferences = await SharedPreferences.getInstance();
    final store = SetupStore(preferences);

    await store.claimPendingOwner('user-a');

    expect(store.pendingOwnerUserId, 'user-a');
    expect(store.pendingChildNickname, isEmpty);
    expect(store.pendingGradeCode, isEmpty);
    expect(store.pendingSchoolYearStartYear, isNull);
  });
}
