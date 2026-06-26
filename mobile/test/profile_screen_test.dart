import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/points/domain/point_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/profile_screen.dart';

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
          pointsSummaryProvider.overrideWith((ref) async => _points()),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('我的家庭空间'), findsOneWidget);
    expect(find.text('监护人A · 138 **** 9696'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('guardianPersona:guardian_default')),
      findsOneWidget,
    );
    expect(find.text('家庭成员'), findsOneWidget);
    expect(find.text('紧急联系人'), findsNothing);
    expect(find.text('家庭与成员'), findsOneWidget);
    expect(find.text('摄像头管理'), findsOneWidget);
    expect(find.text('设备与看护'), findsNothing);
    expect(find.text('AI 规则与提醒'), findsOneWidget);
    expect(find.text('看护报告'), findsOneWidget);
    expect(find.text('日报和周报'), findsOneWidget);
    expect(find.text('成长时刻'), findsNothing);
    expect(find.text('基础版'), findsOneWidget);
    expect(find.text('订阅与权益'), findsNothing);
    expect(find.text('18'), findsOneWidget);
    expect(find.text('积分'), findsOneWidget);
    expect(find.text('订阅与套餐'), findsNothing);
    expect(find.text('积分与奖励'), findsNothing);
    expect(find.text('隐私与权限'), findsNothing);
    expect(find.text('账号安全'), findsOneWidget);
    expect(find.text('帮助与反馈'), findsOneWidget);
    expect(find.text('关于'), findsOneWidget);
    expect(find.text('账号设置'), findsNothing);
    expect(find.text('任务与奖励'), findsNothing);

    await tester.drag(find.byType(Scrollable).first, const Offset(0, -520));
    await tester.pumpAndSettle();
    expect(find.text('退出登录'), findsOneWidget);
  });

  testWidgets(
    'profile screen uses mom animated guardian when motion is allowed',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(393, 852));
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileSummaryProvider.overrideWith((ref) async => _summary()),
            accountProfileProvider.overrideWith(
              (ref) async => _account('妈妈', displayName: '妈妈本人'),
            ),
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
            pointsSummaryProvider.overrideWith((ref) async => _points()),
          ],
          child: const MaterialApp(home: ProfileScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('妈妈 · 138 **** 9696'), findsOneWidget);
      expect(find.text('妈妈'), findsNothing);
      expect(
        find.byKey(const ValueKey('guardianPersonaAnimated:guardian_mom')),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'profile screen uses dad animated guardian when motion is allowed',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(393, 852));
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            profileSummaryProvider.overrideWith((ref) async => _summary()),
            accountProfileProvider.overrideWith(
              (ref) async => _account('爸爸', displayName: '阿米爸爸'),
            ),
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
            pointsSummaryProvider.overrideWith((ref) async => _points()),
          ],
          child: const MaterialApp(home: ProfileScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('爸爸 · 138 **** 9696'), findsOneWidget);
      expect(find.text('爸爸'), findsNothing);
      expect(
        find.byKey(const ValueKey('guardianPersonaAnimated:guardian_dad')),
        findsOneWidget,
      );
    },
  );

  testWidgets('profile hero keeps guardian art inside compact Android width', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(360, 800));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _summary()),
          accountProfileProvider.overrideWith(
            (ref) async => _account('爸爸', displayName: '阿米爸爸'),
          ),
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
          pointsSummaryProvider.overrideWith((ref) async => _points()),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    final artRect = tester.getRect(
      find.byKey(const ValueKey('guardianPersonaAnimated:guardian_dad')),
    );
    expect(
      artRect.right,
      lessThanOrEqualTo(360 - AppSpacing.pageHorizontalCompact),
    );
  });

  testWidgets('profile hero signal chips stay in one row on compact Android', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(320, 800));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileSummaryProvider.overrideWith((ref) async => _summary()),
          accountProfileProvider.overrideWith(
            (ref) async => _account('爸爸', displayName: '阿米爸爸'),
          ),
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
          pointsSummaryProvider.overrideWith((ref) async => _points()),
        ],
        child: const MaterialApp(home: ProfileScreen()),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    final membersSize = tester.getSize(
      find.byKey(const ValueKey('profileHeroMembersEntry')),
    );
    final devicesSize = tester.getSize(
      find.byKey(const ValueKey('profileHeroDevicesEntry')),
    );
    final pointsSize = tester.getSize(
      find.byKey(const ValueKey('profileHeroPointsEntry')),
    );
    final membersTop = tester
        .getTopLeft(find.byKey(const ValueKey('profileHeroMembersEntry')))
        .dy;
    final devicesTop = tester
        .getTopLeft(find.byKey(const ValueKey('profileHeroDevicesEntry')))
        .dy;
    final pointsTop = tester
        .getTopLeft(find.byKey(const ValueKey('profileHeroPointsEntry')))
        .dy;

    expect(membersSize.height, devicesSize.height);
    expect(pointsSize.height, membersSize.height);
    expect(devicesTop, membersTop);
    expect(pointsTop, membersTop);
  });
}

ProfileSummary _summary() {
  return ProfileSummary(
    spaceTitle: '我的家庭空间',
    familyId: 'family_test',
    familyName: '我的家庭空间',
    displayName: '家长',
    phone: '13812349696',
    relationship: '',
    relationshipKey: '',
    role: 'admin',
    roleLabel: '管理员',
    capabilities: _adminCapabilities,
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

AccountProfile _account(String relationship, {String displayName = '家长'}) {
  return AccountProfile(
    userId: 'user_test',
    phone: '13812349696',
    displayName: displayName,
    familyName: '我的家庭空间',
    relationship: relationship,
    relationshipKey: _relationshipKeyForTest(relationship),
    role: 'admin',
    roleLabel: '管理员',
    capabilities: _adminCapabilities,
    avatarPersona: '',
    gender: '',
    ageGroup: '',
  );
}

PointsSummary _points() {
  return const PointsSummary(
    account: PointAccount(
      familyId: 'family_test',
      childId: 'child_test',
      balance: 18,
      stageNoticeHandledBalance: 0,
      updatedAt: 0,
    ),
    ledger: [],
  );
}

const _adminCapabilities = [
  'manage_family_members',
  'manage_family_code',
  'manage_devices',
  'manage_privacy',
  'manage_subscription',
  'manage_child_profile',
  'manage_child_settings',
  'manage_emergency_contacts',
  'manage_rewards',
  'manage_tasks',
  'confirm_tasks',
  'view_live_care',
  'view_reports',
  'view_points_rewards',
  'manage_account_security',
];

String _relationshipKeyForTest(String relationship) {
  return switch (relationship) {
    '妈妈' => 'mom',
    '爸爸' => 'dad',
    _ => '',
  };
}
