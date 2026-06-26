import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/domain/reward_models.dart';
import 'package:warm_sight/src/features/tasks/domain/task_models.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

const taskDetailRoutePrefix = '/tasks/detail';
const rewardsRoutePath = '/rewards';
const liveRoutePath = '/live';

class HomeSummaryInput {
  const HomeSummaryInput({
    required this.now,
    this.profile,
    this.profileLoading = false,
    this.deviceOverview,
    this.deviceLoading = false,
    this.deviceError = false,
    this.cameraHealth,
    this.cameraHealthLoading = false,
    this.cameraHealthError = false,
    this.cameraStatus,
    this.cameraStatusLoading = false,
    this.cameraStatusError = false,
    this.cameraMonitor,
    this.cameraMonitorLoading = false,
    this.tasks,
    this.tasksLoading = false,
    this.tasksError = false,
    this.redemptions,
    this.redemptionsLoading = false,
  });

  final DateTime now;
  final ProfileSummary? profile;
  final bool profileLoading;
  final DeviceOverview? deviceOverview;
  final bool deviceLoading;
  final bool deviceError;
  final CameraHealth? cameraHealth;
  final bool cameraHealthLoading;
  final bool cameraHealthError;
  final CameraStatus? cameraStatus;
  final bool cameraStatusLoading;
  final bool cameraStatusError;
  final CameraMonitorStatus? cameraMonitor;
  final bool cameraMonitorLoading;
  final List<GuardianTask>? tasks;
  final bool tasksLoading;
  final bool tasksError;
  final List<RewardRedemption>? redemptions;
  final bool redemptionsLoading;
}

HomeSummary buildHomeSummary(HomeSummaryInput input) {
  final hasNoDevice =
      input.deviceOverview == null &&
      !input.deviceLoading &&
      !input.deviceError;
  final deviceOnline = hasNoDevice
      ? false
      : input.deviceOverview?.isOnline ?? input.cameraStatus?.isOnline ?? false;
  final cameraOnline = hasNoDevice
      ? false
      : input.cameraStatus?.isOnline ?? input.cameraHealth?.reachable ?? false;
  final deviceIssue = hasDeviceIssue(input);
  final localTasks = localTodayTasks(input.tasks, input.now);
  final tasksReady = localTasks != null;
  final currentTask =
      input.cameraStatus?.currentTask ?? currentTaskFromToday(localTasks);
  final pendingItems = buildPendingItems(
    tasks: localTasks,
    redemptions: input.redemptions,
    deviceIssue: deviceIssue,
    canManageTasks: input.profile?.can('manage_tasks') ?? false,
    canConfirmTasks: input.profile?.can('confirm_tasks') ?? false,
  );
  final pendingCount = pendingItems.length;
  final isLoading =
      input.profileLoading ||
      input.deviceLoading ||
      input.cameraHealthLoading ||
      input.cameraStatusLoading ||
      input.cameraMonitorLoading ||
      (!tasksReady && input.tasksLoading);
  final hasNoChild = !input.profileLoading && input.profile?.child == null;
  final heroObservation =
      !isLoading &&
          !hasNoChild &&
          !hasNoDevice &&
          !deviceIssue &&
          input.cameraMonitor?.hasCurrentReliableObservation == true
      ? meaningfulObservationText(input.cameraMonitor?.lastObservation)
      : null;
  final rhythmNodes = buildRhythmNodes(localTasks, input.now);

  return HomeSummary(
    isLoading: isLoading,
    hasNoDevice: hasNoDevice,
    hasNoChild: hasNoChild,
    deviceIssue: deviceIssue,
    deviceOnline: deviceOnline,
    cameraOnline: cameraOnline,
    pendingCount: pendingCount,
    habitFocus: buildHabitFocus(
      input: input,
      hasNoDevice: hasNoDevice,
      deviceOnline: deviceOnline,
      cameraOnline: cameraOnline,
      deviceIssue: deviceIssue,
      currentTask: currentTask,
      localTasks: localTasks,
      pendingItems: pendingItems,
      pendingCount: pendingCount,
      isLoading: isLoading,
      hasNoChild: hasNoChild,
    ),
    rhythmMode: resolveRhythmMode(localTasks, rhythmNodes),
    rhythmNodes: rhythmNodes,
    pendingItems: pendingItems,
    recentObservation: buildRecentObservationCopy(
      input: input,
      hasNoDevice: hasNoDevice,
      deviceIssue: deviceIssue,
      heroObservation: heroObservation,
      currentTask: currentTask,
      localTasks: localTasks,
      pendingCount: pendingCount,
      isLoading: isLoading,
    ),
    primaryCta: buildPrimaryCta(
      hasNoDevice: hasNoDevice,
      deviceIssue: deviceIssue,
      pendingItems: pendingItems,
      pendingCount: pendingCount,
    ),
    showLiveCareLink: false,
  );
}

