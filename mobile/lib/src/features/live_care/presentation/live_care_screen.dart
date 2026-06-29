import 'dart:async';

import 'package:easy_refresh/easy_refresh.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_helpers.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/state/async_value_ui.dart';
import 'package:warm_sight/src/core/state/refresh_guard.dart';
import 'package:warm_sight/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:warm_sight/src/shared/widgets/app_page_header.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class LiveCareScreen extends ConsumerStatefulWidget {
  const LiveCareScreen({super.key});

  @override
  ConsumerState<LiveCareScreen> createState() => _LiveCareScreenState();
}

class _LiveCareScreenState extends ConsumerState<LiveCareScreen> {
  final _refreshGuard = RefreshGuard();
  var _previewRefreshing = false;
  var _refreshGeneration = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_refreshLiveCare(analyzeFrame: false));
    });
  }

  @override
  void dispose() {
    _refreshGeneration++;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selectedDevice = ref.watch(selectedDeviceProvider);
    if (isInitialAsyncLoad(selectedDevice)) {
      return const AppScreen(
        title: '实时看护',
        fixedHeader: false,
        showHeader: false,
        padding: EdgeInsets.fromLTRB(
          AppSpacing.pageHorizontal,
          8,
          AppSpacing.pageHorizontal,
          AppSpacing.pageBottom,
        ),
        children: [_LoadingLiveCareState()],
      );
    }
    if (selectedDevice.hasError) {
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
          AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '摄像头状态暂时无法同步',
            message: '请稍后刷新。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: () =>
                silentRefreshProvider(ref, selectedDeviceProvider),
            compact: true,
          ),
        ],
      );
    }
    final titleDevice = selectedDevice.asData?.value;
    if (titleDevice == null) {
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
          AppStateView(
            variant: AppStateVariant.deviceOffline,
            title: '还没有连接摄像头',
            message: '连接后可以查看实时画面和看护提醒。',
            primaryActionLabel: '连接看护摄像头',
            onPrimaryAction: () => showAddCameraSheet(context),
            compact: true,
          ),
        ],
      );
    }
    final liveStatus = ref.watch(liveCareStatusProvider);
    final snapshotFrame = ref.watch(cameraSnapshotProvider);
    final events = ref.watch(cameraEventsProvider);
    final subtitle =
        '${titleDevice.displayLocation} · ${titleDevice.displayName}';

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
          onRefresh: () => unawaited(_refreshLiveCare(analyzeFrame: true)),
          previewRefreshing: _previewRefreshing,
        ),
        const SizedBox(height: 8),
        _LiveActions(
          status: liveStatus,
          previewRefreshing: _previewRefreshing,
          onRefresh: () => unawaited(_refreshLiveCare(analyzeFrame: true)),
        ),
        const SizedBox(height: 10),
        _CareFocusPanel(status: liveStatus, events: events),
      ],
    );
  }

  Future<void> _refreshLiveCare({bool analyzeFrame = false}) async {
    if (!mounted) return;
    final generation = ++_refreshGeneration;
    final device = ref.read(selectedDeviceProvider).asData?.value;

    Future<void> runRefresh() async {
      if (!mounted || generation != _refreshGeneration) return;
      if (analyzeFrame && device != null) {
        try {
          await triggerMonitorAnalysis(ref, deviceId: device.id);
        } on CameraException {
          // 手动刷新仍应回落到普通状态刷新，避免实时页被观察服务错误卡住。
        }
      }
      if (!mounted || generation != _refreshGeneration) return;
      await refreshLiveCareDataSilently(ref);
    }

    if (analyzeFrame) {
      if (mounted) setState(() => _previewRefreshing = true);
      try {
        final ran = await ref
            .read(monitorAnalysisGuardProvider)
            .runHeavy(runRefresh);
        if (!ran && mounted && generation == _refreshGeneration) {
          await _refreshGuard.runLight(runRefresh);
        }
      } finally {
        if (mounted && generation == _refreshGeneration) {
          setState(() => _previewRefreshing = false);
        }
      }
      return;
    }

    await _refreshGuard.runLight(runRefresh);
  }
}

class _LoadingLiveCareState extends StatelessWidget {
  const _LoadingLiveCareState();

  @override
  Widget build(BuildContext context) {
    return const AppStateView(
      variant: AppStateVariant.loading,
      title: '正在同步摄像头',
      message: '请稍候。',
      compact: true,
    );
  }
}

