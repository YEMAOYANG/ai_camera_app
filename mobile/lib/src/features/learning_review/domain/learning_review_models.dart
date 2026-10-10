typedef Json = Map<String, dynamic>;
Json jsonMap(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : {};
List<Json> jsonList(Object? value) =>
    value is List ? value.map(jsonMap).toList() : [];
int number(Object? value) => value is num ? value.toInt() : 0;
String textValue(Object? value) => value?.toString() ?? '';

class ReviewRun {
  const ReviewRun(this.data);
  final Json data;
  String get id => textValue(data['id']);
  String get title => textValue(data['title']);
  String get status => textValue(data['status']);
  int get appointmentRevision => number(data['appointmentRevision']);
  int get estimatedMinutes => number(data['estimatedMinutes']);
  int get questionCount => number(data['totalQuestions']);
  int get answeredCount => number(data['currentIndex']);
  DateTime? get scheduledAt => data['scheduledAt'] is num
      ? DateTime.fromMillisecondsSinceEpoch(number(data['scheduledAt']))
      : null;
  Json get coverage => jsonMap(data['coverage']);
  bool get canSchedule => !{
    'completed',
    'skipped',
    'superseded',
    'content_gap',
    'rest',
  }.contains(status);
  String get statusLabel =>
      const {
        'scheduled': '已预约',
        'in_progress': '进行中',
        'paused': '已暂停',
        'needs_schedule': '待安排',
        'completed': '已完成',
        'skipped': '本周已跳过',
        'superseded': '已更新',
        'content_gap': '复习内容准备中',
        'rest': '本周无需复习',
      }[status] ??
      '正在同步';
}

class ReviewDetail {
  ReviewDetail(Json json)
    : run = ReviewRun(jsonMap(json['review'])),
      report = jsonMap(json['report']);
  final ReviewRun run;
  final Json report;
}

class ReviewPreferences {
  const ReviewPreferences(this.data);
  final Json data;
  int get weekday => number(data['weekday']);
  String get time => textValue(data['time']);
  bool get enabled => data['enabled'] == true;
  bool get reminderEnabled => data['reminderEnabled'] == true;
  String? get pausedUntil => data['pausedUntil'] as String?;
}

class LearningWeakness {
  const LearningWeakness(this.data);
  final Json data;
  String get label => textValue(data['label']);
  String get status => textValue(data['status']);
  String get statusLabel =>
      const {
        'needs_review': '需要复习',
        'consolidated': '已有进步',
        'observing': '继续观察',
      }[status] ??
      '等待证据';
  Json get example => jsonMap(data['example']);
}

String learningAnswerLabel(Object? value, Object? rawOptions) {
  final options = jsonList(rawOptions);
  if (value is List) {
    return value.map((v) => learningAnswerLabel(v, rawOptions)).join('、');
  }
  final response = value is Map
      ? value['response'] ?? value['value'] ?? value['answer']
      : value;
  final match = options
      .where((e) => e['value'] == response || e['id'] == response)
      .firstOrNull;
  return match == null
      ? textValue(response)
      : textValue(match['label'] ?? response);
}
