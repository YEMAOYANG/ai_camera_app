import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_reactive_ble/flutter_reactive_ble.dart' as reactive;
import 'package:guardian_parent_app/src/core/storage/onboarding_store.dart';
import 'package:guardian_parent_app/src/core/theme/app_theme.dart';
import 'package:guardian_parent_app/src/features/devices/application/camera_discovery_adapter.dart';
import 'package:guardian_parent_app/src/features/devices/application/camera_discovery_repository.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('camera discovery factory uses mock adapter by default', () {
    final mockAdapter = _FakeCameraDiscoveryAdapter();
    final bleAdapter = _FakeCameraDiscoveryAdapter();
    final selected =
        CameraDiscoveryAdapterFactory(
          mockAdapter: mockAdapter,
          bleAdapter: bleAdapter,
        ).create(
          const CameraDiscoveryConfig(
            backend: CameraDiscoveryBackend.mock,
            allowBleFallbackToMock: false,
          ),
        );

    expect(identical(selected, mockAdapter), isTrue);
  });

  test('camera discovery factory uses BLE adapter when backend is BLE', () {
    final mockAdapter = _FakeCameraDiscoveryAdapter();
    final bleAdapter = _FakeCameraDiscoveryAdapter();
    final selected =
        CameraDiscoveryAdapterFactory(
          mockAdapter: mockAdapter,
          bleAdapter: bleAdapter,
        ).create(
          const CameraDiscoveryConfig(
            backend: CameraDiscoveryBackend.ble,
            allowBleFallbackToMock: true,
          ),
        );

    expect(identical(selected, bleAdapter), isTrue);
  });

  test(
    'camera discovery factory keeps BLE adapter when fallback is disabled',
    () {
      final mockAdapter = _FakeCameraDiscoveryAdapter();
      final bleAdapter = _FakeCameraDiscoveryAdapter();
      final selected =
          CameraDiscoveryAdapterFactory(
            mockAdapter: mockAdapter,
            bleAdapter: bleAdapter,
          ).create(
            const CameraDiscoveryConfig(
              backend: CameraDiscoveryBackend.ble,
              allowBleFallbackToMock: false,
            ),
          );

      expect(identical(selected, bleAdapter), isTrue);
    },
  );

  test(
    'BLE adapter reports unsupported on non-mobile test platforms',
    () async {
      final adapter = BleCameraDiscoveryAdapter(
        permissionProbe: _FakePermissionProbe(
          status: CameraDiscoveryPermissionStatus.ready,
        ),
        bleClient: _FakeReactiveBleClient(),
        scanConfig: const CameraBleScanConfig(
          serviceUuids: [],
          namePrefixes: [],
          manufacturerId: null,
          scanTimeout: Duration(milliseconds: 20),
        ),
      );

      expect(
        await adapter.getPermissionStatus(),
        CameraDiscoveryPermissionStatus.unsupported,
      );
      final result = await adapter.startScan().first;
      expect(result.phase, CameraDiscoveryPhase.connectionFailed);
      expect(result.failureReason, AddCameraFailureReason.unsupported);
    },
  );

  test('BLE adapter times out when scan criteria are not configured', () async {
    final adapter = BleCameraDiscoveryAdapter(
      permissionProbe: _FakePermissionProbe(
        status: CameraDiscoveryPermissionStatus.ready,
      ),
      bleClient: _FakeReactiveBleClient(),
      scanConfig: const CameraBleScanConfig(
        serviceUuids: [],
        namePrefixes: [],
        manufacturerId: null,
        scanTimeout: Duration(milliseconds: 20),
      ),
      isSupportedPlatform: true,
    );

    final result = await adapter.startScan().first;
    expect(result.phase, CameraDiscoveryPhase.notFound);
    expect(result.candidates, isEmpty);
  });

  test('BLE adapter maps powered off bluetooth to bluetoothOff', () async {
    final adapter = BleCameraDiscoveryAdapter(
      permissionProbe: _FakePermissionProbe(
        status: CameraDiscoveryPermissionStatus.ready,
      ),
      bleClient: _FakeReactiveBleClient(status: reactive.BleStatus.poweredOff),
      scanConfig: const CameraBleScanConfig(
        serviceUuids: [],
        namePrefixes: ['WarmSight-'],
        manufacturerId: null,
        scanTimeout: Duration(milliseconds: 20),
      ),
      isSupportedPlatform: true,
    );

    expect(
      await adapter.getPermissionStatus(),
      CameraDiscoveryPermissionStatus.bluetoothOff,
    );
    final result = await adapter.startScan().first;
    expect(result.phase, CameraDiscoveryPhase.bluetoothOff);
    expect(result.failureReason, AddCameraFailureReason.bluetoothUnavailable);
  });

  test(
    'BLE adapter maps unauthorized bluetooth to settings permission',
    () async {
      final adapter = BleCameraDiscoveryAdapter(
        permissionProbe: _FakePermissionProbe(
          status: CameraDiscoveryPermissionStatus.ready,
        ),
        bleClient: _FakeReactiveBleClient(
          status: reactive.BleStatus.unauthorized,
        ),
        scanConfig: const CameraBleScanConfig(
          serviceUuids: [],
          namePrefixes: ['WarmSight-'],
          manufacturerId: null,
          scanTimeout: Duration(milliseconds: 20),
        ),
        isSupportedPlatform: true,
      );

      expect(
        await adapter.getPermissionStatus(),
        CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied,
      );
      final result = await adapter.startScan().first;
      expect(result.phase, CameraDiscoveryPhase.permissionRequired);
      expect(
        result.failureReason,
        AddCameraFailureReason.permissionPermanentlyDenied,
      );
    },
  );

  test('BLE adapter filters random nearby BLE devices', () async {
    final adapter = BleCameraDiscoveryAdapter(
      permissionProbe: _FakePermissionProbe(
        status: CameraDiscoveryPermissionStatus.ready,
      ),
      bleClient: _FakeReactiveBleClient(
        devices: [
          _bleDevice(id: 'speaker-1', name: 'Living Room Speaker', rssi: -45),
        ],
      ),
      scanConfig: const CameraBleScanConfig(
        serviceUuids: [],
        namePrefixes: ['WarmSight-', 'AI-Camera-'],
        manufacturerId: null,
        scanTimeout: Duration(milliseconds: 20),
      ),
      isSupportedPlatform: true,
    );

    final result = await adapter.startScan().firstWhere(
      (item) => item.phase == CameraDiscoveryPhase.notFound,
    );
    expect(result.candidates, isEmpty);
  });

  test('BLE adapter discovers matching camera candidates by signal', () async {
    final adapter = BleCameraDiscoveryAdapter(
      permissionProbe: _FakePermissionProbe(
        status: CameraDiscoveryPermissionStatus.ready,
      ),
      bleClient: _FakeReactiveBleClient(
        devices: [
          _bleDevice(id: 'camera-weak', name: 'WarmSight-002', rssi: -70),
          _bleDevice(id: 'camera-strong', name: 'WarmSight-001', rssi: -42),
        ],
      ),
      scanConfig: const CameraBleScanConfig(
        serviceUuids: [],
        namePrefixes: ['WarmSight-'],
        manufacturerId: null,
        scanTimeout: Duration(milliseconds: 120),
      ),
      isSupportedPlatform: true,
    );

    final result = await adapter.startScan().firstWhere(
      (item) =>
          item.phase == CameraDiscoveryPhase.found &&
          item.candidates.length == 2,
    );
    expect(result.candidates.length, 2);
    expect(result.candidates.first.id, 'ble_camera-strong');
    expect(result.candidates.first.displayName, 'AI 看护摄像头');
    expect(result.candidates.first.bindingCode, startsWith('ble:'));
    expect(
      result.candidates.every(
        (candidate) => candidate.source == CameraDiscoveryCandidateSource.ble,
      ),
      isTrue,
    );
  });

  test(
    'BLE adapter does not create a device before hardware protocol exists',
    () async {
      final adapter = BleCameraDiscoveryAdapter(
        permissionProbe: _FakePermissionProbe(
          status: CameraDiscoveryPermissionStatus.ready,
        ),
        bleClient: _FakeReactiveBleClient(),
        scanConfig: const CameraBleScanConfig(
          serviceUuids: [],
          namePrefixes: [],
          manufacturerId: null,
          scanTimeout: Duration(milliseconds: 20),
        ),
        isSupportedPlatform: true,
      );

      await expectLater(
        adapter.connectCandidate(_singleCandidate),
        throwsA(
          isA<DeviceException>().having(
            (error) => error.code,
            'code',
            'ble_protocol_unavailable',
          ),
        ),
      );
    },
  );

  testWidgets('add camera sheet starts discovery after permissions are ready', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      scanDelay: const Duration(seconds: 30),
    );
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    expect(find.text('正在搜索附近摄像头'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('add_camera_sheet_searching_layout')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('add_camera_sheet_searching_animation')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('add_camera_sheet_footer')), findsNothing);
    expect(find.text('正在查找可连接设备'), findsOneWidget);
    expect(find.text('连接'), findsNothing);
    expect(
      tester
          .getSize(
            find.byKey(const ValueKey('add_camera_sheet_searching_layout')),
          )
          .height,
      lessThanOrEqualTo(430),
    );
    expect(find.text('查看帮助'), findsNothing);
    expect(find.text('开始发现'), findsNothing);
    expect(find.text('继续发现'), findsNothing);
  });

  testWidgets('add camera sheet shows single nearby camera title', (
    tester,
  ) async {
    await _pumpSheet(
      tester,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [_singleCandidate],
    );

    expect(find.text('发现附近摄像头'), findsOneWidget);
    expect(find.text('AI 看护摄像头'), findsOneWidget);
    expect(find.text('连接'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('add_camera_sheet_device_list_layout')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('add_camera_sheet_device_list')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('add_camera_sheet_footer')),
      findsOneWidget,
    );
    _expectNoEngineeringCopy();
  });

  testWidgets('multi-device discovery uses taller list layout with footer', (
    tester,
  ) async {
    await _pumpSheet(
      tester,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: _candidates,
    );

    expect(
      find.byKey(const ValueKey('add_camera_sheet_device_list_layout')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('add_camera_sheet_device_list')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('add_camera_sheet_footer')),
      findsOneWidget,
    );
    expect(
      tester
          .getSize(
            find.byKey(const ValueKey('add_camera_sheet_device_list_layout')),
          )
          .height,
      greaterThanOrEqualTo(500),
    );
  });

  testWidgets('multi-camera discovery selects strongest signal by default', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(candidates: _candidates);
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump(const Duration(milliseconds: 1600));
    await tester.pump();
    expect(find.text('发现附近摄像头'), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 260));
    expect(_primaryButton(tester, '连接').onTap, isNotNull);

    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(adapter.connectedCandidate?.id, 'nearby-bedroom');
    expect(find.text('摄像头已连接'), findsOneWidget);
    expect(find.text('实时看护已准备好'), findsWidgets);
  });

  testWidgets('multi-camera selection connects the tapped camera', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(candidates: _candidates);
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump(const Duration(milliseconds: 1600));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    expect(_primaryButton(tester, '连接').onTap, isNotNull);
    await tester.tap(
      find.byKey(const ValueKey('discoveredCamera_nearby-desk')),
    );
    await tester.pump();
    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(adapter.connectedCandidate?.id, 'nearby-desk');
  });

  testWidgets('bluetooth off state opens bluetooth settings on Android', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      permissionStatus: CameraDiscoveryPermissionStatus.bluetoothOff,
      scanDelay: const Duration(seconds: 30),
    );
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();

    expect(find.text('请打开蓝牙'), findsOneWidget);
    expect(find.text('去打开蓝牙'), findsOneWidget);
    expect(find.text('查看帮助'), findsNothing);
    expect(find.text('连接帮助'), findsNothing);
    _expectSingleCloseButton();
    _expectNoEngineeringCopy();

    adapter.permissionStatus = CameraDiscoveryPermissionStatus.ready;
    await tester.tap(find.text('去打开蓝牙'));
    await tester.pump();
    expect(adapter.openBluetoothSettingsCount, 1);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump();
    await tester.pump();
    expect(find.text('正在搜索附近摄像头'), findsOneWidget);
  });

  testWidgets('permission required state uses parent-facing copy', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      permissionStatus:
          CameraDiscoveryPermissionStatus.bluetoothPermissionRequired,
      requestPermissionStatus: CameraDiscoveryPermissionStatus.ready,
      scanDelay: const Duration(seconds: 30),
    );
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();

    expect(find.text('需要允许蓝牙'), findsOneWidget);
    expect(find.text('允许后，我们才能搜索附近的看护摄像头。'), findsOneWidget);
    expect(find.text('允许并继续'), findsOneWidget);
    expect(find.text('稍后再说'), findsOneWidget);
    _expectNoEngineeringCopy();

    await tester.tap(find.text('允许并继续'));
    await tester.pump();
    await tester.pump();
    await tester.pump();
    expect(find.text('正在搜索附近摄像头'), findsOneWidget);
  });

  testWidgets('permanently denied permission offers system settings', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      permissionStatus:
          CameraDiscoveryPermissionStatus.bluetoothPermissionPermanentlyDenied,
    );
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();

    expect(find.text('需要在系统设置中开启蓝牙权限'), findsOneWidget);
    expect(find.text('去系统设置'), findsOneWidget);
    expect(find.text('稍后再说'), findsOneWidget);
    expect(find.text('开启后再回来，我们会继续搜索附近摄像头。'), findsOneWidget);
    await tester.tap(find.text('去系统设置'));
    await tester.pump();
    expect(adapter.openSettingsCount, 1);
  });

  testWidgets('main discovery states keep one close button', (tester) async {
    for (final phase in const [
      CameraDiscoveryPhase.permissionRequired,
      CameraDiscoveryPhase.bluetoothOff,
      CameraDiscoveryPhase.searching,
      CameraDiscoveryPhase.found,
      CameraDiscoveryPhase.connecting,
      CameraDiscoveryPhase.connected,
      CameraDiscoveryPhase.connectedWithoutLivePreview,
      CameraDiscoveryPhase.notFound,
      CameraDiscoveryPhase.connectionFailed,
      CameraDiscoveryPhase.alreadyBoundToAnotherFamily,
      CameraDiscoveryPhase.networkSetupFailed,
    ]) {
      await _pumpSheet(
        tester,
        initialPhase: phase,
        initialCandidates:
            phase == CameraDiscoveryPhase.found ||
                phase == CameraDiscoveryPhase.connecting
            ? const [_singleCandidate]
            : null,
      );

      _expectSingleCloseButton();
    }
  });

  testWidgets('local network permission uses home camera copy', (tester) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      permissionStatus:
          CameraDiscoveryPermissionStatus.localNetworkPermissionRequired,
    );
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();

    expect(find.text('需要本地网络权限'), findsOneWidget);
    expect(find.text('需要允许本地网络，才能和家里的摄像头建立连接。'), findsOneWidget);
  });

  testWidgets('not found state keeps one primary retry action', (tester) async {
    final adapter = _FakeCameraDiscoveryAdapter(candidates: const []);
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();
    await tester.pump();

    expect(find.text('没有发现附近摄像头'), findsOneWidget);
    expect(find.text('重新搜索'), findsOneWidget);
    expect(find.text('查看帮助'), findsNothing);
    expect(find.text('连接'), findsNothing);
    expect(find.text('继续'), findsNothing);
  });

  testWidgets('connecting state prevents duplicate connect taps', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      candidates: const [_singleCandidate],
      connectDelay: const Duration(milliseconds: 80),
    );
    await _pumpSheet(
      tester,
      adapter: adapter,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [_singleCandidate],
    );

    _primaryButton(tester, '连接').onTap!();
    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 120));
    await tester.pump(const Duration(milliseconds: 300));

    expect(adapter.connectCount, 1);
  });

  testWidgets('successful connection can warn when preview is not ready', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      candidates: const [_singleCandidate],
      livePreviewAvailable: false,
    );
    await _pumpSheet(
      tester,
      adapter: adapter,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [_singleCandidate],
    );

    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('摄像头已添加'), findsWidgets);
    expect(find.text('实时画面暂时不可用，可稍后在看护页重试。'), findsOneWidget);
  });

  testWidgets('connection failed state is clear and retryable', (tester) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      connectError: const DeviceException('连接失败', code: 'connection_lost'),
    );
    await _pumpSheet(
      tester,
      adapter: adapter,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [_singleCandidate],
    );
    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('连接失败'), findsWidgets);
    expect(find.text('重新连接'), findsOneWidget);
    expect(find.textContaining('连接中断'), findsOneWidget);
  });

  testWidgets('BLE adapter unavailable state is parent-facing', (tester) async {
    await _pumpSheet(
      tester,
      initialPhase: CameraDiscoveryPhase.connectionFailed,
      initialFailureReason: AddCameraFailureReason.bleAdapterUnavailable,
    );

    expect(find.text('连接失败'), findsOneWidget);
    expect(find.text('暂时无法连接摄像头，请稍后再试。'), findsOneWidget);
    _expectNoEngineeringCopy();
  });

  testWidgets('BLE hardware protocol missing state is parent-facing', (
    tester,
  ) async {
    await _pumpSheet(
      tester,
      initialPhase: CameraDiscoveryPhase.connectionFailed,
      initialFailureReason: AddCameraFailureReason.hardwareProtocolUnavailable,
    );

    expect(find.text('连接失败'), findsOneWidget);
    expect(find.text('暂时无法完成连接，设备协议还未接入。'), findsOneWidget);
    _expectNoEngineeringCopy();
  });

  testWidgets('already bound candidate returns to disabled device card', (
    tester,
  ) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      connectError: const DeviceException('已被绑定', code: 'already_bound'),
    );
    await _pumpSheet(
      tester,
      adapter: adapter,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [_singleCandidate],
    );
    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('发现附近摄像头'), findsOneWidget);
    expect(find.text('已被其他家庭绑定'), findsOneWidget);
    expect(find.text('没有可连接设备'), findsOneWidget);
    expect(_primaryButton(tester, '没有可连接设备').onTap, isNull);
  });

  testWidgets('disabled already-bound candidate cannot be selected', (
    tester,
  ) async {
    const unavailable = DiscoveredCameraCandidate(
      id: 'nearby-bound',
      displayName: 'AI 看护摄像头',
      bindingCode: 'AI-CARE-BOUND',
      signalStrength: 88,
      status: 'bound_to_other_family',
      isConnectable: false,
      bindingState: CameraCandidateBindingState.boundToAnotherFamily,
      unavailableReason: '已被其他家庭绑定',
    );
    await _pumpSheet(
      tester,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [unavailable],
    );

    expect(find.text('已被其他家庭绑定'), findsOneWidget);
    expect(find.text('没有可连接设备'), findsOneWidget);
    expect(_primaryButton(tester, '没有可连接设备').onTap, isNull);
  });

  testWidgets('already-bound candidates are skipped for default selection', (
    tester,
  ) async {
    const unavailable = DiscoveredCameraCandidate(
      id: 'nearby-bound',
      displayName: 'AI 看护摄像头',
      bindingCode: 'AI-CARE-BOUND',
      signalStrength: 98,
      status: 'bound_to_other_family',
      isConnectable: false,
      bindingState: CameraCandidateBindingState.boundToAnotherFamily,
      unavailableReason: '已被其他家庭绑定',
    );
    const available = DiscoveredCameraCandidate(
      id: 'nearby-available',
      displayName: 'AI 看护摄像头',
      bindingCode: 'AI-CARE-AVAILABLE',
      signalStrength: 70,
      status: 'ready',
    );
    final adapter = _FakeCameraDiscoveryAdapter(
      candidates: const [unavailable, available],
    );
    await _pumpSheet(tester, adapter: adapter);

    await tester.pump();
    await tester.pump();
    expect(find.text('已被其他家庭绑定'), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey('discoveredCamera_nearby-bound')),
    );
    await tester.pump();
    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(adapter.connectedCandidate?.id, 'nearby-available');
  });

  testWidgets('network setup failed state is represented', (tester) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      connectError: const DeviceException(
        '网络连接失败',
        code: 'network_setup_failed',
      ),
    );
    await _pumpSheet(
      tester,
      adapter: adapter,
      initialPhase: CameraDiscoveryPhase.found,
      initialCandidates: const [_singleCandidate],
    );
    _primaryButton(tester, '连接').onTap!();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('网络连接失败'), findsWidgets);
    expect(find.text('请确认家庭 Wi-Fi 可用。'), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
  });

  testWidgets('closing the sheet stops scanning', (tester) async {
    final adapter = _FakeCameraDiscoveryAdapter(
      scanDelay: const Duration(seconds: 30),
    );
    await _pumpSheet(tester, adapter: adapter);
    await tester.pump();

    await tester.tap(find.byIcon(Icons.close));
    await tester.pump();

    expect(adapter.stopScanCount, greaterThan(0));
  });
}

