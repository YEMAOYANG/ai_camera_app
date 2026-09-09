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
  });

  final String gradeCode;
  final bool hasActiveRelease;
  final int availableCourseCount;
  final bool canLearnNow;
  final bool canAccessWorkspace;

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
    _requireExactKeys(availability, const {
      'gradeCode',
      'hasActiveRelease',
      'availableCourseCount',
      'canLearnNow',
      'canAccessWorkspace',
    }, 'learning availability');
    final gradeCode = availability['gradeCode'];
    final hasActiveRelease = availability['hasActiveRelease'];
    final availableCourseCount = availability['availableCourseCount'];
    final canLearnNow = availability['canLearnNow'];
    final canAccessWorkspace = availability['canAccessWorkspace'];
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
        canLearnNow != (hasActiveRelease || availableCourseCount > 0)) {
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
