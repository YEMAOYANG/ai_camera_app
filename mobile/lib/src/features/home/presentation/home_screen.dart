import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:guardian_parent_app/src/core/theme/app_system_ui.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/points/domain/point_models.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/features/rewards/application/reward_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/domain/reward_models.dart';
import 'package:guardian_parent_app/src/features/tasks/application/task_repository.dart';
import 'package:guardian_parent_app/src/features/tasks/domain/task_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_background.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

const _homeHeroImage = 'assets/images/home/home-hero-desk-evening.png';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen>
    with WidgetsBindingObserver {
  final _scrollController = ScrollController();
  var _localTodayText = _homeDateText(DateTime.now());
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
    _localTodayText = _homeDateText(DateTime.now());
    ref.invalidate(todayTasksProvider);
  }

  void _handleScroll() {
    final nextOffset = _scrollController.offset.clamp(0.0, 360.0);
    if ((nextOffset - _scrollOffset).abs() < 0.5) return;
    setState(() => _scrollOffset = nextOffset);
  }

  @override
  Widget build(BuildContext context) {
    final nextTodayText = _homeDateText(DateTime.now());
    if (nextTodayText != _localTodayText) {
      _localTodayText = nextTodayText;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) ref.invalidate(todayTasksProvider);
      });
    }
    final profileSummary = ref.watch(profileSummaryProvider);
    final todayTasks = ref.watch(todayTasksProvider);
    final redemptions = ref.watch(rewardRedemptionsProvider);
    final points = ref.watch(pointsSummaryProvider);
    final deviceOverview = ref.watch(primaryDeviceOverviewProvider);
    final cameraHealth = ref.watch(cameraHealthProvider);
    final cameraStatus = ref.watch(cameraStatusProvider);

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

        return AnnotatedRegion<SystemUiOverlayStyle>(
          value: AppSystemUi.dark().copyWith(
            systemNavigationBarIconBrightness: Brightness.dark,
          ),
          child: Scaffold(
            backgroundColor: AppColors.appBackground,
            body: Stack(
              children: [
                const Positioned.fill(child: AppScreenBackground()),
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  height: heroHeight + 24,
                  child: _HomeHeroBackdrop(
                    profileSummary: profileSummary,
                    deviceOverview: deviceOverview,
                    cameraHealth: cameraHealth,
                    cameraStatus: cameraStatus,
                    todayTasks: todayTasks,
                    redemptions: redemptions,
                    safeTop: safeArea.top,
                    scrollOffset: _scrollOffset,
                  ),
                ),
                CustomScrollView(
                  controller: _scrollController,
                  keyboardDismissBehavior:
                      ScrollViewKeyboardDismissBehavior.onDrag,
                  physics: const BouncingScrollPhysics(
                    parent: AlwaysScrollableScrollPhysics(),
                  ),
                  slivers: [
                    SliverToBoxAdapter(child: SizedBox(height: topSpacer)),
                    SliverToBoxAdapter(
                      child: _HomeContentPanel(
                        bottomPadding: bottomPadding,
                        children: [
                          _HomePrioritySection(
                            tasks: todayTasks,
                            redemptions: redemptions,
                            deviceOverview: deviceOverview,
                            cameraHealth: cameraHealth,
                            cameraStatus: cameraStatus,
                          ),
                          const SizedBox(height: 14),
                          _HomeTodaySection(tasks: todayTasks),
                          const SizedBox(height: 16),
                          _HomeConfirmRewardSection(
                            tasks: todayTasks,
                            points: points,
                            redemptions: redemptions,
                          ),
                          const SizedBox(height: 16),
                          _HomeCareInsightSection(
                            deviceOverview: deviceOverview,
                            cameraHealth: cameraHealth,
                            cameraStatus: cameraStatus,
                            todayTasks: todayTasks,
                          ),
                        ],
                      ),
                    ),
                  ],
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
    if (size.height < 720) return 56;
    if (size.height > 880) return 68;
    return AppHomeHero.panelOverlap + 16;
  }
}

class _HomeContentPanel extends StatelessWidget {
  const _HomeContentPanel({
    required this.children,
    required this.bottomPadding,
  });

  final List<Widget> children;
  final double bottomPadding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFFFAFCFF), AppColors.appBackground],
          stops: [0, 0.22],
        ),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(30)),
        boxShadow: [
          BoxShadow(
            color: AppColors.ink.withValues(alpha: 0.07),
            blurRadius: 24,
            offset: const Offset(0, -8),
          ),
        ],
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
          children: children,
        ),
      ),
    );
  }
}

class _HomeHeroBackdrop extends StatelessWidget {
  const _HomeHeroBackdrop({
    required this.profileSummary,
    required this.deviceOverview,
    required this.cameraHealth,
    required this.cameraStatus,
    required this.todayTasks,
    required this.redemptions,
    required this.safeTop,
    required this.scrollOffset,
  });

  final AsyncValue<ProfileSummary> profileSummary;
  final AsyncValue<DeviceOverview?> deviceOverview;
  final AsyncValue<CameraHealth> cameraHealth;
  final AsyncValue<CameraStatus> cameraStatus;
  final AsyncValue<List<GuardianTask>> todayTasks;
  final AsyncValue<List<RewardRedemption>> redemptions;
  final double safeTop;
  final double scrollOffset;

