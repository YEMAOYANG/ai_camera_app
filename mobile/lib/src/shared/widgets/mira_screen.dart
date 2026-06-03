import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';

class MiraScreen extends StatelessWidget {
  const MiraScreen({
    required this.title,
    required this.children,
    this.subtitle,
    this.trailing,
    this.headerContent,
    this.onBack,
    this.backLabel = '返回',
    this.fixedHeader = true,
    this.padding = const EdgeInsets.fromLTRB(20, 16, 20, 28),
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;
  final Widget? headerContent;
  final VoidCallback? onBack;
  final String backLabel;
  final bool fixedHeader;
  final List<Widget> children;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final safeArea = MediaQuery.paddingOf(context);
    final basePadding = padding.resolve(Directionality.of(context));
    final chromeBottom =
        safeArea.bottom + AppChrome.tabBarHeight + AppChrome.tabBarContentGap;
    final bottomPadding = chromeBottom > basePadding.bottom
        ? chromeBottom
        : basePadding.bottom;
    final topPadding = fixedHeader
        ? safeArea.top + AppChrome.pinnedHeaderHeight + basePadding.top
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
      child: Stack(
        children: [
          const Positioned.fill(child: _MiraScreenBackground()),
          ListView(
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            padding: adjustedPadding,
            children: [
              if (!fixedHeader) ...[
                _MiraLargeHeader(
                  title: title,
                  subtitle: subtitle,
                  trailing: trailing,
                ),
                const SizedBox(height: 18),
              ],
              ...children,
            ],
          ),
          if (fixedHeader)
            _MiraPinnedHeader(
              title: title,
              subtitle: subtitle,
              safeTop: safeArea.top,
              onBack: onBack,
              backLabel: backLabel,
              trailing: trailing,
              headerContent: headerContent,
            ),
        ],
      ),
    );
  }
}

class _MiraLargeHeader extends StatelessWidget {
  const _MiraLargeHeader({
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

class _MiraPinnedHeader extends StatelessWidget {
  const _MiraPinnedHeader({
    required this.title,
    required this.subtitle,
    required this.safeTop,
    required this.backLabel,
    this.onBack,
    this.trailing,
    this.headerContent,
  });

  final String title;
  final String? subtitle;
  final double safeTop;
  final VoidCallback? onBack;
  final String backLabel;
  final Widget? trailing;
  final Widget? headerContent;

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
              padding: EdgeInsets.fromLTRB(20, safeTop, 20, 0),
              child: SizedBox(
                height: AppChrome.pinnedHeaderHeight,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    if (hasBack) ...[
                      MiraIconButton(
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

class _MiraScreenBackground extends StatelessWidget {
  const _MiraScreenBackground();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            AppColors.appBackground,
            AppColors.appBackgroundMid,
            AppColors.appBackgroundWarm,
            AppColors.appBackgroundWarm,
          ],
          stops: [0, 0.44, 0.78, 1],
        ),
      ),
    );
  }
}

class MiraIconButton extends StatelessWidget {
  const MiraIconButton({
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
            color: Colors.white.withValues(alpha: 0.76),
            borderRadius: BorderRadius.circular(15),
            border: Border.all(color: Colors.white.withValues(alpha: 0.86)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF4C6685).withValues(alpha: 0.06),
                blurRadius: 16,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: SizedBox(
            width: 44,
            height: 44,
            child: Center(child: Icon(icon, color: AppColors.ink, size: 20)),
          ),
        ),
      ),
    );
  }
}
