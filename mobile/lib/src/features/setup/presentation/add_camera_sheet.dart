import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/devices/application/selected_device_controller.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/discovery_scene.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/camera_discovery_animation.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';

const kSetupDefaultDeviceName = 'AI 看护摄像头';
const kSetupDefaultBindingCode = 'AI-CARE-NEARBY-KINDERGARTEN-V1';

/// Opens the add-camera flow as a modal bottom sheet over the current page.
Future<bool?> showAddCameraSheet(
  BuildContext context, {
  AddCameraSheetPreviewStage? initialStageForTesting,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    useRootNavigator: true,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    barrierColor: AppColors.ink.withValues(alpha: 0.42),
    enableDrag: true,
    builder: (context) => AddCameraSheet(
      initialStageForTesting: initialStageForTesting,
    ),
  );
}

@visibleForTesting
enum AddCameraSheetPreviewStage {
  searching,
  found,
  connecting,
  success,
  notFound,
  failed,
}

class AddCameraSheet extends ConsumerStatefulWidget {
  const AddCameraSheet({super.key, this.initialStageForTesting});

  @visibleForTesting
  final AddCameraSheetPreviewStage? initialStageForTesting;

  @override
  ConsumerState<AddCameraSheet> createState() => _AddCameraSheetState();
}

enum _AddCameraStage {
  ready,
  permission,
  searching,
  found,
  connecting,
  success,
  notFound,
  failed,
}

