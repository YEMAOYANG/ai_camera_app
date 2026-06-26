import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/setup/presentation/discovery_scene.dart';

export 'discovery_scene.dart' show CameraDiscoveryVisualState;

class CameraDiscoveryAnimation extends StatefulWidget {
  const CameraDiscoveryAnimation({
    super.key,
    required this.state,
    this.size = 252,
    this.showDevice = true,
  });

  final CameraDiscoveryVisualState state;
  final double size;
  final bool showDevice;

  @override
  State<CameraDiscoveryAnimation> createState() =>
      _CameraDiscoveryAnimationState();
}

class _CameraDiscoveryAnimationState extends State<CameraDiscoveryAnimation>
    with TickerProviderStateMixin {
  late final AnimationController _loopController;
  late final AnimationController _transitionController;
  late final AnimationController _confirmController;
  late final AnimationController _deviceRevealController;

  bool get _shouldLoop {
    return switch (widget.state) {
      CameraDiscoveryVisualState.searching ||
      CameraDiscoveryVisualState.found ||
      CameraDiscoveryVisualState.connecting => true,
      _ => false,
    };
  }

  bool get _showsDevice {
    if (!widget.showDevice) return false;
    return widget.state != CameraDiscoveryVisualState.searching;
  }

  @override
  void initState() {
    super.initState();
    _loopController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    );
    _transitionController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 320),
    );
    _confirmController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 520),
    );
    _deviceRevealController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 380),
    );
    if (widget.state == CameraDiscoveryVisualState.found) {
      _transitionController.value = 1;
      _deviceRevealController.value = 1;
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncLoop();
  }

  @override
  void didUpdateWidget(CameraDiscoveryAnimation oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) {
      _handleStateChange(oldWidget.state, widget.state);
    }
    _syncLoop();
  }

  void _handleStateChange(
    CameraDiscoveryVisualState from,
    CameraDiscoveryVisualState to,
  ) {
    if (to == CameraDiscoveryVisualState.found &&
        from == CameraDiscoveryVisualState.searching) {
      _transitionController.forward(from: 0);
      _confirmController.forward(from: 0);
      _deviceRevealController.forward(from: 0);
    } else if (to == CameraDiscoveryVisualState.searching) {
      _transitionController.reverse();
      _confirmController.reset();
      _deviceRevealController.reverse();
    } else if (to != CameraDiscoveryVisualState.found) {
      _confirmController.reset();
    }
  }

  void _syncLoop() {
    final reduceMotion =
        MediaQuery.maybeOf(context)?.disableAnimations ?? false;
    if (_shouldLoop && !reduceMotion) {
      if (!_loopController.isAnimating) _loopController.repeat();
    } else {
      _loopController.stop();
    }
  }

  @override
  void dispose() {
    _loopController.dispose();
    _transitionController.dispose();
    _confirmController.dispose();
    _deviceRevealController.dispose();
    super.dispose();
  }

  double get _deviceScale {
    if (!_showsDevice) return 1;
    final reveal = _deviceRevealController.value;
    final breath = widget.state == CameraDiscoveryVisualState.searching
        ? 0.98 + math.sin(_loopController.value * math.pi * 2) * 0.02
        : 1.0;
    if (widget.state == CameraDiscoveryVisualState.found) {
      final pulse = 1.0 + _confirmController.value * 0.04;
      return (0.82 + reveal * 0.18) * breath * pulse;
    }
    return (0.82 + reveal * 0.18) * breath;
  }

  Color get _statusLightColor {
    return switch (widget.state) {
      CameraDiscoveryVisualState.success => AppColors.success,
      CameraDiscoveryVisualState.failed => AppColors.danger,
      CameraDiscoveryVisualState.notFound => AppColors.warning,
      CameraDiscoveryVisualState.connecting => AppColors.brand,
      _ => AppColors.brandWarm,
    };
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return Semantics(
      image: true,
      label: _semanticsLabel(widget.state),
      child: SizedBox.square(
        dimension: widget.size,
        child: AnimatedBuilder(
          animation: Listenable.merge([
            _loopController,
            _transitionController,
            _confirmController,
            _deviceRevealController,
          ]),
          builder: (context, _) {
            final progress = reduceMotion ? 0.0 : _loopController.value;
            final collapse = reduceMotion
                ? (widget.state == CameraDiscoveryVisualState.found ? 1.0 : 0.0)
                : _transitionController.value;
            final confirmPulse = reduceMotion ? 0.0 : _confirmController.value;
            final deviceOpacity = _showsDevice
                ? (_deviceRevealController.value.clamp(0.0, 1.0))
                : 0.0;
            return Stack(
              alignment: Alignment.center,
              children: [
                CustomPaint(
                  size: Size.square(widget.size),
                  painter: DiscoverySonarPainter(
                    state: widget.state,
                    progress: progress,
                    collapseProgress: collapse,
                    confirmPulse: confirmPulse,
                  ),
                ),
                if (deviceOpacity > 0)
                  Opacity(
                    opacity: deviceOpacity,
                    child: Transform.scale(
                      scale: _deviceScale,
                      child: CustomPaint(
                        size: Size.square(widget.size * 0.52),
                        painter: CameraDevicePainter(
                          scale: 1,
                          statusLightColor: _statusLightColor,
                          showLensRing:
                              widget.state ==
                              CameraDiscoveryVisualState.connecting,
                          lensRingProgress: progress,
                        ),
                      ),
                    ),
                  ),
                if (widget.state == CameraDiscoveryVisualState.success)
                  _StateAccentIcon(
                    icon: Icons.check_rounded,
                    color: AppColors.success,
                    size: widget.size,
                  ),
                if (widget.state == CameraDiscoveryVisualState.failed)
                  _StateAccentIcon(
                    icon: Icons.error_outline_rounded,
                    color: AppColors.danger,
                    size: widget.size,
                  ),
                if (widget.state == CameraDiscoveryVisualState.notFound)
                  _StateAccentIcon(
                    icon: Icons.travel_explore_rounded,
                    color: AppColors.warning,
                    size: widget.size,
                  ),
              ],
            );
          },
        ),
      ),
    );
  }

  String _semanticsLabel(CameraDiscoveryVisualState state) {
    return switch (state) {
      CameraDiscoveryVisualState.ready => '准备发现附近的看护摄像头',
      CameraDiscoveryVisualState.permission => '正在准备附近设备权限',
      CameraDiscoveryVisualState.searching => '正在发现附近的看护摄像头',
      CameraDiscoveryVisualState.found => '已发现附近的看护摄像头',
      CameraDiscoveryVisualState.connecting => '正在建立安全连接',
      CameraDiscoveryVisualState.success => '看护摄像头已连接',
      CameraDiscoveryVisualState.notFound => '没有找到看护摄像头',
      CameraDiscoveryVisualState.failed => '看护摄像头连接失败',
    };
  }
}