HabitFocusCopy buildHabitFocus({
  required HomeSummaryInput input,
  required bool hasNoDevice,
  required bool deviceOnline,
  required bool cameraOnline,
  required bool deviceIssue,
  required GuardianTask? currentTask,
  required List<GuardianTask>? localTasks,
  required List<PendingItem> pendingItems,
  required int pendingCount,
  required bool isLoading,
  required bool hasNoChild,
}) {
  final childName = childDisplayName(input.profile);
  final headerTime = homeHeaderTimeText(input.now);
  final headerTitle = childName == null ? '孩子现在' : '$childName现在';
  final chips = buildHabitChips(
    profile: input.profile,
    profileLoading: input.profileLoading,
    hasNoDevice: hasNoDevice,
    deviceOnline: deviceOnline,
    pendingCount: pendingCount,
    localTasks: localTasks,
    isLoading: isLoading,
  );

  if (isLoading) {
    return HabitFocusCopy(
      headerTime: headerTime,
      headerTitle: headerTitle,
      title: childName == null ? '正在看看今天安排' : '$childName今天怎么样',
      detail: '稍等一下，正在看看今天的小节奏。',
      chips: chips,
    );
  }
  if (hasNoChild) {
    return HabitFocusCopy(
      headerTime: headerTime,
      headerTitle: headerTitle,
      title: '先添加孩子资料',
      detail: '添加后可以推荐作息和看护提醒。',
      chips: chips,
    );
  }
  if (hasNoDevice) {
    return HabitFocusCopy(
      headerTime: headerTime,
      headerTitle: headerTitle,
      title: '还没有连接摄像头',
      detail: '连接后可以查看实时画面和看护提醒。',
      chips: chips,
    );
  }
  if (deviceIssue) {
    return HabitFocusCopy(
      headerTime: headerTime,
      headerTitle: headerTitle,
      title: '先检查看护设备',
      detail: '生活提醒会保留，摄像头恢复后继续记录。',
      chips: chips,
    );
  }

  final title = observationTitle(
    cameraStatus: input.cameraStatus,
    cameraMonitor: input.cameraMonitor,
    currentTask: currentTask,
    localTasks: localTasks,
    pendingItems: pendingItems,
    childName: childName,
    now: input.now,
  );
  final detail = observationDetail(
    cameraMonitor: input.cameraMonitor,
    currentTask: currentTask,
    localTasks: localTasks,
    pendingCount: pendingCount,
    now: input.now,
  );

  return HabitFocusCopy(
    headerTime: headerTime,
    headerTitle: headerTitle,
    title: title,
    detail: detail,
    chips: chips,
  );
}

