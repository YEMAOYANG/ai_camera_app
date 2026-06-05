import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_background.dart';

class AppScreen extends StatelessWidget {
  const AppScreen({
    required this.title,
    required this.children,
    this.subtitle,
    this.trailing,
    this.headerContent,
    this.onBack,
    this.backLabel = '返回',
    this.fixedHeader = true,
    this.showHeader = true,
    this.reserveBottomNavigation = true,
    this.pinnedHeaderHeight = AppChrome.pinnedHeaderHeight,
    this.padding = const EdgeInsets.fromLTRB(
      AppSpacing.pageHorizontal,
      10,
      AppSpacing.pageHorizontal,
      AppSpacing.pageBottom,
    ),
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;
  final Widget? headerContent;
  final VoidCallback? onBack;
  final String backLabel;
  final bool fixedHeader;
  final bool showHeader;
  final bool reserveBottomNavigation;
  final double pinnedHeaderHeight;
  final List<Widget> children;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final safeArea = MediaQuery.paddingOf(context);
    final basePadding = padding.resolve(Directionality.of(context));
    final chromeBottom = reserveBottomNavigation
        ? AppChrome.tabBarBottomGap(safeArea.bottom) +
              AppChrome.tabBarHeight +
              AppChrome.tabBarContentGap
        : safeArea.bottom + 18;
    final bottomPadding = chromeBottom > basePadding.bottom
        ? chromeBottom
        : basePadding.bottom;
    final topPadding = fixedHeader
        ? safeArea.top + pinnedHeaderHeight + basePadding.top
        : basePadding.top + safeArea.top + 2;
    final adjustedPadding = EdgeInsets.fromLTRB(
      basePadding.left,
      topPadding,
      basePadding.right,
      bottomPadding,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColors.appBackgroundWarm,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: AppColors.appBackground,
        body: Stack(
          children: [
            const Positioned.fill(child: AppScreenBackground()),
            ListView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: adjustedPadding,
              children: [
                if (!fixedHeader && showHeader) ...[
                  _AppLargeHeader(
                    title: title,
                    subtitle: subtitle,
                    trailing: trailing,
                  ),
                  const SizedBox(height: 18),
                ],
                ...children,
              ],
            ),
            if (fixedHeader && showHeader)
              _AppPinnedHeader(
                title: title,
                subtitle: subtitle,
                safeTop: safeArea.top,
                onBack: onBack,
                backLabel: backLabel,
                trailing: trailing,
                headerContent: headerContent,
                headerHeight: pinnedHeaderHeight,
              ),
          ],
        ),
      ),
    );
  }
}

class _AppLargeHeader extends StatelessWidget {
  const _AppLargeHeader({
    required this.title,
    required this.subtitle,
    required this.trailing,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;

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
                  fontSize: 28,
                  fontWeight: FontWeight.w800,
                  height: 1.12,
                  letterSpacing: 0,
                ),
              ),
              if (subtitle != null) ...[
                const SizedBox(height: 7),
                Text(
                  subtitle!,
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    height: 1.45,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ],
          ),
        ),
        if (trailing != null) ...[const SizedBox(width: 12), trailing!],
      ],
    );
  }
}

class _AppPinnedHeader extends StatelessWidget {
  const _AppPinnedHeader({
    required this.title,
    required this.subtitle,
    required this.safeTop,
    required this.backLabel,
    this.onBack,
    this.trailing,
    this.headerContent,
    this.headerHeight = AppChrome.pinnedHeaderHeight,
  });

  final String title;
  final String? subtitle;
  final double safeTop;
  final VoidCallback? onBack;
  final String backLabel;
  final Widget? trailing;
  final Widget? headerContent;
  final double headerHeight;

  @override
  Widget build(BuildContext context) {
    final hasBack = onBack != null;

    return Positioned(
      left: 0,
      right: 0,
      top: 0,
      child: ClipRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.appBackground.withValues(alpha: 0.78),
              border: Border(
                bottom: BorderSide(
                  color: AppColors.ink.withValues(alpha: 0.07),
                  width: 0.6,
                ),
              ),
            ),
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.pageHorizontal,
                safeTop,
                AppSpacing.pageHorizontal,
                0,
              ),
              child: SizedBox(
                height: headerHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    if (hasBack) ...[
                      AppIconButton(
                        icon: Icons.arrow_back_ios_new,
                        label: backLabel,
                        onTap: onBack!,
                      ),
                      const SizedBox(width: 12),
                    ],
                    Expanded(
                      child:
                          headerContent ??
                          Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: AppColors.ink,
                                  fontFamily: AppTypography.systemFont,
                                  fontSize: hasBack ? 24 : 28,
                                  fontWeight: FontWeight.w800,
                                  height: hasBack ? 1.14 : 1.12,
                                  letterSpacing: 0,
                                ),
                              ),
                              if (subtitle != null) ...[
                                const SizedBox(height: 7),
                                Text(
                                  subtitle!,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: AppColors.muted,
                                    fontFamily: AppTypography.systemFont,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                    height: 1.35,
                                    letterSpacing: 0,
                                  ),
                                ),
                              ],
                            ],
                          ),
                    ),
                    if (trailing != null) ...[
                      const SizedBox(width: 10),
                      trailing!,
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppIconButton extends StatelessWidget {
  const AppIconButton({
    required this.icon,
    required this.onTap,
    this.label,
    super.key,
  });

  final IconData icon;
  final VoidCallback onTap;
  final String? label;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(
        button: true,
        label: label,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceSoft,
            borderRadius: BorderRadius.circular(AppRadii.control),
            border: Border.all(color: AppColors.borderSoft),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF4C6685).withValues(alpha: 0.035),
                blurRadius: 10,
                offset: const Offset(0, 5),
              ),
            ],
          ),
          child: SizedBox(
            width: AppControls.iconButtonSize,
            height: AppControls.iconButtonSize,
            child: Center(child: Icon(icon, color: AppColors.ink, size: 18)),
          ),
        ),
      ),
    );
  }
}
