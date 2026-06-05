import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/domain/camera_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_page_header.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class LiveCareScreen extends ConsumerWidget {
  const LiveCareScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final deviceOverview = ref.watch(primaryDeviceOverviewProvider);
    final liveStatus = ref.watch(liveCareStatusProvider);
    final snapshotFrame = ref.watch(cameraSnapshotProvider);
    final titleDevice = deviceOverview.asData?.value?.device;
    final subtitle = titleDevice == null
        ? deviceOverview.isLoading
              ? '设备状态同步中'
              : '尚未绑定看护设备'
        : '${titleDevice.displayLocation} · ${titleDevice.displayName}';

    return AppScreen(
      title: '实时看护',
      fixedHeader: false,
      showHeader: false,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.pageHorizontal,
        8,
        AppSpacing.pageHorizontal,
        AppSpacing.pageBottom,
      ),
      children: [
        _LiveCareHero(
          title: '实时看护',
          subtitle: subtitle,
          status: liveStatus,
          snapshot: snapshotFrame,
          onRefresh: () => _refreshLiveCare(ref),
        ),
        const SizedBox(height: AppSpacing.pageSectionGap),
        _LiveActions(
          status: liveStatus,
          snapshot: snapshotFrame,
          onRefresh: () => _refreshLiveCare(ref),
        ),
        const SizedBox(height: AppSpacing.pageSectionGap),
        _CareFocusPanel(status: liveStatus),
      ],
    );
  }

  void _refreshLiveCare(WidgetRef ref) {
    ref
      ..invalidate(liveCareStatusProvider)
      ..invalidate(cameraHealthProvider)
      ..invalidate(cameraRuntimeProvider)
      ..invalidate(cameraStatusProvider)
      ..invalidate(cameraMonitorStatusProvider)
      ..invalidate(cameraSnapshotProvider)
      ..invalidate(primaryDeviceOverviewProvider);
  }
}

class _LiveCareHero extends StatelessWidget {
  const _LiveCareHero({
    required this.title,
    required this.subtitle,
    required this.status,
    required this.snapshot,
    required this.onRefresh,
  });

  final String title;
  final String subtitle;
  final AsyncValue<LiveCareStatus> status;
  final AsyncValue<CameraSnapshotFrame> snapshot;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final label = status.isLoading ? '正在连接' : care?.label ?? '状态同步中';
    final tone = status.isLoading
        ? StatusTone.warning
        : care?.tone ?? StatusTone.neutral;
    final currentTask = care?.currentTask;

    return AppHeroPanel(
      dark: true,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.66),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 26,
                        fontWeight: FontWeight.w900,
                        height: 1.08,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              StatusChip(label: label, tone: tone),
            ],
          ),
          const SizedBox(height: 13),
          _LiveViewport(
            status: status,
            snapshot: snapshot,
            onRefresh: onRefresh,
          ),
          const SizedBox(height: 12),
          Text(
            currentTask == null
                ? '摄像头只在需要时提醒，普通状态不打扰孩子。'
                : '${currentTask.title} · ${currentTask.nextStep}',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.68),
              fontFamily: AppTypography.systemFont,
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              height: 1.45,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _LiveViewport extends StatelessWidget {
  const _LiveViewport({
    required this.status,
    required this.snapshot,
    required this.onRefresh,
  });

  final AsyncValue<LiveCareStatus> status;
  final AsyncValue<CameraSnapshotFrame> snapshot;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final frame = snapshot.asData?.value;
    final available = care?.isAvailable ?? false;

    if (status.isLoading) {
      return const _ViewportPlaceholder(
        icon: Icons.sync_outlined,
        label: '连接中',
        title: '正在确认摄像头状态',
        message: '设备、画面和语音能力会在这里同步。',
        tone: StatusTone.warning,
      );
    }

    if (care == null || !available) {
      return _ViewportPlaceholder(
        icon: Icons.videocam_off_outlined,
        label: care?.label ?? '看护不可用',
        title: '摄像头暂时不在线',
        message: care?.detail ?? '请确认设备电源和家庭网络后再刷新。',
        tone: care?.tone ?? StatusTone.danger,
        onRefresh: onRefresh,
      );
    }

    final icon = available
        ? Icons.videocam_outlined
        : Icons.videocam_off_outlined;
    final label = care.label;
    final tone = care.tone;
    final copy = _viewportCopy(status, snapshot);

    return AppSurface(
      color: const Color(0xFF0E1725),
      borderColor: Colors.white.withValues(alpha: 0.08),
      radius: 22,
      padding: EdgeInsets.zero,
      child: AspectRatio(
        aspectRatio: 16 / 11.2,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: Stack(
            children: [
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: const Color(0xFF101A28),
                    gradient: available
                        ? const LinearGradient(
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                            colors: [Color(0xFF182A3E), Color(0xFF0F172A)],
                          )
                        : null,
                  ),
                ),
              ),
              if (frame?.available == true && frame?.bytes != null)
                Positioned.fill(
                  child: Image.memory(
                    frame!.bytes!,
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) =>
                        const _ViewportIcon(icon: Icons.broken_image_outlined),
                  ),
                )
              else
                Positioned.fill(child: _ViewportIcon(icon: icon)),
              Positioned(
                left: 16,
                top: 16,
                child: StatusChip(label: label, tone: tone),
              ),
              Positioned(
                left: 16,
                right: 16,
                bottom: 16,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.30),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(13),
                    child: Text(
                      copy,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.84),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        height: 1.45,
                        letterSpacing: 0,
                      ),
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

  String _viewportCopy(
    AsyncValue<LiveCareStatus> status,
    AsyncValue<CameraSnapshotFrame> snapshot,
  ) {
    final care = status.asData?.value;
    final frame = snapshot.asData?.value;
    if (status.isLoading) return '正在同步摄像头状态。';
    if (care == null) return '摄像头暂时不在线，请稍后刷新。';
    if (!care.isAvailable) return care.detail;
    final currentTask = care.currentTask;
    if (currentTask != null) {
      return '正在看护“${currentTask.title}”，任务状态会随进度同步更新。';
    }
    if (frame?.available == true) {
      return '这是最近预览画面，点击查看实时画面可进入横屏监控。';
    }
    if (snapshot.isLoading) return '摄像头在线，正在获取最新快照。';
    return frame?.message ?? '摄像头服务在线，真实画面暂未返回。';
  }
}

