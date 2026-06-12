import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/application/reward_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_repository.dart';

void invalidateAuthenticatedSessionData(WidgetRef ref) {
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

  ref.invalidate(pointsSummaryProvider);
  ref.invalidate(rewardItemsProvider);
  ref.invalidate(rewardRedemptionsProvider);
  ref.invalidate(rewardsSummaryProvider);
  ref.invalidate(rewardDetailProvider);

  ref.invalidate(devicesProvider);
  ref.invalidate(primaryDeviceOverviewProvider);
  ref.invalidate(primaryFirmwareStatusProvider);
  ref.invalidate(deviceOverviewProvider);

  ref.invalidate(cameraHealthProvider);
  ref.invalidate(cameraRuntimeProvider);
  ref.invalidate(cameraStatusProvider);
  ref.invalidate(cameraMonitorStatusProvider);
  ref.invalidate(cameraSnapshotProvider);
  ref.invalidate(cameraEventsProvider);
  ref.invalidate(liveCareStatusProvider);
}
