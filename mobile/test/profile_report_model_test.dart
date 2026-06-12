import 'package:flutter_test/flutter_test.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';

void main() {
  test('report section titles localize backend technical event keys', () {
    final report = ReportData.fromJson({
      'title': '今日报告',
      'summary': '今天有看护记录',
      'taskTotal': 0,
      'taskCompleted': 0,
      'pointsEarned': 0,
      'pendingItems': 0,
      'completionRate': 0,
      'skills': [],
      'highlights': [],
      'improvements': [],
      'observations': [
        {
          'title': 'monitor_started',
          'detail': '摄像头已开始观察任务',
          'tone': 'blue',
          'source': '事件记录',
        },
        {
          'title': 'unknown_internal_event',
          'detail': '内部事件',
          'tone': 'blue',
          'source': '事件记录',
        },
      ],
      'tasks': [],
      'nextActions': [],
    });

    expect(report.observations[0].title, '开始观察任务');
    expect(report.observations[1].title, '看护事件');
  });
}