class _ViewportPlaceholder extends StatelessWidget {
  const _ViewportPlaceholder({
    required this.icon,
    required this.label,
    required this.title,
    required this.message,
    required this.tone,
    this.onRefresh,
  });

  final IconData icon;
  final String label;
  final String title;
  final String message;
  final StatusTone tone;
  final VoidCallback? onRefresh;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: const Color(0xFF0E1725),
      borderColor: Colors.white.withValues(alpha: 0.08),
      radius: 22,
      padding: EdgeInsets.zero,
      child: AspectRatio(
        aspectRatio: 16 / 11.2,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(22),
          child: Stack(
            children: [
              const Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [Color(0xFF1A2A3C), Color(0xFF0B111C)],
                    ),
                  ),
                ),
              ),
              Positioned(
                left: 14,
                top: 14,
                child: StatusChip(label: label, tone: tone),
              ),
              Center(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        icon,
                        color: Colors.white.withValues(alpha: 0.76),
                        size: 46,
                      ),
                      const SizedBox(height: 13),
                      Text(
                        title,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Colors.white,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 17,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 0,
                        ),
                      ),
                      const SizedBox(height: 7),
                      Text(
                        message,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.64),
                          fontFamily: AppTypography.systemFont,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          height: 1.45,
                          letterSpacing: 0,
                        ),
                      ),
                      if (onRefresh != null) ...[
                        const SizedBox(height: 14),
                        GestureDetector(
                          behavior: HitTestBehavior.opaque,
                          onTap: onRefresh,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(999),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.10),
                              ),
                            ),
                            child: const Padding(
                              padding: EdgeInsets.symmetric(
                                horizontal: 14,
                                vertical: 9,
                              ),
                              child: Text(
                                '刷新状态',
                                style: TextStyle(
                                  color: Colors.white,
                                  fontFamily: AppTypography.systemFont,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: 0,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ],
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

class _ViewportIcon extends StatelessWidget {
  const _ViewportIcon({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Icon(icon, color: Colors.white.withValues(alpha: 0.68), size: 54),
    );
  }
}

class _LiveActions extends StatelessWidget {
  const _LiveActions({
    required this.status,
    required this.snapshot,
    required this.onRefresh,
  });

  final AsyncValue<LiveCareStatus> status;
  final AsyncValue<CameraSnapshotFrame> snapshot;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final available = status.asData?.value.isAvailable ?? false;
    final streamAvailable =
        status.asData?.value.cameraStatus?.streamAvailable ?? available;
    final frameAvailable = snapshot.asData?.value.available ?? false;
    final actions = [
      _LiveAction(
        icon: Icons.play_arrow_rounded,
        title: '实时画面',
        subtitle: streamAvailable ? '进入横屏' : '暂不可用',
        highlighted: true,
        onTap: available && streamAvailable
            ? () => context.go(liveMonitorPath)
            : null,
      ),
      _LiveAction(
        icon: Icons.refresh_outlined,
        title: available ? '刷新预览' : '重新连接',
        subtitle: '同步状态',
        onTap: onRefresh,
      ),
      _LiveAction(
        icon: Icons.camera_alt_outlined,
        title: '快照',
        subtitle: frameAvailable ? '保存当前' : '等待画面',
        onTap: frameAvailable ? () => _showToast(context, '已保存当前画面') : null,
      ),
      _LiveAction(
        icon: Icons.play_circle_outline,
        title: '事件回放',
        subtitle: '最近片段',
        onTap: () => context.go(liveEventsPath),
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 350;
        return GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: compact ? 2 : 4,
          crossAxisSpacing: 9,
          mainAxisSpacing: 9,
          childAspectRatio: compact ? 2.35 : 0.95,
          children: actions
              .map((action) => _LiveActionCard(action: action))
              .toList(),
        );
      },
    );
  }
}

