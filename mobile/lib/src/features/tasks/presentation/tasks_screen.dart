import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/platform/native_date_picker.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/domain/task_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_compact_toggle.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

final taskSelectedDateProvider = StateProvider<DateTime>((ref) {
  return _dayOnly(DateTime.now());
});

const _taskStartPreparationMinutes = 5;

class TasksScreen extends ConsumerStatefulWidget {
  const TasksScreen({super.key});

  @override
  ConsumerState<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends ConsumerState<TasksScreen> {
  late DateTime _selectedDate;
  late DateTime _weekStart;

  @override
  void initState() {
    super.initState();
    final selectedDate = _dayOnly(ref.read(taskSelectedDateProvider));
    _selectedDate = selectedDate;
    _weekStart = _startOfWeek(selectedDate);
  }

  @override
  Widget build(BuildContext context) {
    final points = ref.watch(pointsSummaryProvider);
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final childAgeGroup = taskAgeGroupForChild(
      stage: snapshot.child.stage,
      grade: snapshot.child.grade,
    );
    final childId = points.asData?.value.account.childId;
    final query = TaskWeekQuery(
      startDate: _weekStart,
      endDate: _weekStart.add(const Duration(days: 6)),
      childId: childId?.isNotEmpty == true ? childId : null,
    );
    final weekTasks = ref.watch(taskWeekProvider(query));

    return AppScreen(
      title: '任务',
      pinnedHeaderHeight: 146,
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
      headerContent: _WeekHeader(
        weekStart: _weekStart,
        selectedDate: _selectedDate,
        tasks: weekTasks.asData?.value ?? const [],
        onPrevious: () => _shiftWeek(-1),
        onNext: () => _shiftWeek(1),
        onToday: _goToToday,
        onSelectDate: (date) => _selectDate(date),
      ),
      children: [
        weekTasks.when(
          data: (tasks) {
            final dayTasks = _tasksForSelectedDay(tasks);
            if (dayTasks.isEmpty) {
              return _TaskEmptyState(
                selectedDate: _selectedDate,
                weekIsEmpty: tasks.isEmpty,
                onCreate: () =>
                    _openCreateSheet(childId, childAgeGroup: childAgeGroup),
                onTemplate: () => _openCreateSheet(
                  childId,
                  childAgeGroup: childAgeGroup,
                  initialMode: TaskEntryMode.day,
                  showTemplatePicker: true,
                ),
              );
            }
            return _GroupedTaskList(
              tasks: dayTasks,
              selectedDate: _selectedDate,
              onOpen: (task) => context.go('$taskDetailPath/${task.id}'),
            );
          },
          loading: () => const AppLoadingState(
            title: '正在整理本周任务',
            message: '正在同步今天和这一周的安排。',
          ),
          error: (error, _) => _TaskErrorState(
            message: error is TaskException ? error.message : '任务同步失败，请稍后重试。',
            onRetry: () => ref.invalidate(taskWeekProvider(query)),
          ),
        ),
      ],
    );
  }

  List<GuardianTask> _tasksForSelectedDay(List<GuardianTask> tasks) {
    final selected = _dateText(_selectedDate);
    return tasks.where((task) => task.scheduledDate == selected).toList()
      ..sort(_sortByStartTime);
  }

  void _shiftWeek(int delta) {
    final nextStart = _weekStart.add(Duration(days: delta * 7));
    setState(() {
      _weekStart = nextStart;
      _selectedDate = nextStart;
    });
    ref.read(taskSelectedDateProvider.notifier).state = _dayOnly(nextStart);
  }

  void _goToToday() {
    final today = _dayOnly(DateTime.now());
    setState(() {
      _selectedDate = today;
      _weekStart = _startOfWeek(today);
    });
    ref.read(taskSelectedDateProvider.notifier).state = today;
  }

  void _selectDate(DateTime date) {
    final selected = _dayOnly(date);
    setState(() => _selectedDate = selected);
    ref.read(taskSelectedDateProvider.notifier).state = selected;
  }

  Future<void> _openCreateSheet(
    String? childId, {
    required TaskAgeGroup childAgeGroup,
    TaskEntryMode initialMode = TaskEntryMode.single,
    bool showTemplatePicker = false,
  }) async {
    final fallbackChildId = childId ?? _firstKnownChildId();
    if (fallbackChildId == null || fallbackChildId.isEmpty) {
      _showToast(context, '请先完成孩子资料，再添加孩子的新任务。');
      return;
    }
    final query = TaskWeekQuery(
      startDate: _weekStart,
      endDate: _weekStart.add(const Duration(days: 6)),
      childId: fallbackChildId,
    );
    final existingTasks = ref.read(taskWeekProvider(query)).asData?.value;

    final savedDate = await showTaskFormSheet(
      context,
      childId: fallbackChildId,
      initialDate: _selectedDate,
      childAgeGroup: childAgeGroup,
      initialMode: initialMode,
      showTemplatePicker: showTemplatePicker,
      onSavedProgress: _refreshTasks,
      existingTasks: existingTasks ?? const [],
    );

    if (!mounted) return;
    if (savedDate != null) {
      final targetDate = _dayOnly(savedDate);
      setState(() {
        _selectedDate = targetDate;
        _weekStart = _startOfWeek(targetDate);
      });
      ref.read(taskSelectedDateProvider.notifier).state = targetDate;
      _refreshTasks();
      showAppStateSnackBar(
        context,
        variant: AppStateVariant.saved,
        title: '已保存',
        message: '任务已加入本周安排。',
      );
    }
  }

  String? _firstKnownChildId() {
    final query = TaskWeekQuery(
      startDate: _weekStart,
      endDate: _weekStart.add(const Duration(days: 6)),
    );
    final tasks = ref.read(taskWeekProvider(query)).asData?.value;
    if (tasks == null || tasks.isEmpty) return null;
    return tasks.first.childId;
  }

  void _refreshTasks() {
    ref
      ..invalidate(taskListProvider)
      ..invalidate(todayTasksProvider);
    final childId = ref
        .read(pointsSummaryProvider)
        .asData
        ?.value
        .account
        .childId;
    ref.invalidate(
      taskWeekProvider(
        TaskWeekQuery(
          startDate: _weekStart,
          endDate: _weekStart.add(const Duration(days: 6)),
          childId: childId?.isNotEmpty == true ? childId : null,
        ),
      ),
    );
  }
}

Future<DateTime?> showTaskFormSheet(
  BuildContext context, {
  required String childId,
  required DateTime initialDate,
  required TaskAgeGroup childAgeGroup,
  TaskEntryMode initialMode = TaskEntryMode.single,
  bool showTemplatePicker = false,
  VoidCallback? onSavedProgress,
  GuardianTask? task,
  List<GuardianTask> existingTasks = const [],
}) {
  return showAppBottomSheet<DateTime>(
    context: context,
    maxHeightFactor: 0.92,
    child: TaskFormSheet(
      childId: childId,
      initialDate: initialDate,
      childAgeGroup: childAgeGroup,
      initialMode: initialMode,
      showTemplatePicker: showTemplatePicker,
      onSavedProgress: onSavedProgress,
      task: task,
      existingTasks: existingTasks,
    ),
  );
}

class _WeekHeader extends StatelessWidget {
  const _WeekHeader({
    required this.weekStart,
    required this.selectedDate,
    required this.tasks,
    required this.onPrevious,
    required this.onNext,
    required this.onToday,
    required this.onSelectDate,
  });

  final DateTime weekStart;
  final DateTime selectedDate;
  final List<GuardianTask> tasks;
  final VoidCallback onPrevious;
  final VoidCallback onNext;
  final VoidCallback onToday;
  final ValueChanged<DateTime> onSelectDate;

  @override
  Widget build(BuildContext context) {
    final weekEnd = weekStart.add(const Duration(days: 6));
    final isCurrentWeek = _isSameWeek(weekStart, DateTime.now());
    final days = List.generate(7, (index) {
      return weekStart.add(Duration(days: index));
    });

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            _WeekNavButton(icon: Icons.chevron_left, onTap: onPrevious),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Text(
                    isCurrentWeek ? '本周' : '任务周',
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${_dateShort(weekStart)} - ${_dateShort(weekEnd)}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 16,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            if (!isCurrentWeek) ...[
              _BackToThisWeekButton(onTap: onToday),
              const SizedBox(width: 8),
            ],
            _WeekNavButton(icon: Icons.chevron_right, onTap: onNext),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            for (var index = 0; index < days.length; index++) ...[
              Expanded(
                child: _DayChip(
                  date: days[index],
                  selected: _sameDay(days[index], selectedDate),
                  count: _countForDate(tasks, days[index]),
                  onTap: () => onSelectDate(days[index]),
                ),
              ),
              if (index != days.length - 1) const SizedBox(width: 5),
            ],
          ],
        ),
      ],
    );
  }
}

class _BackToThisWeekButton extends StatelessWidget {
  const _BackToThisWeekButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.primarySoft,
          borderRadius: BorderRadius.circular(999),
        ),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          child: Text(
            '回到本周',
            style: TextStyle(
              color: AppColors.primary,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

class _WeekNavButton extends StatelessWidget {
  const _WeekNavButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.74),
          borderRadius: BorderRadius.circular(14),
        ),
        child: SizedBox(
          width: 40,
          height: 40,
          child: Center(child: Icon(icon, color: AppColors.ink, size: 20)),
        ),
      ),
    );
  }
}

class _DayChip extends StatelessWidget {
  const _DayChip({
    required this.date,
    required this.selected,
    required this.count,
    required this.onTap,
  });