  @override
  Widget build(BuildContext context) {
    final overview = deviceOverview.asData?.value;
    final hasNoDevice =
        overview == null &&
        !deviceOverview.isLoading &&
        !deviceOverview.hasError;
    final health = cameraHealth.asData?.value;
    final camera = cameraStatus.asData?.value;
    final deviceOnline = hasNoDevice
        ? false
        : overview?.isOnline ?? camera?.isOnline ?? false;
    final cameraOnline = hasNoDevice
        ? false
        : camera?.isOnline ?? health?.reachable ?? false;
    final localTodayTasks = _localTodayTasks(todayTasks.asData?.value);
    final currentTask =
        camera?.currentTask ?? _currentTaskFromToday(localTodayTasks);
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final progress = (scrollOffset / 260).clamp(0.0, 1.0).toDouble();
    final translateY = reduceMotion ? 0.0 : -scrollOffset * 0.16;
    final scale = reduceMotion ? 1.0 : 1.0 + progress * 0.035;
    final imageOpacity = reduceMotion ? 1.0 : 1.0 - progress * 0.14;

    return ClipRect(
      child: Stack(
        children: [
          const Positioned.fill(child: _HomeHeroFallback()),
          Positioned.fill(
            child: Transform.translate(
              offset: Offset(0, translateY),
              child: Transform.scale(
                scale: scale,
                alignment: Alignment.centerRight,
                child: Opacity(
                  opacity: imageOpacity,
                  child: Image.asset(
                    _homeHeroImage,
                    fit: BoxFit.cover,
                    alignment: Alignment.centerRight,
                    errorBuilder: (_, _, _) => const _HomeHeroFallback(),
                  ),
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: [
                    const Color(0xFF111827).withValues(alpha: 0.86),
                    const Color(0xFF111827).withValues(alpha: 0.56),
                    const Color(0xFF111827).withValues(alpha: 0.18),
                  ],
                  stops: const [0, 0.42, 1],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.18),
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.50),
                  ],
                  stops: const [0, 0.48, 1],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: _HomeHeroContent(
              profileSummary: profileSummary,
              hasNoDevice: hasNoDevice,
              deviceOnline: deviceOnline,
              cameraOnline: cameraOnline,
              deviceStateLoading:
                  deviceOverview.isLoading ||
                  cameraHealth.isLoading ||
                  cameraStatus.isLoading,
              currentTask: currentTask,
              pendingCount: _pendingActionCount(localTodayTasks, redemptions),
              todayTaskCount: localTodayTasks?.length,
              safeTop: safeTop,
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeHeroFallback extends StatelessWidget {
  const _HomeHeroFallback();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF1C2940),
            AppColors.brandSage.withValues(alpha: 0.88),
            AppColors.brandWarm.withValues(alpha: 0.72),
          ],
        ),
      ),
    );
  }
}

class _HomeHeroContent extends StatelessWidget {
  const _HomeHeroContent({
    required this.profileSummary,
    required this.deviceOnline,
    required this.cameraOnline,
    required this.deviceStateLoading,
    required this.hasNoDevice,
    required this.currentTask,
    required this.pendingCount,
    required this.todayTaskCount,
    required this.safeTop,
  });

  final AsyncValue<ProfileSummary> profileSummary;
  final bool hasNoDevice;
  final bool deviceOnline;
  final bool cameraOnline;
  final bool deviceStateLoading;
  final GuardianTask? currentTask;
  final int pendingCount;
  final int? todayTaskCount;
  final double safeTop;

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final compact = size.width <= 340 || size.height <= 620;
    final profile = profileSummary.asData?.value;
    final focus = _heroFocusCopy(
      profile: profile,
      profileLoading: profileSummary.isLoading,
      deviceStateLoading: deviceStateLoading,
      hasNoDevice: hasNoDevice,
      currentTask: currentTask,
      deviceOnline: deviceOnline,
      cameraOnline: cameraOnline,
      pendingCount: pendingCount,
      todayTaskCount: todayTaskCount,
    );
    final chips = _heroChips(
      profile: profile,
      profileLoading: profileSummary.isLoading,
      deviceStateLoading: deviceStateLoading,
      hasNoDevice: hasNoDevice,
      deviceOnline: deviceOnline,
      cameraOnline: cameraOnline,
      pendingCount: pendingCount,
      todayTaskCount: todayTaskCount,
    );
    final bottomPadding = compact
        ? AppHomeHero.panelOverlap + 42
        : AppHomeHero.panelOverlap + 62;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.pageHorizontal,
        safeTop + (compact ? 8 : 10),
        AppSpacing.pageHorizontal,
        bottomPadding,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      focus.status,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.72),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        height: 1.1,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      '家庭看护',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                        height: 1.1,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              _HeroRoundButton(
                icon: Icons.notifications_outlined,
                label: '未处理提醒',
                onTap: () => context.go(AppRoute.alerts.path),
              ),
            ],
          ),
          SizedBox(height: compact ? 34 : 44),
          ConstrainedBox(
            constraints: BoxConstraints(maxWidth: compact ? 248 : 266),
            child: Text(
              focus.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: Colors.white,
                fontFamily: AppTypography.systemFont,
                fontSize: compact ? 24 : 27,
                fontWeight: FontWeight.w900,
                height: compact ? 1.12 : 1.16,
                letterSpacing: 0,
              ),
            ),
          ),
          SizedBox(height: compact ? 6 : 8),
          ConstrainedBox(
            constraints: BoxConstraints(maxWidth: compact ? 260 : 288),
            child: Text(
              focus.detail,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.74),
                fontFamily: AppTypography.systemFont,
                fontSize: compact ? 12.5 : 13,
                fontWeight: FontWeight.w600,
                height: compact ? 1.36 : 1.45,
                letterSpacing: 0,
              ),
            ),
          ),
          SizedBox(height: compact ? 11 : 15),
          Wrap(
            spacing: compact ? 6 : 8,
            runSpacing: compact ? 6 : 8,
            children: chips
                .take(3)
                .map(
                  (chip) => _HeroStatusPill(
                    icon: chip.icon,
                    label: chip.label,
                    tone: chip.tone,
                  ),
                )
                .toList(),
          ),
        ],
      ),
    );
  }
}

