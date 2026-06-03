import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/devices/application/device_repository.dart';
import 'package:mira_guardian_app/src/features/devices/domain/device_models.dart';
import 'package:mira_guardian_app/src/features/live_care/application/camera_repository.dart';
import 'package:mira_guardian_app/src/features/live_care/domain/camera_models.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/features/mvp/domain/mvp_models.dart';
import 'package:mira_guardian_app/src/features/points/application/point_repository.dart';
import 'package:mira_guardian_app/src/features/points/domain/point_models.dart';
import 'package:mira_guardian_app/src/features/rewards/application/reward_repository.dart';
import 'package:mira_guardian_app/src/features/rewards/domain/reward_models.dart';
import 'package:mira_guardian_app/src/features/tasks/application/task_repository.dart';
import 'package:mira_guardian_app/src/features/tasks/domain/task_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final todayTasks = ref.watch(todayTasksProvider);
    final redemptions = ref.watch(rewardRedemptionsProvider);
    final points = ref.watch(pointsSummaryProvider);
    final deviceOverview = ref.watch(primaryDeviceOverviewProvider);
    final cameraHealth = ref.watch(cameraHealthProvider);
    final deviceStatus = _deviceStatusLabel(snapshot, deviceOverview);

    return MiraScreen(
      title: 'Mira Guardian',
      subtitle: deviceStatus,
      headerContent: _HomeBrandHeader(deviceStatus: deviceStatus),
      trailing: MiraIconButton(
        icon: Icons.notifications_outlined,
        label: '未处理提醒',
        onTap: () => context.go(AppRoute.alerts.path),
      ),
      children: [
        _CurrentStatePanel(
          snapshot: snapshot,
          deviceOverview: deviceOverview,
          cameraHealth: cameraHealth,
        ),
        const SizedBox(height: 14),
        _PendingQueue(tasks: todayTasks, redemptions: redemptions),
        const SizedBox(height: 14),
        _TodayPlan(tasks: todayTasks),
        const SizedBox(height: 14),
        _PointsRewardsPanel(points: points, redemptions: redemptions),
        const SizedBox(height: 14),
        _AiAdvicePanel(snapshot: snapshot),
        const SizedBox(height: 14),
        _DeviceSummaryPanel(
          snapshot: snapshot,
          deviceOverview: deviceOverview,
          cameraHealth: cameraHealth,
        ),
      ],
    );
  }

  String _deviceStatusLabel(
    GuardianMvpSnapshot snapshot,
    AsyncValue<DeviceOverview?> overview,
  ) {
    final device = overview.asData?.value;
    if (device != null) {
      final careState = device.isOnline ? '在线看护中' : '设备离线';
      return '${device.device.displayName} · $careState';
    }
    if (overview.isLoading) return '${snapshot.device.name} · 状态同步中';
    if (overview.hasError) return '${snapshot.device.name} · 暂未更新';
    final fallback = snapshot.device.online ? '在线看护中' : '设备离线';
    return '${snapshot.device.name} · $fallback';
  }
}

class _HomeBrandHeader extends StatelessWidget {
  const _HomeBrandHeader({required this.deviceStatus});

