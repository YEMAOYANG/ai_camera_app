import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/storage/onboarding_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

const hasCompletedInitialSetupKey = 'hasCompletedInitialSetup';

final setupStoreProvider = Provider<SetupStore>((ref) {
  return SetupStore(ref.watch(sharedPreferencesProvider));
});

class SetupStore {
  const SetupStore(this._preferences);

  final SharedPreferences _preferences;

  bool get hasCompletedInitialSetup {
    return _preferences.getBool(hasCompletedInitialSetupKey) ?? false;
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
