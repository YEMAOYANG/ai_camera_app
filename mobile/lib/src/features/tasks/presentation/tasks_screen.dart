import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/features/mvp/domain/mvp_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class TasksScreen extends ConsumerStatefulWidget {
  const TasksScreen({super.key});

  @override
  ConsumerState<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends ConsumerState<TasksScreen> {
  var _filter = _TaskFilter.today;

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final tasks = _filteredTasks(snapshot.tasks);
    final mainTask = snapshot.tasks.firstWhere(
      (task) => task.status == MvpTaskStatus.running,
      orElse: () => snapshot.tasks.first,
    );

    return MiraScreen(
      title: '任务',
      subtitle: '今日任务、证据确认和奖励计量',
      trailing: MiraIconButton(
        icon: Icons.add,
        label: '新建任务',
        onTap: () => _showTaskCreateSheet(context),
      ),
      children: [
        _MainTaskPanel(task: mainTask),
        const SizedBox(height: 14),
        _FilterBar(
          selected: _filter,
          onSelect: (value) => setState(() => _filter = value),
        ),
        const SizedBox(height: 14),
        if (tasks.isEmpty)
          MiraEmptyState(
            icon: Icons.event_available_outlined,
            title: '这个筛选下没有任务',
            message: '首版只展示今天的 mock 任务。后续可以接日历、模板和重复规则。',
            action: TextButton(
              onPressed: () => setState(() => _filter = _TaskFilter.today),
              child: const Text('回到今日'),
            ),
          )
        else
          MiraSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionTitle('任务列表'),
                const SizedBox(height: 8),
                for (final task in tasks)
                  MiraListRow(
                    icon: _iconForTask(task),
                    title: task.title,
                    subtitle: '${task.timeLabel} · ${task.durationLabel}',
                    tone: _toneForTask(task),
                    trailing: StatusChip(
                      label: task.status.label,
                      tone: task.status.tone,
                    ),
                    onTap: () => context.go('$taskDetailPath/${task.id}'),
                  ),
              ],
            ),
          ),
        const SizedBox(height: 14),
        _TemplateHintPanel(snapshot: snapshot),
      ],
    );
  }

  List<MvpTask> _filteredTasks(List<MvpTask> tasks) {
    return switch (_filter) {
      _TaskFilter.today => tasks,
      _TaskFilter.confirm =>
        tasks
            .where((task) => task.status == MvpTaskStatus.needsConfirmation)
            .toList(),
      _TaskFilter.abnormal =>
        tasks.where((task) => task.status == MvpTaskStatus.abnormal).toList(),
    };
  }

  IconData _iconForTask(MvpTask task) {
    return switch (task.type) {
      '学习' => Icons.menu_book_outlined,
      '作息' => Icons.nights_stay_outlined,
      '生活' => Icons.backpack_outlined,
      _ => Icons.task_alt_outlined,
    };
  }

  MiraListRowTone _toneForTask(MvpTask task) {
    return switch (task.status) {
      MvpTaskStatus.running => MiraListRowTone.blue,
      MvpTaskStatus.completed => MiraListRowTone.green,
      MvpTaskStatus.needsConfirmation => MiraListRowTone.amber,
      MvpTaskStatus.abnormal => MiraListRowTone.red,
      MvpTaskStatus.pendingStart => MiraListRowTone.neutral,
    };
  }
}

class _MainTaskPanel extends StatelessWidget {
  const _MainTaskPanel({required this.task});

  final MvpTask task;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      color: AppColors.brand.withValues(alpha: 0.1),
      borderColor: AppColors.brand.withValues(alpha: 0.12),
      radius: 24,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              StatusChip(label: task.status.label, tone: task.status.tone),
              const Spacer(),
              Text(
                '+${task.points} 分',
                style: const TextStyle(
                  color: AppColors.brand,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            task.title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 24,
              fontWeight: FontWeight.w800,
              height: 1.18,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            task.aiAdvice,
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.55,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _MiniMetric(label: '时间', value: task.timeLabel),
              const SizedBox(width: 8),
              _MiniMetric(label: '证据', value: task.evidence.parentDecision),
            ],
          ),
        ],
      ),
    );
  }
}

class _MiniMetric extends StatelessWidget {
  const _MiniMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.66),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _FilterBar extends StatelessWidget {
  const _FilterBar({required this.selected, required this.onSelect});

  final _TaskFilter selected;
  final ValueChanged<_TaskFilter> onSelect;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final filter in _TaskFilter.values) ...[
            _FilterChip(
              label: filter.label,
              selected: selected == filter,
              onTap: () => onSelect(filter),
            ),
            const SizedBox(width: 8),
          ],
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: AnimatedContainer(
        duration: AppMotion.duration(context, 160),
        constraints: const BoxConstraints(minHeight: 40),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        decoration: BoxDecoration(
          color: selected ? AppColors.ink : Colors.white.withValues(alpha: 0.7),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.white : AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 13,
            fontWeight: FontWeight.w800,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _TemplateHintPanel extends StatelessWidget {
  const _TemplateHintPanel({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('按档案推荐'),
          const SizedBox(height: 8),
          Text(
            '${snapshot.child.stage}${snapshot.child.grade}优先推荐作业自启动、小书包和睡前任务。首版只展示模板建议，不实现完整模板库。',
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.55,
              letterSpacing: 0,
            ),
          ),
        ],
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

enum _TaskFilter {
  today('今日任务'),
  confirm('待确认'),
  abnormal('异常');

  const _TaskFilter(this.label);

  final String label;
}

void _showTaskCreateSheet(BuildContext context) {
  showModalBottomSheet<void>(
    context: context,
    useRootNavigator: true,
    showDragHandle: true,
    backgroundColor: AppColors.appBackgroundWarm,
    builder: (context) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '新建任务',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '首版保留入口和状态，不接完整创建流程。后续会加入日期选择、模板和重复规则。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 16),
            MiraListRow(
              icon: Icons.add_task_outlined,
              title: '普通任务',
              subtitle: '学习、家务、吃饭、睡前任务',
              tone: MiraListRowTone.blue,
              onTap: () => Navigator.of(context).pop(),
            ),
            MiraListRow(
              icon: Icons.backpack_outlined,
              title: '小书包',
              subtitle: '留到后续模板流程，本版不单独实现',
              tone: MiraListRowTone.neutral,
              onTap: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      );
    },
  );
}
