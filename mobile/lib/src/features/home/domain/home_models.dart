import 'package:warm_sight/src/shared/widgets/status_chip.dart';

enum HomePrimaryCtaKind { pendingActions, connectCamera, checkDevice, none }

enum HomeChipKind { device, stage, pending, rhythm, profile }

enum RhythmNodeState { current, upcoming, completed, muted }

enum HomeRhythmMode { rhythm, review, empty }

enum PendingItemKind { task, redemption }

enum PendingItemAction {
  confirmTask,
  reviewMissedTask,
  fulfillReward,
  checkDevice,
}

class HomeChipSpec {
  const HomeChipSpec({
    required this.kind,
    required this.label,
    required this.tone,
  });

  final HomeChipKind kind;
  final String label;
  final StatusTone tone;
}

class PendingItem {
  const PendingItem({
    required this.kind,
    required this.action,
    required this.id,
    required this.title,
    required this.detail,
    required this.routePath,
  });

  final PendingItemKind kind;
  final PendingItemAction action;
  final String id;
  final String title;
  final String detail;
  final String routePath;
}

class RhythmNode {
  const RhythmNode({
    required this.taskId,
    required this.timeLabel,
    required this.title,
    required this.subtitle,
    required this.statusLabel,
    required this.state,
    required this.tone,
  });

  final String taskId;
  final String timeLabel;
  final String title;
  final String subtitle;
  final String statusLabel;
  final RhythmNodeState state;
  final StatusTone tone;
}

class RecentObservationCopy {
  const RecentObservationCopy({
    required this.headline,
    required this.detail,
    this.reminderNote,
    this.visible = true,
    this.showActions = false,
  });

  final String headline;
  final String detail;
  final String? reminderNote;
  final bool visible;
  final bool showActions;
}

class HabitFocusCopy {
  const HabitFocusCopy({
    required this.headerTime,
    required this.headerTitle,
    required this.title,
    required this.detail,
    required this.chips,
  });

  final String headerTime;
  final String headerTitle;
  final String title;
  final String detail;
  final List<HomeChipSpec> chips;
}

class HomePrimaryCta {
  const HomePrimaryCta({
    required this.kind,
    required this.label,
    this.routePath,
  });

  final HomePrimaryCtaKind kind;
  final String label;
  final String? routePath;
}

class HomeSummary {
  const HomeSummary({
    required this.isLoading,
    required this.hasNoDevice,
    required this.hasNoChild,
    required this.deviceIssue,
    required this.deviceOnline,
    required this.cameraOnline,
    required this.pendingCount,
    required this.habitFocus,
    required this.rhythmMode,
    required this.rhythmNodes,
    required this.pendingItems,
    required this.recentObservation,
    required this.primaryCta,
    required this.showLiveCareLink,
  });

  final bool isLoading;
  final bool hasNoDevice;
  final bool hasNoChild;
  final bool deviceIssue;
  final bool deviceOnline;
  final bool cameraOnline;
  final int pendingCount;
  final HabitFocusCopy habitFocus;
  final HomeRhythmMode rhythmMode;
  final List<RhythmNode> rhythmNodes;
  final List<PendingItem> pendingItems;
  final RecentObservationCopy recentObservation;
  final HomePrimaryCta primaryCta;
  final bool showLiveCareLink;
}
