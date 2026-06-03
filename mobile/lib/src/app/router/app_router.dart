import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/app/router/startup_gate.dart';
import 'package:mira_guardian_app/src/app/shell/app_shell.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/storage/auth_session_store.dart';
import 'package:mira_guardian_app/src/core/storage/onboarding_store.dart';
import 'package:mira_guardian_app/src/core/storage/setup_store.dart';
import 'package:mira_guardian_app/src/features/alerts/presentation/alerts_screen.dart';
import 'package:mira_guardian_app/src/features/auth/presentation/login_screen.dart';
import 'package:mira_guardian_app/src/features/home/presentation/home_screen.dart';
import 'package:mira_guardian_app/src/features/legal/presentation/privacy_policy_screen.dart';
import 'package:mira_guardian_app/src/features/legal/presentation/user_agreement_screen.dart';
import 'package:mira_guardian_app/src/features/live_care/presentation/live_care_screen.dart';
import 'package:mira_guardian_app/src/features/points/presentation/points_screen.dart';
import 'package:mira_guardian_app/src/features/profile/presentation/profile_screen.dart';
import 'package:mira_guardian_app/src/features/rewards/presentation/reward_detail_screen.dart';
import 'package:mira_guardian_app/src/features/rewards/presentation/rewards_screen.dart';
import 'package:mira_guardian_app/src/features/setup/presentation/setup_flow_screens.dart';
import 'package:mira_guardian_app/src/features/tasks/presentation/task_detail_screen.dart';
import 'package:mira_guardian_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:mira_guardian_app/src/features/welcome/presentation/welcome_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final onboardingStore = ref.watch(onboardingStoreProvider);
  final sessionStore = ref.watch(authSessionStoreProvider);
  final setupStore = ref.watch(setupStoreProvider);
  final environment = ref.watch(appEnvironmentProvider);
  final initialLocation = _initialLocation(
    onboardingStore: onboardingStore,
    sessionStore: sessionStore,
    setupStore: setupStore,
    environment: environment,
  );

  return GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(path: '/', builder: (_, _) => const StartupGate()),
      GoRoute(
        path: welcomePath,
        name: 'welcome',
        redirect: (_, _) {
          return onboardingStore.hasSeenOnboarding ? loginPath : null;
        },
        builder: (context, _) {
          return WelcomeScreen(
            onComplete: () async {
              await onboardingStore.markSeen();
              if (context.mounted) {
                context.go(loginPath);
              }
            },
          );
        },
      ),
      GoRoute(
        path: loginPath,
        name: 'login',
        builder: (_, _) => const LoginScreen(),
      ),
      GoRoute(
        path: userAgreementPath,
        name: 'legalUserAgreement',
        builder: (_, _) => const UserAgreementScreen(),
      ),
      GoRoute(
        path: privacyPolicyPath,
        name: 'legalPrivacyPolicy',
        builder: (_, _) => const PrivacyPolicyScreen(),
      ),
      GoRoute(
        path: setupParentIdentityPath,
        name: 'setupParentIdentity',
        builder: (_, _) => const ParentIdentitySetupScreen(),
      ),
      GoRoute(
        path: setupDevicePath,
        name: 'setupDevice',
        builder: (_, _) => const DeviceEntrySetupScreen(),
      ),
      GoRoute(
        path: setupWifiPath,
        name: 'setupWifi',
        builder: (_, _) => const WifiSetupScreen(),
      ),
      GoRoute(
        path: setupBindSuccessPath,
        name: 'setupBindSuccess',
        builder: (_, _) => const BindSuccessSetupScreen(),
      ),
      GoRoute(
        path: setupChildProfilePath,
        name: 'setupChildProfile',
        builder: (_, _) => const ChildProfileSetupScreen(),
      ),
      GoRoute(
        path: setupEmergencyContactsPath,
        name: 'setupEmergencyContacts',
        builder: (_, _) => const EmergencyContactsSetupScreen(),
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
            path: '$taskDetailPath/:taskId',
            name: 'taskDetail',
            builder: (_, state) {
              return TaskDetailScreen(
                taskId: state.pathParameters['taskId'] ?? 'math-homework',
              );
            },
          ),
          GoRoute(
            path: pointsPath,
            name: 'points',
            builder: (_, _) => const PointsScreen(),
          ),
          GoRoute(
            path: rewardsPath,
            name: 'rewards',
            builder: (_, _) => const RewardsScreen(),
          ),
          GoRoute(
            path: '$rewardDetailPath/:itemId',
            name: 'rewardDetail',
            builder: (_, state) {
              return RewardDetailScreen(
                itemId: state.pathParameters['itemId'] ?? 'reward-family-game',
              );
            },
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

String _initialLocation({
  required OnboardingStore onboardingStore,
  required AuthSessionStore sessionStore,
  required SetupStore setupStore,
  required AppEnvironment environment,
}) {
  if (!onboardingStore.hasSeenOnboarding) return welcomePath;
  if (!sessionStore.hasUsableSession) return loginPath;
  if (environment.useMockData && setupStore.hasCompletedInitialSetup) {
    return AppRoute.home.path;
  }
  return '/';
}

AppRoute routeFromLocation(String location) {
  return AppRoute.values.firstWhere(
    (route) => location.startsWith(route.path),
    orElse: () => AppRoute.home,
  );
}
