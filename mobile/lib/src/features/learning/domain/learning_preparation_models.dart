enum LearningPreparationStage {
  queued,
  planning,
  generatingContent,
  buildingClassrooms,
  generatingSpeech,
  validating,
  publishing,
  retryWait,
  completed,
}

class LearningPreparationFormatException implements FormatException {
  const LearningPreparationFormatException(this.message);

  @override
  final String message;

  @override
  int? get offset => null;

  @override
  Object? get source => null;

  @override
  String toString() => 'LearningPreparationFormatException: $message';
}

class LearningPreparationAvailability {
  const LearningPreparationAvailability._({
    required this.status,
    required this.gradeCode,
    required this.message,
  });

  static const _unavailableGradeCodes = {
    'primary_2',
    'primary_3',
    'primary_4',
    'primary_5',
    'primary_6',
  };

  final String status;
  final String gradeCode;
  final String message;

  factory LearningPreparationAvailability._fromJson(Object? value) {
    final json = _requireMap(value, 'learningPreparationAvailability');
    _requireExactKeys(json, const {
      'status',
      'gradeCode',
      'message',
    }, 'learningPreparationAvailability');
    final status = _requireString(
      json['status'],
      'learningPreparationAvailability.status',
    );
    final gradeCode = _requireString(
      json['gradeCode'],
      'learningPreparationAvailability.gradeCode',
    );
    final message = _requireString(
      json['message'],
      'learningPreparationAvailability.message',
    );
    if (status != 'unavailable' ||
        !_unavailableGradeCodes.contains(gradeCode) ||
        message.trim().isEmpty) {
      throw const LearningPreparationFormatException(
        'learningPreparationAvailability has invalid values',
      );
    }
    return LearningPreparationAvailability._(
      status: status,
      gradeCode: gradeCode,
      message: message,
    );
  }
}

class LearningPreparationCurrentState {
  const LearningPreparationCurrentState._({
    required this.preparation,
    required this.learningPreparationAvailability,
  });

  static const _normalKeys = {'ok', 'preparation'};
  static const _unavailableKeys = {
    'ok',
    'preparation',
    'learningPreparationAvailability',
  };

  final LearningPreparation? preparation;
  final LearningPreparationAvailability? learningPreparationAvailability;

  factory LearningPreparationCurrentState.fromJson(Object? value) {
    final root = _requireMap(value, 'preparation response');
    final keys = root.keys.toSet();
    if (_setEquals(keys, _normalKeys)) {
      if (root['ok'] != true) {
        throw const LearningPreparationFormatException(
          'preparation response has an invalid envelope',
        );
      }
      final rawPreparation = root['preparation'];
      if (rawPreparation == null) {
        return LearningPreparationCurrentState.fromPreparation(null);
      }
      final preparation = LearningPreparation.fromJson(
        _requireMap(rawPreparation, 'preparation'),
      );
      return LearningPreparationCurrentState.fromPreparation(preparation);
    }

    if (!_setEquals(keys, _unavailableKeys) ||
        root['ok'] != true ||
        root['preparation'] != null) {
      throw const LearningPreparationFormatException(
        'preparation response has an invalid envelope',
      );
    }
    return LearningPreparationCurrentState._(
      preparation: null,
      learningPreparationAvailability:
          LearningPreparationAvailability._fromJson(
            root['learningPreparationAvailability'],
          ),
    );
  }

  factory LearningPreparationCurrentState.fromPreparation(
    LearningPreparation? preparation,
  ) {
    if (preparation != null &&
        (!RegExp(r'^primary_[1-6]$').hasMatch(preparation.gradeCode) ||
         (preparation.schemaVersion == LearningPreparation.schema && preparation.gradeCode != 'primary_1'))) {
      throw const LearningPreparationFormatException(
        'normal preparation response must belong to a registered primary grade',
      );
    }
    return LearningPreparationCurrentState._(
      preparation: preparation,
      learningPreparationAvailability: null,
    );
  }
}

class LearningPreparationSubject {
  const LearningPreparationSubject({
    required this.code,
    required this.label,
    required this.readyCourseCount,
    required this.failedCourseCount,
    required this.totalCourseCount,
    required this.contentCandidateCount,
    required this.contentFailedCount,
  });

  final String code;
  final String label;
  final int readyCourseCount;
  final int failedCourseCount;
  final int totalCourseCount;
  final int? contentCandidateCount;
  final int? contentFailedCount;

