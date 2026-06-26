import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/storage/auth_session_store.dart';
import 'package:warm_sight/src/features/auth/application/session_data_invalidation.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';

final appRealtimeInvalidationCoordinatorProvider =
    Provider.autoDispose<AppRealtimeInvalidationCoordinator>((ref) {
      final coordinator = AppRealtimeInvalidationCoordinator(ref);
      ref.onDispose(coordinator.dispose);
      return coordinator;
    });

class AppRealtimeScope extends ConsumerWidget {
  const AppRealtimeScope({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(appRealtimeControllerProvider);
    ref.listen<AsyncValue<TaskRealtimeEvent>>(taskRealtimeProvider, (
      previous,
      next,
    ) {
      final event = next.asData?.value;
      if (event == null) return;
      ref.read(appRealtimeInvalidationCoordinatorProvider).handle(event);
    });
    return child;
  }
}

class AppRealtimeInvalidationCoordinator {
  AppRealtimeInvalidationCoordinator(this._ref);

  final Ref _ref;
  Timer? _taskTimer;
  Timer? _cameraMonitorTimer;
  Timer? _cameraEventsTimer;
  Timer? _cameraStatusTimer;
  final Set<String> _taskIds = <String>{};
  final Set<String> _careTaskIds = <String>{};
  var _disposed = false;

  static const _debounce = Duration(milliseconds: 900);
  static const _cameraObservationDebounce = Duration(milliseconds: 250);

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
    if (event.isCameraObservationUpdated) {
      if (event.event != null) {
        _ref.read(cameraEventsProvider.notifier).handleRealtimeEvent(event);
      }
      _scheduleCameraMonitorRefresh();
      _invalidateCareSummary();
    }
    if (event.isCameraEventCreated ||
        event.isReminderEventCreated ||
        event.isCameraCommandCreated) {
      _careTaskIds.addAll(event.taskIds);
      if (event.isCameraEventCreated || event.event != null) {
        _ref.read(cameraEventsProvider.notifier).handleRealtimeEvent(event);
      }
      _scheduleCameraEventsRefresh();
      _invalidateCareSummary();
    }
    if (event.isCameraStatusChanged) {
      _scheduleCameraStatusRefresh();
    }
  }

  Future<void> _handleSessionRevoked() async {
    if (_disposed) return;
    await _ref.read(authSessionStoreProvider).clear();
    if (_disposed) return;
    invalidateAuthenticatedSessionDataFromRef(_ref);
  }

  void _invalidateCareSummary() {
    if (_disposed) return;
    final childId = _ref
        .read(profileSummaryProvider)
        .asData
        ?.value
        .child
        ?.id;
    if (childId != null && childId.isNotEmpty) {
      _ref.invalidate(careSummaryProvider(childId));
    }
  }

  void _scheduleTaskRefresh() {
    if (_disposed) return;
    _taskTimer?.cancel();
    _taskTimer = Timer(_debounce, () {
      if (_disposed) return;
      final ids = List<String>.from(_taskIds);
      _taskIds.clear();
      _ref
        ..invalidate(taskListProvider)
        ..invalidate(todayTasksProvider)
        ..invalidate(taskWeekProvider)
        ..invalidate(pointsSummaryProvider)
        ..invalidate(dailyReportProvider)
        ..invalidate(weeklyReportProvider);
      for (final taskId in ids) {
        _ref
          ..invalidate(taskDetailProvider(taskId))
          ..invalidate(taskEventsProvider(taskId));
      }
    });
  }

  void _scheduleCameraMonitorRefresh() {
    if (_disposed) return;
    _cameraMonitorTimer?.cancel();
    _cameraMonitorTimer = Timer(_cameraObservationDebounce, () {
      if (_disposed) return;
      _ref
        ..invalidate(cameraMonitorStatusProvider)
        ..invalidate(liveCareStatusProvider)
        ..invalidate(dailyReportProvider)
        ..invalidate(weeklyReportProvider);
    });
  }

  void _scheduleCameraEventsRefresh() {
    if (_disposed) return;
    _cameraEventsTimer?.cancel();
    _cameraEventsTimer = Timer(_cameraObservationDebounce, () {
      if (_disposed) return;
      final ids = List<String>.from(_careTaskIds);
      _careTaskIds.clear();
      _ref
        ..invalidate(liveCareStatusProvider)
        ..invalidate(cameraMonitorStatusProvider)
        ..invalidate(dailyReportProvider)
        ..invalidate(weeklyReportProvider);
      unawaited(_ref.read(cameraEventsProvider.notifier).refresh());
      for (final taskId in ids) {
        _ref.invalidate(taskEventsProvider(taskId));
      }
    });
  }

  void _scheduleCameraStatusRefresh() {
    if (_disposed) return;
    _cameraStatusTimer?.cancel();
    _cameraStatusTimer = Timer(_debounce, () {
      if (_disposed) return;
      _ref
        ..invalidate(cameraHealthProvider)
        ..invalidate(cameraStatusProvider)
        ..invalidate(cameraRuntimeProvider)
        ..invalidate(primaryDeviceOverviewProvider);
    });
  }

  void dispose() {
    _disposed = true;
    _taskTimer?.cancel();
    _cameraMonitorTimer?.cancel();
    _cameraEventsTimer?.cancel();
    _cameraStatusTimer?.cancel();
  }
}