  final DateTime date;
  final bool selected;
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isToday = _sameDay(date, DateTime.now());
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: AnimatedContainer(
        constraints: const BoxConstraints(minHeight: 66),
        duration: AppMotion.duration(context, 180),
        curve: Curves.easeOutCubic,
        padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 8),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primary
              : isToday
              ? AppColors.selectedBg
              : AppColors.surfaceSoft,
          borderRadius: BorderRadius.circular(AppRadii.control),
          border: Border.all(
            color: selected
                ? AppColors.primary
                : isToday
                ? AppColors.primary.withValues(alpha: 0.14)
                : AppColors.borderSoft,
          ),
        ),
        child: Column(
          children: [
            Text(
              _weekdayShort(date),
              style: TextStyle(
                color: selected
                    ? Colors.white.withValues(alpha: 0.72)
                    : AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${date.day}',
              style: TextStyle(
                color: selected ? Colors.white : AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 20,
                fontWeight: FontWeight.w700,
                height: 1,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              count > 0 ? '$count项' : (isToday ? '今天' : ''),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: selected
                    ? Colors.white.withValues(alpha: 0.72)
                    : isToday
                    ? AppColors.primary
                    : AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 10.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GroupedTaskList extends StatelessWidget {
  const _GroupedTaskList({
    required this.tasks,
    required this.selectedDate,
    required this.onOpen,
  });

  final List<GuardianTask> tasks;
  final DateTime selectedDate;
  final ValueChanged<GuardianTask> onOpen;

  @override
  Widget build(BuildContext context) {
    final awaiting = tasks.where((task) => task.status.awaitsParent).toList();
    final needsCare = tasks
        .where((task) => task.status.needsCare && !task.status.awaitsParent)
        .toList();
    final completed = tasks.where((task) => task.status.isDone).toList();
    final active = tasks
        .where(
          (task) =>
              !task.status.awaitsParent &&
              !task.status.needsCare &&
              !task.status.isDone,
        )
        .toList();

    final sections = <_TaskSectionData>[
      if (awaiting.isNotEmpty) _TaskSectionData('待确认', awaiting),
      if (needsCare.isNotEmpty) _TaskSectionData('需要处理', needsCare),
      if (active.isNotEmpty)
        _TaskSectionData(
          _sameDay(selectedDate, DateTime.now())
              ? '今天'
              : _dateShort(selectedDate),
          active,
        ),
      if (completed.isNotEmpty) _TaskSectionData('已完成', completed, muted: true),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var index = 0; index < sections.length; index++) ...[
          _TaskSection(section: sections[index], onOpen: onOpen),
          if (index != sections.length - 1) const SizedBox(height: 16),
        ],
      ],
    );
  }
}

class _TaskSectionData {
  const _TaskSectionData(this.title, this.tasks, {this.muted = false});

  final String title;
  final List<GuardianTask> tasks;
  final bool muted;
}

class _TaskSection extends StatelessWidget {
  const _TaskSection({required this.section, required this.onOpen});

  final _TaskSectionData section;
  final ValueChanged<GuardianTask> onOpen;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              section.title,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 16,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '${section.tasks.length} 项',
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        _TaskTimeline(
          tasks: section.tasks,
          muted: section.muted,
          onOpen: onOpen,
        ),
      ],
    );
  }
}

class _TaskTimeline extends StatelessWidget {
  const _TaskTimeline({
    required this.tasks,
    required this.onOpen,
    this.muted = false,
  });

  final List<GuardianTask> tasks;
  final ValueChanged<GuardianTask> onOpen;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var index = 0; index < tasks.length; index++)
          _TaskTimelineCard(
            task: tasks[index],
            isLast: index == tasks.length - 1,
            muted: muted,
            onTap: () => onOpen(tasks[index]),
          ),
      ],
    );
  }
}

class _TaskTimelineCard extends StatelessWidget {
  const _TaskTimelineCard({
    required this.task,
    required this.isLast,
    required this.muted,
    required this.onTap,
  });