List<HomeChipSpec> buildHabitChips({
  required ProfileSummary? profile,
  required bool profileLoading,
  required bool hasNoDevice,
  required bool deviceOnline,
  required int pendingCount,
  required List<GuardianTask>? localTasks,
  required bool isLoading,
}) {
  final chips = <HomeChipSpec>[
    if (hasNoDevice)
      const HomeChipSpec(
        kind: HomeChipKind.device,
        label: '待连接',
        tone: StatusTone.neutral,
      )
    else if (isLoading)
      const HomeChipSpec(
        kind: HomeChipKind.device,
        label: '正在检查',
        tone: StatusTone.neutral,
      )
    else
      HomeChipSpec(
        kind: HomeChipKind.device,
        label: deviceOnline ? '设备在线' : '设备离线',
        tone: deviceOnline ? StatusTone.success : StatusTone.danger,
      ),
  ];

  final child = profile?.child;
  if (child != null) {
    final stage = child.displayStage.trim();
    if (stage.isNotEmpty) {
      chips.add(
        HomeChipSpec(
          kind: HomeChipKind.stage,
          label: stage,
          tone: StatusTone.neutral,
        ),
      );
    }
  }

  if (!isLoading && pendingCount > 0) {
    chips.add(
      HomeChipSpec(
        kind: HomeChipKind.pending,
        label: '待处理 $pendingCount',
        tone: StatusTone.warning,
      ),
    );
  } else if (!isLoading && !hasNoDevice && localTasks?.isEmpty == true) {
    chips.add(
      const HomeChipSpec(
        kind: HomeChipKind.rhythm,
        label: '今日未安排',
        tone: StatusTone.neutral,
      ),
    );
  }

  if (!profileLoading) {
    final profileChip = profileIssueChip(profile);
    final duplicateNoDeviceChip = hasNoDevice && profileChip?.label == '待绑定设备';
    if (profileChip != null && !duplicateNoDeviceChip) chips.add(profileChip);
  }

  return chips.take(3).toList();
}

HomeChipSpec? profileIssueChip(ProfileSummary? profile) {
  if (profile == null) return null;
  final child = profile.child;
  if (child == null) {
    return const HomeChipSpec(
      kind: HomeChipKind.profile,
      label: '待添加孩子',
      tone: StatusTone.warning,
    );
  }
  if (child.educationStage.trim().isEmpty && child.grade.trim().isEmpty) {
    return const HomeChipSpec(
      kind: HomeChipKind.profile,
      label: '阶段待补充',
      tone: StatusTone.warning,
    );
  }
  if (profile.deviceCount <= 0) {
    return const HomeChipSpec(
      kind: HomeChipKind.profile,
      label: '待绑定设备',
      tone: StatusTone.warning,
    );
  }
  return null;
}

String observationTitle({
  required CameraStatus? cameraStatus,
  required CameraMonitorStatus? cameraMonitor,
  required GuardianTask? currentTask,
  required List<GuardianTask>? localTasks,
  required List<PendingItem> pendingItems,
  required String? childName,
  required DateTime now,
}) {
  final monitorObservation = meaningfulObservationText(
    cameraMonitor?.hasCurrentReliableObservation == true
        ? cameraMonitor?.lastObservation
        : null,
  );
  if (monitorObservation != null) {
    return compactHomeText(monitorObservation, maxLength: 24);
  }
  if (currentTask != null) {
    final aiSummary = currentTask.aiObservationSummary.trim();
    if (aiSummary.isNotEmpty) {
      return compactHomeText(aiSummary, maxLength: 56);
    }
    return '现在是${currentTask.title}';
  }
  if (pendingItems.isNotEmpty) {
    final missed = pendingItems.any(
      (item) => item.action == PendingItemAction.reviewMissedTask,
    );
    if (missed) return '有一项安排没有看到完成';
    return pendingItems.length == 1 ? '有一件事需要你确认' : '有几件事需要你确认';
  }
  final upcomingOrCurrent = nextUpcomingRhythmTask(localTasks, now);
  if (upcomingOrCurrent != null) {
    if (rhythmNodeState(upcomingOrCurrent) == RhythmNodeState.current) {
      return '现在是${upcomingOrCurrent.title}';
    }
    return '${upcomingOrCurrent.title}快到了';
  }
  final completedCount = countCompletedRhythmTasks(localTasks);
  if (completedCount > 0) {
    return completedCount == 1 ? '今天的节奏都完成了' : '今天已完成 $completedCount 项安排';
  }
  if (cameraStatus?.isOnline == true || cameraMonitor != null) {
    return '还没有最近画面';
  }
  if (localTasks == null || localTasks.isEmpty) {
    return '今天暂时没有新的看护记录';
  }
  return '可以先安排今天的小节奏';
}

