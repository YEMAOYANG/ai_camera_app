class SchoolTextbook {
  const SchoolTextbook({
    required this.editionId,
    required this.revisionId,
    required this.title,
    required this.publisher,
    required this.editionLabel,
    required this.subject,
    required this.volume,
    required this.schoolSystem,
    required this.partial,
    this.indexOnly = false,
    required this.lessonCount,
    required this.selected,
    required this.selectionRevision,
    this.learningStatus,
  });
  final String editionId,
      revisionId,
      title,
      publisher,
      editionLabel,
      subject,
      volume,
      schoolSystem;
  final bool partial, selected, indexOnly;
  final int lessonCount, selectionRevision;
  final TextbookLearningStatus? learningStatus;
  factory SchoolTextbook.fromJson(Map<String, dynamic> json) => SchoolTextbook(
    editionId: json['editionId'] as String,
    revisionId: json['revisionId'] as String,
    title: json['title'] as String,
    publisher: json['publisher'] as String,
    editionLabel: json['editionLabel'] as String,
    subject: json['subject'] as String,
    volume: json['volume'] as String,
    schoolSystem: json['schoolSystem'] as String,
    partial: (json['coverage'] as Map)['status'] == 'partial',
    indexOnly: (json['coverage'] as Map)['status'] == 'index_only',
    lessonCount: json['lessonCount'] as int,
    selected: json['selected'] as bool,
    selectionRevision: json['selectionRevision'] as int,
    learningStatus: json['learningStatus'] is Map
        ? TextbookLearningStatus.fromJson(
            Map<String, dynamic>.from(json['learningStatus'] as Map),
          )
        : null,
  );
  String get subjectLabel => switch (subject) {
    'chinese' => '语文',
    'math' => '数学',
    'english' => '英语',
    'science' => '科学',
    _ => subject,
  };
  String get volumeLabel => switch (volume) {
    'upper' => '上册',
    'lower' => '下册',
    _ => '全册',
  };
  String get key => '$editionId:$revisionId';
  String get versionLabel => editionLabel.contains(' · ')
      ? editionLabel.split(' · ').first
      : publisher;
  String get versionDetail => editionLabel.contains(' · ')
      ? editionLabel.split(' · ').skip(1).join(' · ')
      : editionLabel;
  String get learningSummary {
    if (learningStatus case final status?
        when status.available > 0 || status.status == 'locked') {
      return status.label;
    }
    if (indexOnly) return '目录待同步';
    if (partial) return '已同步部分目录 · 课件待生成';
    return '目录 $lessonCount 课 · 课件待生成';
  }
}

class SchoolTextbookCatalog {
  const SchoolTextbookCatalog({
    required this.year,
    required this.semester,
    required this.books,
    this.contextRevision = 0,
    this.gradeRevision = 1,
    this.termSource = 'calendar',
    this.subjects = const [],
    this.journeys = const [],
  });
  final int year;
  final String semester;
  final List<SchoolTextbook> books;
  final int contextRevision, gradeRevision;
  final String termSource;
  final List<TextbookSubject> subjects;
  final List<TextbookJourney> journeys;
  String get termLabel =>
      '$year—${year + 1} 学年 · ${semester == 'upper' ? '上学期' : '下学期'}';
  String? get manualSemester => termSource == 'parent' ? semester : null;
  String statusFor(String subject) {
    for (final item in subjects) {
      if (item.subject == subject) {
        return item.status;
      }
    }
    if (books.any((b) => b.subject == subject && b.selected)) {
      return 'confirmed';
    }
    return books.any(
          (b) =>
              b.subject == subject &&
              (b.volume == semester || b.volume == 'full'),
        )
        ? 'selection_required'
        : 'unavailable';
  }

  factory SchoolTextbookCatalog.fromJson(dynamic value) {
    if (value is! Map ||
        value['ok'] != true ||
        value['schemaVersion'] != 'mira.learning.textbooks.v1') {
      throw const FormatException('教材资料暂时无法读取');
    }
    return SchoolTextbookCatalog(
      year: value['schoolYearStartYear'] as int,
      contextRevision: value['contextRevision'] as int? ?? 0,
      gradeRevision: value['gradeRevision'] as int? ?? 1,
      termSource: value['termSource'] as String? ?? 'calendar',
      subjects: (value['subjects'] as List? ?? [])
          .map(
            (s) =>
                TextbookSubject(s['subject'] as String, s['status'] as String),
          )
          .toList(),
      journeys: (value['learningJourneys'] as List? ?? [])
          .map(
            (item) => TextbookJourney.fromJson(
              Map<String, dynamic>.from(item as Map),
            ),
          )
          .toList(),
      semester: value['semester'] as String,
      books: (value['books'] as List)
          .map(
            (item) =>
                SchoolTextbook.fromJson(Map<String, dynamic>.from(item as Map)),
          )
          .toList(),
    );
  }
}

class TextbookSubject {
  const TextbookSubject(this.subject, this.status);
  final String subject, status;
}

class TextbookLearningStatus {
  const TextbookLearningStatus({
    required this.status,
    this.available = 0,
    this.completed = 0,
  });
  final String status;
  final int available, completed;
  factory TextbookLearningStatus.fromJson(Map<String, dynamic> json) =>
      TextbookLearningStatus(
        status: json['status'] as String,
        available: json['availableLessonCount'] as int,
        completed: json['completedLessonCount'] as int,
      );
  String get label => available > 0
      ? '已开放 $available 课 · 已学 $completed 课'
      : status == 'locked'
      ? '完成前序课程后开放'
      : '课件待生成';
}

class TextbookJourney {
  const TextbookJourney({
    required this.title,
    required this.status,
    required this.parentNeeded,
    required this.nextStep,
    required this.before,
    required this.verified,
    required this.remaining,
    required this.diagnoses,
    this.reviewDueAt,
  });
  final String title, status, nextStep;
  final bool parentNeeded;
  final int before, verified;
  final List<String> remaining, diagnoses;
  final DateTime? reviewDueAt;
  String get label => parentNeeded
      ? '需要您留意'
      : status == 'retained'
      ? '间隔复习已通过'
      : verified == 6
      ? '本次已独立完成'
      : '孩子正在自己练习';
  factory TextbookJourney.fromJson(Map<String, dynamic> json) =>
      TextbookJourney(
        title: json['title'] as String,
        status: json['status'] as String,
        parentNeeded: json['parentNeeded'] as bool,
        nextStep: json['nextStep'] as String,
        before: json['independentBefore'] as int,
        verified: json['verifiedCount'] as int,
        remaining: List<String>.from(json['remainingSkills'] as List),
        diagnoses: List<String>.from(json['diagnoses'] as List),
        reviewDueAt: json['reviewDueAt'] == null
            ? null
            : DateTime.fromMillisecondsSinceEpoch(
                json['reviewDueAt'] as int,
              ).toLocal(),
      );
}