class _AddCameraSheetState extends ConsumerState<AddCameraSheet>
    with SingleTickerProviderStateMixin {
  _AddCameraStage _stage = _AddCameraStage.searching;
  Timer? _searchTimer;
  var _connecting = false;
  late final AnimationController _foundEntryController;
  late final Animation<double> _foundFade;
  late final Animation<Offset> _foundSlide;

  @override
  void initState() {
    super.initState();
    _foundEntryController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 220),
    );
    _foundFade = CurvedAnimation(
      parent: _foundEntryController,
      curve: Curves.easeOutCubic,
    );
    _foundSlide = Tween<Offset>(
      begin: const Offset(0, 0.06),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _foundEntryController, curve: Curves.easeOutCubic),
    );

    final previewStage = widget.initialStageForTesting;
    if (previewStage == null) {
      _scheduleSearchResult();
    } else {
      _stage = _stageFromPreview(previewStage);
      _connecting = previewStage == AddCameraSheetPreviewStage.connecting;
      if (_stage == _AddCameraStage.found ||
          _stage == _AddCameraStage.connecting) {
        _foundEntryController.value = 1;
      }
    }
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _foundEntryController.dispose();
    super.dispose();
  }

  void _goTo(_AddCameraStage stage) {
    _searchTimer?.cancel();
    if (!mounted) return;
    setState(() => _stage = stage);
    if (stage == _AddCameraStage.searching) {
      _foundEntryController.reset();
      _scheduleSearchResult();
    } else if (stage == _AddCameraStage.found) {
      _foundEntryController.forward(from: 0);
    } else if (stage == _AddCameraStage.connecting) {
      _foundEntryController.value = 1;
    }
  }

  void _startSearch() => _goTo(_AddCameraStage.searching);

  void _scheduleSearchResult() {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 1450), () {
      if (!mounted || _stage != _AddCameraStage.searching) return;
      _goTo(_AddCameraStage.found);
    });
  }

  Future<void> _connectCamera() async {
    if (_connecting) return;
    _searchTimer?.cancel();
    setState(() {
      _stage = _AddCameraStage.connecting;
      _connecting = true;
    });
    try {
      final device = await ref.read(deviceRepositoryProvider).bindDevice(
        bindingCode: kSetupDefaultBindingCode,
        name: kSetupDefaultDeviceName,
        setAsDefault: true,
      );
      await selectDevice(ref, device.id);
      _refreshCameraAfterAdd(ref);
      if (!mounted) return;
      setState(() {
        _stage = _AddCameraStage.success;
        _connecting = false;
      });
      showAppToast(context, '摄像头已连接');
    } on DeviceException catch (error) {
      if (!mounted) return;
      setState(() {
        _stage = _AddCameraStage.failed;
        _connecting = false;
      });
      showAppToast(context, error.message);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _stage = _AddCameraStage.failed;
        _connecting = false;
      });
      showAppToast(context, '连接失败，请稍后重试');
    }
  }

  void _showConnectionHelp() => _goTo(_AddCameraStage.notFound);

  void _close({bool success = false}) {
    Navigator.of(context).pop(success);
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final factor = screenHeight < 740 ? 0.48 : 0.46;
    final sheetHeight = (screenHeight * factor).clamp(300.0, 380.0).toDouble();

    return Align(
      alignment: Alignment.bottomCenter,
      child: Stack(
        alignment: Alignment.bottomCenter,
        clipBehavior: Clip.none,
        children: [
          Positioned(
            bottom: sheetHeight - 40,
            child: IgnorePointer(
              child: Container(
                width: screenHeight * 0.55,
                height: screenHeight * 0.28,
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    colors: [
                      AppColors.brandSageWash.withValues(alpha: 0.08),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
          ),
          Container(
            height: sheetHeight,
            width: double.infinity,
            decoration: BoxDecoration(
              color: AppColors.surfaceElevated,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(28)),
              border: Border(
                top: BorderSide(color: Colors.white.withValues(alpha: 0.84)),
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.ink.withValues(alpha: 0.14),
                  blurRadius: 32,
                  offset: const Offset(0, -10),
                ),
              ],
            ),
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 0),
                  child: AppSheetHandle(),
                ),
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(20, 4, 20, bottomInset + 14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _SheetTitleBlock(stage: _stage),
                        const SizedBox(height: 10),
                        Expanded(
                          child: AnimatedSwitcher(
                            duration: AppMotion.duration(context, 220),
                            switchInCurve: Curves.easeOutCubic,
                            switchOutCurve: Curves.easeInCubic,
                            child: _SheetBody(
                              key: ValueKey(_stage),
                              stage: _stage,
                              foundFade: _foundFade,
                              foundSlide: _foundSlide,
                            ),
                          ),
                        ),
                        _SheetActions(
                          stage: _stage,
                          onConnect: _connectCamera,
                          onRetry: _startSearch,
                          onFinish: () => _close(success: true),
                          onHelp: _showConnectionHelp,
                        ),
                      ],
                    ),
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

_AddCameraStage _stageFromPreview(AddCameraSheetPreviewStage stage) {
  return switch (stage) {
    AddCameraSheetPreviewStage.searching => _AddCameraStage.searching,
    AddCameraSheetPreviewStage.found => _AddCameraStage.found,
    AddCameraSheetPreviewStage.connecting => _AddCameraStage.connecting,
    AddCameraSheetPreviewStage.success => _AddCameraStage.success,
    AddCameraSheetPreviewStage.notFound => _AddCameraStage.notFound,
    AddCameraSheetPreviewStage.failed => _AddCameraStage.failed,
  };
}

String _sheetTitle(_AddCameraStage stage) {
  return switch (stage) {
    _AddCameraStage.ready ||
    _AddCameraStage.permission ||
    _AddCameraStage.searching => '正在发现附近设备',
    _AddCameraStage.found => '发现 1 台设备',
    _AddCameraStage.connecting => '正在连接...',
    _AddCameraStage.success => '摄像头已连接',
    _AddCameraStage.notFound => '没有找到摄像头',
    _AddCameraStage.failed => '连接没有完成',
  };
}

class _SheetTitleBlock extends StatelessWidget {
  const _SheetTitleBlock({required this.stage});

  final _AddCameraStage stage;

  @override
  Widget build(BuildContext context) {
    final isSearching =
        stage == _AddCameraStage.searching ||
        stage == _AddCameraStage.ready ||
        stage == _AddCameraStage.permission;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                _sheetTitle(stage),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 22,
                  fontWeight: FontWeight.w900,
                  height: 1.16,
                  letterSpacing: 0,
                ),
              ),
            ),
            if (isSearching) const _SearchingDots(),
          ],
        ),
        if (isSearching) ...[
          const SizedBox(height: 6),
          const Text(
            '请保持摄像头通电，并靠近手机',
            style: TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              height: 1.35,
              letterSpacing: 0,
            ),
          ),
        ],
      ],
    );
  }
}

class _SearchingDots extends StatefulWidget {
  const _SearchingDots();

  @override
  State<_SearchingDots> createState() => _SearchingDotsState();
}

class _SearchingDotsState extends State<_SearchingDots>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.disableAnimationsOf(context)) {
      return const Text(
        '...',
        style: TextStyle(
          color: AppColors.muted,
          fontWeight: FontWeight.w800,
          fontSize: 18,
        ),
      );
    }
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (index) {
            final phase = ((_controller.value + index * 0.33) % 1);
            final alpha = (math.sin(phase * math.pi)).clamp(0.25, 1.0);
            return Padding(
              padding: const EdgeInsets.only(left: 3),
              child: Opacity(
                opacity: alpha,
                child: Container(
                  width: 5,
                  height: 5,
                  decoration: const BoxDecoration(
                    color: AppColors.brandSage,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            );
          }),
        );
      },
    );
  }
}

