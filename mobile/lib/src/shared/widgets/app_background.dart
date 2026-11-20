import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

/// The same paper ground follows the content across routes.
class AppBackground extends StatelessWidget {
  const AppBackground({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(color: AppColors.appBackground, child: child);
  }
}

class AppScreenBackground extends StatelessWidget {
  const AppScreenBackground({super.key});

  @override
  Widget build(BuildContext context) {
    return const AppBackground(child: SizedBox.expand());
  }
}

class AppBackgroundScaffold extends StatelessWidget {
  const AppBackgroundScaffold({
    required this.child,
    this.extendBody = false,
    super.key,
  });

  final Widget child;
  final bool extendBody;

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.appBackground,
        extendBody: extendBody,
        body: AppBackground(child: child),
      ),
    );
  }
}
