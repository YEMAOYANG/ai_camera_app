import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:guardian_parent_app/src/core/network/api_client.dart';
import 'package:guardian_parent_app/src/features/tasks/domain/task_models.dart';

final taskRepositoryProvider = Provider<TaskRepository>((ref) {
  return TaskRepository(apiClient: ref.watch(apiClientProvider));
});

final todayTasksProvider = FutureProvider<List<GuardianTask>>((ref) {
  return ref.watch(taskRepositoryProvider).todayTasks();
});

final taskListProvider = FutureProvider<List<GuardianTask>>((ref) {
  return ref.watch(taskRepositoryProvider).listTasks();
});

final taskWeekProvider =
    FutureProvider.family<List<GuardianTask>, TaskWeekQuery>((ref, query) {
      return ref
          .watch(taskRepositoryProvider)
          .listTasks(
            childId: query.childId,
            startDate: _dateText(query.startDate),
            endDate: _dateText(query.endDate),
          );
    });

final taskDetailProvider = FutureProvider.family<GuardianTask, String>((
  ref,
  taskId,
) {
  return ref.watch(taskRepositoryProvider).task(taskId);
});

final taskEventsProvider =
    FutureProvider.family<List<GuardianTaskEvent>, String>((ref, taskId) {
      return ref.watch(taskRepositoryProvider).taskEvents(taskId);
    });

class TaskWeekQuery {
  const TaskWeekQuery({
    required this.startDate,
    required this.endDate,
    this.childId,
  });

  final DateTime startDate;
  final DateTime endDate;
  final String? childId;

  @override
  bool operator ==(Object other) {
    return other is TaskWeekQuery &&
        _dateText(other.startDate) == _dateText(startDate) &&
        _dateText(other.endDate) == _dateText(endDate) &&
        other.childId == childId;
  }

  @override
  int get hashCode =>
      Object.hash(_dateText(startDate), _dateText(endDate), childId);
}

class TaskException implements Exception {
  const TaskException(this.message, {this.code = 'task_error'});

  final String message;
  final String code;
}

enum TaskReminderPhase {
  prepare('prepare'),
  start('start'),
  followUp('follow_up'),
  wrapUp('wrap_up'),
  finish('finish');

  const TaskReminderPhase(this.value);

  final String value;
}

class TaskReminderResult {
  const TaskReminderResult({
    required this.task,
    required this.phase,
    required this.message,
  });

  final GuardianTask task;
  final String phase;
  final String message;
}

class TaskRepository {
  TaskRepository({required ApiClient apiClient}) : _apiClient = apiClient;

  final ApiClient _apiClient;

  Future<List<GuardianTask>> todayTasks({
    String? childId,
    DateTime? date,
  }) async {
    final targetDate = date == null ? null : _dateText(date);
    try {
      final response = await _apiClient.get(
        '/tasks/today',
        queryParameters: _compactQuery({
          'childId': childId,
          'date': targetDate,
        }),
      );
      return _parseTasks(response.data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<GuardianTask>> listTasks({
    String? childId,
    String? status,
    String? date,
    String? startDate,
    String? endDate,
  }) async {
    try {
      final response = await _apiClient.get(
        '/tasks',
        queryParameters: _compactQuery({
          'childId': childId,
          'status': status,
          'date': date,
          'startDate': startDate,
          'endDate': endDate,
        }),
      );
      return _parseTasks(response.data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> task(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId');
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> createTask(GuardianTaskDraft draft) async {
    try {
      final response = await _apiClient.post('/tasks', data: draft.toJson());
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<GuardianTask>> createTasks(
    List<GuardianTaskDraft> drafts, {
    DateTime? date,
  }) async {
    if (drafts.isEmpty) return const [];
    try {
      final response = await _apiClient.post(
        '/tasks/batch',
        data: {
          if (date != null) 'date': _dateText(date),
          'tasks': drafts.map((draft) => draft.toJson()).toList(),
        },
      );
      return _parseTasks(response.data);
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> updateTask(
    String taskId,
    Map<String, Object?> data,
  ) async {
    try {
      final response = await _apiClient.patch('/tasks/$taskId', data: data);
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> cancelTask(String taskId) {
    return updateTask(taskId, {'status': GuardianTaskStatus.cancelled.value});
  }

  Future<GuardianTask> startTask(String taskId) async {
    try {
      final response = await _apiClient.post('/tasks/$taskId/start');
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<TaskReminderResult> sendReminder(
    String taskId, {
    required TaskReminderPhase phase,
  }) async {
    try {
      final response = await _apiClient.post(
        '/tasks/$taskId/reminder',
        data: {'phase': phase.value},
      );
      final map = _asMap(response.data);
      final reminder = _asMap(map['reminder']);
      return TaskReminderResult(
        task: GuardianTask.fromJson(_asMap(map['task'])),
        phase: _optionalString(reminder['phase']) ?? phase.value,
        message: _optionalString(reminder['text']) ?? '已发送提醒',
      );
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<GuardianTaskEvent>> taskEvents(String taskId) async {
    try {
      final response = await _apiClient.get('/tasks/$taskId/events');
      final raw = _asMap(response.data)['events'];
      if (raw is! List) return const [];
      return raw
          .map((event) => GuardianTaskEvent.fromJson(_asMap(event)))
          .toList();
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> completeTask(
    String taskId, {
    String? evidenceSummary,
    String completionSource = 'parent',
  }) async {
    try {
      final response = await _apiClient.post(
        '/tasks/$taskId/complete',
        data: {
          'evidenceSummary': evidenceSummary,
          'completionSource': completionSource,
        },
      );
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> parentConfirm(String taskId) async {
    try {
      final response = await _apiClient.post('/tasks/$taskId/parent-confirm');
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> rejectConfirmation(
    String taskId, {
    String? reason,
  }) async {
    try {
      final response = await _apiClient.post(
        '/tasks/$taskId/reject-confirmation',
        data: {'reason': reason},
      );
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  List<GuardianTask> _parseTasks(dynamic data) {
    final map = _asMap(data);
    final rawTasks = map['tasks'];
    if (rawTasks is! List) return const [];
    return rawTasks.map((task) => GuardianTask.fromJson(_asMap(task))).toList();
  }

  TaskException _fromDio(DioException error) {
    final data = error.response?.data;
    if (data is Map) {
      final message = data['message'];
      final code = data['error'];
      if (message is String && message.isNotEmpty) {
        return TaskException(
          message,
          code: code is String ? code : 'task_error',
        );
      }
    }
    return const TaskException('任务数据暂时不可用，请稍后重试。', code: 'network_error');
  }
}

Map<String, Object?> _compactQuery(Map<String, Object?> query) {
  return Map.fromEntries(
    query.entries.where((entry) {
      final value = entry.value;
      return value != null && (value is! String || value.isNotEmpty);
    }),
  );
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

String? _optionalString(Object? value) {
  if (value is String && value.isNotEmpty) return value;
  return null;
}

String _dateText(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}
