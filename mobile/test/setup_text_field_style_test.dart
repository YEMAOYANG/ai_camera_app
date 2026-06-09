import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guardian_parent_app/src/core/theme/app_theme.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/setup_flow_screens.dart';
import 'package:guardian_parent_app/src/shared/domain/guardian_identity.dart';

void main() {
  testWidgets('parent identity setup uses adaptive selectors', (tester) async {
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
