import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/state/async_value_ui.dart';
import 'package:warm_sight/src/core/state/refresh_guard.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/care/application/parent_review_realtime.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/tasks/application/task_realtime_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_week_scope.dart';

/// WS 观察事件携带 lightweight payload 时，立即更新首页 Hero 观察文案。
void applyCameraObservationRealtimeEvent(dynamic ref, TaskRealtimeEvent event) {
  final payload = event.event;
  if (payload == null || payload.isEmpty) return;

  final message = _string(payload['displayMessage']);
  final title = _string(payload['displayTitle']);
  final summary = message.isNotEmpty ? message : title;
  if (summary.isEmpty) return;

  final reliable =
      event.isReliable == true || payload['isReliable'] == true;
  final observedAt = _int(payload['observedAt']) > 0
      ? _int(payload['observedAt'])
      : event.sentAt;

  ref.read(cameraMonitorOverrideProvider.notifier).state = CameraMonitorStatus(
    running: true,
    status: 'observed',
    message: '观察已更新',
    lastObservation: summary,
    lastReminder: '',
    lastObservationObservedAt: observedAt,
    lastObservationReliable: reliable,
    lastObservationDescription: message.isNotEmpty ? message : summary,
  );
}

void applyReminderDecisionRealtimeEvent(dynamic ref, TaskRealtimeEvent event) {
  final review = parentReviewFromRealtimeEvent(event.event);
  if (review == null) return;
  final current = ref.read(pendingParentReviewsOverrideProvider);
  if (current.any((item) => item.id == review.id)) return;
  ref.read(pendingParentReviewsOverrideProvider.notifier).state =
      <ParentReviewItem>[review, ...current];
}

Future<void> refreshCareSummarySilently(dynamic ref) async {
  try {
    final childId = _profileChildId(ref);
    if (childId == null || childId.isEmpty) return;
    await silentRefreshProvider(ref, careSummaryProvider(childId));
    ref.read(pendingParentReviewsOverrideProvider.notifier).state =
        const <ParentReviewItem>[];
  } catch (_) {}
}

String? _profileChildId(dynamic ref) {
  final profileState = ref.read(profileSummaryProvider);
  ProfileSummary? profile;
  if (profileState is AsyncValue<ProfileSummary>) {
    profile = profileState.asData?.value;
  } else if (profileState is ProfileSummary) {
    profile = profileState;
  }
  return profile?.child?.id;
}

Future<void> triggerMonitorAnalysis(
  dynamic ref, {
  String? deviceId,
}) async {
  final guard = ref.read(monitorAnalysisGuardProvider);
  await guard.runHeavy(() async {
    final resolvedDeviceId =
        deviceId ?? ref.read(selectedDeviceProvider).asData?.value?.id;
    final monitor = await ref
        .read(cameraRepositoryProvider)
        .refreshMonitor(deviceId: resolvedDeviceId);
    ref.read(cameraMonitorOverrideProvider.notifier).state = monitor;
  });
}

Future<void> refreshHomeDataSilently(dynamic ref) async {
  await Future.wait([
    silentRefreshProvider(ref, profileSummaryProvider),
    silentRefreshProvider(ref, primaryDeviceOverviewProvider),
    silentRefreshProvider(ref, todayTasksProvider),
    silentRefreshProvider(ref, rewardRedemptionsProvider),
    silentRefreshProvider(ref, cameraHealthProvider),
    silentRefreshProvider(ref, cameraStatusProvider),
    silentRefreshProvider(ref, cameraMonitorStatusProvider),
  ]);
  await refreshCareSummarySilently(ref);
}

Future<void> refreshLiveCareDataSilently(dynamic ref) async {
  await Future.wait([
    silentRefreshProvider(ref, cameraHealthProvider),
    silentRefreshProvider(ref, cameraRuntimeProvider),
    silentRefreshProvider(ref, cameraStatusProvider),
    silentRefreshProvider(ref, cameraMonitorStatusProvider),
    silentRefreshProvider(ref, cameraSnapshotProvider),
    silentRefreshProvider(ref, primaryDeviceOverviewProvider),
  ]);
  await ref.read(cameraEventsProvider.notifier).refresh();
}

Future<void> refreshAllDomainsSilently(dynamic ref) async {
  await Future.wait([
    refreshHomeDataSilently(ref),
    refreshTaskProvidersSilently(ref),
    refreshCameraStatusSilently(ref),
  ]);
}

Future<void> refreshTaskProvidersSilently(
  dynamic ref, {
  List<String> taskIds = const [],
}) async {
  final activeQuery = ref.read(activeTaskWeekQueryProvider);
  final childId = _profileChildId(ref);
  final weekQuery = activeQuery ?? fallbackTaskWeekQuery(childId);
  await Future.wait([
    silentRefreshProvider(ref, taskListProvider),
    silentRefreshProvider(ref, todayTasksProvider),
    silentRefreshProvider(ref, pointsSummaryProvider),
    silentRefreshProvider(ref, dailyReportProvider),
    silentRefreshProvider(ref, weeklyReportProvider),
    if (weekQuery != null)
      silentRefreshProvider(ref, taskWeekProvider(weekQuery)),
    ...taskIds.map((id) => silentRefreshProvider(ref, taskDetailProvider(id))),
    ...taskIds.map((id) => silentRefreshProvider(ref, taskEventsProvider(id))),
  ]);
}

Future<void> refreshCameraMonitorSilently(dynamic ref) async {
  await silentRefreshProvider(ref, cameraMonitorStatusProvider);
  final server = ref.read(cameraMonitorStatusProvider);
  final override = ref.read(cameraMonitorOverrideProvider);
  if (override != null && server is AsyncValue<CameraMonitorStatus>) {
    final serverStatus = server.asData?.value;
    if (serverStatus != null) {
      final serverAt = serverStatus.lastObservationObservedAt ?? 0;
      final overrideAt = override.lastObservationObservedAt ?? 0;
      if (overrideAt <= serverAt) {
        ref.read(cameraMonitorOverrideProvider.notifier).state = null;
      }
    }
  }
  await Future.wait([
    silentRefreshProvider(ref, dailyReportProvider),
    silentRefreshProvider(ref, weeklyReportProvider),
  ]);
}

Future<void> refreshCameraStatusSilently(dynamic ref) async {
  await Future.wait([
    silentRefreshProvider(ref, cameraHealthProvider),
    silentRefreshProvider(ref, cameraStatusProvider),
    silentRefreshProvider(ref, cameraRuntimeProvider),
    silentRefreshProvider(ref, primaryDeviceOverviewProvider),
  ]);
}

Future<void> refreshCameraEventsSilently(
  dynamic ref, {
  List<String> taskIds = const [],
  bool skipEventsListRefresh = false,
}) async {
  if (!skipEventsListRefresh) {
    unawaited(ref.read(cameraEventsProvider.notifier).refresh());
  }
  await Future.wait([
    silentRefreshProvider(ref, dailyReportProvider),
    silentRefreshProvider(ref, weeklyReportProvider),
    ...taskIds.map((id) => silentRefreshProvider(ref, taskEventsProvider(id))),
  ]);
}

String _string(Object? value) {
  if (value is String) return value.trim();
  return '';
}

int _int(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? 0;
  return 0;
}
