import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:fresnel/fresnel.dart' as glass;
import 'package:fresnel/primitives.dart' as glass_renderer;
import 'package:warm_sight/src/core/theme/app_tokens.dart';

enum AppGlassStyle { navigation, header, sheet, overlayControl }

/// Resolve native/shader support and warm the material before the first frame.
Future<void> initializeAppGlass() async {
  if (!kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.android)) {
    await glass.Fresnel.ensureInitialized();
  }
}

/// A scene must not mix native glass with Flutter backdrop filters.
class AppGlassScope extends StatelessWidget {
  const AppGlassScope({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) => glass.FresnelTheme(
    data: glass.FresnelThemeData.light().copyWith(
      onGlass: AppColors.ink,
      accent: AppColors.brand,
      opaqueFallback: AppGlass.opaqueSurface,
      blurSigma: AppGlass.androidBlurSigma,
      thickness: AppGlass.androidThickness,
      refraction: AppGlass.androidRefraction,
    ),
    child: glass.FresnelScope(child: child),
  );
}

/// Native iOS 26 glass with Flutter-owned content, gestures and semantics.
///
/// Clear glass is used for floating chrome; larger reading surfaces use the
/// system's adaptive regular material. Never paint a white panel above native
/// glass: it would hide the background the material is supposed to refract.
class AppGlassSurface extends StatelessWidget {
  const AppGlassSurface({
    required this.child,
    required this.style,
    this.borderRadius = BorderRadius.zero,
    super.key,
  });

  final Widget child;
  final AppGlassStyle style;
  final BorderRadius borderRadius;

  @override
  Widget build(BuildContext context) {
    final highContrast = MediaQuery.highContrastOf(context);
    final capabilities = glass.Fresnel.capabilities;
    final reduceEffects =
        highContrast ||
        MediaQuery.disableAnimationsOf(context) ||
        capabilities.reduceTransparency ||
        capabilities.reduceMotion ||
        capabilities.increaseContrast;
    final nativeAvailable = !reduceEffects && capabilities.hasNativeGlass;
    final isAndroid = Theme.of(context).platform == TargetPlatform.android;

    if (nativeAvailable) {
      return glass.GlassSurface(
        glass: switch (style) {
          AppGlassStyle.navigation ||
          AppGlassStyle.overlayControl => glass.Glass.clear,
          AppGlassStyle.header || AppGlassStyle.sheet => glass.Glass.regular,
        },
        shape: glass.GlassShape.rounded(borderRadius.topLeft.x),
        child: ClipRRect(borderRadius: borderRadius, child: child),
      );
    }

    final overImage = style == AppGlassStyle.overlayControl;
    final opaque = reduceEffects;
    final color = !opaque && isAndroid
        ? switch (style) {
            AppGlassStyle.navigation => AppGlass.androidNavigationFill,
            AppGlassStyle.header => AppGlass.androidHeaderFill,
            AppGlassStyle.sheet => AppGlass.androidSheetFill,
            AppGlassStyle.overlayControl => AppGlass.androidOverlayFill,
          }
        : overImage
        ? (opaque ? AppColors.ink : AppGlass.overlayFallback)
        : (opaque ? AppGlass.opaqueSurface : AppGlass.readableFallback);
    final panel = DecoratedBox(
      decoration: BoxDecoration(
        color: color,
        borderRadius: borderRadius,
        border: Border.all(
          color: highContrast ? AppColors.mutedStrong : AppGlass.fallbackRim,
          width: 0.6,
        ),
      ),
      child: child,
    );

    // Keep the refraction pass on small floating controls. Large reading
    // surfaces need a quieter blur and enough fill to preserve text contrast.
    final useShader =
        isAndroid &&
        !opaque &&
        capabilities.hasImpeller &&
        glass_renderer.GlassShaderProgram.maybeProgram != null &&
        (style == AppGlassStyle.navigation || overImage);
    if (useShader) {
      return glass.GlassSurface(
        glass: glass.Glass.clear,
        shape: glass.GlassShape.rounded(borderRadius.topLeft.x),
        child: ClipRRect(borderRadius: borderRadius, child: panel),
      );
    }

    return ClipRRect(
      borderRadius: borderRadius,
      child: opaque
          ? panel
          : BackdropFilter(
              filter: ImageFilter.blur(
                sigmaX: isAndroid
                    ? AppGlass.androidBlurSigma
                    : AppGlass.fallbackBlurSigma,
                sigmaY: isAndroid
                    ? AppGlass.androidBlurSigma
                    : AppGlass.fallbackBlurSigma,
              ),
              child: panel,
            ),
    );
  }
}
