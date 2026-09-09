import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/setup/application/setup_draft.dart';
import 'package:warm_sight/src/features/setup/application/setup_repository.dart';
import 'package:warm_sight/src/features/setup/presentation/setup_flow_screens.dart';
import 'package:warm_sight/src/shared/domain/guardian_identity.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';

void main() {
  test(
    'legacy child without a confirmed school year is routed to grade selection',
    () {
      final status = SetupStatus.fromResponse({
        'setup': {
          'completed': true,
          'parentIdentity': 'done',
          'childProfile': 'done',
          'nextStep': 'home',
        },
        'child': {
          'grade': '三年级',
          'educationStage': '小学',
          'gradeCode': 'primary_3',
          'gradeSelectionRequired': true,
        },
      });

      expect(status.childGradeSelectionRequired, isTrue);
      expect(status.routePath, setupChildProfilePath);
    },
  );

  testWidgets('parent identity setup shows family role selector', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          guardianIdentityOptionsProvider.overrideWith(
            (ref) async => _identityOptions(),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ParentIdentitySetupScreen(),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(TextField), findsNothing);
    expect(
      find.byKey(const ValueKey('guardianIdentityGroupSelect')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCards')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCard_妈妈')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCard_爸爸')),
      findsOneWidget,
    );
    expect(find.text('家庭身份'), findsOneWidget);
    expect(find.text('显示称呼'), findsOneWidget);
    expect(find.text('父母'), findsOneWidget);
    expect(find.text('妈妈'), findsOneWidget);
    expect(find.text('保姆'), findsNothing);
    expect(find.text('其他照护人'), findsNothing);
    expect(find.text('权限角色'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('familyRoleSegment_admin')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('familyRoleSegment_guardian')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('familyRoleSegment_viewer')),
      findsOneWidget,
    );
    expect(find.text('1 / 2'), findsOneWidget);
    expect(find.text('3 / 2'), findsNothing);
  });

  testWidgets('child learning identity requires both nickname and grade', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [sharedPreferencesProvider.overrideWithValue(preferences)],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ChildProfileSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('设置孩子的学习身份'), findsOneWidget);
    expect(find.text('用于称呼孩子并匹配适龄内容'), findsOneWidget);
    expect(find.text('2 / 2'), findsOneWidget);
    expect(find.text('3 / 2'), findsNothing);
    expect(find.text('幼儿园'), findsOneWidget);
    expect(find.text('小学'), findsOneWidget);
    expect(_stageChoiceColor(tester, 'primary'), AppColors.brandDeep);
    expect(_stageChoiceColor(tester, 'kindergarten'), Colors.transparent);
    expect(find.text('选择小学年级'), findsOneWidget);
    expect(find.text('新一年级'), findsOneWidget);
    expect(find.text('新六年级'), findsOneWidget);
    expect(find.byKey(const ValueKey('gradeOption_primary_3')), findsOneWidget);
    expect(find.byKey(const ValueKey('gradeOption_primary_6')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('gradeOption_kindergarten_small')),
      findsNothing,
    );
    expect(find.text('孩子称呼'), findsOneWidget);
    expect(find.byKey(const ValueKey('setupInput_孩子称呼')), findsOneWidget);
    expect(find.text('摄像头老师会这样称呼孩子'), findsOneWidget);
    expect(find.text('性别'), findsNothing);
    expect(find.text('出生日期'), findsNothing);
    expect(find.text('初中'), findsNothing);
    expect(find.text('高中'), findsNothing);
    expect(find.text('入睡时间'), findsNothing);
    expect(find.text('学校'), findsNothing);
    expect(find.text('兴趣'), findsNothing);
    expect(
      tester.widget<AppPrimaryButton>(find.byType(AppPrimaryButton)).onTap,
      isNull,
    );

    await tester.enterText(find.byKey(const ValueKey('setupInput_孩子称呼')), '乐乐');
    await tester.pump();

    expect(
      tester.widget<AppPrimaryButton>(find.byType(AppPrimaryButton)).onTap,
      isNull,
    );
    expect(preferences.getString(pendingSetupChildNicknameKey), '乐乐');

    await tester.tap(find.byKey(const ValueKey('gradeOption_primary_3')));
    await tester.pumpAndSettle();

    expect(_gradeChoiceColor(tester, 'primary_3'), AppColors.brandDeep);
    expect(
      tester.widget<AppPrimaryButton>(find.byType(AppPrimaryButton)).onTap,
      isNotNull,
    );
    expect(preferences.getString('pendingSetupGradeCode'), 'primary_3');
  });

  testWidgets('only the active school stage grade scale is rendered', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 760);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [sharedPreferencesProvider.overrideWithValue(preferences)],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ChildProfileSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    final first = tester.getRect(
      find.byKey(const ValueKey('gradeOption_primary_1')),
    );
    final second = tester.getRect(
      find.byKey(const ValueKey('gradeOption_primary_2')),
    );
    final third = tester.getRect(
      find.byKey(const ValueKey('gradeOption_primary_3')),
    );
    expect((first.top - second.top).abs(), lessThan(1));
    expect((first.top - third.top).abs(), lessThan(1));
    expect(first.width, greaterThanOrEqualTo(44));
    expect(first.height, greaterThanOrEqualTo(44));
    final fourth = tester.getRect(
      find.byKey(const ValueKey('gradeOption_primary_4')),
    );
    expect(fourth.top, greaterThan(first.bottom));
    expect(
      find.byKey(const ValueKey('gradeOption_kindergarten_big')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);

    await tester.tap(find.byKey(const ValueKey('gradeStage_kindergarten')));
    await tester.pumpAndSettle();

    expect(_stageChoiceColor(tester, 'kindergarten'), AppColors.brandDeep);
    expect(_stageChoiceColor(tester, 'primary'), Colors.transparent);
    expect(find.byKey(const ValueKey('gradeOption_primary_3')), findsNothing);
    expect(
      find.byKey(const ValueKey('gradeOption_kindergarten_small')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('gradeOption_kindergarten_big')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey('gradeOption_kindergarten_big')),
    );
    await tester.pumpAndSettle();
    expect(_gradeChoiceColor(tester, 'kindergarten_big'), AppColors.brandDeep);
    expect(tester.takeException(), isNull);
  });

  testWidgets('pending child nickname resumes an interrupted setup', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({
      pendingSetupChildNicknameKey: '朵朵',
    });
    final preferences = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(preferences),
          setupDraftProvider.overrideWith(
            (ref) => const SetupDraft(childName: '已有姓名'),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ChildProfileSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    final field = tester.widget<TextField>(
      find.byKey(const ValueKey('setupInput_孩子称呼')),
    );
    expect(field.controller?.text, '朵朵');
    expect(
      tester.widget<AppPrimaryButton>(find.byType(AppPrimaryButton)).onTap,
      isNull,
    );
  });

  testWidgets('clearing a legacy child name keeps nickname empty', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(preferences),
          setupDraftProvider.overrideWith(
            (ref) => const SetupDraft(childName: '旧名字'),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ChildProfileSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    final input = find.byKey(const ValueKey('setupInput_孩子称呼'));
    expect(tester.widget<TextField>(input).controller?.text, '旧名字');

    await tester.enterText(input, '');
    await tester.pump();

    expect(tester.widget<TextField>(input).controller?.text, isEmpty);
    expect(
      tester.widget<AppPrimaryButton>(find.byType(AppPrimaryButton)).onTap,
      isNull,
    );
  });

  test('setup status maps child nickname into the setup draft', () {
    final status = SetupStatus.fromResponse({
      'setup': {
        'completed': false,
        'parentIdentity': 'done',
        'childProfile': 'pending',
        'nextStep': 'child',
      },
      'child': {
        'name': '乐乐',
        'nickname': '乐乐',
        'gradeCode': 'primary_3',
        'schoolYearStartYear': DateTime.now().year,
      },
    });

    final draft = setupDraftFromStatus(status);
    expect(status.childNickname, '乐乐');
    expect(draft.childName, '乐乐');
    expect(draft.childNickname, '乐乐');
    expect(draft.childGradeCode, 'primary_3');
  });

  test(
    'setup draft from empty current account status clears old child data',
    () {
      const previous = SetupDraft(
        childName: '小爱',
        childNickname: '爱爱',
        childBirthday: '2021-06-03',
        childGrade: '中班',
        childGender: 'girl',
      );
      final next = setupDraftFromStatus(_emptyChildSetupStatus());

      expect(previous.childName, '小爱');
      expect(previous.childNickname, '爱爱');
      expect(next.childName, isEmpty);
      expect(next.childNickname, isEmpty);
      expect(next.childBirthday, isEmpty);
      expect(next.childGrade, isEmpty);
      expect(next.childGender, 'unspecified');
    },
  );

  testWidgets('legacy setup pages do not show V1 setup progress', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          guardianIdentityOptionsProvider.overrideWith(
            (ref) async => _identityOptions(),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const EmergencyContactsSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('紧急联系人'), findsOneWidget);
    expect(find.text('6 / 2'), findsNothing);
    expect(find.text('3 / 2'), findsNothing);
  });

  testWidgets('parent identity group drives display name options', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          guardianIdentityOptionsProvider.overrideWith(
            (ref) async => _identityOptions(),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ParentIdentitySetupScreen(),
        ),
      ),
    );
    await tester.pump();

    await tester.tap(
      find.byKey(const ValueKey('guardianIdentityGroupOption_grandparent')),
    );
    await tester.pumpAndSettle();

    expect(find.text('祖辈'), findsOneWidget);
    expect(find.text('外公'), findsOneWidget);

    expect(find.text('外婆'), findsOneWidget);
    expect(find.text('爷爷'), findsOneWidget);
    expect(find.text('奶奶'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCard_外公')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCard_外婆')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCard_爷爷')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('guardianDisplayNameCard_奶奶')),
      findsOneWidget,
    );
  });

  testWidgets('parent identity cards stay in two columns on narrow screens', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 760);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          guardianIdentityOptionsProvider.overrideWith(
            (ref) async => _identityOptions(),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ParentIdentitySetupScreen(),
        ),
      ),
    );
    await tester.pump();

    final momRect = tester.getRect(
      find.byKey(const ValueKey('guardianDisplayNameCard_妈妈')),
    );
    final dadRect = tester.getRect(
      find.byKey(const ValueKey('guardianDisplayNameCard_爸爸')),
    );

    expect((momRect.top - dadRect.top).abs(), lessThan(1));
    expect(momRect.width, lessThan(150));
    expect(dadRect.left, greaterThan(momRect.right));
  });
}

