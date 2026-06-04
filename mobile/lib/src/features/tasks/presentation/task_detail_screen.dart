import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/live_care/application/camera_repository.dart';
import 'package:mira_guardian_app/src/features/live_care/domain/camera_models.dart';
import 'package:mira_guardian_app/src/features/points/application/point_repository.dart';
import 'package:mira_guardian_app/src/features/tasks/application/task_repository.dart';
import 'package:mira_guardian_app/src/features/tasks/domain/task_models.dart';
import 'package:mira_guardian_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

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
      data: (task) => MiraScreen(
        title: task.title,
        subtitle: '${task.typeLabel} · ${task.timeLabel}',
        fixedHeader: true,
        backLabel: '返回任务',
        onBack: () => context.go(AppRoute.tasks.path),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 118),
        children: [
          _EvidencePanel(task: task),
          const SizedBox(height: 14),
          MiraSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionTitle('时间和奖励'),
                const SizedBox(height: 8),
                MiraListRow(
                  icon: Icons.timer_outlined,
                  title: task.timeLabel,
                  subtitle: '${task.scheduleLabel} · ${task.durationLabel}',
                  tone: MiraListRowTone.blue,
                ),
                MiraListRow(
                  icon: Icons.stars_outlined,
                  title: '+${task.rewardPoints} 分',
                  subtitle: task.parentDecisionLabel,
                  tone: task.status.awaitsParent
                      ? MiraListRowTone.amber
                      : MiraListRowTone.neutral,
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          _TaskEventsPanel(events: eventsValue),
          const SizedBox(height: 18),
          _TaskDetailActions(task: task, ref: ref),
        ],
      ),
      loading: () => MiraScreen(
        title: '任务详情',
        fixedHeader: true,
        backLabel: '返回任务',
        onBack: () => context.go(AppRoute.tasks.path),
        children: const [_TaskDetailLoading()],
      ),
      error: (error, _) => MiraScreen(
        title: '任务详情',
        fixedHeader: true,
        backLabel: '返回任务',
        onBack: () => context.go(AppRoute.tasks.path),
        children: [
          MiraStateView(
            variant: MiraStateVariant.serviceUnavailable,
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
    return MiraSurface(
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
                    MiraListRow(
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
      'reminder_sent' || 'reminder_failed' => Icons.volume_up_outlined,
      'auto_started' || 'manual_started' => Icons.play_circle_outline,
      'camera_monitor_started' => Icons.center_focus_strong_outlined,
      'camera_command_failed' => Icons.videocam_off_outlined,
      'parent_confirmed' => Icons.verified_outlined,
      'confirmation_rejected' => Icons.rule_outlined,
      _ => Icons.history_outlined,
    };
  }

  MiraListRowTone _eventTone(StatusTone tone) {
    return switch (tone) {
      StatusTone.success => MiraListRowTone.green,
      StatusTone.warning => MiraListRowTone.amber,
      StatusTone.danger => MiraListRowTone.red,
      _ => MiraListRowTone.neutral,
    };
  }
}

class _TaskDetailActions extends StatelessWidget {
  const _TaskDetailActions({required this.task, required this.ref});

  final GuardianTask task;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final canStart = _canStartTask(task);
    final canEditSchedule = _canEditSchedule(task);
    final canSendWrapUpReminder = _canSendWrapUpReminder(task);
    final canSendStartReminder = task.status == GuardianTaskStatus.delayed;

    final actions = <Widget>[];
    if (canStart) {
      actions.add(
        MiraPrimaryButton(
          label: '开始任务',
          trailing: const MiraButtonGlyph(icon: Icons.play_arrow_outlined),
          onTap: () => _startTask(context, ref, task),
        ),
      );
    } else if (task.status.awaitsParent) {
      actions.add(
        MiraPrimaryButton(
          label: '确认完成并发放积分',
          trailing: const MiraButtonGlyph(icon: Icons.fact_check_outlined),
          onTap: () => _confirmTask(context, ref, task),
        ),
      );
      actions.add(
        MiraSecondaryButton(
          label: '驳回证据',
          trailing: const Icon(Icons.rule_outlined, size: 18),
          onTap: () => _rejectTask(context, ref, task),
        ),
      );
    } else if (task.status == GuardianTaskStatus.inProgress) {
      actions.add(
        MiraPrimaryButton(
          label: '标记任务完成',
          trailing: const MiraButtonGlyph(icon: Icons.task_alt_outlined),
          onTap: () => _completeTask(context, ref, task),
        ),
      );
    }

    if (canSendStartReminder) {
      actions.add(
        MiraSecondaryButton(
          label: '提醒孩子开始',
          trailing: const Icon(Icons.volume_up_outlined, size: 18),
          onTap: () => _sendTaskReminder(
            context,
            ref,
            task,
            text: '“${task.title}”时间到了，我们先坐好，从第一步开始。',
            toast: '已发送温和提醒',
          ),
        ),
      );
    }

    if (canSendWrapUpReminder) {
      actions.add(
        MiraSecondaryButton(
          label: '提醒孩子收尾',
          trailing: const Icon(Icons.volume_up_outlined, size: 18),
          onTap: () => _sendTaskReminder(
            context,
            ref,
            task,
            text: '“${task.title}”快到收尾时间了，我们准备整理一下吧。',
            toast: '已提醒孩子准备收尾',
          ),
        ),
      );
    }

    if (canEditSchedule) {
      actions
        ..add(
          MiraSecondaryButton(
            label: '编辑任务',
            trailing: const Icon(Icons.edit_outlined, size: 18),
            onTap: () => _editTask(context, ref, task),
          ),
        )
        ..add(
          MiraSecondaryButton(
            label: '取消任务',
            trailing: const Icon(Icons.event_busy_outlined, size: 18),
            onTap: () => _cancelTask(context, ref, task),
          ),
        );
    }

    if (actions.isEmpty) return const SizedBox.shrink();
    return Column(
      children: [
        for (var index = 0; index < actions.length; index++) ...[
          if (index > 0) const SizedBox(height: 10),
          actions[index],
        ],
      ],
    );
  }
}

class _EvidencePanel extends StatelessWidget {
  const _EvidencePanel({required this.task});

  final GuardianTask task;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
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
              const Spacer(),
              Text(
                '+${task.rewardPoints} 分',
                style: const TextStyle(
                  color: Color(0xFFFDBA74),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _EvidenceStoryCard(task: task),
          const SizedBox(height: 14),
          Text(
            task.nextStep,
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
          Row(
            children: [
              _EvidenceMetric(label: '时间', value: task.timeLabel),
              const SizedBox(width: 8),
              _EvidenceMetric(label: '积分', value: '+${task.rewardPoints}'),
              const SizedBox(width: 8),
              _EvidenceMetric(
                label: '确认',
                value: _confirmationShortLabel(task),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _EvidenceStoryCard extends StatelessWidget {
  const _EvidenceStoryCard({required this.task});

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
              child: const SizedBox(
                width: 48,
                height: 48,
                child: Center(
                  child: Icon(
                    Icons.center_focus_strong_outlined,
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
                    _observationTitle(task),
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
                    task.observationText,
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

class _EvidenceMetric extends StatelessWidget {
  const _EvidenceMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(13),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.58),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
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
    return const MiraLoadingState(
      title: '正在加载任务详情',
      message: '正在整理任务时间、证据和奖励信息。',
    );
  }
}

bool _canStartTask(GuardianTask task) {
  return task.status == GuardianTaskStatus.scheduled ||
      task.status == GuardianTaskStatus.pending ||
      task.status == GuardianTaskStatus.reminderSent ||
      task.status == GuardianTaskStatus.delayed;
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

String _observationTitle(GuardianTask task) {
  if (task.status == GuardianTaskStatus.inProgress) return '实时观察建议';
  if (task.status == GuardianTaskStatus.delayed) return '需要提醒';
  if (task.status.awaitsParent) return '等待你确认完成情况';
  if (task.status == GuardianTaskStatus.completed ||
      task.status == GuardianTaskStatus.confirmed) {
    return '完成记录';
  }
  if (task.status == GuardianTaskStatus.missed) return '任务未完成';
  return '任务安排';
}

String _confirmationShortLabel(GuardianTask task) {
  if (!task.requiresParentConfirmation) return '自动记录';
  if (task.status.awaitsParent) return '待确认';
  if (task.status == GuardianTaskStatus.confirmed) return '已确认';
  return '需确认';
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

Future<void> _startTask(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task,
) async {
  try {
    await ref.read(taskRepositoryProvider).startTask(task.id);
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, '任务已开始');
  } on TaskException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _sendTaskReminder(
  BuildContext context,
  WidgetRef ref,
  GuardianTask task, {
  required String text,
  required String toast,
}) async {
  try {
    await ref.read(cameraRepositoryProvider).speak(text, taskId: task.id);
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, toast);
  } on CameraException catch (error) {
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
      _showToast(context, '已确认完成，+${task.rewardPoints} 积分已写入流水');
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
  try {
    await ref
        .read(taskRepositoryProvider)
        .rejectConfirmation(task.id, reason: '证据不足，等待孩子补充完成。');
    _invalidateTaskData(ref, task.id);
    if (context.mounted) _showToast(context, '已驳回任务证据');
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
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) {
      return AlertDialog(
        title: const Text('取消任务'),
        content: Text('确认取消“${task.title}”？取消后仍会保留记录。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('先不取消'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('确认取消'),
          ),
        ],
      );
    },
  );
  if (confirmed != true) return;

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
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.ink,
      ),
    );
}
