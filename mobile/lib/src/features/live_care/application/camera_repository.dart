import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/network/api_client.dart';
import 'package:mira_guardian_app/src/features/live_care/domain/camera_models.dart';

final cameraRepositoryProvider = Provider<CameraRepository>((ref) {
  return CameraRepository(
    environment: ref.watch(appEnvironmentProvider),
    apiClient: ref.watch(apiClientProvider),
    dio: ref.watch(dioProvider),
  );
});

final cameraHealthProvider = FutureProvider<CameraHealth>((ref) {
  return ref.watch(cameraRepositoryProvider).health();
});

final cameraRuntimeProvider = FutureProvider<CameraRuntime>((ref) {
  return ref.watch(cameraRepositoryProvider).runtime();
});

final cameraSnapshotProvider = FutureProvider<CameraSnapshotFrame>((ref) {
  return ref.watch(cameraRepositoryProvider).snapshot();
});

final liveCareStatusProvider = FutureProvider<LiveCareStatus>((ref) async {
  final repository = ref.watch(cameraRepositoryProvider);
  final health = await repository.health();
  final runtime = await repository.runtime();
  return LiveCareStatus(health: health, runtime: runtime);
});

class CameraRepository {
  const CameraRepository({
    required AppEnvironment environment,
    required ApiClient apiClient,
    required Dio dio,
  }) : _environment = environment,
       _apiClient = apiClient,
       _dio = dio;

  final AppEnvironment _environment;
  final ApiClient _apiClient;
  final Dio _dio;

  Future<CameraHealth> health() async {
    if (_environment.useMockData) return CameraHealth.mock;

    try {
      final response = await _apiClient.get('/camera/health');
      return CameraHealth.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) return CameraHealth.fromJson(_asMap(data));
      throw _fromDio(error, fallback: '摄像头健康状态暂时不可用。');
    }
  }

  Future<CameraRuntime> runtime() async {
    if (_environment.useMockData) return CameraRuntime.mock;

    try {
      final response = await _apiClient.get('/camera/runtime');
      return CameraRuntime.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) return CameraRuntime.fromJson(_asMap(data));
      throw _fromDio(error, fallback: '摄像头运行状态暂时不可用。');
    }
  }

  Future<CameraSnapshotFrame> snapshot() async {
    if (_environment.useMockData) {
      return const CameraSnapshotFrame(
        available: false,
        bytes: null,
        contentType: '',
        message: '开发模式下未拉取真实快照',
      );
    }

    try {
      final response = await _dio.get<List<int>>(
        '/camera/snapshot',
        options: Options(responseType: ResponseType.bytes),
      );
      final bytes = response.data;
      if (bytes == null || bytes.isEmpty) {
        return const CameraSnapshotFrame(
          available: false,
          bytes: null,
          contentType: '',
          message: '后端未返回可用快照',
        );
      }
      return CameraSnapshotFrame(
        available: true,
        bytes: Uint8List.fromList(bytes),
        contentType: response.headers.value('content-type') ?? 'image/jpeg',
        message: '快照已从后端代理同步',
      );
    } on DioException catch (error) {
      final data = error.response?.data;
      if (data is Map) {
        final message = data['message'];
        return CameraSnapshotFrame(
          available: false,
          bytes: null,
          contentType: '',
          message: message is String && message.isNotEmpty
              ? message
              : '真实快照暂不可用',
        );
      }
      return const CameraSnapshotFrame(
        available: false,
        bytes: null,
        contentType: '',
        message: '真实快照暂不可用',
      );
    }
  }

  CameraException _fromDio(DioException error, {required String fallback}) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return CameraException(
          message,
          code: code is String ? code : 'camera_error',
        );
      }
    }
    return CameraException(fallback, code: 'network_error');
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