class _SheetBody extends StatelessWidget {
  const _SheetBody({
    required this.stage,
    required this.foundFade,
    required this.foundSlide,
    super.key,
  });

  final _AddCameraStage stage;
  final Animation<double> foundFade;
  final Animation<Offset> foundSlide;

  @override
  Widget build(BuildContext context) {
    final animSize = MediaQuery.sizeOf(context).height < 740 ? 204.0 : 216.0;
    return switch (stage) {
      _AddCameraStage.ready ||
      _AddCameraStage.permission ||
      _AddCameraStage.searching => Align(
        alignment: Alignment.topCenter,
        child: CameraDiscoveryAnimation(
          state: CameraDiscoveryVisualState.searching,
          size: animSize,
          showDevice: false,
        ),
      ),
      _AddCameraStage.found || _AddCameraStage.connecting => Align(
        alignment: Alignment.topCenter,
        child: SizedBox(
          width: double.infinity,
          child: FadeTransition(
            opacity: foundFade,
            child: SlideTransition(
              position: foundSlide,
              child: _DiscoveredDeviceTile(
                statusLabel: stage == _AddCameraStage.connecting
                    ? '连接中'
                    : '可连接',
                connecting: stage == _AddCameraStage.connecting,
              ),
            ),
          ),
        ),
      ),
      _AddCameraStage.success => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.check_rounded,
          title: '已加入家庭看护空间。',
          tone: _MessageTone.success,
        ),
      ),
      _AddCameraStage.notFound => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.search_off_rounded,
          title: '确认摄像头已通电并靠近手机。',
          tone: _MessageTone.warning,
        ),
      ),
      _AddCameraStage.failed => const Align(
        alignment: Alignment.center,
        child: _SheetMessage(
          icon: Icons.wifi_off_rounded,
          title: '可以重新搜索或稍后再试。',
          tone: _MessageTone.danger,
        ),
      ),
    };
  }
}

class _DiscoveredDeviceTile extends StatefulWidget {
  const _DiscoveredDeviceTile({
    required this.statusLabel,
    this.connecting = false,
  });

  final String statusLabel;
  final bool connecting;

  @override
  State<_DiscoveredDeviceTile> createState() => _DiscoveredDeviceTileState();
}