Color? _gradeChoiceColor(WidgetTester tester, String code) {
  final container = tester.widget<AnimatedContainer>(
    find
        .descendant(
          of: find.byKey(ValueKey('gradeOption_$code')),
          matching: find.byType(AnimatedContainer),
        )
        .first,
  );
  return (container.decoration as BoxDecoration?)?.color;
}

Color? _stageChoiceColor(WidgetTester tester, String code) {
  final container = tester.widget<AnimatedContainer>(
    find.byKey(ValueKey('gradeStage_$code')),
  );
  return (container.decoration as BoxDecoration?)?.color;
}

SetupStatus _emptyChildSetupStatus() {
  return const SetupStatus(
    completed: false,
    parentIdentity: 'done',
    deviceBinding: 'pending',
    wifi: 'pending',
    childProfile: 'pending',
    cameraName: 'pending',
    cameraNameIntro: 'pending',
    cameraNameIntroAt: null,
    contacts: 'pending',
    nextStep: 'child',
    parentDisplayName: '爸爸',
    parentRelationship: '爸爸',
    parentRelationshipKey: 'dad',
    parentRole: 'admin',
    deviceName: '',
    deviceLocation: '',
    wifiName: '',
    childName: '',
    childGender: 'unspecified',
    childBirthday: '',
    childSleepTime: '',
    childEducationStage: '',
    childGrade: '',
    cameraWakeName: '',
  );
}