  final GuardianTask task;
  final bool isLast;
  final bool muted;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final tone = _toneColor(task);
    final showObservation =
        task.aiObservationSummary.isNotEmpty ||
        (task.evidenceSummary.isNotEmpty && task.status.awaitsParent);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 42,
          child: Column(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: tone.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: SizedBox(
                  width: 36,
                  height: 36,
                  child: Center(
                    child: Icon(_iconForTask(task), color: tone, size: 19),
                  ),
                ),
              ),
              if (!isLast)
                Container(
                  width: 2,
                  height: 68,
                  margin: const EdgeInsets.symmetric(vertical: 5),
                  decoration: BoxDecoration(
                    color: AppColors.muted.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: AppSurface(
            onTap: onTap,
            padding: const EdgeInsets.fromLTRB(15, 14, 14, 14),
            radius: 18,
            color: Colors.white.withValues(alpha: muted ? 0.44 : 0.72),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        task.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: muted ? AppColors.muted : AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 16,
                          fontWeight: FontWeight.w900,
                          height: 1.25,
                          letterSpacing: 0,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    StatusChip(
                      label: task.status.label,
                      tone: task.status.tone,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  children: [
                    _TaskMetaPill(label: task.typeLabel),
                    _TaskMetaPill(label: task.timeLabel),
                    if (task.rewardPoints > 0)
                      _TaskMetaPill(label: '+${task.rewardPoints} 分'),
                    if (task.requiresParentConfirmation)
                      const _TaskMetaPill(label: '需家长确认'),
                  ],
                ),
                if (showObservation) ...[
                  const SizedBox(height: 9),
                  Text(
                    task.observationText,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      height: 1.48,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _TaskMetaPill extends StatelessWidget {
  const _TaskMetaPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.appBackgroundMid.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        child: Text(
          label,
          style: const TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 11.5,
            fontWeight: FontWeight.w800,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _TaskEmptyState extends StatelessWidget {
  const _TaskEmptyState({
    required this.selectedDate,
    required this.weekIsEmpty,
    required this.onCreate,
    required this.onTemplate,
  });

  final DateTime selectedDate;
  final bool weekIsEmpty;
  final VoidCallback onCreate;
  final VoidCallback onTemplate;

  @override
  Widget build(BuildContext context) {
    final isPast = _dayOnly(selectedDate).isBefore(_dayOnly(DateTime.now()));
    final isToday = _sameDay(selectedDate, DateTime.now());
    final title = weekIsEmpty
        ? '本周还没有任务'
        : isToday
        ? '今天没有任务'
        : '${_dateShort(selectedDate)}没有任务';
    final message = isPast ? '这一天没有安排记录。' : '添加一个任务，帮孩子把安排记清楚。';

    return AppStateView(
      variant: AppStateVariant.emptyTasks,
      title: title,
      message: message,
      primaryActionLabel: isPast ? null : '添加孩子的新任务',
      onPrimaryAction: isPast ? null : onCreate,
      secondaryActionLabel: isPast ? null : '从模板添加',
      onSecondaryAction: isPast ? null : onTemplate,
    );
  }
}

class _TaskErrorState extends StatelessWidget {
  const _TaskErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppStateView(
      variant: AppStateVariant.serviceUnavailable,
      title: '任务更新失败',
      message: message,
      primaryActionLabel: '重新加载',
      onPrimaryAction: onRetry,
    );
  }
}

class TaskFormSheet extends ConsumerStatefulWidget {
  const TaskFormSheet({
    required this.childId,
    required this.initialDate,
    required this.childAgeGroup,
    this.initialMode = TaskEntryMode.single,
    this.showTemplatePicker = false,
    this.onSavedProgress,
    this.task,
    this.existingTasks = const [],
    super.key,
  });

  final String childId;
  final DateTime initialDate;
  final TaskAgeGroup childAgeGroup;
  final TaskEntryMode initialMode;
  final bool showTemplatePicker;
  final VoidCallback? onSavedProgress;
  final GuardianTask? task;
  final List<GuardianTask> existingTasks;

  @override
  ConsumerState<TaskFormSheet> createState() => _TaskFormSheetState();
}

class _TaskFormSheetState extends ConsumerState<TaskFormSheet> {
  late final TextEditingController _titleController;
  late final TextEditingController _extraController;
  late final TextEditingController _descriptionController;
  late final TextEditingController _rewardController;
  late final ScrollController _sheetScrollController;
  late DateTime _date;
  late String _taskType;
  late String _startTime;
  late String _dueTime;
  late String _scheduleType;
  late bool _requiresParentConfirmation;
  late TaskEntryMode _mode;
  var _rowSequence = 0;
  late List<_ScheduleDraftRow> _rows;
  var _saving = false;
  var _savingContinue = false;
  String? _error;
  var _saveFailed = false;

  @override
  void initState() {
    super.initState();
    final task = widget.task;
    _taskType = task?.type ?? 'learning';
    final descriptionFields = _splitTaskDescription(
      task?.description ?? '',
      _taskConfig(_taskType),
    );
    _titleController = TextEditingController(text: task?.title ?? '');
    _extraController = TextEditingController(text: descriptionFields.extra);
    _descriptionController = TextEditingController(
      text: descriptionFields.detail,
    );
    _sheetScrollController = ScrollController();
    _rewardController = TextEditingController(
      text: task == null
          ? '3'
          : task.rewardPoints > 0
          ? '${task.rewardPoints}'
          : '',
    );
    _date = task == null
        ? widget.initialDate
        : (_parseDate(task.scheduledDate) ?? widget.initialDate);
    final suggestedStartTime = _suggestedStartTimeForDate(_date);
    _startTime = task?.scheduledStart.isNotEmpty == true
        ? task!.scheduledStart
        : suggestedStartTime;
    _dueTime = task?.scheduledEnd.isNotEmpty == true
        ? task!.scheduledEnd
        : _addMinutes(_startTime, _durationForType(_taskType));
    _scheduleType = task?.scheduleType ?? 'one_time';
    _requiresParentConfirmation = task?.requiresParentConfirmation ?? true;
    _mode = widget.task == null ? widget.initialMode : TaskEntryMode.single;
    _rows = [
      _newScheduleRow(
        taskType: _recommendedTaskType(widget.childAgeGroup),
        startTime: _startTime,
      ),
    ];
    if (widget.showTemplatePicker) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _showTemplateSheet();
      });
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    _extraController.dispose();
    _descriptionController.dispose();
    _rewardController.dispose();
    _sheetScrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: bottomInset),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final sheetHeight = constraints.maxHeight.isFinite
              ? constraints.maxHeight
              : MediaQuery.sizeOf(context).height - bottomInset;

          return SizedBox(
            height: sheetHeight,
            child: SafeArea(
              top: false,
              bottom: true,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const AppSheetHandle(),
                    const SizedBox(height: 10),
                    Expanded(
                      child: SingleChildScrollView(
                        controller: _sheetScrollController,
                        keyboardDismissBehavior:
                            ScrollViewKeyboardDismissBehavior.onDrag,
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.task == null
                                  ? (_mode == TaskEntryMode.day
                                        ? '一天安排'
                                        : '添加孩子的新任务')
                                  : '编辑任务',
                              style: const TextStyle(
                                color: AppColors.ink,
                                fontFamily: AppTypography.systemFont,
                                fontSize: 22,
                                fontWeight: FontWeight.w900,
                                letterSpacing: 0,
                              ),
                            ),
                            if (widget.task == null) ...[
                              const SizedBox(height: 14),
                              _TaskModeSwitch(
                                value: _mode,
                                onChanged: (mode) => setState(() {
                                  _mode = mode;
                                  _error = null;
                                }),
                              ),
                            ],
                            const SizedBox(height: 16),
                            if (_mode == TaskEntryMode.single)
                              _buildSingleTaskForm()
                            else
                              _buildDayScheduleForm(),
                            if (_error != null) ...[
                              const SizedBox(height: 12),
                              if (_saveFailed)
                                AppInlineState(
                                  variant: AppStateVariant.saveFailed,
                                  title: '保存失败',
                                  message: _error!,
                                )
                              else
                                Text(
                                  _error!,
                                  style: const TextStyle(
                                    color: AppColors.danger,
                                    fontFamily: AppTypography.systemFont,
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    height: 1.4,
                                  ),
                                ),
                            ],
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    if (_mode == TaskEntryMode.single)
                      _SingleTaskActions(
                        editing: widget.task != null,
                        saving: _saving,
                        savingContinue: _savingContinue,
                        onSave: _saving
                            ? null
                            : () => _saveSingle(continueAdding: false),
                        onSaveAndContinue: _saving || widget.task != null
                            ? null
                            : () => _saveSingle(continueAdding: true),
                      )
                    else
                      AppPrimaryButton(
                        label: _saving ? '保存中' : '保存一天安排',
                        loading: _saving,
                        trailing: const AppButtonGlyph(icon: Icons.check),
                        onTap: _saving ? null : _saveDaySchedule,
                      ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildSingleTaskForm() {
    final config = _taskConfig(_taskType);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _FieldLabel('任务类型'),
        const SizedBox(height: 8),
        _PickerField(
          label: config.label,
          supportingText: config.description,
          icon: config.icon,
          onTap: _chooseTaskType,
        ),
        if (config.extraLabel != null) ...[
          const SizedBox(height: 16),
          _FieldLabel(config.extraLabel!),
          const SizedBox(height: 8),
          _TaskTextField(
            controller: _extraController,
            hintText: config.extraHint ?? '',
          ),
        ],
        const SizedBox(height: 16),
        _FieldLabel(config.titleLabel),
        const SizedBox(height: 8),
        _TaskTextField(
          controller: _titleController,
          hintText: config.titleHint,
        ),
        const SizedBox(height: 16),
        _FieldLabel('日期'),
        const SizedBox(height: 8),
        _PickerField(
          label: _dateChoiceLabel(_date),
          supportingText: _dateText(_date),
          icon: Icons.event_outlined,
          onTap: _pickDate,
        ),
        const SizedBox(height: 16),
        LayoutBuilder(
          builder: (context, constraints) {
            final twoColumns = constraints.maxWidth >= 330;
            final start = _PickerField(
              label: _startTime,
              supportingText: '开始',
              icon: Icons.schedule_outlined,
              onTap: () => _pickSingleTime(start: true),
            );
            final due = _PickerField(
              label: _dueTime,
              supportingText: '结束',
              icon: Icons.timer_outlined,
              onTap: () => _pickSingleTime(start: false),
            );
            if (!twoColumns) {
              return Column(children: [start, const SizedBox(height: 10), due]);
            }
            return Row(
              children: [
                Expanded(child: start),
                const SizedBox(width: 10),
                Expanded(child: due),
              ],
            );
          },
        ),
        const SizedBox(height: 16),
        _FieldLabel('重复规则'),
        const SizedBox(height: 8),
        _PickerField(
          label: _scheduleLabel(_scheduleType),
          supportingText: '可按需要重复提醒',
          icon: Icons.repeat_outlined,
          onTap: _chooseScheduleType,
        ),
        const SizedBox(height: 16),
        _FieldLabel('奖励积分'),
        const SizedBox(height: 8),
        _TaskTextField(
          controller: _rewardController,
          hintText: '${config.defaultReward}',
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        ),
        const SizedBox(height: 16),
        _FieldLabel(config.detailLabel),
        const SizedBox(height: 8),
        _TaskTextField(
          controller: _descriptionController,
          hintText: config.detailHint,
          minLines: 2,
          maxLines: 4,
        ),
        const SizedBox(height: 12),
        _ConfirmSwitch(
          value: _requiresParentConfirmation,
          onChanged: (value) {
            setState(() => _requiresParentConfirmation = value);
          },
        ),
      ],
    );
  }

  Widget _buildDayScheduleForm() {
    final sortedRows = _rows.toList()
      ..sort(
        (a, b) =>
            _minutesOfDay(a.startTime).compareTo(_minutesOfDay(b.startTime)),
      );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _FieldLabel('日期'),
        const SizedBox(height: 8),
        _PickerField(
          label: _dateChoiceLabel(_date),
          supportingText: _dateText(_date),
          icon: Icons.event_outlined,
          onTap: _pickDate,
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _PickerField(
                label: _scheduleLabel(_scheduleType),
                supportingText: '整体重复',
                icon: Icons.repeat_outlined,
                onTap: _chooseScheduleType,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _CompactActionButton(
                label: '从模板添加',
                icon: Icons.auto_awesome_motion_outlined,
                onTap: _showTemplateSheet,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        for (var index = 0; index < sortedRows.length; index++) ...[
          _ScheduleRowCard(
            index: index,
            row: sortedRows[index],
            canDelete: _rows.length > 1,
            onPickStart: () => _pickRowTime(sortedRows[index], start: true),
            onPickEnd: () => _pickRowTime(sortedRows[index], start: false),
            onPickType: () => _chooseRowType(sortedRows[index]),
            onTitleChanged: (value) => _updateRow(
              sortedRows[index],
              sortedRows[index].copyWith(title: value),
            ),
            onRewardChanged: (value) => _updateRow(
              sortedRows[index],
              sortedRows[index].copyWith(
                rewardPoints: int.tryParse(value) ?? 0,
              ),
            ),
            onConfirmChanged: (value) => _updateRow(
              sortedRows[index],
              sortedRows[index].copyWith(requiresParentConfirmation: value),
            ),
            onDelete: () => _deleteRow(sortedRows[index]),
          ),
          const SizedBox(height: 10),
        ],
        _CompactActionButton(
          label: '添加一项',
          icon: Icons.add,
          onTap: _addScheduleRow,
        ),
      ],
    );
  }

  Future<void> _saveSingle({required bool continueAdding}) async {
    final title = _titleController.text.trim();
    final reward = int.tryParse(_rewardController.text.trim()) ?? 0;
    if (title.isEmpty) {
      setState(() {
        _error = '请输入任务名称。';
        _saveFailed = false;
      });
      return;
    }
    if (_startsBeforeAllowedDate(_startTime, _date)) {
      setState(() {
        _error = '开始时间不能早于现在。';
        _saveFailed = false;
      });
      return;
    }
    if (_minutesOfDay(_dueTime) <= _minutesOfDay(_startTime)) {
      setState(() {
        _error = '结束时间要晚于开始时间。';
        _saveFailed = false;
      });
      return;
    }

    setState(() {
      _saving = true;
      _savingContinue = continueAdding;
      _error = null;
      _saveFailed = false;
    });

    try {
      final repository = ref.read(taskRepositoryProvider);
      final config = _taskConfig(_taskType);
      final description = _combinedDescription(
        config.extraLabel == null ? '' : _extraController.text.trim(),
        _descriptionController.text.trim(),
      );
      if (widget.task == null) {
        await repository.createTask(
          GuardianTaskDraft(
            childId: widget.childId,
            title: title,
            description: description,
            taskType: _taskType,
            date: _date,
            startTime: _startTime,
            dueTime: _dueTime,
            scheduleType: _scheduleType,
            repeatRule: _repeatRulePayload(_scheduleType),
            rewardPoints: reward,
            requiresParentConfirmation: _requiresParentConfirmation,
          ),
        );
        widget.onSavedProgress?.call();
      } else {
        await repository.updateTask(widget.task!.id, {
          'title': title,
          'description': description,
          'taskType': _taskType,
          'scheduledDate': _dateText(_date),
          'scheduledStart': _startTime,
          'scheduledEnd': _dueTime,
          'startAt': '${_dateText(_date)}T$_startTime:00',
          'dueAt': '${_dateText(_date)}T$_dueTime:00',
          'scheduleType': _scheduleType,
          'repeatRule': _repeatRulePayload(_scheduleType),
          'rewardPoints': reward,
          'requiresParentConfirmation': _requiresParentConfirmation,
        });
        widget.onSavedProgress?.call();
      }
      if (!mounted) return;
      if (continueAdding) {
        final nextStart = _suggestedStartAfterBoundary(_date, _dueTime);
        setState(() {
          _saving = false;
          _savingContinue = false;
          _titleController.clear();
          _descriptionController.clear();
          _extraController.clear();
          _startTime = nextStart;
          _dueTime = _addMinutes(nextStart, _durationForType(_taskType));
        });
        _showToast(context, '已添加，继续安排下一项');
      } else {
        Navigator.of(context).pop(_date);
      }
    } on TaskException catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _savingContinue = false;
          _error = error.message.isEmpty ? '保存失败，请再试一次。' : error.message;
          _saveFailed = true;
        });
      }
    }
  }

  Future<void> _saveDaySchedule() async {
    final rows = _validatedScheduleRows();
    if (rows == null) return;

    setState(() {
      _saving = true;
      _error = null;
      _saveFailed = false;
    });

    try {
      final drafts = rows.map((row) {
        return GuardianTaskDraft(
          childId: widget.childId,
          title: row.title.trim(),
          description: '',
          taskType: row.taskType,
          date: _date,
          startTime: row.startTime,
          dueTime: row.endTime,
          scheduleType: _scheduleType,
          repeatRule: _repeatRulePayload(_scheduleType),
          rewardPoints: row.rewardPoints,
          requiresParentConfirmation: row.requiresParentConfirmation,
        );
      }).toList();
      await ref.read(taskRepositoryProvider).createTasks(drafts, date: _date);
      widget.onSavedProgress?.call();
      if (mounted) Navigator.of(context).pop(_date);
    } on TaskException catch (error) {
      if (mounted) {
        setState(() {
          _saving = false;
          _error = error.message.isEmpty ? '保存失败，请再试一次。' : error.message;
          _saveFailed = true;
        });
      }
    }
  }

  List<_ScheduleDraftRow>? _validatedScheduleRows() {
    final sorted = _rows.toList()
      ..sort(
        (a, b) =>
            _minutesOfDay(a.startTime).compareTo(_minutesOfDay(b.startTime)),
      );
    final errors = <String, String?>{};
    for (var index = 0; index < sorted.length; index++) {
      final row = sorted[index];
      if (row.title.trim().isEmpty) {
        errors[row.id] = '请输入任务名称';
        continue;
      }
      if (_startsBeforeAllowedDate(row.startTime, _date)) {
        errors[row.id] = '开始时间不能早于现在';
        continue;
      }
      if (_minutesOfDay(row.endTime) <= _minutesOfDay(row.startTime)) {
        errors[row.id] = '结束时间要晚于开始时间';
        continue;
      }
      if (index > 0 &&
          _minutesOfDay(sorted[index - 1].endTime) >
              _minutesOfDay(row.startTime)) {
        errors[row.id] = '这段时间和上一项重叠';
      }
    }

    if (errors.isNotEmpty) {
      setState(() {
        _rows = _rows
            .map(
              (row) => row.copyWith(
                error: errors[row.id],
                clearError: !errors.containsKey(row.id),
              ),
            )
            .toList();
        _error = '请先处理标红的时间段。';
        _saveFailed = false;
      });
      return null;
    }

    setState(() {
      _rows = _rows.map((row) => row.copyWith(clearError: true)).toList();
      _error = null;
    });
    return sorted.map((row) => row.copyWith(clearError: true)).toList();
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await NativeDatePicker.pickDate(
      title: '选择日期',
      initialDate: _date,
      minDate: DateTime(now.year - 1, now.month, now.day),
      maxDate: DateTime(now.year + 2, now.month, now.day),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _date = _dayOnly(picked);
      if (widget.task == null && _mode == TaskEntryMode.single) {
        _startTime = _suggestedStartTimeForDate(_date);
        _dueTime = _addMinutes(_startTime, _durationForType(_taskType));
      }
      _rows = _normalizedRowsForSelectedDate();
    });
  }

  Future<String?> _pickTime(
    String initial, {
    String? minTime,
    String? maxTime,
    String invalidMessage = '结束时间要晚于开始时间',
  }) {
    return showAppBottomSheet<String>(
      context: context,
      maxHeightFactor: 0.58,
      child: _AppTimePickerSheet(
        initialValue: initial,
        minMinutes: minTime == null ? 0 : _minutesOfDay(minTime),
        maxMinutes: maxTime == null ? 23 * 60 + 59 : _minutesOfDay(maxTime),
        invalidMessage: invalidMessage,
      ),
    );
  }

  Future<void> _pickSingleTime({required bool start}) async {
    final minStart = _minimumStartTimeForDate(_date);
    final picked = await _pickTime(
      start ? _startTime : _dueTime,
      minTime: start ? minStart : _addMinutes(_startTime, 1),
      maxTime: start ? '23:58' : null,
      invalidMessage: start ? '开始时间不能早于现在' : '结束时间要晚于开始时间',
    );
    if (picked == null) return;
    var shiftedEnd = false;
    setState(() {
      if (start) {
        _startTime = picked;
        if (_minutesOfDay(_dueTime) <= _minutesOfDay(_startTime)) {
          _dueTime = _addMinutes(_startTime, _durationForType(_taskType));
          shiftedEnd = true;
        }
      } else {
        _dueTime = picked;
      }
    });
    if (shiftedEnd && mounted) _showToast(context, '结束时间已顺延');
  }

  Future<void> _pickRowTime(
    _ScheduleDraftRow row, {
    required bool start,
  }) async {
    final minStart = _minimumStartTimeForDate(_date);
    final picked = await _pickTime(
      start ? row.startTime : row.endTime,
      minTime: start ? minStart : _addMinutes(row.startTime, 1),
      maxTime: start ? '23:58' : null,
      invalidMessage: start ? '开始时间不能早于现在' : '结束时间要晚于开始时间',
    );
    if (picked == null) return;
    var shiftedEnd = false;
    final next = start
        ? row.copyWith(
            startTime: picked,
            endTime: () {
              if (_minutesOfDay(row.endTime) > _minutesOfDay(picked)) {
                return row.endTime;
              }
              shiftedEnd = true;
              return _addMinutes(picked, _durationForType(row.taskType));
            }(),
            clearError: true,
          )
        : row.copyWith(endTime: picked, clearError: true);
    _updateRow(row, next);
    if (shiftedEnd && mounted) _showToast(context, '结束时间已顺延');
  }

  Future<void> _chooseTaskType() async {
    final selected = await _showTaskTypePicker(_taskType);
    if (selected == null || !mounted) return;
    final duration = _durationForType(selected);
    final selectedConfig = _taskConfig(selected);
    setState(() {
      _taskType = selected;
      _dueTime = _addMinutes(_startTime, duration);
      _rewardController.text = '${selectedConfig.defaultReward}';
      if (selectedConfig.extraLabel == null) _extraController.clear();
      _error = null;
    });
  }

  Future<void> _chooseRowType(_ScheduleDraftRow row) async {
    final selected = await _showTaskTypePicker(row.taskType);
    if (selected == null || !mounted) return;
    _updateRow(
      row,
      row.copyWith(
        taskType: selected,
        endTime: _addMinutes(row.startTime, _durationForType(selected)),
        rewardPoints: _taskConfig(selected).defaultReward,
        requiresParentConfirmation: _taskConfig(
          selected,
        ).defaultRequiresConfirmation,
        clearError: true,
      ),
    );
  }

  Future<String?> _showTaskTypePicker(String current) {
    final configs = _taskTypeConfigsForAge(widget.childAgeGroup);
    return showAppBottomSheet<String>(
      context: context,
      child: _PickerSheetScaffold(
        title: '选择任务类型',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final config in configs)
              _PickerListTile(
                icon: config.icon,
                title: config.label,
                message: config.description,
                selected: current == config.value,
                onTap: () => Navigator.of(context).pop(config.value),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _chooseScheduleType() async {
    final selected = await showAppBottomSheet<String>(
      context: context,
      child: _PickerSheetScaffold(
        title: '重复规则',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final option in _scheduleOptions)
              _PickerListTile(
                icon: Icons.repeat_outlined,
                title: option.label,
                message: option.message,
                selected: _scheduleType == option.value,
                onTap: () => Navigator.of(context).pop(option.value),
              ),
          ],
        ),
      ),
    );
    if (selected == null || !mounted) return;
    setState(() => _scheduleType = selected);
  }

  Future<void> _showTemplateSheet() async {
    final recommended = _templatesForAge(widget.childAgeGroup);
    final others = _taskTemplates
        .where((template) => !recommended.contains(template))
        .toList();
    final selected = await showAppBottomSheet<_TaskTemplate>(
      context: context,
      maxHeightFactor: 0.78,
      child: _PickerSheetScaffold(
        title: '选择一个常用安排',
        subtitle: '套用后可以继续修改。',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _TemplateSection(
              title: '推荐',
              templates: recommended,
              onSelect: (template) => Navigator.of(context).pop(template),
            ),
            if (others.isNotEmpty) ...[
              const SizedBox(height: 16),
              _TemplateSection(
                title: '更多安排',
                templates: others,
                onSelect: (template) => Navigator.of(context).pop(template),
              ),
            ],
          ],
        ),
      ),
    );
    if (selected == null || !mounted) return;
    setState(() {
      _mode = TaskEntryMode.day;
      _rows = _rowsFromTemplate(selected.rows);
      _scheduleType = selected.scheduleType;
      _error = null;
      _saveFailed = false;
    });
    if (mounted) _showToast(context, '已套用，可继续修改');
  }

  List<_ScheduleDraftRow> _rowsFromTemplate(List<_TaskTemplateRow> rows) {
    if (rows.isEmpty) return const [];
    final firstStart = rows
        .map((row) => _minutesOfDay(row.startTime))
        .reduce((a, b) => a < b ? a : b);
    final targetStart = _minutesOfDay(_suggestedStartTimeForDate(_date));
    final offset = targetStart > firstStart ? targetStart - firstStart : 0;
    return rows
        .map((row) => _rowFromTemplate(row, minuteOffset: offset))
        .toList();
  }

  _ScheduleDraftRow _rowFromTemplate(
    _TaskTemplateRow row, {
    int minuteOffset = 0,
  }) {
    final startTime = _shiftTime(row.startTime, minuteOffset);
    final endTime = _shiftTime(row.endTime, minuteOffset);
    return _ScheduleDraftRow(
      id: 'row_${_rowSequence++}',
      startTime: startTime,
      endTime: _minutesOfDay(endTime) > _minutesOfDay(startTime)
          ? endTime
          : _addMinutes(startTime, _durationForType(row.taskType)),
      taskType: row.taskType,
      title: row.title,
      rewardPoints: row.rewardPoints,
      requiresParentConfirmation: row.requiresParentConfirmation,
    );
  }

  void _addScheduleRow() {
    final sorted = _rows.toList()
      ..sort(
        (a, b) =>
            _minutesOfDay(a.startTime).compareTo(_minutesOfDay(b.startTime)),
      );
    final last = sorted.isEmpty ? null : sorted.last;
    final nextStart = last == null
        ? _suggestedStartTimeForDate(_date)
        : _suggestedStartAfterBoundary(_date, last.endTime);
    setState(() {
      _rows = [
        ..._rows,
        _newScheduleRow(
          startTime: nextStart,
          taskType:
              last?.taskType ?? _recommendedTaskType(widget.childAgeGroup),
        ),
      ];
      _error = null;
    });
    _scrollSheetToBottom();
  }

  void _scrollSheetToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_sheetScrollController.hasClients) return;
      _sheetScrollController.animateTo(
        _sheetScrollController.position.maxScrollExtent,
        duration: AppMotion.duration(context, 260),
        curve: Curves.easeOutCubic,
      );
      Future<void>.delayed(const Duration(milliseconds: 120), () {
        if (!mounted || !_sheetScrollController.hasClients) return;
        _sheetScrollController.animateTo(
          _sheetScrollController.position.maxScrollExtent,
          duration: AppMotion.duration(context, 180),
          curve: Curves.easeOutCubic,
        );
      });
    });
  }

  void _deleteRow(_ScheduleDraftRow row) {
    if (_rows.length <= 1) return;
    setState(() {
      _rows = _rows.where((item) => item.id != row.id).toList();
      _error = null;
    });
  }

  void _updateRow(_ScheduleDraftRow source, _ScheduleDraftRow next) {
    setState(() {
      _rows = _rows.map((row) => row.id == source.id ? next : row).toList();
      _error = null;
    });
  }

  String _suggestedStartTimeForDate(DateTime date) {
    final latestEnd = _latestExistingEndTimeForDate(date);
    if (latestEnd != null) {
      return _suggestedStartAfterBoundary(date, latestEnd);
    }
    final minTime = _minimumStartTimeForDate(date);
    if (minTime != null) return _suggestedStartAfterBoundary(date, minTime);
    return '19:00';
  }

  String _suggestedStartAfterBoundary(DateTime date, String boundaryTime) {
    final minMinutes = _minimumStartMinutesForDate(date);
    final boundaryMinutes = _minutesOfDay(boundaryTime);
    final baseMinutes = minMinutes == null
        ? boundaryMinutes
        : (boundaryMinutes < minMinutes ? minMinutes : boundaryMinutes);
    return _minuteText(
      (baseMinutes + _taskStartPreparationMinutes)
          .clamp(0, 23 * 60 + 59)
          .toInt(),
    );
  }

  List<_ScheduleDraftRow> _normalizedRowsForSelectedDate() {
    final minMinutes = _minimumStartMinutesForDate(_date);
    if (minMinutes == null) {
      return _rows.map((row) => row.copyWith(clearError: true)).toList();
    }
    final sorted = _rows.toList()
      ..sort(
        (a, b) =>
            _minutesOfDay(a.startTime).compareTo(_minutesOfDay(b.startTime)),
      );
    var cursor = minMinutes;
    final normalizedById = <String, _ScheduleDraftRow>{};
    for (final row in sorted) {
      final startMinutes = _minutesOfDay(row.startTime);
      final endMinutes = _minutesOfDay(row.endTime);
      final duration = (endMinutes - startMinutes).clamp(1, 23 * 60 + 59);
      final nextStart = startMinutes < cursor ? cursor : startMinutes;
      final nextEnd = (nextStart + duration).clamp(0, 23 * 60 + 59).toInt();
      normalizedById[row.id] = row.copyWith(
        startTime: _minuteText(nextStart),
        endTime: _minuteText(nextEnd <= nextStart ? nextStart : nextEnd),
        clearError: true,
      );
      cursor = nextEnd;
    }
    return _rows.map((row) => normalizedById[row.id] ?? row).toList();
  }

  String? _latestExistingEndTimeForDate(DateTime date) {
    final selectedDate = _dateText(date);
    final times =
        widget.existingTasks
            .where(
              (task) =>
                  task.scheduledDate == selectedDate &&
                  task.id != widget.task?.id &&
                  task.status != GuardianTaskStatus.cancelled &&
                  task.scheduledEnd.isNotEmpty,
            )
            .map((task) => task.scheduledEnd)
            .toList()
          ..sort((a, b) => _minutesOfDay(a).compareTo(_minutesOfDay(b)));
    return times.isEmpty ? null : times.last;
  }

  int? _minimumStartMinutesForDate(DateTime date) {
    final now = DateTime.now();
    if (!_sameDay(date, now)) return null;
    return _currentSelectableMinute(now);
  }

  String? _minimumStartTimeForDate(DateTime date) {
    final minutes = _minimumStartMinutesForDate(date);
    return minutes == null ? null : _minuteText(minutes);
  }

  bool _startsBeforeAllowedDate(String time, DateTime date) {
    final minMinutes = _minimumStartMinutesForDate(date);
    return minMinutes != null && _minutesOfDay(time) < minMinutes;
  }

  _ScheduleDraftRow _newScheduleRow({
    required String taskType,
    required String startTime,
    String title = '',
  }) {
    final config = _taskConfig(taskType);
    return _ScheduleDraftRow(
      id: 'row_${_rowSequence++}',
      startTime: startTime,
      endTime: _addMinutes(startTime, config.defaultMinutes),
      taskType: taskType,
      title: title,
      rewardPoints: config.defaultReward,
      requiresParentConfirmation: config.defaultRequiresConfirmation,
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 13,
        fontWeight: FontWeight.w900,
        letterSpacing: 0,
      ),
    );
  }
}

