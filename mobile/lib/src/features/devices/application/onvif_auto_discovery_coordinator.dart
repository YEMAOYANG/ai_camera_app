import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';

typedef OnvifDiscoveryLoader = Future<List<OnvifDiscoveryCandidate>> Function();
typedef OnvifTargetedDiscoveryLoader =
    Future<List<OnvifDiscoveryCandidate>> Function(String targetIp);
typedef OnvifDiscoveryClock = DateTime Function();

DateTime _systemOnvifDiscoveryClock() => DateTime.now();

final onvifAutoDiscoveryCoordinatorProvider =
    Provider.autoDispose<OnvifAutoDiscoveryCoordinator>((ref) {
      final repository = ref.watch(deviceRepositoryProvider);
      return OnvifAutoDiscoveryCoordinator(
        loadCandidates: repository.discoverOnvifDevices,
        loadTargetedCandidates: (targetIp) =>
            repository.discoverOnvifDevices(targetIp: targetIp),
      );
    });

/// Keeps automatic ONVIF discovery quiet and predictable for one app session.
///
/// The backend performs WS-Discovery. This coordinator only rate-limits the
/// authenticated API call and prevents the same physical camera from opening
/// more than one automatic sheet.
class OnvifAutoDiscoveryCoordinator {
  OnvifAutoDiscoveryCoordinator({
    required this._loadCandidates,
    this.loadTargetedCandidates,
    this._cooldown = const Duration(seconds: 45),
    this._clock = _systemOnvifDiscoveryClock,
  });

  final OnvifDiscoveryLoader _loadCandidates;
  final OnvifTargetedDiscoveryLoader? loadTargetedCandidates;
  final Duration _cooldown;
  final OnvifDiscoveryClock _clock;
  final Set<String> _presentedKeys = <String>{};

  DateTime? _lastScanStartedAt;
  Future<List<OnvifDiscoveryCandidate>>? _activeScan;
  bool _presentationActive = false;

  bool get scanInFlight => _activeScan != null;
  bool get presentationActive => _presentationActive;

  Future<List<OnvifDiscoveryCandidate>> scan({bool force = false}) async {
    if (_activeScan != null || _presentationActive) return const [];

    final now = _clock();
    final lastScan = _lastScanStartedAt;
    if (!force && lastScan != null && now.difference(lastScan) < _cooldown) {
      return const [];
    }

    _lastScanStartedAt = now;
    final candidates = await _runScan(_loadCandidates);
    if (candidates.isEmpty) {
      // An empty multicast response should not block an immediate manual retry.
      _lastScanStartedAt = null;
    }
    return _availableCandidates(candidates, includePresented: false);
  }

  /// Manual addition may reuse an automatic scan that is already in flight and
  /// may present a camera the user previously dismissed.
  Future<List<OnvifDiscoveryCandidate>> scanForManualPairing({
    String? targetIp,
  }) async {
    final normalizedTarget = targetIp?.trim() ?? '';
    if (normalizedTarget.isNotEmpty) {
      final active = _activeScan;
      if (active != null) await active;
      final targetedLoader = loadTargetedCandidates;
      if (targetedLoader == null) return const [];
      final candidates = await _runScan(() => targetedLoader(normalizedTarget));
      return _availableCandidates(candidates, includePresented: true);
    }

    final candidates = await (_activeScan ?? _runScan(_loadCandidates));
    return _availableCandidates(candidates, includePresented: true);
  }

  bool beginPresentation(List<OnvifDiscoveryCandidate> candidates) {
    if (_presentationActive || candidates.isEmpty) return false;
    _presentationActive = true;
    _presentedKeys.addAll(candidates.map((candidate) => candidate.dedupeKey));
    return true;
  }

  void endPresentation() {
    _presentationActive = false;
  }

  void allowRediscovery(Iterable<OnvifDiscoveryCandidate> candidates) {
    _presentedKeys.removeAll(
      candidates.map((candidate) => candidate.dedupeKey),
    );
    _lastScanStartedAt = null;
  }

  Future<List<OnvifDiscoveryCandidate>> _runScan(
    OnvifDiscoveryLoader loader,
  ) async {
    final active = _activeScan;
    if (active != null) return active;

    final future = loader();
    _activeScan = future;
    try {
      return await future;
    } finally {
      if (identical(_activeScan, future)) {
        _activeScan = null;
      }
    }
  }

  List<OnvifDiscoveryCandidate> _availableCandidates(
    Iterable<OnvifDiscoveryCandidate> candidates, {
    required bool includePresented,
  }) {
    final available = <String, OnvifDiscoveryCandidate>{};
    for (final candidate in candidates) {
      if (!candidate.isAvailable ||
          candidate.isExpired ||
          (!includePresented && _presentedKeys.contains(candidate.dedupeKey))) {
        continue;
      }
      available.putIfAbsent(candidate.dedupeKey, () => candidate);
    }
    return available.values.toList(growable: false);
  }
}