  final String deviceStatus;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.ink,
            borderRadius: BorderRadius.circular(13),
            boxShadow: [
              BoxShadow(
                color: AppColors.primaryButtonShadow.withValues(alpha: 0.10),
                blurRadius: 16,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: const SizedBox(
            width: 38,
            height: 38,
            child: Center(
              child: Icon(
                Icons.center_focus_strong_outlined,
                color: Colors.white,
                size: 19,
              ),
            ),
          ),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Mira Guardian',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                  height: 1.1,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                deviceStatus,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _CurrentStatePanel extends StatelessWidget {
  const _CurrentStatePanel({
    required this.snapshot,
    required this.deviceOverview,
    required this.cameraHealth,
  });

  final GuardianMvpSnapshot snapshot;
  final AsyncValue<DeviceOverview?> deviceOverview;
  final AsyncValue<CameraHealth> cameraHealth;

  @override
  Widget build(BuildContext context) {
    final overview = deviceOverview.asData?.value;
    final health = cameraHealth.asData?.value;
    final deviceOnline = overview?.isOnline ?? snapshot.device.online;
    final cameraOnline = health?.reachable ?? snapshot.device.cameraEnabled;

    return MiraSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 17),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              StatusChip(
                label: deviceOnline ? '设备在线' : '设备离线',
                tone: deviceOnline ? StatusTone.success : StatusTone.danger,
              ),
              const SizedBox(width: 8),
              StatusChip(
                label: cameraOnline ? '摄像头可达' : '看护降级',
                tone: cameraOnline ? StatusTone.success : StatusTone.warning,
              ),
            ],
          ),
          const SizedBox(height: 20),
          Text(
            '${snapshot.child.currentState}。',
            style: const TextStyle(
              color: Colors.white,
              fontFamily: AppTypography.systemFont,
              fontSize: 25,
              fontWeight: FontWeight.w800,
              height: 1.18,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 9),
          Text(
            snapshot.nextAction,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.72),
              fontFamily: AppTypography.systemFont,
              fontSize: 14,
              fontWeight: FontWeight.w600,
              height: 1.55,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              _StateMetric(
                label: '安全',
                value: cameraOnline ? '正常' : '降级',
                color: const Color(0xFF6EE7B7),
              ),
              const SizedBox(width: 8),
              _StateMetric(
                label: '下一步',
                value: '12m',
                color: const Color(0xFF93C5FD),
              ),
              const SizedBox(width: 8),
              _StateMetric(
                label: '待处理',
                value: '${snapshot.pendingItems.length}',
                color: const Color(0xFFFDBA74),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StateMetric extends StatelessWidget {
  const _StateMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 11),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: TextStyle(
                  color: color,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  height: 1,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                label,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.62),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
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

class _PendingQueue extends StatelessWidget {
  const _PendingQueue({required this.tasks, required this.redemptions});

  final AsyncValue<List<GuardianTask>> tasks;
  final AsyncValue<List<RewardRedemption>> redemptions;

  @override
  Widget build(BuildContext context) {
    return tasks.when(
      data: (taskList) {
        final pendingTasks = taskList.where((task) => task.status.awaitsParent);
        final redemptionList = redemptions.asData?.value ?? const [];
        final pendingRedemptions = redemptionList.where(
          (redemption) => redemption.status == RedemptionStatus.redeemed,
        );
        final total = pendingTasks.length + pendingRedemptions.length;

        return MiraSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _SectionHeader(title: '需要你处理', action: '$total 项'),
              const SizedBox(height: 8),
              if (total == 0)
                const Text(
                  '暂无待确认任务或待兑现奖励。',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    height: 1.55,
                    letterSpacing: 0,
                  ),
                ),
              for (final task in pendingTasks)
                MiraListRow(
                  icon: Icons.fact_check_outlined,
                  title: '${task.title} 等待确认',
                  subtitle: '${task.evidenceText} · +${task.rewardPoints} 分',
                  tone: MiraListRowTone.amber,
                  trailing: _HeaderAction(
                    label: '处理',
                    onTap: () => context.go('$taskDetailPath/${task.id}'),
                  ),
                ),
              for (final redemption in pendingRedemptions)
                MiraListRow(
                  icon: Icons.card_giftcard_outlined,
                  title: '奖励待兑现',
                  subtitle:
                      '${redemption.rewardTitle} · ${redemption.pointsCost} 分',
                  tone: MiraListRowTone.blue,
                  trailing: _HeaderAction(
                    label: '确认',
                    onTap: () => context.go(rewardsPath),
                  ),
                ),
            ],
          ),
        );
      },
      loading: () => const _HomeLoadingPanel(title: '需要你处理'),
      error: (error, _) =>
          _HomeErrorPanel(title: '需要你处理', message: '待处理事项同步失败，请稍后重试。'),
    );
  }
}

class _TodayPlan extends StatelessWidget {
  const _TodayPlan({required this.tasks});

  final AsyncValue<List<GuardianTask>> tasks;

  @override
  Widget build(BuildContext context) {
    return tasks.when(
      data: (taskList) => MiraSurface(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SectionHeader(
              title: '今日任务摘要',
              action: '查看全部',
              onAction: () => context.go(AppRoute.tasks.path),
            ),
            const SizedBox(height: 10),
            if (taskList.isEmpty)
              const Text(
                '今天暂无任务，可以先让安排轻一点，或去任务页添加新的提醒。',
                style: TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  height: 1.55,
                  letterSpacing: 0,
                ),
              ),
            for (final task in taskList.take(3))
              MiraListRow(
                icon: task.status == GuardianTaskStatus.inProgress
                    ? Icons.play_circle_outline
                    : Icons.check_circle_outline,
                title: task.title,
                subtitle: '${task.timeLabel} · ${task.nextStep}',
                tone: task.status == GuardianTaskStatus.inProgress
                    ? MiraListRowTone.blue
                    : MiraListRowTone.neutral,
                trailing: StatusChip(
                  label: task.status.label,
                  tone: task.status.tone,
                ),
                onTap: () => context.go('$taskDetailPath/${task.id}'),
              ),
          ],
        ),
      ),
      loading: () => const _HomeLoadingPanel(title: '今日任务摘要'),
      error: (error, _) =>
          _HomeErrorPanel(title: '今日任务摘要', message: '今日任务同步失败，请稍后重试。'),
    );
  }
}

class _PointsRewardsPanel extends StatelessWidget {
  const _PointsRewardsPanel({required this.points, required this.redemptions});

  final AsyncValue<PointsSummary> points;
  final AsyncValue<List<RewardRedemption>> redemptions;

