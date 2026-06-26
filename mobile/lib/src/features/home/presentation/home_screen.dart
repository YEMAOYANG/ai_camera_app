import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/home/application/home_summary.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_ai_companion_card.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_habit_hero.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_pending_queue.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_cta.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_rhythm_rail.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_shared.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

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
  Timer? _monitorPollTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _scrollController.addListener(_handleScroll);
    _monitorPollTimer = Timer.periodic(const Duration(seconds: 90), (_) {
      if (!mounted) return;
      ref.invalidate(cameraMonitorStatusProvider);
    });
  }

  @override
  void dispose() {
    _monitorPollTimer?.cancel();
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
    final dailyReport = ref.watch(dailyReportProvider);
    final weeklyReport = ref.watch(weeklyReportProvider);

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
                                  _HomeReportSummaryCard(
                                    daily: dailyReport,
                                    weekly: weeklyReport,
                                    onOpen: () =>
                                        context.go(profileReportsHubPath),
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

class _HomeReportSummaryCard extends StatelessWidget {
  const _HomeReportSummaryCard({
    required this.daily,
    required this.weekly,
    required this.onOpen,
  });

  final AsyncValue<ReportData> daily;
  final AsyncValue<ReportData> weekly;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final data = _resolveHomeReport(daily: daily, weekly: weekly);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        HomeSectionTitle(
          title: '看护报告',
          subtitle: data.subtitle,
          actionLabel: '查看',
          onAction: onOpen,
        ),
        const SizedBox(height: 10),
        HomePressable(
          onTap: onOpen,
          child: Semantics(
            button: true,
            label: data.title,
            child: HomeSoftPanel(
              tone: data.tone,
              padding: const EdgeInsets.fromLTRB(14, 13, 14, 13),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  HomeToneIcon(icon: data.icon, tone: data.tone),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          data.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.ink,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 15,
                            fontWeight: FontWeight.w900,
                            height: 1.18,
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          data.detail,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.muted,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 12.5,
                            fontWeight: FontWeight.w600,
                            height: 1.35,
                          ),
                        ),
                        if (data.metrics.isNotEmpty) ...[
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              for (final metric in data.metrics)
                                _HomeReportMetric(label: metric),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  const Icon(
                    Icons.chevron_right_rounded,
                    color: AppColors.subtle,
                    size: 20,
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

class _HomeReportMetric extends StatelessWidget {
  const _HomeReportMetric({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceElevated.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
        child: Text(
          label,
          style: const TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            height: 1.1,
          ),
        ),
      ),
    );
  }
}

class _HomeReportCopy {
  const _HomeReportCopy({
    required this.title,
    required this.subtitle,
    required this.detail,
    required this.icon,
    required this.tone,
    this.metrics = const [],
  });

  final String title;
  final String subtitle;
  final String detail;
  final IconData icon;
  final StatusTone tone;
  final List<String> metrics;
}

_HomeReportCopy _resolveHomeReport({
  required AsyncValue<ReportData> daily,
  required AsyncValue<ReportData> weekly,
}) {
  final dailyData = daily.asData?.value;
  if (dailyData != null && _hasReportContent(dailyData)) {
    return _reportCopy(
      title: '今日报告',
      subtitle: '今天的安排和看护记录',
      data: dailyData,
      icon: Icons.today_outlined,
      tone: StatusTone.success,
    );
  }
  final weeklyData = weekly.asData?.value;
  if (weeklyData != null && _hasReportContent(weeklyData)) {
    return _reportCopy(
      title: '本周报告',
      subtitle: '今天还少，先看本周变化',
      data: weeklyData,
      icon: Icons.calendar_month_outlined,
      tone: StatusTone.neutral,
    );
  }
  if (daily.isLoading || weekly.isLoading) {
    return const _HomeReportCopy(
      title: '正在整理报告',
      subtitle: '今天优先，没有就看本周',
      detail: '稍等一下，正在整理安排和看护记录。',
      icon: Icons.auto_graph_outlined,
      tone: StatusTone.neutral,
    );
  }
  if (daily.hasError && weekly.hasError) {
    return const _HomeReportCopy(
      title: '报告暂时没取到',
      subtitle: '今天优先，没有就看本周',
      detail: '稍后可以再查看。',
      icon: Icons.auto_graph_outlined,
      tone: StatusTone.warning,
    );
  }
  return const _HomeReportCopy(
    title: '还没有可整理的报告',
    subtitle: '今天优先，没有就看本周',
    detail: '完成安排或产生看护记录后，这里会整理今天和本周情况。',
    icon: Icons.auto_graph_outlined,
    tone: StatusTone.neutral,
  );
}

_HomeReportCopy _reportCopy({
  required String title,
  required String subtitle,
  required ReportData data,
  required IconData icon,
  required StatusTone tone,
}) {
  final detail = [data.headline, data.body, data.summary]
      .map((item) => item.trim())
      .firstWhere((item) => item.isNotEmpty, orElse: () => '看看最近安排、积分和看护记录。');
  return _HomeReportCopy(
    title: title,
    subtitle: subtitle,
    detail: detail,
    icon: icon,
    tone: tone,
    metrics: [
      if (data.taskTotal > 0) '完成 ${data.taskCompleted}/${data.taskTotal}',
      if (data.pointsEarned > 0) '+${data.pointsEarned} 分',
      if (data.pendingItems > 0) '${data.pendingItems} 项待处理',
    ],
  );
}

bool _hasReportContent(ReportData data) {
  return data.taskTotal > 0 ||
      data.taskCompleted > 0 ||
      data.pointsEarned > 0 ||
      data.pendingItems > 0 ||
      data.skills.isNotEmpty ||
      data.highlights.isNotEmpty ||
      data.improvements.isNotEmpty ||
      data.observations.isNotEmpty ||
      data.tasks.isNotEmpty ||
      data.nextActions.isNotEmpty;
}
