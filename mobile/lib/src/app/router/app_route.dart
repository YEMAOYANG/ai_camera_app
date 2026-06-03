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
