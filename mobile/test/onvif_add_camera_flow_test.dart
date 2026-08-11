import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/devices/application/onvif_auto_discovery_coordinator.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/setup/presentation/add_camera_sheet.dart';

void main() {
  testWidgets(
    'searching sheet shrink-wraps instead of filling its height cap',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final search = Completer<List<OnvifDiscoveryCandidate>>();
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () => search.future,
      );

      await _pumpLauncher(tester, coordinator);
      await tester.tap(find.text('添加摄像头'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final sheet = find.byKey(const ValueKey('onvif_manual_discovery_sheet'));
      expect(sheet, findsOneWidget);
      expect(tester.getSize(sheet).height, lessThanOrEqualTo(430));
      expect(tester.getBottomLeft(sheet).dy, closeTo(844, 1));

      search.complete(const []);
      await tester.pumpAndSettle();

      expect(find.text('没有找到摄像头'), findsOneWidget);
      expect(find.text('重新搜索'), findsOneWidget);
      expect(find.text('按 IP 地址搜索'), findsNothing);
      expect(find.text('添加蓝牙摄像头'), findsNothing);
      expect(find.textContaining('ONVIF'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'manual camera entry finds a nearby camera without protocol copy',
    (tester) async {
      var loadCount = 0;
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () async {
          loadCount++;
          return [_candidate()];
        },
      );

      await _pumpLauncher(tester, coordinator);
      await tester.tap(find.text('添加摄像头'));
      await tester.pumpAndSettle();

      expect(loadCount, 1);
      expect(find.text('发现待添加设备：1 个'), findsOneWidget);
      expect(find.text('添加蓝牙摄像头'), findsNothing);
      expect(find.textContaining('请打开蓝牙'), findsNothing);
      expect(find.textContaining('ONVIF'), findsNothing);
    },
  );
}

Future<void> _pumpLauncher(
  WidgetTester tester,
  OnvifAutoDiscoveryCoordinator coordinator,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        onvifAutoDiscoveryCoordinatorProvider.overrideWithValue(coordinator),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: Builder(
          builder: (context) {
            return Scaffold(
              body: TextButton(
                onPressed: () => showAddCameraSheet(context),
                child: const Text('添加摄像头'),
              ),
            );
          },
        ),
      ),
    ),
  );
}

OnvifDiscoveryCandidate _candidate() {
  return const OnvifDiscoveryCandidate(
    id: 'onvif-t62',
    discoveryToken: 'temporary-token',
    deviceUniqueId: 'uuid:t62',
    displayName: 'T62',
    requiresCredentials: true,
    supported: true,
    bindingState: 'available',
    capabilities: OnvifDeviceCapabilities(
      onvif: true,
      rtsp: true,
      ptz: false,
      audio: true,
    ),
    expiresAt: null,
    manufacturer: 'Vatilon',
    model: 'T62',
  );
}
