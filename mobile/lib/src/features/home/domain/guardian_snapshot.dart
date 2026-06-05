enum AttentionLevel { normal, watch, urgent }

class GuardianSnapshot {
  const GuardianSnapshot({
    required this.childName,
    required this.location,
    required this.activity,
    required this.currentTask,
    required this.nextCareAction,
    required this.device,
    required this.pendingReviews,
    required this.tasks,
    required this.safetyEvents,
    required this.familyMembers,
  });

  factory GuardianSnapshot.demo() {
    return GuardianSnapshot(
      childName: '小宇',
      location: '书桌区',
      activity: '数学作业进行中',
      currentTask: '数学练习 25 分钟',
      nextCareAction: '19:35 进入 5 分钟休息',
      device: const DeviceSummary(
        name: '客厅设备',
        online: true,
        privacyMode: false,
        audioEnabled: true,
        cameraEnabled: true,
      ),
      pendingReviews: const [
        PendingReview(
          title: '作业证据待确认',
          detail: 'AI 已识别 2 张桌面截图，置信度 86%',
          level: AttentionLevel.watch,
        ),
        PendingReview(
          title: '奖励兑换申请',
          detail: '小宇申请兑换 20 分钟亲子游戏',
          level: AttentionLevel.normal,
        ),
      ],
      tasks: const [
        CareTask(
          title: '数学作业',
          timeLabel: '19:00 - 19:35',
          status: '进行中',
          points: 5,
          evidenceRequired: true,
        ),
        CareTask(
          title: '检查小书包',
          timeLabel: '20:10',
          status: '未开始',
          points: 3,
          evidenceRequired: false,
        ),
        CareTask(
          title: '睡前洗漱',
          timeLabel: '21:00',
          status: '待提醒',
          points: 2,
          evidenceRequired: false,
        ),
      ],
      safetyEvents: const [
        SafetyEvent(
          title: '门口声音',
          timeLabel: '18:42',
          status: '已记录',
          level: AttentionLevel.normal,
        ),
        SafetyEvent(
          title: '离座过久',
          timeLabel: '19:18',
          status: '已温和提醒',
          level: AttentionLevel.watch,
        ),
      ],
      familyMembers: const [
        FamilyMember(name: '妈妈', role: '管理员', active: true),
        FamilyMember(name: '爸爸', role: '监护人', active: true),
        FamilyMember(name: '奶奶', role: '临时查看者', active: false),
      ],
    );
  }

  final String childName;
  final String location;
  final String activity;
  final String currentTask;
  final String nextCareAction;
  final DeviceSummary device;
  final List<PendingReview> pendingReviews;
  final List<CareTask> tasks;
  final List<SafetyEvent> safetyEvents;
  final List<FamilyMember> familyMembers;
}

class DeviceSummary {
  const DeviceSummary({
    required this.name,
    required this.online,
    required this.privacyMode,
    required this.audioEnabled,
    required this.cameraEnabled,
  });

  final String name;
  final bool online;
  final bool privacyMode;
  final bool audioEnabled;
  final bool cameraEnabled;
}

class PendingReview {
  const PendingReview({
    required this.title,
    required this.detail,
    required this.level,
  });

  final String title;
  final String detail;
  final AttentionLevel level;
}

class CareTask {
  const CareTask({
    required this.title,
    required this.timeLabel,
    required this.status,
    required this.points,
    required this.evidenceRequired,
  });

  final String title;
  final String timeLabel;
  final String status;
  final int points;
  final bool evidenceRequired;
}

class SafetyEvent {
  const SafetyEvent({
    required this.title,
    required this.timeLabel,
    required this.status,
    required this.level,
  });

  final String title;
  final String timeLabel;
  final String status;
  final AttentionLevel level;
}

class FamilyMember {
  const FamilyMember({
    required this.name,
    required this.role,
    required this.active,
  });

  final String name;
  final String role;
  final bool active;
}