class _PickerSheetScaffold extends StatelessWidget {
  const _PickerSheetScaffold({
    required this.title,
    required this.child,
    this.subtitle,
  });

  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(title: title, subtitle: subtitle, child: child);
  }
}

class _AppTimePickerSheet extends StatefulWidget {
  const _AppTimePickerSheet({
    required this.initialValue,
    required this.minMinutes,
    required this.maxMinutes,
    required this.invalidMessage,
  });

  final String initialValue;
  final int minMinutes;
  final int maxMinutes;
  final String invalidMessage;

  @override
  State<_AppTimePickerSheet> createState() => _AppTimePickerSheetState();
}

class _AppTimePickerSheetState extends State<_AppTimePickerSheet> {
  late final FixedExtentScrollController _hourController;
  late final FixedExtentScrollController _minuteController;
  late int _hour;
  late int _minute;
  late final int _minMinutes;
  late final int _maxMinutes;

  @override
  void initState() {
    super.initState();
    _minMinutes = widget.minMinutes.clamp(0, 23 * 60 + 59).toInt();
    _maxMinutes = widget.maxMinutes.clamp(_minMinutes, 23 * 60 + 59).toInt();
    final initial = _timeOfDay(
      _minuteText(
        _minutesOfDay(
          widget.initialValue,
        ).clamp(_minMinutes, _maxMinutes).toInt(),
      ),
    );
    _hour = initial.hour;
    _minute = initial.minute;
    _hourController = FixedExtentScrollController(initialItem: _hour);
    _minuteController = FixedExtentScrollController(initialItem: _minute);
  }

