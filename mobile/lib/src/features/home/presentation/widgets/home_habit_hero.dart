import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_shared.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class HomeHabitHero extends StatelessWidget {
  const HomeHabitHero({
    required this.focus,
    required this.isLoading,
    this.learnerName,
    super.key,
  });

  final HabitFocusCopy focus;
  final bool isLoading;
  final String? learnerName;

  static const _heroImage = 'assets/images/home/home-hero-paper.webp';

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth <= 360;
        final expanded = constraints.maxWidth >= 636;
        final name = learnerName;
        final artWidth = (constraints.maxWidth * (name == null ? .76 : .66))
            .clamp(0.0, expanded ? 245.0 : 410.0);
        final copyWidth =
            ((constraints.maxWidth - AppSpacing.pageHorizontalExpanded * 2) *
                    .68)
                .clamp(0.0, 410.0);
        return ConstrainedBox(
          constraints: BoxConstraints(
            minHeight: constraints.constrainHeight(
              artWidth / (name == null ? 1.5 : 1.58),
            ),
          ),
          child: Stack(
            children: [
              Positioned(
                top: -5,
                right: -10,
                width: artWidth,
                child: Image.asset(
                  _heroImage,
                  excludeFromSemantics: true,
                  fit: BoxFit.fitWidth,
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.pageHorizontalExpanded,
                  16,
                  AppSpacing.pageHorizontalExpanded,
                  16,
                ),
                child: ConstrainedBox(
                  constraints: BoxConstraints(maxWidth: copyWidth),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 8,
                        runSpacing: 4,
                        children: [
                          Text(focus.headerTime, style: _eyebrow),
                          if (name == null) ...[
                            const Text('·', style: _eyebrow),
                            Text(focus.headerTitle, style: _eyebrow),
                          ],
                        ],
                      ),
                      const SizedBox(height: 8),
                      if (isLoading)
                        const _HeroSkeleton()
                      else ...[
                        Text(
                          name == null ? focus.title : '$name的学习',
                          style: AppTypography.shellHeading.copyWith(
                            fontSize: compact ? 29 : 33,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 7),
                        Text(
                          name == null ? focus.detail : focus.title,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: AppColors.mutedStrong,
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            height: 1.4,
                          ),
                        ),
                        if (focus.chips.isNotEmpty) ...[
                          const SizedBox(height: 15),
                          Wrap(
                            spacing: 15,
                            runSpacing: 7,
                            children: [
                              for (final chip in focus.chips)
                                _HeroStatus(chip: chip),
                            ],
                          ),
                        ],
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  static const _eyebrow = TextStyle(
    color: AppColors.mutedStrong,
    fontSize: 12,
    fontWeight: FontWeight.w600,
    height: 1.3,
  );
}

class HomeStudentQrButton extends StatelessWidget {
  const HomeStudentQrButton({required this.onTap, super.key});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: '扫码登录学习网页',
      child: Semantics(
        button: true,
        enabled: onTap != null,
        label: '扫码登录学习网页',
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            key: const ValueKey('homeStudentQrScanButton'),
            onTap: onTap,
            borderRadius: BorderRadius.circular(AppRadii.control),
            child: SizedBox.square(
              dimension: 48,
              child: Icon(
                Icons.qr_code_scanner_rounded,
                color: onTap == null ? AppColors.disabledInk : AppColors.ink,
                size: 23,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HeroSkeleton extends StatelessWidget {
  const _HeroSkeleton();

  @override
  Widget build(BuildContext context) {
    final decoration = BoxDecoration(
      color: AppColors.brandSageWash.withValues(alpha: .87),
      borderRadius: BorderRadius.circular(6),
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DecoratedBox(
          decoration: decoration,
          child: const SizedBox(width: 192, height: 30),
        ),
        const SizedBox(height: 12),
        DecoratedBox(
          decoration: decoration,
          child: const SizedBox(width: 148, height: 12),
        ),
      ],
    );
  }
}

class _HeroStatus extends StatelessWidget {
  const _HeroStatus({required this.chip});

  final HomeChipSpec chip;

  @override
  Widget build(BuildContext context) {
    final color = switch (chip.tone) {
      StatusTone.success => AppColors.success,
      StatusTone.warning => AppColors.warning,
      StatusTone.danger => AppColors.danger,
      StatusTone.neutral => AppColors.mutedStrong,
    };

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(homeChipIcon(chip.kind), color: color, size: 14),
        const SizedBox(width: 5),
        Flexible(
          child: Text(
            chip.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: color,
              fontSize: 11.5,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }
}
