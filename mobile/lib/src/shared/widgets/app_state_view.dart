import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';

enum AppStateVariant {
  serviceUnavailable,
  networkUnavailable,
  deviceOffline,
  cameraUnavailable,
  emptyTasks,
  emptyRewards,
  emptyLedger,
  searchEmpty,
  loading,
  saveFailed,
  saved,
  permission,
  noData,
}

class AppStateAssets {
  const AppStateAssets._();

  static const serviceUnavailable =
      'assets/images/states/service-unavailable.png';
  static const emptyTasks = 'assets/images/states/empty-tasks.png';
  static const deviceOffline = 'assets/images/states/device-offline.png';
  static const emptyRewards = 'assets/images/states/empty-rewards.png';
  static const searchEmpty = 'assets/images/states/search-empty.png';
  static const successSaved = 'assets/images/states/success-saved.png';
}

class AppStateView extends StatelessWidget {
  const AppStateView({
    required this.variant,
    required this.title,
    required this.message,
    this.illustrationAsset,
    this.primaryActionLabel,
    this.onPrimaryAction,
    this.primaryActionIcon,
    this.secondaryActionLabel,
    this.onSecondaryAction,
    this.compact = false,
    this.padding,
    super.key,
  });

  final AppStateVariant variant;
  final String title;
  final String message;
  final String? illustrationAsset;
  final String? primaryActionLabel;
  final VoidCallback? onPrimaryAction;
  final IconData? primaryActionIcon;
  final String? secondaryActionLabel;
  final VoidCallback? onSecondaryAction;
  final bool compact;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final accent = variant._accent;

    final content = LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth.isFinite
            ? constraints.maxWidth
            : MediaQuery.sizeOf(context).width - 40;
        final primaryIcon = _primaryIcon;
        final artSize = (compact ? width * 0.34 : width * 0.48)
            .clamp(compact ? 78.0 : 118.0, compact ? 112.0 : 174.0)
            .toDouble();
        final buttonWidth = math.min(width, compact ? 240.0 : 286.0);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _StateIllustrationStage(
              asset: illustrationAsset ?? variant._asset,
              accent: accent,
              size: artSize,
              success: variant == AppStateVariant.saved,
              loading: variant == AppStateVariant.loading,
            ),
            SizedBox(height: compact ? 12 : 16),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: compact ? 16 : 19,
                fontWeight: FontWeight.w800,
                height: 1.22,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            ConstrainedBox(
              constraints: BoxConstraints(maxWidth: math.min(width, 330)),
              child: Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  height: 1.55,
                  letterSpacing: 0,
                ),
              ),
            ),
            if (primaryActionLabel != null || secondaryActionLabel != null)
              SizedBox(height: compact ? 15 : 18),
            if (primaryActionLabel != null)
              SizedBox(
                width: buttonWidth,
                child: AppPrimaryButton(
                  label: primaryActionLabel!,
                  trailing: primaryIcon == null
                      ? null
                      : AppButtonGlyph(icon: primaryIcon),
                  onTap: onPrimaryAction,
                ),
              ),
            if (secondaryActionLabel != null) ...[
              const SizedBox(height: 10),
              SizedBox(
                width: buttonWidth,
                child: AppSecondaryButton(
                  label: secondaryActionLabel!,
                  onTap: onSecondaryAction,
                ),
              ),
            ],
          ],
        );
      },
    );

    if (!compact) {
      return Padding(
        padding: padding ?? const EdgeInsets.fromLTRB(4, 18, 4, 20),
        child: content,
      );
    }

    return AppSurface(
      color: Colors.white.withValues(alpha: 0.34),
      borderColor: Colors.white.withValues(alpha: 0.58),
      radius: 16,
      padding: padding ?? const EdgeInsets.fromLTRB(16, 18, 16, 18),
      child: content,
    );
  }

  IconData? get _primaryIcon {
    return primaryActionIcon ?? variant._primaryIcon;
  }
}

class AppInlineState extends StatelessWidget {
  const AppInlineState({
    required this.variant,
    required this.title,
    required this.message,
    this.actionLabel,
    this.onAction,
    super.key,
  });

