import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';

const selectedDeviceIdPreferenceKey = 'selectedDeviceId';

final selectedDeviceIdProvider = StateProvider<String?>((ref) {
  final value = ref
      .watch(sharedPreferencesProvider)
      .getString(selectedDeviceIdPreferenceKey);
  return value == null || value.isEmpty ? null : value;
});

final selectedDeviceProvider = FutureProvider<GuardianDevice?>((ref) async {
  final repository = ref.watch(deviceRepositoryProvider);
  final preferences = ref.watch(sharedPreferencesProvider);
  final selectedId = ref.watch(selectedDeviceIdProvider);
  final devices = await repository.devices();
  if (devices.isEmpty) {
    await preferences.remove(selectedDeviceIdPreferenceKey);
    ref.read(selectedDeviceIdProvider.notifier).state = null;
    return null;
  }

  final selected = _findActiveDevice(devices, selectedId);
  if (selected != null) return selected;

  final backendDefault = await repository.defaultDevice();
  final fallback =
      _findActiveDevice(devices, backendDefault?.id) ??
      _firstDefaultDevice(devices) ??
      _firstActiveDevice(devices);
  if (fallback == null) {
    await preferences.remove(selectedDeviceIdPreferenceKey);
    ref.read(selectedDeviceIdProvider.notifier).state = null;
    return null;
  }
  await preferences.setString(selectedDeviceIdPreferenceKey, fallback.id);
  ref.read(selectedDeviceIdProvider.notifier).state = fallback.id;
  return fallback;
});

Future<void> selectDevice(WidgetRef ref, String deviceId) async {
  final value = deviceId.trim();
  if (value.isEmpty) return;
  await ref
      .read(sharedPreferencesProvider)
      .setString(selectedDeviceIdPreferenceKey, value);
  ref.read(selectedDeviceIdProvider.notifier).state = value;
  ref.invalidate(selectedDeviceProvider);
}

GuardianDevice? _findActiveDevice(List<GuardianDevice> devices, String? id) {
  if (id == null || id.isEmpty) return null;
  for (final device in devices) {
    if (device.id == id && device.status != 'unbound') return device;
  }
  return null;
}

GuardianDevice? _firstDefaultDevice(List<GuardianDevice> devices) {
  for (final device in devices) {
    if (device.isDefault && device.status != 'unbound') return device;
  }
  return null;
}

GuardianDevice? _firstActiveDevice(List<GuardianDevice> devices) {
  for (final device in devices) {
    if (device.status != 'unbound') return device;
  }
  return null;
}
