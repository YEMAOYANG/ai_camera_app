import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/app/router/app_router.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/devices/presentation/onvif_auto_discovery_gate.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/presentation/privacy_authorization_gate.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';
import 'package:warm_sight/src/features/tasks/presentation/tasks_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import 'package:warm_sight/src/shared/widgets/app_viewport.dart';

class AppShell extends ConsumerWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).uri.path;
    final selectedRoute = routeFromLocation(location);
    final canAddTask =
        ref.watch(profileSummaryProvider).asData?.value.can('manage_tasks') ??
        false;
    final rail = AppViewport.sideNavigationOf(context);
    final hasRail = rail != null;
    final onLeft = rail?.edge == AppVerticalBarEdge.left;
    final railWidth = rail?.width ?? 0;
    final navigation = _AppTabNavigation(
      selectedRoute: selectedRoute,
      onSelected: (route) => context.go(route.path),
      canAddTask: canAddTask,
      onAddTask: () => _openTaskSheet(context, ref),
      vertical: hasRail,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.shellPaper,
        extendBody: true,
        body: Stack(
          children: [
            Positioned.fill(
              left: hasRail && onLeft ? railWidth : 0,
              right: hasRail && !onLeft ? railWidth : 0,
              child: Builder(
                builder: (context) {
                  final media = MediaQuery.of(context);
                  return MediaQuery(
                    data: hasRail
                        ? media
                              .removePadding(
                                removeLeft: onLeft,
                                removeRight: !onLeft,
                              )
                              .copyWith(
                                size: Size(
                                  media.size.width - railWidth,
                                  media.size.height,
                                ),
                              )
                        : media,
                    child: PrivacyAuthorizationGate(
                      secondaryOverlayBuilder: (content) =>
                          OnvifAutoDiscoveryGate(child: content),
                      child: child,
                    ),
                  );
                },
              ),
            ),
            Positioned(
              left: !hasRail || onLeft ? 0 : null,
              right: !hasRail || !onLeft ? 0 : null,
              top: rail?.top,
              bottom: 0,
              width: hasRail ? railWidth : null,
              child: navigation,
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
}

class _AppTabNavigation extends StatelessWidget {
  const _AppTabNavigation({
    required this.selectedRoute,
    required this.onSelected,
    required this.canAddTask,
    required this.onAddTask,
    required this.vertical,
  });

  final AppRoute selectedRoute;
  final ValueChanged<AppRoute> onSelected;
  final bool canAddTask;
  final VoidCallback onAddTask;
  final bool vertical;

  static const _tabRoutes = [
    AppRoute.home,
    AppRoute.tasks,
    AppRoute.live,
    AppRoute.profile,
  ];
  static const _addSlotWidth = 64.0;
  static const _railItemHeight = 52.0;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    if (vertical) {
      return ColoredBox(
        color: AppColors.navDockBg,
        child: SafeArea(
          left: false,
          right: false,
          minimum: const EdgeInsets.only(bottom: 8),
          child: Align(
            alignment: Alignment.bottomCenter,
            child: SingleChildScrollView(
              reverse: true,
              child: SizedBox(
                key: const ValueKey('sideNavigation'),
                height:
                    _railItemHeight *
                    (_tabRoutes.length + (canAddTask ? 1 : 0)),
                width: AppChrome.sideNavigationWidth,
                child: LayoutBuilder(builder: _buildTabs),
              ),
            ),
          ),
        ),
      );
    }

    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          top: -AppChrome.tabBarContentGap,
          height: AppChrome.tabBarContentGap,
          left: 0,
          right: 0,
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.navDockBg.withValues(alpha: 0),
                    AppColors.navDockBg,
                  ],
                ),
              ),
            ),
          ),
        ),
        ColoredBox(
          color: AppColors.navDockBg,
          child: Padding(
            padding: EdgeInsets.only(
              bottom: AppChrome.tabBarBottomGap(bottomInset),
            ),
            child: Center(
              heightFactor: 1,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: SizedBox(
                  height: AppChrome.tabBarHeight,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: LayoutBuilder(builder: _buildTabs),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTabs(BuildContext context, BoxConstraints constraints) {
    final selectedIndex = _tabRoutes.indexOf(selectedRoute);
    final addIndex = _tabRoutes.indexOf(AppRoute.live);
    final addExtent = canAddTask
        ? (vertical ? _railItemHeight : _addSlotWidth)
        : 0.0;
    final extent = vertical ? constraints.maxHeight : constraints.maxWidth;
    final tabExtent = (extent - addExtent) / _tabRoutes.length;
    final selectedStart =
        selectedIndex * tabExtent + (selectedIndex >= addIndex ? addExtent : 0);

    return Stack(
      fit: StackFit.expand,
      clipBehavior: Clip.none,
      children: [
        if (selectedIndex >= 0)
          AnimatedPositionedDirectional(
            key: const ValueKey('bottomNavSelection'),
            start: vertical ? 0 : selectedStart,
            end: vertical ? 0 : null,
            top: vertical ? selectedStart : 0,
            bottom: vertical ? null : 0,
            width: vertical ? null : tabExtent,
            height: vertical ? tabExtent : null,
            duration: AppMotion.duration(context, 320),
            curve: const Cubic(.22, .80, .22, 1),
            child: const IgnorePointer(
              child: Align(
                alignment: Alignment(0, -.58),
                child: SizedBox(
                  width: 56,
                  height: 36,
                  child: CustomPaint(painter: _NavigationWashPainter()),
                ),
              ),
            ),
          ),
        Flex(
          direction: vertical ? Axis.vertical : Axis.horizontal,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var index = 0; index < _tabRoutes.length; index++) ...[
              if (index == addIndex && canAddTask)
                SizedBox(
                  width: vertical ? null : addExtent,
                  height: vertical ? addExtent : null,
                  child: Center(child: _BottomNavAddAction(onTap: onAddTask)),
                ),
              Expanded(
                child: _BottomNavItem(
                  route: _tabRoutes[index],
                  selected: selectedIndex == index,
                  onTap: () => onSelected(_tabRoutes[index]),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

class _NavigationWashPainter extends CustomPainter {
  const _NavigationWashPainter();

  @override
  void paint(Canvas canvas, Size size) {
    _paintWash(
      canvas,
      center: Offset(size.width * .61, size.height * .56),
      radiusX: 20,
      radiusY: 13,
      gradient: const RadialGradient(
        colors: [AppColors.navWashSecondary, AppColors.navWashSecondaryEdge],
        stops: [.13, 1],
      ),
    );
    _paintWash(
      canvas,
      center: Offset(size.width * .43, size.height * .50),
      radiusX: 22,
      radiusY: 16,
      gradient: const RadialGradient(
        colors: [
          AppColors.navWashCenter,
          AppColors.navWashFade,
          AppColors.navWashEdge,
        ],
        stops: [.06, .62, 1],
      ),
    );
  }

  void _paintWash(
    Canvas canvas, {
    required Offset center,
    required double radiusX,
    required double radiusY,
    required RadialGradient gradient,
  }) {
    final shaderBounds = Rect.fromCircle(center: Offset.zero, radius: 1);
    canvas.save();
    canvas.translate(center.dx, center.dy);
    canvas.scale(radiusX, radiusY);
    canvas.drawCircle(
      Offset.zero,
      1,
      Paint()..shader = gradient.createShader(shaderBounds),
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(_NavigationWashPainter oldDelegate) => false;
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
          borderRadius: BorderRadius.circular(AppRadii.control),
          focusColor: AppColors.navActiveBg.withValues(alpha: 0.52),
          highlightColor: Colors.transparent,
          hoverColor: Colors.transparent,
          onTap: onTap,
          splashColor: Colors.transparent,
          child: SizedBox(
            height: AppChrome.tabBarHeight,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedScale(
                  scale: selected ? 1.08 : 1,
                  duration: duration,
                  curve: Curves.easeOutCubic,
                  child: SizedBox(
                    height: 26,
                    child: Icon(
                      selected ? route.selectedIcon : route.icon,
                      color: foreground,
                      size: 22,
                    ),
                  ),
                ),
                const SizedBox(height: 2),
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      route.label,
                      maxLines: 1,
                      style: TextStyle(
                        color: foreground,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: selected
                            ? FontWeight.w700
                            : FontWeight.w500,
                        height: 1.12,
                      ),
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
          behavior: HitTestBehavior.opaque,
          onTapDown: (_) => setState(() => _pressed = true),
          onTapCancel: () => setState(() => _pressed = false),
          onTapUp: (_) => setState(() => _pressed = false),
          onTap: widget.onTap,
          child: AnimatedScale(
            scale: reduceMotion || !_pressed ? 1 : 0.965,
            duration: AppMotion.duration(context, 120),
            curve: Curves.easeOutCubic,
            child: const Center(
              child: Material(
                color: AppColors.navFabBg,
                shape: CircleBorder(
                  side: BorderSide(color: AppColors.navFabBorder),
                ),
                child: SizedBox.square(
                  dimension: 34,
                  child: Icon(Icons.add, color: AppColors.navFabFg, size: 21),
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
