import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/domain/task_models.dart';
import 'package:guardian_parent_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class TaskDetailScreen extends ConsumerStatefulWidget {
  const TaskDetailScreen({required this.taskId, super.key});

  final String taskId;

  @override
  ConsumerState<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends ConsumerState<TaskDetailScreen> {
  void _refreshTaskDetail() {
    ref
      ..invalidate(taskDetailProvider(widget.taskId))
      ..invalidate(taskEventsProvider(widget.taskId))
      ..invalidate(taskListProvider)
      ..invalidate(todayTasksProvider)
      ..invalidate(taskWeekProvider);
  }

  @override
  Widget build(BuildContext context) {
    final taskValue = ref.watch(taskDetailProvider(widget.taskId));
    final eventsValue = ref.watch(taskEventsProvider(widget.taskId));

    return taskValue.when(
      data: (task) => AppScreen(
        title: task.title,
        subtitle: '${task.typeLabel} · ${task.timeLabel}',
        fixedHeader: true,
        backLabel: '返回任务',
        onBack: () => context.go(AppRoute.tasks.path),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 118),
        children: [
          _EvidencePanel(task: task, ref: ref),
          const SizedBox(height: 14),
          AppSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionTitle('时间和奖励'),
                const SizedBox(height: 8),
                AppListRow(
                  icon: Icons.timer_outlined,
                  title: task.timeLabel,
                  subtitle: '${task.scheduleLabel} · ${task.durationLabel}',
                  tone: AppListRowTone.blue,
                ),
                if (task.rewardPoints > 0)
                  AppListRow(
                    icon: Icons.stars_outlined,
                    title: '+${task.rewardPoints} 分',
                    subtitle: task.parentDecisionLabel,
                    tone: task.status.awaitsParent
                        ? AppListRowTone.amber
                        : AppListRowTone.neutral,
                  ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          _TaskEventsPanel(events: eventsValue),
        ],
      ),
      loading: () => AppScreen(
        title: '任务详情',
        fixedHeader: true,
        backLabel: '返回任务',
        onBack: () => context.go(AppRoute.tasks.path),
        children: const [_TaskDetailLoading()],
      ),
      error: (error, _) => AppScreen(
        title: '任务详情',
        fixedHeader: true,
        backLabel: '返回任务',
        onBack: () => context.go(AppRoute.tasks.path),
        children: [
          AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '任务详情暂时打不开',
            message: error is TaskException ? error.message : '请稍后重试。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: _refreshTaskDetail,
          ),
        ],
      ),
    );
  }
}

class _TaskEventsPanel extends StatelessWidget {
  const _TaskEventsPanel({required this.events});

  final AsyncValue<List<GuardianTaskEvent>> events;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('任务记录'),
          const SizedBox(height: 8),
          events.when(
            data: (items) {
              if (items.isEmpty) {
                return const Text(
                  '任务开始后，提醒和确认记录会显示在这里。',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    height: 1.5,
                  ),
                );
              }
              return Column(
                children: [
                  for (
                    var index = 0;
                    index < items.length && index < 5;
                    index++
                  )
                    AppListRow(
                      icon: _eventIcon(items[index].eventType),
                      title: items[index].title,
                      subtitle:
                          '${_formatEventTime(items[index].createdAt)} · ${items[index].displayMessage}',
                      tone: _eventTone(items[index].tone),
                    ),
                ],
              );
            },
            loading: () => const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                '正在整理任务记录。',
                style: TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            error: (_, _) => const Text(
              '任务记录暂时没有同步完成。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  IconData _eventIcon(String eventType) {
    return switch (eventType) {
      'reminder_sent' ||
      'reminder_failed' ||
      'start_reminder_sent' ||
      'start_reminder_failed' ||
      'manual_start_reminder_sent' ||
      'manual_start_reminder_failed' ||
      'manual_prepare_reminder_sent' ||
      'manual_prepare_reminder_failed' ||
      'manual_reminder_sent' ||
      'manual_reminder_failed' ||
      'wrap_up_reminder_sent' ||
      'wrap_up_reminder_failed' ||
      'finish_reminder_sent' ||
      'finish_reminder_failed' ||
      'manual_finish_reminder_sent' ||
      'manual_finish_reminder_failed' => Icons.volume_up_outlined,
      'auto_started' || 'manual_started' => Icons.play_circle_outline,
      'camera_monitor_started' => Icons.center_focus_strong_outlined,
      'monitor_not_required' => Icons.visibility_off_outlined,
      'camera_command_failed' => Icons.videocam_off_outlined,
      'parent_confirmed' => Icons.verified_outlined,
      'confirmation_rejected' || 'parent_rejected' => Icons.rule_outlined,
      'points_award_skipped' => Icons.block_outlined,
      _ => Icons.history_outlined,
    };
  }

