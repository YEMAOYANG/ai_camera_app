import 'package:flutter_test/flutter_test.dart';
import 'package:mira_guardian_app/src/features/tasks/domain/task_models.dart';

void main() {
  test('task runtime statuses use parent-facing labels', () {
    expect(GuardianTaskStatus.scheduled.label, '待开始');
    expect(GuardianTaskStatus.reminderSent.label, '即将开始');
    expect(GuardianTaskStatus.inProgress.label, '进行中');
    expect(GuardianTaskStatus.delayed.label, '需要提醒');
    expect(GuardianTaskStatus.awaitingParentConfirmation.label, '待确认');
    expect(GuardianTaskStatus.completed.label, '已完成');
    expect(GuardianTaskStatus.missed.label, '未完成');
  });

  test('task runtime status values parse from backend payloads', () {
    expect(
      GuardianTaskStatus.fromValue('in_progress'),
      GuardianTaskStatus.inProgress,
    );
    expect(GuardianTaskStatus.fromValue('delayed'), GuardianTaskStatus.delayed);
    expect(GuardianTaskStatus.fromValue('missed'), GuardianTaskStatus.missed);
  });
}
