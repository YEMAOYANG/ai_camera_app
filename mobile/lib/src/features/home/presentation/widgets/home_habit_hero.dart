import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/home/domain/home_models.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_shared.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class HomeHabitHero extends StatelessWidget {
  const HomeHabitHero({
    super.key,
    required this.focus,
    required this.safeTop,
    required this.scrollOffset,
    required this.isLoading,
    required this.panelOverlap,
  });

  final HabitFocusCopy focus;
  final double safeTop;
  final double scrollOffset;
  final bool isLoading;
  final double panelOverlap;

  static const _heroImage = 'assets/images/home/home-hero-desk-evening.png';

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final progress = (scrollOffset / 260).clamp(0.0, 1.0).toDouble();
    final translateY = reduceMotion ? 0.0 : -scrollOffset * 0.16;
    final scale = reduceMotion ? 1.0 : 1.0 + progress * 0.035;
    final imageOpacity = reduceMotion ? 1.0 : 1.0 - progress * 0.14;
    final compact =
        MediaQuery.sizeOf(context).width <= 340 ||
        MediaQuery.sizeOf(context).height <= 620;
    final bottomPadding = panelOverlap + (compact ? 10 : 12);
    final topInset = safeTop > 0 ? safeTop : 24.0;
    final topPadding = topInset + (compact ? 12 : 14);

    return ClipRect(
      child: Stack(
        children: [
          const Positioned.fill(child: _HomeHeroFallback()),
          Positioned.fill(
            child: Transform.translate(
              offset: Offset(0, translateY),
              child: Transform.scale(
                scale: scale,
                alignment: Alignment.centerRight,
                child: Opacity(
                  opacity: imageOpacity,
                  child: Image.asset(
                    _heroImage,
                    fit: BoxFit.cover,
                    alignment: Alignment.centerRight,
                    errorBuilder: (_, _, _) => const _HomeHeroFallback(),
                  ),
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: [
                    const Color(0xFF111827).withValues(alpha: 0.86),
                    const Color(0xFF111827).withValues(alpha: 0.56),
                    const Color(0xFF111827).withValues(alpha: 0.18),
                  ],
                  stops: const [0, 0.42, 1],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.18),
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.50),
                  ],
                  stops: const [0, 0.48, 1],
                ),
              ),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: compact ? 44 : 52,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.surfaceElevated.withValues(alpha: 0),
                    AppColors.surfaceElevated.withValues(alpha: 0.72),
                    AppColors.surfaceElevated,
                  ],
                  stops: const [0, 0.55, 1],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.pageHorizontal,
                topPadding,
                AppSpacing.pageHorizontal,
                bottomPadding,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              focus.headerTime,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.72),
                                fontFamily: AppTypography.systemFont,
                                fontSize: 12,
                                fontWeight: FontWeight.w800,
                                height: 1.1,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              focus.headerTitle,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Colors.white,
                                fontFamily: AppTypography.systemFont,
                                fontSize: 18,
                                fontWeight: FontWeight.w900,
                                height: 1.1,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 10),
                      HomePressable(
                        onTap: () => context.go(AppRoute.alerts.path),
                        child: Semantics(
                          button: true,
                          label: '未处理提醒',
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.20),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.18),
                              ),
                            ),
                            child: SizedBox(
                              width: AppControls.minTouchTarget,
                              height: AppControls.minTouchTarget,
                              child: Center(
                                child: Icon(
                                  Icons.notifications_outlined,
                                  color: Colors.white,
                                  size: 19,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: compact ? 14 : 18),
                  if (isLoading)
                    _HeroSkeleton(compact: compact)
                  else ...[
                    Flexible(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            focus.title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: Colors.white,
                              fontFamily: AppTypography.systemFont,
                              fontSize: compact ? 22 : 26,
                              fontWeight: FontWeight.w900,
                              height: compact ? 1.12 : 1.16,
                            ),
                          ),
                          SizedBox(height: compact ? 6 : 8),
                          Text(
                            focus.detail,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.74),
                              fontFamily: AppTypography.systemFont,
                              fontSize: compact ? 12.5 : 13,
                              fontWeight: FontWeight.w600,
                              height: compact ? 1.36 : 1.45,
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: compact ? 6 : 8),
                    SizedBox(
                      height: 28,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        padding: EdgeInsets.zero,
                        itemCount: focus.chips.length,
                        separatorBuilder: (_, _) =>
                            SizedBox(width: compact ? 6 : 8),
                        itemBuilder: (context, index) =>
                            _HeroStatusPill(chip: focus.chips[index]),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroSkeleton extends StatelessWidget {
  const _HeroSkeleton({required this.compact});

  final bool compact;

  @override
  Widget build(BuildContext context) {
    final color = Colors.white.withValues(alpha: 0.16);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: compact ? 220 : 240,
          height: compact ? 28 : 32,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(10),
          ),
        ),
        const SizedBox(height: 10),
        Container(
          width: compact ? 260 : 280,
          height: 16,
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(8),
          ),
        ),
      ],
    );
  }
}

class _HeroStatusPill extends StatelessWidget {
  const _HeroStatusPill({required this.chip});

  final HomeChipSpec chip;

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width <= 340;
    final color = _heroPillIconColor(chip.tone);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.26),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: Colors.white.withValues(alpha: 0.24)),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: compact ? 8 : 10,
          vertical: compact ? 5 : 6,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              homeChipIcon(chip.kind),
              color: color,
              size: compact ? 12 : 13,
            ),
            SizedBox(width: compact ? 4 : 5),
            Text(
              chip.label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.90),
                fontFamily: AppTypography.systemFont,
                fontSize: compact ? 11 : 11.5,
                fontWeight: FontWeight.w800,
                height: 1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Color _heroPillIconColor(StatusTone tone) {
  return switch (tone) {
    StatusTone.success => const Color(0xFFBFF3D3),
    StatusTone.warning => const Color(0xFFFFE1A8),
    StatusTone.danger => const Color(0xFFFFC7C7),
    StatusTone.neutral => Colors.white,
  };
}

class _HomeHeroFallback extends StatelessWidget {
  const _HomeHeroFallback();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF1C2940),
            AppColors.brandSage.withValues(alpha: 0.88),
            AppColors.brandWarm.withValues(alpha: 0.72),
          ],
        ),
      ),
    );
  }
}