GuardianIdentityOptions _identityOptions() {
  return GuardianIdentityOptions.fromJson({
    'identityGroups': [
      {
        'key': 'parent',
        'label': '父母',
        'defaultKey': 'mom',
        'defaultLabel': '妈妈',
        'labels': [
          {
            'key': 'mom',
            'label': '妈妈',
            'imageAsset': 'assets/images/guardian/guardian_mom.png',
          },
          {
            'key': 'dad',
            'label': '爸爸',
            'imageAsset': 'assets/images/guardian/guardian_dad.png',
          },
        ],
      },
      {
        'key': 'grandparent',
        'label': '祖辈',
        'defaultKey': 'maternal_grandpa',
        'defaultLabel': '外公',
        'labels': [
          {
            'key': 'maternal_grandpa',
            'label': '外公',
            'imageAsset':
                'assets/images/guardian/guardian_maternal_grandpa.png',
          },
          {
            'key': 'maternal_grandma',
            'label': '外婆',
            'imageAsset':
                'assets/images/guardian/guardian_maternal_grandma.png',
          },
          {
            'key': 'grandpa',
            'label': '爷爷',
            'imageAsset': 'assets/images/guardian/guardian_grandpa.png',
          },
          {
            'key': 'grandma',
            'label': '奶奶',
            'imageAsset': 'assets/images/guardian/guardian_grandma.png',
          },
        ],
      },
    ],
    'familyRoles': [
      {'key': 'admin', 'label': '管理员'},
      {'key': 'guardian', 'label': '监护人'},
      {'key': 'viewer', 'label': '临时查看者'},
    ],
  });
}
