import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/tasks/domain/task_models.dart';

void main() {
  test('task runtime statuses use parent-facing labels', () {
    expect(GuardianTaskStatus.scheduled.label, '待开始');
    expect(GuardianTaskStatus.reminderSent.label, '即将开始');
    expect(GuardianTaskStatus.inProgress.label, '进行中');
    expect(GuardianTaskStatus.delayed.label, '需要提醒');
    expect(GuardianTaskStatus.awaitingParentConfirmation.label, '待确认');
    expect(GuardianTaskStatus.completed.label, '已完成');
    expect(GuardianTaskStatus.rejected.label, '已驳回');
    expect(GuardianTaskStatus.missed.label, '未完成');
    expect(GuardianTaskStatus.rejected.isDone, isTrue);
    expect(GuardianTaskStatus.rejected.needsCare, isFalse);
  });

  test('task runtime status values parse from backend payloads', () {
    expect(
      GuardianTaskStatus.fromValue('in_progress'),
      GuardianTaskStatus.inProgress,
    );
    expect(GuardianTaskStatus.fromValue('delayed'), GuardianTaskStatus.delayed);
    expect(
      GuardianTaskStatus.fromValue('rejected'),
      GuardianTaskStatus.rejected,
    );
    expect(GuardianTaskStatus.fromValue('missed'), GuardianTaskStatus.missed);
  });

  test('rejected task copy does not mention child supplement flow', () {
    final task = GuardianTask.fromJson({
      'id': 'task_rejected',
      'taskId': 'task_rejected',
      'familyId': 'family_1',
      'childId': 'child_1',
      'title': '读单词',
      'type': 'learning',
      'taskType': 'learning',
      'scheduleType': 'one_time',
      'status': 'rejected',
      'scheduledDate': '2026-06-04',
      'scheduledStart': '11:00',
      'scheduledEnd': '11:30',
      'rewardPoints': 3,
      'requiresParentConfirmation': true,
      'rejectionReason': '证据不足，等待孩子补充完成。',
      'createdAt': 0,
      'updatedAt': 0,
    });

    expect(task.status.label, '已驳回');
    expect(task.parentDecisionLabel, '未发放积分');
    expect(task.nextStep, '本次任务未通过确认，未发放积分。');
    expect(task.aiAdvice, '原因：证据不足，未通过家长确认。');
    expect(task.nextStep, isNot(contains('等待孩子')));
    expect(task.aiAdvice, isNot(contains('补充完成')));
  });

  test('rejected task events use final V1 labels', () {
    final rejected = GuardianTaskEvent.fromJson({
      'id': 'evt_rejected',
      'taskId': 'task_1',
      'eventType': 'parent_rejected',
      'message': '家长已驳回完成确认',
      'createdAt': 0,
    });
    final skipped = GuardianTaskEvent.fromJson({
      'id': 'evt_skipped',
      'taskId': 'task_1',
      'eventType': 'points_award_skipped',
      'message': '本次任务未发放积分',
      'createdAt': 0,
    });

    expect(rejected.title, '家长驳回确认');
    expect(skipped.title, '未发放积分');
    expect(skipped.displayMessage, '本次任务未发放积分');
  });
}
