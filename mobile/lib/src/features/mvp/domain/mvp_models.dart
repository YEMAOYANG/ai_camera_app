import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class GuardianMvpSnapshot {
  const GuardianMvpSnapshot({
    required this.child,
    required this.device,
    required this.aiSummary,
    required this.nextAction,
    required this.pendingItems,
    required this.tasks,
    required this.alerts,
    required this.familyMembers,
    required this.settings,
  });

  final ChildProfileSummary child;
  final GuardianDeviceSummary device;
  final String aiSummary;
  final String nextAction;
  final List<PendingCareItem> pendingItems;
  final List<MvpTask> tasks;
  final List<MvpAlert> alerts;
  final List<MvpFamilyMember> familyMembers;
  final List<MvpSettingEntry> settings;

  MvpTask taskById(String id) {
    return tasks.firstWhere((task) => task.id == id, orElse: () => tasks.first);
  }
}

class ChildProfileSummary {
  const ChildProfileSummary({
    required this.name,
    required this.stage,
    required this.grade,
    required this.location,
    required this.currentState,
    required this.todayFocus,
  });

  final String name;
  final String stage;
  final String grade;
  final String location;
  final String currentState;
  final String todayFocus;
}

class GuardianDeviceSummary {
  const GuardianDeviceSummary({
    required this.name,
    required this.room,
    required this.online,
    required this.connectionLabel,
    required this.networkLabel,
    required this.privacyLightOn,
    required this.cameraEnabled,
    required this.microphoneEnabled,
    required this.lastOnlineLabel,
  });

  final String name;
  final String room;
  final bool online;
  final String connectionLabel;
  final String networkLabel;
  final bool privacyLightOn;
  final bool cameraEnabled;
  final bool microphoneEnabled;
  final String lastOnlineLabel;
}

class PendingCareItem {
  const PendingCareItem({
    required this.title,
    required this.detail,
    required this.actionLabel,
    required this.tone,
    required this.taskId,
  });

  final String title;
  final String detail;
  final String actionLabel;
  final StatusTone tone;
  final String? taskId;
}

enum MvpTaskStatus {
  pendingStart('待开始', StatusTone.neutral),
  running('进行中', StatusTone.success),
  needsConfirmation('待确认', StatusTone.warning),
  completed('已完成', StatusTone.success),
  abnormal('异常', StatusTone.danger);

  const MvpTaskStatus(this.label, this.tone);

  final String label;
  final StatusTone tone;
}

class MvpTask {
  const MvpTask({
    required this.id,
    required this.title,
    required this.type,
    required this.timeLabel,
    required this.durationLabel,
    required this.status,
    required this.points,
    required this.evidence,
    required this.aiAdvice,
    required this.nextStep,
  });

  final String id;
  final String title;
  final String type;
  final String timeLabel;
  final String durationLabel;
  final MvpTaskStatus status;
  final int points;
  final TaskEvidence evidence;
  final String aiAdvice;
  final String nextStep;
}

class TaskEvidence {
  const TaskEvidence({
    required this.summary,
    required this.confidenceLabel,
    required this.leaveSeatCount,
    required this.parentDecision,
  });

  final String summary;
  final String confidenceLabel;
  final int leaveSeatCount;
  final String parentDecision;
}

enum AlertState {
  unread('未读', StatusTone.danger),
  read('已读', StatusTone.neutral),
  processing('处理中', StatusTone.warning),
  handled('已处理', StatusTone.success),
  falseAlarm('误报', StatusTone.neutral);

  const AlertState(this.label, this.tone);

  final String label;
  final StatusTone tone;
}

class MvpAlert {
  const MvpAlert({
    required this.id,
    required this.title,
    required this.timeLabel,
    required this.summary,
    required this.level,
    required this.state,
    required this.suggestedAction,
  });

  final String id;
  final String title;
  final String timeLabel;
  final String summary;
  final String level;
  final AlertState state;
  final String suggestedAction;
}

class MvpFamilyMember {
  const MvpFamilyMember({
    required this.name,
    required this.role,
    required this.permission,
    required this.notifyLabel,
  });

  final String name;
  final String role;
  final String permission;
  final String notifyLabel;
}

class MvpSettingEntry {
  const MvpSettingEntry({
    required this.title,
    required this.subtitle,
    required this.kind,
  });

  final String title;
  final String subtitle;
  final MvpSettingKind kind;
}

enum MvpSettingKind {
  family,
  child,
  device,
  aiRules,
  privacy,
  userAgreement,
  privacyPolicy,
  logout,
}