  factory LearningPreparationSubject.fromJson(
    Object? value, {
    required bool includesContentProgress,
  }) {
    final json = _requireMap(value, 'subject');
    _requireExactKeys(
      json,
      includesContentProgress
          ? const {
              'code',
              'label',
              'readyCourseCount',
              'failedCourseCount',
              'totalCourseCount',
              'contentCandidateCount',
              'contentFailedCount',
            }
          : const {
              'code',
              'label',
              'readyCourseCount',
              'failedCourseCount',
              'totalCourseCount',
            },
      'subject',
    );
    final ready = _requireNonnegativeInt(
      json['readyCourseCount'],
      'subject.readyCourseCount',
    );
    final failed = _requireNonnegativeInt(
      json['failedCourseCount'],
      'subject.failedCourseCount',
    );
    final total = _requireNonnegativeInt(
      json['totalCourseCount'],
      'subject.totalCourseCount',
    );
    _validateCounts(
      ready: ready,
      failed: failed,
      total: total,
      field: 'subject',
    );
    final contentCandidate = includesContentProgress
        ? _requireNonnegativeInt(
            json['contentCandidateCount'],
            'subject.contentCandidateCount',
          )
        : null;
    final contentFailed = includesContentProgress
        ? _requireNonnegativeInt(
            json['contentFailedCount'],
            'subject.contentFailedCount',
          )
        : null;
    if (contentCandidate != null &&
        contentFailed != null &&
        contentCandidate + contentFailed > total) {
      throw const LearningPreparationFormatException(
        'subject content counts are inconsistent',
      );
    }
    return LearningPreparationSubject(
      code: _requireString(json['code'], 'subject.code'),
      label: _requireString(json['label'], 'subject.label'),
      readyCourseCount: ready,
      failedCourseCount: failed,
      totalCourseCount: total,
      contentCandidateCount: contentCandidate,
      contentFailedCount: contentFailed,
    );
  }
}

class LearningPreparationContentCanary {
  const LearningPreparationContentCanary({
    required this.targetCount,
    required this.candidateCount,
    required this.failedCount,
    required this.passed,
  });

  final int targetCount;
  final int candidateCount;
  final int failedCount;
  final bool passed;

  factory LearningPreparationContentCanary.fromJson(Object? value) {
    final json = _requireMap(value, 'contentProgress.canary');
    _requireExactKeys(json, const {
      'targetCount',
      'candidateCount',
      'failedCount',
      'passed',
    }, 'contentProgress.canary');
    final target = _requireNonnegativeInt(
      json['targetCount'],
      'contentProgress.canary.targetCount',
    );
    final candidate = _requireNonnegativeInt(
      json['candidateCount'],
      'contentProgress.canary.candidateCount',
    );
    final failed = _requireNonnegativeInt(
      json['failedCount'],
      'contentProgress.canary.failedCount',
    );
    final passed = _requireBool(
      json['passed'],
      'contentProgress.canary.passed',
    );
    if (target != 3 || candidate + failed > target) {
      throw const LearningPreparationFormatException(
        'contentProgress.canary counts are inconsistent',
      );
    }
    if (passed != (candidate == target && failed == 0)) {
      throw const LearningPreparationFormatException(
        'contentProgress.canary passed is inconsistent',
      );
    }
    return LearningPreparationContentCanary(
      targetCount: target,
      candidateCount: candidate,
      failedCount: failed,
      passed: passed,
    );
  }
}

class LearningPreparationContentProgress {
  const LearningPreparationContentProgress({
    required this.candidateCount,
    required this.failedCount,
    required this.targetCount,
    required this.canary,
  });

  final int candidateCount;
  final int failedCount;
  final int targetCount;
  final LearningPreparationContentCanary canary;

  factory LearningPreparationContentProgress.fromJson(Object? value) {
    final json = _requireMap(value, 'contentProgress');
    _requireExactKeys(json, const {
      'candidateCount',
      'failedCount',
      'targetCount',
      'canary',
    }, 'contentProgress');
    final candidate = _requireNonnegativeInt(
      json['candidateCount'],
      'contentProgress.candidateCount',
    );
    final failed = _requireNonnegativeInt(
      json['failedCount'],
      'contentProgress.failedCount',
    );
    final target = _requireNonnegativeInt(
      json['targetCount'],
      'contentProgress.targetCount',
    );
    if (!{27, 30}.contains(target) || candidate + failed > target) {
      throw const LearningPreparationFormatException(
        'contentProgress counts are inconsistent',
      );
    }
    final canary = LearningPreparationContentCanary.fromJson(json['canary']);
    if (canary.candidateCount > candidate || canary.failedCount > failed) {
      throw const LearningPreparationFormatException(
        'contentProgress canary exceeds global counts',
      );
    }
    return LearningPreparationContentProgress(
      candidateCount: candidate,
      failedCount: failed,
      targetCount: target,
      canary: canary,
    );
  }
}