String observationDetail({
  required CameraMonitorStatus? cameraMonitor,
  required GuardianTask? currentTask,
  required List<GuardianTask>? localTasks,
  required int pendingCount,
  required DateTime now,
}) {
  if (cameraMonitor?.hasCurrentReliableObservation == true) {
    final description = compactHomeText(
      cameraMonitor!.lastObservationDescription,
      maxLength: 44,
    );
    if (meaningfulObservationText(description) != null) {
      return description;
    }
    final reason = compactHomeText(
      cameraMonitor.lastObservationDecisionReason,
      maxLength: 44,
    );
    if (meaningfulObservationText(reason) != null) {
      return reason;
    }
    return '这条记录来自摄像头画面。';
  }
  if (pendingCount > 0) {
    return '$pendingCount 件事等你处理，先看记录再决定。';
  }
  if (currentTask != null) {
    final countdown = nextStepCountdown(currentTask, now);
    if (countdown != null) {
      return '当前是${currentTask.title}，$countdown';
    }
    if (currentTask.nextStep.trim().isNotEmpty) {
      return currentTask.nextStep.trim();
    }
    return '按节奏轻声提醒，不中途打断孩子。';
  }
  final nextTask = nextUpcomingRhythmTask(localTasks, now);
  if (nextTask != null) {
    final time = taskTimeText(nextTask);
    return '下一步是${nextTask.title}${time == '今天' ? '' : ' · $time'}';
  }
  if (countCompletedRhythmTasks(localTasks) > 0) {
    return '可以看看今天的记录，或安排下一步。';
  }
  return '没有可靠画面时，不会判断孩子状态。';
}

String? nextStepCountdown(GuardianTask task, DateTime now) {
  final target = task.nextReminderAt ?? _endTimestamp(task);
  if (target == null) return null;
  final diff = target - now.millisecondsSinceEpoch;
  if (diff <= 0) return '即将进入下一步';
  final minutes = (diff / 60000).ceil();
  if (minutes < 60) return '约 $minutes 分钟后进入下一步';
  final hours = minutes ~/ 60;
  final remainMinutes = minutes % 60;
  if (remainMinutes == 0) return '约 $hours 小时后进入下一步';
  return '约 $hours 小时 $remainMinutes 分钟后进入下一步';
}

int? _endTimestamp(GuardianTask task) {
  if (task.scheduledEnd.isEmpty) return null;
  final parts = task.scheduledEnd.split(':');
  if (parts.length < 2) return null;
  final hour = int.tryParse(parts[0]);
  final minute = int.tryParse(parts[1]);
  if (hour == null || minute == null) return null;
  final now = DateTime.now();
  return DateTime(
    now.year,
    now.month,
    now.day,
    hour,
    minute,
  ).millisecondsSinceEpoch;
}

GuardianTask? nextUpcomingRhythmTask(List<GuardianTask>? tasks, DateTime now) {
  if (tasks == null || tasks.isEmpty) return null;
  final candidates =
      tasks.where(_isRhythmCandidate).where((task) {
        final state = rhythmNodeState(task);
        return state == RhythmNodeState.current ||
            state == RhythmNodeState.upcoming;
      }).toList()..sort((a, b) {
        final aActive = _activeRhythmPriority(a);
        final bActive = _activeRhythmPriority(b);
        if (aActive != bActive) return aActive.compareTo(bActive);
        final aDistance = _taskDistanceFromNow(a, now);
        final bDistance = _taskDistanceFromNow(b, now);
        if (aDistance != bDistance) return aDistance.compareTo(bDistance);
        return sortTasksByTime(a, b);
      });
  return candidates.isEmpty ? null : candidates.first;
}

int countCompletedRhythmTasks(List<GuardianTask>? tasks) {
  if (tasks == null || tasks.isEmpty) return 0;
  return tasks
      .where(_isRhythmCandidate)
      .where((task) => rhythmNodeState(task) == RhythmNodeState.completed)
      .length;
}

List<RhythmNode> buildRhythmNodes(List<GuardianTask>? tasks, [DateTime? now]) {
  if (tasks == null || tasks.isEmpty) return const [];
  final selected = selectRhythmTasks(tasks, now ?? DateTime.now());
  return [
    for (final task in selected)
      RhythmNode(
        taskId: task.id,
        timeLabel: taskTimeText(task),
        title: task.title,
        subtitle: task.nextStep,
        statusLabel: task.status.label,
        state: rhythmNodeState(task),
        tone: rhythmNodeTone(task),
      ),
  ];
}

