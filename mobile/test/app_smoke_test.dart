import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/app/app.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/core/storage/auth_session_store.dart';
import 'package:guardian_parent_app/src/core/storage/onboarding_store.dart';
import 'package:guardian_parent_app/src/core/storage/setup_store.dart';
import 'package:guardian_parent_app/src/features/devices/application/camera_discovery_adapter.dart';
import 'package:guardian_parent_app/src/features/devices/application/selected_device_controller.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';
import 'package:guardian_parent_app/src/features/live_care/presentation/live_care_screen.dart';
import 'package:guardian_parent_app/src/features/setup/application/setup_repository.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

Map<String, dynamic>? _lastSetupChildBody;
Map<String, dynamic>? _lastBoundDeviceBody;
int _cameraHealthRequestCount = 0;
int _cameraStatusRequestCount = 0;
int _cameraSnapshotRequestCount = 0;

void main() {
  test('legacy setup device steps do not force legacy setup pages', () {
    expect(
      _setupStatusForRoute(
        parentIdentity: 'done',
        childProfile: 'pending',
        nextStep: 'device',
      ).routePath,
      setupChildProfilePath,
    );
    expect(
      _setupStatusForRoute(
        parentIdentity: 'done',
        childProfile: 'done',
        nextStep: 'wifi',
      ).routePath,
      AppRoute.home.path,
    );
    expect(
      _setupStatusForRoute(
        parentIdentity: 'done',
        childProfile: 'done',
        nextStep: 'cameraName',
      ).routePath,
      AppRoute.home.path,
    );
    expect(
      _setupStatusForRoute(
        parentIdentity: 'done',
        childProfile: 'done',
        nextStep: 'emergencyContacts',
      ).routePath,
      AppRoute.home.path,
    );
  });

  testWidgets('renders the welcome onboarding slides', (tester) async {
    await _pumpApp(tester, preferences: const {});
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('家庭看护'), findsOneWidget);
    expect(find.text('少盯一点，也能知道孩子现在怎么样。'), findsOneWidget);
    expect(find.text('继续'), findsOneWidget);
    expect(find.text('登录或创建家庭'), findsOneWidget);

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('隐私边界'), findsOneWidget);
    expect(find.text('摄像头看到的内容，不会被长期保留。'), findsOneWidget);

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('家庭空间'), findsOneWidget);
    expect(find.text('看护要有科技感，也要有家的温度。'), findsOneWidget);
    expect(find.text('开始设置'), findsOneWidget);

    await tester.tap(find.text('开始设置'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('登录暖瞳'), findsOneWidget);
    expect(find.text('手机号'), findsOneWidget);
  });

  testWidgets('welcome onboarding fits compact Android phones', (tester) async {
    await _pumpApp(
      tester,
      preferences: const {},
      logicalSize: const Size(360, 720),
      devicePixelRatio: 3,
    );
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('继续'), findsOneWidget);
    expect(find.text('登录或创建家庭'), findsOneWidget);
    expect(tester.getTopLeft(find.text('继续')).dy, greaterThan(580));
    expect(
      tester.getBottomLeft(find.text('登录或创建家庭')).dy,
      inInclusiveRange(680, 720),
    );
  });

  testWidgets('skips onboarding after it has been seen', (tester) async {
    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('登录暖瞳'), findsOneWidget);
    expect(find.text('少盯一点，也能知道孩子现在怎么样。'), findsNothing);
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
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('登录暖瞳'), findsNothing);
    expect(find.text('今日节奏'), findsOneWidget);
    expect(find.text('当前没有需要你处理的事'), findsNothing);
    expect(
      tester.getSize(find.byKey(const ValueKey('bottomNavAddAction'))),
      const Size(44, 44),
    );
  });

  testWidgets('completed setup can enter home without a camera', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: false,
    );
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text('登录暖瞳'), findsNothing);
    expect(find.text('还没有连接摄像头'), findsWidgets);
    expect(find.text('摄像头还没连接'), findsOneWidget);
    expect(find.text('连接'), findsOneWidget);
    expect(find.text('连接第一台看护摄像头'), findsNothing);
  });

  testWidgets(
    'empty home without tasks or camera has one gentle camera entry',
    (tester) async {
      final now = DateTime.now();
      await _pumpApp(
        tester,
        preferences: {
          hasSeenOnboardingKey: true,
          hasCompletedInitialSetupKey: true,
          authAccessTokenKey: 'test_access_saved',
          authRefreshTokenKey: 'test_refresh_saved',
          authAccessTokenExpiresAtKey: now
              .add(const Duration(minutes: 15))
              .millisecondsSinceEpoch,
          authRefreshTokenExpiresAtKey: now
              .add(const Duration(days: 30))
              .millisecondsSinceEpoch,
          authUserIdKey: 'test_parent_13800002026',
          authPhoneKey: '13800002026',
        },
        hasDevice: false,
        seedTasks: false,
      );
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.text('今日安排'), findsOneWidget);
      expect(find.text('今天还没有安排'), findsOneWidget);
      expect(find.text('添加安排'), findsOneWidget);
      expect(find.text('选个模板'), findsOneWidget);
      expect(find.text('连接看护摄像头'), findsOneWidget);
      expect(find.text('查看全部'), findsNothing);
      expect(find.text('连接第一台看护摄像头'), findsNothing);
      expect(find.text('还没有连接看护摄像头'), findsNothing);
      expect(find.text('需要你处理'), findsNothing);
      expect(find.text('当前没有需要你处理的事'), findsNothing);
    },
  );

  testWidgets('empty home template action opens day arrangement sheet', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: false,
      seedTasks: false,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('选个模板'));
    await tester.pumpAndSettle();

    expect(find.text('选择一天安排'), findsOneWidget);
    expect(find.text('上学日晨间'), findsWidgets);

    await tester.tap(find.bySemanticsLabel('关闭').last);
    await tester.pumpAndSettle();
    expect(find.text('选择一天安排'), findsNothing);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('选择一天安排'), findsNothing);
  });

  testWidgets('task tab opens tasks without automatically showing templates', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: false,
      seedTasks: false,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();

    expect(find.text('选择一天安排'), findsNothing);
    expect(find.text('本周还没有安排'), findsOneWidget);
  });

  testWidgets('tasks can be created without a camera', (tester) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: false,
      seedTasks: false,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(EditableText).first, '喝水休息');
    await tester.ensureVisible(find.text('保存并继续添加'));
    await tester.tap(find.text('保存并继续添加'));
    await tester.pumpAndSettle();

    expect(find.text('已添加，继续安排下一项'), findsOneWidget);
    expect(find.text('请先连接摄像头'), findsNothing);
  });

  testWidgets('task detail without camera shows record-only state', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: false,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('户外活动').first);
    await tester.tap(find.text('户外活动').first);
    await tester.pumpAndSettle();

    expect(find.text('当前只记录安排'), findsOneWidget);
    expect(find.text('未连接摄像头，连接后可使用语音提醒和看护记录。'), findsOneWidget);
    expect(find.textContaining('摄像头观察中'), findsNothing);
    expect(find.textContaining('摄像头提醒中'), findsNothing);
  });

  testWidgets(
    'empty home with camera keeps plan empty state without camera CTA',
    (tester) async {
      final now = DateTime.now();
      await _pumpApp(
        tester,
        preferences: {
          hasSeenOnboardingKey: true,
          hasCompletedInitialSetupKey: true,
          authAccessTokenKey: 'test_access_saved',
          authRefreshTokenKey: 'test_refresh_saved',
          authAccessTokenExpiresAtKey: now
              .add(const Duration(minutes: 15))
              .millisecondsSinceEpoch,
          authRefreshTokenExpiresAtKey: now
              .add(const Duration(days: 30))
              .millisecondsSinceEpoch,
          authUserIdKey: 'test_parent_13800002026',
          authPhoneKey: '13800002026',
        },
        hasDevice: true,
        seedTasks: false,
      );
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.text('今日安排'), findsOneWidget);
      expect(find.text('今天还没有安排'), findsOneWidget);
      expect(find.text('添加安排'), findsOneWidget);
      expect(find.text('选个模板'), findsOneWidget);
      expect(find.text('连接看护摄像头'), findsNothing);
      expect(find.text('查看全部'), findsNothing);
    },
  );

  testWidgets('camera management is a direct profile entry without care rows', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();
    expect(find.text('摄像头管理'), findsOneWidget);
    expect(find.text('设备与看护'), findsNothing);

    await tester.tap(find.text('摄像头管理'));
    await tester.pumpAndSettle();

    expect(find.text('摄像头管理'), findsWidgets);
    expect(find.text('当前看护设备'), findsNothing);
    expect(find.text('看护能力'), findsNothing);
    expect(find.text('作息时间'), findsNothing);
    expect(find.text('默认 · 当前'), findsOneWidget);
    expect(find.byTooltip('添加摄像头'), findsOneWidget);
    expect(find.textContaining('mock'), findsNothing);
    expect(find.textContaining('runtime'), findsNothing);
    expect(find.textContaining('provider'), findsNothing);
    expect(find.textContaining('bindingCode'), findsNothing);
  });

  testWidgets('live care shows no-camera connection state', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [selectedDeviceProvider.overrideWith((ref) async => null)],
        child: const MaterialApp(home: LiveCareScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('还没有连接摄像头'), findsOneWidget);
    expect(find.text('连接看护摄像头'), findsOneWidget);
  });

  testWidgets('live care online hero shows camera status once', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          selectedDeviceProvider.overrideWith((ref) async => _liveCareDevice()),
          liveCareStatusProvider.overrideWith(
            (ref) async => _onlineLiveCareStatus(),
          ),
          cameraSnapshotProvider.overrideWith(
            (ref) async => CameraSnapshotFrame.unavailable,
          ),
          cameraEventsProvider.overrideWith((ref) async => const []),
        ],
        child: const MaterialApp(home: LiveCareScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('摄像头在线'), findsOneWidget);
  });

  testWidgets('login after logout refreshes profile for the new account', (
    tester,
  ) async {
    await _pumpApp(
      tester,
      preferences: const {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
      },
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester, phone: '13500008291');
    await _openProfileTab(tester);
    expect(find.text('妈妈 · 135 **** 8291'), findsOneWidget);

    await tester.scrollUntilVisible(find.text('退出登录'), 420);
    await tester.drag(find.byType(Scrollable).last, const Offset(0, -120));
    await tester.pumpAndSettle();
    await tester.tap(find.text('退出登录'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('退出'));
    await tester.pumpAndSettle();

    expect(find.text('登录暖瞳'), findsOneWidget);

    await _loginSuccessfully(tester, phone: '13860439696');
    await _openProfileTab(tester);

    expect(find.text('爸爸 · 138 **** 9696'), findsOneWidget);
    expect(find.text('妈妈 · 135 **** 8291'), findsNothing);
  });

  testWidgets('runs login then first setup flow into home', (tester) async {
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

    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester);

    expect(find.text('确认家长身份'), findsOneWidget);
    expect(find.text('1 / 2'), findsOneWidget);
    expect(find.text('3 / 2'), findsNothing);
    expect(find.byKey(const ValueKey('familyRoleSegment_admin')), findsNothing);
    await tester.tap(find.text('继续填写孩子资料'));
    await tester.pumpAndSettle();

    expect(find.text('孩子资料'), findsOneWidget);
    expect(find.text('2 / 2'), findsOneWidget);
    expect(find.text('3 / 2'), findsNothing);
    expect(find.text('就读阶段'), findsNothing);
    expect(find.text('幼儿园'), findsNothing);
    expect(find.text('幼儿园班级'), findsOneWidget);
    expect(find.text('小班'), findsOneWidget);
    expect(find.text('中班'), findsOneWidget);
    expect(find.text('大班'), findsOneWidget);
    expect(find.text('入睡时间'), findsNothing);
    expect(find.text('学校'), findsNothing);
    expect(find.text('兴趣'), findsNothing);
    expect(find.text('小学'), findsNothing);
    expect(find.text('初中'), findsNothing);
    await tester.enterText(find.byType(EditableText).at(0), '小宇');
    await tester.pump();
    await tester.tap(find.text('完成设置'));
    await tester.pump();
    expect(find.text('请选择孩子生日'), findsOneWidget);
    expect(_lastSetupChildBody, isNull);

    await _tapBirthdayField(tester);
    await tester.pumpAndSettle();
    expect(find.text('2021-06-01'), findsOneWidget);
    expect(find.text('已推荐班级'), findsOneWidget);
    expect(find.text('推荐 中班，可手动调整。'), findsOneWidget);

    await tester.tap(find.text('完成设置'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();

    expect(find.text('还没有连接摄像头'), findsWidgets);
    expect(_lastSetupChildBody?['educationStage'], '幼儿园');
    expect(_lastSetupChildBody?['ageStage'], '幼儿园 中班');
    expect(_lastSetupChildBody?['grade'], '中班');
    expect(find.text('连接第一台看护摄像头'), findsNothing);
    expect(find.text('摄像头还没连接'), findsOneWidget);
    expect(find.text('今日节奏'), findsOneWidget);
    expect(find.text('\u7c73\u62c9怎么说'), findsNothing);
    expect(find.textContaining('bindingCode'), findsNothing);
    expect(find.textContaining('mock'), findsNothing);

    showAddCameraSheet(tester.element(find.text('摄像头还没连接')));
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();

    expect(find.text('添加摄像头'), findsNothing);
    final cameraSheetIsOpen =
        find.text('正在搜索附近摄像头').evaluate().isNotEmpty ||
        find.text('发现附近摄像头').evaluate().isNotEmpty;
    expect(cameraSheetIsOpen, isTrue);
    expect(find.text('查看帮助'), findsNothing);
    expect(find.text('开始发现'), findsNothing);
    expect(find.text('继续发现'), findsNothing);

    await tester.pump(const Duration(milliseconds: 1900));
    await tester.pump();

    expect(find.text('发现附近摄像头'), findsOneWidget);
    expect(find.text('儿童房摄像头'), findsOneWidget);
    expect(find.text('客厅摄像头'), findsOneWidget);
    expect(find.text('餐厅摄像头'), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey('discoveredCamera_nearby-living-room')),
    );
    await tester.pump();
    expect(find.text('连接'), findsWidgets);
    await tester.tap(find.text('连接').last);
    await tester.pumpAndSettle();

    expect(find.text('摄像头已连接'), findsWidgets);
    expect(find.text('实时看护已准备好'), findsWidgets);
    expect(_lastBoundDeviceBody?['name'], '客厅摄像头');
    expect(_lastBoundDeviceBody?['bindingCode'], contains('LIVING'));
    expect(_cameraHealthRequestCount, greaterThan(0));
    expect(_cameraStatusRequestCount, greaterThan(0));
    expect(_cameraSnapshotRequestCount, greaterThan(0));
  });

  testWidgets('shows login validation errors from continue', (tester) async {
    await _pumpApp(tester, preferences: const {hasSeenOnboardingKey: true});
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('继续'));
    await tester.pump(const Duration(milliseconds: 250));

    expect(find.text('请填写手机号'), findsOneWidget);
    expect(find.text('请输入验证码'), findsWidgets);
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

    expect(find.text('登录暖瞳'), findsOneWidget);

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
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester);

    expect(find.text('今日节奏'), findsOneWidget);
    expect(find.text('当前没有需要你处理的事'), findsNothing);

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    expect(find.text('户外活动'), findsWidgets);
    expect(find.text('+0 分'), findsNothing);

    await tester.tap(find.text('户外活动').last);
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
    expect(find.text('最近记录'), findsOneWidget);
    expect(find.textContaining('还没看到孩子开始'), findsWidgets);
    expect(find.textContaining('任务事件'), findsNothing);
    expect(find.textContaining('已执行'), findsNothing);
    expect(find.textContaining('开始观察'), findsNothing);

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();
    expect(find.text('家庭看护空间'), findsOneWidget);
    expect(find.text('家庭成员'), findsWidgets);
    expect(find.text('家庭与成员'), findsOneWidget);
    expect(find.text('摄像头管理'), findsOneWidget);
    expect(find.text('设备与看护'), findsNothing);
    expect(find.text('紧急联系人'), findsNothing);
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
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await _loginSuccessfully(tester);

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('睡前绘本').last);
    await tester.tap(find.text('睡前绘本').last);
    await tester.pumpAndSettle();

    expect(find.text('等待你确认'), findsOneWidget);
    expect(find.text('确认完成'), findsOneWidget);
    expect(find.text('驳回'), findsOneWidget);

    await tester.tap(find.text('驳回'));
    await tester.pumpAndSettle();

    expect(find.text('驳回完成确认'), findsOneWidget);
    expect(find.text('确认驳回'), findsOneWidget);

    await tester.tap(find.text('确认驳回'));
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
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();

    await _scrollProfileToTop(tester);
    await tester.tap(find.byKey(const ValueKey('profileHeroPointsEntry')));
    await tester.pumpAndSettle();
    expect(find.text('补发或更正积分'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('积分流水'), 420);
    expect(find.text('积分流水'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.card_giftcard_outlined));
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
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();
    expect(find.text('家庭看护空间'), findsOneWidget);

    await tester.tap(find.text('家庭看护空间').first);
    await tester.pumpAndSettle();
    expect(find.text('个人信息'), findsOneWidget);
    expect(find.text('身份已确认'), findsNothing);
    expect(find.text('显示称呼'), findsNothing);
    expect(find.text('手机号'), findsWidgets);
    expect(find.text('更换'), findsOneWidget);
    await tester.tap(find.text('更换'));
    await tester.pumpAndSettle();
    expect(find.text('更换手机号'), findsOneWidget);
    expect(find.text('当前手机号'), findsOneWidget);
    await tester.tap(find.text('取消').last);
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('accountIdentityGroupSelect')),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('accountDisplayNameCards')), findsNothing);
    await tester.tap(find.text('保存'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();
    expect(find.text('家庭看护空间'), findsOneWidget);

    final familyMembersEntry = find.text('家庭成员').last;
    await tester.scrollUntilVisible(familyMembersEntry, 420);
    await tester.ensureVisible(familyMembersEntry);
    await tester.pumpAndSettle();
    await tester.tap(familyMembersEntry);
    await tester.pumpAndSettle();
    expect(find.text('家庭成员'), findsWidgets);
    expect(find.text('妈妈'), findsWidgets);
    expect(find.text('家长'), findsNothing);
    await tester.tap(find.byIcon(Icons.person_add_outlined));
    await tester.pumpAndSettle();
    expect(find.text('邀请家庭成员'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('memberIdentityGroupSelect')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('memberDisplayNameCards')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('memberDisplayNameCard_妈妈')),
      findsOneWidget,
    );
    expect(find.text('家庭身份'), findsOneWidget);
    expect(find.text('显示称呼'), findsOneWidget);
    expect(find.text('权限角色'), findsOneWidget);
    await tester.tap(find.text('取消').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();

    await _openProfileEntry(
      tester,
      '孩子资料',
      expectedTitle: '孩子资料',
      expectedTexts: const ['孩子称呼', '性别', '出生日期', '幼儿园班级'],
      absentTexts: const ['入睡时间', '学校', '兴趣', '就读阶段'],
    );

    final familyHubEntry = find.text('家庭与成员').last;
    await tester.scrollUntilVisible(familyHubEntry, 420);
    await tester.ensureVisible(familyHubEntry);
    await tester.pumpAndSettle();
    await tester.tap(familyHubEntry);
    await tester.pumpAndSettle();
    expect(find.text('紧急联系人'), findsOneWidget);
    final emergencyEntry = find.text('紧急联系人').last;
    await tester.scrollUntilVisible(emergencyEntry, 420);
    await tester.ensureVisible(emergencyEntry);
    await tester.pumpAndSettle();
    await tester.tap(emergencyEntry);
    await tester.pumpAndSettle();
    await tester.tap(find.text('编辑').first);
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('contactIdentityGroupSelect')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('contactDisplayNameCards')),
      findsOneWidget,
    );
    expect(find.text('家庭身份'), findsOneWidget);
    expect(find.text('显示称呼'), findsOneWidget);
    expect(find.text('guardian'), findsNothing);
    await tester.tap(find.text('取消').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();

    await _openProfileEntry(tester, '摄像头管理', expectedTitle: '摄像头管理');
    await _openProfileEntry(tester, 'AI 规则与提醒', expectedTitle: 'AI 规则与提醒');
    await _openProfileEntry(
      tester,
      '看护报告',
      expectedTitle: '看护报告',
      expectedTexts: const ['今日报告', '周报', '成长时刻'],
    );
    await _openProfileEntry(
      tester,
      '账号安全',
      expectedTitle: '账号安全',
      expectedTexts: const ['账号保护中', '登录设备', '本机 iPhone', '注销账号'],
      absentTexts: const ['编辑个人信息', '账号与安全'],
    );
    await _openProfileEntry(tester, '关于', expectedTitle: '关于我们');

    await _openProfileSubscription(tester);
    await _openProfileNestedEntry(
      tester,
      'AI 规则与提醒',
      '语音与称呼',
      expectedTitle: '语音与称呼',
    );
    await _openProfileNestedEntry(
      tester,
      'AI 规则与提醒',
      '看护能力',
      expectedTitle: '看护能力',
      expectedTexts: const [
        '坐姿提醒',
        '玩具收纳',
        '用餐开始提醒',
        '用餐习惯提醒',
        '午睡提醒',
        '晚上入睡提醒',
        '起床提醒',
      ],
      absentTexts: const ['更多提醒能力', '转场提醒', '已开启', '已关闭'],
    );
    await _openProfileNestedEntry(
      tester,
      'AI 规则与提醒',
      '作息时间',
      expectedTitle: '作息节奏',
      expectedTexts: const ['上学日', '周末', '起床', '早餐', '午睡', '晚上睡觉'],
      absentTexts: const ['假期作息', '后续可按假期单独调整。'],
    );
    await _openProfileNestedEntry(
      tester,
      'AI 规则与提醒',
      '通知与提醒',
      expectedTitle: '通知与提醒',
    );
    expect(find.text('安全区域'), findsNothing);
    expect(find.text('打卡审核'), findsNothing);
  });

  testWidgets('care capabilities remain configurable before camera binding', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      hasDevice: false,
      seedTasks: false,
    );
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.text('我的').last);
    await tester.pumpAndSettle();

    await _openProfileNestedEntry(
      tester,
      'AI 规则与提醒',
      '看护能力',
      expectedTitle: '看护能力',
      expectedTexts: const [
        '未连接摄像头',
        '坐姿提醒',
        '玩具收纳',
        '用餐开始提醒',
        '用餐习惯提醒',
        '午睡提醒',
        '晚上入睡提醒',
        '起床提醒',
      ],
      absentTexts: const ['还没有可用摄像头', '更多提醒能力', '后续开放'],
    );
  });

  testWidgets('tasks screen adapts to common phone sizes', (tester) async {
    final now = DateTime.now();
    final preferences = {
      hasSeenOnboardingKey: true,
      hasCompletedInitialSetupKey: true,
      authAccessTokenKey: 'test_access_saved',
      authRefreshTokenKey: 'test_refresh_saved',
      authAccessTokenExpiresAtKey: now
          .add(const Duration(minutes: 15))
          .millisecondsSinceEpoch,
      authRefreshTokenExpiresAtKey: now
          .add(const Duration(days: 30))
          .millisecondsSinceEpoch,
      authUserIdKey: 'test_parent_13800002026',
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
      await _pumpApp(
        tester,
        preferences: preferences,
        logicalSize: size,
        hasDevice: true,
      );
      await tester.pump(const Duration(milliseconds: 500));

      await tester.tap(find.text('任务').last);
      await tester.pumpAndSettle();

      expect(find.text('户外活动'), findsWidgets);
      expect(find.text('本周'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.byIcon(Icons.add).first);
      await tester.pumpAndSettle();
      expect(find.text('添加生活提醒'), findsOneWidget);
      expect(find.text('生活习惯'), findsOneWidget);
      expect(find.text('学习任务'), findsNothing);
      expect(find.text('保存并继续添加'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('生活习惯').first);
      await tester.pumpAndSettle();
      expect(find.text('选择提醒类型'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.ensureVisible(find.text('运动/户外').last);
      await tester.tap(find.text('运动/户外').last);
      await tester.pumpAndSettle();
      expect(find.text('活动内容'), findsOneWidget);
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
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      logicalSize: const Size(430, 932),
      hasDevice: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(EditableText).first, '喝水休息');
    await tester.ensureVisible(find.text('保存并继续添加'));
    await tester.tap(find.text('保存并继续添加'));
    await tester.pumpAndSettle();

    expect(find.text('已添加，继续安排下一项'), findsOneWidget);
    expect(find.text('添加生活提醒'), findsOneWidget);

    await tester.ensureVisible(find.text('一天安排'));
    await tester.tap(find.text('一天安排'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('从模板添加'));
    await tester.pumpAndSettle();
    expect(find.text('选择一天安排'), findsOneWidget);
    expect(find.textContaining('套可选'), findsOneWidget);
    expect(find.text('上学日'), findsWidgets);
    expect(find.text('周末'), findsWidgets);

    expect(find.text('中班睡前准备'), findsNothing);
    await tester.ensureVisible(find.text('睡前准备'));
    await tester.tap(find.text('睡前准备'));
    await tester.pumpAndSettle();
    expect(find.text('保存一天安排'), findsOneWidget);
    expect(find.text('睡前阅读'), findsWidgets);

    await tester.ensureVisible(find.text('保存一天安排'));
    await tester.tap(find.text('保存一天安排'));
    await tester.pumpAndSettle();

    expect(find.text('保存一天安排'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('task template sheet shows backend error and retry', (
    tester,
  ) async {
    final now = DateTime.now();
    await _pumpApp(
      tester,
      preferences: {
        hasSeenOnboardingKey: true,
        hasCompletedInitialSetupKey: true,
        authAccessTokenKey: 'test_access_saved',
        authRefreshTokenKey: 'test_refresh_saved',
        authAccessTokenExpiresAtKey: now
            .add(const Duration(minutes: 15))
            .millisecondsSinceEpoch,
        authRefreshTokenExpiresAtKey: now
            .add(const Duration(days: 30))
            .millisecondsSinceEpoch,
        authUserIdKey: 'test_parent_13800002026',
        authPhoneKey: '13800002026',
      },
      logicalSize: const Size(430, 932),
      hasDevice: true,
      failTaskTemplates: true,
    );
    await tester.pump(const Duration(milliseconds: 500));

    await tester.tap(find.text('任务').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.add).first);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('一天安排'));
    await tester.tap(find.text('一天安排'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('从模板添加'));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('常用安排暂时没取到'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
    expect(find.textContaining('套可选'), findsNothing);
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

Future<void> _loginSuccessfully(
  WidgetTester tester, {
  String phone = '13800002026',
}) async {
  await tester.enterText(find.byType(EditableText).at(0), phone);
  await tester.tap(find.text('获取验证码'));
  await tester.pump(const Duration(milliseconds: 250));

  expect(find.text('验证码已发送，稍后可重新获取。'), findsOneWidget);
  expect(find.text('59 秒'), findsOneWidget);
  final codeField = tester.widget<EditableText>(
    find.byType(EditableText).at(1),
  );
  expect(codeField.controller.text, '123456');
  expect(codeField.focusNode.hasFocus, isTrue);

  await tester.tap(find.textContaining('我已阅读并同意'));
  await tester.pump(const Duration(milliseconds: 250));
  await tester.tap(find.text('继续'));
  await tester.pump(const Duration(milliseconds: 120));

  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
}

Future<void> _openProfileTab(WidgetTester tester) async {
  await tester.tap(find.text('我的').last);
  await tester.pumpAndSettle();
}

Future<void> _openProfileEntry(
  WidgetTester tester,
  String label, {
  required String expectedTitle,
  List<String> expectedTexts = const [],
  List<String> absentTexts = const [],
}) async {
  final entry = find.text(label).last;
  await tester.scrollUntilVisible(entry, 420);
  await tester.ensureVisible(entry);
  await tester.pumpAndSettle();
  await tester.tap(entry);
  await tester.pumpAndSettle();
  expect(find.text(expectedTitle), findsWidgets);
  for (final text in expectedTexts) {
    expect(find.text(text), findsWidgets);
  }
  for (final text in absentTexts) {
    expect(find.textContaining(text), findsNothing);
  }
  expect(find.textContaining('backend'), findsNothing);
  expect(find.textContaining('API'), findsNothing);
  await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
  await tester.pumpAndSettle();
}

Future<void> _scrollProfileToTop(WidgetTester tester) async {
  await tester.fling(
    find.byType(Scrollable).first,
    const Offset(0, 1200),
    3000,
  );
  await tester.pumpAndSettle();
}

Future<void> _openProfileSubscription(WidgetTester tester) async {
  await _scrollProfileToTop(tester);
  final entry = find.byKey(const ValueKey('profileHeroPlanEntry'));
  expect(entry, findsOneWidget);
  await tester.pumpAndSettle();
  await tester.tap(entry);
  await tester.pumpAndSettle();

  expect(find.text('让看护更完整'), findsOneWidget);
  expect(find.byKey(const ValueKey('subscriptionHeroImage')), findsOneWidget);
  await tester.ensureVisible(find.text('¥29').first);
  expect(find.text('¥29'), findsWidgets);
  expect(find.text('开通会员版'), findsOneWidget);
  await tester.tap(find.text('开通会员版'));
  await tester.pump(const Duration(milliseconds: 350));
  expect(find.textContaining('在线付款入口暂未开放'), findsOneWidget);
  Navigator.of(
    tester.element(find.textContaining('在线付款入口暂未开放')),
    rootNavigator: true,
  ).pop();
  await tester.pumpAndSettle();
  await tester.drag(find.byType(PageView).first, const Offset(-320, 0));
  await tester.pumpAndSettle();
  expect(find.text('¥59'), findsWidgets);
  await tester.ensureVisible(find.text('恢复购买'));
  expect(find.text('恢复购买'), findsOneWidget);
  expect(find.text('用户协议'), findsOneWidget);
  expect(find.text('隐私政策'), findsOneWidget);
  expect(find.text('儿童隐私授权说明'), findsOneWidget);
  await tester.tap(find.text('恢复购买'));
  await tester.pump(const Duration(milliseconds: 350));
  expect(find.textContaining('暂未找到可恢复的订阅记录'), findsOneWidget);
  Navigator.of(
    tester.element(find.textContaining('暂未找到可恢复的订阅记录')),
    rootNavigator: true,
  ).pop();
  await tester.pumpAndSettle();
  await tester.tap(find.text('用户协议'));
  await tester.pumpAndSettle();
  expect(find.text('用户协议'), findsWidgets);
  await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
  await tester.pumpAndSettle();
  await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
  await tester.pumpAndSettle();
}

Future<void> _openProfileNestedEntry(
  WidgetTester tester,
  String category,
  String label, {
  required String expectedTitle,
  List<String> expectedTexts = const [],
  List<String> absentTexts = const [],
}) async {
  final categoryEntry = find.text(category).last;
  await tester.scrollUntilVisible(categoryEntry, 420);
  await tester.ensureVisible(categoryEntry);
  await tester.pumpAndSettle();
  await tester.tap(categoryEntry);
  await tester.pumpAndSettle();
  expect(find.text(category), findsWidgets);

  final nested = find.text(label).last;
  await tester.scrollUntilVisible(nested, 420);
  await tester.ensureVisible(nested);
  await tester.pumpAndSettle();
  await tester.tap(nested);
  await tester.pumpAndSettle();
  expect(find.text(expectedTitle), findsWidgets);
  for (final text in expectedTexts) {
    expect(find.text(text), findsWidgets);
  }
  for (final text in absentTexts) {
    expect(find.text(text), findsNothing);
  }
  expect(find.textContaining('backend'), findsNothing);
  expect(find.textContaining('API'), findsNothing);
  await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
  await tester.pumpAndSettle();
  if (find.byIcon(Icons.arrow_back_ios_new).evaluate().isNotEmpty) {
    await tester.tap(find.byIcon(Icons.arrow_back_ios_new));
    await tester.pumpAndSettle();
  }
}

Future<void> _tapBirthdayField(WidgetTester tester) async {
  final field = find.byKey(const ValueKey('setupInput_出生日期'));
  await tester.ensureVisible(field);
  final rect = tester.getRect(field);
  await tester.tapAt(Offset(rect.left + 12, rect.center.dy));
}

Future<void> _pumpApp(
  WidgetTester tester, {
  required Map<String, Object> preferences,
  Size logicalSize = const Size(393, 852),
  double devicePixelRatio = 3,
  bool hasDevice = false,
  bool failTaskTemplates = false,
  bool seedTasks = true,
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
  final fakeApi = _FakeApiServer(
    completedSetup: preferences[hasCompletedInitialSetupKey] == true,
    hasDevice: hasDevice,
    failTaskTemplates: failTaskTemplates,
    seedTasks: seedTasks,
  );
  final fakeDio = fakeApi.dio;

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        appEnvironmentProvider.overrideWithValue(
          const AppEnvironment(flavor: AppFlavor.test, apiBaseUrl: ''),
        ),
        cameraDiscoveryConfigProvider.overrideWithValue(
          const CameraDiscoveryConfig(
            backend: CameraDiscoveryBackend.mock,
            allowBleFallbackToMock: false,
          ),
        ),
        rawDioProvider.overrideWithValue(fakeDio),
        dioProvider.overrideWithValue(fakeDio),
        sharedPreferencesProvider.overrideWithValue(sharedPreferences),
      ],
      child: const GuardianApp(),
    ),
  );
  await tester.pump(const Duration(milliseconds: 50));
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
              child: AppStateView(
                variant: AppStateVariant.serviceUnavailable,
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

GuardianDevice _liveCareDevice() {
  return const GuardianDevice(
    id: 'device_live_care',
    familyId: 'family_test',
    bindingCode: 'BIND-LIVE-CARE',
    name: '儿童房摄像头',
    wakeName: '小豆',
    location: '儿童房',
    status: 'online',
    isDefault: true,
    createdAt: 1,
    updatedAt: 1,
  );
}

LiveCareStatus _onlineLiveCareStatus() {
  return const LiveCareStatus(
    health: CameraHealth(
      ok: true,
      reachable: true,
      adapter: 'test',
      serviceLabel: '摄像头服务',
      message: '摄像头服务在线',
    ),
    runtime: CameraRuntime(
      ok: true,
      reachable: true,
      adapter: 'test',
      voiceState: 'idle',
      voiceRunning: false,
      message: '运行状态已同步',
    ),
    cameraStatus: CameraStatus(
      connectionStatus: 'online',
      streamAvailable: true,
      snapshotAvailable: true,
      speakerAvailable: true,
      monitorAvailable: true,
      ptzAvailable: false,
      lastSeenAt: 1,
      runtimeProvider: '',
      message: '摄像头在线，最新状态已同步。',
    ),
    monitorStatus: CameraMonitorStatus(
      running: true,
      status: 'running',
      message: '观察中',
      lastObservation: '',
      lastReminder: '',
    ),
  );
}

SetupStatus _setupStatusForRoute({
  required String parentIdentity,
  required String childProfile,
  required String nextStep,
}) {
  return SetupStatus(
    completed: false,
    parentIdentity: parentIdentity,
    deviceBinding: 'pending',
    wifi: 'pending',
    childProfile: childProfile,
    cameraName: 'pending',
    cameraNameIntro: 'pending',
    cameraNameIntroAt: null,
    contacts: 'pending',
    nextStep: nextStep,
    parentDisplayName: '',
    parentRelationship: '',
    parentRelationshipKey: '',
    deviceName: '',
    deviceLocation: '',
    wifiName: '',
    childName: '',
    childGender: '',
    childBirthday: '',
    childSleepTime: '',
    childEducationStage: '',
    childGrade: '',
    cameraWakeName: '',
  );
}

class _FakeApiServer {
  _FakeApiServer({
    required this._completedSetup,
    required this._hasDevice,
    this.failTaskTemplates = false,
    this.seedTasks = true,
  }) {
    _lastSetupChildBody = null;
    _lastBoundDeviceBody = null;
    _cameraHealthRequestCount = 0;
    _cameraStatusRequestCount = 0;
    _cameraSnapshotRequestCount = 0;
    if (seedTasks) {
      _tasks.addAll([
        _task(
          id: 'task_outdoor_play',
          title: '户外活动',
          description: '放学后户外走走，结束后喝水休息。',
          type: 'sports_outdoor',
          status: 'in_progress',
          scheduledStart: '17:20',
          scheduledEnd: '17:50',
          rewardPoints: 1,
        ),
        _task(
          id: 'task_bedtime_story',
          title: '睡前绘本',
          description: '睡前读一本绘本，完成后由家长确认。',
          type: 'reading_interest',
          status: 'awaiting_parent_confirmation',
          scheduledStart: '20:30',
          scheduledEnd: '20:50',
          rewardPoints: 2,
          evidenceSummary: '孩子已经完成睡前阅读，等待你确认。',
        ),
      ]);
    }
  }

  final bool _completedSetup;
  final bool failTaskTemplates;
  final bool seedTasks;
  bool _hasDevice;
  int _taskCounter = 0;
  String _relationship = '妈妈';
  String _relationshipKey = 'mom';
  String _phone = '13800002026';
  final List<Map<String, dynamic>> _tasks = [];

  late final Dio dio = _buildDio();

  Dio _buildDio() {
    final dio = Dio(BaseOptions(baseUrl: 'http://test.local/api'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final response = _handle(options);
          if ((response.statusCode ?? 200) >= 400) {
            handler.reject(
              DioException(
                requestOptions: options,
                response: response,
                type: DioExceptionType.badResponse,
              ),
            );
            return;
          }
          handler.resolve(response);
        },
      ),
    );
    return dio;
  }

  Response<dynamic> _handle(RequestOptions options) {
    final path = _normalizePath(options.path);
    final method = options.method.toUpperCase();
    final body = _body(options.data);
    final segments = path.split('/').where((item) => item.isNotEmpty).toList();

    if (method == 'POST' && path == '/auth/sms/request') {
      return _ok(options, {
        'ok': true,
        'codeSent': true,
        'debugCode': '123456',
        'message': '验证码已发送',
      });
    }
    if (method == 'POST' && path == '/auth/sms/login') {
      return _ok(options, _sessionPayload(_text(body['phone'], '13800002026')));
    }
    if (method == 'POST' && path == '/auth/token/refresh') {
      return _ok(options, _sessionPayload('13800002026'));
    }
    if (method == 'POST' && path == '/auth/logout') {
      return _ok(options, {'ok': true});
    }

    if (method == 'GET' && path == '/setup/status') {
      return _ok(options, _setupPayload());
    }
    if (method == 'POST' && path.startsWith('/setup/')) {
      if (path == '/setup/parent-identity') {
        _relationship = _text(body['relationship'], _relationship);
        _relationshipKey = _text(body['relationshipKey'], _relationshipKey);
      }
      if (path == '/setup/child') {
        _lastSetupChildBody = Map<String, dynamic>.from(body);
      }
      return _ok(options, _setupPayloadFor(path));
    }

    if (method == 'GET' && path == '/profile/summary') {
      return _ok(options, {'ok': true, 'summary': _profileSummary()});
    }
    if (method == 'GET' && path == '/profile/guardian-identity-options') {
      return _ok(options, {'ok': true, 'options': _identityOptions()});
    }
    if (method == 'GET' && path == '/family/members') {
      return _ok(options, {
        'ok': true,
        'members': [_familyMember()],
      });
    }
    if (method == 'GET' && path == '/family/invitations') {
      return _ok(options, {'ok': true, 'invitations': []});
    }
    if (method == 'POST' && path == '/family/invitations') {
      return _ok(options, {'ok': true, 'invitation': _familyInvitation(body)});
    }
    if (method == 'POST' && path.contains('/family/invitations/')) {
      return _ok(options, {'ok': true, 'invitation': _familyInvitation({})});
    }
    if ((method == 'POST' || method == 'PATCH') &&
        path.startsWith('/family/members')) {
      return _ok(options, {'ok': true, 'member': _familyMember(body)});
    }
    if (method == 'DELETE' && path.startsWith('/family/members/')) {
      return _ok(options, {'ok': true});
    }
    if (method == 'GET' && path == '/children/current') {
      return _ok(options, {'ok': true, 'child': _child()});
    }
    if (method == 'PATCH' && path.startsWith('/children/')) {
      return _ok(options, {'ok': true, 'child': _child(body)});
    }
    if (method == 'GET' && path == '/contacts/emergency') {
      return _ok(options, {
        'ok': true,
        'contacts': [_contact()],
      });
    }
    if ((method == 'POST' || method == 'PATCH') &&
        path.startsWith('/contacts/emergency')) {
      return _ok(options, {'ok': true, 'contact': _contact(body)});
    }
    if (method == 'DELETE' && path.startsWith('/contacts/emergency/')) {
      return _ok(options, {'ok': true});
    }
    if (method == 'GET' && path == '/account/profile') {
      return _ok(options, {'ok': true, 'profile': _accountProfile()});
    }
    if (method == 'PATCH' && path == '/account/profile') {
      _relationship = _text(body['relationship'], _relationship);
      _relationshipKey = _text(body['relationshipKey'], _relationshipKey);
      return _ok(options, {'ok': true, 'profile': _accountProfile()});
    }
    if (method == 'GET' && path == '/account/security') {
      return _ok(options, {'ok': true, 'security': _accountSecurity()});
    }
    if (method == 'POST' && path == '/account/phone/code') {
      return _ok(options, {
        'ok': true,
        'codeSent': true,
        'expiresAt': _now + 300000,
        'debugCode': '123456',
        'message': '验证码已发送',
      });
    }
    if (method == 'PATCH' && path == '/account/phone') {
      _phone = _text(body['phone'], _phone);
      return _ok(options, {
        'ok': true,
        'message': '手机号已更新',
        'profile': _accountProfile(),
        'security': _accountSecurity(),
      });
    }

    if (method == 'GET' &&
        segments.length == 2 &&
        segments.first == 'settings') {
      return _ok(options, {'ok': true, 'setting': _setting(segments[1])});
    }
    if (method == 'PATCH' &&
        segments.length == 2 &&
        segments.first == 'settings') {
      return _ok(options, {'ok': true, 'setting': _setting(segments[1], body)});
    }

    if (method == 'GET' && path == '/subscription/status') {
      return _ok(options, {'ok': true, 'subscription': _subscriptionStatus()});
    }
    if (method == 'GET' && path == '/subscriptions/plans') {
      return _ok(options, {'ok': true, 'plans': _subscriptionPlans()});
    }
    if (method == 'GET' && path == '/subscriptions/entitlements') {
      return _ok(options, {
        'ok': true,
        'entitlements': _subscriptionFeatures(),
      });
    }
    if (method == 'POST' && path == '/subscriptions/checkout-session') {
      return _ok(options, {
        'ok': true,
        'checkout': {
          'planId': _text(body['planId'], 'member'),
          'planTitle': '会员版',
          'status': 'pending_payment',
          'provider': 'app_store',
          'paymentRequired': true,
          'receiptVerificationRequired': true,
          'message': '在线付款入口暂未开放，当前可先查看套餐权益。',
        },
      });
    }
    if (method == 'POST' && path == '/subscriptions/restore') {
      return _ok(options, {
        'ok': true,
        'restore': {'status': 'no_purchase_record', 'message': '暂未找到可恢复的订阅记录。'},
      });
    }

    if (method == 'GET' && path == '/reports/daily') {
      return _ok(options, {'ok': true, 'report': _dailyReport()});
    }
    if (method == 'GET' && path == '/reports/weekly') {
      return _ok(options, {'ok': true, 'report': _weeklyReport()});
    }
    if (method == 'GET' && path == '/growth/moments') {
      return _ok(options, {'ok': true, 'moments': []});
    }
    if (method == 'GET' && segments.length == 2 && segments.first == 'legal') {
      return _ok(options, {
        'ok': true,
        'document': _legalDocument(segments[1]),
      });
    }
    if (method == 'GET' && path == '/app/about') {
      return _ok(options, {'ok': true, 'about': _about()});
    }
    if (method == 'POST' && path == '/feedback') {
      return _ok(options, {
        'ok': true,
        'feedback': {'status': 'received'},
      });
    }

    if (method == 'GET' && path == '/tasks/today') {
      final date = _text(options.queryParameters['date'], _today);
      return _ok(options, {
        'ok': true,
        'date': date,
        'tasks': _tasks.where((task) => task['scheduledDate'] == date).toList(),
      });
    }
    if (method == 'GET' && path == '/tasks/templates') {
      if (failTaskTemplates) {
        return _error(options, 503, 'templates_unavailable', '常用安排暂时没取到');
      }
      return _ok(options, _taskTemplatesResponse(options.queryParameters));
    }
    if (method == 'GET' && path == '/tasks') {
      return _ok(options, {'ok': true, 'tasks': _tasks});
    }
    if (method == 'POST' && path == '/tasks') {
      final task = _taskFromBody(body);
      _tasks.add(task);
      return _ok(options, {'ok': true, 'task': task});
    }
    if (method == 'POST' && path == '/tasks/batch') {
      final rawTasks = body['tasks'];
      final created = rawTasks is List
          ? rawTasks.map((item) => _taskFromBody(_body(item))).toList()
          : [_taskFromBody(body)];
      _tasks.addAll(created);
      return _ok(options, {'ok': true, 'tasks': created});
    }
    if (segments.length >= 2 && segments.first == 'tasks') {
      final taskId = segments[1];
      final task = _findTask(taskId);
      if (task == null) return _notFound(options);
      if (method == 'GET' && segments.length == 2) {
        return _ok(options, {'ok': true, 'task': task});
      }
      if (method == 'PATCH' && segments.length == 2) {
        task.addAll(body);
        return _ok(options, {'ok': true, 'task': task});
      }
      if (method == 'GET' && segments.length == 3 && segments[2] == 'events') {
        return _ok(options, {'ok': true, 'events': _taskEvents(task)});
      }
      if (method == 'POST' && segments.length == 3) {
        return _taskAction(options, task, segments[2], body);
      }
    }

    if (method == 'GET' && path == '/points/account') {
      return _ok(options, {'ok': true, 'account': _pointAccount()});
    }
    if (method == 'GET' && path == '/points/settings') {
      return _ok(options, {'ok': true, 'settings': _pointSettings()});
    }
    if (method == 'PATCH' && path == '/points/settings') {
      return _ok(options, {'ok': true, 'settings': _pointSettings(body)});
    }
    if (method == 'GET' && path == '/points/ledger') {
      return _ok(options, {'ok': true, 'ledger': _pointLedger()});
    }
    if (method == 'POST' && path == '/points/adjust') {
      return _ok(options, {'ok': true, 'account': _pointAccount()});
    }
    if (method == 'GET' && path == '/rewards/items') {
      return _ok(options, {'ok': true, 'items': _rewardItems()});
    }
    if (method == 'GET' &&
        segments.length == 3 &&
        segments[0] == 'rewards' &&
        segments[1] == 'items') {
      return _ok(options, {
        'ok': true,
        'item': _rewardItems().firstWhere((item) => item['id'] == segments[2]),
      });
    }
    if ((method == 'POST' || method == 'PATCH') &&
        path.startsWith('/rewards/items')) {
      return _ok(options, {'ok': true, 'item': _rewardItems().first});
    }
    if (method == 'DELETE' && path.startsWith('/rewards/items/')) {
      return _ok(options, {'ok': true});
    }
    if (method == 'GET' && path == '/rewards/redemptions') {
      return _ok(options, {'ok': true, 'redemptions': _redemptions()});
    }
    if (method == 'POST' && path.startsWith('/rewards/redemptions')) {
      return _ok(options, {'ok': true, 'redemption': _redemptions().first});
    }

    if (method == 'GET' && path == '/devices') {
      return _ok(options, {
        'ok': true,
        'devices': _hasDevice ? [_device()] : const [],
      });
    }
    if (method == 'POST' && path == '/devices') {
      _hasDevice = true;
      _lastBoundDeviceBody = Map<String, dynamic>.from(body);
      return _ok(options, {
        'ok': true,
        'duplicate': false,
        'device': _device(body),
        'defaultDevice': _device(),
      });
    }
    if (method == 'GET' && path == '/devices/default') {
      return _ok(options, {
        'ok': true,
        'device': _hasDevice ? _device() : null,
      });
    }
    if (method == 'POST' && path.endsWith('/set-default')) {
      return _ok(options, {'ok': true, 'device': _device()});
    }
    if (method == 'GET' &&
        segments.length == 2 &&
        segments.first == 'devices') {
      return _ok(options, {'ok': true, 'device': _device()});
    }
    if (method == 'GET' &&
        segments.length == 3 &&
        segments.first == 'devices' &&
        segments[2] == 'status') {
      return _ok(options, {'ok': true, 'status': _deviceStatus()});
    }
    if (method == 'PATCH' && path.startsWith('/devices/')) {
      return _ok(options, {'ok': true, 'device': _device(body)});
    }
    if (method == 'POST' && path.endsWith('/unbind')) {
      _hasDevice = false;
      return _ok(options, {
        'ok': true,
        'device': {..._device(), 'status': 'unbound', 'unboundAt': _now},
        'defaultDevice': null,
      });
    }

    if (method == 'GET' && path == '/camera/health') {
      _cameraHealthRequestCount += 1;
      return _ok(options, {
        'ok': true,
        'cameraRuntime': {'reachable': true},
      });
    }
    if (method == 'GET' && path == '/camera/runtime') {
      return _ok(options, {
        'ok': true,
        'cameraRuntime': {'reachable': true},
      });
    }
    if (method == 'GET' && path == '/camera/status') {
      _cameraStatusRequestCount += 1;
      return _ok(options, {'ok': true, 'status': _cameraStatus()});
    }
    if (method == 'GET' && path == '/camera/monitor/status') {
      return _ok(options, {'ok': true, 'monitor': _monitorStatus()});
    }
    if (method == 'POST' && path == '/camera/monitor/refresh') {
      return _ok(options, {'ok': true, 'monitor': _monitorStatus()});
    }
    if (method == 'GET' && path == '/camera/events') {
      return _ok(options, {'ok': true, 'events': _cameraEvents()});
    }
    if (method == 'GET' && path == '/camera/snapshot') {
      _cameraSnapshotRequestCount += 1;
      return _ok(options, <int>[0xff, 0xd8, 0xff, 0xd9]);
    }
    if (method == 'GET' && path == '/camera/webrtc/session') {
      return _ok(options, {
        'ok': true,
        'session': {'signalingUrl': '', 'stream': '', 'expiresAt': _now},
      });
    }
    if (method == 'POST' && path == '/camera/commands/speak') {
      return _ok(options, {'ok': true});
    }
    if (method == 'POST' && path == '/camera/commands/ptz') {
      return _ok(options, {
        'ok': true,
        'command': {
          'commandId': 'cmd_ptz',
          'commandType': 'ptz_move',
          'status': 'succeeded',
          'message': '操作已完成',
          'createdAt': _now,
          'updatedAt': _now,
        },
      });
    }
    if (method == 'GET' && path.startsWith('/firmware/devices/')) {
      return _ok(options, _firmwareStatus());
    }
    if (method == 'GET' && path == '/care/capabilities') {
      return _ok(options, {
        'ok': true,
        'childId': 'child_test',
        'capabilities': _careCapabilities(),
      });
    }
    if (method == 'GET' && path == '/care/routine-windows') {
      final dayType = _text(options.queryParameters['dayType'], 'school_day');
      return _ok(options, {
        'ok': true,
        'childId': 'child_test',
        'dayType': dayType,
        'windows': _routineWindows(dayType),
      });
    }
    if (method == 'PUT' && path == '/care/routine-windows') {
      final dayType = _text(options.queryParameters['dayType'], 'school_day');
      final rawWindows = body['windows'];
      return _ok(options, {
        'ok': true,
        'childId': 'child_test',
        'dayType': dayType,
        'windows': rawWindows is List ? rawWindows : _routineWindows(dayType),
      });
    }

    return _notFound(options);
  }

  Response<dynamic> _taskAction(
    RequestOptions options,
    Map<String, dynamic> task,
    String action,
    Map<String, dynamic> body,
  ) {
    if (action == 'start') {
      task['status'] = 'in_progress';
      task['startedAt'] = _now;
      return _ok(options, {'ok': true, 'task': task});
    }
    if (action == 'reminder') {
      return _ok(options, {
        'ok': true,
        'task': task,
        'reminder': {'phase': _text(body['phase'], 'manual'), 'text': '已提醒孩子'},
      });
    }
    if (action == 'complete') {
      final completionSource = _text(body['completionSource'], 'parent');
      task['completionSource'] = completionSource;
      task['status'] = completionSource == 'parent_manual'
          ? 'completed'
          : 'awaiting_parent_confirmation';
      task['completedAt'] = _now;
      task['evidenceSummary'] = _text(
        body['evidenceSummary'],
        '孩子已经完成任务，等待你确认。',
      );
      if (completionSource == 'parent_manual') {
        task['pointsGrantedAt'] = null;
      }
      return _ok(options, {'ok': true, 'task': task});
    }
    if (action == 'acknowledge-missed') {
      task['status'] = 'missed';
      task['parentActions'] = <Object>[];
      return _ok(options, {'ok': true, 'task': task});
    }
    if (action == 'parent-confirm') {
      task['status'] = 'confirmed';
      task['confirmedAt'] = _now;
      task['pointsGrantedAt'] = _now;
      return _ok(options, {'ok': true, 'task': task});
    }
    if (action == 'reject-confirmation') {
      task['status'] = 'rejected';
      task['rejectedAt'] = _now;
      task['rejectionReason'] = _text(body['reason'], '证据不足，未通过家长确认。');
      return _ok(options, {'ok': true, 'task': task});
    }
    return _notFound(options);
  }

  Map<String, dynamic> _setupPayloadFor(String path) {
    return switch (path) {
      '/setup/parent-identity' => _setupPayload(nextStep: 'child'),
      '/setup/device' => _setupPayload(
        parent: true,
        device: true,
        nextStep: 'child',
      ),
      '/setup/wifi' => _setupPayload(
        parent: true,
        device: true,
        nextStep: 'child',
      ),
      '/setup/child' => _setupPayload(
        parent: true,
        device: true,
        child: true,
        completed: true,
        nextStep: 'home',
      ),
      '/setup/camera-name/intro' => {
        ..._setupPayload(
          parent: true,
          device: true,
          wifi: true,
          child: true,
          nextStep: 'cameraName',
        ),
        'broadcast': {
          'played': false,
          'status': 'offline',
          'message': '摄像头暂时不在线，稍后可以再试听。',
        },
      },
      '/setup/camera-name/preview' => {
        ..._setupPayload(
          parent: true,
          device: true,
          wifi: true,
          child: true,
          nextStep: 'cameraName',
        ),
        'broadcast': {
          'played': false,
          'status': 'offline',
          'message': '摄像头暂时不在线，稍后可以再试听。',
        },
      },
      '/setup/camera-name' => _setupPayload(
        parent: true,
        device: true,
        wifi: true,
        child: true,
        cameraName: true,
        nextStep: 'contacts',
      ),
      '/setup/contacts' => _setupPayload(
        parent: true,
        device: true,
        wifi: true,
        child: true,
        cameraName: true,
        nextStep: 'complete',
      ),
      '/setup/complete' => _setupPayload(
        parent: true,
        device: true,
        wifi: true,
        child: true,
        cameraName: true,
        contacts: true,
        completed: true,
        nextStep: 'home',
      ),
      _ => _setupPayload(),
    };
  }

  Map<String, dynamic> _setupPayload({
    bool? completed,
    bool parent = false,
    bool device = false,
    bool wifi = false,
    bool child = false,
    bool cameraName = false,
    bool contacts = false,
    String? nextStep,
  }) {
    final done = completed ?? _completedSetup;
    return {
      'ok': true,
      'setup': {
        'completed': done,
        'parentIdentity': done || parent ? 'done' : 'pending',
        'deviceBinding': done || device ? 'done' : 'pending',
        'wifi': done || wifi ? 'done' : 'pending',
        'childProfile': done || child ? 'done' : 'pending',
        'cameraName': done || cameraName ? 'done' : 'pending',
        'cameraNameIntro': done || cameraName ? 'done' : 'pending',
        'cameraNameIntroAt': done || cameraName ? _now : null,
        'contacts': done || contacts ? 'done' : 'pending',
        'nextStep': done ? 'home' : (nextStep ?? 'parentIdentity'),
      },
      'parentIdentity': parent
          ? {
              'displayName': _relationship,
              'relationship': _relationship,
              'relationshipKey': _relationshipKey,
            }
          : null,
      'device': device
          ? {'id': 'device_test', 'name': '暖瞳摄像头', 'location': '儿童房'}
          : null,
      'wifi': wifi ? {'ssid': 'Home Wi-Fi 2.4G'} : null,
      'child': child
          ? {
              'id': 'child_test',
              'name': '小宇',
              'gender': 'unspecified',
              'educationStage': '幼儿园',
              'grade': '大班',
              'birthday': '',
            }
          : null,
      'cameraName': device || cameraName || done ? {'wakeName': '小豆'} : null,
    };
  }

  Map<String, dynamic> _sessionPayload(String phone) {
    _applyAccountPersona(phone);
    return {
      'ok': true,
      'tokens': {
        'accessToken': 'test_access_${phone}_$_now',
        'refreshToken': 'test_refresh_${phone}_$_now',
        'accessTokenExpiresAt': _now + 900000,
        'refreshTokenExpiresAt': _now + 2592000000,
      },
      'user': {'id': 'test_parent_$phone', 'phone': phone},
    };
  }

  Map<String, dynamic> _profileSummary() {
    return {
      'spaceTitle': '家庭看护空间',
      'familyId': 'family_test',
      'familyName': '林家的家庭空间',
      'displayName': _relationshipKey == 'dad' ? '林先生' : '林女士',
      'phone': _phone,
      'role': 'admin',
      'roleLabel': '管理员',
      'relationship': _relationship,
      'relationshipKey': _relationshipKey,
      'avatarPersona': _relationshipKey == 'dad' ? 'father' : 'mother',
      'capabilities': _adminCapabilities,
      'memberCount': 2,
      'deviceCount': _hasDevice ? 1 : 0,
      'pendingItemCount': _tasks
          .where((task) => task['status'] == 'awaiting_parent_confirmation')
          .length,
      'child': _child(),
    };
  }

  Map<String, dynamic> _child([Map<String, dynamic>? body]) {
    return {
      'id': 'child_test',
      'name': _text(body?['name'], '小宇'),
      'nickname': _text(body?['nickname'], '小宇'),
      'gender': _text(body?['gender'], 'unspecified'),
      'birthday': _text(body?['birthday'], '2020-06-01'),
      'sleepTime': _text(body?['sleepTime'], '21:00'),
      'ageStage': _text(body?['ageStage'], 'kindergarten'),
      'educationStage': _text(body?['educationStage'], '幼儿园'),
      'grade': _text(body?['grade'], '中班'),
      'schoolName': _text(body?['schoolName'], ''),
      'interests': body?['interests'] ?? ['绘本', '运动'],
      'taskPreferences': body?['taskPreferences'] ?? {},
    };
  }

  Map<String, dynamic> _familyMember([Map<String, dynamic>? body]) {
    final relationshipKey = _text(body?['relationshipKey'], _relationshipKey);
    return {
      'id': 'member_admin',
      'name': _text(body?['name'], _identityLabelForKey(relationshipKey)),
      'relationshipKey': relationshipKey,
      'phone': _text(body?['phone'], _phone),
      'role': _text(body?['role'], 'admin'),
      'status': _text(body?['status'], 'active'),
      'notifyEnabled': body?['notifyEnabled'] ?? true,
      'userId': 'test_parent_$_phone',
    };
  }

  Map<String, dynamic> _familyInvitation(Map<String, dynamic> body) {
    final relationshipKey = _text(body['relationshipKey'], 'mom');
    return {
      'id': 'invite_test',
      'name': _text(body['name'], _identityLabelForKey(relationshipKey)),
      'relationshipKey': relationshipKey,
      'phone': _text(body['phone'], '13900002026'),
      'role': _text(body['role'], 'guardian'),
      'status': 'pending',
      'createdAt': _now,
      'expiresAt': _now + 604800000,
    };
  }

  Map<String, dynamic> _identityOptions() {
    return {
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
        {
          'key': 'family',
          'label': '其他家人',
          'defaultKey': 'family_default',
          'defaultLabel': '其他家人',
          'labels': [
            {
              'key': 'aunt',
              'label': '阿姨',
              'imageAsset': 'assets/images/guardian/guardian_aunt.png',
            },
            {
              'key': 'uncle',
              'label': '叔叔',
              'imageAsset': 'assets/images/guardian/guardian_uncle.png',
            },
            {
              'key': 'paternal_aunt',
              'label': '姑姑',
              'imageAsset': 'assets/images/guardian/guardian_paternal_aunt.png',
            },
            {
              'key': 'maternal_uncle',
              'label': '舅舅',
              'imageAsset':
                  'assets/images/guardian/guardian_maternal_uncle.png',
            },
            {
              'key': 'family_default',
              'label': '其他家人',
              'imageAsset': 'assets/images/guardian/guardian_default.png',
            },
          ],
        },
      ],
      'familyRoles': [
        {'key': 'admin', 'label': '管理员', 'description': '可管理成员、设备和全部家庭设置。'},
        {
          'key': 'guardian',
          'label': '监护人',
          'description': '可维护孩子资料、任务、奖励和紧急联系人，不管理成员和设备。',
        },
        {
          'key': 'viewer',
          'label': '临时查看者',
          'description': '可接收必要提醒和查看基础状态，不管理设置。',
        },
      ],
    };
  }

  Map<String, dynamic> _contact([Map<String, dynamic>? body]) {
    final relationshipKey = _text(body?['relationshipKey'], 'family_default');
    final relationship = _text(
      body?['relationship'],
      relationshipKey == 'mom'
          ? '妈妈'
          : relationshipKey == 'dad'
          ? '爸爸'
          : '其他家人',
    );
    return {
      'id': 'contact_test',
      'name': _text(body?['name'], '李老师'),
      'phone': _text(body?['phone'], '13900002026'),
      'relationship': relationship,
      'relationshipKey': relationshipKey,
      'defaultNotify': body?['defaultNotify'] ?? true,
    };
  }

  Map<String, dynamic> _accountProfile() {
    return {
      'userId': 'test_parent_$_phone',
      'displayName': _relationshipKey == 'dad' ? '林先生' : '林女士',
      'phone': _phone,
      'familyName': '林家的家庭空间',
      'relationship': _relationship,
      'relationshipKey': _relationshipKey,
      'role': 'admin',
      'roleLabel': '管理员',
      'capabilities': _adminCapabilities,
    };
  }

  void _applyAccountPersona(String phone) {
    _phone = phone;
    if (phone == '13860439696') {
      _relationship = '爸爸';
      _relationshipKey = 'dad';
      return;
    }
    if (phone.endsWith('8291')) {
      _relationship = '妈妈';
      _relationshipKey = 'mom';
    }
  }

  Map<String, dynamic> _accountSecurity() {
    return {
      'phone': _phone,
      'loginMethod': 'sms',
      'accountStatus': 'active',
      'loginDevices': [
        {
          'id': 'session_test',
          'label': '本机 iPhone',
          'deviceType': 'phone',
          'platform': 'ios',
          'appVersion': '',
          'active': true,
          'current': true,
          'createdAt': _now,
          'lastActiveAt': _now,
          'rotatedAt': _now,
        },
      ],
    };
  }

  String _identityLabelForKey(String key) {
    switch (key) {
      case 'mom':
        return '妈妈';
      case 'dad':
        return '爸爸';
      case 'maternal_grandpa':
        return '外公';
      case 'maternal_grandma':
        return '外婆';
      case 'grandpa':
        return '爷爷';
      case 'grandma':
        return '奶奶';
      case 'aunt':
        return '阿姨';
      case 'uncle':
        return '叔叔';
      case 'paternal_aunt':
        return '姑姑';
      case 'maternal_uncle':
        return '舅舅';
      case 'family_default':
        return '其他家人';
    }
    return '家庭成员';
  }

  Map<String, dynamic> _setting(String key, [Map<String, dynamic>? body]) {
    return {
      'key': key,
      'value': body?['value'] ?? _settingValue(key),
      'updatedAt': _now,
    };
  }

  Map<String, dynamic> _settingValue(String key) {
    return switch (key) {
      'notifications' => {
        'taskReminder': true,
        'taskEndReminder': true,
        'deviceOfflineReminder': true,
        'pointsRewardReminder': true,
        'safetyAlert': false,
        'dailySummary': false,
      },
      'privacy' => {
        'cameraCollectionAuthorized': true,
        'voiceBroadcastAuthorized': true,
        'childPrivacyAuthorized': true,
        'remoteViewingNoticeEnabled': true,
        'storeEventSnapshotsOnly': true,
        'dataRetentionDays': 30,
      },
      'conversation' => {
        'wakeName': '看护助手',
        'voiceStyle': '温和女声',
        'boundaryLevel': 'balanced',
        'freeChatEnabled': true,
        'freeChatSingleMinutes': 8,
        'freeChatDailyMinutes': 25,
        'homeworkModeRestricted': true,
        'bedtimeQuietEnabled': true,
      },
      'education' => {
        'schoolbagEnabled': true,
        'schoolStage': 'kindergarten',
        'courseScheduleEnabled': false,
        'learningDiagnosisEnabled': false,
        'notes': '',
      },
      _ => {
        'taskObservationEnabled': true,
        'voiceReminderEnabled': true,
        'delayReminderEnabled': true,
        'delayReminderIntervalMinutes': 3,
        'maxDelayReminderCount': 3,
        'cameraObservationStrategy': 'balanced',
      },
    };
  }

  Map<String, dynamic> _subscriptionStatus() {
    return {
      'plan': 'basic',
      'planId': 'basic',
      'planLabel': '基础版',
      'status': 'active',
      'statusLabel': '已启用',
      'renewalText': '随设备提供基础看护能力',
      'storeProvider': 'app_store',
      'entitlements': _subscriptionFeatures()
          .map(
            (item) => {
              'key': item['key'],
              'name': item['name'],
              'enabled': item['basic'],
            },
          )
          .toList(),
    };
  }

  List<Map<String, dynamic>> _subscriptionPlans() {
    return [
      {
        'id': 'basic',
        'title': '基础版',
        'subtitle': '随设备提供基础看护能力',
        'price': '随设备提供',
        'billing': '无需额外订阅',
        'recommended': false,
        'ctaLabel': '当前套餐',
        'features': ['看护提醒', '实时看护', '基础日报', '隐私控制'],
        'highlights': ['基础提醒', '实时查看', '基础日报', '隐私控制'],
      },
      {
        'id': 'member',
        'title': '会员版',
        'subtitle': '长期报告和趋势洞察',
        'price': '¥29',
        'billing': '/月',
        'recommended': true,
        'ctaLabel': '开通会员版',
        'features': ['云端长期报告', '高级趋势', '题目辅导颗粒度', '更多提醒基线'],
        'highlights': ['长期报告', '趋势洞察', '提醒升级', '辅导额度'],
      },
      {
        'id': 'family_plus',
        'title': '家庭高级版',
        'subtitle': '多孩子、多设备和多人协作',
        'price': '¥59',
        'billing': '/月起',
        'recommended': false,
        'ctaLabel': '查看家庭高级版',
        'features': ['多孩子与多设备', '多联系人协作', '长期成长档案', '合作内容包'],
        'highlights': ['多设备', '多人协作', '成长档案', '内容包'],
      },
    ];
  }

  List<Map<String, dynamic>> _subscriptionFeatures() {
    return [
      {
        'key': 'task_reminders',
        'name': '看护提醒',
        'basic': true,
        'member': true,
        'family_plus': true,
      },
      {
        'key': 'live_care',
        'name': '实时看护',
        'basic': true,
        'member': true,
        'family_plus': true,
      },
      {
        'key': 'daily_report',
        'name': '基础日报',
        'basic': true,
        'member': true,
        'family_plus': true,
      },
      {
        'key': 'long_term_reports',
        'name': '长期云端报告',
        'basic': false,
        'member': true,
        'family_plus': true,
      },
      {
        'key': 'advanced_trends',
        'name': '高级趋势',
        'basic': false,
        'member': true,
        'family_plus': true,
      },
      {
        'key': 'multi_device_family',
        'name': '多孩子与多设备',
        'basic': false,
        'member': false,
        'family_plus': true,
      },
    ];
  }

  Map<String, dynamic> _dailyReport() {
    return {
      'date': _today,
      'title': '今日报告',
      'summary': '今天还有需要家长处理的记录。',
      'taskTotal': _tasks.length,
      'taskCompleted': _tasks
          .where((task) => task['status'] == 'confirmed')
          .length,
      'pendingItems': _tasks
          .where((task) => task['status'] == 'awaiting_parent_confirmation')
          .length,
      'pointsEarned': 1,
      'suggestion': '先确认需要处理的记录，再决定是否写入成长记录。',
    };
  }

  Map<String, dynamic> _weeklyReport() {
    return {
      'startDate': _today,
      'endDate': _today,
      'title': '周报',
      'taskTotal': _tasks.length,
      'taskCompleted': 1,
      'completionRate': 0.5,
      'pointsEarned': 1,
      'summary': '本周完成 1 / ${_tasks.length} 项任务。',
    };
  }

  Map<String, dynamic> _legalDocument(String key) {
    final isPrivacy = key == 'privacy-policy';
    return {
      'key': key,
      'title': isPrivacy
          ? '隐私政策'
          : key == 'child-privacy-authorization'
          ? '儿童隐私授权说明'
          : '用户协议',
      'summary': isPrivacy ? '说明隐私与儿童数据处理边界。' : '说明服务使用边界。',
      'version': '1.0',
      'effectiveDate': '2026-06-04',
      'sections': [
        {
          'title': isPrivacy ? '1. 开发者与适用范围' : '1. 服务说明',
          'paragraphs': [
            isPrivacy ? '我们只在必要范围内处理家庭看护数据。' : '本应用为家长提供家庭看护辅助能力。',
          ],
        },
      ],
    };
  }

  Map<String, dynamic> _about() {
    return {
      'appName': '暖瞳',
      'displayName': '暖瞳',
      'version': '1.0.0',
      'build': '2026.06',
      'appUpdate': {
        'status': 'latest',
        'latestVersion': '1.0.0',
        'latestBuild': '2026.06',
        'releaseDate': '2026.06.10',
        'notes': '当前已是最新版本',
      },
      'description': '面向家长的家庭 AI 看护与成长记录 App。',
      'principles': ['儿童隐私优先', '关键决定由家长确认', '温和提醒，不过度打扰'],
    };
  }

  Map<String, dynamic> _taskTemplatesResponse(Map<String, dynamic> query) {
    final grade = _text(query['grade'], '');
    final dayType = _text(query['dayType'], '');
    final tag = _text(query['tag'], '');
    final templates = _fakeTaskTemplates().where((template) {
      if (grade.isNotEmpty && template['grade'] != grade) return false;
      if (dayType.isNotEmpty && template['dayType'] != dayType) return false;
      final tags = template['tags'];
      if (tag.isNotEmpty &&
          tag != 'all' &&
          (tags is! List || !tags.contains(tag))) {
        return false;
      }
      return true;
    }).toList();
    return {
      'ok': true,
      'templates': templates,
      'tags': const [
        {'value': 'all', 'label': '全部'},
        {'value': 'school_day', 'label': '上学日'},
        {'value': 'weekend', 'label': '周末'},
        {'value': 'morning', 'label': '晨间'},
        {'value': 'after_school', 'label': '放学后'},
        {'value': 'bedtime', 'label': '睡前'},
        {'value': 'outdoor', 'label': '户外'},
        {'value': 'cleanup', 'label': '收纳'},
        {'value': 'reading', 'label': '阅读'},
        {'value': 'meal', 'label': '用餐'},
        {'value': 'emotion', 'label': '表达'},
        {'value': 'self_care', 'label': '自理'},
        {'value': 'rules', 'label': '规则'},
        {'value': 'helper', 'label': '小帮手'},
      ],
      'grades': const [
        {'value': 'small', 'label': '小班'},
        {'value': 'middle', 'label': '中班'},
        {'value': 'big', 'label': '大班'},
      ],
      'dayTypes': const [
        {'value': 'school_day', 'label': '上学日'},
        {'value': 'weekend', 'label': '周末'},
      ],
      'recommendedGrade': grade.isEmpty ? 'middle' : grade,
      'recommendedGradeLabel': grade == 'small'
          ? '小班'
          : grade == 'big'
          ? '大班'
          : '中班',
    };
  }

  List<Map<String, dynamic>> _fakeTaskTemplates() {
    return [
      for (final grade in const ['small', 'middle', 'big'])
        for (var index = 0; index < 10; index++)
          _fakeTaskTemplate(grade, index),
    ];
  }

  Map<String, dynamic> _fakeTaskTemplate(String grade, int index) {
    final gradeLabel = switch (grade) {
      'small' => '小班',
      'big' => '大班',
      _ => '中班',
    };
    final titles = [
      '上学日晨间',
      '放学后表达',
      '餐前餐后',
      '睡前准备',
      '周末户外',
      '亲子阅读',
      '家庭小帮手',
      '整理自己的物品',
      '情绪分享',
      '规则与轮流',
    ];
    final tagSets = const [
      ['school_day', 'morning', 'self_care', 'meal'],
      ['school_day', 'after_school', 'emotion'],
      ['school_day', 'meal', 'cleanup'],
      ['school_day', 'bedtime', 'reading'],
      ['weekend', 'outdoor', 'rules'],
      ['weekend', 'reading', 'emotion'],
      ['weekend', 'helper', 'cleanup'],
      ['weekend', 'cleanup', 'self_care'],
      ['school_day', 'emotion', 'reading'],
      ['weekend', 'rules', 'outdoor'],
    ];
    final rows = index == 3
        ? const [
            {
              'startTime': '20:20',
              'endTime': '20:30',
              'taskType': 'sleep',
              'title': '自己洗漱',
              'rewardPoints': 1,
              'requiresParentConfirmation': false,
            },
            {
              'startTime': '20:30',
              'endTime': '20:50',
              'taskType': 'reading_interest',
              'title': '睡前阅读',
              'rewardPoints': 1,
              'requiresParentConfirmation': false,
            },
          ]
        : const [
            {
              'startTime': '17:20',
              'endTime': '17:35',
              'taskType': 'life',
              'title': '喝水休息',
              'rewardPoints': 1,
              'requiresParentConfirmation': false,
            },
            {
              'startTime': '17:40',
              'endTime': '18:00',
              'taskType': 'sports_outdoor',
              'title': '户外活动',
              'rewardPoints': 2,
              'requiresParentConfirmation': false,
            },
          ];
    return {
      'id': 'kg-$grade-$index',
      'templateKey': 'kg-$grade-$index',
      'title': titles[index],
      'subtitle': '适合幼儿园孩子的一天小提醒',
      'grade': grade,
      'gradeLabel': gradeLabel,
      'ageGroups': ['kindergarten_$grade'],
      'scheduleType': index < 4 ? 'weekday' : 'weekly',
      'dayType': index < 4 || index == 8 ? 'school_day' : 'weekend',
      'dayTypeLabel': index < 4 || index == 8 ? '上学日' : '周末',
      'tags': tagSets[index],
      'tagLabels': tagSets[index],
      'rows': rows,
    };
  }

  Map<String, dynamic> _taskFromBody(Map<String, dynamic> body) {
    _taskCounter += 1;
    return _task(
      id: 'task_created_$_taskCounter',
      title: _text(body['title'], '新提醒'),
      description: _text(body['description'], ''),
      type: _text(body['taskType'], 'life'),
      status: _text(body['status'], 'pending'),
      scheduledDate: _text(body['scheduledDate'], _today),
      scheduledStart: _text(body['scheduledStart'], '16:00'),
      scheduledEnd: _text(body['scheduledEnd'], '16:20'),
      rewardPoints: _int(body['rewardPoints'], 0),
    );
  }

  Map<String, dynamic> _task({
    required String id,
    required String title,
    required String description,
    required String type,
    required String status,
    String? scheduledDate,
    required String scheduledStart,
    required String scheduledEnd,
    required int rewardPoints,
    String evidenceSummary = '',
  }) {
    final date = scheduledDate ?? _today;
    return {
      'id': id,
      'taskId': id,
      'familyId': 'family_test',
      'childId': 'child_test',
      'title': title,
      'description': description,
      'taskType': type,
      'type': type,
      'scheduleType': 'one_time',
      'startAt': '${date}T$scheduledStart:00+08:00',
      'dueAt': '${date}T$scheduledEnd:00+08:00',
      'repeatRule': null,
      'status': status,
      'priority': 3,
      'scheduledDate': date,
      'scheduledStart': scheduledStart,
      'scheduledEnd': scheduledEnd,
      'rewardPoints': rewardPoints,
      'requiresParentConfirmation': true,
      'completionSource': '',
      'evidence': {'summary': evidenceSummary},
      'evidenceSummary': evidenceSummary,
      'aiObservationSummary': '',
      'rejectionReason': '',
      'createdBy': 'test_parent_13800002026',
      'createdAt': _now,
      'updatedAt': _now,
      'completedAt': status == 'awaiting_parent_confirmation' ? _now : null,
      'startedAt': status == 'in_progress' ? _now : null,
      'endedAt': null,
      'missedAt': null,
      'delayedAt': null,
      'lastReminderAt': null,
      'nextReminderAt': null,
      'delayReminderCount': 0,
      'reminderMinutesBefore': 5,
      'reminderStatus': 'pending',
      'cameraObservationStatus': 'normal',
      'deviceId': 'device_test',
      'timezone': 'Asia/Shanghai',
      'confirmedAt': null,
      'rejectedAt': null,
      'pointsGrantedAt': null,
      'parentActions': status == 'missed'
          ? [
              {'value': 'reschedule', 'label': '重新安排'},
              {'value': 'manual_complete', 'label': '手动标记完成'},
              {'value': 'acknowledge_missed', 'label': '不处理'},
            ]
          : [],
    };
  }

  Map<String, dynamic>? _findTask(String id) {
    for (final task in _tasks) {
      if (task['id'] == id || task['taskId'] == id) return task;
    }
    return null;
  }

  List<Map<String, dynamic>> _taskEvents(Map<String, dynamic> task) {
    return [
      {
        'id': 'event_${task['id']}_created',
        'taskId': task['id'],
        'eventType': 'task_created',
        'message': '任务已创建',
        'payload': {},
        'createdAt': _now,
      },
      if (task['status'] == 'rejected')
        {
          'id': 'event_${task['id']}_rejected',
          'taskId': task['id'],
          'eventType': 'confirmation_rejected',
          'message': '本次任务未通过确认，未发放积分。',
          'payload': {},
          'createdAt': _now,
        },
    ];
  }

  Map<String, dynamic> _pointAccount() {
    return {
      'familyId': 'family_test',
      'childId': 'child_test',
      'balance': 60,
      'updatedAt': _now,
    };
  }

  Map<String, dynamic> _pointSettings([Map<String, dynamic>? body]) {
    final unit = _text(body?['unit'], 'flower');
    final options = [
      {
        'key': 'points',
        'label': '积分',
        'description': '通用分值，适合偏任务化的家庭激励。',
        'suffix': '分',
        'imageAsset': 'assets/images/points/unit-points.png',
      },
      {
        'key': 'flower',
        'label': '小红花',
        'description': '默认方案，适合低龄儿童和日常正向反馈。',
        'suffix': '朵小红花',
        'imageAsset': 'assets/images/points/unit-flower.png',
      },
      {
        'key': 'star',
        'label': '小星星',
        'description': '更轻量的阶段激励，适合兴趣任务和成长记录。',
        'suffix': '颗小星星',
        'imageAsset': 'assets/images/points/unit-star.png',
      },
    ];
    final selected = options.firstWhere(
      (option) => option['key'] == unit,
      orElse: () => options[1],
    );
    return {
      'stageThreshold': _int(body?['stageThreshold'], 10),
      'unit': selected['key'],
      'unitOption': selected,
      'unitOptions': options,
      'updatedAt': _now,
    };
  }

  List<Map<String, dynamic>> _pointLedger() {
    return [
      {
        'id': 'ledger_test',
        'childId': 'child_test',
        'delta': 1,
        'balanceAfter': 1,
        'type': 'task_completed',
        'sourceType': 'task',
        'sourceId': 'task_math_homework',
        'note': '任务奖励',
        'createdAt': _now,
      },
    ];
  }

  List<Map<String, dynamic>> _rewardItems() {
    return [
      {
        'id': 'reward_family_game',
        'familyId': 'family_test',
        'childId': 'child_test',
        'title': '周末亲子游戏 20 分钟',
        'description': '由家长兑现的一段共同游戏时间。',
        'pointsCost': 20,
        'category': 'family',
        'status': 'active',
        'icon': 'sports',
      },
    ];
  }

  List<Map<String, dynamic>> _redemptions() {
    return [
      {
        'id': 'redeem_test',
        'childId': 'child_test',
        'rewardItemId': 'reward_family_game',
        'rewardTitle': '周末亲子游戏 20 分钟',
        'pointsCost': 20,
        'status': 'redeemed',
        'requestedAt': _now,
        'fulfilledAt': null,
        'cancelledAt': null,
      },
    ];
  }

  List<Map<String, dynamic>> _careCapabilities() {
    const scenarios = [
      ('posture', '坐姿提醒', ['posture']),
      ('toy_cleanup', '玩具收纳', <String>[]),
      ('meal_start', '用餐开始提醒', ['breakfast', 'lunch', 'dinner']),
      ('meal_habit', '用餐习惯提醒', ['breakfast', 'lunch', 'dinner']),
      ('nap_time', '午睡提醒', ['nap']),
      ('bedtime', '晚上入睡提醒', ['bedtime']),
      ('wake_up', '起床提醒', ['wake_up']),
      ('transition', '转场提醒', ['transition']),
    ];
    return [
      for (final item in scenarios)
        {
          'id': 'care_${item.$1}',
          'childId': 'child_test',
          'deviceId': 'device_test',
          'scenario': item.$1,
          'label': item.$2,
          'enabled': true,
          'dayTypes': ['school_day', 'weekend'],
          'timeWindows': item.$3,
          'minObservationSeconds': item.$1 == 'toy_cleanup' ? 180 : 30,
          'observationThreshold': 0.72,
          'cooldownSeconds': item.$1 == 'toy_cleanup' ? 1800 : 1200,
          'dailyLimit': item.$1 == 'toy_cleanup' ? 3 : 4,
          'parentNotifyThreshold': 2,
          'allowSpeaker': true,
          'recordOnly': false,
          'lastRemindedAt': null,
          'dailyReminderCount': 0,
        },
    ];
  }

  Map<String, dynamic> _device([Map<String, dynamic>? body]) {
    return {
      'id': 'device_test',
      'name': _text(body?['deviceName'] ?? body?['name'], '暖瞳摄像头'),
      'location': _text(body?['location'], '书桌旁'),
      'status': 'online',
      'isDefault': true,
      'bindingCode': 'BIND-TEST',
      'boundAt': _now,
      'lastSeenAt': _now,
      'capabilities': {
        'snapshot': true,
        'stream': true,
        'twoWayAudio': true,
        'monitor': true,
      },
    };
  }

  Map<String, dynamic> _deviceStatus() {
    return {
      'deviceId': 'device_test',
      'connectionStatus': 'online',
      'batteryLevel': null,
      'networkType': 'wifi',
      'lastSeenAt': _now,
      'message': '设备在线',
      'capabilities': {
        'snapshot': true,
        'stream': true,
        'twoWayAudio': true,
        'monitor': true,
      },
    };
  }

  Map<String, dynamic> _cameraStatus() {
    return {
      'connectionStatus': 'online',
      'snapshotAvailable': true,
      'streamAvailable': true,
      'speakerAvailable': true,
      'monitorAvailable': true,
      'ptzAvailable': false,
      'lastSeenAt': _now,
      'message': '设备在线',
    };
  }

  Map<String, dynamic> _monitorStatus() {
    return {
      'running': true,
      'status': 'running',
      'lastObservation': {
        'verdict': 'normal',
        'reason': 'task_in_progress',
        'confidence': 0.8,
      },
      'lastReminder': '',
    };
  }

  List<Map<String, dynamic>> _cameraEvents() {
    return [
      {
        'id': 'evt_camera_1',
        'source': 'task_event',
        'eventType': 'child_not_ready',
        'title': '还没看到孩子开始',
        'message': '暂时还不能确认孩子已经开始。',
        'displayTitle': '还没看到孩子开始',
        'displayMessage': '暂时还不能确认孩子已经开始。',
        'category': 'camera_observation',
        'severity': 'warning',
        'taskTitle': '睡前阅读',
        'evidenceSummary': '未看到对应动作',
        'hasReplay': false,
        'status': 'recorded',
        'tone': 'warning',
        'createdAt': _now,
        'payload': {},
      },
    ];
  }

  List<Map<String, dynamic>> _routineWindows(String dayType) {
    const rows = [
      ('wake_up', '07:00', '07:40'),
      ('breakfast', '07:30', '08:10'),
      ('lunch', '11:40', '12:30'),
      ('nap', '12:40', '14:20'),
      ('dinner', '18:00', '19:00'),
      ('bedtime', '20:30', '21:20'),
    ];
    return [
      for (final row in rows)
        {
          'id': 'routine_${dayType}_${row.$1}',
          'childId': 'child_test',
          'dayType': dayType,
          'windowType': row.$1,
          'startTime': row.$2,
          'endTime': row.$3,
          'enabled': true,
          'timezone': 'Asia/Shanghai',
        },
    ];
  }

  Map<String, dynamic> _firmwareStatus() {
    return {
      'ok': true,
      'device': _device(),
      'firmware': {
        'currentVersion': '0.1.0-dev',
        'updateAvailable': false,
        'latestPackage': null,
        'lastJob': null,
        'execution': 'not_configured',
      },
    };
  }

  Response<dynamic> _ok(RequestOptions options, dynamic data) {
    return Response<dynamic>(
      requestOptions: options,
      statusCode: 200,
      data: data,
    );
  }

  Response<dynamic> _notFound(RequestOptions options) {
    return Response<dynamic>(
      requestOptions: options,
      statusCode: 404,
      data: {'ok': false, 'error': 'not_found', 'message': '路径不存在'},
    );
  }

  Response<dynamic> _error(
    RequestOptions options,
    int statusCode,
    String code,
    String message,
  ) {
    return Response<dynamic>(
      requestOptions: options,
      statusCode: statusCode,
      data: {'ok': false, 'error': code, 'message': message},
    );
  }

  Map<String, dynamic> _body(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return <String, dynamic>{};
  }

  String _normalizePath(String rawPath) {
    final uri = Uri.tryParse(rawPath);
    var path = uri?.hasScheme == true ? uri!.path : rawPath;
    if (path.startsWith('/api/')) {
      path = path.substring(4);
    }
    return path;
  }

  String _text(dynamic value, String fallback) {
    return value is String && value.isNotEmpty ? value : fallback;
  }

  int _int(dynamic value, int fallback) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value) ?? fallback;
    return fallback;
  }

  int get _now => DateTime.now().millisecondsSinceEpoch;

  String get _today {
    final now = DateTime.now();
    return '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
  }
}
