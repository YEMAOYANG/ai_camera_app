import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';

typedef StudentAccessScope = ({
  String childId,
  String gradeCode,
  int? schoolYearStartYear,
  int? gradeConfirmedAt,
});

StudentAccessScope studentAccessScope(ChildProfile child) => (
  childId: child.id,
  gradeCode: child.gradeCode,
  schoolYearStartYear: child.schoolYearStartYear,
  gradeConfirmedAt: child.gradeConfirmedAt,
);

/// Login eligibility is checked once per child/grade while the flow is open.
/// Home course polling must not tear down the camera or focused PIN fields.
/// The preview/approve/pairing APIs still enforce current server permissions.
final studentAccessAvailabilityProvider = FutureProvider.autoDispose
    .family<LearningAvailability, StudentAccessScope>((ref, scope) {
      return ref
          .watch(learningAvailabilityRepositoryProvider)
          .current(scope.childId);
    });