class LearningPreparationSafeError {
  const LearningPreparationSafeError({
    required this.code,
    required this.message,
  });

  final String code;
  final String message;

  factory LearningPreparationSafeError.fromJson(Object? value) {
    final json = _requireMap(value, 'error');
    _requireExactKeys(json, const {'code', 'message'}, 'error');
    return LearningPreparationSafeError(
      code: _requireString(json['code'], 'error.code'),
      message: _requireString(json['message'], 'error.message'),
    );
  }
}

class CourseSupplySummary {
  const CourseSupplySummary({
    required this.paused,
    required this.message,
    this.delayed = false,
  });
  final bool paused;
  final bool delayed;
  final String message;

  factory CourseSupplySummary.fromJson(Object? value) {
    final json = _requireMap(value, 'courseSupply');
    if (json['schemaVersion'] != 'learning.course-supply-summary.v1' ||
        json['paused'] is! bool ||
        json['message'] is! String) {
      throw const LearningPreparationFormatException('invalid courseSupply');
    }
    return CourseSupplySummary(
      paused: json['paused'] as bool,
      delayed: json['delayed'] == true,
      message: json['message'] as String,
    );
  }
}

class LearningPreparation {
  const LearningPreparation._({
    required this.schemaVersion,
    required this.id,
    required this.childId,
    required this.gradeCode,
    required this.gradeLabel,
    required this.subjects,
    required this.status,
    required this.stage,
    required this.supportedStage,
    required this.progressPercent,
    required this.totalCourseCount,
    required this.readyCourseCount,
    required this.failedCourseCount,
    required this.attempt,
    required this.canRetry,
    required this.retryAfterMs,
    required this.message,
    required this.lastProgressAt,
    required this.updatedAt,
    required this.completedAt,
    required this.error,
    required this.contentProgress,
    this.courseSupply,
  });

  static const schema = 'mira.learning.preparation.v1';
  static const schemaV2 = 'mira.learning.preparation.v2';
  static const _supportedSubjectCodes = {'chinese', 'math', 'english'};

  final String schemaVersion;
  final String id;
  final String childId;
  final String gradeCode;
  final String gradeLabel;
  final List<LearningPreparationSubject> subjects;
  final String status;
  final LearningPreparationStage stage;
  final bool supportedStage;
  final int progressPercent;
  final int totalCourseCount;
  final int readyCourseCount;
  final int failedCourseCount;
  final int attempt;
  final bool canRetry;
  final int? retryAfterMs;
  final String message;
  final int? lastProgressAt;
  final int updatedAt;
  final int? completedAt;
  final LearningPreparationSafeError? error;
  final LearningPreparationContentProgress? contentProgress;
  final CourseSupplySummary? courseSupply;

  bool get isReady {
    if ((schemaVersion != schema && schemaVersion != schemaV2) ||
        status != 'ready' ||
        !supportedStage ||
        stage != LearningPreparationStage.completed ||
        progressPercent != 100 ||
        totalCourseCount <= 0 ||
        readyCourseCount != totalCourseCount ||
        failedCourseCount != 0 ||
        subjects.length != _supportedSubjectCodes.length) {
      return false;
    }

    final codes = subjects.map((subject) => subject.code).toSet();
    if (codes.length != subjects.length ||
        !_setEquals(codes, _supportedSubjectCodes) ||
        subjects.any(
          (subject) =>
              subject.totalCourseCount <= 0 ||
              subject.readyCourseCount != subject.totalCourseCount ||
              subject.failedCourseCount != 0,
        )) {
      return false;
    }

    final v1Ready =
        subjects.fold<int>(
              0,
              (sum, subject) => sum + subject.totalCourseCount,
            ) ==
            totalCourseCount &&
        subjects.fold<int>(
              0,
              (sum, subject) => sum + subject.readyCourseCount,
            ) ==
            readyCourseCount &&
        subjects.fold<int>(
              0,
              (sum, subject) => sum + subject.failedCourseCount,
            ) ==
            failedCourseCount;
    if (!v1Ready) return false;
    if (schemaVersion == schema) return contentProgress == null;

    final content = contentProgress;
    return content != null &&
        content.targetCount == totalCourseCount &&
        content.candidateCount == content.targetCount &&
        content.failedCount == 0 &&
        content.canary.passed;
  }

  bool get isFailed =>
      status == 'failed' &&
      supportedStage &&
      stage == LearningPreparationStage.completed;