class _HeroFocusCopy {
  const _HeroFocusCopy({
    required this.status,
    required this.title,
    required this.detail,
  });

  final String status;
  final String title;
  final String detail;
}

class _HeroChipSpec {
  const _HeroChipSpec({
    required this.icon,
    required this.label,
    required this.tone,
  });

  final IconData icon;
  final String label;
  final StatusTone tone;
}

_HeroFocusCopy _heroFocusCopy({
  required ProfileSummary? profile,
  required bool profileLoading,
  required bool deviceStateLoading,
  required bool hasNoDevice,
  required GuardianTask? currentTask,
  required bool deviceOnline,
  required bool cameraOnline,
  required int pendingCount,
  required int? todayTaskCount,
}) {
  final childName = _childDisplayName(profile);
  if (profileLoading || deviceStateLoading || todayTaskCount == null) {
    return _HeroFocusCopy(
      status: '正在同步家庭状态',
      title: childName == null ? '家庭看护' : '$childName的看护同步中',
      detail: '正在读取今天的任务、设备和看护状态。',
    );
  }
  if (profile?.child == null) {
    return const _HeroFocusCopy(
      status: '孩子资料未创建',
      title: '先添加孩子资料',
      detail: '添加孩子资料后，可以安排任务和看护提醒。',
    );
  }
  if (hasNoDevice) {
    return const _HeroFocusCopy(
      status: '基础设置已完成',
      title: '还没有连接摄像头',
      detail: '连接后可以查看实时画面、看护提醒和设备观察。',
    );
  }
  if (!deviceOnline || !cameraOnline) {
    return const _HeroFocusCopy(
      status: '看护状态需要检查',
      title: '先检查看护设备',
      detail: '任务安排会保留，恢复连接后再同步观察记录。',
    );
  }
  if (pendingCount > 0) {
    return _HeroFocusCopy(
      status: '今天有事项需要确认',
      title: '$pendingCount 件事等你处理',
      detail: '先看证据和奖励，再决定是否写入记录。',
    );
  }
  if (currentTask != null) {
    return _HeroFocusCopy(
      status: '正在看护当前任务',
      title: '${currentTask.title}进行中',
      detail: '完成后再请你确认，不中途打断孩子。',
    );
  }
  if (todayTaskCount == 0) {
    return const _HeroFocusCopy(
      status: '今天安排很轻',
      title: '还没有需要处理的事',
      detail: '需要时再去任务页添加提醒。',
    );
  }
  return _HeroFocusCopy(
    status: '看护数据正在同步',
    title: childName == null ? '看护数据同步中' : '$childName今天有 $todayTaskCount 项安排',
    detail: '任务到点后会自动提醒，晚些时候再请你确认。',
  );
}

List<_HeroChipSpec> _heroChips({
  required ProfileSummary? profile,
  required bool profileLoading,
  required bool deviceStateLoading,
  required bool hasNoDevice,
  required bool deviceOnline,
  required bool cameraOnline,
  required int pendingCount,
  required int? todayTaskCount,
}) {
  final chips = <_HeroChipSpec>[
    if (hasNoDevice)
      const _HeroChipSpec(
        icon: Icons.add_a_photo_outlined,
        label: '待连接',
        tone: StatusTone.neutral,
      )
    else if (deviceStateLoading)
      const _HeroChipSpec(
        icon: Icons.sensors_outlined,
        label: '设备同步中',
        tone: StatusTone.neutral,
      )
    else
      _HeroChipSpec(
        icon: Icons.sensors_outlined,
        label: deviceOnline ? '设备在线' : '设备离线',
        tone: deviceOnline ? StatusTone.success : StatusTone.danger,
      ),
  ];
  if (profileLoading || todayTaskCount == null) {
    chips.add(
      const _HeroChipSpec(
        icon: Icons.sync_outlined,
        label: '资料同步中',
        tone: StatusTone.neutral,
      ),
    );
  } else if (hasNoDevice) {
    chips.add(
      const _HeroChipSpec(
        icon: Icons.videocam_outlined,
        label: '可稍后连接',
        tone: StatusTone.neutral,
      ),
    );
  } else if (!cameraOnline) {
    chips.add(
      const _HeroChipSpec(
        icon: Icons.center_focus_strong_outlined,
        label: '看护降级',
        tone: StatusTone.warning,
      ),
    );
  } else if (pendingCount > 0) {
    chips.add(
      _HeroChipSpec(
        icon: Icons.fact_check_outlined,
        label: '待确认 $pendingCount',
        tone: StatusTone.warning,
      ),
    );
  } else if (todayTaskCount == 0) {
    chips.add(
      const _HeroChipSpec(
        icon: Icons.event_outlined,
        label: '今日未安排',
        tone: StatusTone.neutral,
      ),
    );
  } else {
    chips.add(
      const _HeroChipSpec(
        icon: Icons.sync_outlined,
        label: '任务同步中',
        tone: StatusTone.success,
      ),
    );
  }
  final profileIssue = profileLoading ? null : _profileIssueChip(profile);
  if (profileIssue != null) chips.add(profileIssue);
  return chips;
}