HomeRhythmMode resolveRhythmMode(
  List<GuardianTask>? tasks,
  List<RhythmNode> nodes,
) {
  if (nodes.isEmpty) return HomeRhythmMode.empty;
  final hasCurrentOrUpcoming = nodes.any(
    (node) =>
        node.state == RhythmNodeState.current ||
        node.state == RhythmNodeState.upcoming,
  );
  if (hasCurrentOrUpcoming) return HomeRhythmMode.rhythm;
  final hasAnyTask = tasks?.isNotEmpty ?? false;
  return hasAnyTask ? HomeRhythmMode.review : HomeRhythmMode.empty;
}

List<GuardianTask> selectRhythmTasks(List<GuardianTask> tasks, DateTime now) {
  if (tasks.isEmpty) return const [];
  final latest = tasks.where(_isRhythmCandidate).toList()
    ..sort((a, b) {
      final timeCompare = _taskTimelineValue(
        b,
        now,
      ).compareTo(_taskTimelineValue(a, now));
      if (timeCompare != 0) return timeCompare;
      return b.id.compareTo(a.id);
    });
  return latest.take(5).toList()..sort(sortTasksByTime);
}

RhythmNodeState rhythmNodeState(GuardianTask task) {
  if (task.status == GuardianTaskStatus.inProgress ||
      task.status == GuardianTaskStatus.reminderSent ||
      task.status == GuardianTaskStatus.delayed) {
    return RhythmNodeState.current;
  }
  if (task.status == GuardianTaskStatus.completed ||
      task.status == GuardianTaskStatus.confirmed) {
    return RhythmNodeState.completed;
  }
  if (task.status == GuardianTaskStatus.scheduled ||
      task.status == GuardianTaskStatus.pending) {
    return RhythmNodeState.upcoming;
  }
  return RhythmNodeState.muted;
}

StatusTone rhythmNodeTone(GuardianTask task) {
  return task.status.tone;
}

List<PendingItem> buildPendingItems({
  required List<GuardianTask>? tasks,
  required List<RewardRedemption>? redemptions,
  required bool deviceIssue,
  bool canManageTasks = false,
  bool canConfirmTasks = false,
}) {
  final items = <PendingItem>[];
  if (tasks != null) {
    for (final task in tasks.where(
      (item) => item.status.awaitsParent && canConfirmTasks,
    )) {
      items.add(
        PendingItem(
          kind: PendingItemKind.task,
          action: PendingItemAction.confirmTask,
          id: task.id,
          title: '${task.title}待确认',
          detail: task.rewardPoints > 0
              ? '确认后再发放 ${task.rewardPoints} 分'
              : '看一眼记录再确认',
          routePath: '$taskDetailRoutePrefix/${task.id}',
        ),
      );
    }
    for (final task in tasks.where(
      (item) =>
          (item.status == GuardianTaskStatus.missed ||
              item.status == GuardianTaskStatus.expired) &&
          ((canManageTasks && item.hasParentAction('reschedule')) ||
              (canConfirmTasks && item.hasParentAction('manual_complete')) ||
              (canConfirmTasks && item.hasParentAction('acknowledge_missed'))),
    )) {
      items.add(
        PendingItem(
          kind: PendingItemKind.task,
          action: PendingItemAction.reviewMissedTask,
          id: task.id,
          title: '本次没有看到完成结果',
          detail: '${task.title}可以重新安排、手动记录或不处理。',
          routePath: '$taskDetailRoutePrefix/${task.id}',
        ),
      );
    }
  }
  for (final redemption in pendingRedemptions(redemptions)) {
    items.add(
      PendingItem(
        kind: PendingItemKind.redemption,
        action: PendingItemAction.fulfillReward,
        id: redemption.id,
        title: '${redemption.rewardTitle}待兑现',
        detail: '${redemption.pointsCost} 分 · 需要家长确认',
        routePath: rewardsRoutePath,
      ),
    );
  }
  if (deviceIssue) {
    items.add(
      const PendingItem(
        kind: PendingItemKind.task,
        action: PendingItemAction.checkDevice,
        id: 'device_issue',
        title: '看护设备需要检查',
        detail: '网络或摄像头状态暂不稳定',
        routePath: liveRoutePath,
      ),
    );
  }
  return items;
}

