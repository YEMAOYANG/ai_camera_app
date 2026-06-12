import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/features/profile/presentation/profile_pages.dart';
import 'package:guardian_parent_app/src/shared/domain/guardian_identity.dart';

void main() {
  testWidgets('viewer can see family code but cannot reset it', (tester) async {
    await _pumpFamilyMembersPage(
      tester,
      capabilities: const ['view_basic_home', 'view_alerts'],
    );

    expect(find.text('家庭号'), findsWidgets);
    expect(find.text('ABCD1234'), findsOneWidget);
    expect(find.text('复制'), findsOneWidget);
    expect(find.text('新成员入口'), findsNothing);
    expect(find.text('林家的家庭空间'), findsNothing);
    expect(find.text('只有家庭管理员可以重置家庭号。'), findsOneWidget);
    expect(find.text('重置'), findsNothing);
  });

  testWidgets('admin can reset family code inline', (tester) async {
    await _pumpFamilyMembersPage(
      tester,
      capabilities: const ['manage_family_members', 'manage_family_code'],
    );

    expect(find.text('复制'), findsOneWidget);
    expect(find.text('重置'), findsOneWidget);
    expect(find.text('新成员入口'), findsNothing);
  });
}

Future<void> _pumpFamilyMembersPage(
  WidgetTester tester, {
  required List<String> capabilities,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        accountProfileProvider.overrideWith(
          (ref) async => AccountProfile(
            userId: 'viewer_user',
            phone: '13600002326',
            displayName: '临时查看者',
            familyName: '林家的家庭空间',
            relationship: '外婆',
            relationshipKey: 'maternal_grandma',
            role: capabilities.contains('manage_family_code')
                ? 'admin'
                : 'viewer',
            roleLabel: capabilities.contains('manage_family_code')
                ? '管理员'
                : '临时查看者',
            capabilities: capabilities,
            avatarPersona: '',
            gender: '',
            ageGroup: '',
          ),
        ),
        familyCodeProvider.overrideWith(
          (ref) async => const FamilyCodeInfo(
            familyId: 'family_test',
            familyName: '林家的家庭空间',
            code: 'ABCD1234',
            updatedAt: null,
          ),
        ),
        familyMembersProvider.overrideWith((ref) async => const []),
        familyInvitationsProvider.overrideWith((ref) async => const []),
        guardianIdentityOptionsProvider.overrideWith(
          (ref) async => const GuardianIdentityOptions(
            identityGroups: [],
            familyRoles: [],
          ),
        ),
      ],
      child: const MaterialApp(home: FamilyMembersPage()),
    ),
  );

  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}
