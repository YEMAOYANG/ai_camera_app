import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/care/domain/care_models.dart';

final careRepositoryProvider = Provider<CareRepository>((ref) {
  return CareRepository(apiClient: ref.watch(apiClientProvider));
});

final careCapabilitiesProvider =
    FutureProvider.family<List<CareCapability>, CareCapabilitiesQuery>((
      ref,
      query,
    ) {
      return ref
          .watch(careRepositoryProvider)
          .capabilities(childId: query.childId, deviceId: query.deviceId);
    });

final routineWindowsProvider =
    FutureProvider.family<List<RoutineWindow>, RoutineWindowsQuery>((
      ref,
      query,
    ) {
      return ref
          .watch(careRepositoryProvider)
          .routineWindows(childId: query.childId, dayType: query.dayType);
    });

final careSummaryProvider = FutureProvider.family<CareSummary, String?>((
  ref,
  childId,
) {
  return ref.watch(careRepositoryProvider).summary(childId: childId);
});

final careReminderEventsProvider = FutureProvider<List<CareReminderEvent>>((
  ref,
) {
  return ref.watch(careRepositoryProvider).reminderEvents();
});

class CareCapabilitiesQuery {
  const CareCapabilitiesQuery({this.childId, this.deviceId});

  final String? childId;
  final String? deviceId;

  @override
  bool operator ==(Object other) {
    return other is CareCapabilitiesQuery &&
        other.childId == childId &&
        other.deviceId == deviceId;
  }

  @override
  int get hashCode => Object.hash(childId, deviceId);
}

class RoutineWindowsQuery {
  const RoutineWindowsQuery({this.childId, required this.dayType});

  final String? childId;
  final String dayType;

  @override
  bool operator ==(Object other) {
    return other is RoutineWindowsQuery &&
        other.childId == childId &&
        other.dayType == dayType;
  }

  @override
  int get hashCode => Object.hash(childId, dayType);
}

class CareRepository {
  const CareRepository({required this.apiClient});

  final ApiClient apiClient;

  Future<List<CareCapability>> capabilities({
    String? childId,
    String? deviceId,
  }) async {
    try {
      final response = await apiClient.get(
        '/care/capabilities',
        queryParameters: {
          if (childId != null && childId.isNotEmpty) 'childId': childId,
          if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
        },
      );
      final raw = _asMap(response.data)['capabilities'];
      if (raw is! List) return const [];
      return raw.map((item) => CareCapability.fromJson(_asMap(item))).toList();
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '看护能力暂时不可用。');
    }
  }

  Future<List<CareCapability>> updateCapabilities({
    required List<Map<String, Object?>> capabilities,
    String? childId,
    String? deviceId,
  }) async {
    try {
      final response = await apiClient.patch(
        '/care/capabilities',
        data: {
          if (childId != null && childId.isNotEmpty) 'childId': childId,
          if (deviceId != null && deviceId.isNotEmpty) 'deviceId': deviceId,
          'capabilities': capabilities,
        },
      );
      final raw = _asMap(response.data)['capabilities'];
      if (raw is! List) return const [];
      return raw.map((item) => CareCapability.fromJson(_asMap(item))).toList();
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '看护能力暂时无法保存。');
    }
  }

  Future<List<RoutineWindow>> routineWindows({
    String? childId,
    String? dayType,
  }) async {
    try {
      final response = await apiClient.get(
        '/care/routine-windows',
        queryParameters: {
          if (childId != null && childId.isNotEmpty) 'childId': childId,
          if (dayType != null && dayType.isNotEmpty) 'dayType': dayType,
        },
      );
      final raw = _asMap(response.data)['windows'];
      if (raw is! List) return const [];
      return raw.map((item) => RoutineWindow.fromJson(_asMap(item))).toList();
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '作息设置暂时不可用。');
    }
  }

  Future<List<RoutineWindow>> replaceRoutineWindows({
    required List<RoutineWindow> windows,
    String? childId,
    required String dayType,
  }) async {
    try {
      final response = await apiClient.put(
        '/care/routine-windows?dayType=$dayType',
        data: {
          if (childId != null && childId.isNotEmpty) 'childId': childId,
          'dayType': dayType,
          'windows': windows.map((item) => item.toJson()).toList(),
        },
      );
      final raw = _asMap(response.data)['windows'];
      if (raw is! List) return const [];
      return raw.map((item) => RoutineWindow.fromJson(_asMap(item))).toList();
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '作息设置暂时无法保存。');
    }
  }

  Future<CareSummary> summary({String? childId}) async {
    try {
      final response = await apiClient.get(
        '/care/summary',
        queryParameters: {
          if (childId != null && childId.isNotEmpty) 'childId': childId,
        },
      );
      return CareSummary.fromJson(_asMap(response.data));
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '看护状态暂时不可用。');
    }
  }

  Future<List<CareReminderEvent>> reminderEvents({String? childId}) async {
    try {
      final response = await apiClient.get(
        '/reminders/events',
        queryParameters: {
          if (childId != null && childId.isNotEmpty) 'childId': childId,
        },
      );
      final raw = _asMap(response.data)['events'];
      if (raw is! List) return const [];
      return raw
          .map((item) => CareReminderEvent.fromJson(_asMap(item)))
          .toList();
    } on DioException catch (error) {
      throw _fromDio(error, fallback: '提醒记录暂时不可用。');
    }
  }
}

CareException _fromDio(DioException error, {required String fallback}) {
  final data = error.response?.data;
  if (data is Map) {
    final message = data['message'];
    final code = data['error'];
    if (message is String && message.isNotEmpty) {
      return CareException(message, code: code is String ? code : 'care_error');
    }
  }
  return CareException(fallback, code: 'network_error');
}

class CareException implements Exception {
  const CareException(this.message, {required this.code});

  final String message;
  final String code;

  @override
  String toString() => message;
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
