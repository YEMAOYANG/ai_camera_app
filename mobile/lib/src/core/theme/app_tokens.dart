import 'package:flutter/material.dart';

/// Palette from `brand/brand-guidelines.md`: ink teal for text and primary
/// actions, sprout green for growth and success, warm gold only where a
/// caregiver decision is waiting, on a warm paper ground.
class AppColors {
  const AppColors._();

  static const brand = Color(0xFF284048);
  static const brandSoft = Color(0xFF90B098);
  static const brandDeep = Color(0xFF1F343B);
  static const brandWash = Color(0xFFE3ECE2);
  static const brandSage = Color(0xFF3E7257);
  static const brandSageWash = Color(0xFFE3ECE2);
  static const brandWarm = Color(0xFFE0A838);
  static const brandWarmWash = Color(0xFFFBEFD0);
  // AI surfaces share the sprout tone; the brand rules out blue-purple "AI".
  static const ai = Color(0xFF3E7257);
  static const aiWash = Color(0xFFE3ECE2);
  static const warm = Color(0xFFE0A838);
  static const primary = primaryButtonStart;
  static const primaryPressed = primaryButtonEnd;
  static const primarySoft = Color(0xFFF1EADB);
  static const selectedBg = Color(0xFFE3ECE2);
  static const focusRing = primaryButtonStart;
  static const ink = Color(0xFF284048);
  static const muted = Color(0xFF5A6C70);
  // Small form copy on tinted backgrounds needs slightly stronger contrast.
  static const mutedStrong = Color(0xFF4F6166);
  static const subtle = Color(0xFF74858A);
  static const textPrimary = ink;
  static const textSecondary = muted;
  static const appBackground = shellPaper;
  static const appBackgroundMid = Color(0xFFF9F3E7);
  static const appBackgroundWarm = Color(0xFFF7F0E2);
  // Surfaces are a warm near-white: pure white next to the paper ground reads
  // as a dirty edge.
  static const surface = Color(0xFFFFFDF8);
  static const surfaceSoft = Color(0xE6FFFDF8);
  static const surfaceElevated = Color(0xFFFFFDF8);
  static const surfaceStrong = Color(0xFFF1EADB);
  static const surfaceTinted = Color(0xFFF4EEE1);
  static const border = Color(0xFFDED7C7);
  static const borderSoft = Color(0xFFE9E2D5);
  static const borderSubtle = borderSoft;
  static const focus = focusRing;
  static const success = Color(0xFF3E7257);
  static const successWash = Color(0xFFE3ECE2);
  // Readable amber for text and icons; the bright gold fill is [brandWarm].
  static const warning = Color(0xFF8F5E0A);
  static const warningWash = Color(0xFFFBEFD0);
  static const danger = Color(0xFFB2473B);
  static const dangerWash = Color(0xFFF8E4DF);
  static const disabledFill = Color(0xFFECE5D6);
  static const disabledBg = disabledFill;
  static const disabledInk = Color(0xFF8E9A98);
  static const primaryButtonStart = Color(0xFF284048);
  static const primaryButtonEnd = Color(0xFF213840);
  static const primaryButtonShadow = Color(0xFF284048);
  static const onPrimary = Color(0xFFFFF8E8);
  static const shellPaper = Color(0xFFFCFAF2);
  static const shellRule = Color(0xFFE1E4D5);
  static const navDockBg = shellPaper;
  static const navDockBgWarm = Color(0xFFFFFDF8);
  static const navDockBorder = Color(0xFFEDE4D3);
  static const navDockShadow = Color(0xFF284048);
  static const navActiveBg = Color(0xFFE3ECE2);
  static const navActiveFg = Color(0xFF294D3E);
  static const navInactiveFg = Color(0xFF5C695C);
  static const navWashCenter = Color(0xCC89B99D);
  static const navWashFade = Color(0x65B8D1B9);
  static const navWashEdge = Color(0x00B8D1B9);
  static const navWashSecondary = Color(0xABA9C69B);
  static const navWashSecondaryEdge = Color(0x00C1D4AE);
  static const navFabBg = Color(0xFFEFF2E6);
  static const navFabFg = Color(0xFF46624A);
  static const navFabBorder = Color(0xFFD0D9C3);
  static const navItemActiveBg = navActiveBg;
  static const navItemActiveFg = navActiveFg;
  static const navItemInactiveFg = navInactiveFg;
}

