import 'dart:async';

import 'package:flutter/material.dart';
import 'package:warm_sight/src/shared/widgets/app_viewport.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_helpers.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/state/async_value_ui.dart';
import 'package:warm_sight/src/core/state/refresh_guard.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/care/application/parent_review_realtime.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/home/application/home_summary.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_habit_hero.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_cta.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_primary_learning_preview.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_rhythm_arc.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_rhythm_rail.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_shared.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen>
    with WidgetsBindingObserver {
  final _refreshGuard = RefreshGuard();
  var _localTodayText = homeDateText(DateTime.now());
  var _refreshGeneration = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    _refreshGeneration++;
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    _localTodayText = homeDateText(DateTime.now());
    unawaited(_refreshHomeSilently());
  }

  Future<void> _refreshHomeSilently() async {
    final generation = ++_refreshGeneration;
    _localTodayText = homeDateText(DateTime.now());
    await _refreshGuard.runLight(() async {
      if (!mounted || generation != _refreshGeneration) return;
      await refreshHomeDataSilently(ref);
    });
  }

  Future<void> _refreshHome() async {
    final generation = ++_refreshGeneration;
    _localTodayText = homeDateText(DateTime.now());
    await _refreshGuard.runLight(() async {
      if (!mounted || generation != _refreshGeneration) return;
      await refreshHomeDataSilently(ref);
    });
  }

  void _invalidateHomeProviders() {
    unawaited(_refreshHomeSilently());
  }

  void _openStudentQrScanner(AsyncValue<ProfileSummary> profile) {
    final summary = profile.asData?.value;
    if (summary == null) {
      showAppToast(
        context,
        profile.hasError ? '家庭资料暂时无法同步' : '正在同步家庭资料',
        message: profile.hasError ? '请下拉刷新后再试。' : '请稍后再试。',
        tone: profile.hasError ? AppToastTone.danger : AppToastTone.neutral,
      );
      return;
    }
    if (!summary.can('manage_child_profile')) {
      showAppToast(
        context,
        '需要家庭管理员授权',
        message: '当前账号没有管理孩子资料的权限。',
        tone: AppToastTone.warning,
      );
      return;
    }
    final child = summary.child;
    if (child == null) {
      showAppToast(
        context,
        '请先完善孩子资料',
        message: '完成小学年级设置后即可扫码登录学习网页。',
        tone: AppToastTone.warning,
      );
      return;
    }
    final grade =
        ChildGradeOption.fromCode(child.gradeCode) ??
        ChildGradeOption.fromLegacy(
          educationStage: child.educationStage,
          grade: child.grade,
        );
    if (grade?.isPrimary != true) {
      showAppToast(
        context,
        '当前年级暂不支持扫码登录',
        message: '学生学习空间仅面向已开放年级。',
        tone: AppToastTone.warning,
      );
      return;
    }
    final availability = child.id.trim().isEmpty
        ? null
        : ref.read(
            studentAccessAvailabilityProvider(studentAccessScope(child)),
          );
    if (availability == null || availability.isLoading) {
      showAppToast(
        context,
        '正在确认学习空间权限',
        message: '确认后即可扫码登录。',
        tone: AppToastTone.neutral,
      );
      return;
    }
    if (availability.hasError) {
      showAppToast(
        context,
        '学习空间权限加载失败',
        message: '请检查网络或下拉刷新后再试。',
        tone: AppToastTone.danger,
      );
      return;
    }
    final current = availability.asData?.value;
    if (current?.gradeCode != child.gradeCode ||
        current?.canAccessWorkspace != true) {
      showAppToast(
        context,
        '当前暂不能登录学习空间',
        message: '请确认孩子已选择开放年级，并完成年级设置。',
        tone: AppToastTone.warning,
      );
      return;
    }
    context.push(studentAccessQrPath);
  }

  HomeSummaryInput _buildInput() {
    final now = DateTime.now();
    final profileSummary = ref.watch(profileSummaryProvider);
    final todayTasks = ref.watch(todayTasksProvider);
    final redemptions = ref.watch(rewardRedemptionsProvider);
    final deviceOverview = ref.watch(primaryDeviceOverviewProvider);
    final cameraHealth = ref.watch(cameraHealthProvider);
    final cameraStatus = ref.watch(cameraStatusProvider);
    final cameraMonitor = ref.watch(cameraMonitorDisplayProvider);
    final child = profileSummary.asData?.value.child;
    if (child != null && child.contentMode == 'primary_learning') {
      ref.watch(studentAccessAvailabilityProvider(studentAccessScope(child)));
    }
    final childId = child?.id;
    final overrideReviews = ref.watch(pendingParentReviewsOverrideProvider);
    final serverReviews = childId != null && childId.isNotEmpty
        ? ref
              .watch(careSummaryProvider(childId))
              .asData
              ?.value
              .needsParentReview
        : null;
    final parentReviews = mergeParentReviews(
      overrideItems: overrideReviews,
      serverItems: serverReviews,
    );

    return HomeSummaryInput(
      now: now,
      profile: profileSummary.asData?.value,
      profileLoading: isInitialAsyncLoad(profileSummary),
      deviceOverview: deviceOverview.asData?.value,
      deviceLoading: isInitialAsyncLoad(deviceOverview),
      deviceError: deviceOverview.hasError,
      cameraHealth: cameraHealth.asData?.value,
      cameraHealthLoading: isInitialAsyncLoad(cameraHealth),
      cameraHealthError: cameraHealth.hasError,
      cameraStatus: cameraStatus.asData?.value,
      cameraStatusLoading: isInitialAsyncLoad(cameraStatus),
      cameraStatusError: cameraStatus.hasError,
      cameraMonitor: cameraMonitor.asData?.value,
      cameraMonitorLoading: isInitialAsyncLoad(cameraMonitor),
      tasks: todayTasks.asData?.value,
      tasksLoading: isInitialAsyncLoad(todayTasks),
      tasksError: todayTasks.hasError,
      redemptions: redemptions.asData?.value,
      redemptionsLoading: redemptions.isLoading,
      parentReviews: parentReviews.isEmpty ? null : parentReviews,
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
    final profileSummary = ref.watch(profileSummaryProvider);
    final summary = buildHomeSummary(input);
    final dailyReport = ref.watch(dailyReportProvider);
    final weeklyReport = ref.watch(weeklyReportProvider);
    final childId = input.profile?.child?.id;
    final child = input.profile?.child;
    final childGrade = child == null
        ? null
        : ChildGradeOption.fromCode(child.gradeCode) ??
              ChildGradeOption.fromLegacy(
                educationStage: child.educationStage,
                grade: child.grade,
              );
    final isPrimaryLearning =
        child?.contentMode == 'primary_learning' &&
        childGrade?.isPrimary == true;
    final showRhythmArc =
        !summary.isInitialLoading &&
        !input.tasksError &&
        summary.rhythmNodes.isNotEmpty;
    if (childId != null && childId.isNotEmpty) {
      ref.listen(careSummaryProvider(childId), (previous, next) {
        if (next.hasValue) {
          ref.read(pendingParentReviewsOverrideProvider.notifier).state =
              const <ParentReviewItem>[];
        }
      });
    }

    final safeBottom = MediaQuery.paddingOf(context).bottom;
    final bottomPadding = AppViewport.verticalBarEdgeOf(context) == null
        ? AppChrome.tabBarBottomGap(safeBottom) +
              AppChrome.tabBarHeight +
              AppChrome.tabBarContentGap +
              18
        : safeBottom + 18;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.shellPaper,
        body: RefreshIndicator(
          color: AppColors.navActiveFg,
          onRefresh: _refreshHome,
          child: CustomScrollView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            slivers: [
              SliverToBoxAdapter(
                child: SafeArea(
                  bottom: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.pageHorizontalExpanded,
                      5,
                      AppSpacing.pageHorizontalExpanded,
                      2,
                    ),
                    child: Row(
                      children: [
                        Image.asset(
                          'assets/brand/nuantong-logo-mark.png',
                          width: 27,
                          height: 27,
                          excludeFromSemantics: true,
                        ),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            '暖瞳',
                            style: TextStyle(
                              color: AppColors.ink,
                              fontSize: 20,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                        HomeStudentQrButton(
                          onTap: () => _openStudentQrScanner(profileSummary),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: HomeHabitHero(
                  focus: summary.habitFocus,
                  isLoading: summary.isInitialLoading,
                  learnerName:
                      isPrimaryLearning &&
                          (summary.hasNoDevice || summary.deviceIssue)
                      ? childDisplayName(input.profile)
                      : null,
                ),
              ),
              if (showRhythmArc && !isPrimaryLearning)
                SliverToBoxAdapter(
                  child: HomeRhythmArc(
                    nodes: summary.rhythmNodes,
                    now: input.now,
                  ),
                ),
              SliverToBoxAdapter(
                child: DecoratedBox(
                  decoration: const BoxDecoration(
                    border: Border(top: BorderSide(color: AppColors.shellRule)),
                  ),
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.pageHorizontalExpanded,
                      isPrimaryLearning ? 14 : 20,
                      AppSpacing.pageHorizontalExpanded,
                      bottomPadding,
                    ),
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final twoColumns = constraints.maxWidth >= 600;
                        return Flex(
                          direction: twoColumns
                              ? Axis.horizontal
                              : Axis.vertical,
                          crossAxisAlignment: twoColumns
                              ? CrossAxisAlignment.start
                              : CrossAxisAlignment.stretch,
                          children: [
                            Flexible(
                              flex: twoColumns ? 6 : 0,
                              fit: FlexFit.tight,
                              child: isPrimaryLearning && child != null
                                  ? HomePrimaryLearningPreview(
                                      key: ValueKey(
                                        'primaryLearningPreviewChild_${child.id}',
                                      ),
                                      child: child,
                                    )
                                  : HomeRhythmRail(
                                      mode: summary.rhythmMode,
                                      nodes: summary.rhythmNodes,
                                      isLoading:
                                          summary.isInitialLoading &&
                                          summary.rhythmNodes.isEmpty,
                                      hasTaskError: input.tasksError,
                                      hasNoDevice: summary.hasNoDevice,
                                    ),
                            ),
                            SizedBox(width: twoColumns ? 28 : 0),
                            Flexible(
                              flex: twoColumns ? 4 : 0,
                              fit: FlexFit.tight,
                              child: Container(
                                decoration: twoColumns
                                    ? const BoxDecoration(
                                        border: BorderDirectional(
                                          start: BorderSide(
                                            color: AppColors.shellRule,
                                          ),
                                        ),
                                      )
                                    : null,
                                padding: twoColumns
                                    ? const EdgeInsetsDirectional.only(
                                        start: 22,
                                      )
                                    : EdgeInsets.zero,
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    if (showRhythmArc && isPrimaryLearning) ...[
                                      if (!twoColumns)
                                        const SizedBox(height: 22),
                                      HomeRhythmArc(
                                        nodes: summary.rhythmNodes,
                                        now: input.now,
                                        padding: EdgeInsets.zero,
                                      ),
                                      const SizedBox(height: 22),
                                    ] else if (!twoColumns)
                                      const SizedBox(height: 22),
                                    _HomeReportSummaryCard(
                                      daily: dailyReport,
                                      weekly: weeklyReport,
                                      onOpen: () =>
                                          context.go(profileReportsHubPath),
                                    ),
                                    const SizedBox(height: 16),
                                    HomePrimaryCtaBar(
                                      cta: summary.primaryCta,
                                      showLiveCareLink:
                                          summary.showLiveCareLink,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
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
      subtitle: dailyData.learning.lessonCount > 0
          ? '今天的学习和看护记录'
          : '今天的安排和看护记录',
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
  if (isInitialAsyncLoad(daily) || isInitialAsyncLoad(weekly)) {
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
      if (data.learning.lessonCount > 0) '学习 ${data.learning.lessonCount} 节',
      if (data.learning.needsSupportCount > 0)
        '${data.learning.needsSupportCount} 节需留意',
      if (data.taskTotal > 0) '完成 ${data.taskCompleted}/${data.taskTotal}',
      if (data.pointsEarned > 0) '+${data.pointsEarned} 分',
      if (data.pendingItems > 0) '${data.pendingItems} 项待处理',
    ],
  );
}

bool _hasReportContent(ReportData data) {
  return data.learning.lessonCount > 0 ||
      data.taskTotal > 0 ||
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