RecentObservationCopy buildRecentObservationCopy({
  required HomeSummaryInput input,
  required bool hasNoDevice,
  required bool deviceIssue,
  required String? heroObservation,
  required GuardianTask? currentTask,
  required List<GuardianTask>? localTasks,
  required int pendingCount,
  required bool isLoading,
}) {
  if (isLoading) {
    return const RecentObservationCopy(
      headline: '正在整理最近记录',
      detail: '稍等一下，正在看看今天有没有值得关注的情况。',
    );
  }
  if (hasNoDevice) {
    return const RecentObservationCopy(
      headline: '连接摄像头后显示最近观察',
      detail: '现在可以先安排生活提醒，设备上线后会记录重要情况。',
      visible: false,
    );
  }
  if (deviceIssue) {
    return const RecentObservationCopy(
      headline: '摄像头暂时不稳定，今天的安排会保留',
      detail: '恢复在线后，会继续记录看护情况。',
    );
  }
  final monitorObservation = meaningfulObservationText(
    input.cameraMonitor?.hasCurrentReliableObservation == true
        ? input.cameraMonitor?.lastObservation
        : null,
  );
  final repeatedInHero = sameHomeObservation(
    monitorObservation,
    heroObservation,
  );
  if (repeatedInHero) {
    return const RecentObservationCopy(
      headline: '最近观察已显示在顶部',
      detail: '',
      visible: false,
    );
  }
  final observation = monitorObservation;

  if (currentTask != null &&
      (currentTask.status == GuardianTaskStatus.inProgress ||
          currentTask.status == GuardianTaskStatus.reminderSent)) {
    if (observation == null) {
      return const RecentObservationCopy(
        headline: '暂时没有可靠画面记录',
        detail: '可以刷新观察，或进入实时画面看看。',
        showActions: true,
      );
    }
    return RecentObservationCopy(
      headline: '最近观察',
      detail: compactHomeText(observation, maxLength: 72),
    );
  }

  if (observation == null) {
    return const RecentObservationCopy(
      headline: '暂时没有可靠画面记录',
      detail: '可以刷新观察，或进入实时画面看看。',
      showActions: true,
    );
  }

  return RecentObservationCopy(
    headline: '最近观察',
    detail: compactHomeText(observation, maxLength: 72),
  );
}

HomePrimaryCta buildPrimaryCta({
  required bool hasNoDevice,
  required bool deviceIssue,
  required List<PendingItem> pendingItems,
  required int pendingCount,
}) {
  if (pendingCount > 0) {
    return const HomePrimaryCta(kind: HomePrimaryCtaKind.none, label: '');
  }
  if (hasNoDevice) {
    return const HomePrimaryCta(kind: HomePrimaryCtaKind.none, label: '');
  }
  return const HomePrimaryCta(kind: HomePrimaryCtaKind.none, label: '');
}

bool _isRhythmCandidate(GuardianTask task) {
  return true;
}

int _taskTimelineValue(GuardianTask task, DateTime now) {
  final end = _taskEndDateTime(task, now);
  final start = _taskStartDateTime(task, now);
  return (end ?? start ?? DateTime(now.year, now.month, now.day))
      .millisecondsSinceEpoch;
}

int _activeRhythmPriority(GuardianTask task) {
  if (task.status == GuardianTaskStatus.inProgress ||
      task.status == GuardianTaskStatus.reminderSent ||
      task.status == GuardianTaskStatus.delayed) {
    return 0;
  }
  return 1;
}

int _taskDistanceFromNow(GuardianTask task, DateTime now) {
  final times = [
    _taskStartDateTime(task, now),
    _taskEndDateTime(task, now),
  ].whereType<DateTime>().toList();
  if (times.isEmpty) return 1 << 30;
  return times
      .map((time) => time.difference(now).inMinutes.abs())
      .reduce((a, b) => a < b ? a : b);
}

DateTime? _taskStartDateTime(GuardianTask task, DateTime now) {
  return _taskDateTime(task.scheduledDate, task.scheduledStart, now);
}