class _HeroStatusPill extends StatelessWidget {
  const _HeroStatusPill({
    required this.icon,
    required this.label,
    required this.tone,
  });

  final IconData icon;
  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width <= 340;
    final color = switch (tone) {
      StatusTone.success => AppColors.success,
      StatusTone.warning => AppColors.warning,
      StatusTone.danger => AppColors.danger,
      StatusTone.neutral => Colors.white,
    };

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.22),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: Colors.white.withValues(alpha: 0.16)),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? 8 : 10,
          vertical: compact ? 5 : 6,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: compact ? 12 : 13),
            SizedBox(width: compact ? 4 : 5),
            Text(
              label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.90),
                fontFamily: AppTypography.systemFont,
                fontSize: compact ? 11 : 11.5,
                fontWeight: FontWeight.w800,
                height: 1,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroRoundButton extends StatelessWidget {
  const _HeroRoundButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return _HomePressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: label,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.20),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
          ),
          child: SizedBox(
            width: AppControls.minTouchTarget,
            height: AppControls.minTouchTarget,
            child: Center(child: Icon(icon, color: Colors.white, size: 19)),
          ),
        ),
      ),
    );
  }
}

class _HomePressable extends StatefulWidget {
  const _HomePressable({required this.child, required this.onTap});

  final Widget child;
  final VoidCallback onTap;

  @override
  State<_HomePressable> createState() => _HomePressableState();
}

class _HomePressableState extends State<_HomePressable> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.of(context).disableAnimations
        ? 1.0
        : (_pressed ? AppMotion.buttonPressScale : 1.0);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onTapDown: (_) => setState(() => _pressed = true),
      onTapCancel: () => setState(() => _pressed = false),
      onTapUp: (_) => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: scale,
        duration: AppMotion.duration(context, 150),
        curve: Curves.easeOutCubic,
        child: widget.child,
      ),
    );
  }
}

class _HomePrioritySection extends StatelessWidget {
  const _HomePrioritySection({
    required this.tasks,
    required this.redemptions,
    required this.deviceOverview,
    required this.cameraHealth,
    required this.cameraStatus,
  });

  final AsyncValue<List<GuardianTask>> tasks;
  final AsyncValue<List<RewardRedemption>> redemptions;
  final AsyncValue<DeviceOverview?> deviceOverview;
  final AsyncValue<CameraHealth> cameraHealth;
  final AsyncValue<CameraStatus> cameraStatus;

  @override
  Widget build(BuildContext context) {
    final taskList = _localTodayTasks(tasks.asData?.value);
    final hasNoDevice =
        deviceOverview.asData?.value == null &&
        !deviceOverview.isLoading &&
        !deviceOverview.hasError;
    if (hasNoDevice) {
      return const _HomeNoDeviceSection();
    }
    if (taskList == null) {
      if (tasks.isLoading) {
        return const _HomeSoftState(title: '正在整理需要处理的事', message: '一会儿就好。');
      }
      return const _HomeSoftState(
        title: '有些内容暂时没更新',
        message: '可以稍后再看。',
        tone: StatusTone.warning,
      );
    }

    final pendingTasks = taskList.where((task) => task.status.awaitsParent);
    final pendingRedemptions = _pendingRedemptions(redemptions);
    final actions = <_PriorityAction>[
      for (final task in pendingTasks)
        _PriorityAction(
          icon: Icons.fact_check_outlined,
          title: '${task.title}待确认',
          detail: task.rewardPoints > 0
              ? '确认后再发放 ${task.rewardPoints} 分'
              : '看一眼记录再确认',
          tone: StatusTone.warning,
          actionLabel: '处理',
          onTap: () => context.go('$taskDetailPath/${task.id}'),
        ),
      for (final redemption in pendingRedemptions)
        _PriorityAction(
          icon: Icons.card_giftcard_outlined,
          title: '${redemption.rewardTitle}待兑现',
          detail: '${redemption.pointsCost} 分 · 需要家长确认',
          tone: StatusTone.warning,
          actionLabel: '确认',
          onTap: () => context.go(rewardsPath),
        ),
    ];

    if (_hasDeviceIssue(deviceOverview, cameraHealth, cameraStatus)) {
      actions.add(
        _PriorityAction(
          icon: Icons.wifi_tethering_error_outlined,
          title: '看护设备需要检查',
          detail: '网络或摄像头状态暂不稳定',
          tone: StatusTone.danger,
          actionLabel: '查看',
          onTap: () => context.go(AppRoute.live.path),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _HomeSectionTitle(
          title: '需要你处理',
          meta: actions.isEmpty ? '0 项' : '${actions.length} 项',
        ),
        const SizedBox(height: 10),
        if (actions.isEmpty)
          const _CalmStatusLine(
            icon: Icons.check_circle_outline,
            title: '今天还没有需要你处理的事',
            detail: '晚些时候再提醒你确认。',
            tone: StatusTone.success,
          )
        else
          _PriorityActionPanel(actions: actions),
      ],
    );
  }
}

class _HomeNoDeviceSection extends StatelessWidget {
  const _HomeNoDeviceSection();