  bool get shouldPoll =>
      supportedStage &&
      stage != LearningPreparationStage.completed &&
      (status == 'queued' || status == 'running');

  Duration get retryAfter {
    final milliseconds = (retryAfterMs ?? 30000).clamp(2000, 30000);
    return Duration(milliseconds: milliseconds);
  }

  factory LearningPreparation.fromJson(Map<String, dynamic> json) {
    final schemaVersion = _requireString(
      json['schemaVersion'],
      'schemaVersion',
    );
    final includesContentProgress = schemaVersion == schemaV2;
    if (schemaVersion != schema && !includesContentProgress) {
      throw const LearningPreparationFormatException(
        'unsupported preparation schema',
      );
    }
    _requireExactKeys(
      json,
      includesContentProgress
          ? {
              if (json.containsKey('courseSupply')) 'courseSupply',
              'schemaVersion',
              'id',
              'childId',
              'gradeCode',
              'gradeLabel',
              'subjects',
              'status',
              'stage',
              'progressPercent',
              'totalCourseCount',
              'readyCourseCount',
              'failedCourseCount',
              'attempt',
              'canRetry',
              'retryAfterMs',
              'message',
              'lastProgressAt',
              'updatedAt',
              'completedAt',
              'error',
              'contentProgress',
            }
          : {
              if (json.containsKey('courseSupply')) 'courseSupply',
              'schemaVersion',
              'id',
              'childId',
              'gradeCode',
              'gradeLabel',
              'subjects',
              'status',
              'stage',
              'progressPercent',
              'totalCourseCount',
              'readyCourseCount',
              'failedCourseCount',
              'attempt',
              'canRetry',
              'retryAfterMs',
              'message',
              'lastProgressAt',
              'updatedAt',
              'completedAt',
              'error',
            },
      'preparation',
    );
    final status = _requireString(json['status'], 'status');
    final stageValue = _requireString(json['stage'], 'stage');
    final parsedStage = _parseStage(stageValue);
    final total = _requireNonnegativeInt(
      json['totalCourseCount'],
      'totalCourseCount',
    );
    final ready = _requireNonnegativeInt(
      json['readyCourseCount'],
      'readyCourseCount',
    );
    final failed = _requireNonnegativeInt(
      json['failedCourseCount'],
      'failedCourseCount',
    );
    _validateCounts(
      ready: ready,
      failed: failed,
      total: total,
      field: 'preparation',
    );
    final progress = _requireInt(json['progressPercent'], 'progressPercent');
    if (progress < 0 || progress > 100) {
      throw const LearningPreparationFormatException(
        'progressPercent must be between 0 and 100',
      );
    }
    final canRetry = _requireBool(json['canRetry'], 'canRetry');
    if (canRetry &&
        (status != 'failed' ||
            !parsedStage.supported ||
            parsedStage.value != LearningPreparationStage.completed)) {
      throw const LearningPreparationFormatException(
        'canRetry requires failed completed preparation',
      );
    }

    final rawSubjects = json['subjects'];
    if (rawSubjects is! List) {
      throw const LearningPreparationFormatException('subjects must be a list');
    }
    final subjects = List<LearningPreparationSubject>.unmodifiable(
      rawSubjects.map(
        (subject) => LearningPreparationSubject.fromJson(
          subject,
          includesContentProgress: includesContentProgress,
        ),
      ),
    );
    final contentProgress = includesContentProgress
        ? LearningPreparationContentProgress.fromJson(json['contentProgress'])
        : null;
    if (contentProgress != null) {
      final expectedTotal = json['gradeCode'] == 'primary_1' ? 30 : 27;
      if (total != expectedTotal || contentProgress.targetCount != total) {
        throw const LearningPreparationFormatException(
          'contentProgress target does not match preparation total',
        );
      }
      final subjectCandidateCount = subjects.fold<int>(
        0,
        (sum, subject) => sum + subject.contentCandidateCount!,
      );
      final subjectFailedCount = subjects.fold<int>(
        0,
        (sum, subject) => sum + subject.contentFailedCount!,
      );
      final subjectTotalCount = subjects.fold<int>(
        0,
        (sum, subject) => sum + subject.totalCourseCount,
      );
      final subjectReadyCount = subjects.fold<int>(
        0,
        (sum, subject) => sum + subject.readyCourseCount,
      );
      final subjectFormalFailedCount = subjects.fold<int>(
        0,
        (sum, subject) => sum + subject.failedCourseCount,
      );
      if (subjectTotalCount != total ||
          subjectReadyCount != ready ||
          subjectFormalFailedCount != failed ||
          subjectCandidateCount != contentProgress.candidateCount ||
          subjectFailedCount != contentProgress.failedCount) {
        throw const LearningPreparationFormatException(
          'subject counts do not match preparation totals',
        );
      }
    }
    final rawError = json['error'];

    return LearningPreparation._(
      schemaVersion: schemaVersion,
      id: _requireNonemptyString(json['id'], 'id'),
      childId: _requireNonemptyString(json['childId'], 'childId'),
      gradeCode: _requireNonemptyString(json['gradeCode'], 'gradeCode'),
      gradeLabel: _requireNonemptyString(json['gradeLabel'], 'gradeLabel'),
      subjects: subjects,
      status: status,
      stage: parsedStage.value,
      supportedStage: parsedStage.supported,
      progressPercent: progress,
      totalCourseCount: total,
      readyCourseCount: ready,
      failedCourseCount: failed,
      attempt: _requireNonnegativeInt(json['attempt'], 'attempt'),
      canRetry: canRetry,
      retryAfterMs: _requireNullableInt(json['retryAfterMs'], 'retryAfterMs'),
      message: _requireString(json['message'], 'message'),
      lastProgressAt: _requireNullableInt(
        json['lastProgressAt'],
        'lastProgressAt',
      ),
      updatedAt: _requireInt(json['updatedAt'], 'updatedAt'),
      completedAt: _requireNullableInt(json['completedAt'], 'completedAt'),
      error: rawError == null
          ? null
          : LearningPreparationSafeError.fromJson(rawError),
      contentProgress: contentProgress,
      courseSupply: json.containsKey('courseSupply')
          ? CourseSupplySummary.fromJson(json['courseSupply'])
          : null,
    );
  }
}

