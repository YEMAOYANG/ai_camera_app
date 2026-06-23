import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guardian_parent_app/src/core/theme/app_theme.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/setup_flow_screens.dart';
import 'package:guardian_parent_app/src/shared/domain/guardian_identity.dart';

void main() {
  testWidgets('parent identity setup hides V1 family role selector', (
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
    expect(find.byKey(const ValueKey('familyRoleSegment_admin')), findsNothing);
    expect(
      find.byKey(const ValueKey('familyRoleSegment_guardian')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey('familyRoleSegment_viewer')),
      findsNothing,
    );
    expect(find.text('1 / 2'), findsOneWidget);
    expect(find.text('3 / 2'), findsNothing);
  });

  testWidgets('child profile setup is the second V1 setup step', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ChildProfileSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('孩子资料'), findsOneWidget);
    expect(find.text('2 / 2'), findsOneWidget);
    expect(find.text('3 / 2'), findsNothing);
    expect(find.text('就读阶段'), findsNothing);
    expect(find.text('幼儿园'), findsNothing);
    expect(find.text('幼儿园班级'), findsOneWidget);
    expect(find.text('小班'), findsOneWidget);
    expect(find.text('中班'), findsOneWidget);
    expect(find.text('大班'), findsOneWidget);
    expect(_choiceColor(tester, '小班'), isNot(AppColors.brandWash));
    expect(_choiceColor(tester, '中班'), isNot(AppColors.brandWash));
    expect(_choiceColor(tester, '大班'), isNot(AppColors.brandWash));
    expect(find.textContaining('生日和班级只用于'), findsNothing);
  });

  testWidgets('child profile birthday recommends kindergarten class', (
    tester,
  ) async {
    const datePickerChannel = MethodChannel('ai_camera_app/native_date_picker');
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      datePickerChannel,
      (call) async => '2021-06-01',
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        datePickerChannel,
        null,
      ),
    );

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ChildProfileSetupScreen(),
        ),
      ),
    );
    await tester.pump();

    await _tapBirthdayField(tester);
    await tester.pumpAndSettle();

    expect(find.text('2021-06-01'), findsOneWidget);
    expect(find.text('已推荐班级'), findsOneWidget);
    expect(find.text('推荐 中班，可手动调整。'), findsOneWidget);
    expect(_choiceColor(tester, '中班'), AppColors.brandWash);
    expect(_choiceColor(tester, '大班'), isNot(AppColors.brandWash));
  });

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

    await tester.tap(find.byKey(const ValueKey('guardianIdentityGroupSelect')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('祖辈').last);
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

Future<void> _tapBirthdayField(WidgetTester tester) async {
  final field = find.byKey(const ValueKey('setupInput_出生日期'));
  await tester.ensureVisible(field);
  final rect = tester.getRect(field);
  await tester.tapAt(Offset(rect.left + 12, rect.center.dy));
}

Color? _choiceColor(WidgetTester tester, String option) {
  final container = tester.widget<AnimatedContainer>(
    find
        .descendant(
          of: find.byKey(ValueKey('choice_幼儿园班级_$option')),
          matching: find.byType(AnimatedContainer),
        )
        .first,
  );
  return (container.decoration as BoxDecoration?)?.color;
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
