import 'package:flutter/material.dart';

const welcomePath = '/welcome';
const loginPath = '/login';
const userAgreementPath = '/legal/user-agreement';
const privacyPolicyPath = '/legal/privacy-policy';
const setupParentIdentityPath = '/setup/parent-identity';
const setupDevicePath = '/setup/device';
const setupWifiPath = '/setup/wifi';
const setupBindSuccessPath = '/setup/bind-success';
const setupChildProfilePath = '/setup/child-profile';
const setupEmergencyContactsPath = '/setup/emergency-contacts';
const taskDetailPath = '/tasks/detail';
const pointsPath = '/points';
const rewardsPath = '/rewards';
const rewardDetailPath = '/rewards/detail';
const rewardEditPath = '/rewards/edit';
const redemptionsPath = '/rewards/redemptions';
const liveMonitorPath = '/live/monitor';
const liveEventsPath = '/live/events';
const profileFamilyHubPath = '/profile/family';
const profileDeviceHubPath = '/profile/device-care';
const profileTaskRewardHubPath = '/profile/task-rewards';
const profileRulesHubPath = '/profile/rules-reminders';
const profilePrivacyHubPath = '/profile/privacy-authorization';
const profileAccountPath = '/profile/account';
const profileSecurityPath = '/profile/security';
const profileFamilyMembersPath = '/profile/family-members';
const profileChildPath = '/profile/child';
const profileContactsPath = '/profile/emergency-contacts';
const profileDevicesPath = '/profile/devices';
const profileDeviceDetailPath = '/profile/devices/detail';
const profileCameraStatusPath = '/profile/camera-status';
const profileAiRulesPath = '/profile/ai-care-rules';
const profileNotificationsPath = '/profile/notifications';
const profilePrivacyPath = '/profile/privacy';
const profileChildPrivacyPath = '/legal/child-privacy-authorization';
const profileAboutPath = '/profile/about';
const profileSubscriptionPath = '/profile/subscription';
const profileDailyReportPath = '/profile/reports/daily';
const profileWeeklyReportPath = '/profile/reports/weekly';
const profileMomentsPath = '/profile/moments';
const profileConversationPath = '/profile/conversation';
const profileEducationPath = '/profile/education';
const profileFeedbackPath = '/profile/feedback';

enum AppRoute {
  home('/home', '首页', Icons.home_outlined, Icons.home),
  tasks('/tasks', '任务', Icons.checklist_outlined, Icons.checklist),
  live('/live', '看护', Icons.videocam_outlined, Icons.videocam),
  alerts('/alerts', '告警', Icons.notifications_outlined, Icons.notifications),
  profile('/profile', '我的', Icons.person_outline, Icons.person);

  const AppRoute(this.path, this.label, this.icon, this.selectedIcon);

  final String path;
  final String label;
  final IconData icon;
  final IconData selectedIcon;
}
