import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/app/app.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/storage/auth_session_store.dart';
import 'package:mira_guardian_app/src/core/storage/onboarding_store.dart';
import 'package:mira_guardian_app/src/core/storage/setup_store.dart';
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

    expect(find.text('绑定 Mira 设备'), findsOneWidget);
    await tester.tap(find.text('配置 Wi-Fi'));
    await tester.pumpAndSettle();

    expect(find.text('Wi-Fi 配网'), findsOneWidget);
    await tester.tap(find.text('开始绑定'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(find.text('设备绑定成功'), findsOneWidget);
    await tester.tap(find.text('创建孩子资料'));
    await tester.pumpAndSettle();

    expect(find.text('孩子资料'), findsOneWidget);
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
    expect(find.text('今日任务'), findsOneWidget);

    await tester.tap(find.text('数学作业').last);
    await tester.pumpAndSettle();
    expect(find.text('AI 判断建议'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();

    await tester.tap(find.text('看护').last);
    await tester.pumpAndSettle();
    expect(find.text('实时看护'), findsOneWidget);

    await tester.tap(find.text('告警').last);
    await tester.pumpAndSettle();
    expect(find.text('告警列表'), findsOneWidget);

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();
    expect(find.text('家庭管理'), findsOneWidget);
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
  await tester.enterText(find.byType(EditableText).at(1), '0426');
  await tester.tap(find.text('继续'));
  await tester.pump(const Duration(milliseconds: 120));
  expect(find.text('正在确认'), findsOneWidget);

  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required Map<String, Object> preferences,
}) async {
  tester.view
    ..physicalSize = const Size(1179, 2556)
    ..devicePixelRatio = 3;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  SharedPreferences.setMockInitialValues(preferences);
  final sharedPreferences = await SharedPreferences.getInstance();

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        appEnvironmentProvider.overrideWithValue(AppEnvironment.development()),
        sharedPreferencesProvider.overrideWithValue(sharedPreferences),
      ],
      child: const MiraGuardianApp(),
    ),
  );
}
