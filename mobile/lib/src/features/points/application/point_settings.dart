import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';

final pointRewardSettingsRepositoryProvider =
    Provider<PointRewardSettingsRepository>((ref) {
      return PointRewardSettingsRepository(
        apiClient: ref.watch(apiClientProvider),
      );
    });

final pointRewardSettingsProvider = FutureProvider<PointRewardSettings>((
  ref,
) async {
  return ref.watch(pointRewardSettingsRepositoryProvider).fetch();
});

class PointRewardSettingsRepository {
  PointRewardSettingsRepository({required this.apiClient});

  final ApiClient apiClient;

  Future<PointRewardSettings> fetch() async {
    try {
      final response = await apiClient.get('/points/settings');
      return PointRewardSettings.fromJson(_asMap(response.data)['settings']);
    } on DioException catch (error) {
      throw _pointExceptionFromDio(error);
    }
  }

  Future<PointRewardSettings> save({
    required int stageThreshold,
    required String unit,
  }) async {
    try {
      final response = await apiClient.patch(
        '/points/settings',
        data: {'stageThreshold': stageThreshold, 'unit': unit},
      );
      return PointRewardSettings.fromJson(_asMap(response.data)['settings']);
    } on DioException catch (error) {
      throw _pointExceptionFromDio(error);
    }
  }
}

class PointRewardUnitOption {
  const PointRewardUnitOption({
    required this.key,
    required this.label,
    required this.suffix,
    required this.description,
    required this.imageAsset,
  });

  final String key;
  final String label;
  final String suffix;
  final String description;
  final String imageAsset;

  static const fallback = PointRewardUnitOption(
    key: 'flower',
    label: '小红花',
    suffix: '朵小红花',
    description: '默认方案，适合低龄儿童和日常正向反馈。',
    imageAsset: 'assets/images/points/unit-flower.png',
  );

  static PointRewardUnitOption fromJson(dynamic value) {
    final json = _asMap(value);
    return PointRewardUnitOption(
      key: _asString(json['key']),
      label: _asString(json['label']),
      suffix: _asString(json['suffix']),
      description: _asString(json['description']),
      imageAsset: _asString(json['imageAsset']),
    );
  }
}

class PointRewardSettings {
  const PointRewardSettings({
    required this.stageThreshold,
    required this.unit,
    required this.unitOptions,
    this.updatedAt,
  });

  final int stageThreshold;
  final PointRewardUnitOption unit;
  final List<PointRewardUnitOption> unitOptions;
  final int? updatedAt;

  static const fallback = PointRewardSettings(
    stageThreshold: 10,
    unit: PointRewardUnitOption.fallback,
    unitOptions: [PointRewardUnitOption.fallback],
  );

  String get unitKey => unit.key;
  String get unitLabel => unit.label;
  String get unitSuffix => unit.suffix;

  String amount(int value) {
    return '$value $unitSuffix';
  }

  static PointRewardSettings fromJson(dynamic value) {
    final json = _asMap(value);
    final options = _asList(json['unitOptions'])
        .map(PointRewardUnitOption.fromJson)
        .where((item) => item.key.isNotEmpty)
        .toList();
    final unitKey = _asString(json['unit']);
    final selected = options.firstWhere(
      (item) => item.key == unitKey,
      orElse: () =>
          options.isNotEmpty ? options.first : PointRewardUnitOption.fallback,
    );
    return PointRewardSettings(
      stageThreshold: _asInt(
        json['stageThreshold'],
        fallback: 10,
      ).clamp(1, 99).toInt(),
      unit: selected,
      unitOptions: options.isEmpty
          ? const [PointRewardUnitOption.fallback]
          : options,
      updatedAt: json['updatedAt'] == null ? null : _asInt(json['updatedAt']),
    );
  }
}

PointException _pointExceptionFromDio(DioException error) {
  final data = error.response?.data;
  if (data is Map) {
    final message = data['message'];
    final code = data['error'];
    if (message is String && message.isNotEmpty) {
      return PointException(
        message,
        code: code is String ? code : 'point_settings_error',
      );
    }
  }
  return const PointException('积分设置暂时不可用，请稍后重试。', code: 'network_error');
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

List<dynamic> _asList(dynamic value) {
  return value is List ? value : const [];
}

String _asString(dynamic value) {
  return value is String ? value : '';
}

int _asInt(dynamic value, {int fallback = 0}) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value) ?? fallback;
  return fallback;
}
