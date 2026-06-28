import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/features/tasks/application/task_repository.dart';

/// Tasks Tab 当前可见的周查询；离屏时 coordinator 用 fallbackWeekQuery 补刷。
final activeTaskWeekQueryProvider = StateProvider<TaskWeekQuery?>((ref) => null);

DateTime startOfTaskWeek(DateTime date) {
  final day = DateTime(date.year, date.month, date.day);
  return day.subtract(Duration(days: day.weekday - 1));
}

TaskWeekQuery? fallbackTaskWeekQuery(String? childId) {
  if (childId == null || childId.isEmpty) return null;
  final weekStart = startOfTaskWeek(DateTime.now());
  return TaskWeekQuery(
    startDate: weekStart,
    endDate: weekStart.add(const Duration(days: 6)),
    childId: childId,
  );
}
