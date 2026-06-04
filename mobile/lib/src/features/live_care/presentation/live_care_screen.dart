import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/devices/application/device_repository.dart';
import 'package:mira_guardian_app/src/features/live_care/application/camera_repository.dart';
import 'package:mira_guardian_app/src/features/live_care/domain/camera_models.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class LiveCareScreen extends ConsumerWidget {
  const LiveCareScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final deviceOverview = ref.watch(primaryDeviceOverviewProvider);
    final liveStatus = ref.watch(liveCareStatusProvider);
    final snapshotFrame = ref.watch(cameraSnapshotProvider);
    final titleDevice = deviceOverview.asData?.value?.device;
    final subtitle = titleDevice == null
        ? '${snapshot.device.room} · ${snapshot.device.name}'
        : '${titleDevice.displayLocation} · ${titleDevice.displayName}';

    return MiraScreen(
      title: '实时看护',
      subtitle: subtitle,
      children: [
        _LiveViewport(
          status: liveStatus,
          snapshot: snapshotFrame,
          onRefresh: () => _refreshLiveCare(ref),
        ),
        const SizedBox(height: 14),
        _LiveActions(
          status: liveStatus,
          snapshot: snapshotFrame,
          onRefresh: () => _refreshLiveCare(ref),
        ),
        const SizedBox(height: 14),
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
      return const MiraLoadingState(
        title: '正在连接摄像头',
        message: '正在确认设备在线状态和实时看护能力。',
      );
    }

    if (care == null || !available) {
      return MiraStateView(
        variant: MiraStateVariant.cameraUnavailable,
        title: '摄像头暂时不在线',
        message: care?.detail ?? '我们暂时拿不到实时画面。请确认设备电源和家庭网络后再刷新。',
        primaryActionLabel: '刷新状态',
        onPrimaryAction: onRefresh,
      );
    }

    final icon = available
        ? Icons.videocam_outlined
        : Icons.videocam_off_outlined;
    final label = care.label;
    final tone = care.tone;
    final copy = _viewportCopy(status, snapshot);

    return MiraSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: EdgeInsets.zero,
      child: AspectRatio(
        aspectRatio: 16 / 11.2,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(24),
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
    return Column(
      children: [
        MiraPrimaryButton(
          label: '查看实时画面',
          trailing: const MiraButtonGlyph(icon: Icons.play_arrow_rounded),
          onTap: available && streamAvailable
              ? () => context.go(liveMonitorPath)
              : null,
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: MiraSecondaryButton(
                label: available ? '刷新预览' : '重新连接',
                trailing: const Icon(Icons.refresh_outlined, size: 18),
                onTap: onRefresh,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: MiraSecondaryButton(
                label: '快照',
                trailing: const Icon(Icons.camera_alt_outlined, size: 18),
                onTap: frameAvailable
                    ? () => _showToast(context, '已保存当前画面')
                    : null,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: MiraSecondaryButton(
                label: '回放',
                trailing: const Icon(Icons.play_circle_outline, size: 18),
                onTap: () => context.go(liveEventsPath),
              ),
            ),
          ],
        ),
      ],
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

    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('当前看护'),
          const SizedBox(height: 8),
          MiraListRow(
            icon: currentTask == null
                ? Icons.shield_outlined
                : Icons.play_circle_outline,
            title: currentTask == null ? '当前没有进行中的任务' : currentTask.title,
            subtitle: currentTask == null
                ? '需要查看时进入实时画面，普通状态不会打扰孩子。'
                : '${currentTask.timeLabel} · 任务状态会随进度同步更新',
            tone: care?.isAvailable == true
                ? MiraListRowTone.green
                : MiraListRowTone.amber,
          ),
          MiraListRow(
            icon: Icons.play_circle_outline,
            title: '事件回放',
            subtitle: '查看最近的任务、提醒和看护片段',
            tone: MiraListRowTone.blue,
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
    return MiraScreen(
      title: '事件回放',
      subtitle: '最近片段',
      onBack: () => context.go(AppRoute.live.path),
      children: [
        monitor.when(
          loading: () =>
              const MiraLoadingState(title: '正在整理最近片段', message: '请稍等一下。'),
          error: (_, _) => const MiraStateView(
            variant: MiraStateVariant.serviceUnavailable,
            title: '暂时拿不到回放',
            message: '稍后再试，任务记录不会受到影响。',
          ),
          data: (value) {
            if (value.lastObservation.isEmpty && value.lastReminder.isEmpty) {
              return const MiraStateView(
                variant: MiraStateVariant.noData,
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
                    tone: MiraListRowTone.blue,
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
                    tone: MiraListRowTone.amber,
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
  final MiraListRowTone tone;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      child: MiraListRow(
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