  AppListRowTone _eventTone(StatusTone tone) {
    return switch (tone) {
      StatusTone.success => AppListRowTone.green,
      StatusTone.warning => AppListRowTone.amber,
      StatusTone.danger => AppListRowTone.red,
      _ => AppListRowTone.neutral,
    };
  }
}

class _TaskHeroActions extends StatelessWidget {
  const _TaskHeroActions({required this.task, required this.ref});

  final GuardianTask task;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final canEditSchedule = _canEditSchedule(task);
    final canSendWrapUpReminder = _canSendWrapUpReminder(task);
    final canSendStartReminder = task.status == GuardianTaskStatus.delayed;
    final profile = ref.watch(profileSummaryProvider).asData?.value;
    final canManageTasks = profile?.can('manage_tasks') ?? false;
    final canConfirmTasks = profile?.can('confirm_tasks') ?? false;

    final actions = <_HeroActionData>[];
    if (task.status.awaitsParent && canConfirmTasks) {
      actions
        ..add(
          _HeroActionData(
            label: '确认完成',
            icon: Icons.fact_check_outlined,
            tone: _HeroActionTone.primary,
            onTap: () => _confirmTask(context, ref, task),
          ),
        )
        ..add(
          _HeroActionData(
            label: '驳回',
            icon: Icons.rule_outlined,
            tone: _HeroActionTone.danger,
            onTap: () => _rejectTask(context, ref, task),
          ),
        );
    } else if (task.status == GuardianTaskStatus.inProgress) {
      if (canConfirmTasks) {
        actions.add(
          _HeroActionData(
            label: '标记任务完成',
            icon: Icons.task_alt_outlined,
            tone: _HeroActionTone.primary,
            onTap: () => _completeTask(context, ref, task),
          ),
        );
      }
      if (canManageTasks && canSendWrapUpReminder) {
        actions.add(
          _HeroActionData(
            label: '提醒收尾',
            icon: Icons.volume_up_outlined,
            tone: _HeroActionTone.secondary,
            onTap: () => _sendTaskReminder(
              context,
              ref,
              task,
              phase: TaskReminderPhase.wrapUp,
              toast: '已提醒孩子准备收尾',
            ),
          ),
        );
      }
    } else if (canSendStartReminder && (canManageTasks || canConfirmTasks)) {
      if (canManageTasks) {
        actions.add(
          _HeroActionData(
            label: '再提醒一次',
            icon: Icons.volume_up_outlined,
            tone: _HeroActionTone.primary,
            onTap: () => _sendTaskReminder(
              context,
              ref,
              task,
              phase: TaskReminderPhase.start,
              toast: '已发送温和提醒',
            ),
          ),
        );
      }
      if (canConfirmTasks) {
        actions.add(
          _HeroActionData(
            label: '标记完成',
            icon: Icons.task_alt_outlined,
            tone: _HeroActionTone.secondary,
            onTap: () => _completeTask(context, ref, task),
          ),
        );
      }
    } else if (canEditSchedule && canManageTasks) {
      actions.add(
        _HeroActionData(
          label: '编辑任务',
          icon: Icons.edit_outlined,
          tone: _HeroActionTone.secondary,
          onTap: () => _editTask(context, ref, task),
        ),
      );
      actions.add(
        _HeroActionData(
          label: '取消任务',
          icon: Icons.event_busy_outlined,
          tone: _HeroActionTone.danger,
          onTap: () => _cancelTask(context, ref, task),
        ),
      );
    }

    if (actions.isEmpty) return const SizedBox.shrink();
    return Column(
      children: [
        const SizedBox(height: 14),
        Row(
          children: [
            for (
              var index = 0;
              index < actions.length && index < 2;
              index++
            ) ...[
              if (index > 0) const SizedBox(width: 10),
              Expanded(child: _HeroActionButton(data: actions[index])),
            ],
          ],
        ),
      ],
    );
  }
}

