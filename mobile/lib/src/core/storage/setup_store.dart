import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

const hasCompletedInitialSetupKey = 'hasCompletedInitialSetup';
const pendingSetupGradeCodeKey = 'pendingSetupGradeCode';
const pendingSetupSchoolYearStartKey = 'pendingSetupSchoolYearStart';
const pendingSetupChildNicknameKey = 'pendingSetupChildNickname';
const pendingSetupOwnerUserIdKey = 'pendingSetupOwnerUserId';

final setupStoreProvider = Provider<SetupStore>((ref) {
  return SetupStore(ref.watch(sharedPreferencesProvider));
});

class SetupStore {
  const SetupStore(this._preferences);

  final SharedPreferences _preferences;

  bool get hasCompletedInitialSetup {
    return _preferences.getBool(hasCompletedInitialSetupKey) ?? false;
  }

  String get pendingGradeCode {
    return _preferences.getString(pendingSetupGradeCodeKey) ?? '';
  }

  int? get pendingSchoolYearStartYear {
    return _preferences.getInt(pendingSetupSchoolYearStartKey);
  }

  String get pendingChildNickname {
    return _preferences.getString(pendingSetupChildNicknameKey) ?? '';
  }

  String get pendingOwnerUserId {
    return _preferences.getString(pendingSetupOwnerUserIdKey) ?? '';
  }

  /// Claims the local, unfinished setup draft for one authenticated account.
  ///
  /// Pending setup fields intentionally keep their existing keys so in-progress
  /// drafts survive app upgrades. The owner id is the privacy boundary: a
  /// different (or previously unknown) account clears those fields before it
  /// can enter the setup flow.
  Future<void> claimPendingOwner(String userId) async {
    final normalizedUserId = userId.trim();
    if (normalizedUserId.isEmpty) {
      await clearPendingChildProfile();
      await _preferences.remove(pendingSetupOwnerUserIdKey);
      return;
    }

    if (pendingOwnerUserId == normalizedUserId) return;

    // Clear first, then publish the new owner. This ordering prevents stale
    // child data from becoming visible to the newly authenticated account.
    await clearPendingChildProfile();
    await _preferences.setString(pendingSetupOwnerUserIdKey, normalizedUserId);
  }

  Future<void> savePendingChildNickname(String nickname) async {
    final normalized = nickname.trim();
    if (normalized.isEmpty) {
      await _preferences.remove(pendingSetupChildNicknameKey);
      return;
    }
    await _preferences.setString(pendingSetupChildNicknameKey, normalized);
  }

  Future<void> savePendingGrade({
    required String gradeCode,
    required int schoolYearStartYear,
  }) async {
    await _preferences.setString(pendingSetupGradeCodeKey, gradeCode);
    await _preferences.setInt(
      pendingSetupSchoolYearStartKey,
      schoolYearStartYear,
    );
  }

  Future<void> clearPendingGrade() async {
    await _preferences.remove(pendingSetupGradeCodeKey);
    await _preferences.remove(pendingSetupSchoolYearStartKey);
  }

  Future<void> clearPendingChildProfile() async {
    await clearPendingGrade();
    await _preferences.remove(pendingSetupChildNicknameKey);
  }

  Future<void> markCompleted() {
    return _preferences.setBool(hasCompletedInitialSetupKey, true);
  }

  Future<void> reset() {
    return _preferences.remove(hasCompletedInitialSetupKey);
  }

  // Development reset if needed:
  // await sharedPreferences.remove(hasCompletedInitialSetupKey);
}
