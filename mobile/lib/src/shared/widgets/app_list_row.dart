import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

class AppListRow extends StatelessWidget {
  const AppListRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    this.trailing,
    this.tone = AppListRowTone.neutral,
    this.onTap,
    this.subtitleMaxLines = 2,
    super.key,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final Widget? trailing;
  final AppListRowTone tone;
  final VoidCallback? onTap;
  final int subtitleMaxLines;

  @override
  Widget build(BuildContext context) {
    final color = switch (tone) {
      AppListRowTone.blue => AppColors.brand,
      AppListRowTone.green => AppColors.success,
      AppListRowTone.amber => AppColors.warning,
      AppListRowTone.red => AppColors.danger,
      AppListRowTone.neutral => AppColors.ink,
    };

    final child = Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(13),
            ),
            child: SizedBox(
              width: 38,
              height: 38,
              child: Center(child: Icon(icon, color: color, size: 19)),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    height: 1.25,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  maxLines: subtitleMaxLines,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    height: 1.42,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          if (trailing != null) ...[const SizedBox(width: 10), trailing!],
          if (onTap != null && trailing == null) ...[
            const SizedBox(width: 8),
            const Icon(Icons.chevron_right, color: AppColors.muted, size: 18),
          ],
        ],
      ),
    );

    if (onTap == null) return child;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: child,
    );
  }
}

enum AppListRowTone { neutral, blue, green, amber, red }
