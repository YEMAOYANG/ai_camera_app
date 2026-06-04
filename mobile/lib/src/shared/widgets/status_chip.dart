import 'package:flutter/material.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/home/domain/guardian_snapshot.dart';

enum StatusTone { neutral, success, warning, danger }

class StatusChip extends StatelessWidget {
  const StatusChip({
    required this.label,
    this.tone = StatusTone.neutral,
    super.key,
  });

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final colors = _colors(context, tone);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colors.border),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        child: Text(
          label,
          style: TextStyle(
            color: colors.foreground,
            fontSize: 11.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  _ChipColors _colors(BuildContext context, StatusTone tone) {
    final scheme = Theme.of(context).colorScheme;

    return switch (tone) {
      StatusTone.success => _ChipColors(
        background: AppColors.successWash,
        foreground: AppColors.success,
        border: AppColors.success.withValues(alpha: 0.10),
      ),
      StatusTone.warning => _ChipColors(
        background: AppColors.warningWash,
        foreground: AppColors.warning,
        border: AppColors.warning.withValues(alpha: 0.12),
      ),
      StatusTone.danger => _ChipColors(
        background: AppColors.dangerWash,
        foreground: AppColors.danger,
        border: AppColors.danger.withValues(alpha: 0.10),
      ),
      StatusTone.neutral => _ChipColors(
        background: AppColors.surfaceSoft,
        foreground: scheme.onSurfaceVariant,
        border: AppColors.borderSoft,
      ),
    };
  }
}

class StatusToneMapper {
  const StatusToneMapper._();

  static const watchLevel = AttentionLevel.watch;

  static Color colorFor(BuildContext context, AttentionLevel level) {
    final scheme = Theme.of(context).colorScheme;

    return switch (level) {
      AttentionLevel.normal => scheme.primary,
      AttentionLevel.watch => AppColors.warning,
      AttentionLevel.urgent => scheme.error,
    };
  }
}

class _ChipColors {
  const _ChipColors({
    required this.background,
    required this.foreground,
    required this.border,
  });

  final Color background;
  final Color foreground;
  final Color border;
}
