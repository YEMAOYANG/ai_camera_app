import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/features/setup/application/setup_repository.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';

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
  final grade =
      ChildGradeOption.fromCode(status.childGradeCode) ??
      ChildGradeOption.fromLegacy(
        educationStage: status.childEducationStage,
        grade: status.childGrade,
      );
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
    childNickname: status.childNickname.trim(),
    childNicknameEdited: status.childNickname.trim().isNotEmpty,
    childBirthday: status.childBirthday.trim(),
    childSleepTime: status.childSleepTime.trim().isEmpty
        ? '21:00'
        : status.childSleepTime.trim(),
    childGender: status.childGender.trim().isEmpty
        ? 'unspecified'
        : status.childGender.trim(),
    childStage: status.childEducationStage.trim().isEmpty
        ? grade?.stageLabel ?? ''
        : status.childEducationStage.trim(),
    childGrade: status.childGrade.trim(),
    childGradeCode: grade?.code ?? '',
    childSchoolYearStartYear: status.childSchoolYearStartYear,
    cameraWakeName: status.cameraWakeName.trim().isEmpty
        ? '小暖'
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
    this.childNickname = '',
    this.childNicknameEdited = false,
    this.childBirthday = '',
    this.childSleepTime = '21:00',
    this.childGender = 'unspecified',
    this.childStage = '',
    this.childGrade = '',
    this.childGradeCode = '',
    this.childSchoolYearStartYear,
    this.cameraWakeName = '小暖',
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
  final String childNickname;

  /// True after the nickname has an explicit backend value or the parent has
  /// edited the field. This keeps an intentional empty edit from falling back
  /// to a legacy child name on the next rebuild.
  final bool childNicknameEdited;
  final String childBirthday;
  final String childSleepTime;
  final String childGender;
  final String childStage;
  final String childGrade;
  final String childGradeCode;
  final int? childSchoolYearStartYear;
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
    String? childNickname,
    bool? childNicknameEdited,
    String? childBirthday,
    String? childSleepTime,
    String? childGender,
    String? childStage,
    String? childGrade,
    String? childGradeCode,
    int? childSchoolYearStartYear,
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
      childNickname: childNickname ?? this.childNickname,
      childNicknameEdited: childNicknameEdited ?? this.childNicknameEdited,
      childBirthday: childBirthday ?? this.childBirthday,
      childSleepTime: childSleepTime ?? this.childSleepTime,
      childGender: childGender ?? this.childGender,
      childStage: childStage ?? this.childStage,
      childGrade: childGrade ?? this.childGrade,
      childGradeCode: childGradeCode ?? this.childGradeCode,
      childSchoolYearStartYear:
          childSchoolYearStartYear ?? this.childSchoolYearStartYear,
      cameraWakeName: cameraWakeName ?? this.cameraWakeName,
      emergencyName: emergencyName ?? this.emergencyName,
      emergencyPhone: emergencyPhone ?? this.emergencyPhone,
    );
  }
}