({LearningPreparationStage value, bool supported}) _parseStage(String value) {
  return switch (value) {
    'queued' => (value: LearningPreparationStage.queued, supported: true),
    'planning' => (value: LearningPreparationStage.planning, supported: true),
    'generating_content' => (
      value: LearningPreparationStage.generatingContent,
      supported: true,
    ),
    'building_classrooms' => (
      value: LearningPreparationStage.buildingClassrooms,
      supported: true,
    ),
    'generating_speech' => (
      value: LearningPreparationStage.generatingSpeech,
      supported: true,
    ),
    'validating' => (
      value: LearningPreparationStage.validating,
      supported: true,
    ),
    'publishing' => (
      value: LearningPreparationStage.publishing,
      supported: true,
    ),
    'retry_wait' => (
      value: LearningPreparationStage.retryWait,
      supported: true,
    ),
    'completed' => (value: LearningPreparationStage.completed, supported: true),
    _ => (value: LearningPreparationStage.queued, supported: false),
  };
}

Map<String, dynamic> _requireMap(Object? value, String field) {
  if (value is! Map) {
    throw LearningPreparationFormatException('$field must be an object');
  }
  if (value.keys.any((key) => key is! String)) {
    throw LearningPreparationFormatException('$field keys must be strings');
  }
  return Map<String, dynamic>.from(value);
}

void _requireExactKeys(
  Map<String, dynamic> value,
  Set<String> expected,
  String field,
) {
  if (!_setEquals(value.keys.toSet(), expected)) {
    throw LearningPreparationFormatException('$field has an invalid shape');
  }
}

bool _setEquals(Set<String> left, Set<String> right) {
  return left.length == right.length && left.containsAll(right);
}

String _requireString(Object? value, String field) {
  if (value is! String) {
    throw LearningPreparationFormatException('$field must be a string');
  }
  return value;
}

String _requireNonemptyString(Object? value, String field) {
  final result = _requireString(value, field);
  if (result.isEmpty) {
    throw LearningPreparationFormatException('$field must not be empty');
  }
  return result;
}

bool _requireBool(Object? value, String field) {
  if (value is! bool) {
    throw LearningPreparationFormatException('$field must be a boolean');
  }
  return value;
}

int _requireInt(Object? value, String field) {
  if (value is! int) {
    throw LearningPreparationFormatException('$field must be an integer');
  }
  return value;
}

int _requireNonnegativeInt(Object? value, String field) {
  final result = _requireInt(value, field);
  if (result < 0) {
    throw LearningPreparationFormatException('$field must be nonnegative');
  }
  return result;
}

int? _requireNullableInt(Object? value, String field) {
  if (value == null) return null;
  return _requireInt(value, field);
}

void _validateCounts({
  required int ready,
  required int failed,
  required int total,
  required String field,
}) {
  if (ready > total || failed > total || ready + failed > total) {
    throw LearningPreparationFormatException('$field counts are inconsistent');
  }
}