DateTime? _taskEndDateTime(GuardianTask task, DateTime now) {
  return _taskDateTime(task.scheduledDate, task.scheduledEnd, now);
}

DateTime? _taskDateTime(
  String dateText,
  String timeText,
  DateTime fallbackDay,
) {
  if (timeText.isEmpty) return null;
  final parts = timeText.split(':');
  if (parts.length < 2) return null;
  final hour = int.tryParse(parts[0]);
  final minute = int.tryParse(parts[1]);
  if (hour == null || minute == null) return null;
  final date = DateTime.tryParse(dateText);
  final day = date ?? fallbackDay;
  return DateTime(day.year, day.month, day.day, hour, minute);
}

bool hasDeviceIssue(HomeSummaryInput input) {
  final overview = input.deviceOverview;
  if (overview == null && !input.deviceLoading && !input.deviceError) {
    return false;
  }
  return input.deviceError ||
      input.cameraHealthError ||
      input.cameraStatusError ||
      (overview != null && !overview.isOnline) ||
      (input.cameraHealth != null && !input.cameraHealth!.reachable) ||
      (input.cameraStatus != null && !input.cameraStatus!.isOnline);
}

List<RewardRedemption> pendingRedemptions(List<RewardRedemption>? redemptions) {
  return redemptions
          ?.where((item) => item.status == RedemptionStatus.redeemed)
          .toList() ??
      const [];
}

GuardianTask? currentTaskFromToday(List<GuardianTask>? tasks) {
  if (tasks == null || tasks.isEmpty) return null;
  for (final task in tasks) {
    if (task.status == GuardianTaskStatus.inProgress) return task;
  }
  for (final task in tasks) {
    if (task.status == GuardianTaskStatus.reminderSent ||
        task.status == GuardianTaskStatus.delayed) {
      return task;
    }
  }
  return null;
}

List<GuardianTask>? localTodayTasks(List<GuardianTask>? tasks, DateTime now) {
  if (tasks == null) return null;
  final today = homeDateText(now);
  return tasks.where((task) => task.scheduledDate == today).toList();
}

String homeDateText(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

String homeHeaderTimeText(DateTime date) {
  final hour = date.hour;
  if (hour < 6) return '今天清晨';
  if (hour < 11) return '今天上午';
  if (hour < 14) return '今天中午';
  if (hour < 18) return '今天下午';
  return '今天晚上';
}

String? childDisplayName(ProfileSummary? profile) {
  final child = profile?.child;
  if (child == null) return null;
  if (child.nickname.trim().isNotEmpty) return child.nickname.trim();
  if (child.name.trim().isNotEmpty) return child.name.trim();
  return null;
}

String taskTimeText(GuardianTask task) {
  if (task.scheduledStart.isNotEmpty) return task.scheduledStart;
  if (task.scheduledEnd.isNotEmpty) return task.scheduledEnd;
  return '今天';
}

int sortTasksByTime(GuardianTask a, GuardianTask b) {
  return taskTimeText(a).compareTo(taskTimeText(b));
}

String compactHomeText(String text, {int maxLength = 42}) {
  final trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return '${trimmed.substring(0, maxLength)}…';
}

bool isMeaningfulHomeObservation(String text) {
  return meaningfulObservationText(text) != null;
}

bool sameHomeObservation(String? left, String? right) {
  final a = left?.trim();
  final b = right?.trim();
  return a != null && a.isNotEmpty && b != null && b.isNotEmpty && a == b;
}

String? meaningfulObservationText(String? text) {
  final trimmed = text?.trim() ?? '';
  if (trimmed.isEmpty) return null;
  final normalized = trimmed.toLowerCase();
  const genericValues = {'其他', '未知', '无明显活动', 'other', 'unknown'};
  const staleNegativeValues = {'暂时没在画面里看到孩子。', '暂时没在画面里看到孩子'};
  if (genericValues.contains(trimmed) || genericValues.contains(normalized)) {
    return null;
  }
  if (staleNegativeValues.contains(trimmed)) return '暂未看到孩子';
  for (final generic in genericValues) {
    if (trimmed.endsWith('：$generic') || trimmed.endsWith(': $generic')) {
      return null;
    }
  }
  return trimmed;
}