Future<void> _pumpSheet(
  WidgetTester tester, {
  CameraDiscoveryPhase? initialPhase,
  AddCameraFailureReason? initialFailureReason,
  List<DiscoveredCameraCandidate>? initialCandidates,
  _FakeCameraDiscoveryAdapter? adapter,
}) async {
  SharedPreferences.setMockInitialValues({});
  final preferences = await SharedPreferences.getInstance();
  final adapterValue = adapter ?? _FakeCameraDiscoveryAdapter();
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light,
      home: ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(preferences),
          cameraDiscoveryRepositoryProvider.overrideWithValue(
            CameraDiscoveryRepository(adapter: adapterValue),
          ),
          cameraDiscoveryAdapterProvider.overrideWithValue(adapterValue),
        ],
        child: Scaffold(
          body: AddCameraSheet(
            initialPhaseForTesting: initialPhase,
            initialFailureReasonForTesting: initialFailureReason,
            initialCandidatesForTesting: initialCandidates,
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}

void _expectNoEngineeringCopy() {
  for (final word in const [
    'mock',
    'bindingCode',
    'runtime',
    'provider',
    'backend',
    'RTSP',
    'API',
    'deviceId',
    'Mira',
    '米拉',
    'Mira Guardian',
  ]) {
    expect(find.textContaining(word), findsNothing, reason: word);
  }
}

void _expectSingleCloseButton() {
  expect(find.text('关闭'), findsNothing);
  expect(find.byIcon(Icons.close_rounded), findsNothing);
  expect(find.byIcon(Icons.close), findsOneWidget);
}

AppPrimaryButton _primaryButton(WidgetTester tester, String label) {
  return tester.widget<AppPrimaryButton>(
    find.widgetWithText(AppPrimaryButton, label),
  );
}

const _singleCandidate = DiscoveredCameraCandidate(
  id: 'nearby-single',
  displayName: 'AI 看护摄像头',
  bindingCode: 'AI-CARE-NEARBY-SINGLE',
  signalStrength: 88,
  status: 'ready',
);

const _candidates = [
  DiscoveredCameraCandidate(
    id: 'nearby-desk',
    displayName: '书桌旁摄像头',
    bindingCode: 'AI-CARE-NEARBY-DESK',
    signalStrength: 71,
    status: 'ready',
    roomHint: '书桌旁',
  ),
  DiscoveredCameraCandidate(
    id: 'nearby-bedroom',
    displayName: '儿童房摄像头',
    bindingCode: 'AI-CARE-NEARBY-BEDROOM',
    signalStrength: 94,
    status: 'ready',
    roomHint: '儿童房',
  ),
  DiscoveredCameraCandidate(
    id: 'nearby-living',
    displayName: '客厅摄像头',
    bindingCode: 'AI-CARE-NEARBY-LIVING',
    signalStrength: 63,
    status: 'ready',
    roomHint: '客厅',
  ),
];

class _FakeCameraDiscoveryAdapter implements CameraDiscoveryAdapter {
  _FakeCameraDiscoveryAdapter({
    this.candidates = const [_singleCandidate],
    this.livePreviewAvailable = true,
    this.connectDelay = Duration.zero,
    this.scanDelay = Duration.zero,
    this.permissionStatus = CameraDiscoveryPermissionStatus.ready,
    this.requestPermissionStatus,
    this.connectError,
  });

  final List<DiscoveredCameraCandidate> candidates;
  final bool livePreviewAvailable;
  final Duration connectDelay;
  final Duration scanDelay;
  CameraDiscoveryPermissionStatus permissionStatus;
  final CameraDiscoveryPermissionStatus? requestPermissionStatus;
  final DeviceException? connectError;

  DiscoveredCameraCandidate? connectedCandidate;
  var connectCount = 0;
  var stopScanCount = 0;
  var openSettingsCount = 0;
  var openBluetoothSettingsCount = 0;
  StreamController<CameraDiscoveryResult>? _controller;
  Timer? _scanTimer;

  @override
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus() async {
    return permissionStatus;
  }

  @override
  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions() async {
    return requestPermissionStatus ?? permissionStatus;
  }

  @override
  Future<bool> isBluetoothAvailable() async {
    return permissionStatus != CameraDiscoveryPermissionStatus.bluetoothOff;
  }

  @override
  Stream<CameraDiscoveryResult> startScan() {
    final controller = StreamController<CameraDiscoveryResult>();
    _controller = controller;
    if (scanDelay == Duration.zero) {
      scheduleMicrotask(() => _emitScanResult(controller));
    } else {
      _scanTimer = Timer(scanDelay, () => _emitScanResult(controller));
    }
    return controller.stream;
  }

  void _emitScanResult(StreamController<CameraDiscoveryResult> controller) {
    if (controller.isClosed) return;
    controller.add(
      CameraDiscoveryResult(
        phase: candidates.isEmpty
            ? CameraDiscoveryPhase.notFound
            : CameraDiscoveryPhase.found,
        candidates: candidates,
        failureReason: candidates.isEmpty
            ? AddCameraFailureReason.timeout
            : null,
      ),
    );
    unawaited(controller.close());
  }

  @override
  Future<void> stopScan() async {
    stopScanCount += 1;
    _scanTimer?.cancel();
    _scanTimer = null;
    final controller = _controller;
    _controller = null;
    if (controller != null && !controller.isClosed) {
      await controller.close();
    }
  }

  @override
  Future<GuardianDevice> connectCandidate(
    DiscoveredCameraCandidate candidate,
  ) async {
    connectCount += 1;
    connectedCandidate = candidate;
    if (!candidate.canSelect) {
      throw DeviceException(
        candidate.unavailableReason ?? '这台摄像头暂时无法连接。',
        code: candidate.isOwnedByAnotherFamily
            ? 'already_bound'
            : 'candidate_unavailable',
      );
    }
    if (connectDelay > Duration.zero) {
      await Future<void>.delayed(connectDelay);
    }
    final error = connectError;
    if (error != null) throw error;
    return GuardianDevice(
      id: 'device_${candidate.id}',
      familyId: 'family_test',
      bindingCode: candidate.bindingCode,
      name: candidate.displayName,
      wakeName: '小豆',
      location: candidate.roomHint ?? '家庭空间',
      status: 'online',
      isDefault: true,
      createdAt: 1,
      updatedAt: 1,
    );
  }

  @override
  Future<CameraReadinessResult> checkReadiness(String deviceId) async {
    return CameraReadinessResult(
      livePreviewAvailable: livePreviewAvailable,
      message: livePreviewAvailable ? '实时看护已准备好' : '实时画面暂时不可用',
    );
  }

  @override
  Future<void> openSystemSettings() async {
    openSettingsCount += 1;
  }

  @override
  Future<void> openBluetoothSettings() async {
    openBluetoothSettingsCount += 1;
  }
}

class _FakePermissionProbe implements CameraDiscoveryPermissionProbe {
  const _FakePermissionProbe({required this.status});

  final CameraDiscoveryPermissionStatus status;

  @override
  Future<CameraDiscoveryPermissionStatus> getPermissionStatus() async {
    return status;
  }

  @override
  Future<CameraDiscoveryPermissionStatus> requestRequiredPermissions() async {
    return status;
  }

  @override
  Future<bool> isBluetoothAvailable() async {
    return status != CameraDiscoveryPermissionStatus.bluetoothOff;
  }

  @override
  Future<void> openSystemSettings() async {}

  @override
  Future<void> openBluetoothSettings() async {}
}

class _FakeReactiveBleClient implements ReactiveBleClient {
  _FakeReactiveBleClient({
    this._status = reactive.BleStatus.ready,
    this.devices = const [],
  });

  final reactive.BleStatus _status;
  final List<reactive.DiscoveredDevice> devices;
  var scanCount = 0;

  @override
  reactive.BleStatus get status => _status;

  @override
  Stream<reactive.BleStatus> get statusStream => Stream.value(_status);

  @override
  Stream<reactive.DiscoveredDevice> scanForDevices({
    required List<reactive.Uuid> withServices,
    required reactive.ScanMode scanMode,
    required bool requireLocationServicesEnabled,
  }) async* {
    scanCount += 1;
    for (final device in devices) {
      await Future<void>.delayed(Duration.zero);
      yield device;
    }
  }
}

reactive.DiscoveredDevice _bleDevice({
  required String id,
  required String name,
  required int rssi,
  List<String> serviceUuids = const [],
  List<int> manufacturerData = const [],
}) {
  return reactive.DiscoveredDevice(
    id: id,
    name: name,
    serviceData: const {},
    manufacturerData: Uint8List.fromList(manufacturerData),
    rssi: rssi,
    serviceUuids: serviceUuids.map(reactive.Uuid.parse).toList(growable: false),
    connectable: reactive.Connectable.available,
  );
}
