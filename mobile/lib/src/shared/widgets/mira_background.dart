import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';

class MiraAppBackground extends StatelessWidget {
  const MiraAppBackground({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            AppColors.appBackground,
            AppColors.appBackgroundMid,
            AppColors.appBackgroundWarm,
            AppColors.appBackgroundWarm,
          ],
          stops: [0, 0.42, 0.76, 1],
        ),
      ),
      child: Stack(
        children: [
          const Positioned.fill(child: _MiraAmbientWash()),
          child,
        ],
      ),
    );
  }
}

class MiraScreenBackground extends StatelessWidget {
  const MiraScreenBackground({super.key});

  @override
  Widget build(BuildContext context) {
    return const MiraAppBackground(child: SizedBox.expand());
  }
}

class MiraBackgroundScaffold extends StatelessWidget {
  const MiraBackgroundScaffold({
    required this.child,
    this.extendBody = false,
    super.key,
  });

  final Widget child;
  final bool extendBody;

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColors.appBackgroundWarm,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: AppColors.appBackground,
        extendBody: extendBody,
        body: MiraAppBackground(child: child),
      ),
    );
  }
}

class _MiraAmbientWash extends StatelessWidget {
  const _MiraAmbientWash();

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Stack(
        children: [
          const Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0x6BFFFFFF),
                    Color(0x0DFFFFFF),
                    Color(0x102F6CF6),
                  ],
                  stops: [0, 0.48, 1],
                ),
              ),
            ),
          ),
          Positioned(
            left: -110,
            top: 76,
            width: 260,
            height: 300,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    AppColors.brandSoft.withValues(alpha: 0.15),
                    AppColors.brandSoft.withValues(alpha: 0.04),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
          Positioned(
            right: -126,
            bottom: 40,
            width: 300,
            height: 340,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFFD8922B).withValues(alpha: 0.10),
                    const Color(0xFFD8922B).withValues(alpha: 0.025),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
