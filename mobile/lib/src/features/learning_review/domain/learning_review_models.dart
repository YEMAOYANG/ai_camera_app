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

class ReviewEvidenceItem {
  const ReviewEvidenceItem(this.data);
  final Json data;

  String get goal => textValue(data['knowledgeLabel']).isNotEmpty
      ? textValue(data['knowledgeLabel'])
      : '本题学习目标';
  String get target => textValue(data['target']);
  String get assessmentMode => textValue(data['assessmentMode']);
  String get assessmentLabel =>
      const {
        'listening_picture': '听音选图',
        'character_picture': '看字选图',
        'pinyin_picture': '拼音配图',
        'picture_comprehension': '图境理解',
      }[assessmentMode] ??
      '';
  Json get sourceIdentity => jsonMap(data['sourceIdentity']);
  String get sourceTitle => textValue(sourceIdentity['title']).isNotEmpty
      ? textValue(sourceIdentity['title'])
      : textValue(data['courseTitle']);
  Json get claim => jsonMap(data['evidenceClaim']);
  List<String> claimTexts(String key) => claim[key] is List
      ? (claim[key] as List)
            .whereType<String>()
            .where((s) => s.isNotEmpty)
            .toList()
      : [];
  bool get repeated => data['evidenceMode'] == 'repeated_practice';
  bool get adultHelpUnknown =>
      data['adultHelpKnown'] == false ||
      data['independenceStatus'] == 'adult_help_unknown';
  String get resultLabel => data['correct'] == true
      ? '本题答对'
      : data['correct'] == false
      ? '本题未答对'
      : '结果待核实';
  String get supportLabel {
    final labels = <String>[
      if (repeated) '原题复练',
      if (data['hintUsed'] == true) '已使用提示',
      if (data['explanationSeen'] == true) '已看讲解',
      if (data['adultHelp'] == true) '家长协助',
      if (adultHelpUnknown)
        data['systemUnaided'] == true ? '未用系统提示，家长帮助未知' : '家长帮助未知',
    ];
    if (labels.isNotEmpty) return labels.join(' · ');
    if (data['independenceStatus'] == 'assisted_or_repeated') return '已获助或复现';
    return data['independent'] == true ? '首次独立作答' : '独立性未确认';
  }
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