class _HeroActionData {
  const _HeroActionData({
    required this.label,
    required this.icon,
    required this.tone,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final _HeroActionTone tone;
  final VoidCallback onTap;
}

enum _HeroActionTone { primary, secondary, danger }

class _HeroActionButton extends StatelessWidget {
  const _HeroActionButton({required this.data});

  final _HeroActionData data;

  @override
  Widget build(BuildContext context) {
    final foreground = switch (data.tone) {
      _HeroActionTone.primary => AppColors.ink,
      _HeroActionTone.secondary => Colors.white,
      _HeroActionTone.danger => AppColors.danger,
    };
    final background = switch (data.tone) {
      _HeroActionTone.primary => Colors.white,
      _HeroActionTone.secondary => Colors.white.withValues(alpha: 0.10),
      _HeroActionTone.danger => AppColors.dangerWash,
    };
    final border = switch (data.tone) {
      _HeroActionTone.primary => Colors.white,
      _HeroActionTone.secondary => Colors.white.withValues(alpha: 0.14),
      _HeroActionTone.danger => AppColors.dangerWash,
    };

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(15),
        onTap: data.onTap,
        splashColor: Colors.white.withValues(alpha: 0.08),
        highlightColor: Colors.white.withValues(alpha: 0.06),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(15),
            border: Border.all(color: border),
          ),
          child: SizedBox(
            height: AppControls.buttonHeight,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(data.icon, color: foreground, size: 17),
                const SizedBox(width: 7),
                Flexible(
                  child: Text(
                    data.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: foreground,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _EvidencePanel extends StatelessWidget {
  const _EvidencePanel({required this.task, required this.ref});

  final GuardianTask task;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              StatusChip(label: task.status.label, tone: task.status.tone),
              if (_heroTrailingLabel(task).isNotEmpty) ...[
                const Spacer(),
                Text(
                  _heroTrailingLabel(task),
                  style: const TextStyle(
                    color: Color(0xFFFDBA74),
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 14),
          Text(
            _heroTitle(task),
            style: const TextStyle(
              color: Colors.white,
              fontFamily: AppTypography.systemFont,
              fontSize: 20,
              fontWeight: FontWeight.w900,
              height: 1.2,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            _heroDescription(task),
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.78),
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.55,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 14),
          _HeroInsightCard(task: task),
          _TaskHeroActions(task: task, ref: ref),
        ],
      ),
    );
  }
}

class _HeroInsightCard extends StatelessWidget {
  const _HeroInsightCard({required this.task});

  final GuardianTask task;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(16),
              ),
              child: SizedBox(
                width: 48,
                height: 48,
                child: Center(
                  child: Icon(
                    _heroInsightIcon(task),
                    color: Colors.white,
                    size: 24,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _heroInsightTitle(task),
                    style: const TextStyle(
                      color: Colors.white,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      height: 1.25,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    _heroInsightBody(task),
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.70),
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      height: 1.45,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 16,
        fontWeight: FontWeight.w800,
        letterSpacing: 0,
      ),
    );
  }
}

class _TaskDetailLoading extends StatelessWidget {
  const _TaskDetailLoading();

  @override
  Widget build(BuildContext context) {
    return const AppLoadingState(
      title: '正在加载任务详情',
      message: '正在整理任务时间、证据和奖励信息。',
    );
  }
}

bool _canEditSchedule(GuardianTask task) {
  return task.status == GuardianTaskStatus.scheduled ||
      task.status == GuardianTaskStatus.pending ||
      task.status == GuardianTaskStatus.reminderSent;
}

bool _canSendWrapUpReminder(GuardianTask task) {
  if (task.status != GuardianTaskStatus.inProgress) return false;
  final dueAt = DateTime.tryParse(task.dueAt);
  if (dueAt == null) return false;
  final remaining = dueAt.difference(DateTime.now());
  return !remaining.isNegative && remaining <= const Duration(minutes: 5);
}

String _heroTrailingLabel(GuardianTask task) {
  if (task.status == GuardianTaskStatus.rejected) return '未发放';
  if (task.status == GuardianTaskStatus.completed ||
      task.status == GuardianTaskStatus.confirmed) {
    return task.pointsGrantedAt != null && task.rewardPoints > 0
        ? '+${task.rewardPoints} 分'
        : '已记录';
  }
  return '';
}

String _heroTitle(GuardianTask task) {
  return switch (task.status) {
    GuardianTaskStatus.scheduled || GuardianTaskStatus.pending => '任务还没开始',
    GuardianTaskStatus.reminderSent => '即将开始',
    GuardianTaskStatus.inProgress => '任务进行中',
    GuardianTaskStatus.delayed => '还没有开始',
    GuardianTaskStatus.awaitingParentConfirmation => '等待你确认',
    GuardianTaskStatus.completed || GuardianTaskStatus.confirmed => '已完成',
    GuardianTaskStatus.rejected => '已驳回',
    GuardianTaskStatus.missed || GuardianTaskStatus.expired => '已错过',
    GuardianTaskStatus.cancelled => '已取消',
  };
}

String _heroDescription(GuardianTask task) {
  return switch (task.status) {
    GuardianTaskStatus.scheduled ||
    GuardianTaskStatus.pending => '到时间后会提醒孩子开始。',
    GuardianTaskStatus.reminderSent => '已经提醒孩子，等待任务开始。',
    GuardianTaskStatus.inProgress =>
      task.requiresParentConfirmation
          ? '正在记录任务状态，完成后会进入确认。'
          : '正在记录任务状态，结束后会进入记录。',
    GuardianTaskStatus.delayed => '已提醒孩子开始，可以稍后再看或手动处理。',
    GuardianTaskStatus.awaitingParentConfirmation => '任务时间已结束，请确认孩子是否完成。',
    GuardianTaskStatus.completed || GuardianTaskStatus.confirmed =>
      task.pointsGrantedAt != null && task.rewardPoints > 0
          ? '已确认完成并发放积分。'
          : '任务已完成并进入记录。',
    GuardianTaskStatus.rejected => '本次任务未通过确认，未发放积分。',
    GuardianTaskStatus.missed ||
    GuardianTaskStatus.expired => '任务时间已过，本次未记录完成。',
    GuardianTaskStatus.cancelled => '任务已取消，记录仍会保留。',
  };
}

IconData _heroInsightIcon(GuardianTask task) {
  return switch (task.status) {
    GuardianTaskStatus.awaitingParentConfirmation => Icons.fact_check_outlined,
    GuardianTaskStatus.completed ||
    GuardianTaskStatus.confirmed => Icons.verified_outlined,
    GuardianTaskStatus.rejected => Icons.rule_outlined,
    GuardianTaskStatus.inProgress => Icons.center_focus_strong_outlined,
    GuardianTaskStatus.delayed => Icons.volume_up_outlined,
    GuardianTaskStatus.missed ||
    GuardianTaskStatus.expired => Icons.event_busy_outlined,
    _ => Icons.schedule_outlined,
  };
}

String _heroInsightTitle(GuardianTask task) {
  return switch (task.status) {
    GuardianTaskStatus.awaitingParentConfirmation => '观察摘要',
    GuardianTaskStatus.completed || GuardianTaskStatus.confirmed => '完成记录',
    GuardianTaskStatus.rejected => '驳回原因',
    GuardianTaskStatus.inProgress => '当前观察',
    GuardianTaskStatus.delayed => '提醒记录',
    GuardianTaskStatus.missed || GuardianTaskStatus.expired => '任务记录',
    _ => '任务安排',
  };
}

String _heroInsightBody(GuardianTask task) {
  if (task.status == GuardianTaskStatus.rejected) {
    return task.rejectionReason.isNotEmpty
        ? '原因：${task.rejectionReason}'
        : '本次任务未通过确认，未发放积分。';
  }
  if (task.status == GuardianTaskStatus.delayed) {
    if (task.delayReminderCount > 0) {
      return '已温和提醒 ${task.delayReminderCount} 次，可以稍后再看任务状态。';
    }
    return '孩子还没有开始，必要时可以再提醒一次。';
  }
  if (task.status == GuardianTaskStatus.inProgress) {
    if (task.cameraObservationStatus == 'unavailable' ||
        task.cameraObservationStatus == 'offline') {
      return '摄像头暂时离线，任务仍会记录，恢复后继续同步。';
    }
    return task.observationText;
  }
  if (task.status.awaitsParent) {
    if (task.aiObservationSummary.isNotEmpty ||
        task.evidenceSummary.isNotEmpty ||
        task.evidence.isNotEmpty) {
      return task.observationText;
    }
    return '暂未获得完整观察结果，可根据实际情况确认。';
  }
  if (task.status == GuardianTaskStatus.completed ||
      task.status == GuardianTaskStatus.confirmed) {
    if (task.pointsGrantedAt != null && task.rewardPoints > 0) {
      return '+${task.rewardPoints} 分已发放，任务已进入记录。';
    }
    return '任务时间已结束，已记录完成。';
  }
  if (task.status == GuardianTaskStatus.missed ||
      task.status == GuardianTaskStatus.expired) {
    return '任务时间已过，本次没有记录到完成结果。';
  }
  return _timeUntilStartLabel(task);
}

String _timeUntilStartLabel(GuardianTask task) {
  final startAt = DateTime.tryParse(task.startAt);
  if (startAt == null) return '到时间后会提醒孩子开始。';
  final remaining = startAt.difference(DateTime.now());
  if (remaining.isNegative) return '任务即将进入下一步记录。';
  if (remaining.inHours >= 1) {
    final hours = remaining.inHours;
    final minutes = remaining.inMinutes.remainder(60);
    return minutes > 0 ? '距离开始还有 $hours 小时 $minutes 分钟。' : '距离开始还有 $hours 小时。';
  }
  final minutes = remaining.inMinutes <= 0 ? 1 : remaining.inMinutes;
  return '距离开始还有 $minutes 分钟。';
}

Future<void> _completeTask(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task,
) async {
  try {
    await ref
        .read(taskRepositoryProvider)
        .completeTask(task.id, evidenceSummary: task.evidenceText);
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, '任务已进入家长确认状态');
  } on TaskException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _sendTaskReminder(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task, {
  required TaskReminderPhase phase,
  required String toast,
}) async {
  try {
    await ref.read(taskRepositoryProvider).sendReminder(task.id, phase: phase);
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, toast);
  } on TaskException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _confirmTask(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task,
) async {
  try {
    await ref.read(taskRepositoryProvider).parentConfirm(task.id);
    _invalidateTaskData(ref, task.id);
    ref.invalidate(pointsSummaryProvider);
    if (context.mounted) {
      final message = task.rewardPoints > 0
          ? '已确认完成，+${task.rewardPoints} 积分已写入流水'
          : '已确认完成，任务已进入记录';
      _showToast(context, message);
    }
  } on TaskException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _rejectTask(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task,
) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '驳回完成确认',
    message: '确认驳回“${task.title}”？驳回后本次不会发放积分。',
    confirmLabel: '确认驳回',
    cancelLabel: '先不驳回',
    danger: true,
  );
  if (!confirmed) return;

  try {
    await ref
        .read(taskRepositoryProvider)
        .rejectConfirmation(task.id, reason: '证据不足，未通过家长确认。');
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, '已驳回，本次不发放积分');
  } on TaskException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _editTask(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task,
) async {
  final initialDate = DateTime.tryParse(task.scheduledDate) ?? DateTime.now();
  final savedDate = await showTaskFormSheet(
    context,
    childId: task.childId,
    initialDate: initialDate,
    childAgeGroup: TaskAgeGroup.lowerPrimary,
    task: task,
  );

  if (savedDate != null) {
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, '任务已更新');
  }
}

Future<void> _cancelTask(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task,
) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '取消任务',
    message: '确认取消“${task.title}”？取消后仍会保留记录。',
    confirmLabel: '确认取消',
    cancelLabel: '先不取消',
    danger: true,
  );
  if (!confirmed) return;

  try {
    await ref.read(taskRepositoryProvider).cancelTask(task.id);
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, '任务已取消');
  } on TaskException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

void _invalidateTaskData(WidgetRef ref, String taskId) {
  ref
    ..invalidate(taskDetailProvider(taskId))
    ..invalidate(taskEventsProvider(taskId))
    ..invalidate(taskListProvider)
    ..invalidate(todayTasksProvider)
    ..invalidate(taskWeekProvider);
}

String _formatEventTime(int milliseconds) {
  if (milliseconds <= 0) return '刚刚';
  final date = DateTime.fromMillisecondsSinceEpoch(milliseconds);
  return '${_twoDigits(date.hour)}:${_twoDigits(date.minute)}';
}

String _twoDigits(int value) => value.toString().padLeft(2, '0');

void _showToast(BuildContext context, String message) {
  showAppToast(context, message);
}
