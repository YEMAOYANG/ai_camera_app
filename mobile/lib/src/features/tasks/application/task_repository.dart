import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/config/app_environment.dart';
import 'package:mira_guardian_app/src/core/network/api_client.dart';
import 'package:mira_guardian_app/src/features/tasks/domain/task_models.dart';

final taskRepositoryProvider = Provider<TaskRepository>((ref) {
  return TaskRepository(
    environment: ref.watch(appEnvironmentProvider),
    apiClient: ref.watch(apiClientProvider),
  );
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

class TaskRepository {
  TaskRepository({
    required AppEnvironment environment,
    required ApiClient apiClient,
  }) : _environment = environment,
       _apiClient = apiClient {
    _mockTasks = _buildMockTasks();
  }

  final AppEnvironment _environment;
  final ApiClient _apiClient;
  late List<GuardianTask> _mockTasks;

  Future<List<GuardianTask>> todayTasks({
    String? childId,
    DateTime? date,
  }) async {
    final targetDate = date == null ? null : _dateText(date);
    if (_environment.useMockData) {
      return _filterMockTasks(childId: childId, date: targetDate);
    }

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
    if (_environment.useMockData) {
      return _filterMockTasks(
        childId: childId,
        status: status,
        date: date,
        startDate: startDate,
        endDate: endDate,
      );
    }

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
    if (_environment.useMockData) {
      return _mockTasks.firstWhere(
        (task) => task.id == taskId,
        orElse: () => _mockTasks.first,
      );
    }

    try {
      final response = await _apiClient.get('/tasks/$taskId');
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<GuardianTask> createTask(GuardianTaskDraft draft) async {
    if (_environment.useMockData) {
      final task = _mockTaskFromDraft(draft);
      _mockTasks = [..._mockTasks, task];
      return task;
    }

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
    if (_environment.useMockData) {
      final created = <GuardianTask>[];
      for (var index = 0; index < drafts.length; index++) {
        created.add(_mockTaskFromDraft(drafts[index], sequence: index));
      }
      _mockTasks = [..._mockTasks, ...created];
      return created;
    }

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
    if (_environment.useMockData) {
      return _updateMockTask(taskId, (task) {
        return task.copyWith(
          title: _optionalString(data['title']) ?? task.title,
          description: _optionalString(data['description']) ?? task.description,
          type: _optionalString(data['taskType']) ?? task.type,
          rewardPoints: _optionalInt(data['rewardPoints']) ?? task.rewardPoints,
          priority: _optionalInt(data['priority']) ?? task.priority,
          status: data['status'] is String
              ? GuardianTaskStatus.fromValue(data['status'] as String)
              : task.status,
        );
      });
    }

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
    if (_environment.useMockData) {
      return _updateMockTask(
        taskId,
        (task) => task.copyWith(status: GuardianTaskStatus.inProgress),
      );
    }

    try {
      final response = await _apiClient.post('/tasks/$taskId/start');
      return GuardianTask.fromJson(_asMap(_asMap(response.data)['task']));
    } on DioException catch (error) {
      throw _fromDio(error);
    }
  }

  Future<List<GuardianTaskEvent>> taskEvents(String taskId) async {
    if (_environment.useMockData) return _mockEventsFor(taskId);

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
    if (_environment.useMockData) {
      return _updateMockTask(
        taskId,
        (task) => task.copyWith(
          status: task.requiresParentConfirmation
              ? GuardianTaskStatus.awaitingParentConfirmation
              : GuardianTaskStatus.completed,
          evidenceSummary: evidenceSummary ?? '任务已完成，等待家长确认后发放积分。',
          completionSource: completionSource,
          completedAt: DateTime.now().millisecondsSinceEpoch,
        ),
      );
    }

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
    if (_environment.useMockData) {
      return _updateMockTask(
        taskId,
        (task) => task.copyWith(
          status: GuardianTaskStatus.confirmed,
          confirmedAt: DateTime.now().millisecondsSinceEpoch,
          pointsGrantedAt: DateTime.now().millisecondsSinceEpoch,
        ),
      );
    }

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
    if (_environment.useMockData) {
      return _updateMockTask(
        taskId,
        (task) => task.copyWith(
          status: GuardianTaskStatus.rejected,
          rejectionReason: reason ?? '证据不足，等待孩子补充完成。',
        ),
      );
    }

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

  GuardianTask _updateMockTask(
    String taskId,
    GuardianTask Function(GuardianTask task) update,
  ) {
    final index = _mockTasks.indexWhere((task) => task.id == taskId);
    if (index < 0) return _mockTasks.first;
    final next = update(_mockTasks[index]);
    _mockTasks = [..._mockTasks]..[index] = next;
    return next;
  }

  GuardianTask _mockTaskFromDraft(GuardianTaskDraft draft, {int sequence = 0}) {
    final now = DateTime.now().millisecondsSinceEpoch;
    final taskId = 'task_mock_${now}_${_mockTasks.length}_$sequence';
    return GuardianTask.fromJson({
      ...draft.toJson(),
      'id': taskId,
      'taskId': taskId,
      'familyId': 'mock_family',
      'status': 'pending',
      'createdAt': now,
      'updatedAt': now,
    });
  }

  List<GuardianTask> _filterMockTasks({
    String? childId,
    String? status,
    String? date,
    String? startDate,
    String? endDate,
  }) {
    return _mockTasks.where((task) {
      if (childId != null && childId.isNotEmpty && task.childId != childId) {
        return false;
      }
      if (status != null && status.isNotEmpty && task.status.value != status) {
        return false;
      }
      if (date != null && date.isNotEmpty && task.scheduledDate != date) {
        return false;
      }
      if (startDate != null &&
          startDate.isNotEmpty &&
          task.scheduledDate.compareTo(startDate) < 0) {
        return false;
      }
      if (endDate != null &&
          endDate.isNotEmpty &&
          task.scheduledDate.compareTo(endDate) > 0) {
        return false;
      }
      return true;
    }).toList();
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

List<GuardianTask> _buildMockTasks() {
  final now = DateTime.now();
  final monday = now.subtract(Duration(days: now.weekday - 1));
  final today = _dateText(now);
  final tomorrow = _dateText(now.add(const Duration(days: 1)));
  final friday = _dateText(monday.add(const Duration(days: 4)));
  return [
    {
      'id': 'drink-break',
      'taskId': 'drink-break',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '喝水休息',
      'description': '5 分钟，先缓冲不催作业',
      'type': 'life',
      'taskType': 'life',
      'scheduleType': 'daily',
      'status': 'confirmed',
      'scheduledDate': today,
      'scheduledStart': '17:30',
      'scheduledEnd': '',
      'rewardPoints': 1,
      'priority': 3,
      'requiresParentConfirmation': true,
      'evidenceSummary': '摄像头完成一次温和提醒，孩子已喝水。',
      'aiObservationSummary': '状态平稳，适合作为作业前缓冲。',
      'pointsGrantedAt': now.millisecondsSinceEpoch,
      'createdAt': now.millisecondsSinceEpoch,
      'updatedAt': now.millisecondsSinceEpoch,
    },
    {
      'id': 'math-homework',
      'taskId': 'math-homework',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '数学作业',
      'description': '25 分钟专注 + 5 分钟休息',
      'type': 'learning',
      'taskType': 'learning',
      'scheduleType': 'weekday',
      'status': 'in_progress',
      'scheduledDate': today,
      'scheduledStart': '19:00',
      'scheduledEnd': '19:40',
      'rewardPoints': 5,
      'priority': 1,
      'requiresParentConfirmation': true,
      'evidenceSummary': '桌面截图显示书写动作稳定，离座后 3 分钟内回座。',
      'aiObservationSummary': '当前专注轮次稳定，结束后建议确认作业证据。',
      'createdAt': now.millisecondsSinceEpoch,
      'updatedAt': now.millisecondsSinceEpoch,
    },
    {
      'id': 'english-read',
      'taskId': 'english-read',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '英语听读',
      'description': '15 分钟',
      'type': 'learning',
      'taskType': 'learning',
      'scheduleType': 'one_time',
      'status': 'awaiting_parent_confirmation',
      'scheduledDate': today,
      'scheduledStart': '19:50',
      'scheduledEnd': '',
      'rewardPoints': 3,
      'priority': 2,
      'requiresParentConfirmation': true,
      'evidenceSummary': '音频片段显示朗读完成，需要家长确认发音任务结果。',
      'aiObservationSummary': '朗读已完成，建议确认后给具体表扬。',
      'createdAt': now.millisecondsSinceEpoch,
      'updatedAt': now.millisecondsSinceEpoch,
    },
    {
      'id': 'schoolbag',
      'taskId': 'schoolbag',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '检查小书包',
      'description': '睡前 + 明早复查',
      'type': 'schoolbag',
      'taskType': 'schoolbag',
      'scheduleType': 'weekly',
      'status': 'pending',
      'scheduledDate': tomorrow,
      'scheduledStart': '20:10',
      'scheduledEnd': '',
      'rewardPoints': 3,
      'priority': 2,
      'requiresParentConfirmation': true,
      'evidenceSummary': '明天按一年级课表准备语文、数学和美术材料。',
      'createdAt': now.millisecondsSinceEpoch,
      'updatedAt': now.millisecondsSinceEpoch,
    },
    {
      'id': 'art-material',
      'taskId': 'art-material',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '美术材料准备',
      'description': '纸杯、彩纸、胶棒',
      'type': 'schoolbag',
      'taskType': 'schoolbag',
      'scheduleType': 'one_time',
      'status': 'pending',
      'scheduledDate': friday,
      'scheduledStart': '07:30',
      'scheduledEnd': '',
      'rewardPoints': 2,
      'priority': 2,
      'requiresParentConfirmation': true,
      'createdAt': now.millisecondsSinceEpoch,
      'updatedAt': now.millisecondsSinceEpoch,
    },
  ].map(GuardianTask.fromJson).toList();
}

List<GuardianTaskEvent> _mockEventsFor(String taskId) {
  final now = DateTime.now().millisecondsSinceEpoch;
  return [
    {
      'id': 'event_${taskId}_created',
      'taskId': taskId,
      'eventType': 'task_created',
      'message': '任务已创建',
      'createdAt': now - 600000,
    },
    {
      'id': 'event_${taskId}_reminder',
      'taskId': taskId,
      'eventType': 'reminder_sent',
      'message': '已提醒孩子准备开始',
      'createdAt': now - 300000,
    },
    {
      'id': 'event_${taskId}_started',
      'taskId': taskId,
      'eventType': 'auto_started',
      'message': '任务已自动开始',
      'createdAt': now - 120000,
    },
  ].map((event) => GuardianTaskEvent.fromJson(event)).toList();
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

int? _optionalInt(Object? value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

String _dateText(DateTime date) {
  final month = date.month.toString().padLeft(2, '0');
  final day = date.day.toString().padLeft(2, '0');
  return '${date.year}-$month-$day';
}