  @override
  void dispose() {
    _hourController.dispose();
    _minuteController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selectedMinutes = _hour * 60 + _minute;
    final valid =
        selectedMinutes >= _minMinutes && selectedMinutes <= _maxMinutes;
    final rangeLabel = _minMinutes == 0 && _maxMinutes == 23 * 60 + 59
        ? null
        : '可选择 ${_minuteText(_minMinutes)} - ${_minuteText(_maxMinutes)}';
    return AppBottomSheetBody(
      title: '选择时间',
      subtitle: rangeLabel,
      scrollable: false,
      footer: Row(
        children: [
          Expanded(
            child: AppSecondaryButton(
              label: '取消',
              onTap: () => Navigator.of(context).pop(),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: AppPrimaryButton(
              label: '确定',
              trailing: const AppButtonGlyph(icon: Icons.check),
              onTap: valid
                  ? () {
                      Navigator.of(
                        context,
                      ).pop(_timeText(TimeOfDay(hour: _hour, minute: _minute)));
                    }
                  : null,
            ),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AppSurface(
            radius: 20,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            color: AppColors.surfaceSoft,
            borderColor: AppColors.borderSoft,
            child: SizedBox(
              height: 174,
              child: Row(
                children: [
                  Expanded(
                    child: _TimeWheel(
                      controller: _hourController,
                      values: List.generate(24, (index) => index),
                      suffix: '时',
                      onChanged: (value) => setState(() => _hour = value),
                    ),
                  ),
                  Container(
                    width: 1,
                    height: 116,
                    color: AppColors.muted.withValues(alpha: 0.12),
                  ),
                  Expanded(
                    child: _TimeWheel(
                      controller: _minuteController,
                      values: List.generate(60, (index) => index),
                      suffix: '分',
                      onChanged: (value) => setState(() => _minute = value),
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (!valid) ...[
            const SizedBox(height: 9),
            Text(
              widget.invalidMessage,
              style: const TextStyle(
                color: AppColors.danger,
                fontFamily: AppTypography.systemFont,
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 0,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TimeWheel extends StatelessWidget {
  const _TimeWheel({
    required this.controller,
    required this.values,
    required this.suffix,
    required this.onChanged,
  });

  final FixedExtentScrollController controller;
  final List<int> values;
  final String suffix;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return CupertinoPicker(
      scrollController: controller,
      itemExtent: 42,
      diameterRatio: 1.12,
      squeeze: 1.04,
      selectionOverlay: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.primary.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(14),
        ),
      ),
      onSelectedItemChanged: (index) => onChanged(values[index]),
      children: [
        for (final value in values)
          Center(
            child: Text(
              '${value.toString().padLeft(2, '0')} $suffix',
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 19,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ),
      ],
    );
  }
}

class _TaskModeSwitch extends StatelessWidget {
  const _TaskModeSwitch({required this.value, required this.onChanged});

  final TaskEntryMode value;
  final ValueChanged<TaskEntryMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(AppRadii.button),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.all(4),
        child: Row(
          children: [
            for (final mode in TaskEntryMode.values)
              Expanded(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => onChanged(mode),
                  child: AnimatedContainer(
                    duration: AppMotion.duration(context, 160),
                    curve: Curves.easeOutCubic,
                    padding: const EdgeInsets.symmetric(vertical: 9),
                    decoration: BoxDecoration(
                      color: value == mode
                          ? AppColors.selectedBg
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(AppRadii.control),
                    ),
                    child: Text(
                      mode.label,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: value == mode
                            ? AppColors.primary
                            : AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PickerField extends StatelessWidget {
  const _PickerField({
    required this.label,
    required this.supportingText,
    required this.icon,
    required this.onTap,
  });

  final String label;
  final String supportingText;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: AppSurface(
        radius: AppRadii.input,
        padding: const EdgeInsets.fromLTRB(13, 11, 12, 11),
        color: AppColors.surfaceSoft,
        borderColor: AppColors.borderSoft,
        child: Row(
          children: [
            Icon(icon, color: AppColors.primary, size: 18),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      letterSpacing: 0,
                    ),
                  ),
                  if (supportingText.isNotEmpty) ...[
                    const SizedBox(height: 3),
                    Text(
                      supportingText,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: AppColors.muted, size: 18),
          ],
        ),
      ),
    );
  }
}

class _CompactActionButton extends StatelessWidget {
  const _CompactActionButton({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.surfaceSoft,
          borderRadius: BorderRadius.circular(AppRadii.input),
          border: Border.all(color: AppColors.borderSoft),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: AppControls.compactButtonHeight,
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, color: AppColors.primary, size: 18),
                const SizedBox(width: 7),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
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

class _ScheduleRowCard extends StatelessWidget {
  const _ScheduleRowCard({
    required this.index,
    required this.row,
    required this.canDelete,
    required this.onPickStart,
    required this.onPickEnd,
    required this.onPickType,
    required this.onTitleChanged,
    required this.onRewardChanged,
    required this.onConfirmChanged,
    required this.onDelete,
  });

  final int index;
  final _ScheduleDraftRow row;
  final bool canDelete;
  final VoidCallback onPickStart;
  final VoidCallback onPickEnd;
  final VoidCallback onPickType;
  final ValueChanged<String> onTitleChanged;
  final ValueChanged<String> onRewardChanged;
  final ValueChanged<bool> onConfirmChanged;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final config = _taskConfig(row.taskType);
    return AppSurface(
      radius: 16,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 11),
      color: AppColors.surfaceSoft,
      borderColor: row.error == null
          ? AppColors.borderSoft
          : AppColors.danger.withValues(alpha: 0.26),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 68,
                child: Column(
                  children: [
                    _TimeBlockButton(value: row.startTime, onTap: onPickStart),
                    const SizedBox(height: 6),
                    Container(
                      width: 2,
                      height: 12,
                      decoration: BoxDecoration(
                        color: AppColors.muted.withValues(alpha: 0.18),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    const SizedBox(height: 6),
                    _TimeBlockButton(value: row.endTime, onTap: onPickEnd),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTap: onPickType,
                            child: Row(
                              children: [
                                Icon(
                                  config.icon,
                                  size: 17,
                                  color: AppColors.primary,
                                ),
                                const SizedBox(width: 6),
                                Flexible(
                                  child: Text(
                                    config.label,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                      color: AppColors.ink,
                                      fontFamily: AppTypography.systemFont,
                                      fontSize: 13,
                                      fontWeight: FontWeight.w600,
                                      letterSpacing: 0,
                                    ),
                                  ),
                                ),
                                const Icon(
                                  Icons.keyboard_arrow_down,
                                  color: AppColors.muted,
                                  size: 17,
                                ),
                              ],
                            ),
                          ),
                        ),
                        if (canDelete)
                          IconButton(
                            visualDensity: VisualDensity.compact,
                            icon: const Icon(Icons.close, size: 18),
                            color: AppColors.muted,
                            onPressed: onDelete,
                          ),
                      ],
                    ),
                    const SizedBox(height: 11),
                    TextFormField(
                      key: ValueKey('title_${row.id}'),
                      initialValue: row.title,
                      onChanged: onTitleChanged,
                      textInputAction: TextInputAction.next,
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0,
                      ),
                      decoration: InputDecoration(
                        hintText: '任务名称',
                        hintStyle: const TextStyle(
                          color: AppColors.subtle,
                          fontWeight: FontWeight.w500,
                        ),
                        isDense: true,
                        filled: true,
                        fillColor: AppColors.appBackgroundMid.withValues(
                          alpha: 0.42,
                        ),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 11,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: AppColors.borderSubtle,
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: AppColors.borderSubtle,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(
                            color: AppColors.focusRing,
                            width: 1.0,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        SizedBox(
                          width: 74,
                          child: TextFormField(
                            key: ValueKey('reward_${row.id}'),
                            initialValue: '${row.rewardPoints}',
                            onChanged: onRewardChanged,
                            keyboardType: TextInputType.number,
                            inputFormatters: [
                              FilteringTextInputFormatter.digitsOnly,
                            ],
                            style: const TextStyle(
                              color: AppColors.ink,
                              fontFamily: AppTypography.systemFont,
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                            decoration: InputDecoration(
                              prefixText: '+',
                              suffixText: '分',
                              isDense: true,
                              filled: true,
                              fillColor: AppColors.appBackgroundMid.withValues(
                                alpha: 0.42,
                              ),
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 10,
                              ),
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(
                                  color: AppColors.borderSubtle,
                                ),
                              ),
                              enabledBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(
                                  color: AppColors.borderSubtle,
                                ),
                              ),
                              focusedBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(
                                  color: AppColors.focusRing,
                                  width: 1.0,
                                ),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.end,
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              const Flexible(
                                child: Text(
                                  '家长确认',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    color: AppColors.muted,
                                    fontFamily: AppTypography.systemFont,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 0,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 6),
                              AppCompactToggle(
                                value: row.requiresParentConfirmation,
                                onChanged: onConfirmChanged,
                                label: '家长确认',
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (row.error != null) ...[
            const SizedBox(height: 8),
            Text(
              row.error!,
              style: const TextStyle(
                color: AppColors.danger,
                fontFamily: AppTypography.systemFont,
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 0,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TimeBlockButton extends StatelessWidget {
  const _TimeBlockButton({required this.value, required this.onTap});

  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.appBackgroundMid.withValues(alpha: 0.62),
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: AppColors.borderSoft),
        ),
        child: SizedBox(
          width: 68,
          height: 36,
          child: Center(
            child: Text(
              value,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PickerListTile extends StatelessWidget {
  const _PickerListTile({
    required this.icon,
    required this.title,
    required this.message,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String message;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: AppSurface(
          radius: AppRadii.input,
          padding: const EdgeInsets.fromLTRB(14, 12, 13, 12),
          color: selected ? AppColors.selectedBg : AppColors.surfaceSoft,
          borderColor: selected
              ? AppColors.primary.withValues(alpha: 0.16)
              : AppColors.borderSoft,
          child: Row(
            children: [
              Icon(
                icon,
                color: selected ? AppColors.primary : AppColors.muted,
                size: 19,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      message,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        height: 1.35,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              if (selected)
                const Icon(
                  Icons.check_circle,
                  color: AppColors.primary,
                  size: 19,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TemplateSection extends StatelessWidget {
  const _TemplateSection({
    required this.title,
    required this.templates,
    required this.onSelect,
  });

  final String title;
  final List<_TaskTemplate> templates;
  final ValueChanged<_TaskTemplate> onSelect;

  @override
  Widget build(BuildContext context) {
    if (templates.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _FieldLabel(title),
        const SizedBox(height: 8),
        for (final template in templates)
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => onSelect(template),
            child: Padding(
              padding: const EdgeInsets.only(bottom: 9),
              child: AppSurface(
                radius: 18,
                padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
                color: Colors.white.withValues(alpha: 0.66),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            template.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: AppColors.ink,
                              fontFamily: AppTypography.systemFont,
                              fontSize: 15,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0,
                            ),
                          ),
                        ),
                        Text(
                          '${template.rows.length} 项',
                          style: const TextStyle(
                            color: AppColors.muted,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      template.subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        height: 1.4,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _SingleTaskActions extends StatelessWidget {
  const _SingleTaskActions({
    required this.editing,
    required this.saving,
    required this.savingContinue,
    required this.onSave,
    required this.onSaveAndContinue,
  });

  final bool editing;
  final bool saving;
  final bool savingContinue;
  final VoidCallback? onSave;
  final VoidCallback? onSaveAndContinue;

  @override
  Widget build(BuildContext context) {
    if (editing) {
      return AppPrimaryButton(
        label: saving ? '保存中' : '保存',
        loading: saving,
        trailing: const AppButtonGlyph(icon: Icons.check),
        onTap: onSave,
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final vertical = constraints.maxWidth < 360;
        final secondary = AppSecondaryButton(
          label: savingContinue ? '保存中' : '保存并继续添加',
          onTap: onSaveAndContinue,
        );
        final primary = AppPrimaryButton(
          label: saving && !savingContinue ? '保存中' : '保存',
          loading: saving && !savingContinue,
          trailing: const AppButtonGlyph(icon: Icons.check),
          onTap: onSave,
        );
        if (vertical) {
          return Column(
            children: [secondary, const SizedBox(height: 10), primary],
          );
        }
        return Row(
          children: [
            Expanded(child: secondary),
            const SizedBox(width: 10),
            Expanded(child: primary),
          ],
        );
      },
    );
  }
}

class _TaskTextField extends StatelessWidget {
  const _TaskTextField({
    required this.controller,
    required this.hintText,
    this.keyboardType,
    this.inputFormatters,
    this.minLines = 1,
    this.maxLines = 1,
  });

  final TextEditingController controller;
  final String hintText;
  final TextInputType? keyboardType;
  final List<TextInputFormatter>? inputFormatters;
  final int minLines;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      inputFormatters: inputFormatters,
      minLines: minLines,
      maxLines: maxLines,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 15,
        fontWeight: FontWeight.w600,
      ),
      decoration: InputDecoration(
        hintText: hintText,
        hintStyle: const TextStyle(
          color: AppColors.subtle,
          fontWeight: FontWeight.w500,
        ),
        filled: true,
        fillColor: AppColors.surfaceSoft,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 15,
          vertical: 14,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.input),
          borderSide: const BorderSide(color: AppColors.borderSoft),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.input),
          borderSide: const BorderSide(color: AppColors.borderSoft),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadii.input),
          borderSide: const BorderSide(color: AppColors.focus, width: 1.1),
        ),
      ),
    );
  }
}

class _ConfirmSwitch extends StatelessWidget {
  const _ConfirmSwitch({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: AppRadii.input,
      padding: const EdgeInsets.fromLTRB(14, 11, 12, 11),
      color: AppColors.surfaceSoft,
      borderColor: AppColors.borderSoft,
      child: Row(
        children: [
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '需要家长确认',
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                  ),
                ),
                SizedBox(height: 4),
                Text(
                  '确认后再发放积分，适合作业证据和奖励任务。',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    height: 1.35,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          AppCompactToggle(value: value, onChanged: onChanged, label: '需要家长确认'),
        ],
      ),
    );
  }
}

enum TaskEntryMode {
  single('单个任务'),
  day('一天安排');

  const TaskEntryMode(this.label);

  final String label;
}

enum TaskAgeGroup { preschool, lowerPrimary, upperPrimary, teen }

class _Option {
  const _Option(this.value, this.label, this.message);

  final String value;
  final String label;
  final String message;
}

const _scheduleOptions = [
  _Option('one_time', '不重复', '只在选中的日期执行一次'),
  _Option('daily', '每天', '适合习惯和睡前流程'),
  _Option('weekday', '工作日', '周一到周五自动安排'),
  _Option('weekly', '每周', '每周同一天重复提醒'),
];

class _TaskTypeConfig {
  const _TaskTypeConfig({
    required this.value,
    required this.label,
    required this.description,
    required this.icon,
    required this.defaultMinutes,
    required this.defaultReward,
    required this.defaultRequiresConfirmation,
    required this.titleLabel,
    required this.titleHint,
    required this.detailLabel,
    required this.detailHint,
    this.extraLabel,
    this.extraHint,
    this.ageGroups = _allAgeGroups,
  });

  final String value;
  final String label;
  final String description;
  final IconData icon;
  final int defaultMinutes;
  final int defaultReward;
  final bool defaultRequiresConfirmation;
  final String titleLabel;
  final String titleHint;
  final String detailLabel;
  final String detailHint;
  final String? extraLabel;
  final String? extraHint;
  final List<TaskAgeGroup> ageGroups;
}

const _allAgeGroups = [
  TaskAgeGroup.preschool,
  TaskAgeGroup.lowerPrimary,
  TaskAgeGroup.upperPrimary,
  TaskAgeGroup.teen,
];

const _taskTypeConfigs = [
  _TaskTypeConfig(
    value: 'learning',
    label: '学习任务',
    description: '作业、复习、预习和听读',
    icon: Icons.menu_book_outlined,
    defaultMinutes: 30,
    defaultReward: 3,
    defaultRequiresConfirmation: true,
    titleLabel: '任务内容',
    titleHint: '例如：完成数学练习册第 3 页',
    detailLabel: '备注',
    detailHint: '例如：专注完成，不追求速度',
    extraLabel: '科目',
    extraHint: '例如：数学',
    ageGroups: [
      TaskAgeGroup.lowerPrimary,
      TaskAgeGroup.upperPrimary,
      TaskAgeGroup.teen,
    ],
  ),
  _TaskTypeConfig(
    value: 'life',
    label: '生活习惯',
    description: '喝水、整理、洗漱和日常习惯',
    icon: Icons.water_drop_outlined,
    defaultMinutes: 15,
    defaultReward: 1,
    defaultRequiresConfirmation: false,
    titleLabel: '习惯名称',
    titleHint: '例如：喝水休息',
    detailLabel: '提醒',
    detailHint: '例如：温和提醒一次即可',
  ),
  _TaskTypeConfig(
    value: 'sleep',
    label: '睡前流程',
    description: '洗漱、整理、阅读和入睡节奏',
    icon: Icons.nights_stay_outlined,
    defaultMinutes: 20,
    defaultReward: 2,
    defaultRequiresConfirmation: false,
    titleLabel: '流程名称',
    titleHint: '例如：睡前洗漱',
    detailLabel: '步骤清单',
    detailHint: '例如：洗漱、整理书包、上床',
    ageGroups: [
      TaskAgeGroup.preschool,
      TaskAgeGroup.lowerPrimary,
      TaskAgeGroup.upperPrimary,
    ],
  ),
  _TaskTypeConfig(
    value: 'schoolbag',
    label: '小书包/物品准备',
    description: '课本、作业本、水杯和明日用品',
    icon: Icons.backpack_outlined,
    defaultMinutes: 10,
    defaultReward: 2,
    defaultRequiresConfirmation: true,
    titleLabel: '准备事项',
    titleHint: '例如：检查小书包',
    detailLabel: '物品清单',
    detailHint: '例如：课本、作业本、水杯',
    ageGroups: [
      TaskAgeGroup.preschool,
      TaskAgeGroup.lowerPrimary,
      TaskAgeGroup.upperPrimary,
    ],
  ),
  _TaskTypeConfig(
    value: 'housework',
    label: '家务任务',
    description: '整理桌面、收纳、简单家务',
    icon: Icons.cleaning_services_outlined,
    defaultMinutes: 20,
    defaultReward: 3,
    defaultRequiresConfirmation: true,
    titleLabel: '家务内容',
    titleHint: '例如：整理书桌',
    detailLabel: '完成标准',
    detailHint: '例如：桌面只保留今天要用的书本',
    ageGroups: [TaskAgeGroup.upperPrimary, TaskAgeGroup.teen],
  ),
  _TaskTypeConfig(
    value: 'reading_interest',
    label: '阅读/兴趣',
    description: '阅读、绘画、音乐或兴趣练习',
    icon: Icons.local_library_outlined,
    defaultMinutes: 20,
    defaultReward: 2,
    defaultRequiresConfirmation: false,
    titleLabel: '内容',
    titleHint: '例如：睡前阅读',
    detailLabel: '目标',
    detailHint: '例如：阅读 20 分钟，读完后简单聊一聊',
  ),
  _TaskTypeConfig(
    value: 'sports_outdoor',
    label: '运动/户外',
    description: '跳绳、散步、球类和户外活动',
    icon: Icons.directions_run_outlined,
    defaultMinutes: 30,
    defaultReward: 3,
    defaultRequiresConfirmation: false,
    titleLabel: '活动内容',
    titleHint: '例如：跳绳练习',
    detailLabel: '安全提醒',
    detailHint: '例如：运动前喝水，结束后整理物品',
  ),
  _TaskTypeConfig(
    value: 'custom',
    label: '家长自定义',
    description: '临时安排或孩子自己的计划',
    icon: Icons.edit_note_outlined,
    defaultMinutes: 20,
    defaultReward: 2,
    defaultRequiresConfirmation: true,
    titleLabel: '名称',
    titleHint: '例如：整理明天要带的资料',
    detailLabel: '备注',
    detailHint: '写下要注意的地方',
  ),
];

class _ScheduleDraftRow {
  const _ScheduleDraftRow({
    required this.id,
    required this.startTime,
    required this.endTime,
    required this.taskType,
    required this.title,
    required this.rewardPoints,
    required this.requiresParentConfirmation,
    this.error,
  });

  final String id;
  final String startTime;
  final String endTime;
  final String taskType;
  final String title;
  final int rewardPoints;
  final bool requiresParentConfirmation;
  final String? error;

  _ScheduleDraftRow copyWith({
    String? startTime,
    String? endTime,
    String? taskType,
    String? title,
    int? rewardPoints,
    bool? requiresParentConfirmation,
    String? error,
    bool clearError = false,
  }) {
    return _ScheduleDraftRow(
      id: id,
      startTime: startTime ?? this.startTime,
      endTime: endTime ?? this.endTime,
      taskType: taskType ?? this.taskType,
      title: title ?? this.title,
      rewardPoints: rewardPoints ?? this.rewardPoints,
      requiresParentConfirmation:
          requiresParentConfirmation ?? this.requiresParentConfirmation,
      error: clearError ? null : error ?? this.error,
    );
  }
}

class _TaskTemplate {
  const _TaskTemplate({
    required this.title,
    required this.subtitle,
    required this.rows,
    required this.ageGroups,
    this.scheduleType = 'one_time',
  });

  final String title;
  final String subtitle;
  final List<_TaskTemplateRow> rows;
  final List<TaskAgeGroup> ageGroups;
  final String scheduleType;
}

class _TaskTemplateRow {
  const _TaskTemplateRow({
    required this.startTime,
    required this.endTime,
    required this.taskType,
    required this.title,
    required this.rewardPoints,
    required this.requiresParentConfirmation,
  });

  final String startTime;
  final String endTime;
  final String taskType;
  final String title;
  final int rewardPoints;
  final bool requiresParentConfirmation;
}

const _taskTemplates = [
  _TaskTemplate(
    title: '放学后学习',
    subtitle: '适合小学阶段的作业、休息和阅读节奏',
    ageGroups: [TaskAgeGroup.lowerPrimary, TaskAgeGroup.upperPrimary],
    rows: [
      _TaskTemplateRow(
        startTime: '19:00',
        endTime: '19:40',
        taskType: 'learning',
        title: '数学作业',
        rewardPoints: 3,
        requiresParentConfirmation: true,
      ),
      _TaskTemplateRow(
        startTime: '19:40',
        endTime: '19:55',
        taskType: 'life',
        title: '休息',
        rewardPoints: 1,
        requiresParentConfirmation: false,
      ),
      _TaskTemplateRow(
        startTime: '20:00',
        endTime: '20:20',
        taskType: 'reading_interest',
        title: '阅读',
        rewardPoints: 2,
        requiresParentConfirmation: false,
      ),
    ],
  ),
  _TaskTemplate(
    title: '睡前流程',
    subtitle: '洗漱、整理和睡前阅读，帮助晚上收束下来',
    scheduleType: 'daily',
    ageGroups: [
      TaskAgeGroup.preschool,
      TaskAgeGroup.lowerPrimary,
      TaskAgeGroup.upperPrimary,
    ],
    rows: [
      _TaskTemplateRow(
        startTime: '20:30',
        endTime: '20:45',
        taskType: 'sleep',
        title: '洗漱',
        rewardPoints: 1,
        requiresParentConfirmation: false,
      ),
      _TaskTemplateRow(
        startTime: '20:45',
        endTime: '21:00',
        taskType: 'schoolbag',
        title: '整理书包',
        rewardPoints: 2,
        requiresParentConfirmation: true,
      ),
      _TaskTemplateRow(
        startTime: '21:00',
        endTime: '21:20',
        taskType: 'reading_interest',
        title: '睡前阅读',
        rewardPoints: 2,
        requiresParentConfirmation: false,
      ),
    ],
  ),
  _TaskTemplate(
    title: '小书包检查',
    subtitle: '把明天上学要带的物品逐项确认',
    ageGroups: [
      TaskAgeGroup.preschool,
      TaskAgeGroup.lowerPrimary,
      TaskAgeGroup.upperPrimary,
    ],
    rows: [
      _TaskTemplateRow(
        startTime: '20:00',
        endTime: '20:10',
        taskType: 'schoolbag',
        title: '检查课本',
        rewardPoints: 1,
        requiresParentConfirmation: true,
      ),
      _TaskTemplateRow(
        startTime: '20:10',
        endTime: '20:20',
        taskType: 'schoolbag',
        title: '检查作业本',
        rewardPoints: 1,
        requiresParentConfirmation: true,
      ),
      _TaskTemplateRow(
        startTime: '20:20',
        endTime: '20:30',
        taskType: 'schoolbag',
        title: '检查水杯和红领巾',
        rewardPoints: 1,
        requiresParentConfirmation: true,
      ),
    ],
  ),
  _TaskTemplate(
    title: '周末上午',
    subtitle: '阅读、户外和一个轻家务任务',
    ageGroups: [
      TaskAgeGroup.lowerPrimary,
      TaskAgeGroup.upperPrimary,
      TaskAgeGroup.teen,
    ],
    rows: [
      _TaskTemplateRow(
        startTime: '09:30',
        endTime: '10:00',
        taskType: 'reading_interest',
        title: '阅读',
        rewardPoints: 2,
        requiresParentConfirmation: false,
      ),
      _TaskTemplateRow(
        startTime: '10:10',
        endTime: '10:40',
        taskType: 'sports_outdoor',
        title: '户外运动',
        rewardPoints: 3,
        requiresParentConfirmation: false,
      ),
      _TaskTemplateRow(
        startTime: '10:50',
        endTime: '11:10',
        taskType: 'housework',
        title: '家务小任务',
        rewardPoints: 3,
        requiresParentConfirmation: true,
      ),
    ],
  ),
  _TaskTemplate(
    title: '自主安排',
    subtitle: '适合高年级和更大孩子自己确认晚间节奏',
    ageGroups: [TaskAgeGroup.upperPrimary, TaskAgeGroup.teen],
    rows: [
      _TaskTemplateRow(
        startTime: '19:30',
        endTime: '20:00',
        taskType: 'learning',
        title: '自主学习',
        rewardPoints: 3,
        requiresParentConfirmation: true,
      ),
      _TaskTemplateRow(
        startTime: '20:10',
        endTime: '20:30',
        taskType: 'custom',
        title: '明日准备',
        rewardPoints: 2,
        requiresParentConfirmation: true,
      ),
    ],
  ),
];

Object? _repeatRulePayload(String scheduleType) {
  return switch (scheduleType) {
    'daily' => {'freq': 'daily'},
    'weekly' => {'freq': 'weekly'},
    'weekday' => {
      'freq': 'weekly',
      'days': [1, 2, 3, 4, 5],
    },
    _ => null,
  };
}

_TaskTypeConfig _taskConfig(String value) {
  return _taskTypeConfigs.firstWhere(
    (config) => config.value == value,
    orElse: () => _taskTypeConfigs.last,
  );
}

List<_TaskTypeConfig> _taskTypeConfigsForAge(TaskAgeGroup ageGroup) {
  final recommended = _taskTypeConfigs
      .where((config) => config.ageGroups.contains(ageGroup))
      .toList();
  final rest = _taskTypeConfigs
      .where((config) => !config.ageGroups.contains(ageGroup))
      .toList();
  return [...recommended, ...rest];
}

String _recommendedTaskType(TaskAgeGroup ageGroup) {
  return switch (ageGroup) {
    TaskAgeGroup.preschool => 'life',
    TaskAgeGroup.lowerPrimary => 'learning',
    TaskAgeGroup.upperPrimary => 'learning',
    TaskAgeGroup.teen => 'custom',
  };
}

List<_TaskTemplate> _templatesForAge(TaskAgeGroup ageGroup) {
  final matches = _taskTemplates
      .where((template) => template.ageGroups.contains(ageGroup))
      .toList();
  if (matches.isEmpty) return _taskTemplates.take(3).toList();
  return matches.take(3).toList();
}

TaskAgeGroup taskAgeGroupForChild({
  required String stage,
  required String grade,
}) {
  final text = '$stage $grade';
  if (text.contains('幼') || text.contains('学前')) {
    return TaskAgeGroup.preschool;
  }
  if (text.contains('五') || text.contains('六') || text.contains('高年级')) {
    return TaskAgeGroup.upperPrimary;
  }
  if (text.contains('初') ||
      text.contains('中学') ||
      text.contains('更大') ||
      text.contains('青少年')) {
    return TaskAgeGroup.teen;
  }
  return TaskAgeGroup.lowerPrimary;
}

String _scheduleLabel(String value) {
  return _scheduleOptions
      .firstWhere(
        (option) => option.value == value,
        orElse: () => _scheduleOptions.first,
      )
      .label;
}

int _durationForType(String taskType) => _taskConfig(taskType).defaultMinutes;

class _TaskDescriptionFields {
  const _TaskDescriptionFields({required this.extra, required this.detail});

  final String extra;
  final String detail;
}

_TaskDescriptionFields _splitTaskDescription(
  String description,
  _TaskTypeConfig config,
) {
  final text = description.trim();
  if (text.isEmpty || config.extraLabel == null) {
    return _TaskDescriptionFields(extra: '', detail: text);
  }
  final parts = text.split(' · ');
  if (parts.length >= 2) {
    return _TaskDescriptionFields(
      extra: parts.first.trim(),
      detail: parts.skip(1).join(' · ').trim(),
    );
  }
  return _TaskDescriptionFields(extra: text, detail: '');
}

String _combinedDescription(String extra, String detail) {
  final parts = [
    extra,
    detail,
  ].where((part) => part.trim().isNotEmpty).toList();
  return parts.join(' · ');
}

int _minutesOfDay(String time) {
  final parts = time.split(':');
  final hour = parts.isNotEmpty ? int.tryParse(parts[0]) ?? 0 : 0;
  final minute = parts.length > 1 ? int.tryParse(parts[1]) ?? 0 : 0;
  return hour * 60 + minute;
}

String _addMinutes(String time, int minutes) {
  final next = (_minutesOfDay(time) + minutes).clamp(0, 23 * 60 + 59).toInt();
  final hour = (next ~/ 60).toString().padLeft(2, '0');
  final minute = (next % 60).toString().padLeft(2, '0');
  return '$hour:$minute';
}

String _shiftTime(String time, int minutes) {
  return _minuteText(
    (_minutesOfDay(time) + minutes).clamp(0, 23 * 60 + 59).toInt(),
  );
}

int _currentSelectableMinute(DateTime now) {
  final extraMinute =
      now.second > 0 || now.millisecond > 0 || now.microsecond > 0 ? 1 : 0;
  return (now.hour * 60 + now.minute + extraMinute)
      .clamp(0, 23 * 60 + 59)
      .toInt();
}

TimeOfDay _timeOfDay(String time) {
  final parts = time.split(':');
  return TimeOfDay(
    hour: parts.isNotEmpty ? int.tryParse(parts[0]) ?? 19 : 19,
    minute: parts.length > 1 ? int.tryParse(parts[1]) ?? 0 : 0,
  );
}

String _timeText(TimeOfDay time) {
  final hour = time.hour.toString().padLeft(2, '0');
  final minute = time.minute.toString().padLeft(2, '0');
  return '$hour:$minute';
}

String _minuteText(int minutes) {
  final safeMinutes = minutes.clamp(0, 23 * 60 + 59).toInt();
  final hour = (safeMinutes ~/ 60).toString().padLeft(2, '0');
  final minute = (safeMinutes % 60).toString().padLeft(2, '0');
  return '$hour:$minute';
}

int _sortByStartTime(GuardianTask a, GuardianTask b) {
  final time = a.scheduledStart.compareTo(b.scheduledStart);
  if (time != 0) return time;
  return a.createdAt.compareTo(b.createdAt);
}

int _countForDate(List<GuardianTask> tasks, DateTime date) {
  final dateText = _dateText(date);
  return tasks.where((task) => task.scheduledDate == dateText).length;
}

IconData _iconForTask(GuardianTask task) {
  return switch (task.type) {
    'learning' => Icons.menu_book_outlined,
    'sleep' => Icons.nights_stay_outlined,
    'life' => Icons.water_drop_outlined,
    'schoolbag' => Icons.backpack_outlined,
    'housework' => Icons.cleaning_services_outlined,
    'reading_interest' => Icons.local_library_outlined,
    'sports_outdoor' => Icons.directions_run_outlined,
    'custom' => Icons.edit_note_outlined,
    _ => Icons.task_alt_outlined,
  };
}

Color _toneColor(GuardianTask task) {
  return switch (task.status) {
    GuardianTaskStatus.inProgress => AppColors.primary,
    GuardianTaskStatus.completed ||
    GuardianTaskStatus.confirmed => const Color(0xFF2F8F68),
    GuardianTaskStatus.awaitingParentConfirmation ||
    GuardianTaskStatus.delayed => const Color(0xFFD8922B),
    GuardianTaskStatus.rejected ||
    GuardianTaskStatus.missed ||
    GuardianTaskStatus.expired => AppColors.danger,
    _ => AppColors.muted,
  };
}

DateTime _dayOnly(DateTime date) => DateTime(date.year, date.month, date.day);

DateTime _startOfWeek(DateTime date) {
  final day = _dayOnly(date);
  return day.subtract(Duration(days: day.weekday - 1));
}

bool _sameDay(DateTime a, DateTime b) {
  return a.year == b.year && a.month == b.month && a.day == b.day;
}

bool _isSameWeek(DateTime a, DateTime b) {
  return _sameDay(_startOfWeek(a), _startOfWeek(b));
}

String _dateText(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

DateTime? _parseDate(String value) {
  final parsed = DateTime.tryParse(value);
  return parsed == null ? null : _dayOnly(parsed);
}

String _dateShort(DateTime date) => '${date.month}月${date.day}日';

String _weekdayShort(DateTime date) {
  return const ['一', '二', '三', '四', '五', '六', '日'][date.weekday - 1];
}

String _dateChoiceLabel(DateTime date) {
  final today = _dayOnly(DateTime.now());
  if (_sameDay(date, today)) return '今天';
  if (_sameDay(date, today.add(const Duration(days: 1)))) return '明天';
  return '${_weekdayShort(date)} ${date.month}/${date.day}';
}

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