class AppRadii {
  const AppRadii._();

  static const button = 12.0;
  static const buttonSecondary = 12.0;
  static const input = 12.0;
  static const control = 14.0;
  static const card = 8.0;
  static const cardMedium = 16.0;
  static const cardLarge = 18.0;
  static const hero = 20.0;
  static const welcomeArt = 26.0;
  static const full = 999.0;
}

class AppSpacing {
  const AppSpacing._();

  static const pageHorizontalCompact = 14.0;
  static const pageHorizontal = 16.0;
  static const pageHorizontalExpanded = 18.0;
  static const pageSectionGap = 12.0;
  static const pageHeroPadding = 16.0;
  static const pageBottom = 28.0;
}

class AppHomeHero {
  const AppHomeHero._();

  static const minHeight = 318.0;
  static const maxHeight = 390.0;
  static const panelOverlap = 64.0;
  static const panelRadius = 34.0;
  static const contentTopPadding = 18.0;
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

  static const buttonHeight = 44.0;
  static const compactButtonHeight = 44.0;
  static const fieldHeight = 48.0;
  static const iconButtonSize = 44.0;
  static const minTouchTarget = 44.0;
}

class AppChrome {
  const AppChrome._();

  static const tabBarHeight = 62.0;
  static const sideNavigationWidth = 60.0;
  static const readingWidth = 720.0;
  static const tabBarDockRadius = 31.0;
  static const tabBarContentGap = 8.0;
  static const pinnedHeaderHeight = 78.0;

  /// The tab bar is anchored to the bottom edge and pads itself by the full
  /// system inset, so pages reserve that same inset below their content.
  static double tabBarBottomGap(double safeAreaBottom) {
    return safeAreaBottom > 0 ? safeAreaBottom : 0.0;
  }
}

/// Materials for navigation and modal layers; content keeps its own surface.
class AppGlass {
  const AppGlass._();

  static const fallbackBlurSigma = 8.0;
  static const sheetRadius = 22.0;
  static const fallbackRim = Color(0x66FFFFFF);
  static const readableFallback = Color(0xF5FAF5EA);
  static const overlayFallback = Color(0x4D1B2A30);
  static const opaqueSurface = Color(0xFFFAF5EA);
  static const androidBlurSigma = 6.0;
  static const androidThickness = 0.42;
  static const androidRefraction = 1.20;
  static const androidNavigationFill = Color(0xEBFFFDF8);
  static const androidHeaderFill = Color(0xE0FAF5EA);
  static const androidSheetFill = Color(0xF0FAF5EA);
  static const androidOverlayFill = Color(0x3D1B2A30);
  static const selectionTop = Color(0x1FFFFFFF);
  static const selectionBottom = Color(0x1890B098);
  static const selectionBorder = Color(0x30284048);

  static const dockShadow = BoxShadow(
    color: Color(0x0F284048),
    blurRadius: 12,
    offset: Offset(0, 5),
  );
}

class AppTypography {
  const AppTypography._();

  static const systemFont = '.AppleSystemUIFont';
  static const pageHeading = TextStyle(
    color: AppColors.ink,
    fontSize: 28,
    fontWeight: FontWeight.w700,
    height: 1.18,
  );
  static const sectionHeading = TextStyle(
    color: AppColors.ink,
    fontSize: 21,
    fontWeight: FontWeight.w700,
    height: 1.22,
  );
  static const caption = TextStyle(
    color: AppColors.mutedStrong,
    fontSize: 12,
    height: 1.4,
  );
  static const shellHeading = TextStyle(
    color: AppColors.navActiveFg,
    fontFamily: 'Songti SC',
    fontFamilyFallback: ['Noto Serif CJK SC', 'Noto Serif', systemFont],
    fontWeight: FontWeight.w700,
    height: 1.2,
  );
}
