class ReportLearningSummary {
  const ReportLearningSummary({
    this.lessonCount = 0,
    this.needsSupportCount = 0,
    this.reviewCount = 0,
    this.lessons = const [],
    this.coachingSummary = const {},
  });

  final int lessonCount;
  final int needsSupportCount;
  final int reviewCount;
  final List<ReportLearningLesson> lessons;
  final Map<String, dynamic> coachingSummary;

  factory ReportLearningSummary.fromJson(Object? value) {
    final json = _map(value);
    return ReportLearningSummary(
      lessonCount: _number(json['lessonCount']),
      needsSupportCount: _number(json['needsSupportCount']),
      reviewCount: _number(json['reviewCount']),
      coachingSummary: _map(json['coachingSummary']),
      lessons: (json['lessons'] is List ? json['lessons'] as List : const [])
          .whereType<Map>()
          .map((item) => ReportLearningLesson.fromJson(_map(item)))
          .toList(),
    );
  }
}

class ReportLearningLesson {
  ReportLearningLesson.fromJson(Map<String, dynamic> json)
    : title = _text(json['courseTitle']),
      childName = _text(json['childName']),
      statusLabel = _text(json['statusLabel']),
      evidenceLabel = _text(json['evidenceLabel']),
      recordDate = _text(json['recordDate']),
      needsSupport = json['needsSupport'] == true,
      pictureSupported = json['kind'] == 'textbook',
      baseline = json['baseline'] is Map ? _map(json['baseline']) : null,
      verification = json['verification'] is Map
          ? _map(json['verification'])
          : null,
      remaining = _strings(json['remainingSkills']),
      diagnoses = _strings(json['diagnoses']),
      nextStep = _text(json['nextStep']),
      sessionId = _text(json['learningSessionId']),
      parentSupport = _map(json['parentSupport']),
      coaching = _map(json['coaching']),
      reviewDueAt = json['reviewDueAt'] is num
          ? DateTime.fromMillisecondsSinceEpoch(
              (json['reviewDueAt'] as num).toInt(),
              isUtc: true,
            ).add(const Duration(hours: 8))
          : null;

  final String title,
      childName,
      statusLabel,
      evidenceLabel,
      recordDate,
      nextStep,
      sessionId;
  final Map<String, dynamic> parentSupport, coaching;
  final bool needsSupport, pictureSupported;
  final Map<String, dynamic>? baseline, verification;
  final List<String> remaining, diagnoses;
  final DateTime? reviewDueAt;

  String? get baselineLabel =>
      baseline != null && _number(baseline!['total']) > 0
      ? '${pictureSupported ? '前测' : '练习'}独立答对 ${_number(baseline!['correct'])}/${_number(baseline!['total'])}'
      : null;
  String? get verificationLabel => verification == null
      ? null
      : '新情境独立通过 ${_number(verification!['correct'])}/${_number(verification!['total'])}';
  String? get helpLabel {
    if (baseline == null || _number(baseline!['total']) == 0) return null;
    return '${pictureSupported ? '前测' : '练习'}提示 ${_number(baseline!['hints'])} 题'
        '${baseline!['adultHelp'] is num ? ' · 家长帮助 ${_number(baseline!['adultHelp'])} 题' : ''}';
  }
}

Map<String, dynamic> _map(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : const {};
int _number(Object? value) => value is num ? value.toInt() : 0;
String _text(Object? value) => value is String ? value : '';
List<String> _strings(Object? value) =>
    value is List ? value.whereType<String>().toList() : const [];
