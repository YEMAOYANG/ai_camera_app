import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/features/devices/application/onvif_auto_discovery_coordinator.dart';
import 'package:warm_sight/src/features/setup/presentation/onvif_pairing_sheet.dart';

/// Runs quiet ONVIF discovery only inside the authenticated application shell.
class OnvifAutoDiscoveryGate extends ConsumerStatefulWidget {
  const OnvifAutoDiscoveryGate({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<OnvifAutoDiscoveryGate> createState() =>
      _OnvifAutoDiscoveryGateState();
}

class _OnvifAutoDiscoveryGateState extends ConsumerState<OnvifAutoDiscoveryGate>
    with WidgetsBindingObserver {
  bool _presentingSheet = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_scan());
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_scan());
    });
  }

  Future<void> _scan({bool force = false}) async {
    if (!mounted || _presentingSheet) return;
    final route = ModalRoute.of(context);
    if (route != null && !route.isCurrent) return;

    final coordinator = ref.read(onvifAutoDiscoveryCoordinatorProvider);
    try {
      final candidates = await coordinator.scan(force: force);
      if (!mounted || candidates.isEmpty || _presentingSheet) return;
      final currentRoute = ModalRoute.of(context);
      if (currentRoute != null && !currentRoute.isCurrent) return;
      if (!coordinator.beginPresentation(candidates)) return;

      _presentingSheet = true;
      OnvifPairingOutcome? outcome;
      try {
        outcome = await showOnvifPairingSheet(context, candidates: candidates);
      } finally {
        coordinator.endPresentation();
        _presentingSheet = false;
      }
      if (!mounted || outcome != OnvifPairingOutcome.rediscover) return;
      coordinator.allowRediscovery(candidates);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        unawaited(_scan(force: true));
      });
    } catch (_) {
      // Automatic discovery stays silent when the LAN or backend is unavailable.
      // Manual device addition remains available from device management.
    }
  }

  @override
  Widget build(BuildContext context) {
    // Keep the session-scoped coordinator alive only while the authenticated
    // shell exists. Logging out disposes its cooldown and dedupe memory.
    ref.watch(onvifAutoDiscoveryCoordinatorProvider);
    return widget.child;
  }
}
