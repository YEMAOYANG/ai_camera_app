import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/network/api_client.dart';
import 'package:mira_guardian_app/src/features/rewards/domain/reward_models.dart';

final rewardRepositoryProvider = Provider<RewardRepository>((ref) {
  return RewardRepository(
    environment: ref.watch(appEnvironmentProvider),
    apiClient: ref.watch(apiClientProvider),
  );
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
  RewardRepository({
    required AppEnvironment environment,
    required ApiClient apiClient,
  }) : _environment = environment,
       _apiClient = apiClient {
    _mockItems = _buildMockItems();
    _mockRedemptions = _buildMockRedemptions();
  }

  final AppEnvironment _environment;
  final ApiClient _apiClient;
  late List<RewardItem> _mockItems;
  late List<RewardRedemption> _mockRedemptions;

  Future<List<RewardItem>> items({String? childId}) async {
    if (_environment.useMockData) return _mockItems;

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
    if (_environment.useMockData) {
      return _mockItems.firstWhere(
        (item) => item.id == itemId,
        orElse: () => _mockItems.first,
      );
    }

    try {
      final response = await _apiClient.get('/rewards/items/$itemId');
      return RewardItem.fromJson(_asMap(_asMap(response.data)['item']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<RewardRedemption>> redemptions({String? childId}) async {
    if (_environment.useMockData) return _mockRedemptions;

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
    if (_environment.useMockData) {
      final item = RewardItem.fromJson({
        'id': 'reward_mock_${DateTime.now().millisecondsSinceEpoch}',
        'familyId': 'mock_family',
        ...body,
        'status': 'active',
      });
      _mockItems = [item, ..._mockItems];
      return item;
    }

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
    if (_environment.useMockData) {
      final index = _mockItems.indexWhere((item) => item.id == itemId);
      if (index < 0) return _mockItems.first;
      final current = _mockItems[index];
      final item = RewardItem(
        id: current.id,
        familyId: current.familyId,
        childId: current.childId,
        title: title,
        description: description ?? current.description,
        pointsCost: pointsCost,
        category: category ?? current.category,
        status: current.status,
        icon: icon ?? current.icon,
      );
      _mockItems = [..._mockItems]..[index] = item;
      return item;
    }

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
    if (_environment.useMockData) {
      _mockItems = _mockItems.where((item) => item.id != itemId).toList();
      return;
    }
    try {
      await _apiClient.delete('/rewards/items/$itemId');
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<RewardRedemption> createRedemption(String rewardItemId) async {
    if (_environment.useMockData) {
      final item = await this.item(rewardItemId);
      final redemption = RewardRedemption(
        id: 'redemption_mock_${DateTime.now().millisecondsSinceEpoch}',
        childId: item.childId,
        rewardItemId: item.id,
        rewardTitle: item.title,
        pointsCost: item.pointsCost,
        status: RedemptionStatus.redeemed,
        requestedAt: DateTime.now().millisecondsSinceEpoch,
        fulfilledAt: null,
        cancelledAt: null,
      );
      _mockRedemptions = [redemption, ..._mockRedemptions];
      return redemption;
    }

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
    if (_environment.useMockData) {
      return _updateMockRedemption(
        redemptionId,
        (redemption) => RewardRedemption(
          id: redemption.id,
          childId: redemption.childId,
          rewardItemId: redemption.rewardItemId,
          rewardTitle: redemption.rewardTitle,
          pointsCost: redemption.pointsCost,
          status: RedemptionStatus.fulfilled,
          requestedAt: redemption.requestedAt,
          fulfilledAt: DateTime.now().millisecondsSinceEpoch,
          cancelledAt: redemption.cancelledAt,
        ),
      );
    }

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
    if (_environment.useMockData) {
      return _updateMockRedemption(
        redemptionId,
        (redemption) => RewardRedemption(
          id: redemption.id,
          childId: redemption.childId,
          rewardItemId: redemption.rewardItemId,
          rewardTitle: redemption.rewardTitle,
          pointsCost: redemption.pointsCost,
          status: RedemptionStatus.cancelled,
          requestedAt: redemption.requestedAt,
          fulfilledAt: redemption.fulfilledAt,
          cancelledAt: DateTime.now().millisecondsSinceEpoch,
        ),
      );
    }

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

  RewardRedemption _updateMockRedemption(
    String redemptionId,
    RewardRedemption Function(RewardRedemption redemption) update,
  ) {
    final index = _mockRedemptions.indexWhere(
      (redemption) => redemption.id == redemptionId,
    );
    if (index < 0) return _mockRedemptions.first;
    final next = update(_mockRedemptions[index]);
    _mockRedemptions = [..._mockRedemptions]..[index] = next;
    return next;
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

List<RewardItem> _buildMockItems() {
  return [
    {
      'id': 'reward-family-game',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '周末亲子游戏 20 分钟',
      'description': '由家长兑现，适合作业和睡前任务稳定完成后兑换。',
      'pointsCost': 10,
      'category': 'family',
      'status': 'active',
      'icon': 'game',
    },
    {
      'id': 'reward-story',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '睡前故事加一篇',
      'description': '温和的小奖励，不把屏幕时间作为默认激励。',
      'pointsCost': 6,
      'category': 'bedtime',
      'status': 'active',
      'icon': 'book',
    },
    {
      'id': 'reward-park',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '周末公园选择权',
      'description': '让孩子选择一次家庭活动路线。',
      'pointsCost': 18,
      'category': 'outing',
      'status': 'active',
      'icon': 'park',
    },
  ].map(RewardItem.fromJson).toList();
}

List<RewardRedemption> _buildMockRedemptions() {
  return [
    {
      'id': 'redemption_mock_board_game',
      'childId': 'mock_child',
      'rewardItemId': 'reward-family-game',
      'rewardTitle': '周末亲子游戏 20 分钟',
      'pointsCost': 10,
      'status': 'redeemed',
      'requestedAt': DateTime.now().millisecondsSinceEpoch - 1000 * 60 * 40,
    },
  ].map(RewardRedemption.fromJson).toList();
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