class _LiveAction {
  const _LiveAction({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.highlighted = false,
    this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool highlighted;
  final VoidCallback? onTap;
}

class _LiveActionCard extends StatelessWidget {
  const _LiveActionCard({required this.action});

  final _LiveAction action;

  @override
  Widget build(BuildContext context) {
    final enabled = action.onTap != null;
    final fg = action.highlighted ? Colors.white : AppColors.ink;
    return Opacity(
      opacity: enabled ? 1 : 0.56,
      child: AppSurface(
        onTap: action.onTap,
        radius: 19,
        padding: const EdgeInsets.fromLTRB(11, 11, 11, 10),
        color: action.highlighted
            ? AppColors.ink
            : Colors.white.withValues(alpha: 0.80),
        borderColor: action.highlighted ? AppColors.ink : AppColors.borderSoft,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(action.icon, color: fg, size: 21),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  action.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: fg,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  action.subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: action.highlighted
                        ? Colors.white.withValues(alpha: 0.62)
                        : AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _CareFocusPanel extends StatelessWidget {
  const _CareFocusPanel({required this.status});

  final AsyncValue<LiveCareStatus> status;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final currentTask = care?.currentTask;

    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('当前看护'),
          const SizedBox(height: 8),
          AppListRow(
            icon: currentTask == null
                ? Icons.shield_outlined
                : Icons.play_circle_outline,
            title: currentTask == null ? '当前没有进行中的任务' : currentTask.title,
            subtitle: currentTask == null
                ? '需要查看时进入实时画面，普通状态不会打扰孩子。'
                : '${currentTask.timeLabel} · 任务状态会随进度同步更新',
            tone: care?.isAvailable == true
                ? AppListRowTone.green
                : AppListRowTone.amber,
          ),
          AppListRow(
            icon: Icons.play_circle_outline,
            title: '事件回放',
            subtitle: '查看最近的任务、提醒和看护片段',
            tone: AppListRowTone.blue,
            onTap: () => context.go(liveEventsPath),
          ),
        ],
      ),
    );
  }
}

class LiveEventsScreen extends ConsumerWidget {
  const LiveEventsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final monitor = ref.watch(cameraMonitorStatusProvider);
    return AppScreen(
      title: '事件回放',
      subtitle: '最近片段',
      onBack: () => context.go(AppRoute.live.path),
      children: [
        monitor.when(
          loading: () =>
              const AppLoadingState(title: '正在整理最近片段', message: '请稍等一下。'),
          error: (_, _) => const AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '暂时拿不到回放',
            message: '稍后再试，任务记录不会受到影响。',
          ),
          data: (value) {
            if (value.lastObservation.isEmpty && value.lastReminder.isEmpty) {
              return const AppStateView(
                variant: AppStateVariant.noData,
                title: '还没有可回放的片段',
                message: '当任务提醒或看护片段产生后，会在这里显示。',
              );
            }
            return Column(
              children: [
                if (value.lastObservation.isNotEmpty)
                  _PlaybackCard(
                    icon: Icons.visibility_outlined,
                    title: '最近看护片段',
                    time: '刚刚',
                    message: value.lastObservation,
                    tone: AppListRowTone.blue,
                  ),
                if (value.lastObservation.isNotEmpty &&
                    value.lastReminder.isNotEmpty)
                  const SizedBox(height: 12),
                if (value.lastReminder.isNotEmpty)
                  _PlaybackCard(
                    icon: Icons.notifications_active_outlined,
                    title: '最近提醒',
                    time: '刚刚',
                    message: value.lastReminder,
                    tone: AppListRowTone.amber,
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _PlaybackCard extends StatelessWidget {
  const _PlaybackCard({
    required this.icon,
    required this.title,
    required this.time,
    required this.message,
    required this.tone,
  });

  final IconData icon;
  final String title;
  final String time;
  final String message;
  final AppListRowTone tone;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      child: AppListRow(
        icon: icon,
        title: title,
        subtitle: '$time · $message',
        tone: tone,
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 16,
        fontWeight: FontWeight.w800,
        letterSpacing: 0,
      ),
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
