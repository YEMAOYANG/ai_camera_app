import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';

final dioProvider = Provider<Dio>((ref) {
  final environment = ref.watch(appEnvironmentProvider);

  return Dio(
    BaseOptions(
      baseUrl: environment.apiBaseUrl,
      connectTimeout: const Duration(seconds: 8),
      receiveTimeout: const Duration(seconds: 12),
      sendTimeout: const Duration(seconds: 8),
      headers: {'Accept': 'application/json'},
    ),
  );
});

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(ref.watch(dioProvider));
});

class ApiClient {
  const ApiClient(this._dio);

  final Dio _dio;

  Future<Response<dynamic>> get(String path) {
    return _dio.get<dynamic>(path);
  }

  Future<Response<dynamic>> post(String path, {Object? data}) {
    return _dio.post<dynamic>(path, data: data);
  }
}
