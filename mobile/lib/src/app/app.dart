import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/app/realtime/app_realtime_scope.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/app/router/app_router.dart';
import 'package:warm_sight/src/core/theme/app_theme.dart';
import 'package:warm_sight/src/shared/widgets/app_glass_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_viewport.dart';

class GuardianApp extends ConsumerWidget {
  const GuardianApp({this.displayGeometryEvents, super.key});

  final Stream<Object?>? displayGeometryEvents;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);

    return AppRealtimeScope(
      child: MaterialApp.router(
        title: '暖瞳',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        builder: (context, child) => AppViewport(
          geometryEvents: displayGeometryEvents,
          navigationChanges: router.routerDelegate,
          useSystemBarForTabs: () {
            final routes = router.routerDelegate.currentConfiguration;
            final location = routes.isEmpty
                ? null
                : routes.last.matchedLocation;
            return AppRoute.values.any((route) => route.path == location);
          },
          child: AppGlassScope(child: child!),
        ),
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        routerConfig: router,
      ),
    );
  }
}
