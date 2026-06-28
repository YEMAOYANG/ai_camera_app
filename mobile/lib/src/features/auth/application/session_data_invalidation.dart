import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/care/application/parent_review_realtime.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/setup/application/setup_draft.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';

void invalidateAuthenticatedSessionData(WidgetRef ref) {
  _invalidateAuthenticatedSessionData(ref);
}

void invalidateAuthenticatedSessionDataFromRef(Ref ref) {
  _invalidateAuthenticatedSessionData(ref);
}

void _invalidateAuthenticatedSessionData(dynamic ref) {
  ref.invalidate(setupDraftProvider);

  ref.invalidate(profileSummaryProvider);
  ref.invalidate(familyMembersProvider);
  ref.invalidate(familyInvitationsProvider);
  ref.invalidate(familyCodeProvider);
  ref.invalidate(currentChildProvider);
  ref.invalidate(emergencyContactsProvider);
  ref.invalidate(accountProfileProvider);
  ref.invalidate(accountSecurityProvider);
  ref.invalidate(subscriptionStatusProvider);
  ref.invalidate(dailyReportProvider);
  ref.invalidate(weeklyReportProvider);
  ref.invalidate(growthMomentsProvider);

  ref.invalidate(todayTasksProvider);
  ref.invalidate(taskListProvider);
  ref.invalidate(taskWeekProvider);
  ref.invalidate(taskDetailProvider);
  ref.invalidate(taskEventsProvider);
  ref.invalidate(taskTemplatesProvider);

  ref.invalidate(pointsSummaryProvider);
  ref.invalidate(rewardItemsProvider);
  ref.invalidate(rewardRedemptionsProvider);
  ref.invalidate(rewardsSummaryProvider);
  ref.invalidate(rewardDetailProvider);

  ref.invalidate(devicesProvider);
  ref.invalidate(selectedDeviceIdProvider);
  ref.invalidate(selectedDeviceProvider);
  ref.invalidate(primaryDeviceOverviewProvider);
  ref.invalidate(primaryFirmwareStatusProvider);
  ref.invalidate(deviceOverviewProvider);

  ref.invalidate(cameraHealthProvider);
  ref.invalidate(cameraRuntimeProvider);
  ref.invalidate(cameraStatusProvider);
  ref.invalidate(cameraMonitorStatusProvider);
  ref.read(cameraMonitorOverrideProvider.notifier).state = null;
  ref.invalidate(cameraSnapshotProvider);
  ref.invalidate(cameraEventsProvider);
  ref.invalidate(liveCareStatusProvider);

  ref.invalidate(careCapabilitiesProvider);
  ref.invalidate(routineWindowsProvider);
  ref.invalidate(careSummaryProvider);
  ref.invalidate(careReminderEventsProvider);
  ref.read(pendingParentReviewsOverrideProvider.notifier).state =
      const <ParentReviewItem>[];
}
