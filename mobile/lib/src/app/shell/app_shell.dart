import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/app/router/app_router.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';

class AppShell extends StatelessWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.path;
    final selectedRoute = routeFromLocation(location);
    final selectedIndex = AppRoute.values.indexOf(selectedRoute);

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
            Positioned.fill(child: child),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _MiraBottomNavigation(
                selectedIndex: selectedIndex,
                onSelected: (index) => context.go(AppRoute.values[index].path),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MiraBottomNavigation extends StatelessWidget {
  const _MiraBottomNavigation({
    required this.selectedIndex,
    required this.onSelected,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.appBackgroundWarm.withValues(alpha: 0.78),
            border: Border(
              top: BorderSide(
                color: AppColors.ink.withValues(alpha: 0.07),
                width: 0.6,
              ),
            ),
          ),
          child: Padding(
            padding: EdgeInsets.only(bottom: bottomInset),
            child: SizedBox(
              height: AppChrome.tabBarHeight,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (var index = 0; index < AppRoute.values.length; index++)
                    Expanded(
                      child: _BottomNavItem(
                        route: AppRoute.values[index],
                        selected: selectedIndex == index,
                        onTap: () => onSelected(index),
                      ),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNavItem extends StatelessWidget {
  const _BottomNavItem({
    required this.route,
    required this.selected,
    required this.onTap,
  });

  final AppRoute route;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(
        button: true,
        selected: selected,
        label: route.label,
        child: AnimatedScale(
          scale: reduceMotion || !selected ? 1 : 1.02,
          duration: AppMotion.duration(context, 180),
          curve: Curves.easeOutCubic,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                selected ? route.selectedIcon : route.icon,
                color: selected ? AppColors.brand : const Color(0x99526579),
                size: 21,
              ),
              const SizedBox(height: 3),
              Text(
                route.label,
                style: TextStyle(
                  color: selected ? AppColors.brand : const Color(0x99526579),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 10.5,
                  fontWeight: selected ? FontWeight.w800 : FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
