import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/app/router/app_router.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/features/points/application/point_repository.dart';
import 'package:mira_guardian_app/src/features/tasks/application/task_repository.dart';
import 'package:mira_guardian_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';

class AppShell extends ConsumerWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).uri.path;
    final selectedRoute = routeFromLocation(location);

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColors.appBackgroundWarm,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: AppColors.appBackground,
        body: Stack(
          children: [
            Positioned.fill(child: child),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _MiraBottomNavigation(
                selectedRoute: selectedRoute,
                onSelected: (route) => context.go(route.path),
                onAddTask: () => _openTaskSheet(context, ref),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openTaskSheet(BuildContext context, WidgetRef ref) async {
    String? childId;
    try {
      childId = (await ref.read(pointsSummaryProvider.future)).account.childId;
    } catch (_) {
      childId = null;
    }
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
      _showShellToast(context, '请先完成孩子资料，再添加孩子的新任务。');
      return;
    }
    final resolvedChildId = childId;

    final snapshot = ref.read(guardianMvpSnapshotProvider);
    final savedDate = await showTaskFormSheet(
      context,
      childId: resolvedChildId,
      initialDate: DateTime.now(),
      childAgeGroup: taskAgeGroupForChild(
        stage: snapshot.child.stage,
        grade: snapshot.child.grade,
      ),
      onSavedProgress: () =>
          _invalidateTaskLists(ref, resolvedChildId, DateTime.now()),
    );

    if (savedDate == null) return;
    _invalidateTaskLists(ref, resolvedChildId, savedDate);
    if (context.mounted) {
      context.go(AppRoute.tasks.path);
      showMiraStateSnackBar(
        context,
        variant: MiraStateVariant.saved,
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
}

class _MiraBottomNavigation extends StatelessWidget {
  const _MiraBottomNavigation({
    required this.selectedRoute,
    required this.onSelected,
    required this.onAddTask,
  });

  final AppRoute selectedRoute;
  final ValueChanged<AppRoute> onSelected;
  final VoidCallback onAddTask;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        14,
        0,
        14,
        bottomInset > 0 ? bottomInset : 10,
      ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(26),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF19273B).withValues(alpha: 0.08),
              blurRadius: 28,
              offset: const Offset(0, 16),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(26),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Colors.white.withValues(alpha: 0.66),
                    AppColors.appBackgroundWarm.withValues(alpha: 0.48),
                  ],
                ),
                border: Border.all(color: Colors.white.withValues(alpha: 0.68)),
              ),
              child: SizedBox(
                height: AppChrome.tabBarHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      child: _BottomNavItem(
                        route: AppRoute.home,
                        selected: selectedRoute == AppRoute.home,
                        onTap: () => onSelected(AppRoute.home),
                      ),
                    ),
                    Expanded(
                      child: _BottomNavItem(
                        route: AppRoute.tasks,
                        selected: selectedRoute == AppRoute.tasks,
                        onTap: () => onSelected(AppRoute.tasks),
                      ),
                    ),
                    _BottomNavAddAction(onTap: onAddTask),
                    Expanded(
                      child: _BottomNavItem(
                        route: AppRoute.live,
                        selected: selectedRoute == AppRoute.live,
                        onTap: () => onSelected(AppRoute.live),
                      ),
                    ),
                    Expanded(
                      child: _BottomNavItem(
                        route: AppRoute.profile,
                        selected: selectedRoute == AppRoute.profile,
                        onTap: () => onSelected(AppRoute.profile),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
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
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(
        button: true,
        selected: selected,
        label: route.label,
        child: AnimatedOpacity(
          opacity: selected ? 1 : 0.82,
          duration: AppMotion.duration(context, 180),
          curve: Curves.easeOutCubic,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              AnimatedContainer(
                duration: AppMotion.duration(context, 180),
                curve: Curves.easeOutCubic,
                width: 38,
                height: 28,
                decoration: BoxDecoration(
                  color: selected
                      ? AppColors.brand.withValues(alpha: 0.11)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Center(
                  child: Icon(
                    selected ? route.selectedIcon : route.icon,
                    color: selected ? AppColors.brand : const Color(0x99526579),
                    size: 20,
                  ),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                route.label,
                style: TextStyle(
                  color: selected ? AppColors.brand : const Color(0x99526579),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 10.5,
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w700,
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
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => setState(() => _pressed = true),
      onTapCancel: () => setState(() => _pressed = false),
      onTapUp: (_) => setState(() => _pressed = false),
      onTap: widget.onTap,
      child: Semantics(
        button: true,
        label: '新增任务',
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 7),
          child: AnimatedScale(
            scale: reduceMotion || !_pressed ? 1 : AppMotion.buttonPressScale,
            duration: AppMotion.duration(context, 120),
            curve: Curves.easeOutCubic,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [
                    AppColors.primaryButtonStart,
                    AppColors.primaryButtonEnd,
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(22),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primaryButtonShadow.withValues(
                      alpha: 0.22,
                    ),
                    blurRadius: 16,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: const SizedBox(
                width: 50,
                height: 50,
                child: Center(
                  child: Icon(Icons.add, color: Colors.white, size: 23),
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

void _showShellToast(BuildContext context, String message) {
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
