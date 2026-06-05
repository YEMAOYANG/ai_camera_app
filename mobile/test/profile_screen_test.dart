import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/features/profile/presentation/profile_screen.dart';

void main() {
  testWidgets('profile screen shows fallback persona and top-level groups', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _summary()),
          accountProfileProvider.overrideWith((ref) async => _account('监护人A')),
          subscriptionStatusProvider.overrideWith(
            (ref) async => const SubscriptionStatus(
              planId: 'basic',
              planLabel: '基础版',
              status: 'active',
              statusLabel: '已启用',
              renewalText: '基础看护保持可用',
              entitlements: [],
            ),
          ),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('家庭看护空间'), findsOneWidget);
    expect(find.text('监护人A · 138 **** 9696'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('guardianPersona:guardian_default')),
      findsOneWidget,
    );
    expect(find.text('家庭与成员'), findsOneWidget);
    expect(find.text('设备与看护'), findsOneWidget);
    expect(find.text('AI 规则与提醒'), findsOneWidget);
    expect(find.text('订阅与套餐'), findsOneWidget);
    expect(find.text('积分与奖励'), findsOneWidget);
    expect(find.text('隐私与授权'), findsOneWidget);
    expect(find.text('账号设置'), findsOneWidget);
    expect(find.text('任务与奖励'), findsNothing);
  });
}

ProfileSummary _summary() {
  return ProfileSummary(
    spaceTitle: '家庭看护空间',
    familyId: 'family_test',
    familyName: '我的家庭空间',
    displayName: '家长',
    phone: '13812349696',
    roleLabel: '管理员',
    avatarPersona: '',
    memberCount: 4,
    deviceCount: 2,
    pendingItemCount: 1,
    child: ChildProfile.fromJson({
      'id': 'child_test',
      'name': '小晨',
      'educationStage': '幼儿园',
      'grade': '中班',
    }),
  );
}

AccountProfile _account(String relationship) {
  return AccountProfile(
    userId: 'user_test',
    phone: '13812349696',
    displayName: '家长',
    familyName: '我的家庭空间',
    relationship: relationship,
    role: 'admin',
    avatarPersona: '',
    gender: '',
    ageGroup: '',
  );
}
