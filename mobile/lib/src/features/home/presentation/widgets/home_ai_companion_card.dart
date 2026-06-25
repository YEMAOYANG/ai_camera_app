import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/home/domain/home_models.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_shared.dart';

class HomeRecentObservationCard extends StatelessWidget {
  const HomeRecentObservationCard({
    super.key,
    required this.copy,
    required this.isLoading,
    this.onRefresh,
    this.onOpenLive,
  });

  final RecentObservationCopy copy;
  final bool isLoading;
  final VoidCallback? onRefresh;
  final VoidCallback? onOpenLive;

  @override
  Widget build(BuildContext context) {
    if (!copy.visible && !isLoading) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const HomeSectionTitle(title: '看护概览', subtitle: '只显示可靠的画面记录'),
        const SizedBox(height: 10),
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.aiWash.withValues(alpha: 0.82),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: AppColors.ai.withValues(alpha: 0.12)),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.ai.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(AppRadii.full),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 10,
                      vertical: 5,
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.visibility_outlined,
                          size: 13,
                          color: AppColors.ai,
                        ),
                        const SizedBox(width: 5),
                        Text(
                          '看护说明',
                          style: TextStyle(
                            color: AppColors.ai,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                if (isLoading)
                  Container(
                    width: double.infinity,
                    height: 16,
                    decoration: BoxDecoration(
                      color: AppColors.ai.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(8),
                    ),
                  )
                else ...[
                  Text(
                    copy.headline,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 15,
                      fontWeight: FontWeight.w900,
                      height: 1.25,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    copy.detail,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.45,
                    ),
                  ),
                  if (copy.reminderNote != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      copy.reminderNote!,
                      style: TextStyle(
                        color: AppColors.ai.withValues(alpha: 0.88),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700,
                        height: 1.35,
                      ),
                    ),
                  ],
                  if (copy.showActions &&
                      (onRefresh != null || onOpenLive != null)) ...[
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        if (onRefresh != null)
                          _ObservationAction(
                            label: '刷新观察',
                            icon: Icons.refresh_rounded,
                            onTap: onRefresh!,
                          ),
                        if (onOpenLive != null)
                          _ObservationAction(
                            label: '实时画面',
                            icon: Icons.videocam_outlined,
                            onTap: onOpenLive!,
                          ),
                      ],
                    ),
                  ],
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _ObservationAction extends StatelessWidget {
  const _ObservationAction({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return HomePressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: label,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceElevated.withValues(alpha: 0.78),
            borderRadius: BorderRadius.circular(AppRadii.full),
            border: Border.all(color: AppColors.ai.withValues(alpha: 0.12)),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 14, color: AppColors.ai),
                const SizedBox(width: 5),
                Text(
                  label,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w900,
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
