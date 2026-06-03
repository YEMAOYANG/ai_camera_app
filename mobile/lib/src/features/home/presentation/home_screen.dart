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

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final deviceCareState = snapshot.device.online ? '在线看护中' : '设备离线';

    return MiraScreen(
      title: 'Mira Guardian',
      subtitle: '${snapshot.device.name} · $deviceCareState',
      headerContent: _HomeBrandHeader(
        deviceStatus: '${snapshot.device.name} · $deviceCareState',
      ),
      trailing: MiraIconButton(
        icon: Icons.notifications_outlined,
        label: '未处理提醒',
        onTap: () => context.go(AppRoute.alerts.path),
      ),
      children: [
        _CurrentStatePanel(snapshot: snapshot),
        const SizedBox(height: 14),
        _PendingQueue(snapshot: snapshot),
        const SizedBox(height: 14),
        _TodayPlan(snapshot: snapshot),
        const SizedBox(height: 14),
        _AiAdvicePanel(snapshot: snapshot),
        const SizedBox(height: 14),
        _DeviceSummaryPanel(snapshot: snapshot),
      ],
    );
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
  const _CurrentStatePanel({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
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
                label: snapshot.device.online ? '设备在线' : '设备离线',
                tone: snapshot.device.online
                    ? StatusTone.success
                    : StatusTone.danger,
              ),
              const SizedBox(width: 8),
              StatusChip(
                label: snapshot.device.privacyLightOn ? '隐私灯亮起' : '隐私待确认',
                tone: snapshot.device.privacyLightOn
                    ? StatusTone.neutral
                    : StatusTone.warning,
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
                value: '正常',
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
  const _PendingQueue({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader(
            title: '需要你处理',
            action: '${snapshot.pendingItems.length} 项',
          ),
          const SizedBox(height: 8),
          for (final item in snapshot.pendingItems)
            MiraListRow(
              icon: item.taskId == null
                  ? Icons.card_giftcard_outlined
                  : Icons.fact_check_outlined,
              title: item.title,
              subtitle: item.detail,
              tone: item.tone == StatusTone.warning
                  ? MiraListRowTone.amber
                  : MiraListRowTone.blue,
              trailing: TextButton(
                onPressed: () {
                  if (item.taskId != null) {
                    context.go('$taskDetailPath/${item.taskId}');
                    return;
                  }
                  _showToast(context, '奖励申请已进入确认队列');
                },
                child: Text(item.actionLabel),
              ),
            ),
        ],
      ),
    );
  }
}

class _TodayPlan extends StatelessWidget {
  const _TodayPlan({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SectionHeader(
            title: '今日计划',
            action: '查看全部',
            onAction: () => context.go(AppRoute.tasks.path),
          ),
          const SizedBox(height: 10),
          for (final task in snapshot.tasks.take(3))
            MiraListRow(
              icon: task.status == MvpTaskStatus.running
                  ? Icons.play_circle_outline
                  : Icons.check_circle_outline,
              title: task.title,
              subtitle: '${task.timeLabel} · ${task.nextStep}',
              tone: task.status == MvpTaskStatus.running
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
                  'AI 判断建议',
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
  const _DeviceSummaryPanel({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
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
            title: snapshot.device.name,
            subtitle:
                '${snapshot.device.room} · ${snapshot.device.networkLabel}',
            tone: snapshot.device.online
                ? MiraListRowTone.green
                : MiraListRowTone.red,
            trailing: StatusChip(
              label: snapshot.device.connectionLabel,
              tone: snapshot.device.online
                  ? StatusTone.success
                  : StatusTone.danger,
            ),
          ),
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
        TextButton(onPressed: onAction, child: Text(action)),
      ],
    );
  }
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
