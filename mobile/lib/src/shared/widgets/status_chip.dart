import 'package:flutter/material.dart';
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
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        child: Text(
          label,
          style: TextStyle(
            color: colors.foreground,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }

  _ChipColors _colors(BuildContext context, StatusTone tone) {
    final scheme = Theme.of(context).colorScheme;

    return switch (tone) {
      StatusTone.success => const _ChipColors(
        background: Color(0xFFE3F4EA),
        foreground: Color(0xFF236044),
      ),
      StatusTone.warning => const _ChipColors(
        background: Color(0xFFFFF1D8),
        foreground: Color(0xFF8A5A00),
      ),
      StatusTone.danger => const _ChipColors(
        background: Color(0xFFFFE0E0),
        foreground: Color(0xFF8E2D2D),
      ),
      StatusTone.neutral => _ChipColors(
        background: scheme.surfaceContainerHighest,
        foreground: scheme.onSurfaceVariant,
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
      AttentionLevel.watch => const Color(0xFF9A6500),
      AttentionLevel.urgent => scheme.error,
    };
  }
}

class _ChipColors {
  const _ChipColors({required this.background, required this.foreground});

  final Color background;
  final Color foreground;
}
