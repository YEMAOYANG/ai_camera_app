import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/application/onvif_auto_discovery_coordinator.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/devices/presentation/onvif_auto_discovery_gate.dart';
import 'package:warm_sight/src/features/setup/presentation/onvif_pairing_sheet.dart';

void main() {
  testWidgets('authenticated shell gate opens one automatic discovery sheet', (
    tester,
  ) async {
    var loadCount = 0;
    final coordinator = OnvifAutoDiscoveryCoordinator(
      loadCandidates: () async {
        loadCount++;
        return [_candidate()];
      },
    );
    final router = GoRouter(
      initialLocation: '/home',
      routes: [
        ShellRoute(
          builder: (_, _, child) => OnvifAutoDiscoveryGate(child: child),
          routes: [
            GoRoute(
              path: '/home',
              builder: (_, _) => const Scaffold(body: Text('首页')),
            ),
          ],
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          onvifAutoDiscoveryCoordinatorProvider.overrideWithValue(coordinator),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('发现待添加设备：1 个'), findsOneWidget);
    expect(find.textContaining('ONVIF'), findsNothing);
    expect(loadCount, 1);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(loadCount, 1);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();

    expect(find.text('发现待添加设备：1 个'), findsNothing);
    expect(loadCount, 1);
  });

  testWidgets('logging out resets automatic discovery dedupe state', (
    tester,
  ) async {
    final authenticated = ValueNotifier<bool>(true);
    addTearDown(authenticated.dispose);
    var coordinatorCreateCount = 0;
    var loadCount = 0;

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          onvifAutoDiscoveryCoordinatorProvider.overrideWith((ref) {
            coordinatorCreateCount++;
            return OnvifAutoDiscoveryCoordinator(
              loadCandidates: () async {
                loadCount++;
                return [_candidate()];
              },
            );
          }),
        ],
        child: MaterialApp(
          home: ValueListenableBuilder<bool>(
            valueListenable: authenticated,
            builder: (_, isAuthenticated, _) {
              return isAuthenticated
                  ? const OnvifAutoDiscoveryGate(
                      child: Scaffold(body: Text('首页')),
                    )
                  : const Scaffold(body: Text('登录页'));
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('发现待添加设备：1 个'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    authenticated.value = false;
    await tester.pumpAndSettle();
    expect(find.text('登录页'), findsOneWidget);

    authenticated.value = true;
    await tester.pumpAndSettle();
    expect(find.text('发现待添加设备：1 个'), findsOneWidget);
    expect(coordinatorCreateCount, 2);
    expect(loadCount, 2);
  });

  testWidgets('protocol-like device labels are replaced with customer copy', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: OnvifPairingSheet(candidates: [_protocolNamedCandidate()]),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final visibleCopy = tester
        .widgetList<Text>(find.byType(Text))
        .map((widget) => widget.data ?? '')
        .join(' ')
        .toLowerCase();
    expect(visibleCopy, isNot(contains('onvif')));
    expect(visibleCopy, isNot(contains('rtsp')));
    expect(find.text('智能摄像机'), findsWidgets);
  });

  testWidgets('pairing sheet submits device details without credential input', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    Map<String, dynamic>? pairingBody;
    final dio = Dio(BaseOptions(baseUrl: 'https://example.test'));
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          pairingBody = Map<String, dynamic>.from(options.data as Map);
          handler.resolve(
            Response(
              requestOptions: options,
              data: {
                'ok': true,
                'device': _device(),
                'defaultDevice': _device(),
                'connection': {
                  'verified': true,
                  'capabilities': {
                    'onvif': true,
                    'rtsp': true,
                    'ptz': false,
                    'audio': true,
                  },
                },
              },
            ),
          );
        },
      ),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sharedPreferencesProvider.overrideWithValue(preferences),
          deviceRepositoryProvider.overrideWithValue(
            DeviceRepository(apiClient: ApiClient(dio)),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: Builder(
            builder: (context) {
              return Scaffold(
                body: TextButton(
                  onPressed: () => showOnvifPairingSheet(
                    context,
                    candidates: [_candidate()],
                  ),
                  child: const Text('打开'),
                ),
              );
            },
          ),
        ),
      ),
    );

    await tester.tap(find.text('打开'));
    await tester.pumpAndSettle();
    expect(find.text('发现待添加设备：1 个'), findsOneWidget);

    await tester.tap(find.text('添加'));
    await tester.pumpAndSettle();
    final fields = find.byType(TextField);
    expect(fields, findsNWidgets(2));
    expect(find.byKey(const ValueKey('onvif_username_field')), findsNothing);
    expect(find.byKey(const ValueKey('onvif_password_field')), findsNothing);

    await tester.enterText(
      find.descendant(
        of: find.byKey(const ValueKey('onvif_location_field')),
        matching: find.byType(TextField),
      ),
      '儿童房',
    );
    await tester.tap(find.text('一键添加'));
    await tester.pumpAndSettle();

    expect(pairingBody, isNot(contains('username')));
    expect(pairingBody, isNot(contains('password')));
    expect(pairingBody?['name'], '智能摄像机');
    expect(pairingBody?['location'], '儿童房');
    expect(find.text('发现待添加设备：1 个'), findsNothing);
    expect(
      preferences.getString(selectedDeviceIdPreferenceKey),
      'paired-device',
    );
  });
}

OnvifDiscoveryCandidate _candidate() {
  return const OnvifDiscoveryCandidate(
    id: 'onvif-t62',
    discoveryToken: 'temporary-token',
    deviceUniqueId: 'uuid:t62',
    displayName: 'T62',
    requiresCredentials: false,
    supported: true,
    bindingState: 'available',
    capabilities: OnvifDeviceCapabilities(
      onvif: true,
      rtsp: true,
      ptz: false,
      audio: true,
    ),
    expiresAt: null,
    model: 'T62',
  );
}

OnvifDiscoveryCandidate _protocolNamedCandidate() {
  return const OnvifDiscoveryCandidate(
    id: 'protocol-camera',
    discoveryToken: 'temporary-token',
    deviceUniqueId: 'uuid:protocol-camera',
    displayName: 'ONVIF Camera',
    requiresCredentials: false,
    supported: true,
    bindingState: 'available',
    capabilities: OnvifDeviceCapabilities(
      onvif: true,
      rtsp: true,
      ptz: false,
      audio: true,
    ),
    expiresAt: null,
    model: 'RTSP / ONVIF Camera',
  );
}

Map<String, Object?> _device() {
  return {
    'id': 'paired-device',
    'familyId': 'family-test',
    'bindingCode': 'onvif:uuid:t62',
    'name': '智能摄像机',
    'wakeName': '小暖',
    'location': '儿童房',
    'status': 'online',
    'isDefault': true,
    'createdAt': 1,
    'updatedAt': 2,
    'unboundAt': null,
  };
}
