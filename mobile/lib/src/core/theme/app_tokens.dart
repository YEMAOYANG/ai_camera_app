import 'package:flutter/material.dart';

class AppColors {
  const AppColors._();

  static const brand = Color(0xFF2F6CF6);
  static const brandSoft = Color(0xFF7FA6FF);
  static const brandDeep = Color(0xFF2459D6);
  static const brandWash = Color(0xFFEAF1FF);
  static const primary = primaryButtonStart;
  static const primaryPressed = primaryButtonEnd;
  static const primarySoft = Color(0xFFEFF3F8);
  static const selectedBg = Color(0xFFE9EEF6);
  static const focusRing = primaryButtonStart;
  static const ink = Color(0xFF142033);
  static const muted = Color(0xFF66758A);
  static const subtle = Color(0xFF8A96A8);
  static const textPrimary = ink;
  static const textSecondary = muted;
  static const appBackground = Color(0xFFF8FAFD);
  static const appBackgroundMid = Color(0xFFEEF4FA);
  static const appBackgroundWarm = Color(0xFFF7F7F3);
  static const surface = Color(0xF2FFFFFF);
  static const surfaceSoft = Color(0xCCFFFFFF);
  static const surfaceElevated = Color(0xFFFFFFFF);
  static const border = Color(0xFFE2E8F0);
  static const borderSoft = Color(0xFFEAF0F6);
  static const borderSubtle = borderSoft;
  static const focus = focusRing;
  static const success = Color(0xFF2F8F68);
  static const successWash = Color(0xFFE6F4EE);
  static const warning = Color(0xFFD8922B);
  static const warningWash = Color(0xFFFFF2D8);
  static const danger = Color(0xFFB64A4A);
  static const dangerWash = Color(0xFFFFE7E5);
  static const disabledFill = Color(0xFFE9EEF4);
  static const disabledBg = disabledFill;
  static const disabledInk = Color(0xFF9AA6B5);
  static const primaryButtonStart = Color(0xFF1C2940);
  static const primaryButtonEnd = Color(0xFF111827);
  static const primaryButtonShadow = Color(0xFF172033);
}

class AppRadii {
  const AppRadii._();

  static const button = 15.0;
  static const buttonSecondary = 15.0;
  static const input = 15.0;
  static const control = 14.0;
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

class AppControls {
  const AppControls._();

  static const buttonHeight = 50.0;
  static const compactButtonHeight = 46.0;
  static const fieldHeight = 48.0;
  static const iconButtonSize = 40.0;
  static const minTouchTarget = 44.0;
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