class CameraDeviceGlyph extends StatelessWidget {
  const CameraDeviceGlyph({
    super.key,
    this.size = 72,
    this.statusLightColor = AppColors.brandWarm,
    this.elevated = true,
    this.compact = false,
  });

  final double size;
  final Color statusLightColor;
  final bool elevated;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (compact) {
      return SizedBox.square(
        dimension: size,
        child: DecoratedBox(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              colors: [
                AppColors.surfaceElevated,
                AppColors.brandSageWash.withValues(alpha: 0.5),
              ],
            ),
            border: Border.all(
              color: AppColors.brandSage.withValues(alpha: 0.18),
            ),
          ),
          child: CustomPaint(
            painter: CameraDevicePainter(
              scale: 0.86,
              statusLightColor: statusLightColor,
              elevated: false,
            ),
          ),
        ),
      );
    }
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(
        painter: CameraDevicePainter(
          scale: 1,
          statusLightColor: statusLightColor,
          elevated: elevated,
        ),
      ),
    );
  }
}

class _StateAccentIcon extends StatelessWidget {
  const _StateAccentIcon({
    required this.icon,
    required this.color,
    required this.size,
  });

  final IconData icon;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      right: size * 0.08,
      top: size * 0.1,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Padding(
          padding: const EdgeInsets.all(6),
          child: Icon(icon, color: color, size: 22),
        ),
      ),
    );
  }
}
