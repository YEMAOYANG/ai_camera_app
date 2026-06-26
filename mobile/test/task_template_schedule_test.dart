import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/tasks/application/task_template_schedule.dart';
import 'package:warm_sight/src/features/tasks/domain/task_models.dart';

void main() {
  group('resolveTemplateApplyDate', () {
    test(
      'moves school-day morning template to next school day after afternoon',
      () {
        final result = resolveTemplateApplyDate(
          now: DateTime(2026, 6, 24, 18, 30),
          selectedDate: DateTime(2026, 6, 24),
          dayType: 'school_day',
          rows: _rows(start: '07:15', end: '08:00'),
        );

        expect(result.date, DateTime(2026, 6, 25));
        expect(result.message, '已安排到明天');
      },
    );

    test('keeps school-day bedtime template today when it has not started', () {
      final result = resolveTemplateApplyDate(
        now: DateTime(2026, 6, 24, 18, 30),
        selectedDate: DateTime(2026, 6, 24),
        dayType: 'school_day',
        rows: _rows(start: '20:20', end: '21:00'),
      );

      expect(result.date, DateTime(2026, 6, 24));
      expect(result.adjusted, isFalse);
      expect(result.message, isEmpty);
    });

    test('moves Friday night school-day morning template to next Monday', () {
      final result = resolveTemplateApplyDate(
        now: DateTime(2026, 6, 26, 22),
        selectedDate: DateTime(2026, 6, 26),
        dayType: 'school_day',
        rows: _rows(start: '07:15', end: '08:00'),
      );

      expect(result.date, DateTime(2026, 6, 29));
      expect(result.message, '已安排到下周一');
    });

    test('moves weekday selected weekend template to this Saturday', () {
      final result = resolveTemplateApplyDate(
        now: DateTime(2026, 6, 24, 12),
        selectedDate: DateTime(2026, 6, 24),
        dayType: 'weekend',
        rows: _rows(start: '09:20', end: '10:30'),
      );

      expect(result.date, DateTime(2026, 6, 27));
      expect(result.message, '已安排到本周六');
    });

    test(
      'moves passed weekend morning template to next available weekend date',
      () {
        final result = resolveTemplateApplyDate(
          now: DateTime(2026, 6, 27, 20),
          selectedDate: DateTime(2026, 6, 27),
          dayType: 'weekend',
          rows: _rows(start: '09:20', end: '10:30'),
        );

        expect(result.date, DateTime(2026, 6, 28));
        expect(result.message, '已安排到明天');
      },
    );
  });
}

List<TaskTemplateRow> _rows({required String start, required String end}) {
  return [
    TaskTemplateRow(
      startTime: start,
      endTime: end,
      taskType: 'life',
      title: '生活提醒',
      rewardPoints: 1,
      requiresParentConfirmation: false,
    ),
  ];
}