  final AppStateVariant variant;
  final String title;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return AppStateView(
      variant: variant,
      title: title,
      message: message,
      primaryActionLabel: actionLabel,
      onPrimaryAction: onAction,
      compact: true,
    );
  }
}

class AppLoadingState extends StatelessWidget {
  const AppLoadingState({
    required this.title,
    this.message = '正在同步最新内容',
    this.rows = 3,
    this.compact = false,
    super.key,
  });

  final String title;
  final String message;
  final int rows;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      padding: EdgeInsets.fromLTRB(
        16,
        compact ? 16 : 20,
        16,
        compact ? 16 : 20,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _SoftPulseDot(size: compact ? 34 : 42),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: compact ? 15 : 16,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      message,
                      style: const TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                        height: 1.45,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: compact ? 14 : 18),
          for (var index = 0; index < rows; index++) ...[
            _SkeletonRow(index: index),
            if (index != rows - 1) const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

void showAppStateSnackBar(
  BuildContext context, {
  required AppStateVariant variant,
  required String title,
  String? message,
}) {
  showAppToast(context, title, message: message, tone: variant._toastTone);
}

class _StateIllustrationStage extends StatelessWidget {
  const _StateIllustrationStage({
    required this.asset,
    required this.accent,
    required this.size,
    required this.success,
    required this.loading,
  });

  final String asset;
  final Color accent;
  final double size;
  final bool success;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final animationDuration = AppMotion.duration(context, 280);

    return SizedBox(
      width: size,
      height: size,
      child: TweenAnimationBuilder<double>(
        tween: Tween(begin: reduceMotion ? 1.0 : 0.0, end: 1.0),
        duration: animationDuration,
        curve: Curves.easeOutCubic,
        builder: (context, value, child) {
          return Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.center,
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      accent.withValues(alpha: 0.16),
                      accent.withValues(alpha: 0.045),
                      accent.withValues(alpha: 0),
                    ],
                  ),
                ),
                child: SizedBox(width: size * 0.86, height: size * 0.86),
              ),
              Opacity(
                opacity: reduceMotion ? 1 : value,
                child: Transform.scale(
                  scale: reduceMotion ? 1 : 0.965 + value * 0.035,
                  child: child,
                ),
              ),
              if (loading)
                Positioned(
                  bottom: size * 0.16,
                  left: size * 0.18,
                  right: size * 0.18,
                  child: _QuietLoadingRail(accent: accent),
                ),
              if (success)
                Positioned(
                  right: size * 0.09,
                  bottom: size * 0.17,
                  child: _SuccessMark(accent: accent),
                ),
            ],
          );
        },
        child: Image.asset(
          asset,
          fit: BoxFit.contain,
          errorBuilder: (context, error, stackTrace) {
            return DecoratedBox(
              decoration: BoxDecoration(
                color: accent.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(26),
              ),
              child: Icon(success ? Icons.check : Icons.info_outline),
            );
          },
        ),
      ),
    );
  }
}

class _QuietLoadingRail extends StatelessWidget {
  const _QuietLoadingRail({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppRadii.full),
      child: SizedBox(
        height: 3,
        child: ColoredBox(color: accent.withValues(alpha: 0.22)),
      ),
    );
  }
}

class _SuccessMark extends StatelessWidget {
  const _SuccessMark({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: accent.withValues(alpha: 0.16)),
        boxShadow: [
          BoxShadow(
            color: accent.withValues(alpha: 0.16),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: SizedBox.square(
        dimension: 32,
        child: Center(child: Icon(Icons.check, color: accent, size: 18)),
      ),
    );
  }
}

class _SoftPulseDot extends StatelessWidget {
  const _SoftPulseDot({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brand.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: Colors.white.withValues(alpha: 0.52)),
      ),
      child: SizedBox(
        width: size,
        height: size,
        child: Center(
          child: Icon(
            Icons.blur_on,
            color: AppColors.brand.withValues(alpha: 0.82),
            size: 18,
          ),
        ),
      ),
    );
  }
}

