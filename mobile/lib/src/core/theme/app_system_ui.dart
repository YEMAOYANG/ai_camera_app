import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class AppSystemUi {
  const AppSystemUi._();

  static SystemUiOverlayStyle light({
    Color statusBarColor = Colors.transparent,
    Color navigationBarColor = Colors.transparent,
  }) {
    return SystemUiOverlayStyle.dark.copyWith(
      statusBarColor: statusBarColor,
      statusBarIconBrightness: Brightness.dark,
      statusBarBrightness: Brightness.light,
      systemNavigationBarColor: navigationBarColor,
      systemNavigationBarDividerColor: Colors.transparent,
      systemNavigationBarIconBrightness: Brightness.dark,
      systemNavigationBarContrastEnforced: false,
      systemStatusBarContrastEnforced: false,
    );
  }

  static SystemUiOverlayStyle dark({
    Color statusBarColor = Colors.transparent,
    Color navigationBarColor = Colors.transparent,
  }) {
    return SystemUiOverlayStyle.light.copyWith(
      statusBarColor: statusBarColor,
      statusBarIconBrightness: Brightness.light,
      statusBarBrightness: Brightness.dark,
      systemNavigationBarColor: navigationBarColor,
      systemNavigationBarDividerColor: Colors.transparent,
      systemNavigationBarIconBrightness: Brightness.light,
      systemNavigationBarContrastEnforced: false,
      systemStatusBarContrastEnforced: false,
    );
  }
}