  @override
  Widget build(BuildContext context) {
    final summary = points.asData?.value;
    final pending =
        redemptions.asData?.value
            .where((item) => item.status == RedemptionStatus.redeemed)
            .length ??
        0;

    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader(
            title: '积分与奖励',
            action: points.isLoading ? '同步中' : '查看',
            onAction: () => context.go(pointsPath),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _CompactEntry(
                  icon: Icons.stars_outlined,
                  title: summary == null ? '--' : '${summary.account.balance}',
                  subtitle: '当前积分',
                  tone: MiraListRowTone.amber,
                  onTap: () => context.go(pointsPath),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _CompactEntry(
                  icon: Icons.card_giftcard_outlined,
                  title: '$pending',
                  subtitle: '待兑现奖励',
                  tone: MiraListRowTone.blue,
                  onTap: () => context.go(rewardsPath),
                ),
              ),
            ],
          ),
          if (points.hasError) ...[
            const SizedBox(height: 10),
            const Text(
              '积分暂时没有更新，任务和看护功能仍可继续使用。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                height: 1.45,
                letterSpacing: 0,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CompactEntry extends StatelessWidget {
  const _CompactEntry({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.tone,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final MiraListRowTone tone;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = switch (tone) {
      MiraListRowTone.blue => AppColors.brand,
      MiraListRowTone.green => const Color(0xFF2F8F68),
      MiraListRowTone.amber => const Color(0xFFD8922B),
      MiraListRowTone.red => const Color(0xFFB64A4A),
      MiraListRowTone.neutral => AppColors.ink,
    };

    return MiraSurface(
      radius: 15,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 11),
      color: color.withValues(alpha: 0.07),
      borderColor: color.withValues(alpha: 0.10),
      onTap: onTap,
      child: Row(
        children: [
          Icon(icon, color: color, size: 19),
          const SizedBox(width: 9),
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
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    height: 1,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
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

class _AiAdvicePanel extends StatelessWidget {
  const _AiAdvicePanel({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      color: AppColors.brand.withValues(alpha: 0.08),
      borderColor: AppColors.brand.withValues(alpha: 0.12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.auto_awesome_outlined,
            color: AppColors.brand,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '观察建议',
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  snapshot.aiSummary,
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
          ),
        ],
      ),
    );
  }
}

class _DeviceSummaryPanel extends StatelessWidget {
  const _DeviceSummaryPanel({
    required this.snapshot,
    required this.deviceOverview,
    required this.cameraHealth,
  });

  final GuardianMvpSnapshot snapshot;
  final AsyncValue<DeviceOverview?> deviceOverview;
  final AsyncValue<CameraHealth> cameraHealth;

  @override
  Widget build(BuildContext context) {
    final overview = deviceOverview.asData?.value;
    final health = cameraHealth.asData?.value;
    final title = overview?.device.displayName ?? snapshot.device.name;
    final subtitle =
        overview?.subtitle ??
        '${snapshot.device.room} · ${snapshot.device.networkLabel}';
    final statusLabel =
        overview?.connectionLabel ?? snapshot.device.connectionLabel;
    final statusTone =
        overview?.tone ??
        (snapshot.device.online ? StatusTone.success : StatusTone.danger);
    final rowTone = (overview?.isOnline ?? snapshot.device.online)
        ? MiraListRowTone.green
        : MiraListRowTone.red;

    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader(
            title: '设备摘要',
            action: '看护',
            onAction: () => context.go(AppRoute.live.path),
          ),
          const SizedBox(height: 10),
          MiraListRow(
            icon: Icons.videocam_outlined,
            title: title,
            subtitle: subtitle,
            tone: rowTone,
            trailing: StatusChip(label: statusLabel, tone: statusTone),
            onTap: () => context.go(AppRoute.live.path),
          ),
          if (health != null && !health.reachable) ...[
            const SizedBox(height: 8),
            const Text(
              '摄像头暂时不在线，首页已切换为降级状态。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                height: 1.45,
                letterSpacing: 0,
              ),
            ),
          ],
          if (deviceOverview.hasError) ...[
            const SizedBox(height: 8),
            const Text(
              '设备状态暂时没有更新，仍可进入看护页查看最新情况。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                height: 1.45,
                letterSpacing: 0,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.title,
    required this.action,
    this.onAction,
  });

  final String title;
  final String action;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ),
        _HeaderAction(label: action, onTap: onAction),
      ],
    );
  }
}

class _HeaderAction extends StatelessWidget {
  const _HeaderAction({required this.label, this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Opacity(
        opacity: enabled ? 1 : 0.62,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: enabled
                ? Colors.white.withValues(alpha: 0.74)
                : Colors.white.withValues(alpha: 0.42),
            borderRadius: BorderRadius.circular(AppRadii.full),
            border: Border.all(color: AppColors.ink.withValues(alpha: 0.05)),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
            child: Text(
              label,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeLoadingPanel extends StatelessWidget {
  const _HomeLoadingPanel({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final loadingTitle = switch (title) {
      '需要你处理' => '正在整理待处理事项',
      '今日任务摘要' => '正在整理今日任务',
      _ => '正在同步最新内容',
    };

    return MiraLoadingState(
      title: loadingTitle,
      message: '正在整理最新的家庭看护信息。',
      compact: true,
    );
  }
}

class _HomeErrorPanel extends StatelessWidget {
  const _HomeErrorPanel({required this.title, required this.message});

  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return MiraInlineState(
      variant: MiraStateVariant.serviceUnavailable,
      title: '$title暂时没有更新',
      message: message,
    );
  }
}
