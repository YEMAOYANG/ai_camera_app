import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/devices/application/onvif_auto_discovery_coordinator.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';

void main() {
  test(
    'filters unavailable devices and deduplicates a physical camera',
    () async {
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () async => [
          _candidate(id: 'first', deviceUniqueId: 'uuid:same'),
          _candidate(id: 'duplicate', deviceUniqueId: 'uuid:same'),
          _candidate(
            id: 'unsupported',
            deviceUniqueId: 'uuid:unsupported',
            supported: false,
          ),
          _candidate(
            id: 'bound',
            deviceUniqueId: 'uuid:bound',
            bindingState: 'boundToCurrentFamily',
          ),
        ],
      );

      final discovered = await coordinator.scan();

      expect(discovered.map((candidate) => candidate.id), ['first']);
    },
  );

  test(
    'cooldown and presentation guard prevent repeated automatic sheets',
    () async {
      var now = DateTime(2026, 7, 29, 10);
      var loadCount = 0;
      final candidate = _candidate(id: 'camera', deviceUniqueId: 'uuid:camera');
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () async {
          loadCount++;
          return [candidate];
        },
        cooldown: const Duration(seconds: 45),
        clock: () => now,
      );

      final first = await coordinator.scan();
      expect(first, [candidate]);
      expect(coordinator.beginPresentation(first), isTrue);
      expect(await coordinator.scan(), isEmpty);
      coordinator.endPresentation();

      now = now.add(const Duration(seconds: 20));
      expect(await coordinator.scan(), isEmpty);
      expect(loadCount, 1);

      now = now.add(const Duration(seconds: 30));
      expect(await coordinator.scan(), isEmpty);
      expect(loadCount, 2);
    },
  );

  test(
    'in-flight guard prevents overlapping backend discovery calls',
    () async {
      final completer = Completer<List<OnvifDiscoveryCandidate>>();
      var loadCount = 0;
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () {
          loadCount++;
          return completer.future;
        },
        cooldown: Duration.zero,
      );

      final first = coordinator.scan();
      final second = await coordinator.scan();
      expect(second, isEmpty);
      expect(loadCount, 1);

      completer.complete([
        _candidate(id: 'camera', deviceUniqueId: 'uuid:camera'),
      ]);
      expect(await first, hasLength(1));
    },
  );

  test(
    'manual scan waits for the active automatic discovery request',
    () async {
      final completer = Completer<List<OnvifDiscoveryCandidate>>();
      var loadCount = 0;
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () {
          loadCount++;
          return completer.future;
        },
      );

      final automatic = coordinator.scan();
      final manual = coordinator.scanForManualPairing();
      expect(loadCount, 1);

      final candidate = _candidate(id: 'camera', deviceUniqueId: 'uuid:camera');
      completer.complete([candidate]);

      expect(await automatic, [candidate]);
      expect(await manual, [candidate]);
      expect(loadCount, 1);
    },
  );

  test(
    'manual scan can present a camera dismissed from automatic discovery',
    () async {
      var loadCount = 0;
      final candidate = _candidate(id: 'camera', deviceUniqueId: 'uuid:camera');
      final coordinator = OnvifAutoDiscoveryCoordinator(
        loadCandidates: () async {
          loadCount++;
          return [candidate];
        },
      );

      final automatic = await coordinator.scan();
      expect(coordinator.beginPresentation(automatic), isTrue);
      coordinator.endPresentation();

      expect(await coordinator.scanForManualPairing(), [candidate]);
      expect(loadCount, 2);
    },
  );

  test('manual IP search uses the targeted discovery loader', () async {
    String? receivedTarget;
    final candidate = _candidate(id: 'camera', deviceUniqueId: 'uuid:camera');
    final coordinator = OnvifAutoDiscoveryCoordinator(
      loadCandidates: () async => const [],
      loadTargetedCandidates: (targetIp) async {
        receivedTarget = targetIp;
        return [candidate];
      },
    );

    expect(
      await coordinator.scanForManualPairing(targetIp: '192.168.228.147'),
      [candidate],
    );
    expect(receivedTarget, '192.168.228.147');
  });

  test('an empty automatic result does not block an immediate retry', () async {
    var loadCount = 0;
    final coordinator = OnvifAutoDiscoveryCoordinator(
      loadCandidates: () async {
        loadCount++;
        return const [];
      },
    );

    expect(await coordinator.scan(), isEmpty);
    expect(await coordinator.scan(), isEmpty);
    expect(loadCount, 2);
  });

  test('expired token can explicitly allow a forced rediscovery', () async {
    final candidate = _candidate(id: 'camera', deviceUniqueId: 'uuid:camera');
    final coordinator = OnvifAutoDiscoveryCoordinator(
      loadCandidates: () async => [candidate],
    );

    final first = await coordinator.scan();
    coordinator.beginPresentation(first);
    coordinator.endPresentation();
    coordinator.allowRediscovery(first);

    expect(await coordinator.scan(force: true), [candidate]);
  });
}

OnvifDiscoveryCandidate _candidate({
  required String id,
  required String deviceUniqueId,
  bool supported = true,
  String bindingState = 'available',
}) {
  return OnvifDiscoveryCandidate(
    id: id,
    discoveryToken: 'token-$id',
    deviceUniqueId: deviceUniqueId,
    displayName: '智能摄像机',
    requiresCredentials: true,
    supported: supported,
    bindingState: bindingState,
    capabilities: const OnvifDeviceCapabilities(
      onvif: true,
      rtsp: true,
      ptz: false,
      audio: true,
    ),
    expiresAt: null,
  );
}