  @override
  Widget build(BuildContext context) {
    return _SoftPanel(
      tone: StatusTone.neutral,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _InsightRow(
            icon: Icons.videocam_outlined,
            title: '还没有连接看护摄像头',
            detail: '连接后可以查看实时画面、看护提醒和设备观察。',
            tone: StatusTone.neutral,
          ),
          const SizedBox(height: 12),
          AppPrimaryButton(
            label: '连接第一台看护摄像头',
            trailing: const AppButtonGlyph(icon: Icons.arrow_forward),
            onTap: () => showAddCameraSheet(context),
          ),
          const SizedBox(height: 8),
          AppSecondaryButton(label: '稍后再说', onTap: () {}),
        ],
      ),
    );
  }
}

class _PriorityAction {
  const _PriorityAction({
    required this.icon,
    required this.title,
    required this.detail,
    required this.tone,
    required this.actionLabel,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String detail;
  final StatusTone tone;
  final String actionLabel;
  final VoidCallback onTap;
}

class _PriorityActionPanel extends StatelessWidget {
  const _PriorityActionPanel({required this.actions});

  final List<_PriorityAction> actions;

  @override
  Widget build(BuildContext context) {
    final visible = actions.take(2).toList();
    return _SoftPanel(
      tone: visible.any((item) => item.tone == StatusTone.danger)
          ? StatusTone.danger
          : StatusTone.warning,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
      child: Column(
        children: [
          for (var index = 0; index < visible.length; index++) ...[
            _PriorityActionRow(action: visible[index]),
            if (index != visible.length - 1)
              Divider(height: 14, color: AppColors.ink.withValues(alpha: 0.06)),
          ],
          if (actions.length > visible.length) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                '还有 ${actions.length - visible.length} 项，进入对应页面处理。',
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  height: 1.35,
                  letterSpacing: 0,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PriorityActionRow extends StatelessWidget {
  const _PriorityActionRow({required this.action});

  final _PriorityAction action;

  @override
  Widget build(BuildContext context) {
    final color = _toneColor(action.tone);
    return _HomePressable(
      onTap: action.onTap,
      child: Semantics(
        button: true,
        label: '${action.title}，${action.actionLabel}',
        child: Row(
          children: [
            _ToneIcon(icon: action.icon, tone: action.tone),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    action.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 15,
                      fontWeight: FontWeight.w900,
                      height: 1.18,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    action.detail,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.25,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Text(
              action.actionLabel,
              style: TextStyle(
                color: color,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _HomeTodaySection extends StatelessWidget {
  const _HomeTodaySection({required this.tasks});

  final AsyncValue<List<GuardianTask>> tasks;

  @override
  Widget build(BuildContext context) {
    final taskList = _localTodayTasks(tasks.asData?.value);
    if (taskList == null) {
      if (tasks.isLoading) {
        return const _HomeSoftState(title: '正在整理今天', message: '稍后显示安排。');
      }
      return const _HomeSoftState(
        title: '今天暂时没更新',
        message: '可以去任务页查看。',
        tone: StatusTone.warning,
      );
    }

    final sorted = [...taskList]..sort(_sortTasksByTime);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _HomeSectionTitle(
          title: '今天',
          meta: taskList.isEmpty ? '未安排' : '${taskList.length} 项安排',
          actionLabel: taskList.isEmpty ? '去安排' : '全部',
          onAction: () => context.go(AppRoute.tasks.path),
        ),
        const SizedBox(height: 10),
        if (sorted.isEmpty)
          _CalmStatusLine(
            icon: Icons.event_note_outlined,
            title: '今天还没有安排任务',
            detail: '需要时再添加提醒。',
            tone: StatusTone.neutral,
            onTap: () => context.go(AppRoute.tasks.path),
          )
        else
          _TodayTimeline(tasks: sorted.take(3).toList()),
      ],
    );
  }
}

class _TodayTimeline extends StatelessWidget {
  const _TodayTimeline({required this.tasks});

  final List<GuardianTask> tasks;

  @override
  Widget build(BuildContext context) {
    return _SoftPanel(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
      child: Column(
        children: [
          for (var index = 0; index < tasks.length; index++) ...[
            _TodayTaskRow(task: tasks[index]),
            if (index != tasks.length - 1)
              Divider(
                height: 16,
                color: AppColors.ink.withValues(alpha: 0.055),
              ),
          ],
        ],
      ),
    );
  }
}

class _TodayTaskRow extends StatelessWidget {
  const _TodayTaskRow({required this.task});

  final GuardianTask task;

  @override
  Widget build(BuildContext context) {
    final statusStyle = _HomeTaskStatusStyle.fromStatus(task.status);
    return _HomePressable(
      onTap: () => context.go('$taskDetailPath/${task.id}'),
      child: Semantics(
        button: true,
        label: '${task.title}，${task.status.label}',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _TodayTaskTimeToken(label: _taskTimeText(task), style: statusStyle),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          task.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.ink,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 15,
                            fontWeight: FontWeight.w900,
                            height: 1.15,
                            letterSpacing: 0,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      _HomeTaskStatusChip(
                        label: task.status.label,
                        style: statusStyle,
                      ),
                    ],
                  ),
                  const SizedBox(height: 5),
                  Text(
                    task.nextStep,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
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
          ],
        ),
      ),
    );
  }
}

class _TodayTaskTimeToken extends StatelessWidget {
  const _TodayTaskTimeToken({required this.label, required this.style});

  final String label;
  final _HomeTaskStatusStyle style;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 54,
      child: Align(
        alignment: Alignment.topLeft,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: style.background,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: style.border),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 5),
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: style.foreground,
                fontFamily: AppTypography.systemFont,
                fontSize: 11.5,
                fontWeight: FontWeight.w800,
                height: 1.15,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeTaskStatusChip extends StatelessWidget {
  const _HomeTaskStatusChip({required this.label, required this.style});

  final String label;
  final _HomeTaskStatusStyle style;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: style.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: style.border),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        child: Text(
          label,
          style: TextStyle(
            color: style.foreground,
            fontFamily: AppTypography.systemFont,
            fontSize: 11.5,
            fontWeight: FontWeight.w700,
            height: 1.1,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _HomeTaskStatusStyle {
  const _HomeTaskStatusStyle({
    required this.foreground,
    required this.background,
    required this.border,
  });

  final Color foreground;
  final Color background;
  final Color border;

  factory _HomeTaskStatusStyle.fromStatus(GuardianTaskStatus status) {
    if (status == GuardianTaskStatus.inProgress) {
      return _HomeTaskStatusStyle(
        foreground: AppColors.brandDeep,
        background: AppColors.brandWash.withValues(alpha: 0.92),
        border: AppColors.brand.withValues(alpha: 0.14),
      );
    }
    if (status == GuardianTaskStatus.completed ||
        status == GuardianTaskStatus.confirmed) {
      return _HomeTaskStatusStyle(
        foreground: AppColors.success,
        background: AppColors.successWash.withValues(alpha: 0.86),
        border: AppColors.success.withValues(alpha: 0.12),
      );
    }
    return _HomeTaskStatusStyle.fromTone(status.tone);
  }

  factory _HomeTaskStatusStyle.fromTone(StatusTone tone) {
    final foreground = tone == StatusTone.neutral
        ? AppColors.muted
        : _toneColor(tone);
    final background = tone == StatusTone.neutral
        ? AppColors.surfaceStrong.withValues(alpha: 0.68)
        : _toneWash(tone).withValues(alpha: 0.74);
    final border = foreground.withValues(
      alpha: tone == StatusTone.neutral ? 0.10 : 0.12,
    );
    return _HomeTaskStatusStyle(
      foreground: foreground,
      background: background,
      border: border,
    );
  }
}

class _HomeConfirmRewardSection extends StatelessWidget {
  const _HomeConfirmRewardSection({
    required this.tasks,
    required this.points,
    required this.redemptions,
  });

  final AsyncValue<List<GuardianTask>> tasks;
  final AsyncValue<PointsSummary> points;
  final AsyncValue<List<RewardRedemption>> redemptions;

  @override
  Widget build(BuildContext context) {
    final pendingTasks =
        _localTodayTasks(
          tasks.asData?.value,
        )?.where((task) => task.status.awaitsParent).length ??
        0;
    final pendingRewards = _pendingRedemptions(redemptions).length;
    final balance = points.asData?.value.account.balance;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _HomeSectionTitle(title: '确认与奖励', meta: ''),
        const SizedBox(height: 10),
        _SoftPanel(
          tone: StatusTone.neutral,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
          child: Row(
            children: [
              Expanded(
                child: _SummaryMetric(
                  value: '${pendingTasks + pendingRewards}',
                  label: '待确认',
                  tone: pendingTasks + pendingRewards > 0
                      ? StatusTone.warning
                      : StatusTone.neutral,
                  onTap: () => context.go(AppRoute.tasks.path),
                ),
              ),
              _MetricDivider(),
              Expanded(
                child: _SummaryMetric(
                  value: balance == null ? '--' : '$balance',
                  label: '积分',
                  tone: StatusTone.warning,
                  onTap: () => context.go(pointsPath),
                ),
              ),
              _MetricDivider(),
              Expanded(
                child: _SummaryMetric(
                  value: '$pendingRewards',
                  label: '待兑现',
                  tone: pendingRewards > 0
                      ? StatusTone.warning
                      : StatusTone.neutral,
                  onTap: () => context.go(rewardsPath),
                ),
              ),
            ],
          ),
        ),
        if (points.hasError) ...[
          const SizedBox(height: 8),
          const Text(
            '积分稍后再更新，任务和看护可以继续使用。',
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
      ],
    );
  }
}

class _HomeCareInsightSection extends StatelessWidget {
  const _HomeCareInsightSection({
    required this.deviceOverview,
    required this.cameraHealth,
    required this.cameraStatus,
    required this.todayTasks,
  });

  final AsyncValue<DeviceOverview?> deviceOverview;
  final AsyncValue<CameraHealth> cameraHealth;
  final AsyncValue<CameraStatus> cameraStatus;
  final AsyncValue<List<GuardianTask>> todayTasks;

  @override
  Widget build(BuildContext context) {
    final overview = deviceOverview.asData?.value;
    final hasNoDevice =
        overview == null &&
        !deviceOverview.isLoading &&
        !deviceOverview.hasError;
    final health = cameraHealth.asData?.value;
    final camera = cameraStatus.asData?.value;
    final deviceOnline = hasNoDevice
        ? false
        : overview?.isOnline ?? camera?.isOnline ?? false;
    final cameraOnline = hasNoDevice
        ? false
        : camera?.isOnline ?? health?.reachable ?? false;
    final localTodayTasks = _localTodayTasks(todayTasks.asData?.value);
    final currentTask =
        camera?.currentTask ?? _currentTaskFromToday(localTodayTasks);
    final hasIssue =
        (!hasNoDevice && (!deviceOnline || !cameraOnline)) ||
        deviceOverview.hasError ||
        cameraHealth.hasError ||
        cameraStatus.hasError;
    final statusTitle = hasNoDevice
        ? '等待连接摄像头'
        : hasIssue
        ? '看护状态需要检查'
        : currentTask != null
        ? '${currentTask.title}观察中'
        : '看护状态稳定';
    final statusDetail = hasNoDevice
        ? '连接后可以查看实时画面和看护提醒。'
        : hasIssue
        ? '网络或摄像头暂不稳定，先保留今天的安排。'
        : currentTask?.nextStep ?? '任务到点后会自动提醒，隐私灯保持可见。';
    final advice = _homeAdviceFromRealData(
      currentTask: currentTask,
      tasks: localTodayTasks,
      loading: todayTasks.isLoading,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _HomeSectionTitle(
          title: '看护与建议',
          meta: hasNoDevice
              ? '待连接'
              : hasIssue
              ? '需留意'
              : '正常',
        ),
        const SizedBox(height: 10),
        _SoftPanel(
          tone: hasNoDevice
              ? StatusTone.neutral
              : hasIssue
              ? StatusTone.warning
              : StatusTone.success,
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          child: Column(
            children: [
              _InsightRow(
                icon: hasNoDevice
                    ? Icons.videocam_outlined
                    : hasIssue
                    ? Icons.sensors_off_outlined
                    : Icons.center_focus_strong_outlined,
                title: statusTitle,
                detail: statusDetail,
                tone: hasNoDevice
                    ? StatusTone.neutral
                    : hasIssue
                    ? StatusTone.warning
                    : StatusTone.success,
                onTap: () => hasNoDevice
                    ? showAddCameraSheet(context)
                    : context.go(AppRoute.live.path),
              ),
              Divider(
                height: 18,
                color: AppColors.ink.withValues(alpha: 0.055),
              ),
              _InsightRow(
                icon: Icons.auto_awesome_outlined,
                title: 'AI 观察建议',
                detail: advice,
                tone: StatusTone.neutral,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _HomeSectionTitle extends StatelessWidget {
  const _HomeSectionTitle({
    required this.title,
    required this.meta,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String meta;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Row(
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                  height: 1.14,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(width: 9),
              Text(
                meta,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.subtle,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  height: 1.2,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
        if (actionLabel != null && onAction != null)
          _TextAction(label: actionLabel!, onTap: onAction!),
      ],
    );
  }
}

class _TextAction extends StatelessWidget {
  const _TextAction({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return _HomePressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: label,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Text(
            label,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

class _CalmStatusLine extends StatelessWidget {
  const _CalmStatusLine({
    required this.icon,
    required this.title,
    required this.detail,
    required this.tone,
    this.onTap,
  });

  final IconData icon;
  final String title;
  final String detail;
  final StatusTone tone;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final content = _SoftPanel(
      tone: tone,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      child: Row(
        children: [
          _ToneIcon(icon: icon, tone: tone),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    height: 1.18,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  detail,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    height: 1.25,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
    if (onTap == null) return content;
    return _HomePressable(
      onTap: onTap!,
      child: Semantics(button: true, label: title, child: content),
    );
  }
}

class _SoftPanel extends StatelessWidget {
  const _SoftPanel({
    required this.child,
    this.tone = StatusTone.neutral,
    this.padding = const EdgeInsets.all(14),
  });

  final Widget child;
  final StatusTone tone;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _toneWash(tone),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _toneColor(tone).withValues(alpha: 0.10)),
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

class _ToneIcon extends StatelessWidget {
  const _ToneIcon({required this.icon, required this.tone});

  final IconData icon;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final color = _toneColor(tone);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(13),
      ),
      child: SizedBox(
        width: 38,
        height: 38,
        child: Center(child: Icon(icon, color: color, size: 19)),
      ),
    );
  }
}

class _SummaryMetric extends StatelessWidget {
  const _SummaryMetric({
    required this.value,
    required this.label,
    required this.tone,
    required this.onTap,
  });

  final String value;
  final String label;
  final StatusTone tone;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return _HomePressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: '$label $value',
        child: SizedBox(
          height: 58,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: _toneColor(tone),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 22,
                  fontWeight: FontWeight.w900,
                  height: 1,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  height: 1,
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

class _MetricDivider extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: 42,
      color: AppColors.ink.withValues(alpha: 0.055),
    );
  }
}

class _InsightRow extends StatelessWidget {
  const _InsightRow({
    required this.icon,
    required this.title,
    required this.detail,
    required this.tone,
    this.onTap,
  });

  final IconData icon;
  final String title;
  final String detail;
  final StatusTone tone;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final row = Row(
      children: [
        _ToneIcon(icon: icon, tone: tone),
        const SizedBox(width: 11),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14.5,
                  fontWeight: FontWeight.w900,
                  height: 1.18,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                detail,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
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
      ],
    );
    if (onTap == null) return row;
    return _HomePressable(
      onTap: onTap!,
      child: Semantics(button: true, label: title, child: row),
    );
  }
}

class _HomeSoftState extends StatelessWidget {
  const _HomeSoftState({
    required this.title,
    required this.message,
    this.tone = StatusTone.neutral,
  });

  final String title;
  final String message;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    return _SoftPanel(
      tone: tone,
      child: Row(
        children: [
          _ToneIcon(icon: Icons.hourglass_empty_outlined, tone: tone),
          const SizedBox(width: 11),
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
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  message,
                  style: const TextStyle(
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
        ],
      ),
    );
  }
}

List<RewardRedemption> _pendingRedemptions(
  AsyncValue<List<RewardRedemption>> redemptions,
) {
  return redemptions.asData?.value
          .where((item) => item.status == RedemptionStatus.redeemed)
          .toList() ??
      const [];
}

int _pendingActionCount(
  List<GuardianTask>? tasks,
  AsyncValue<List<RewardRedemption>> redemptions,
) {
  final taskCount =
      tasks?.where((task) => task.status.awaitsParent).length ?? 0;
  return taskCount + _pendingRedemptions(redemptions).length;
}

bool _hasDeviceIssue(
  AsyncValue<DeviceOverview?> deviceOverview,
  AsyncValue<CameraHealth> cameraHealth,
  AsyncValue<CameraStatus> cameraStatus,
) {
  final overview = deviceOverview.asData?.value;
  if (overview == null &&
      !deviceOverview.isLoading &&
      !deviceOverview.hasError) {
    return false;
  }
  final health = cameraHealth.asData?.value;
  final camera = cameraStatus.asData?.value;
  return deviceOverview.hasError ||
      cameraHealth.hasError ||
      cameraStatus.hasError ||
      (overview != null && !overview.isOnline) ||
      (health != null && !health.reachable) ||
      (camera != null && !camera.isOnline);
}

GuardianTask? _currentTaskFromToday(List<GuardianTask>? tasks) {
  if (tasks == null || tasks.isEmpty) return null;
  for (final task in tasks) {
    if (task.status == GuardianTaskStatus.inProgress) return task;
  }
  for (final task in tasks) {
    if (task.status == GuardianTaskStatus.reminderSent ||
        task.status == GuardianTaskStatus.delayed) {
      return task;
    }
  }
  return null;
}

List<GuardianTask>? _localTodayTasks(List<GuardianTask>? tasks) {
  if (tasks == null) return null;
  final today = _homeDateText(DateTime.now());
  return tasks.where((task) => task.scheduledDate == today).toList();
}

String _homeDateText(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}

String? _childDisplayName(ProfileSummary? profile) {
  final child = profile?.child;
  if (child == null) return null;
  if (child.nickname.trim().isNotEmpty) return child.nickname.trim();
  if (child.name.trim().isNotEmpty) return child.name.trim();
  return null;
}

_HeroChipSpec? _profileIssueChip(ProfileSummary? profile) {
  if (profile == null) return null;
  final child = profile.child;
  if (child == null) {
    return const _HeroChipSpec(
      icon: Icons.person_add_alt_1_outlined,
      label: '待添加孩子',
      tone: StatusTone.warning,
    );
  }
  if (child.educationStage.trim().isEmpty && child.grade.trim().isEmpty) {
    return const _HeroChipSpec(
      icon: Icons.school_outlined,
      label: '阶段待补充',
      tone: StatusTone.warning,
    );
  }
  if (profile.deviceCount <= 0) {
    return const _HeroChipSpec(
      icon: Icons.sensors_off_outlined,
      label: '待绑定设备',
      tone: StatusTone.warning,
    );
  }
  return null;
}

String _homeAdviceFromRealData({
  required GuardianTask? currentTask,
  required List<GuardianTask>? tasks,
  required bool loading,
}) {
  if (loading && tasks == null) return '正在同步观察建议。';
  final candidates = <GuardianTask>[?currentTask, ...?tasks];
  for (final task in candidates) {
    final text = _taskAdviceCandidate(task);
    if (text.isNotEmpty) return _compactHomeText(text);
  }
  if (tasks == null) return '观察建议稍后更新。';
  if (tasks.isEmpty) return '今天还没有新的观察建议。';
  return '任务到点后会自动记录观察结果。';
}

String _taskAdviceCandidate(GuardianTask task) {
  if (task.aiObservationSummary.trim().isNotEmpty) {
    return task.aiObservationSummary.trim();
  }
  if (task.status == GuardianTaskStatus.inProgress &&
      task.nextStep.trim().isNotEmpty) {
    return task.nextStep.trim();
  }
  if ((task.status.awaitsParent || task.status.isDone) &&
      task.evidenceSummary.trim().isNotEmpty) {
    return task.evidenceSummary.trim();
  }
  return '';
}

String _compactHomeText(String text) {
  final trimmed = text.trim();
  return trimmed.length > 42 ? '${trimmed.substring(0, 42)}…' : trimmed;
}

String _taskTimeText(GuardianTask task) {
  if (task.scheduledStart.isNotEmpty) return task.scheduledStart;
  if (task.scheduledEnd.isNotEmpty) return task.scheduledEnd;
  return '今天';
}

int _sortTasksByTime(GuardianTask a, GuardianTask b) {
  return _taskTimeText(a).compareTo(_taskTimeText(b));
}

Color _toneColor(StatusTone tone) {
  return switch (tone) {
    StatusTone.success => AppColors.success,
    StatusTone.warning => AppColors.warning,
    StatusTone.danger => AppColors.danger,
    StatusTone.neutral => AppColors.ink,
  };
}

Color _toneWash(StatusTone tone) {
  return switch (tone) {
    StatusTone.success => AppColors.successWash.withValues(alpha: 0.78),
    StatusTone.warning => AppColors.warningWash.withValues(alpha: 0.74),
    StatusTone.danger => AppColors.dangerWash.withValues(alpha: 0.72),
    StatusTone.neutral => AppColors.surfaceTinted,
  };
}
