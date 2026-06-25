import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/app/router/app_router.dart';
import 'package:guardian_parent_app/src/core/theme/app_system_ui.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_realtime_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';

class AppShell extends ConsumerWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen<AsyncValue<TaskRealtimeEvent>>(taskRealtimeProvider, (
      previous,
      next,
    ) {
      final event = next.asData?.value;
      if (event == null) return;
      _handleRealtimeEvent(ref, event);
    });

    final location = GoRouterState.of(context).uri.path;
    final selectedRoute = routeFromLocation(location);
    final canAddTask =
        ref.watch(profileSummaryProvider).asData?.value.can('manage_tasks') ??
        false;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.appBackground,
        extendBody: true,
        body: Stack(
          children: [
            Positioned.fill(child: child),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _AppBottomNavigation(
                selectedRoute: selectedRoute,
                onSelected: (route) => context.go(route.path),
                canAddTask: canAddTask,
                onAddTask: () => _openTaskSheet(context, ref),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openTaskSheet(BuildContext context, WidgetRef ref) async {
    final canAddTask =
        ref.read(profileSummaryProvider).asData?.value.can('manage_tasks') ??
        false;
    if (!canAddTask) {
      _showShellToast(context, '当前身份不能新增安排');
      return;
    }
    String? childId;
    var childAgeGroup = TaskAgeGroup.preschool;
    try {
      final summary = await ref.read(profileSummaryProvider.future);
      final child = summary.child;
      if (child != null) {
        childId = child.id.isNotEmpty ? child.id : null;
        childAgeGroup = taskAgeGroupForChild(
          stage: child.educationStage.isNotEmpty
              ? child.educationStage
              : child.ageStage,
          grade: child.grade,
        );
      }
    } catch (_) {
      childId = null;
    }
    try {
      childId ??= (await ref.read(
        pointsSummaryProvider.future,
      )).account.childId;
    } catch (_) {}
    if (childId == null || childId.isEmpty) {
      try {
        final tasks = await ref.read(taskListProvider.future);
        if (tasks.isEmpty) {
          childId = null;
        } else {
          childId = tasks.first.childId;
        }
      } catch (_) {
        childId = null;
      }
    }
    if (!context.mounted) return;
    if (childId == null || childId.isEmpty) {
      final tasks = ref.read(taskListProvider).asData?.value;
      if (tasks != null && tasks.isNotEmpty) {
        childId = tasks.first.childId;
      }
    }
    if (childId == null || childId.isEmpty) {
      _showShellToast(context, '请先完成孩子资料，再添加生活提醒。');
      return;
    }
    final resolvedChildId = childId;
    final selectedDate = ref.read(taskSelectedDateProvider);
    final selectedWeekStart = _startOfWeek(selectedDate);
    final selectedWeekQuery = TaskWeekQuery(
      startDate: selectedWeekStart,
      endDate: selectedWeekStart.add(const Duration(days: 6)),
      childId: resolvedChildId,
    );
    var existingTasks = ref
        .read(taskWeekProvider(selectedWeekQuery))
        .asData
        ?.value;
    if (existingTasks == null) {
      try {
        existingTasks = await ref.read(
          taskWeekProvider(selectedWeekQuery).future,
        );
      } catch (_) {
        existingTasks = const [];
      }
    }
    if (!context.mounted) return;

    final savedDate = await showTaskFormSheet(
      context,
      childId: resolvedChildId,
      initialDate: selectedDate,
      childAgeGroup: childAgeGroup,
      onSavedProgress: () =>
          _invalidateTaskLists(ref, resolvedChildId, selectedDate),
      existingTasks: existingTasks ?? const [],
    );

    if (savedDate == null) return;
    ref.read(taskSelectedDateProvider.notifier).state = _dayOnly(savedDate);
    _invalidateTaskLists(ref, resolvedChildId, savedDate);
    if (context.mounted) {
      context.go(AppRoute.tasks.path);
      showAppStateSnackBar(
        context,
        variant: AppStateVariant.saved,
        title: '已保存',
        message: '任务已加入安排。',
      );
    }
  }

  void _invalidateTaskLists(WidgetRef ref, String childId, DateTime date) {
    ref
      ..invalidate(taskListProvider)
      ..invalidate(todayTasksProvider)
      ..invalidate(
        taskWeekProvider(
          TaskWeekQuery(
            startDate: _startOfWeek(date),
            endDate: _startOfWeek(date).add(const Duration(days: 6)),
            childId: childId,
          ),
        ),
      );
  }

  void _handleRealtimeEvent(WidgetRef ref, TaskRealtimeEvent event) {
    if (event.isTaskUpdate || event.isTaskStatusChanged) {
      _handleTaskRealtimeEvent(ref, event);
    }
    if (event.isCameraObservationUpdated) {
      _handleCameraObservationRealtimeEvent(ref);
    }
    if (event.isCameraEventCreated) {
      _handleCameraEventRealtimeEvent(ref);
    }
    if (event.isCameraStatusChanged) {
      _handleCameraStatusRealtimeEvent(ref);
    }
  }

  void _handleTaskRealtimeEvent(WidgetRef ref, TaskRealtimeEvent event) {
    ref
      ..invalidate(taskListProvider)
      ..invalidate(todayTasksProvider)
      ..invalidate(taskWeekProvider)
      ..invalidate(pointsSummaryProvider);
    for (final taskId in event.taskIds) {
      ref
        ..invalidate(taskDetailProvider(taskId))
        ..invalidate(taskEventsProvider(taskId));
    }
  }

  void _handleCameraObservationRealtimeEvent(WidgetRef ref) {
    ref
      ..invalidate(cameraMonitorStatusProvider)
      ..invalidate(cameraEventsProvider)
      ..invalidate(liveCareStatusProvider);
  }

  void _handleCameraEventRealtimeEvent(WidgetRef ref) {
    ref
      ..invalidate(cameraEventsProvider)
      ..invalidate(liveCareStatusProvider);
  }

  void _handleCameraStatusRealtimeEvent(WidgetRef ref) {
    ref
      ..invalidate(cameraHealthProvider)
      ..invalidate(cameraStatusProvider)
      ..invalidate(cameraRuntimeProvider)
      ..invalidate(primaryDeviceOverviewProvider);
  }
}

class _AppBottomNavigation extends StatelessWidget {
  const _AppBottomNavigation({
    required this.selectedRoute,
    required this.onSelected,
    required this.canAddTask,
    required this.onAddTask,
  });

  final AppRoute selectedRoute;
  final ValueChanged<AppRoute> onSelected;
  final bool canAddTask;
  final VoidCallback onAddTask;

  static const _tabRoutes = [
    AppRoute.home,
    AppRoute.tasks,
    AppRoute.live,
    AppRoute.profile,
  ];
  static const _addSlotWidth = 60.0;
  static const _indicatorHeight = 48.0;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final width = MediaQuery.sizeOf(context).width;
    final horizontalInset = width <= 360 ? 18.0 : 22.0;
    final bottomGap = AppChrome.tabBarBottomGap(bottomInset);
    final selectedIndex = _selectedTabIndex(selectedRoute);
    final duration = AppMotion.duration(context, 210);

    return Padding(
      padding: EdgeInsets.fromLTRB(
        horizontalInset,
        0,
        horizontalInset,
        bottomGap,
      ),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 420),
          child: DecoratedBox(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppChrome.tabBarDockRadius),
              boxShadow: [
                BoxShadow(
                  color: AppColors.navDockShadow.withValues(alpha: 0.055),
                  blurRadius: 26,
                  offset: const Offset(0, 12),
                ),
                BoxShadow(
                  color: AppColors.navDockShadow.withValues(alpha: 0.025),
                  blurRadius: 8,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppChrome.tabBarDockRadius),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [AppColors.navDockBg, AppColors.navDockBgWarm],
                    ),
                    border: Border.all(color: AppColors.navDockBorder),
                  ),
                  child: SizedBox(
                    height: AppChrome.tabBarHeight,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 4,
                      ),
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          final addSlotWidth = canAddTask ? _addSlotWidth : 0.0;
                          final itemWidth =
                              (constraints.maxWidth - addSlotWidth) /
                              _tabRoutes.length;
                          final indicatorLeft =
                              selectedIndex * itemWidth +
                              (canAddTask && selectedIndex >= 2
                                  ? _addSlotWidth
                                  : 0) +
                              2;
                          final indicatorWidth = itemWidth - 4;
                          final indicatorTop =
                              (constraints.maxHeight - _indicatorHeight) / 2;

                          return Stack(
                            children: [
                              AnimatedPositioned(
                                duration: duration,
                                curve: Curves.easeOutCubic,
                                left: indicatorLeft,
                                top: indicatorTop,
                                width: indicatorWidth,
                                height: _indicatorHeight,
                                child: DecoratedBox(
                                  decoration: BoxDecoration(
                                    color: AppColors.navActiveBg,
                                    borderRadius: BorderRadius.circular(
                                      AppRadii.full,
                                    ),
                                    boxShadow: [
                                      BoxShadow(
                                        color: AppColors.navDockShadow
                                            .withValues(alpha: 0.022),
                                        blurRadius: 7,
                                        offset: const Offset(0, 3),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.center,
                                children: [
                                  for (final route in _tabRoutes) ...[
                                    if (route == AppRoute.live && canAddTask)
                                      SizedBox(
                                        width: _addSlotWidth,
                                        child: Center(
                                          child: _BottomNavAddAction(
                                            onTap: onAddTask,
                                          ),
                                        ),
                                      ),
                                    Expanded(
                                      child: _BottomNavItem(
                                        route: route,
                                        selected: selectedRoute == route,
                                        onTap: () => onSelected(route),
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ],
                          );
                        },
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  int _selectedTabIndex(AppRoute route) {
    final index = _tabRoutes.indexOf(route);
    return index < 0 ? 0 : index;
  }
}

class _BottomNavItem extends StatelessWidget {
  const _BottomNavItem({
    required this.route,
    required this.selected,
    required this.onTap,
  });

  final AppRoute route;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final duration = AppMotion.duration(context, 200);
    final foreground = selected
        ? AppColors.navActiveFg
        : AppColors.navInactiveFg;
    return Semantics(
      button: true,
      selected: selected,
      label: route.label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(AppRadii.full),
          focusColor: AppColors.navActiveBg.withValues(alpha: 0.52),
          highlightColor: Colors.transparent,
          hoverColor: Colors.transparent,
          onTap: onTap,
          splashColor: Colors.transparent,
          child: SizedBox(
            height: AppControls.minTouchTarget,
            child: Center(
              child: AnimatedOpacity(
                opacity: selected ? 1 : 0.88,
                duration: duration,
                curve: Curves.easeOutCubic,
                child: AnimatedScale(
                  scale: selected ? 1.03 : 1,
                  duration: duration,
                  curve: Curves.easeOutCubic,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      AnimatedSwitcher(
                        duration: duration,
                        switchInCurve: Curves.easeOutCubic,
                        switchOutCurve: Curves.easeOutCubic,
                        transitionBuilder: (child, animation) {
                          final scale = Tween<double>(begin: 0.96, end: 1)
                              .animate(
                                CurvedAnimation(
                                  parent: animation,
                                  curve: Curves.easeOutCubic,
                                ),
                              );
                          return FadeTransition(
                            opacity: animation,
                            child: ScaleTransition(scale: scale, child: child),
                          );
                        },
                        child: TweenAnimationBuilder<Color?>(
                          key: ValueKey('${route.name}-$selected'),
                          tween: ColorTween(end: foreground),
                          duration: duration,
                          curve: Curves.easeOutCubic,
                          builder: (context, color, _) {
                            return Icon(
                              selected ? route.selectedIcon : route.icon,
                              color: color,
                              size: selected ? 21 : 20,
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 1),
                      AnimatedDefaultTextStyle(
                        duration: duration,
                        curve: Curves.easeOutCubic,
                        style: TextStyle(
                          color: foreground,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 10.4,
                          fontWeight: selected
                              ? FontWeight.w700
                              : FontWeight.w600,
                          height: 1.0,
                          letterSpacing: 0,
                        ),
                        child: Text(
                          route.label,
                          maxLines: 1,
                          overflow: TextOverflow.clip,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNavAddAction extends StatefulWidget {
  const _BottomNavAddAction({required this.onTap});

  final VoidCallback onTap;

  @override
  State<_BottomNavAddAction> createState() => _BottomNavAddActionState();
}

class _BottomNavAddActionState extends State<_BottomNavAddAction> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return Semantics(
      button: true,
      label: '新增任务',
      child: SizedBox.square(
        key: const ValueKey('bottomNavAddAction'),
        dimension: AppControls.minTouchTarget,
        child: GestureDetector(
          onTapDown: (_) => setState(() => _pressed = true),
          onTapCancel: () => setState(() => _pressed = false),
          onTapUp: (_) => setState(() => _pressed = false),
          onTap: widget.onTap,
          child: AnimatedScale(
            scale: reduceMotion || !_pressed ? 1 : 0.965,
            duration: AppMotion.duration(context, 120),
            curve: Curves.easeOutCubic,
            child: Material(
              color: AppColors.navFabBg,
              shape: const CircleBorder(),
              elevation: 0,
              shadowColor: Colors.transparent,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.navDockShadow.withValues(alpha: 0.10),
                      blurRadius: 14,
                      offset: const Offset(0, 6),
                    ),
                    BoxShadow(
                      color: Colors.white.withValues(alpha: 0.14),
                      blurRadius: 1,
                      offset: const Offset(0, 1),
                      spreadRadius: -1,
                    ),
                  ],
                ),
                child: const Center(
                  child: Icon(Icons.add, color: AppColors.navFabFg, size: 22),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

DateTime _startOfWeek(DateTime date) {
  final normalized = DateTime(date.year, date.month, date.day);
  return normalized.subtract(Duration(days: normalized.weekday - 1));
}

DateTime _dayOnly(DateTime date) => DateTime(date.year, date.month, date.day);

void _showShellToast(BuildContext context, String message) {
  showAppToast(context, message, tone: AppToastTone.warning);
}
