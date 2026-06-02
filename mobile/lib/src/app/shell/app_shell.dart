import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/app/router/app_router.dart';

class AppShell extends StatelessWidget {
  const AppShell({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final location = GoRouterState.of(context).uri.path;
    final selectedRoute = routeFromLocation(location);
    final selectedIndex = AppRoute.values.indexOf(selectedRoute);

    return Scaffold(
      body: SafeArea(child: child),
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) {
          context.go(AppRoute.values[index].path);
        },
        destinations: [
          for (final route in AppRoute.values)
            NavigationDestination(
              icon: Icon(route.icon),
              selectedIcon: Icon(route.selectedIcon),
              label: route.label,
            ),
        ],
      ),
    );
  }
}
