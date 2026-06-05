import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/core/storage/setup_store.dart';

final setupRepositoryProvider = Provider<SetupRepository>((ref) {
  return SetupRepository(
    apiClient: ref.watch(apiClientProvider),
    setupStore: ref.watch(setupStoreProvider),
  );
});

class SetupException implements Exception {
  const SetupException(this.message, {this.code = 'setup_error'});

  final String message;
  final String code;
}

class SetupStatus {
  const SetupStatus({
    required this.completed,
    required this.parentIdentity,
    required this.deviceBinding,
    required this.wifi,
    required this.childProfile,
    required this.contacts,
    required this.nextStep,
  });

  final bool completed;
  final String parentIdentity;
  final String deviceBinding;
  final String wifi;
  final String childProfile;
  final String contacts;
  final String nextStep;

  bool get hasDeviceBinding => deviceBinding == 'done';

  String get routePath {
    if (completed || nextStep == 'home') return AppRoute.home.path;
    return switch (nextStep) {
      'parentIdentity' => setupParentIdentityPath,
      'device' => setupDevicePath,
      'wifi' => setupWifiPath,
      'child' => setupChildProfilePath,
      'contacts' || 'complete' => setupEmergencyContactsPath,
      _ => setupParentIdentityPath,
    };
  }

  static SetupStatus fromResponse(dynamic data) {
    final map = _asMap(data);
    final setup = _asMap(map['setup']);
    return SetupStatus(
      completed: setup['completed'] == true,
      parentIdentity: _asString(setup['parentIdentity'], fallback: 'pending'),
      deviceBinding: _asString(setup['deviceBinding'], fallback: 'pending'),
      wifi: _asString(setup['wifi'], fallback: 'pending'),
      childProfile: _asString(setup['childProfile'], fallback: 'pending'),
      contacts: _asString(setup['contacts'], fallback: 'pending'),
      nextStep: _asString(setup['nextStep'], fallback: 'parentIdentity'),
    );
  }
}

class SetupRepository {
  const SetupRepository({
    required ApiClient apiClient,
    required SetupStore setupStore,
  }) : _apiClient = apiClient,
       _setupStore = setupStore;

  final ApiClient _apiClient;
  final SetupStore _setupStore;

  Future<SetupStatus> status() async {
    try {
      final response = await _apiClient.get('/setup/status');
      final status = SetupStatus.fromResponse(response.data);
      await _syncLocalCompletion(status);
      return status;
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<SetupStatus> saveParentIdentity({
    required String displayName,
    required String relationship,
  }) {
    return _postStep('/setup/parent-identity', {
      'displayName': displayName,
      'relationship': relationship,
    });
  }

  Future<SetupStatus> saveDevice({
    required String deviceName,
    required String location,
    String? bindingCode,
  }) {
    return _postStep('/setup/device', {
      'deviceName': deviceName,
      'location': location,
      'bindingCode': bindingCode,
    });
  }

  Future<SetupStatus> saveWifi({
    required String ssid,
    required String password,
    String authType = 'wpa2',
  }) {
    return _postStep('/setup/wifi', {
      'ssid': ssid,
      'password': password,
      'authType': authType,
    });
  }

  Future<SetupStatus> saveChild({
    required String name,
    String? nickname,
    String? ageStage,
    String? birthday,
  }) {
    return _postStep('/setup/child', {
      'name': name,
      'nickname': nickname,
      'ageStage': ageStage,
      'birthday': birthday,
    });
  }

  Future<SetupStatus> saveContacts({
    required String name,
    required String phone,
    String? relationship,
  }) {
    return _postStep('/setup/contacts', {
      'contacts': [
        {
          'name': name,
          'phone': phone,
          'relationship': relationship ?? 'guardian',
        },
      ],
    });
  }

  Future<SetupStatus> complete() async {
    final status = await _postStep('/setup/complete', const {});
    if (status.completed) {
      await _setupStore.markCompleted();
    }
    return status;
  }

  Future<SetupStatus> _postStep(String path, Map<String, Object?> body) async {
    try {
      final response = await _apiClient.post(path, data: body);
      final status = SetupStatus.fromResponse(response.data);
      await _syncLocalCompletion(status);
      return status;
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<void> _syncLocalCompletion(SetupStatus status) async {
    if (status.completed) {
      await _setupStore.markCompleted();
    } else {
      await _setupStore.reset();
    }
  }

  SetupException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return SetupException(
          message,
          code: code is String ? code : 'setup_error',
        );
      }
    }
    return const SetupException('暂时连不上服务，请稍后再试。', code: 'network_error');
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String _asString(dynamic value, {String fallback = ''}) {
  return value is String && value.isNotEmpty ? value : fallback;
}
