import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/profile/presentation/privacy_authorization_gate.dart';

void main() {
  testWidgets(
    'unconfigured admin family with a camera sees authorization before other sheets',
    (tester) async {
      await _usePhoneViewport(tester);
      await tester.pumpWidget(
        _gateApp(
          summary: _summary(deviceCount: 1, canManagePrivacy: true),
          setting: _privacySetting(updatedAt: null),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();

      expect(find.text('开启画面看护'), findsOneWidget);
      expect(
        tester.getSize(find.byType(PrivacyAuthorizationSheet)).height,
        lessThan(520),
      );
      expect(find.byKey(const ValueKey('secondary_overlay')), findsNothing);

      await tester.tap(find.bySemanticsLabel('关闭'));
      await tester.pumpAndSettle();

      expect(find.text('开启画面看护'), findsNothing);
      expect(find.byKey(const ValueKey('secondary_overlay')), findsOneWidget);
    },
  );

  testWidgets('family without a camera does not see authorization', (
    tester,
  ) async {
    await tester.pumpWidget(
      _gateApp(
        summary: _summary(deviceCount: 0, canManagePrivacy: true),
        setting: _privacySetting(updatedAt: null),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('开启画面看护'), findsNothing);
    expect(find.byKey(const ValueKey('secondary_overlay')), findsOneWidget);
  });

  testWidgets('configured family is not prompted again', (tester) async {
    await tester.pumpWidget(
      _gateApp(
        summary: _summary(deviceCount: 1, canManagePrivacy: true),
        setting: _privacySetting(updatedAt: 1),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('开启画面看护'), findsNothing);
    expect(find.byKey(const ValueKey('secondary_overlay')), findsOneWidget);
  });

  testWidgets('family member without privacy permission is not prompted', (
    tester,
  ) async {
    await tester.pumpWidget(
      _gateApp(
        summary: _summary(deviceCount: 1, canManagePrivacy: false),
        setting: _privacySetting(updatedAt: null),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('开启画面看护'), findsNothing);
    expect(find.byKey(const ValueKey('secondary_overlay')), findsOneWidget);
  });

  testWidgets('authorization sheet returns an explicit later decision', (
    tester,
  ) async {
    await _usePhoneViewport(tester);
    bool? decision;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              return TextButton(
                onPressed: () async {
                  decision = await showPrivacyAuthorizationSheet(
                    context,
                    onDecision: (_) async {},
                  );
                },
                child: const Text('打开授权'),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('打开授权'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('privacy_authorization_later')));
    await tester.pumpAndSettle();

    expect(decision, isFalse);
    expect(find.text('开启画面看护'), findsNothing);
  });

  test('profile setting distinguishes a missing decision from saved data', () {
    final missing = ProfileSetting.fromJson({
      'key': 'privacy',
      'value': <String, dynamic>{},
      'updatedAt': null,
    });
    final configured = ProfileSetting.fromJson({
      'key': 'privacy',
      'value': <String, dynamic>{},
      'updatedAt': 123,
    });

    expect(missing.isConfigured, isFalse);
    expect(configured.isConfigured, isTrue);
  });
}

Widget _gateApp({
  required ProfileSummary summary,
  required ProfileSetting setting,
}) {
  return ProviderScope(
    overrides: [
      profileSummaryProvider.overrideWith((ref) async => summary),
      profileSettingProvider.overrideWith((ref, key) async => setting),
    ],
    child: MaterialApp(
      home: PrivacyAuthorizationGate(
        secondaryOverlayBuilder: (child) => KeyedSubtree(
          key: const ValueKey('secondary_overlay'),
          child: child,
        ),
        child: const Scaffold(body: Text('家庭首页')),
      ),
    ),
  );
}

ProfileSummary _summary({
  required int deviceCount,
  required bool canManagePrivacy,
}) {
  return ProfileSummary(
    spaceTitle: '家庭看护空间',
    familyId: 'family_test',
    familyName: '测试家庭',
    displayName: '家长',
    phone: '13800000000',
    relationship: '妈妈',
    relationshipKey: 'mom',
    role: canManagePrivacy ? 'admin' : 'guardian',
    roleLabel: canManagePrivacy ? '管理员' : '监护人',
    capabilities: [if (canManagePrivacy) 'manage_privacy', 'view_live_care'],
    avatarPersona: '',
    memberCount: 1,
    deviceCount: deviceCount,
    pendingItemCount: 0,
    child: null,
  );
}

ProfileSetting _privacySetting({required int? updatedAt}) {
  return ProfileSetting(
    key: 'privacy',
    value: const {
      'cameraCollectionAuthorized': false,
      'childPrivacyAuthorized': false,
      'remoteViewingNoticeEnabled': true,
      'storeEventSnapshotsOnly': true,
    },
    updatedAt: updatedAt,
  );
}

Future<void> _usePhoneViewport(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(390, 844));
  addTearDown(() => tester.binding.setSurfaceSize(null));
}
