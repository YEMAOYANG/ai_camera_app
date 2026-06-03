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

final taskDetailProvider = FutureProvider.family<GuardianTask, String>((
  ref,
  taskId,
) {
  return ref.watch(taskRepositoryProvider).task(taskId);
});

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

  Future<List<GuardianTask>> todayTasks({String? childId}) async {
    if (_environment.useMockData) {
      return _mockTasks;
    }

    try {
      final response = await _apiClient.get(
        '/tasks/today',
        queryParameters: {'childId': childId},
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
  }) async {
    if (_environment.useMockData) {
      return _mockTasks;
    }

    try {
      final response = await _apiClient.get(
        '/tasks',
        queryParameters: {
          'childId': childId,
          'status': status,
          'date': date,
        },
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

  Future<GuardianTask> completeTask(
    String taskId, {
    String? evidenceSummary,
  }) async {
    if (_environment.useMockData) {
      return _updateMockTask(
        taskId,
        (task) => task.copyWith(
          status: GuardianTaskStatus.awaitingParentConfirmation,
          evidenceSummary:
              evidenceSummary ?? '任务已标记完成，等待家长确认后发放积分。',
          completedAt: DateTime.now().millisecondsSinceEpoch,
        ),
      );
    }

    try {
      final response = await _apiClient.post(
        '/tasks/$taskId/complete',
        data: {'evidenceSummary': evidenceSummary},
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

  List<GuardianTask> _parseTasks(dynamic data) {
    final map = _asMap(data);
    final rawTasks = map['tasks'];
    if (rawTasks is! List) return const [];
    return rawTasks
        .map((task) => GuardianTask.fromJson(_asMap(task)))
        .toList();
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
  final today = DateTime.now().toIso8601String().substring(0, 10);
  return [
    {
      'id': 'drink-break',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '喝水休息',
      'description': '摄像头完成一次温和提醒，孩子已喝水。',
      'type': 'life',
      'status': 'confirmed',
      'scheduledDate': today,
      'scheduledStart': '17:30',
      'scheduledEnd': '',
      'rewardPoints': 1,
      'requiresParentConfirmation': true,
      'evidenceSummary': '摄像头完成一次温和提醒，孩子已喝水。',
      'pointsGrantedAt': DateTime.now().millisecondsSinceEpoch,
    },
    {
      'id': 'math-homework',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '数学作业',
      'description': '25 分钟专注 + 5 分钟休息',
      'type': 'learning',
      'status': 'in_progress',
      'scheduledDate': today,
      'scheduledStart': '19:00',
      'scheduledEnd': '19:40',
      'rewardPoints': 5,
      'requiresParentConfirmation': true,
      'evidenceSummary': '桌面截图显示书写动作稳定，离座后 3 分钟内回座。',
    },
    {
      'id': 'schoolbag',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '检查小书包',
      'description': '睡前 + 明早复查',
      'type': 'schoolbag',
      'status': 'pending',
      'scheduledDate': today,
      'scheduledStart': '20:10',
      'scheduledEnd': '',
      'rewardPoints': 3,
      'requiresParentConfirmation': true,
      'evidenceSummary': '明天按一年级课表准备语文、数学和美术材料。',
    },
    {
      'id': 'english-read',
      'familyId': 'mock_family',
      'childId': 'mock_child',
      'title': '英语听读',
      'description': '15 分钟',
      'type': 'learning',
      'status': 'awaiting_parent_confirmation',
      'scheduledDate': today,
      'scheduledStart': '19:50',
      'scheduledEnd': '',
      'rewardPoints': 3,
      'requiresParentConfirmation': true,
      'evidenceSummary': '音频片段显示朗读完成，需要家长确认发音任务结果。',
    },
  ].map(GuardianTask.fromJson).toList();
}

Map<String, dynamic> _asMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}
