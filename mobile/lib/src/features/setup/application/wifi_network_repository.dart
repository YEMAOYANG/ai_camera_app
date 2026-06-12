import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:network_info_plus/network_info_plus.dart';
import 'package:permission_handler/permission_handler.dart';

final wifiNetworkRepositoryProvider = Provider<WifiNetworkRepository>((ref) {
  return WifiNetworkRepository(NetworkInfo());
});

class WifiNetworkRepository {
  const WifiNetworkRepository(this._networkInfo);

  final NetworkInfo _networkInfo;

  Future<WifiNetworkResult> currentWifi() async {
    if (kIsWeb) {
      return const WifiNetworkResult.unavailable(
        message: '当前平台不支持读取 Wi-Fi 名称，请手动输入。',
      );
    }

    try {
      if (Platform.isIOS || Platform.isAndroid) {
        final permission = await _ensureLocationPermission();
        if (!permission.granted) {
          return WifiNetworkResult.permissionRequired(
            message: permission.message,
          );
        }
      }

      final rawName = await _networkInfo.getWifiName();
      final ssid = _normalizeSsid(rawName);
      if (ssid == null) {
        return const WifiNetworkResult.unavailable(
          message: '未能读取当前 Wi-Fi，请确认已连接家庭网络并允许定位权限。',
        );
      }
      return WifiNetworkResult.detected(ssid: ssid);
    } catch (_) {
      return const WifiNetworkResult.unavailable(
        message: '当前 Wi-Fi 信息读取失败，请手动输入网络名称。',
      );
    }
  }

  Future<_WifiPermissionResult> _ensureLocationPermission() async {
    final status = await Permission.locationWhenInUse.status;
    if (status.isGranted || status.isLimited) {
      return const _WifiPermissionResult.granted();
    }
    if (status.isPermanentlyDenied || status.isRestricted) {
      return const _WifiPermissionResult.denied(
        '需要允许定位权限后才能读取当前 Wi-Fi 名称。你也可以先手动输入。',
      );
    }
    final requested = await Permission.locationWhenInUse.request();
    if (requested.isGranted || requested.isLimited) {
      return const _WifiPermissionResult.granted();
    }
    return const _WifiPermissionResult.denied('未获得定位权限，无法自动识别当前 Wi-Fi，请手动输入。');
  }

  String? _normalizeSsid(String? value) {
    final trimmed = value?.trim();
    if (trimmed == null || trimmed.isEmpty) return null;
    if (trimmed == '<unknown ssid>') return null;
    if (trimmed.length >= 2 &&
        trimmed.startsWith('"') &&
        trimmed.endsWith('"')) {
      return trimmed.substring(1, trimmed.length - 1);
    }
    return trimmed;
  }
}

class WifiNetworkResult {
  const WifiNetworkResult._({
    required this.state,
    required this.message,
    this.ssid,
  });

  const WifiNetworkResult.detected({required String ssid})
    : this._(
        state: WifiNetworkState.detected,
        ssid: ssid,
        message: '已识别当前 Wi-Fi',
      );

  const WifiNetworkResult.permissionRequired({required String message})
    : this._(state: WifiNetworkState.permissionRequired, message: message);

  const WifiNetworkResult.unavailable({required String message})
    : this._(state: WifiNetworkState.unavailable, message: message);

  final WifiNetworkState state;
  final String message;
  final String? ssid;

  bool get hasSsid => ssid != null && ssid!.trim().isNotEmpty;
}

enum WifiNetworkState { detected, permissionRequired, unavailable }

class _WifiPermissionResult {
  const _WifiPermissionResult._({required this.granted, required this.message});

  const _WifiPermissionResult.granted()
    : this._(granted: true, message: '已获得权限');

  const _WifiPermissionResult.denied(String message)
    : this._(granted: false, message: message);

  final bool granted;
  final String message;
}
