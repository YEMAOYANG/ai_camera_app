import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/features/setup/application/setup_repository.dart';

final setupDraftProvider = StateProvider<SetupDraft>((ref) {
  return const SetupDraft();
});

void syncSetupDraftFromStatus(WidgetRef ref, SetupStatus status) {
  ref.read(setupDraftProvider.notifier).state = setupDraftFromStatus(status);
}

SetupDraft setupDraftFromStatus(SetupStatus status) {
  final identity = status.parentRelationshipKey.isNotEmpty
      ? status.parentRelationshipKey
      : status.parentRelationship.isNotEmpty
      ? status.parentRelationship
      : status.parentDisplayName;
  // Rebuild the draft from the current account's setup status. Do not merge
  // with the previous draft, otherwise a logout/login switch can keep the
  // former account's child profile in the new account's first setup flow.
  return SetupDraft(
    parentIdentity: identity,
    parentName: status.parentDisplayName.isNotEmpty
        ? status.parentDisplayName
        : status.parentRelationship,
    familyRole: status.parentRole.trim(),
    deviceName: status.deviceName.trim(),
    room: status.deviceLocation.trim(),
    wifiName: status.wifiName.trim(),
    childName: status.childName.trim(),
    childBirthday: status.childBirthday.trim(),
    childSleepTime: status.childSleepTime.trim().isEmpty
        ? '21:00'
        : status.childSleepTime.trim(),
    childGender: status.childGender.trim().isEmpty
        ? 'unspecified'
        : status.childGender.trim(),
    childStage: status.childEducationStage.trim().isEmpty
        ? '幼儿园'
        : status.childEducationStage.trim(),
    childGrade: status.childGrade.trim(),
    cameraWakeName: status.cameraWakeName.trim().isEmpty
        ? '小豆'
        : status.cameraWakeName.trim(),
  );
}

class SetupDraft {
  const SetupDraft({
    this.parentIdentity = '',
    this.parentName = '',
    this.familyRole = '',
    this.deviceName = '',
    this.room = '',
    this.wifiName = '',
    this.wifiPassword = '',
    this.childName = '',
    this.childBirthday = '',
    this.childSleepTime = '21:00',
    this.childGender = 'unspecified',
    this.childStage = '幼儿园',
    this.childGrade = '',
    this.cameraWakeName = '小豆',
    this.emergencyName = '',
    this.emergencyPhone = '',
  });

  final String parentIdentity;
  final String parentName;
  final String familyRole;
  final String deviceName;
  final String room;
  final String wifiName;
  final String wifiPassword;
  final String childName;
  final String childBirthday;
  final String childSleepTime;
  final String childGender;
  final String childStage;
  final String childGrade;
  final String cameraWakeName;
  final String emergencyName;
  final String emergencyPhone;

  SetupDraft copyWith({
    String? parentIdentity,
    String? parentName,
    String? familyRole,
    String? deviceName,
    String? room,
    String? wifiName,
    String? wifiPassword,
    String? childName,
    String? childBirthday,
    String? childSleepTime,
    String? childGender,
    String? childStage,
    String? childGrade,
    String? cameraWakeName,
    String? emergencyName,
    String? emergencyPhone,
  }) {
    return SetupDraft(
      parentIdentity: parentIdentity ?? this.parentIdentity,
      parentName: parentName ?? this.parentName,
      familyRole: familyRole ?? this.familyRole,
      deviceName: deviceName ?? this.deviceName,
      room: room ?? this.room,
      wifiName: wifiName ?? this.wifiName,
      wifiPassword: wifiPassword ?? this.wifiPassword,
      childName: childName ?? this.childName,
      childBirthday: childBirthday ?? this.childBirthday,
      childSleepTime: childSleepTime ?? this.childSleepTime,
      childGender: childGender ?? this.childGender,
      childStage: childStage ?? this.childStage,
      childGrade: childGrade ?? this.childGrade,
      cameraWakeName: cameraWakeName ?? this.cameraWakeName,
      emergencyName: emergencyName ?? this.emergencyName,
      emergencyPhone: emergencyPhone ?? this.emergencyPhone,
    );
  }
}
