import 'package:guardian_parent_app/src/features/tasks/domain/task_models.dart';

class TaskTemplateApplyDateResolution {
  const TaskTemplateApplyDateResolution({
    required this.date,
    required this.adjusted,
    required this.message,
  });

  final DateTime date;
  final bool adjusted;
  final String message;
}

TaskTemplateApplyDateResolution resolveTemplateApplyDate({
  required DateTime now,
  required DateTime selectedDate,
  required String dayType,
  required List<TaskTemplateRow> rows,
}) {
  final today = _dayOnly(now);
  var candidate = _dayOnly(selectedDate);
  if (candidate.isBefore(today)) {
    candidate = today;
  }
  candidate = _nextMatchingDate(candidate, dayType);

  if (_sameDay(candidate, today) && _templateHasStarted(rows, now)) {
    candidate = _nextMatchingDate(
      candidate.add(const Duration(days: 1)),
      dayType,
    );
  }

  final adjusted = !_sameDay(candidate, _dayOnly(selectedDate));
  return TaskTemplateApplyDateResolution(
    date: candidate,
    adjusted: adjusted,
    message: adjusted ? _applyDateMessage(candidate, today) : '',
  );
}

DateTime _nextMatchingDate(DateTime start, String dayType) {
  var candidate = _dayOnly(start);
  for (var i = 0; i < 14; i++) {
    if (_dayTypeMatches(candidate, dayType)) {
      return candidate;
    }
    candidate = candidate.add(const Duration(days: 1));
  }
  return _dayOnly(start);
}

bool _dayTypeMatches(DateTime date, String dayType) {
  return switch (dayType) {
    'school_day' =>
      date.weekday >= DateTime.monday && date.weekday <= DateTime.friday,
    'weekend' =>
      date.weekday == DateTime.saturday || date.weekday == DateTime.sunday,
    _ => true,
  };
}

bool _templateHasStarted(List<TaskTemplateRow> rows, DateTime now) {
  if (rows.isEmpty) return false;
  final currentMinute = now.hour * 60 + now.minute;
  final earliestStart = rows
      .map((row) => _minutesOfDay(row.startTime))
      .reduce((a, b) => a < b ? a : b);
  final latestEnd = rows
      .map(
        (row) =>
            _minutesOfDay(row.endTime.isEmpty ? row.startTime : row.endTime),
      )
      .reduce((a, b) => a > b ? a : b);
  return earliestStart <= currentMinute || latestEnd <= currentMinute;
}

String _applyDateMessage(DateTime target, DateTime today) {
  if (_sameDay(target, today.add(const Duration(days: 1)))) {
    return '已安排到明天';
  }
  final weekStart = _startOfWeek(today);
  final targetWeekStart = _startOfWeek(target);
  final prefix = _sameDay(weekStart, targetWeekStart) ? '本周' : '下周';
  return '已安排到$prefix${_weekdayShort(target)}';
}

DateTime _startOfWeek(DateTime date) {
  final day = _dayOnly(date);
  return day.subtract(Duration(days: day.weekday - DateTime.monday));
}

String _weekdayShort(DateTime date) {
  return const ['一', '二', '三', '四', '五', '六', '日'][date.weekday - 1];
}

int _minutesOfDay(String time) {
  final parts = time.split(':');
  final hour = parts.isNotEmpty ? int.tryParse(parts[0]) ?? 0 : 0;
  final minute = parts.length > 1 ? int.tryParse(parts[1]) ?? 0 : 0;
  return hour * 60 + minute;
}

DateTime _dayOnly(DateTime date) => DateTime(date.year, date.month, date.day);

bool _sameDay(DateTime a, DateTime b) =>
    a.year == b.year && a.month == b.month && a.day == b.day;
