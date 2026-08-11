import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';

void refreshCameraAfterAdd(WidgetRef ref) {
  ref
    ..invalidate(devicesProvider)
    ..invalidate(primaryDeviceOverviewProvider)
    ..invalidate(selectedDeviceProvider)
    ..invalidate(cameraHealthProvider)
    ..invalidate(cameraRuntimeProvider)
    ..invalidate(cameraStatusProvider)
    ..invalidate(cameraMonitorStatusProvider)
    ..invalidate(cameraSnapshotProvider)
    ..invalidate(cameraEventsProvider)
    ..invalidate(liveCareStatusProvider)
    ..invalidate(profileSummaryProvider)
    ..invalidate(accountProfileProvider);
}
