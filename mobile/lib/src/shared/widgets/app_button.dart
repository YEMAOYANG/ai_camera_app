import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

class AppPrimaryButton extends StatelessWidget {
  const AppPrimaryButton({
    required this.label,
    required this.onTap,
    this.loading = false,
    this.trailing,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final bool loading;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null && !loading;
    return _TapScale(
      onTap: enabled ? onTap : null,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadii.button),
        child: DecoratedBox(
          // One flat ink fill: the primary action is the only dark block on a
          // page, so it needs no gradient or sheen to stand out.
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.button),
            color: enabled || loading
                ? AppColors.primaryButtonStart
                : AppColors.disabledFill,
            boxShadow: [
              if (enabled || loading)
                BoxShadow(
                  color: AppColors.primaryButtonShadow.withValues(alpha: 0.14),
                  blurRadius: 12,
                  offset: const Offset(0, 5),
                ),
            ],
          ),
          child: Stack(
            children: [
              SizedBox(
                height: AppControls.buttonHeight,
                width: double.infinity,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        color: enabled || loading
                            ? AppColors.onPrimary
                            : AppColors.disabledInk,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                    if (loading || trailing != null) ...[
                      const SizedBox(width: 8),
                      loading ? const AppButtonSpinner() : trailing!,
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class AppSecondaryButton extends StatelessWidget {
  const AppSecondaryButton({
    required this.label,
    required this.onTap,
    this.trailing,
    this.height = AppControls.compactButtonHeight,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final Widget? trailing;
  final double height;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return _TapScale(
      onTap: enabled ? onTap : null,
      child: Opacity(
        opacity: enabled ? 1 : 0.58,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceElevated,
            borderRadius: BorderRadius.circular(AppRadii.buttonSecondary),
            border: Border.all(color: AppColors.border),
          ),
          child: SizedBox(
            height: height,
            width: double.infinity,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: enabled ? AppColors.ink : AppColors.disabledInk,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                  ),
                ),
                if (trailing != null) ...[const SizedBox(width: 8), trailing!],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class AppDangerButton extends StatelessWidget {
  const AppDangerButton({
    required this.label,
    required this.onTap,
    this.trailing,
    this.height = AppControls.buttonHeight,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final Widget? trailing;
  final double height;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return _TapScale(
      onTap: enabled ? onTap : null,
      child: Opacity(
        opacity: enabled ? 1 : 0.58,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.dangerWash,
            borderRadius: BorderRadius.circular(AppRadii.buttonSecondary),
            border: Border.all(color: AppColors.danger.withValues(alpha: 0.16)),
            boxShadow: [
              if (enabled)
                BoxShadow(
                  color: AppColors.danger.withValues(alpha: 0.05),
                  blurRadius: 9,
                  offset: const Offset(0, 5),
                ),
            ],
          ),
          child: SizedBox(
            height: height,
            width: double.infinity,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: enabled ? AppColors.danger : AppColors.disabledInk,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
                if (trailing != null) ...[
                  const SizedBox(width: 8),
                  IconTheme.merge(
                    data: IconThemeData(
                      color: enabled ? AppColors.danger : AppColors.disabledInk,
                      size: 18,
                    ),
                    child: trailing!,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class AppButtonGlyph extends StatelessWidget {
  const AppButtonGlyph({required this.icon, super.key});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: SizedBox(
        width: 20,
        height: 20,
        child: Center(child: Icon(icon, color: Colors.white, size: 14)),
      ),
    );
  }
}

class AppButtonSpinner extends StatelessWidget {
  const AppButtonSpinner({super.key});

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        color: Color(0x1AFFFFFF),
        borderRadius: BorderRadius.all(Radius.circular(AppRadii.full)),
      ),
      child: SizedBox(
        width: 20,
        height: 20,
        child: Center(
          child: SizedBox(
            width: 12,
            height: 12,
            child: CircularProgressIndicator(
              strokeWidth: 1.8,
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
              backgroundColor: Color(0x55FFFFFF),
            ),
          ),
        ),
      ),
    );
  }
}

class _TapScale extends StatefulWidget {
  const _TapScale({required this.child, required this.onTap});

  final Widget child;
  final VoidCallback? onTap;

  @override
  State<_TapScale> createState() => _TapScaleState();
}

class _TapScaleState extends State<_TapScale> {
  var _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.of(context).disableAnimations
        ? 1.0
        : (_pressed ? AppMotion.buttonPressScale : 1.0);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      onTapDown: widget.onTap == null
          ? null
          : (_) => setState(() => _pressed = true),
      onTapCancel: widget.onTap == null
          ? null
          : () => setState(() => _pressed = false),
      onTapUp: widget.onTap == null
          ? null
          : (_) => setState(() => _pressed = false),
      child: AnimatedScale(
        scale: scale,
        duration: AppMotion.duration(context, 150),
        curve: Curves.easeOutCubic,
        child: widget.child,
      ),
    );
  }
}
