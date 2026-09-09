class ChildGradeOption {
  const ChildGradeOption({
    required this.code,
    required this.stageCode,
    required this.stageLabel,
    required this.gradeLabel,
    required this.displayLabel,
    required this.contentMode,
  });

  final String code;
  final String stageCode;
  final String stageLabel;
  final String gradeLabel;
  final String displayLabel;
  final String contentMode;

  bool get isPrimary => stageCode == 'primary';

  bool get isFormalLearningSupported => code == 'primary_1';

  static const kindergarten = <ChildGradeOption>[
    ChildGradeOption(
      code: 'kindergarten_small',
      stageCode: 'kindergarten',
      stageLabel: '幼儿园',
      gradeLabel: '小班',
      displayLabel: '新小班',
      contentMode: 'kindergarten_growth',
    ),
    ChildGradeOption(
      code: 'kindergarten_middle',
      stageCode: 'kindergarten',
      stageLabel: '幼儿园',
      gradeLabel: '中班',
      displayLabel: '新中班',
      contentMode: 'kindergarten_growth',
    ),
    ChildGradeOption(
      code: 'kindergarten_big',
      stageCode: 'kindergarten',
      stageLabel: '幼儿园',
      gradeLabel: '大班',
      displayLabel: '新大班',
      contentMode: 'kindergarten_growth',
    ),
  ];

  static const primary = <ChildGradeOption>[
    ChildGradeOption(
      code: 'primary_1',
      stageCode: 'primary',
      stageLabel: '小学',
      gradeLabel: '一年级',
      displayLabel: '新一年级',
      contentMode: 'primary_learning',
    ),
    ChildGradeOption(
      code: 'primary_2',
      stageCode: 'primary',
      stageLabel: '小学',
      gradeLabel: '二年级',
      displayLabel: '新二年级',
      contentMode: 'primary_learning',
    ),
    ChildGradeOption(
      code: 'primary_3',
      stageCode: 'primary',
      stageLabel: '小学',
      gradeLabel: '三年级',
      displayLabel: '新三年级',
      contentMode: 'primary_learning',
    ),
    ChildGradeOption(
      code: 'primary_4',
      stageCode: 'primary',
      stageLabel: '小学',
      gradeLabel: '四年级',
      displayLabel: '新四年级',
      contentMode: 'primary_learning',
    ),
    ChildGradeOption(
      code: 'primary_5',
      stageCode: 'primary',
      stageLabel: '小学',
      gradeLabel: '五年级',
      displayLabel: '新五年级',
      contentMode: 'primary_learning',
    ),
    ChildGradeOption(
      code: 'primary_6',
      stageCode: 'primary',
      stageLabel: '小学',
      gradeLabel: '六年级',
      displayLabel: '新六年级',
      contentMode: 'primary_learning',
    ),
  ];

  static const all = <ChildGradeOption>[...kindergarten, ...primary];

  static ChildGradeOption? fromCode(String? value) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) return null;
    for (final option in all) {
      if (option.code == normalized) return option;
    }
    return null;
  }

  static ChildGradeOption? fromLegacy({String? educationStage, String? grade}) {
    final stage = educationStage?.trim() ?? '';
    final label = grade?.trim() ?? '';
    if (label.isEmpty) return null;
    for (final option in all) {
      if (option.gradeLabel != label) continue;
      if (stage.isEmpty || option.stageLabel == stage) return option;
    }
    return null;
  }
}

int gradeSchoolYearStartYear([DateTime? now]) {
  return (now ?? DateTime.now()).year;
}
