import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
class RefreshGuard {
  bool _inFlight = false;
  var _pendingLight = false;

  Future<void> runLight(Future<void> Function() action) async {
    if (_inFlight) {
      _pendingLight = true;
      return;
    }
    _inFlight = true;
    try {
      do {
        _pendingLight = false;
        await action();
      } while (_pendingLight);
    } finally {
      _inFlight = false;
    }
  }
}

/// 全 App 共享 POST analyze 限频（设备级）。
class MonitorAnalysisGuard {
  MonitorAnalysisGuard({this.minInterval = const Duration(seconds: 3)});

  final Duration minInterval;
  bool _inFlight = false;
  DateTime? _lastHeavyAt;

  bool get isInFlight => _inFlight;

  Future<bool> runHeavy(Future<void> Function() action) async {
    if (_inFlight) return false;
    final last = _lastHeavyAt;
    if (last != null && DateTime.now().difference(last) < minInterval) {
      return false;
    }
    _inFlight = true;
    _lastHeavyAt = DateTime.now();
    try {
      await action();
      return true;
    } finally {
      _inFlight = false;
    }
  }
}

final monitorAnalysisGuardProvider = Provider<MonitorAnalysisGuard>(
  (ref) => MonitorAnalysisGuard(),
);
