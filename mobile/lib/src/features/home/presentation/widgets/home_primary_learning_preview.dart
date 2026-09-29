import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/parent_learning_observation_sheet.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/textbook_learning_summary.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';

class HomePrimaryLearningPreview extends StatelessWidget {
  const HomePrimaryLearningPreview({required this.child, super.key});
  final ChildProfile child;
  @override
  Widget build(BuildContext context) => Column(
    key: const ValueKey('primaryLearningPreview'),
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      TextbookLearningSummary(
        childId: child.id,
        onManage: () => context.push(profileSchoolTextbooksPath),
      ),
      ParentLearningObservationEntry(childId: child.id, childName: child.name),
    ],
  );
}
