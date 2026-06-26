import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/network/api_client.dart';
import 'package:warm_sight/src/features/rewards/domain/reward_models.dart';

final rewardRepositoryProvider = Provider<RewardRepository>((ref) {
  return RewardRepository(apiClient: ref.watch(apiClientProvider));
});

final rewardItemsProvider = FutureProvider<List<RewardItem>>((ref) {
  return ref.watch(rewardRepositoryProvider).items();
});

final rewardRedemptionsProvider = FutureProvider<List<RewardRedemption>>((ref) {
  return ref.watch(rewardRepositoryProvider).redemptions();
});

final rewardsSummaryProvider = FutureProvider<RewardsSummary>((ref) async {
  final repository = ref.watch(rewardRepositoryProvider);
  final items = await repository.items();
  final redemptions = await repository.redemptions();
  return RewardsSummary(items: items, redemptions: redemptions);
});

final rewardDetailProvider = FutureProvider.family<RewardItem, String>((
  ref,
  itemId,
) {
  return ref.watch(rewardRepositoryProvider).item(itemId);
});

class RewardException implements Exception {
  const RewardException(this.message, {this.code = 'reward_error'});

  final String message;
  final String code;
}

class RewardRepository {
  RewardRepository({required this._apiClient});

  final ApiClient _apiClient;

  Future<List<RewardItem>> items({String? childId}) async {
    try {
      final response = await _apiClient.get(
        '/rewards/items',
        queryParameters: {'childId': childId},
      );
      final raw = _asMap(response.data)['items'];
      if (raw is! List) return const [];
      return raw.map((item) => RewardItem.fromJson(_asMap(item))).toList();
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardItem> item(String itemId) async {
    try {
      final response = await _apiClient.get('/rewards/items/$itemId');
      return RewardItem.fromJson(_asMap(_asMap(response.data)['item']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<RewardRedemption>> redemptions({String? childId}) async {
    try {
      final response = await _apiClient.get(
        '/rewards/redemptions',
        queryParameters: {'childId': childId},
      );
      final raw = _asMap(response.data)['redemptions'];
      if (raw is! List) return const [];
      return raw
          .map((redemption) => RewardRedemption.fromJson(_asMap(redemption)))
          .toList();
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardItem> createItem({
    required String childId,
    required String title,
    required int pointsCost,
    String? description,
    String? category,
    String? icon,
  }) async {
    final body = {
      'childId': childId,
      'title': title,
      'pointsCost': pointsCost,
      'description': description,
      'category': category,
      'icon': icon,
    };
    try {
      final response = await _apiClient.post('/rewards/items', data: body);
      return RewardItem.fromJson(_asMap(_asMap(response.data)['item']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardItem> updateItem({
    required String itemId,
    required String title,
    required int pointsCost,
    String? description,
    String? category,
    String? icon,
  }) async {
    final body = {
      'title': title,
      'pointsCost': pointsCost,
      'description': description,
      'category': category,
      'icon': icon,
    };
    try {
      final response = await _apiClient.patch(
        '/rewards/items/$itemId',
        data: body,
      );
      return RewardItem.fromJson(_asMap(_asMap(response.data)['item']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<void> deleteItem(String itemId) async {
    try {
      await _apiClient.delete('/rewards/items/$itemId');
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardRedemption> createRedemption(String rewardItemId) async {
    try {
      final response = await _apiClient.post(
        '/rewards/redemptions',
        data: {'rewardItemId': rewardItemId},
      );
      return RewardRedemption.fromJson(
        _asMap(_asMap(response.data)['redemption']),
      );
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardRedemption> fulfillRedemption(String redemptionId) async {
    try {
      final response = await _apiClient.post(
        '/rewards/redemptions/$redemptionId/fulfill',
      );
      return RewardRedemption.fromJson(
        _asMap(_asMap(response.data)['redemption']),
      );
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardRedemption> cancelRedemption(String redemptionId) async {
    try {
      final response = await _apiClient.post(
        '/rewards/redemptions/$redemptionId/cancel',
      );
      return RewardRedemption.fromJson(
        _asMap(_asMap(response.data)['redemption']),
      );
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  RewardException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return RewardException(
          message,
          code: code is String ? code : 'reward_error',
        );
      }
    }
    return const RewardException('奖励数据暂时不可用，请稍后重试。', code: 'network_error');
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
