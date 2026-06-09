import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

final clientDeviceInfoProvider = FutureProvider<ClientDeviceInfo>((ref) async {
  return ClientDeviceInfo.load();
});

class ClientDeviceInfo {
  const ClientDeviceInfo({
    required this.label,
    required this.type,
    required this.platform,
    required this.model,
    required this.hardware,
    required this.osVersion,
    required this.appVersion,
  });

  final String label;
  final String type;
  final String platform;
  final String model;
  final String hardware;
  final String osVersion;
  final String appVersion;

  Map<String, String> get headers {
    return {
      'X-Mira-Device-Label': label,
      'X-Mira-Device-Type': type,
      'X-Mira-Device-Platform': platform,
      if (model.isNotEmpty) 'X-Mira-Device-Model': model,
      if (hardware.isNotEmpty) 'X-Mira-Device-Hardware': hardware,
      if (osVersion.isNotEmpty) 'X-Mira-OS-Version': osVersion,
      if (appVersion.isNotEmpty) 'X-Mira-App-Version': appVersion,
    };
  }

  static Future<ClientDeviceInfo> load() async {
    final appVersion = await _appVersion();
    try {
      final plugin = DeviceInfoPlugin();
      switch (defaultTargetPlatform) {
        case TargetPlatform.iOS:
          final info = await plugin.iosInfo;
          final hardware = info.utsname.machine.trim();
          final model = info.model.trim();
          final label = _iosMarketingName(hardware) ?? _iosFallbackLabel(model);
          return ClientDeviceInfo(
            label: label,
            type: 'phone',
            platform: 'ios',
            model: model,
            hardware: hardware,
            osVersion: '${info.systemName} ${info.systemVersion}'.trim(),
            appVersion: appVersion,
          );
        case TargetPlatform.android:
          final info = await plugin.androidInfo;
          final manufacturer = _titleCase(info.manufacturer);
          final model = info.model.trim();
          return ClientDeviceInfo(
            label: _compactJoin([manufacturer, model], fallback: 'Android 手机'),
            type: 'phone',
            platform: 'android',
            model: model,
            hardware: info.hardware.trim(),
            osVersion: 'Android ${info.version.release}'.trim(),
            appVersion: appVersion,
          );
        case TargetPlatform.macOS:
          final info = await plugin.macOsInfo;
          final model = info.model.trim();
          return ClientDeviceInfo(
            label: model.isEmpty ? 'Mac 设备' : model,
            type: 'desktop',
            platform: 'macos',
            model: model,
            hardware: info.arch.trim(),
            osVersion: info.osRelease.trim(),
            appVersion: appVersion,
          );
        case TargetPlatform.windows:
          final info = await plugin.windowsInfo;
          final computerName = info.computerName.trim();
          return ClientDeviceInfo(
            label: computerName.isEmpty ? 'Windows 设备' : computerName,
            type: 'desktop',
            platform: 'windows',
            model: info.productName.trim(),
            hardware: '',
            osVersion: info.displayVersion.trim(),
            appVersion: appVersion,
          );
        case TargetPlatform.linux:
          final info = await plugin.linuxInfo;
          return ClientDeviceInfo(
            label: info.prettyName.trim().isEmpty
                ? 'Linux 设备'
                : info.prettyName.trim(),
            type: 'desktop',
            platform: 'linux',
            model: info.name.trim(),
            hardware: info.machineId?.trim() ?? '',
            osVersion: info.versionId?.trim() ?? '',
            appVersion: appVersion,
          );
        case TargetPlatform.fuchsia:
          return _fallback(appVersion);
      }
    } catch (_) {
      return _fallback(appVersion);
    }
  }

  static ClientDeviceInfo _fallback(String appVersion) {
    final platform = defaultTargetPlatform.name.toLowerCase();
    final isPhone =
        defaultTargetPlatform == TargetPlatform.iOS ||
        defaultTargetPlatform == TargetPlatform.android;
    final label = switch (defaultTargetPlatform) {
      TargetPlatform.iOS => '本机 iPhone',
      TargetPlatform.android => 'Android 手机',
      TargetPlatform.macOS => 'Mac 设备',
      TargetPlatform.windows => 'Windows 设备',
      TargetPlatform.linux => 'Linux 设备',
      TargetPlatform.fuchsia => '已登录设备',
    };
    return ClientDeviceInfo(
      label: label,
      type: isPhone ? 'phone' : 'desktop',
      platform: platform,
      model: '',
      hardware: '',
      osVersion: '',
      appVersion: appVersion,
    );
  }
}

Future<String> _appVersion() async {
  try {
    final packageInfo = await PackageInfo.fromPlatform();
    final build = packageInfo.buildNumber.trim();
    final version = packageInfo.version.trim();
    if (version.isEmpty) return '';
    return build.isEmpty ? version : '$version+$build';
  } catch (_) {
    return '';
  }
}

String? _iosMarketingName(String hardware) {
  return const {
    'iPhone18,1': 'iPhone 17 Pro',
    'iPhone18,2': 'iPhone 17 Pro Max',
    'iPhone18,3': 'iPhone 17',
  }[hardware];
}

String _iosFallbackLabel(String model) {
  if (model.toLowerCase().contains('ipad')) return '本机 iPad';
  return '本机 iPhone';
}

String _compactJoin(List<String> parts, {required String fallback}) {
  final unique = <String>[];
  for (final part in parts) {
    final trimmed = part.trim();
    if (trimmed.isEmpty) continue;
    if (unique.any((item) => item.toLowerCase() == trimmed.toLowerCase())) {
      continue;
    }
    unique.add(trimmed);
  }
  return unique.isEmpty ? fallback : unique.join(' ');
}

String _titleCase(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) return '';
  return trimmed
      .split(RegExp(r'\s+'))
      .map((word) {
        if (word.isEmpty) return word;
        return word[0].toUpperCase() + word.substring(1).toLowerCase();
      })
      .join(' ');
}
