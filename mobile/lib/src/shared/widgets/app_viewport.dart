import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' show DisplayFeature;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';

enum AppVerticalBarEdge { left, right }

typedef AppSideNavigation = ({
  AppVerticalBarEdge edge,
  double width,
  double top,
  bool usesSystemBar,
});

/// Keeps the same Navigator and its routes mounted as the window changes size.
class AppViewport extends StatefulWidget {
  const AppViewport({
    required this.child,
    this.geometryEvents,
    this.navigationChanges,
    this.useSystemBarForTabs,
    super.key,
  });

  final Widget child;
  final Stream<Object?>? geometryEvents;
  final Listenable? navigationChanges;
  final bool Function()? useSystemBarForTabs;

  static AppSideNavigation? sideNavigationOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_ViewportScope>()?.navigation;

  static AppVerticalBarEdge? verticalBarEdgeOf(BuildContext context) =>
      sideNavigationOf(context)?.edge;

  static bool supportsFoldingOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_ViewportScope>()?.foldable ??
      false;

  @override
  State<AppViewport> createState() => _AppViewportState();
}

class _AppViewportState extends State<AppViewport> {
  static const _channel = EventChannel('ai_camera_app/display_geometry');

  StreamSubscription<Object?>? _geometrySubscription;
  _WindowGeometry? _geometry;
  bool _navigationRefreshPending = false;

