import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/points/domain/point_models.dart';

final pointRepositoryProvider = Provider<PointRepository>((ref) {
  return PointRepository(apiClient: ref.watch(apiClientProvider));
});

final pointsSummaryProvider = FutureProvider<PointsSummary>((ref) async {
  final repository = ref.watch(pointRepositoryProvider);
  final account = await repository.account();
  final ledger = await repository.ledger(childId: account.childId);
  return PointsSummary(account: account, ledger: ledger);
});

class PointException implements Exception {
  const PointException(this.message, {this.code = 'point_error'});

  final String message;
  final String code;
}

class PointRepository {
  PointRepository({required this._apiClient});

  final ApiClient _apiClient;

  Future<PointAccount> account({String? childId}) async {
    try {
      final response = await _apiClient.get(
        '/points/account',
        queryParameters: {'childId': childId},
      );
      final map = _asMap(response.data);
      final account = map['account'];
      if (account is Map) {
        return PointAccount.fromJson(_asMap(account));
      }
      final accounts = map['accounts'];
      if (accounts is List && accounts.isNotEmpty) {
        final parsed = accounts.map((item) {
          return PointAccount.fromJson(_asMap(item));
        }).toList();
        final total = parsed.fold<int>(0, (sum, item) => sum + item.balance);
        return PointAccount(
          familyId: parsed.first.familyId,
          childId: parsed.first.childId,
          balance: total,
          updatedAt: parsed.first.updatedAt,
        );
      }
      return PointAccount.empty;
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<PointLedgerEntry>> ledger({String? childId}) async {
    try {
      final response = await _apiClient.get(
        '/points/ledger',
        queryParameters: {'childId': childId},
      );
      final raw = _asMap(response.data)['ledger'];
      if (raw is! List) return const [];
      return raw
          .map((entry) => PointLedgerEntry.fromJson(_asMap(entry)))
          .toList();
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<PointAccount> adjust({
    required String childId,
    required int delta,
    String? note,
  }) async {
    try {
      final response = await _apiClient.post(
        '/points/adjust',
        data: {'childId': childId, 'delta': delta, 'note': note},
      );
      return PointAccount.fromJson(_asMap(_asMap(response.data)['account']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  PointException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return PointException(
          message,
          code: code is String ? code : 'point_error',
        );
      }
    }
    return const PointException('积分数据暂时不可用，请稍后重试。', code: 'network_error');
  }
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
