class LearningAvailabilityFormatException implements FormatException {
  const LearningAvailabilityFormatException(this.message);

  @override
  final String message;

  @override
  int? get offset => null;

  @override
  Object? get source => null;

  @override
  String toString() => 'LearningAvailabilityFormatException: $message';
}

class LearningAvailability {
  const LearningAvailability({
    required this.gradeCode,
    required this.hasActiveRelease,
    required this.availableCourseCount,
    required this.canLearnNow,
    this.canAccessWorkspace = false,
    this.learningState,
  });

  final String gradeCode;
  final bool hasActiveRelease;
  final int availableCourseCount;
  final bool canLearnNow;
  final bool canAccessWorkspace;
  final LearningAvailabilityState? learningState;

  factory LearningAvailability.fromJson(Object? value) {
    final root = _requireMap(value, 'learning availability response');
    _requireExactKeys(root, const {
      'ok',
      'availability',
    }, 'learning availability response');
    if (root['ok'] != true) {
      throw const LearningAvailabilityFormatException(
        'learning availability response is not successful',
      );
    }

    final availability = _requireMap(
      root['availability'],
      'learning availability',
    );
    _requireExactKeys(availability, {
      'gradeCode',
      'hasActiveRelease',
      'availableCourseCount',
      'canLearnNow',
      'canAccessWorkspace',
      if (availability.containsKey('learningState')) 'learningState',
    }, 'learning availability');
    final gradeCode = availability['gradeCode'];
    final hasActiveRelease = availability['hasActiveRelease'];
    final availableCourseCount = availability['availableCourseCount'];
    final canLearnNow = availability['canLearnNow'];
    final canAccessWorkspace = availability['canAccessWorkspace'];
    final learningState = availability.containsKey('learningState')
        ? LearningAvailabilityState.fromJson(availability['learningState'])
        : null;
    if (canAccessWorkspace is! bool) {
      throw const LearningAvailabilityFormatException(
        'learning availability canAccessWorkspace is invalid',
      );
    }
    if (gradeCode is! String || gradeCode.trim().isEmpty) {
      throw const LearningAvailabilityFormatException(
        'learning availability gradeCode is invalid',
      );
    }
    if (hasActiveRelease is! bool) {
      throw const LearningAvailabilityFormatException(
        'learning availability hasActiveRelease is invalid',
      );
    }
    if (availableCourseCount is! int || availableCourseCount < 0) {
      throw const LearningAvailabilityFormatException(
        'learning availability availableCourseCount is invalid',
      );
    }
    if (canLearnNow is! bool ||
        canLearnNow !=
            (learningState == null
                ? hasActiveRelease || availableCourseCount > 0
                : availableCourseCount > 0) ||
        (learningState != null &&
            learningState.availableCourseCount != availableCourseCount)) {
      throw const LearningAvailabilityFormatException(
        'learning availability canLearnNow is inconsistent',
      );
    }
    return LearningAvailability(
      gradeCode: gradeCode,
      hasActiveRelease: hasActiveRelease,
      availableCourseCount: availableCourseCount,
      canLearnNow: canLearnNow,
      canAccessWorkspace: canAccessWorkspace,
      learningState: learningState,
    );
  }
}

class LearningAvailabilityState {
  const LearningAvailabilityState({
    required this.status,
    required this.availableCourseCount,
    required this.newCourseCount,
    required this.reviewCourseCount,
    required this.message,
  });

  final String status;
  final int availableCourseCount;
  final int newCourseCount;
  final int reviewCourseCount;
  final String message;
  bool get isTerminal =>
      status == 'scope_completed' || status == 'not_open' || status == 'empty';

  factory LearningAvailabilityState.fromJson(Object? value) {
    final row = _requireMap(value, 'learningState');
    _requireExactKeys(row, const {
      'schemaVersion',
      'availabilityStatus',
      'availableCourseCount',
      'newCourseCount',
      'reviewCourseCount',
      'publishedCourseCount',
      'message',
    }, 'learningState');
    const statuses = {
      'ready',
      'preparing',
      'paused',
      'not_open',
      'scope_completed',
      'empty',
    };
    if (row['schemaVersion'] != 'mira.learning.availability-state.v1' ||
        !statuses.contains(row['availabilityStatus']) ||
        row['message'] is! String ||
        (row['message'] as String).trim().isEmpty ||
        [
          'availableCourseCount',
          'newCourseCount',
          'reviewCourseCount',
          'publishedCourseCount',
        ].any((key) => row[key] is! int || (row[key] as int) < 0)) {
      throw const LearningAvailabilityFormatException('invalid learningState');
    }
    final available = row['availableCourseCount'] as int;
    final fresh = row['newCourseCount'] as int;
    final review = row['reviewCourseCount'] as int;
    if (available != fresh + review ||
        available > (row['publishedCourseCount'] as int)) {
      throw const LearningAvailabilityFormatException(
        'inconsistent learningState counts',
      );
    }
    return LearningAvailabilityState(
      status: row['availabilityStatus'] as String,
      availableCourseCount: available,
      newCourseCount: fresh,
      reviewCourseCount: review,
      message: row['message'] as String,
    );
  }
}

Map<String, dynamic> _requireMap(Object? value, String field) {
  if (value is! Map || value.keys.any((key) => key is! String)) {
    throw LearningAvailabilityFormatException('$field must be an object');
  }
  return Map<String, dynamic>.from(value);
}

void _requireExactKeys(
  Map<String, dynamic> value,
  Set<String> expected,
  String field,
) {
  final actual = value.keys.toSet();
  if (actual.length != expected.length || !actual.containsAll(expected)) {
    throw LearningAvailabilityFormatException('$field has an invalid shape');
  }
}
