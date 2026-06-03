import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/devices/application/device_repository.dart';
import 'package:mira_guardian_app/src/features/devices/domain/device_models.dart';
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
        _ObservationPanel(status: liveStatus),
        const SizedBox(height: 14),
        _DeviceRuntimePanel(
          deviceOverview: deviceOverview,
          liveStatus: liveStatus,
        ),
      ],
    );
  }

  void _refreshLiveCare(WidgetRef ref) {
    ref
      ..invalidate(liveCareStatusProvider)
      ..invalidate(cameraHealthProvider)
      ..invalidate(cameraRuntimeProvider)
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
    if (frame?.available == true) {
      return '快照已更新，画面仅用于家长查看当前状态。';
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
    final frameAvailable = snapshot.asData?.value.available ?? false;
    final buttons = [
      MiraSecondaryButton(
        label: '刷新状态',
        trailing: const Icon(Icons.refresh_outlined, size: 18),
        onTap: onRefresh,
      ),
      MiraSecondaryButton(
        label: '确认观察',
        trailing: const Icon(Icons.fact_check_outlined, size: 18),
        onTap: available
            ? () => _showLiveConfirmSheet(context, status.asData!.value)
            : null,
      ),
      MiraSecondaryButton(
        label: '快照',
        trailing: const Icon(Icons.camera_alt_outlined, size: 18),
        onTap: frameAvailable ? () => _showToast(context, '快照已更新') : null,
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 360) {
          return Column(
            children: [
              for (var index = 0; index < buttons.length; index++) ...[
                buttons[index],
                if (index != buttons.length - 1) const SizedBox(height: 10),
              ],
            ],
          );
        }

        return Row(
          children: [
            for (var index = 0; index < buttons.length; index++) ...[
              Expanded(child: buttons[index]),
              if (index != buttons.length - 1) const SizedBox(width: 10),
            ],
          ],
        );
      },
    );
  }
}

class _ObservationPanel extends StatelessWidget {
  const _ObservationPanel({required this.status});

  final AsyncValue<LiveCareStatus> status;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;

    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('AI 观察摘要'),
          const SizedBox(height: 10),
          Text(
            care?.runtime.summary ??
                (status.isLoading ? '正在同步观察摘要。' : '暂时没有拿到最新观察摘要。'),
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.55,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 10),
          MiraListRow(
            icon: Icons.fact_check_outlined,
            title: '家长确认入口',
            subtitle: care?.isAvailable == true
                ? '确认当前观察，或标记 AI 判断需要调整'
                : '真实画面不可用时，仅保留状态确认入口',
            tone: care?.isAvailable == true
                ? MiraListRowTone.blue
                : MiraListRowTone.amber,
            onTap: care == null
                ? null
                : () => _showLiveConfirmSheet(context, care),
          ),
        ],
      ),
    );
  }
}

class _DeviceRuntimePanel extends StatelessWidget {
  const _DeviceRuntimePanel({
    required this.deviceOverview,
    required this.liveStatus,
  });

  final AsyncValue<DeviceOverview?> deviceOverview;
  final AsyncValue<LiveCareStatus> liveStatus;

  @override
  Widget build(BuildContext context) {
    final overview = deviceOverview.asData?.value;
    final care = liveStatus.asData?.value;

    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('设备状态'),
          const SizedBox(height: 8),
          MiraListRow(
            icon: Icons.wifi_outlined,
            title: overview?.device.displayName ?? 'Mira 设备',
            subtitle: overview?.subtitle ?? '正在读取设备绑定状态',
            tone: overview?.isOnline == false
                ? MiraListRowTone.red
                : MiraListRowTone.green,
            trailing: StatusChip(
              label: overview?.connectionLabel ?? '同步中',
              tone: overview?.tone ?? StatusTone.neutral,
            ),
          ),
          MiraListRow(
            icon: Icons.memory_outlined,
            title: care?.runtime.stateLabel ?? '摄像头运行状态',
            subtitle: care?.health.message ?? '正在同步摄像头状态',
            tone: care?.isAvailable == false
                ? MiraListRowTone.red
                : MiraListRowTone.blue,
            trailing: StatusChip(
              label: care?.health.reachable == true ? '可达' : '降级',
              tone: care?.health.tone ?? StatusTone.neutral,
            ),
          ),
          MiraListRow(
            icon: Icons.privacy_tip_outlined,
            title: '隐私与能力边界',
            subtitle: '实时看护只展示家长需要确认的画面和观察摘要。',
            tone: MiraListRowTone.neutral,
          ),
        ],
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

void _showLiveConfirmSheet(BuildContext context, LiveCareStatus status) {
  showModalBottomSheet<void>(
    context: context,
    useRootNavigator: true,
    showDragHandle: true,
    backgroundColor: AppColors.appBackgroundWarm,
    builder: (context) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '家长确认',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              status.runtime.summary,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
              ),
            ),
            const SizedBox(height: 16),
            MiraListRow(
              icon: Icons.check_circle_outline,
              title: '确认当前状态',
              subtitle: '写入今日看护记录',
              tone: MiraListRowTone.green,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已确认当前观察');
              },
            ),
            MiraListRow(
              icon: Icons.report_outlined,
              title: '标记观察不准确',
              subtitle: '后续提醒会参考这次反馈',
              tone: MiraListRowTone.amber,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已记录 AI 判断反馈');
              },
            ),
          ],
        ),
      );
    },
  );
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
