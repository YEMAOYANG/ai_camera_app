import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/app/router/startup_gate.dart';
import 'package:guardian_parent_app/src/app/shell/app_shell.dart';
import 'package:guardian_parent_app/src/core/storage/auth_session_store.dart';
import 'package:guardian_parent_app/src/core/storage/onboarding_store.dart';
import 'package:guardian_parent_app/src/features/alerts/presentation/alerts_screen.dart';
import 'package:guardian_parent_app/src/features/auth/presentation/login_screen.dart';
import 'package:guardian_parent_app/src/features/home/presentation/home_screen.dart';
import 'package:guardian_parent_app/src/features/live_care/presentation/live_monitor_screen.dart';
import 'package:guardian_parent_app/src/features/live_care/presentation/live_care_screen.dart';
import 'package:guardian_parent_app/src/features/points/presentation/points_screen.dart';
import 'package:guardian_parent_app/src/features/profile/presentation/profile_pages.dart';
import 'package:guardian_parent_app/src/features/profile/presentation/profile_screen.dart';
import 'package:guardian_parent_app/src/features/rewards/presentation/reward_detail_screen.dart';
import 'package:guardian_parent_app/src/features/rewards/presentation/rewards_screen.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/setup_flow_screens.dart';
import 'package:guardian_parent_app/src/features/tasks/presentation/task_detail_screen.dart';
import 'package:guardian_parent_app/src/features/tasks/presentation/tasks_screen.dart';
import 'package:guardian_parent_app/src/features/welcome/presentation/welcome_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final onboardingStore = ref.watch(onboardingStoreProvider);
  final sessionStore = ref.watch(authSessionStoreProvider);
  final initialLocation = _initialLocation(
    onboardingStore: onboardingStore,
    sessionStore: sessionStore,
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
        builder: (_, _) => const LegalRemoteDocumentPage(
          documentKey: 'user-agreement',
        ),
      ),
      GoRoute(
        path: privacyPolicyPath,
        name: 'legalPrivacyPolicy',
        builder: (_, _) => const LegalRemoteDocumentPage(
          documentKey: 'privacy-policy',
        ),
      ),
      GoRoute(
        path: profileChildPrivacyPath,
        name: 'legalChildPrivacyAuthorization',
        builder: (_, _) => const LegalRemoteDocumentPage(
          documentKey: 'child-privacy-authorization',
        ),
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
      GoRoute(
        path: liveMonitorPath,
        name: 'liveMonitor',
        builder: (_, _) => const LiveMonitorScreen(),
      ),
      GoRoute(
        path: liveEventsPath,
        name: 'liveEvents',
        builder: (_, _) => const LiveEventsScreen(),
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
        path: redemptionsPath,
        name: 'redemptions',
        builder: (_, _) => const RedemptionsPage(),
      ),
      GoRoute(
        path: rewardEditPath,
        name: 'rewardCreate',
        builder: (_, _) => const RewardEditPage(),
      ),
      GoRoute(
        path: '$rewardEditPath/:itemId',
        name: 'rewardEdit',
        builder: (_, state) {
          return RewardEditPage(itemId: state.pathParameters['itemId']);
        },
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
        path: profileFamilyHubPath,
        name: 'profileFamilyHub',
        builder: (_, _) => const FamilyHubPage(),
      ),
      GoRoute(
        path: profileDeviceHubPath,
        name: 'profileDeviceHub',
        builder: (_, _) => const DeviceCareHubPage(),
      ),
      GoRoute(
        path: profileTaskRewardHubPath,
        name: 'profileTaskRewardHub',
        builder: (_, _) => const TaskRewardHubPage(),
      ),
      GoRoute(
        path: profileRulesHubPath,
        name: 'profileRulesHub',
        builder: (_, _) => const RulesReminderHubPage(),
      ),
      GoRoute(
        path: profilePrivacyHubPath,
        name: 'profilePrivacyHub',
        builder: (_, _) => const PrivacyAuthorizationHubPage(),
      ),
      GoRoute(
        path: profileAccountSettingsPath,
        name: 'profileAccountSettings',
        builder: (_, _) => const AccountSettingsHubPage(),
      ),
      GoRoute(
        path: profileAccountPath,
        name: 'profileAccount',
        builder: (_, _) => const AccountProfilePage(),
      ),
      GoRoute(
        path: profileSecurityPath,
        name: 'profileSecurity',
        builder: (_, _) => const AccountSecurityPage(),
      ),
      GoRoute(
        path: profileFamilyMembersPath,
        name: 'profileFamilyMembers',
        builder: (_, _) => const FamilyMembersPage(),
      ),
      GoRoute(
        path: profileChildPath,
        name: 'profileChild',
        builder: (_, _) => const ChildProfilePage(),
      ),
      GoRoute(
        path: profileContactsPath,
        name: 'profileContacts',
        builder: (_, _) => const EmergencyContactsPage(),
      ),
      GoRoute(
        path: profileDevicesPath,
        name: 'profileDevices',
        builder: (_, _) => const DeviceManagementPage(),
      ),
      GoRoute(
        path: '$profileDeviceDetailPath/:deviceId',
        name: 'profileDeviceDetail',
        builder: (_, state) {
          return DeviceDetailPage(
            deviceId: state.pathParameters['deviceId'] ?? '',
          );
        },
      ),
      GoRoute(
        path: profileCameraStatusPath,
        name: 'profileCameraStatus',
        builder: (_, _) => const CameraCareStatusPage(),
      ),
      GoRoute(
        path: profileAiRulesPath,
        name: 'profileAiRules',
        builder: (_, _) => const AiCareRulesPage(),
      ),
      GoRoute(
        path: profileNotificationsPath,
        name: 'profileNotifications',
        builder: (_, _) => const NotificationSettingsPage(),
      ),
      GoRoute(
        path: profilePrivacyPath,
        name: 'profilePrivacy',
        builder: (_, _) => const PrivacyPermissionsPage(),
      ),
      GoRoute(
        path: profileConversationPath,
        name: 'profileConversation',
        builder: (_, _) => const ConversationRulesPage(),
      ),
      GoRoute(
        path: profileEducationPath,
        name: 'profileEducation',
        builder: (_, _) => const EducationContentPage(),
      ),
      GoRoute(
        path: profileAboutPath,
        name: 'profileAbout',
        builder: (_, _) => const AboutPage(),
      ),
      GoRoute(
        path: profileSubscriptionPath,
        name: 'profileSubscription',
        builder: (_, _) => const SubscriptionPage(),
      ),
      GoRoute(
        path: profileDailyReportPath,
        name: 'profileDailyReport',
        builder: (_, _) => const DailyReportPage(),
      ),
      GoRoute(
        path: profileWeeklyReportPath,
        name: 'profileWeeklyReport',
        builder: (_, _) => const WeeklyReportPage(),
      ),
      GoRoute(
        path: profileMomentsPath,
        name: 'profileMoments',
        builder: (_, _) => const GrowthMomentsPage(),
      ),
      GoRoute(
        path: profileFeedbackPath,
        name: 'profileFeedback',
        builder: (_, _) => const FeedbackPage(),
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

String _initialLocation({
  required OnboardingStore onboardingStore,
  required AuthSessionStore sessionStore,
}) {
  if (!onboardingStore.hasSeenOnboarding) return welcomePath;
  if (!sessionStore.hasUsableSession) return loginPath;
  return '/';
}

AppRoute routeFromLocation(String location) {
  return AppRoute.values.firstWhere(
    (route) => location.startsWith(route.path),
    orElse: () => AppRoute.home,
  );
}
