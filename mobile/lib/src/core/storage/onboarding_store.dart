import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const hasSeenOnboardingKey = 'hasSeenOnboarding';

final sharedPreferencesProvider = Provider<SharedPreferences>((ref) {
  throw UnimplementedError('SharedPreferences must be provided in bootstrap.');
});

final onboardingStoreProvider = Provider<OnboardingStore>((ref) {
  return OnboardingStore(ref.watch(sharedPreferencesProvider));
});

class OnboardingStore {
  const OnboardingStore(this._preferences);

  final SharedPreferences _preferences;

  bool get hasSeenOnboarding {
    return _preferences.getBool(hasSeenOnboardingKey) ?? false;
  }

  Future<void> markSeen() {
    return _preferences.setBool(hasSeenOnboardingKey, true);
  }

  // Development reset if needed:
  // await sharedPreferences.remove(hasSeenOnboardingKey);
}
