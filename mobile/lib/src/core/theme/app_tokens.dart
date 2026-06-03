import 'package:flutter/material.dart';

class AppColors {
  const AppColors._();

  static const brand = Color(0xFF2F6CF6);
  static const brandSoft = Color(0xFF7FA6FF);
  static const ink = Color(0xFF142033);
  static const muted = Color(0xFF66758A);
  static const appBackground = Color(0xFFF8FAFD);
  static const appBackgroundMid = Color(0xFFEEF4FA);
  static const appBackgroundWarm = Color(0xFFF7F7F3);
  static const primaryButtonStart = Color(0xFF1C2940);
  static const primaryButtonEnd = Color(0xFF111827);
  static const primaryButtonShadow = Color(0xFF172033);
}

class AppRadii {
  const AppRadii._();

  static const button = 19.0;
  static const buttonSecondary = 18.0;
  static const card = 8.0;
  static const welcomeArt = 26.0;
  static const full = 999.0;
}

class AppMotion {
  const AppMotion._();

  static Duration duration(BuildContext context, int milliseconds) {
    return MediaQuery.of(context).disableAnimations
        ? Duration.zero
        : Duration(milliseconds: milliseconds);
  }

  static const buttonPressScale = 0.975;
}

class AppChrome {
  const AppChrome._();

  static const tabBarHeight = 72.0;
  static const tabBarContentGap = 12.0;
  static const pinnedHeaderHeight = 96.0;
}

class AppTypography {
  const AppTypography._();

  static const systemFont = '.AppleSystemUIFont';
}
