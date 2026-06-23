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
    required this.cameraName,
    required this.cameraNameIntro,
    required this.cameraNameIntroAt,
    required this.contacts,
    required this.nextStep,
    required this.parentDisplayName,
    required this.parentRelationship,
    required this.parentRelationshipKey,
    required this.deviceName,
    required this.deviceLocation,
    required this.wifiName,
    required this.childName,
    required this.childGender,
    required this.childBirthday,
    required this.childSleepTime,
    required this.childEducationStage,
    required this.childGrade,
    required this.cameraWakeName,
  });

  final bool completed;
  final String parentIdentity;
  final String deviceBinding;
  final String wifi;
  final String childProfile;
  final String cameraName;
  final String cameraNameIntro;
  final int? cameraNameIntroAt;
  final String contacts;
  final String nextStep;
  final String parentDisplayName;
  final String parentRelationship;
  final String parentRelationshipKey;
  final String deviceName;
  final String deviceLocation;
  final String wifiName;
  final String childName;
  final String childGender;
  final String childBirthday;
  final String childSleepTime;
  final String childEducationStage;
  final String childGrade;
  final String cameraWakeName;

  bool get hasDeviceBinding => deviceBinding == 'done';

  String get routePath {
    if (completed || nextStep == 'home') return AppRoute.home.path;
    if (parentIdentity != 'done') return setupParentIdentityPath;
    if (childProfile != 'done') return setupChildProfilePath;
    return AppRoute.home.path;
  }

  static SetupStatus fromResponse(dynamic data) {
    final map = _asMap(data);
    final setup = _asMap(map['setup']);
    final parent = _asMap(map['parentIdentity']);
    final device = _asMap(map['device']);
    final wifi = _asMap(map['wifi']);
    final child = _asMap(map['child']);
    final cameraName = _asMap(map['cameraName']);
    return SetupStatus(
      completed: setup['completed'] == true,
      parentIdentity: _asString(setup['parentIdentity'], fallback: 'pending'),
      deviceBinding: _asString(setup['deviceBinding'], fallback: 'pending'),
      wifi: _asString(setup['wifi'], fallback: 'pending'),
      childProfile: _asString(setup['childProfile'], fallback: 'pending'),
      cameraName: _asString(setup['cameraName'], fallback: 'pending'),
      cameraNameIntro: _asString(setup['cameraNameIntro'], fallback: 'pending'),
      cameraNameIntroAt: _asNullableInt(setup['cameraNameIntroAt']),
      contacts: _asString(setup['contacts'], fallback: 'pending'),
      nextStep: _asString(setup['nextStep'], fallback: 'parentIdentity'),
      parentDisplayName: _asString(parent['displayName']),
      parentRelationship: _asString(parent['relationship']),
      parentRelationshipKey: _asString(parent['relationshipKey']),
      deviceName: _asString(device['name']),
      deviceLocation: _asString(device['location']),
      wifiName: _asString(wifi['ssid']),
      childName: _asString(child['name']),
      childGender: _asString(child['gender'], fallback: 'unspecified'),
      childBirthday: _asString(child['birthday']),
      childSleepTime: _asString(child['sleepTime']),
      childEducationStage: _asString(child['educationStage']),
      childGrade: _asString(child['grade']),
      cameraWakeName: _asString(cameraName['wakeName']),
    );
  }
}

class SetupBroadcastResult {
  const SetupBroadcastResult({
    required this.played,
    required this.status,
    required this.message,
  });

  final bool played;
  final String status;
  final String message;

  static SetupBroadcastResult fromResponse(dynamic data) {
    final broadcast = _asMap(_asMap(data)['broadcast']);
    return SetupBroadcastResult(
      played: broadcast['played'] == true,
      status: _asString(broadcast['status']),
      message: _asString(broadcast['message'], fallback: '摄像头暂时不在线，稍后可以再试听。'),
    );
  }
}

class SetupRepository {
  const SetupRepository({required this._apiClient, required this._setupStore});

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
    required String relationshipKey,
  }) {
    return _postStep('/setup/parent-identity', {
      'displayName': displayName,
      'relationship': relationship,
      'relationshipKey': relationshipKey,
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
    String gender = 'unspecified',
    String? ageStage,
    String? educationStage,
    String? grade,
    String? birthday,
    String? sleepTime,
  }) {
    return _postStep('/setup/child', {
      'name': name,
      'nickname': nickname,
      'gender': gender,
      'ageStage': ageStage,
      'educationStage': educationStage,
      'grade': grade,
      'birthday': birthday,
      'sleepTime': sleepTime,
    });
  }

  Future<SetupStatus> saveCameraName({required String wakeName}) {
    return _postStep('/setup/camera-name', {'wakeName': wakeName});
  }

  Future<SetupBroadcastResult> playCameraNameIntro() async {
    try {
      final response = await _apiClient.post('/setup/camera-name/intro');
      return SetupBroadcastResult.fromResponse(response.data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<SetupBroadcastResult> previewCameraName({
    required String wakeName,
  }) async {
    try {
      final response = await _apiClient.post(
        '/setup/camera-name/preview',
        data: {'wakeName': wakeName},
      );
      return SetupBroadcastResult.fromResponse(response.data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
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

int? _asNullableInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}
