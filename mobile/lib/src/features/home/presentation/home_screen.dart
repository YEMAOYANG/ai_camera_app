import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_system_ui.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/home/application/home_summary.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_ai_companion_card.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_habit_hero.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_pending_queue.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_primary_cta.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_rhythm_rail.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/application/reward_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_repository.dart';

const _homePanelSurface = AppColors.surfaceElevated;
const _homeScaffoldBackground = AppColors.surfaceElevated;

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen>
    with WidgetsBindingObserver {
  final _scrollController = ScrollController();
  var _localTodayText = homeDateText(DateTime.now());
  var _scrollOffset = 0.0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _scrollController.addListener(_handleScroll);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _scrollController
      ..removeListener(_handleScroll)
      ..dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    _localTodayText = homeDateText(DateTime.now());
    unawaited(_refreshMonitorOnce());
    _invalidateHomeProviders();
  }

  void _invalidateHomeProviders() {
    ref
      ..invalidate(profileSummaryProvider)
      ..invalidate(primaryDeviceOverviewProvider)
      ..invalidate(todayTasksProvider)
      ..invalidate(rewardRedemptionsProvider)
      ..invalidate(cameraStatusProvider)
      ..invalidate(cameraHealthProvider)
      ..invalidate(cameraMonitorStatusProvider);
  }

  Future<void> _refreshHome() async {
    _localTodayText = homeDateText(DateTime.now());
    await _refreshMonitorOnce();
    _invalidateHomeProviders();
    await Future.wait<Object?>(
      [
        ref.read(profileSummaryProvider.future).then<Object?>((value) => value),
        ref
            .read(primaryDeviceOverviewProvider.future)
            .then<Object?>((value) => value),
        ref.read(todayTasksProvider.future).then<Object?>((value) => value),
        ref
            .read(rewardRedemptionsProvider.future)
            .then<Object?>((value) => value),
        ref.read(cameraHealthProvider.future).then<Object?>((value) => value),
        ref.read(cameraStatusProvider.future).then<Object?>((value) => value),
        ref
            .read(cameraMonitorStatusProvider.future)
            .then<Object?>((value) => value),
      ].map((future) => future.catchError((_) => null)),
    );
  }

  Future<void> _refreshMonitorOnce() async {
    try {
      await ref.read(cameraRepositoryProvider).refreshMonitor();
    } catch (_) {
      // 页面仍可通过普通状态接口和下拉刷新兜底，不因为一次观察刷新失败进入错误态。
    }
  }

  void _handleScroll() {
    final nextOffset = _scrollController.offset.clamp(0.0, 360.0);
    if ((nextOffset - _scrollOffset).abs() < 0.5) return;
    setState(() => _scrollOffset = nextOffset);
  }

  HomeSummaryInput _buildInput() {
    final now = DateTime.now();
    final profileSummary = ref.watch(profileSummaryProvider);
    final todayTasks = ref.watch(todayTasksProvider);
    final redemptions = ref.watch(rewardRedemptionsProvider);
    final deviceOverview = ref.watch(primaryDeviceOverviewProvider);
    final cameraHealth = ref.watch(cameraHealthProvider);
    final cameraStatus = ref.watch(cameraStatusProvider);
    final cameraMonitor = ref.watch(cameraMonitorStatusProvider);

    return HomeSummaryInput(
      now: now,
      profile: profileSummary.asData?.value,
      profileLoading: profileSummary.isLoading,
      deviceOverview: deviceOverview.asData?.value,
      deviceLoading: deviceOverview.isLoading,
      deviceError: deviceOverview.hasError,
      cameraHealth: cameraHealth.asData?.value,
      cameraHealthLoading: cameraHealth.isLoading,
      cameraHealthError: cameraHealth.hasError,
      cameraStatus: cameraStatus.asData?.value,
      cameraStatusLoading: cameraStatus.isLoading,
      cameraStatusError: cameraStatus.hasError,
      cameraMonitor: cameraMonitor.asData?.value,
      cameraMonitorLoading: cameraMonitor.isLoading,
      tasks: todayTasks.asData?.value,
      tasksLoading: todayTasks.isLoading,
      tasksError: todayTasks.hasError,
      redemptions: redemptions.asData?.value,
      redemptionsLoading: redemptions.isLoading,
    );
  }

  @override
  Widget build(BuildContext context) {
    final nextTodayText = homeDateText(DateTime.now());
    if (nextTodayText != _localTodayText) {
      _localTodayText = nextTodayText;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _invalidateHomeProviders();
      });
    }

    final input = _buildInput();
    final summary = buildHomeSummary(input);

    return LayoutBuilder(
      builder: (context, constraints) {
        final safeArea = MediaQuery.paddingOf(context);
        final size = MediaQuery.sizeOf(context);
        final heroHeight = _resolveHeroHeight(size, safeArea, constraints);
        final panelOverlap = _resolvePanelOverlap(size);
        final topSpacer = math.max(0.0, heroHeight - panelOverlap);
        final bottomPadding =
            AppChrome.tabBarBottomGap(safeArea.bottom) +
            AppChrome.tabBarHeight +
            AppChrome.tabBarContentGap +
            18;
        final minPanelHeight = math.max(0.0, constraints.maxHeight - topSpacer);

        return AnnotatedRegion<SystemUiOverlayStyle>(
          value: AppSystemUi.dark().copyWith(
            systemNavigationBarIconBrightness: Brightness.dark,
          ),
          child: Scaffold(
            backgroundColor: _homeScaffoldBackground,
            body: Stack(
              children: [
                const Positioned.fill(
                  child: ColoredBox(color: _homeScaffoldBackground),
                ),
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: heroHeight,
                  child: HomeHabitHero(
                    focus: summary.habitFocus,
                    safeTop: safeArea.top,
                    scrollOffset: _scrollOffset,
                    isLoading: summary.isLoading,
                    panelOverlap: panelOverlap,
                  ),
                ),
                RefreshIndicator(
                  color: AppColors.brandDeep,
                  onRefresh: _refreshHome,
                  child: CustomScrollView(
                    controller: _scrollController,
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
                    physics: const BouncingScrollPhysics(
                      parent: AlwaysScrollableScrollPhysics(),
                    ),
                    slivers: [
                      SliverToBoxAdapter(child: SizedBox(height: topSpacer)),
                      SliverToBoxAdapter(
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: _homePanelSurface,
                            borderRadius: const BorderRadius.vertical(
                              top: Radius.circular(30),
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: AppColors.ink.withValues(alpha: 0.07),
                                blurRadius: 24,
                                offset: const Offset(0, -8),
                              ),
                            ],
                          ),
                          child: ConstrainedBox(
                            constraints: BoxConstraints(
                              minHeight: minPanelHeight,
                            ),
                            child: Padding(
                              padding: EdgeInsets.fromLTRB(
                                AppSpacing.pageHorizontal,
                                20,
                                AppSpacing.pageHorizontal,
                                bottomPadding,
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  HomeRhythmRail(
                                    mode: summary.rhythmMode,
                                    nodes: summary.rhythmNodes,
                                    isLoading:
                                        summary.isLoading &&
                                        summary.rhythmNodes.isEmpty,
                                    hasTaskError: input.tasksError,
                                    hasNoDevice: summary.hasNoDevice,
                                  ),
                                  const SizedBox(height: 14),
                                  HomePendingQueue(
                                    items: summary.pendingItems,
                                    hasNoDevice: summary.hasNoDevice,
                                    isLoading: summary.isLoading,
                                    showNoDevicePrompt:
                                        summary.rhythmNodes.isNotEmpty,
                                  ),
                                  const SizedBox(height: 14),
                                  HomeRecentObservationCard(
                                    copy: summary.recentObservation,
                                    isLoading: summary.isLoading,
                                    onRefresh: () => unawaited(_refreshHome()),
                                    onOpenLive: () =>
                                        context.go(AppRoute.live.path),
                                  ),
                                  const SizedBox(height: 14),
                                  HomePrimaryCtaBar(
                                    cta: summary.primaryCta,
                                    showLiveCareLink: summary.showLiveCareLink,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  double _resolveHeroHeight(
    Size size,
    EdgeInsets safeArea,
    BoxConstraints constraints,
  ) {
    final width = constraints.maxWidth.isFinite
        ? constraints.maxWidth
        : size.width;
    if (size.height <= 620) {
      final compactRaw = size.height * 0.63 + safeArea.top * 0.22;
      return compactRaw.clamp(352.0, 372.0).toDouble();
    }
    final byHeight = size.height * 0.46;
    final byWidth = width * 0.92;
    final raw = math.min(byHeight, byWidth) + safeArea.top * 0.36;
    return raw.clamp(AppHomeHero.minHeight, AppHomeHero.maxHeight).toDouble();
  }

  double _resolvePanelOverlap(Size size) {
    if (size.height < 720) return 96;
    if (size.height > 880) return AppHomeHero.panelOverlap + 78;
    return AppHomeHero.panelOverlap + 58;
  }
}