  @override
  void initState() {
    super.initState();
    widget.navigationChanges?.addListener(_onNavigationChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final events =
          widget.geometryEvents ??
          (!kIsWeb && Platform.isIOS
              ? _channel.receiveBroadcastStream()
              : null);
      _geometrySubscription = events?.listen(
        (event) => setState(() => _geometry = _WindowGeometry.parse(event)),
      );
    });
  }

  @override
  void didUpdateWidget(AppViewport oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.navigationChanges != widget.navigationChanges) {
      oldWidget.navigationChanges?.removeListener(_onNavigationChanged);
      widget.navigationChanges?.addListener(_onNavigationChanged);
    }
  }

  void _onNavigationChanged() {
    if (_geometry?.systemBarBottom == null || _navigationRefreshPending) return;
    // The router can finish matching a route while its subtree is building.
    if (SchedulerBinding.instance.schedulerPhase ==
        SchedulerPhase.persistentCallbacks) {
      _navigationRefreshPending = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _navigationRefreshPending = false;
        if (mounted) setState(() {});
      });
    } else {
      setState(() {});
    }
  }

  @override
  void dispose() {
    widget.navigationChanges?.removeListener(_onNavigationChanged);
    unawaited(_geometrySubscription?.cancel());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final bounds = Offset.zero & media.size;
    final horizontalInsets = media.viewPadding;
    final safeBounds = horizontalInsets.horizontal < bounds.width
        ? Rect.fromLTRB(
            horizontalInsets.left,
            0,
            bounds.right - horizontalInsets.right,
            bounds.bottom,
          )
        : bounds;
    final geometry = _geometry;
    // UIKit and Flutter can report the new window on different frames.
    final current = geometry?.matches(media.size) == true ? geometry : null;
    final divisions = current?.divisions
        .where((division) => bounds.overlaps(division))
        .map(
          (division) => division.height > division.width
              ? Rect.fromLTRB(division.left, 0, division.right, bounds.bottom)
              : Rect.fromLTRB(0, division.top, bounds.right, division.bottom),
        );
    final panes = DisplayFeatureSubScreen.subScreensInBounds(
      safeBounds,
      divisions ?? const [],
    ).where((pane) => !pane.isEmpty).toList();
    const minimumContentWidth = 300.0;
    const minimumRailHeight = 282.0;
    final side = current?.barEdge;
    final laneWidth = side == AppVerticalBarEdge.left
        ? horizontalInsets.left
        : horizontalInsets.right;
    final systemBarBottom = current?.systemBarBottom;
    final useSystemBar = widget.useSystemBarForTabs?.call() ?? false;
    AppSideNavigation? railFor(Rect pane) {
      final touchesSystemEdge = switch (side) {
        AppVerticalBarEdge.left => pane.left == safeBounds.left,
        AppVerticalBarEdge.right => pane.right == safeBounds.right,
        null => false,
      };
      if (!touchesSystemEdge || side == null) return null;
      if (useSystemBar &&
          laneWidth >= AppChrome.sideNavigationWidth &&
          pane.width >= minimumContentWidth &&
          systemBarBottom != null) {
        final railTop = math.max(pane.top, systemBarBottom + 8);
        final bottomInset = math.max(
          8.0,
          media.viewPadding.bottom - (bounds.bottom - pane.bottom),
        );
        if (pane.bottom - bottomInset - railTop >= minimumRailHeight) {
          return (
            edge: side,
            width: laneWidth,
            top: railTop - pane.top,
            usesSystemBar: true,
          );
        }
      }
      return pane.width >= minimumContentWidth + AppChrome.sideNavigationWidth
          ? (
              edge: side,
              width: AppChrome.sideNavigationWidth,
              top: 0,
              usesSystemBar: false,
            )
          : null;
    }

    // Prefer the pane next to the system bar when it has room for navigation.
    final railPanes = panes.where((pane) => railFor(pane) != null);
    final candidates = railPanes.isEmpty ? panes : railPanes;
    final pane = candidates.isEmpty
        ? safeBounds
        : candidates.reduce(
            (best, pane) => pane.width * pane.height > best.width * best.height
                ? pane
                : best,
          );
    final navigation = railFor(pane);
    final viewport = navigation?.usesSystemBar == true
        ? Rect.fromLTRB(
            side == AppVerticalBarEdge.left ? bounds.left : pane.left,
            pane.top,
            side == AppVerticalBarEdge.right ? bounds.right : pane.right,
            pane.bottom,
          )
        : pane;

    EdgeInsets localInsets(EdgeInsets insets) => EdgeInsets.fromLTRB(
      math.max(0, insets.left - viewport.left),
      math.max(0, insets.top - viewport.top),
      math.max(0, insets.right - (bounds.right - viewport.right)),
      math.max(0, insets.bottom - (bounds.bottom - viewport.bottom)),
    );

    final localMedia = viewport == bounds
        ? media
        : media.copyWith(
            size: viewport.size,
            padding: localInsets(media.padding),
            viewPadding: localInsets(media.viewPadding),
            viewInsets: localInsets(media.viewInsets),
            systemGestureInsets: localInsets(media.systemGestureInsets),
            displayFeatures: [
              for (final feature in media.displayFeatures)
                if (viewport.overlaps(feature.bounds))
                  DisplayFeature(
                    bounds: feature.bounds
                        .intersect(viewport)
                        .shift(-viewport.topLeft),
                    type: feature.type,
                    state: feature.state,
                  ),
            ],
          );

    return ColoredBox(
      color: AppColors.appBackground,
      child: Stack(
        children: [
          Positioned.fromRect(
            rect: viewport,
            child: ClipRect(
              clipBehavior: viewport == bounds ? Clip.none : Clip.hardEdge,
              child: MediaQuery(
                data: localMedia,
                child: _ViewportScope(
                  navigation: navigation,
                  foldable: geometry?.foldable ?? false,
                  child: widget.child,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ViewportScope extends InheritedWidget {
  const _ViewportScope({
    required this.navigation,
    required this.foldable,
    required super.child,
  });

  final AppSideNavigation? navigation;
  final bool foldable;

  @override
  bool updateShouldNotify(_ViewportScope oldWidget) =>
      oldWidget.navigation != navigation || oldWidget.foldable != foldable;
}

class _WindowGeometry {
  const _WindowGeometry(
    this.size,
    this.barEdge,
    this.foldable,
    this.divisions,
    this.systemBarBottom,
  );

  final Size size;
  final AppVerticalBarEdge? barEdge;
  final bool foldable;
  final List<Rect> divisions;
  final double? systemBarBottom;

  bool matches(Size other) =>
      (size.width - other.width).abs() < 1 &&
      (size.height - other.height).abs() < 1;

  static _WindowGeometry? parse(Object? event) {
    if (event is! Map ||
        event['width'] is! num ||
        event['height'] is! num ||
        event['divisions'] is! List) {
      return null;
    }
    final size = Size(
      (event['width'] as num).toDouble(),
      (event['height'] as num).toDouble(),
    );
    final edge = switch (event['barEdge']) {
      'left' => AppVerticalBarEdge.left,
      'right' => AppVerticalBarEdge.right,
      _ => null,
    };
    final divisions = <Rect>[
      for (final region in event['divisions'] as List)
        if (region is List &&
            region.length == 4 &&
            region.every((v) => v is num && v.isFinite))
          Rect.fromLTWH(
            (region[0] as num).toDouble(),
            (region[1] as num).toDouble(),
            (region[2] as num).toDouble(),
            (region[3] as num).toDouble(),
          ),
    ];
    final systemBarBottom = event['systemBarBottom'];
    return _WindowGeometry(
      size,
      edge,
      event['foldable'] == true,
      divisions,
      systemBarBottom is num && systemBarBottom.isFinite
          ? systemBarBottom.toDouble()
          : null,
    );
  }
}
