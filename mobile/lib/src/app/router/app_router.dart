import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/app/shell/app_shell.dart';
import 'package:mira_guardian_app/src/features/alerts/presentation/alerts_screen.dart';
import 'package:mira_guardian_app/src/features/home/presentation/home_screen.dart';
import 'package:mira_guardian_app/src/features/live_care/presentation/live_care_screen.dart';
import 'package:mira_guardian_app/src/features/profile/presentation/profile_screen.dart';
import 'package:mira_guardian_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:mira_guardian_app/src/features/welcome/presentation/welcome_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: welcomePath,
    routes: [
      GoRoute(path: '/', redirect: (_, _) => welcomePath),
      GoRoute(
        path: welcomePath,
        name: 'welcome',
        builder: (_, _) => const WelcomeScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) {
          return AppShell(child: child);
        },
        routes: [
          GoRoute(
            path: AppRoute.home.path,
            name: AppRoute.home.name,
            builder: (_, _) => const HomeScreen(),
          ),
          GoRoute(
            path: AppRoute.tasks.path,
            name: AppRoute.tasks.name,
            builder: (_, _) => const TasksScreen(),
          ),
          GoRoute(
            path: AppRoute.live.path,
            name: AppRoute.live.name,
            builder: (_, _) => const LiveCareScreen(),
          ),
          GoRoute(
            path: AppRoute.alerts.path,
            name: AppRoute.alerts.name,
            builder: (_, _) => const AlertsScreen(),
          ),
          GoRoute(
            path: AppRoute.profile.path,
            name: AppRoute.profile.name,
            builder: (_, _) => const ProfileScreen(),
          ),
        ],
      ),
    ],
  );
});

AppRoute routeFromLocation(String location) {
  return AppRoute.values.firstWhere(
    (route) => location.startsWith(route.path),
    orElse: () => AppRoute.home,
  );
}