class _SkeletonRow extends StatelessWidget {
  const _SkeletonRow({required this.index});

  final int index;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.muted.withValues(alpha: 0.10),
            borderRadius: BorderRadius.circular(14),
          ),
          child: const SizedBox(width: 42, height: 42),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              FractionallySizedBox(
                widthFactor: switch (index % 3) {
                  0 => 0.72,
                  1 => 0.56,
                  _ => 0.64,
                },
                child: const _SkeletonBar(height: 13),
              ),
              const SizedBox(height: 8),
              FractionallySizedBox(
                widthFactor: switch (index % 3) {
                  0 => 0.92,
                  1 => 0.78,
                  _ => 0.84,
                },
                child: const _SkeletonBar(height: 10),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _SkeletonBar extends StatelessWidget {
  const _SkeletonBar({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.muted.withValues(alpha: 0.11),
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: SizedBox(height: height, width: double.infinity),
    );
  }
}

extension on AppStateVariant {
  String get _asset {
    return switch (this) {
      AppStateVariant.emptyTasks => AppStateAssets.emptyTasks,
      AppStateVariant.deviceOffline ||
      AppStateVariant.cameraUnavailable ||
      AppStateVariant.permission => AppStateAssets.deviceOffline,
      AppStateVariant.emptyRewards ||
      AppStateVariant.emptyLedger => AppStateAssets.emptyRewards,
      AppStateVariant.searchEmpty => AppStateAssets.searchEmpty,
      AppStateVariant.saved => AppStateAssets.successSaved,
      AppStateVariant.serviceUnavailable ||
      AppStateVariant.networkUnavailable ||
      AppStateVariant.loading ||
      AppStateVariant.saveFailed ||
      AppStateVariant.noData => AppStateAssets.serviceUnavailable,
    };
  }

  Color get _accent {
    return switch (this) {
      AppStateVariant.emptyRewards ||
      AppStateVariant.emptyLedger => const Color(0xFFD8922B),
      AppStateVariant.saved => const Color(0xFF2F8F68),
      AppStateVariant.deviceOffline ||
      AppStateVariant.cameraUnavailable ||
      AppStateVariant.permission => const Color(0xFF58728C),
      AppStateVariant.emptyTasks ||
      AppStateVariant.searchEmpty => AppColors.brand,
      AppStateVariant.serviceUnavailable ||
      AppStateVariant.networkUnavailable ||
      AppStateVariant.loading ||
      AppStateVariant.saveFailed ||
      AppStateVariant.noData => AppColors.brandSoft,
    };
  }

  AppToastTone get _toastTone {
    return switch (this) {
      AppStateVariant.saved => AppToastTone.success,
      AppStateVariant.saveFailed ||
      AppStateVariant.serviceUnavailable ||
      AppStateVariant.networkUnavailable ||
      AppStateVariant.deviceOffline ||
      AppStateVariant.cameraUnavailable => AppToastTone.danger,
      AppStateVariant.permission => AppToastTone.warning,
      AppStateVariant.emptyRewards ||
      AppStateVariant.emptyLedger => AppToastTone.warning,
      AppStateVariant.emptyTasks ||
      AppStateVariant.searchEmpty ||
      AppStateVariant.loading ||
      AppStateVariant.noData => AppToastTone.neutral,
    };
  }

  IconData? get _primaryIcon {
    return switch (this) {
      AppStateVariant.emptyTasks => Icons.add,
      AppStateVariant.saved => Icons.check,
      AppStateVariant.permission => Icons.settings_outlined,
      AppStateVariant.searchEmpty => Icons.search,
      AppStateVariant.serviceUnavailable ||
      AppStateVariant.networkUnavailable ||
      AppStateVariant.deviceOffline ||
      AppStateVariant.cameraUnavailable ||
      AppStateVariant.loading ||
      AppStateVariant.saveFailed ||
      AppStateVariant.emptyRewards ||
      AppStateVariant.emptyLedger ||
      AppStateVariant.noData => Icons.refresh,
    };
  }
}
