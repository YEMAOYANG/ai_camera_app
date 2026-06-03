import 'package:flutter/material.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';

class MiraPrimaryButton extends StatelessWidget {
  const MiraPrimaryButton({
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
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.button),
            border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                if (enabled || loading) ...[
                  AppColors.primaryButtonStart,
                  AppColors.primaryButtonEnd,
                ] else ...[
                  AppColors.muted.withValues(alpha: 0.54),
                  AppColors.muted.withValues(alpha: 0.40),
                ],
              ],
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.primaryButtonShadow.withValues(
                  alpha: enabled || loading ? 0.24 : 0.06,
                ),
                blurRadius: 24,
                offset: const Offset(0, 15),
              ),
            ],
          ),
          child: Stack(
            children: [
              Positioned(
                left: 18,
                right: 18,
                top: 1,
                height: 1,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        Colors.white.withValues(alpha: 0),
                        Colors.white.withValues(alpha: 0.42),
                        Colors.white.withValues(alpha: 0),
                      ],
                    ),
                  ),
                ),
              ),
              const Positioned(
                left: -80,
                top: -70,
                width: 210,
                height: 160,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      colors: [Color(0x183B82F6), Color(0x003B82F6)],
                    ),
                  ),
                ),
              ),
              SizedBox(
                height: 56,
                width: double.infinity,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      label,
                      style: TextStyle(
                        color: Colors.white,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                    if (loading || trailing != null) ...[
                      const SizedBox(width: 9),
                      loading ? const MiraButtonSpinner() : trailing!,
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

class MiraSecondaryButton extends StatelessWidget {
  const MiraSecondaryButton({
    required this.label,
    required this.onTap,
    this.trailing,
    super.key,
  });

  final String label;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return _TapScale(
      onTap: enabled ? onTap : null,
      child: Opacity(
        opacity: enabled ? 1 : 0.58,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadii.buttonSecondary),
            border: Border.all(color: Colors.white.withValues(alpha: 0.7)),
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Colors.white.withValues(alpha: 0.78),
                Colors.white.withValues(alpha: 0.54),
              ],
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(
                  0xFF4C6685,
                ).withValues(alpha: enabled ? 0.07 : 0.03),
                blurRadius: 18,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: SizedBox(
            height: 50,
            width: double.infinity,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
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

class MiraButtonGlyph extends StatelessWidget {
  const MiraButtonGlyph({required this.icon, super.key});

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
        width: 22,
        height: 22,
        child: Center(child: Icon(icon, color: Colors.white, size: 15)),
      ),
    );
  }
}

class MiraButtonSpinner extends StatelessWidget {
  const MiraButtonSpinner({super.key});

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        color: Color(0x1AFFFFFF),
        borderRadius: BorderRadius.all(Radius.circular(AppRadii.full)),
      ),
      child: SizedBox(
        width: 22,
        height: 22,
        child: Center(
          child: SizedBox(
            width: 13,
            height: 13,
            child: CircularProgressIndicator(
              strokeWidth: 2,
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
        duration: AppMotion.duration(context, 180),
        curve: Curves.easeOutCubic,
        child: widget.child,
      ),
    );
  }
}