class _DiscoveredDeviceTileState extends State<_DiscoveredDeviceTile>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ringController;

  @override
  void initState() {
    super.initState();
    _ringController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat();
  }

  @override
  void dispose() {
    _ringController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final statusColor = widget.connecting ? AppColors.brand : AppColors.success;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(AppRadii.cardLarge),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.surfaceElevated,
            AppColors.brandSageWash.withValues(alpha: 0.35),
          ],
        ),
        border: Border.all(
          color: widget.connecting
              ? AppColors.brand.withValues(alpha: 0.28)
              : AppColors.brandSage.withValues(alpha: 0.26),
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.brandSage.withValues(alpha: 0.1),
            blurRadius: 16,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadii.cardLarge),
        child: Stack(
          children: [
            Positioned(
              left: 0,
              top: 10,
              bottom: 10,
              child: Container(
                width: 3,
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              child: Row(
                children: [
                  SizedBox(
                    width: 58,
                    height: 58,
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        if (!reduceMotion)
                          AnimatedBuilder(
                            animation: _ringController,
                            builder: (context, _) => CustomPaint(
                              size: const Size.square(58),
                              painter: DiscoveryIconRingPainter(
                                progress: _ringController.value,
                                active: !widget.connecting,
                              ),
                            ),
                          ),
                        CameraDeviceGlyph(
                          size: 48,
                          compact: true,
                          statusLightColor: statusColor,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          kSetupDefaultDeviceName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.ink,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 15,
                            fontWeight: FontWeight.w900,
                            height: 1.2,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          children: [
                            _SignalBars(
                              active: widget.connecting ? 3 : 4,
                              color: widget.connecting
                                  ? AppColors.brand
                                  : AppColors.brandSage,
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                widget.connecting
                                    ? '正在建立安全连接'
                                    : '信号良好 · ${widget.statusLabel}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  color: AppColors.muted,
                                  fontFamily: AppTypography.systemFont,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  height: 1.2,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 6),
                  if (widget.connecting)
                    const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppColors.brand,
                      ),
                    )
                  else
                    Icon(
                      Icons.arrow_forward_ios_rounded,
                      size: 14,
                      color: AppColors.muted.withValues(alpha: 0.7),
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

class _SignalBars extends StatelessWidget {
  const _SignalBars({required this.active, required this.color});

  final int active;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(4, (index) {
        final on = index < active;
        return Container(
          width: 3,
          height: 6 + index * 3,
          margin: const EdgeInsets.only(right: 2),
          decoration: BoxDecoration(
            color: on ? color : AppColors.border,
            borderRadius: BorderRadius.circular(1),
          ),
        );
      }),
    );
  }
}

enum _MessageTone { success, warning, danger }

class _SheetMessage extends StatelessWidget {
  const _SheetMessage({
    required this.icon,
    required this.title,
    required this.tone,
  });

  final IconData icon;
  final String title;
  final _MessageTone tone;

  @override
  Widget build(BuildContext context) {
    final colors = switch (tone) {
      _MessageTone.success => (
        bg: AppColors.successWash,
        fg: AppColors.success,
      ),
      _MessageTone.warning => (
        bg: AppColors.warningWash,
        fg: AppColors.warning,
      ),
      _MessageTone.danger => (
        bg: AppColors.dangerWash,
        fg: AppColors.danger,
      ),
    };
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 58,
          height: 58,
          decoration: BoxDecoration(
            color: colors.bg,
            borderRadius: BorderRadius.circular(21),
          ),
          child: Icon(icon, color: colors.fg, size: 29),
        ),
        const SizedBox(height: 14),
        Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 14,
            fontWeight: FontWeight.w700,
            height: 1.42,
          ),
        ),
      ],
    );
  }
}

class _SheetActions extends StatelessWidget {
  const _SheetActions({
    required this.stage,
    required this.onConnect,
    required this.onRetry,
    required this.onFinish,
    required this.onHelp,
  });

  final _AddCameraStage stage;
  final VoidCallback onConnect;
  final VoidCallback onRetry;
  final VoidCallback onFinish;
  final VoidCallback onHelp;

  @override
  Widget build(BuildContext context) {
    return switch (stage) {
      _AddCameraStage.ready ||
      _AddCameraStage.permission ||
      _AddCameraStage.searching => Padding(
        padding: const EdgeInsets.only(top: 6),
        child: _HelpLink(onTap: onHelp),
      ),
      _AddCameraStage.found => AppPrimaryButton(label: '连接', onTap: onConnect),
      _AddCameraStage.connecting => const AppPrimaryButton(
        label: '正在连接',
        onTap: null,
        loading: true,
      ),
      _AddCameraStage.success => AppPrimaryButton(label: '完成', onTap: onFinish),
      _AddCameraStage.notFound => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppPrimaryButton(label: '重新搜索', onTap: onRetry),
          const SizedBox(height: 10),
          _HelpLink(onTap: onHelp),
        ],
      ),
      _AddCameraStage.failed => AppPrimaryButton(label: '重新搜索', onTap: onRetry),
    };
  }
}

class _HelpLink extends StatelessWidget {
  const _HelpLink({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: TextButton(
        onPressed: onTap,
        style: TextButton.styleFrom(
          foregroundColor: AppColors.muted,
          minimumSize: const Size(96, 40),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: const Text(
          '连接帮助',
          style: TextStyle(
            fontFamily: AppTypography.systemFont,
            fontSize: 13,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

void _refreshCameraAfterAdd(WidgetRef ref) {
  ref
    ..invalidate(devicesProvider)
    ..invalidate(primaryDeviceOverviewProvider)
    ..invalidate(selectedDeviceProvider)
    ..invalidate(cameraHealthProvider)
    ..invalidate(cameraRuntimeProvider)
    ..invalidate(cameraStatusProvider)
    ..invalidate(cameraMonitorStatusProvider)
    ..invalidate(cameraSnapshotProvider)
    ..invalidate(cameraEventsProvider)
    ..invalidate(liveCareStatusProvider)
    ..invalidate(profileSummaryProvider)
    ..invalidate(accountProfileProvider);
}

/// Deep-link fallback: transparent page that presents the sheet immediately.
class AddCameraRouteScreen extends StatefulWidget {
  const AddCameraRouteScreen({super.key});

  @override
  State<AddCameraRouteScreen> createState() => _AddCameraRouteScreenState();
}

class _AddCameraRouteScreenState extends State<AddCameraRouteScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await showAddCameraSheet(context);
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Colors.transparent,
      body: SizedBox.shrink(),
    );
  }
}

/// Setup flow entry: presents sheet and pops setup route when finished.
class DeviceEntrySetupScreen extends StatefulWidget {
  const DeviceEntrySetupScreen({super.key});

  @override
  State<DeviceEntrySetupScreen> createState() => _DeviceEntrySetupScreenState();
}

class _DeviceEntrySetupScreenState extends State<DeviceEntrySetupScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await showAddCameraSheet(context);
      if (mounted) Navigator.of(context).pop();
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: AppColors.appBackgroundWarm,
      body: SizedBox.shrink(),
    );
  }
}
