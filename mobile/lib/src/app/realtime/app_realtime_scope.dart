import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_helpers.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/features/auth/application/session_data_invalidation.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';

final appRealtimeInvalidationCoordinatorProvider =
    Provider<AppRealtimeInvalidationCoordinator>((ref) {
      final coordinator = AppRealtimeInvalidationCoordinator(ref);
      ref.onDispose(coordinator.dispose);
      return coordinator;
    });

class AppRealtimeScope extends ConsumerStatefulWidget {
  const AppRealtimeScope({required this.child, super.key});

  final Widget child;

  @override
  ConsumerState<AppRealtimeScope> createState() => _AppRealtimeScopeState();
}

class _AppRealtimeScopeState extends ConsumerState<AppRealtimeScope> {
  Timer? _catchUpTimer;
  AppRealtimeConnectionPhase? _lastPhase;

  @override
  void dispose() {
    _catchUpTimer?.cancel();
    super.dispose();
  }

  void _scheduleCatchUpRefresh() {
    _catchUpTimer?.cancel();
    _catchUpTimer = Timer(const Duration(milliseconds: 500), () {
      if (!mounted) return;
      unawaited(refreshAllDomainsSilently(ref));
    });
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(appRealtimeControllerProvider);
    ref.watch(appRealtimeInvalidationCoordinatorProvider);

    ref.listen<AppRealtimeStatus>(appRealtimeStatusProvider, (previous, next) {
      final wasConnected = previous?.phase == AppRealtimeConnectionPhase.connected;
      final isConnected = next.phase == AppRealtimeConnectionPhase.connected;
      if (isConnected && (!wasConnected || _lastPhase != next.phase)) {
        _scheduleCatchUpRefresh();
      }
      _lastPhase = next.phase;
    });

    ref.listen<AsyncValue<TaskRealtimeEvent>>(taskRealtimeProvider, (
      previous,
      next,
    ) {
      final event = next.asData?.value;
      if (event == null) return;
      ref.read(appRealtimeInvalidationCoordinatorProvider).handle(event);
    });
    return widget.child;
  }
}

class AppRealtimeInvalidationCoordinator {
  AppRealtimeInvalidationCoordinator(this._ref);

  final Ref _ref;
  Timer? _taskTimer;
  Timer? _cameraMonitorTimer;
  Timer? _cameraEventsTimer;
  Timer? _cameraStatusTimer;
  Timer? _careBurstTimer;
  final Set<String> _taskIds = <String>{};
  final Set<String> _careTaskIds = <String>{};
  var _disposed = false;
  var _careBurstScheduled = false;
  static const _debounce = Duration(milliseconds: 900);
  static const _cameraObservationDebounce = Duration(milliseconds: 250);
  static const _careBurstDebounce = Duration(milliseconds: 200);

  void handle(TaskRealtimeEvent event) {
    if (_disposed) return;
    if (event.isSessionRevoked) {
      unawaited(_handleSessionRevoked());
      return;
    }
    if (event.isTaskUpdate || event.isTaskStatusChanged) {
      _taskIds.addAll(event.taskIds);
      _scheduleTaskRefresh();
    }
    if (event.isReminderDecisionCreated) {
      applyReminderDecisionRealtimeEvent(_ref, event);
      _scheduleCareBurst(event.observationId);
      _scheduleCameraMonitorRefresh();
    }
    if (event.isCameraObservationUpdated) {
      applyCameraObservationRealtimeEvent(_ref, event);
      final insertedEvent = event.event != null;
      if (insertedEvent) {
        _ref.read(cameraEventsProvider.notifier).handleRealtimeEvent(event);
      }
      _scheduleCareBurst(event.observationId);
      _scheduleCameraMonitorRefresh();
      if (!insertedEvent) {
        _scheduleCameraEventsRefresh();
      }
    }
    if (event.isCameraEventCreated ||
        event.isReminderEventCreated ||
        event.isCameraCommandCreated) {
      _careTaskIds.addAll(event.taskIds);
      final insertedEvent = event.isCameraEventCreated && event.event != null;
      if (insertedEvent || event.event != null) {
        _ref.read(cameraEventsProvider.notifier).handleRealtimeEvent(event);
      }
      if (!insertedEvent) {
        _scheduleCameraEventsRefresh();
      } else {
        unawaited(
          refreshCameraEventsSilently(_ref, skipEventsListRefresh: true),
        );
      }
      _scheduleCareBurst(event.observationId);
    }
    if (event.isCameraStatusChanged) {
      _scheduleCameraStatusRefresh();
    }
  }

  void _scheduleCareBurst(String observationId) {
    if (_disposed) return;
    if (observationId.isNotEmpty) {
    }
    if (_careBurstScheduled) return;
    _careBurstScheduled = true;
    _careBurstTimer?.cancel();
    _careBurstTimer = Timer(_careBurstDebounce, () {
      if (_disposed) return;
      _careBurstScheduled = false;
      unawaited(refreshCareSummarySilently(_ref));
    });
  }

  Future<void> _handleSessionRevoked() async {
    if (_disposed) return;
    await _ref.read(authSessionStoreProvider).clear();
    if (_disposed) return;
    invalidateAuthenticatedSessionDataFromRef(_ref);
  }

  void _scheduleTaskRefresh() {
    if (_disposed) return;
    _taskTimer?.cancel();
    _taskTimer = Timer(_debounce, () {
      if (_disposed) return;
      final ids = List<String>.from(_taskIds);
      _taskIds.clear();
      unawaited(refreshTaskProvidersSilently(_ref, taskIds: ids));
    });
  }

  void _scheduleCameraMonitorRefresh() {
    if (_disposed) return;
    _cameraMonitorTimer?.cancel();
    _cameraMonitorTimer = Timer(_cameraObservationDebounce, () {
      if (_disposed) return;
      unawaited(refreshCameraMonitorSilently(_ref));
    });
  }

  void _scheduleCameraEventsRefresh() {
    if (_disposed) return;
    _cameraEventsTimer?.cancel();
    _cameraEventsTimer = Timer(_cameraObservationDebounce, () {
      if (_disposed) return;
      final ids = List<String>.from(_careTaskIds);
      _careTaskIds.clear();
      unawaited(refreshCameraEventsSilently(_ref, taskIds: ids));
    });
  }

  void _scheduleCameraStatusRefresh() {
    if (_disposed) return;
    _cameraStatusTimer?.cancel();
    _cameraStatusTimer = Timer(_debounce, () {
      if (_disposed) return;
      unawaited(refreshCameraStatusSilently(_ref));
    });
  }

  void dispose() {
    _disposed = true;
    _taskTimer?.cancel();
    _cameraMonitorTimer?.cancel();
    _cameraEventsTimer?.cancel();
    _cameraStatusTimer?.cancel();
    _careBurstTimer?.cancel();
  }
}
