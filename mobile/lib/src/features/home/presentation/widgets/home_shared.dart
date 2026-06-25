import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/home/domain/home_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

IconData homeChipIcon(HomeChipKind kind) {
  return switch (kind) {
    HomeChipKind.device => Icons.sensors_outlined,
    HomeChipKind.stage => Icons.school_outlined,
    HomeChipKind.pending => Icons.fact_check_outlined,
    HomeChipKind.rhythm => Icons.event_outlined,
    HomeChipKind.profile => Icons.person_outline,
  };
}

Color homeToneColor(StatusTone tone) {
  return switch (tone) {
    StatusTone.success => AppColors.success,
    StatusTone.warning => AppColors.warning,
    StatusTone.danger => AppColors.danger,
    StatusTone.neutral => AppColors.ink,
  };
}

Color homeToneWash(StatusTone tone) {
  return switch (tone) {
    StatusTone.success => AppColors.successWash.withValues(alpha: 0.78),
    StatusTone.warning => AppColors.warningWash.withValues(alpha: 0.74),
    StatusTone.danger => AppColors.dangerWash.withValues(alpha: 0.72),
    StatusTone.neutral => AppColors.surfaceTinted,
  };
}

class HomePressable extends StatefulWidget {
  const HomePressable({super.key, required this.child, required this.onTap});

  final Widget child;
  final VoidCallback onTap;

  @override
  State<HomePressable> createState() => _HomePressableState();
}

class _HomePressableState extends State<HomePressable> {
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

class HomeSoftPanel extends StatelessWidget {
  const HomeSoftPanel({
    super.key,
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
        color: homeToneWash(tone),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: homeToneColor(tone).withValues(alpha: 0.10)),
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

class HomeSectionTitle extends StatelessWidget {
  const HomeSectionTitle({
    super.key,
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String? subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
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
              if (subtitle != null) ...[
                const SizedBox(height: 4),
                Text(
                  subtitle!,
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
            ],
          ),
        ),
        if (actionLabel != null && onAction != null)
          HomePressable(
            onTap: onAction!,
            child: Semantics(
              button: true,
              label: actionLabel,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                child: Text(
                  actionLabel!,
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
          ),
      ],
    );
  }
}

class HomeToneIcon extends StatelessWidget {
  const HomeToneIcon({super.key, required this.icon, required this.tone});

  final IconData icon;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final color = homeToneColor(tone);
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