class _LiveCareHero extends StatelessWidget {
  const _LiveCareHero({
    required this.title,
    required this.subtitle,
    required this.status,
    required this.snapshot,
    required this.onRefresh,
    this.previewRefreshing = false,
  });

  final String title;
  final String subtitle;
  final AsyncValue<LiveCareStatus> status;
  final AsyncValue<CameraSnapshotFrame> snapshot;
  final VoidCallback onRefresh;
  final bool previewRefreshing;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final statusInitialLoad = isInitialAsyncLoad(status);
    final label = statusInitialLoad ? '正在连接' : care?.label ?? '状态检查中';
    final tone = statusInitialLoad
        ? StatusTone.warning
        : care?.tone ?? StatusTone.neutral;

    return AppHeroPanel(
      dark: true,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
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
                        fontSize: 24,
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
            previewRefreshing: previewRefreshing,
            onRefresh: onRefresh,
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
    this.previewRefreshing = false,
  });

  final AsyncValue<LiveCareStatus> status;
  final AsyncValue<CameraSnapshotFrame> snapshot;
  final VoidCallback onRefresh;
  final bool previewRefreshing;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final frame = snapshot.asData?.value;
    final available = care?.isAvailable ?? false;
    final statusInitialLoad = isInitialAsyncLoad(status);

    if (statusInitialLoad) {
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
    final copy = _viewportCopy(status, snapshot);

    return AppSurface(
      color: const Color(0xFF0E1725),
      borderColor: Colors.white.withValues(alpha: 0.08),
      radius: 22,
      padding: EdgeInsets.zero,
      child: AspectRatio(
        aspectRatio: 16 / 9.4,
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
      return '正在看护“${currentTask.title}”，进度会同步更新。';
    }
    if (frame?.available == true) {
      return '这是最近预览画面，点击查看实时画面可进入竖屏监控。';
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
        aspectRatio: 16 / 9.4,
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
    required this.onRefresh,
    this.previewRefreshing = false,
  });

  final AsyncValue<LiveCareStatus> status;
  final VoidCallback onRefresh;
  final bool previewRefreshing;

  @override
  Widget build(BuildContext context) {
    final available = status.asData?.value.isAvailable ?? false;
    final streamAvailable =
        status.asData?.value.cameraStatus?.streamAvailable ?? available;
    final refreshSubtitle = previewRefreshing ? '同步中…' : '同步状态';
    final actions = [
      _LiveAction(
        icon: Icons.play_arrow_rounded,
        title: '实时画面',
        subtitle: streamAvailable ? '进入监控' : '暂不可用',
        highlighted: true,
        onTap: available && streamAvailable
            ? () => context.go(liveMonitorPath)
            : null,
      ),
      _LiveAction(
        icon: Icons.refresh_outlined,
        title: available ? '刷新预览' : '重新连接',
        subtitle: refreshSubtitle,
        loading: previewRefreshing,
        onTap: previewRefreshing ? null : onRefresh,
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < 360;
        return Row(
          children: [
            for (var index = 0; index < actions.length; index++) ...[
              Expanded(
                child: SizedBox(
                  height: compact ? 74 : 80,
                  child: _LiveActionCard(
                    action: actions[index],
                    compact: compact,
                  ),
                ),
              ),
              if (index != actions.length - 1) const SizedBox(width: 8),
            ],
          ],
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
    this.loading = false,
    this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final bool highlighted;
  final bool loading;
  final VoidCallback? onTap;
}

class _LiveActionCard extends StatelessWidget {
  const _LiveActionCard({required this.action, this.compact = false});

  final _LiveAction action;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final enabled = action.onTap != null;
    final fg = action.highlighted ? Colors.white : AppColors.ink;
    return Opacity(
      opacity: enabled ? 1 : 0.56,
      child: AppSurface(
        onTap: action.onTap,
        radius: 17,
        padding: EdgeInsets.fromLTRB(10, compact ? 8 : 10, 10, compact ? 8 : 9),
        color: action.highlighted
            ? AppColors.ink
            : Colors.white.withValues(alpha: 0.80),
        borderColor: action.highlighted ? AppColors.ink : AppColors.borderSoft,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(
              action.loading ? Icons.sync_outlined : action.icon,
              color: fg,
              size: compact ? 20 : 21,
            ),
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
  const _CareFocusPanel({required this.status, required this.events});

  final AsyncValue<LiveCareStatus> status;
  final AsyncValue<CameraEventsState> events;

  @override
  Widget build(BuildContext context) {
    final care = status.asData?.value;
    final currentTask = care?.currentTask;
    final monitor = care?.monitorStatus;
    final hasFreshObservation = monitor?.hasCurrentReliableObservation == true;
    final hasStaleObservation = monitor?.hasStaleObservation == true;
    final isPrefilterOnly =
        monitor?.lastObservationFreshness ==
        CameraObservationFreshness.prefilterOnly;
    final hasObservationDisplay =
        hasFreshObservation || hasStaleObservation || isPrefilterOnly;
    final eventItems = events.asData?.value.items ?? const <LiveCareEvent>[];
    final summaryEvents = eventItems
        .where(
          (event) =>
              !(event.eventType == 'ptz_move' && event.status == 'failed'),
        )
        .toList();
    final recentEvent = summaryEvents.isEmpty ? null : summaryEvents.first;
    final recentHasRoutine = recentEvent?.isRoutineRecord == true;

    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('当前看护'),
          const SizedBox(height: 8),
          AppListRow(
            icon: hasObservationDisplay
                ? Icons.visibility_outlined
                : currentTask == null
                ? Icons.shield_outlined
                : Icons.play_circle_outline,
            title: hasFreshObservation
                ? monitor!.lastObservation
                : hasStaleObservation
                ? monitor!.displayObservationTitle()
                : isPrefilterOnly
                ? '画面已更新，正在整理观察结果'
                : currentTask == null
                ? '当前没有进行中的看护安排'
                : currentTask.title,
            subtitle: hasFreshObservation
                ? _monitorObservationSubtitle(monitor!)
                : hasStaleObservation
                ? '较早的画面结论，不作为当前状态。'
                : isPrefilterOnly
                ? '预检已更新，稍后会整理新的观察结果。'
                : currentTask == null
                ? recentHasRoutine
                      ? '最近有作息提醒，进入实时画面可查看当前状态。'
                      : '需要查看时进入实时画面，普通状态不会打扰孩子。'
                : '${currentTask.timeLabel} · 看护记录会在这里更新',
            tone: care?.isAvailable == true
                ? AppListRowTone.green
                : AppListRowTone.amber,
            subtitleMaxLines: 1,
          ),
          if (events.isLoading)
            const AppListRow(
              icon: Icons.history_toggle_off_outlined,
              title: '正在整理近期记录',
              subtitle: '正在整理最近的画面观察。',
              tone: AppListRowTone.neutral,
            )
          else if (recentEvent == null)
            AppListRow(
              icon: Icons.history_toggle_off_outlined,
              title: '还没有可靠的画面记录',
              subtitle: '看到孩子、没看到孩子或画面不可判断时会显示在这里。',
              tone: AppListRowTone.neutral,
              onTap: () => context.go(liveEventsPath),
            )
          else
            AppListRow(
              icon: Icons.history_outlined,
              title: '最近记录',
              subtitle: _recentEventSubtitle(recentEvent),
              tone: _eventListTone(recentEvent),
              onTap: () => context.go(liveEventsPath),
              subtitleMaxLines: 1,
            ),
        ],
      ),
    );
  }
}

AppListRowTone _eventListTone(LiveCareEvent event) {
  return switch (event.toneKey) {
    'success' => AppListRowTone.green,
    'warning' => AppListRowTone.amber,
    'danger' => AppListRowTone.red,
    _ => AppListRowTone.blue,
  };
}

String _recentEventSubtitle(LiveCareEvent event) {
  final prefix = switch (event.recordKind) {
    'routine' => '作息提醒',
    'reminder' => '语音提醒',
    'vision' => '画面观察',
    _ => '看护记录',
  };
  return '$prefix · ${event.timeLabel} · ${event.displayTitle}：${event.displayMessage}';
}

String _monitorObservationSubtitle(CameraMonitorStatus monitor) {
  final parts = <String>[
    monitor.lastObservationDescription,
    if (monitor.lastObservationDecisionReason.isNotEmpty)
      monitor.lastObservationDecisionReason,
  ];
  final text = parts.where((part) => part.trim().isNotEmpty).join(' · ');
  final display = parentFacingCameraObservationText(text, maxLength: 42);
  return display.isEmpty ? '这条记录来自摄像头画面。' : display;
}

class LiveEventsScreen extends ConsumerStatefulWidget {
  const LiveEventsScreen({super.key});

  @override
  ConsumerState<LiveEventsScreen> createState() => _LiveEventsScreenState();
}

class _LiveEventsScreenState extends ConsumerState<LiveEventsScreen> {
  final _scrollController = ScrollController();
  final _refreshController = EasyRefreshController(
    controlFinishRefresh: true,
    controlFinishLoad: true,
  );

  @override
  void dispose() {
    _scrollController.dispose();
    _refreshController.dispose();
    super.dispose();
  }

  Future<void> _handleRefresh() {
    return ref.read(cameraEventsProvider.notifier).refresh();
  }

  Future<bool> _handleLoadMore() {
    return ref.read(cameraEventsProvider.notifier).loadMore();
  }

  @override
  Widget build(BuildContext context) {
    final events = ref.watch(cameraEventsProvider);
    final eventsState = events.asData?.value;
    return AppScreen(
      title: '看护记录',
      subtitle: '画面观察和需要回看的情况',
      onBack: () => context.go(AppRoute.live.path),
      scrollController: _scrollController,
      reserveBottomNavigation: false,
      refreshDisplacement: 52,
      easyRefreshController: _refreshController,
      onRefresh: _handleRefresh,
      onLoadMore: eventsState?.hasMore == true ? _handleLoadMore : null,
      children: [
        events.when(
          skipLoadingOnRefresh: true,
          loading: () =>
              const AppLoadingState(title: '正在整理最近片段', message: '请稍等一下。'),
          error: (_, _) => const AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '暂时拿不到回放',
            message: '稍后再试，任务记录不会受到影响。',
          ),
          data: (state) {
            final items = state.items;
            if (items.isEmpty) {
              return const AppStateView(
                variant: AppStateVariant.noData,
                title: '还没有可靠的画面记录',
                message: '看到孩子、没看到孩子或画面不可判断时会显示在这里。',
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (var index = 0; index < items.length; index++) ...[
                  _PlaybackCard(
                    icon: _eventIcon(items[index]),
                    title: items[index].displayTitle,
                    time: items[index].timeLabel,
                    message: _recentEventSubtitle(items[index]),
                    tone: _eventListTone(items[index]),
                  ),
                  if (index != items.length - 1) const SizedBox(height: 12),
                ],
                if (state.isLoadingMore) ...[
                  const SizedBox(height: 16),
                  const Center(
                    child: SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      ],
    );
  }
}

IconData _eventIcon(LiveCareEvent event) {
  if (event.category == 'camera_observation' ||
      event.category == 'child_presence') {
    return Icons.visibility_outlined;
  }
  if (event.category == 'snapshot') {
    return Icons.camera_alt_outlined;
  }
  if (event.category == 'care_reminder') {
    return Icons.record_voice_over_outlined;
  }
  if (event.category == 'camera_status') {
    return Icons.videocam_off_outlined;
  }
  return switch (event.eventType) {
    'ptz_move' => Icons.control_camera_outlined,
    'speak' => Icons.record_voice_over_outlined,
    'snapshot' => Icons.camera_alt_outlined,
    'start_monitor' || 'stop_monitor' => Icons.visibility_outlined,
    _ =>
      event.source == 'task_event'
          ? Icons.task_alt_outlined
          : Icons.play_circle_outline,
  };
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
    final color = _playbackToneColor(tone);
    return AppSurface(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(14),
              ),
              child: SizedBox(
                width: 42,
                height: 42,
                child: Center(child: Icon(icon, color: color, size: 21)),
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 15,
                      fontWeight: FontWeight.w900,
                      height: 1.25,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    time,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 11.5,
                      fontWeight: FontWeight.w700,
                      height: 1.25,
                      letterSpacing: 0,
                    ),
                  ),
                  if (message.trim().isNotEmpty) ...[
                    const SizedBox(height: 7),
                    Text(
                      message,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                        height: 1.42,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Color _playbackToneColor(AppListRowTone tone) {
  return switch (tone) {
    AppListRowTone.blue => AppColors.brand,
    AppListRowTone.green => AppColors.success,
    AppListRowTone.amber => AppColors.warning,
    AppListRowTone.red => AppColors.danger,
    AppListRowTone.neutral => AppColors.ink,
  };
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
