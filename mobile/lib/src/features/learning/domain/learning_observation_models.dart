class ParentObservationLesson {
  const ParentObservationLesson({
    required this.lessonId,
    required this.title,
    required this.unitTitle,
    required this.gradeCode,
    required this.subject,
    required this.criteria,
    required this.confirmationId,
  });

  final String lessonId;
  final String title;
  final String unitTitle;
  final String gradeCode;
  final String subject;
  final List<String> criteria;
  final String confirmationId;

  String get subjectLabel => switch (subject) {
    'chinese' => '语文',
    'math' => '数学',
    'english' => '英语',
    _ => '',
  };

  static List<ParentObservationLesson> fromPath(
    Object? value, {
    required String subject,
  }) {
    if (value is! Map ||
        value['ok'] != true ||
        value['schemaVersion'] != 'mira.learning.progressive-path.v1' ||
        value['curriculumVersion'] != 'mira.primary.progressive.v1' ||
        value['subject'] != subject ||
        value['currentGradeLessons'] is! List ||
        value['prerequisites'] is! List) {
      throw const FormatException('学习确认信息暂时不可用，请刷新后再试');
    }
    final lessons = <ParentObservationLesson>[];
    final seen = <String>{};
    for (final row in [
      ...value['prerequisites'] as List,
      ...value['currentGradeLessons'] as List,
    ]) {
      if (row is! Map || row['assessmentMode'] != 'observed') continue;
      final observation = row['observation'];
      if (observation is! Map || observation['canConfirm'] != true) continue;
      final id = row['lessonId'];
      final title = row['title'];
      final unit = row['unitTitle'];
      final grade = row['gradeCode'];
      final criteria = observation['criteria'];
      final confirmation = observation['confirmationId'];
      if (id is! String ||
          !RegExp(r'^(ZH|EN|M)[1-6][AB]\d{2}\.\d{2,}$').hasMatch(id) ||
          !seen.add(id) ||
          row['subject'] != subject ||
          row['canStart'] != true ||
          row['status'] == 'locked' ||
          title is! String ||
          title.trim().isEmpty ||
          unit is! String ||
          unit.trim().isEmpty ||
          grade is! String ||
          !RegExp(r'^primary_[1-6]$').hasMatch(grade) ||
          criteria is! List ||
          criteria.isEmpty ||
          criteria.any((item) => item is! String || item.trim().isEmpty) ||
          confirmation is! String ||
          !RegExp(r'^obs_[a-f0-9]{64}$').hasMatch(confirmation)) {
        throw const FormatException('学习确认内容已变化，请刷新后再试');
      }
      lessons.add(
        ParentObservationLesson(
          lessonId: id,
          title: title,
          unitTitle: unit,
          gradeCode: grade,
          subject: subject,
          criteria: List<String>.unmodifiable(criteria.cast<String>()),
          confirmationId: confirmation,
        ),
      );
    }
    return List.unmodifiable(lessons);
  }
}
