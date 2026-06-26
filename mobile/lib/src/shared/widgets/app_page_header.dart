import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

class AppHeroPanel extends StatelessWidget {
  const AppHeroPanel({
    required this.child,
    this.dark = false,
    this.padding = const EdgeInsets.all(AppSpacing.pageHeroPadding),
    this.colors,
    this.borderColor,
    this.onTap,
    super.key,
  });

  final Widget child;
  final bool dark;
  final EdgeInsetsGeometry padding;
  final List<Color>? colors;
  final Color? borderColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final panel = ClipRRect(
      borderRadius: BorderRadius.circular(AppRadii.hero),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: dark ? AppColors.ink : AppColors.surfaceSoft,
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors:
                colors ??
                (dark
                    ? const [Color(0xFF17243A), Color(0xFF101827)]
                    : const [Color(0xF7FFFFFF), Color(0xEAF1F6F8)]),
          ),
          border: Border.all(
            color:
                borderColor ??
                (dark
                    ? Colors.white.withValues(alpha: 0.08)
                    : AppColors.borderSoft),
          ),
        ),
        child: Stack(
          children: [
            if (dark)
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      center: const Alignment(0.75, -0.85),
                      radius: 1.2,
                      colors: [
                        AppColors.brandSage.withValues(alpha: 0.32),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              )
            else
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: RadialGradient(
                      center: const Alignment(0.8, -0.7),
                      radius: 1.1,
                      colors: [
                        AppColors.brandSage.withValues(alpha: 0.13),
                        Colors.transparent,
                      ],
                    ),
                  ),
                ),
              ),
            Padding(padding: padding, child: child),
          ],
        ),
      ),
    );

    if (onTap == null) return panel;
    return _Pressable(onTap: onTap, child: panel);
  }
}

class AppHeroIconButton extends StatelessWidget {
  const AppHeroIconButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.dark = false,
    super.key,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool dark;

  @override
  Widget build(BuildContext context) {
    return _Pressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: label,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: dark
                ? Colors.white.withValues(alpha: 0.12)
                : Colors.white.withValues(alpha: 0.70),
            borderRadius: BorderRadius.circular(15),
            border: Border.all(
              color: dark
                  ? Colors.white.withValues(alpha: 0.10)
                  : AppColors.ink.withValues(alpha: 0.05),
            ),
          ),
          child: SizedBox(
            width: AppControls.minTouchTarget,
            height: AppControls.minTouchTarget,
            child: Center(
              child: Icon(
                icon,
                color: dark ? Colors.white : AppColors.ink,
                size: 19,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppQuickAction {
  const AppQuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color = AppColors.ink,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color color;
}

class AppQuickActionRow extends StatelessWidget {
  const AppQuickActionRow({
    required this.actions,
    this.dark = false,
    super.key,
  });

  final List<AppQuickAction> actions;
  final bool dark;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var index = 0; index < actions.length; index++) ...[
          Expanded(
            child: _QuickActionButton(action: actions[index], dark: dark),
          ),
          if (index != actions.length - 1) const SizedBox(width: 7),
        ],
      ],
    );
  }
}

class _QuickActionButton extends StatelessWidget {
  const _QuickActionButton({required this.action, required this.dark});

  final AppQuickAction action;
  final bool dark;

  @override
  Widget build(BuildContext context) {
    return _Pressable(
      onTap: action.onTap,
      child: Semantics(
        button: true,
        label: action.label,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: dark
                ? Colors.white.withValues(alpha: 0.11)
                : Colors.white.withValues(alpha: 0.76),
            borderRadius: BorderRadius.circular(17),
            border: Border.all(
              color: dark
                  ? Colors.white.withValues(alpha: 0.09)
                  : AppColors.ink.withValues(alpha: 0.045),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 9),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  action.icon,
                  color: dark ? Colors.white : action.color,
                  size: 20,
                ),
                const SizedBox(height: 6),
                Text(
                  action.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: dark
                        ? Colors.white.withValues(alpha: 0.86)
                        : AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 10.5,
                    fontWeight: FontWeight.w800,
                    height: 1.1,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Pressable extends StatefulWidget {
  const _Pressable({required this.child, required this.onTap});

  final Widget child;
  final VoidCallback? onTap;

  @override
  State<_Pressable> createState() => _PressableState();
}

class _PressableState extends State<_Pressable> {
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
