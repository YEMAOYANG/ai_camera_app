import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/app/app.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/storage/auth_session_store.dart';
import 'package:mira_guardian_app/src/core/storage/onboarding_store.dart';
import 'package:mira_guardian_app/src/core/storage/setup_store.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('renders the welcome onboarding slides', (tester) async {
    await _pumpApp(tester, preferences: const {});
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('家庭看护'), findsOneWidget);
    expect(find.text('少盯一点，也能知道孩子现在怎么样。'), findsOneWidget);
    expect(find.text('继续'), findsOneWidget);
    expect(find.text('登录或创建家庭'), findsOneWidget);

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('任务陪伴'), findsOneWidget);
    expect(find.text('AI 负责安静观察，孩子保留自己的节奏。'), findsOneWidget);

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('家长确认'), findsOneWidget);
    expect(find.text('关键决定由家长确认，AI 不替你承诺。'), findsOneWidget);

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('家庭空间'), findsOneWidget);
    expect(find.text('看护要有科技感，也要有家的温度。'), findsOneWidget);
    expect(find.text('开始设置'), findsOneWidget);

    await tester.tap(find.text('开始设置'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('登录家庭看护空间'), findsOneWidget);
    expect(find.text('手机号'), findsOneWidget);
  });

  testWidgets('skips onboarding after it has been seen', (tester) async {
    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('登录家庭看护空间'), findsOneWidget);
    expect(find.text('家庭看护'), findsNothing);
  });

  testWidgets('starts at home when refresh session is still valid', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'mock_access_saved',
        authRefreshTokenKey: 'mock_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'mock_parent_13800002026',
        authPhoneKey: '13800002026',
      },
    );
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('登录家庭看护空间'), findsNothing);
    expect(find.text('需要你处理'), findsOneWidget);
  });

  testWidgets('runs login then first setup flow into home', (tester) async {
    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester);

    expect(find.text('确认家长身份'), findsOneWidget);
    await tester.tap(find.text('继续绑定设备'));
    await tester.pumpAndSettle();

    expect(find.text('绑定看护设备'), findsOneWidget);
    await tester.tap(find.text('配置 Wi-Fi'));
    await tester.pumpAndSettle();

    expect(find.text('Wi-Fi 配网'), findsOneWidget);
    await tester.enterText(find.byType(EditableText).at(0), 'Mira Home 2.4G');
    await tester.enterText(find.byType(EditableText).at(1), 'mira2026home');
    await tester.pump();
    await tester.tap(find.text('开始绑定'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(find.text('设备绑定成功'), findsOneWidget);
    await tester.tap(find.text('创建孩子资料'));
    await tester.pumpAndSettle();

    expect(find.text('孩子资料'), findsOneWidget);
    await tester.enterText(find.byType(EditableText).at(0), '小宇');
    await tester.pump();
    await tester.tap(find.text('设置紧急联系人'));
    await tester.pumpAndSettle();

    expect(find.text('紧急联系人'), findsOneWidget);
    await tester.tap(find.text('进入首页'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(find.text('Mira Guardian'), findsOneWidget);
    expect(find.text('客厅米拉 · 在线看护中'), findsOneWidget);
    expect(find.text('需要你处理'), findsOneWidget);
  });

  testWidgets('shows login validation errors from continue', (tester) async {
    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 250));

    expect(find.text('请填写手机号'), findsOneWidget);
    expect(find.text('请输入验证码'), findsOneWidget);
    expect(find.text('请先同意用户协议和隐私政策'), findsOneWidget);

    await tester.enterText(find.byType(EditableText).at(0), '12345');
    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 250));

    expect(find.text('请输入正确的 11 位手机号'), findsOneWidget);
  });

  testWidgets('opens legal documents from login agreement links', (
    tester,
  ) async {
    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.widgetWithText(TextButton, '用户协议'));
    await tester.pumpAndSettle();

    expect(find.text('用户协议'), findsOneWidget);
    expect(find.text('1. 服务说明'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();

    expect(find.text('登录家庭看护空间'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, '隐私政策'));
    await tester.pumpAndSettle();

    expect(find.text('隐私政策'), findsOneWidget);
    expect(find.text('1. 开发者与适用范围'), findsOneWidget);
  });

  testWidgets('switches main tabs and opens task detail', (tester) async {
    await _pumpApp(
      tester,
      preferences: const {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
      },
    );
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester);

    expect(find.text('Mira Guardian'), findsOneWidget);
    expect(find.text('客厅米拉 · 在线看护中'), findsOneWidget);

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    expect(find.text('数学作业'), findsWidgets);
    expect(find.text('+0 分'), findsNothing);

    await tester.tap(find.text('数学作业').last);
    await tester.pumpAndSettle();
    expect(find.text('任务进行中'), findsOneWidget);
    expect(find.text('当前观察'), findsOneWidget);
    expect(find.text('时间和奖励'), findsOneWidget);
    expect(find.text('任务记录'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();

    await tester.tap(find.text('看护').last);
    await tester.pumpAndSettle();
    expect(find.text('实时看护'), findsOneWidget);

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();
    expect(find.text('家庭看护空间'), findsOneWidget);
    expect(find.text('家庭与孩子'), findsOneWidget);
  });

  testWidgets('rejecting a confirmation task is final in V1 copy', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      preferences: const {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
      },
    );
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester);

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('英语听读').last);
    await tester.tap(find.text('英语听读').last);
    await tester.pumpAndSettle();

    expect(find.text('等待你确认'), findsOneWidget);
    expect(find.text('确认完成'), findsOneWidget);
    expect(find.text('驳回'), findsOneWidget);

    await tester.tap(find.text('驳回'));
    await tester.pumpAndSettle();

    expect(find.text('已驳回'), findsWidgets);
    expect(find.text('本次任务未通过确认，未发放积分。'), findsWidgets);
    expect(find.text('原因：证据不足，未通过家长确认。'), findsOneWidget);
    expect(find.text('时间和奖励'), findsOneWidget);
    expect(find.text('任务记录'), findsOneWidget);
    expect(find.text('确认完成'), findsNothing);
    expect(find.textContaining('等待孩子补充'), findsNothing);
    expect(find.textContaining('补充完成'), findsNothing);
  });

  testWidgets('opens points and rewards flows from profile', (tester) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'mock_access_saved',
        authRefreshTokenKey: 'mock_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'mock_parent_13800002026',
        authPhoneKey: '13800002026',
      },
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();

    final pointsEntry = find.text('积分账户');
    await tester.scrollUntilVisible(pointsEntry, 400);
    await Scrollable.ensureVisible(
      tester.element(pointsEntry),
      alignment: 0.35,
    );
    await tester.pumpAndSettle();
    await tester.tap(pointsEntry);
    await tester.pumpAndSettle();
    expect(find.text('积分流水'), findsOneWidget);
    expect(find.text('补发或更正积分'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();
    final rewardsEntry = find.text('奖励中心');
    await tester.scrollUntilVisible(rewardsEntry, 400);
    await Scrollable.ensureVisible(
      tester.element(rewardsEntry),
      alignment: 0.35,
    );
    await tester.pumpAndSettle();
    await tester.tap(rewardsEntry);
    await tester.pumpAndSettle();
    expect(find.text('奖励商店'), findsOneWidget);
    expect(find.text('兑换记录'), findsOneWidget);

    await tester.tap(find.text('周末亲子游戏 20 分钟').first);
    await tester.pumpAndSettle();
    expect(find.text('兑换说明'), findsOneWidget);
    expect(find.text('兑换奖励'), findsOneWidget);
  });

  testWidgets('profile tab opens formal secondary pages', (tester) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'mock_access_saved',
        authRefreshTokenKey: 'mock_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'mock_parent_13800002026',
        authPhoneKey: '13800002026',
      },
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();
    expect(find.text('家庭看护空间'), findsOneWidget);

    for (final entry in const [
      ['家庭成员', '家庭成员'],
      ['孩子资料', '孩子资料'],
      ['紧急联系人', '紧急联系人'],
      ['设备管理', '设备管理'],
      ['摄像头与看护状态', '摄像头与看护'],
      ['AI 看护规则', 'AI 看护规则'],
      ['通知与提醒', '通知与提醒'],
      ['隐私与权限', '隐私与权限'],
      ['对话与人设', '对话与人设'],
      ['学习内容', '学习内容'],
      ['今日报告', '今日报告'],
      ['周报', '周报'],
      ['成长时刻', '成长时刻'],
      ['个人信息', '个人信息'],
      ['账号安全', '账号安全'],
      ['订阅与套餐', '订阅与套餐'],
      ['关于', '关于'],
    ]) {
      await _openProfileEntry(tester, entry.first, expectedTitle: entry.last);
    }

    expect(find.text('安全区域'), findsNothing);
    expect(find.text('打卡审核'), findsNothing);
  });

  testWidgets('tasks screen adapts to common phone sizes', (tester) async {
    final now = DateTime.now();
    final preferences = {
      hasSeenOnboardingKey: true,
      hasCompletedInitialSetupKey: true,
      authAccessTokenKey: 'mock_access_saved',
      authRefreshTokenKey: 'mock_refresh_saved',
      authAccessTokenExpiresAtKey: now
          .add(const Duration(minutes: 15))
          .millisecondsSinceEpoch,
      authRefreshTokenExpiresAtKey: now
          .add(const Duration(days: 30))
          .millisecondsSinceEpoch,
      authUserIdKey: 'mock_parent_13800002026',
      authPhoneKey: '13800002026',
    };
    const sizes = [
      Size(320, 568),
      Size(390, 844),
      Size(430, 932),
      Size(360, 740),
      Size(412, 915),
    ];

    for (final size in sizes) {
      await _pumpApp(tester, preferences: preferences, logicalSize: size);
      await tester.pump(const Duration(milliseconds: 500));

      await tester.tap(find.text('任务').last);
      await tester.pumpAndSettle();

      expect(find.text('数学作业'), findsWidgets);
      expect(find.text('本周'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byIcon(Icons.add).first);
      await tester.pumpAndSettle();
      expect(find.text('添加孩子的新任务'), findsOneWidget);
      expect(find.text('保存并继续添加'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('学习任务').first);
      await tester.pumpAndSettle();
      expect(find.text('选择任务类型'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('生活习惯').last);
      await tester.pumpAndSettle();
      expect(find.text('习惯名称'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('task creation supports continue and day arrangement templates', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'mock_access_saved',
        authRefreshTokenKey: 'mock_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'mock_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      logicalSize: const Size(430, 932),
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(EditableText).at(1), '语文阅读');
    await tester.ensureVisible(find.text('保存并继续添加'));
    await tester.tap(find.text('保存并继续添加'));
    await tester.pumpAndSettle();

    expect(find.text('已添加，继续安排下一项'), findsOneWidget);
    expect(find.text('添加孩子的新任务'), findsOneWidget);

    await tester.ensureVisible(find.text('一天安排'));
    await tester.tap(find.text('一天安排'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('从模板添加'));
    await tester.pumpAndSettle();
    expect(find.text('选择一个常用安排'), findsOneWidget);

    await tester.tap(find.text('放学后学习'));
    await tester.pumpAndSettle();
    expect(find.text('保存一天安排'), findsOneWidget);
    expect(find.text('阅读'), findsWidgets);

    await tester.ensureVisible(find.text('保存一天安排'));
    await tester.tap(find.text('保存一天安排'));
    await tester.pumpAndSettle();

    expect(find.text('保存一天安排'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('product state views render on small and large phones', (
    tester,
  ) async {
    const sizes = [Size(320, 568), Size(430, 932)];

    for (final size in sizes) {
      await _pumpStateView(tester, logicalSize: size);
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('暂时连不上服务'), findsOneWidget);
      expect(find.text('重新连接'), findsOneWidget);
      expect(find.textContaining('后端'), findsNothing);
      expect(find.textContaining('API'), findsNothing);
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('product state views respect reduced motion', (tester) async {
    await _pumpStateView(
      tester,
      logicalSize: const Size(320, 568),
      disableAnimations: true,
    );
    await tester.pump();

    expect(find.text('暂时连不上服务'), findsOneWidget);
    expect(find.text('重新连接'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

Future<void> _loginSuccessfully(WidgetTester tester) async {
  await tester.enterText(find.byType(EditableText).at(0), '13800002026');
  await tester.tap(find.text('获取验证码'));
  await tester.pump(const Duration(milliseconds: 250));

  expect(find.text('验证码已发送，稍后可重新获取。'), findsOneWidget);
  expect(find.text('59 秒'), findsOneWidget);
  final codeField = tester.widget<EditableText>(
    find.byType(EditableText).at(1),
  );
  expect(codeField.focusNode.hasFocus, isTrue);

  await tester.tap(find.textContaining('我已阅读并同意'));
  await tester.pump(const Duration(milliseconds: 250));
  await tester.enterText(find.byType(EditableText).at(1), '123456');
  await tester.tap(find.text('继续'));
  await tester.pump(const Duration(milliseconds: 120));
  expect(find.text('正在确认'), findsOneWidget);

  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
}

Future<void> _openProfileEntry(
  WidgetTester tester,
  String label, {
  required String expectedTitle,
}) async {
  final entry = find.text(label).last;
  await tester.scrollUntilVisible(entry, 420);
  await tester.ensureVisible(entry);
  await tester.pumpAndSettle();
  await tester.tap(entry);
  await tester.pumpAndSettle();
  expect(find.text(expectedTitle), findsWidgets);
  expect(find.textContaining('backend'), findsNothing);
  expect(find.textContaining('API'), findsNothing);
  await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
  await tester.pumpAndSettle();
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required Map<String, Object> preferences,
  Size logicalSize = const Size(393, 852),
  double devicePixelRatio = 3,
}) async {
  tester.view
    ..physicalSize = logicalSize * devicePixelRatio
    ..devicePixelRatio = devicePixelRatio;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  SharedPreferences.setMockInitialValues(preferences);
  final sharedPreferences = await SharedPreferences.getInstance();

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        appEnvironmentProvider.overrideWithValue(AppEnvironment.mock()),
        sharedPreferencesProvider.overrideWithValue(sharedPreferences),
      ],
      child: const MiraGuardianApp(),
    ),
  );
}

Future<void> _pumpStateView(
  WidgetTester tester, {
  required Size logicalSize,
  double devicePixelRatio = 3,
  bool disableAnimations = false,
}) async {
  tester.view
    ..physicalSize = logicalSize * devicePixelRatio
    ..devicePixelRatio = devicePixelRatio;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  await tester.pumpWidget(
    MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(
          size: logicalSize,
          devicePixelRatio: devicePixelRatio,
          disableAnimations: disableAnimations,
        ),
        child: const Scaffold(
          body: SafeArea(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: MiraStateView(
                variant: MiraStateVariant.serviceUnavailable,
                title: '暂时连不上服务',
                message: '可能是网络不稳定，或者服务正在重启。你可以稍后再试。',
                primaryActionLabel: '重新连接',
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
