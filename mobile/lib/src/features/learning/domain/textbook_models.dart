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
  );
  String get subjectLabel => switch (subject) {
    'chinese' => '语文',
    'math' => '数学',
    'english' => '英语',
    _ => subject,
  };
  String get volumeLabel => switch (volume) {
    'upper' => '上册',
    'lower' => '下册',
    _ => '全册',
  };
  String get key => '$editionId:$revisionId';
}

class SchoolTextbookCatalog {
  const SchoolTextbookCatalog({
    required this.year,
    required this.semester,
    required this.books,
  });
  final int year;
  final String semester;
  final List<SchoolTextbook> books;
  factory SchoolTextbookCatalog.fromJson(dynamic value) {
    if (value is! Map ||
        value['ok'] != true ||
        value['schemaVersion'] != 'mira.learning.textbooks.v1') {
      throw const FormatException('教材资料暂时无法读取');
    }
    return SchoolTextbookCatalog(
      year: value['schoolYearStartYear'] as int,
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
