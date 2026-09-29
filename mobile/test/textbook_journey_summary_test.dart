import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/textbook_learning_summary.dart';

void main() {
  testWidgets(
    'parent sees unresolved skills and a concrete next action without opening another page',
    (tester) async {
      final catalog = SchoolTextbookCatalog.fromJson({
        'ok': true,
        'schemaVersion': 'mira.learning.textbooks.v1',
        'schoolYearStartYear': 2026,
        'semester': 'upper',
        'books': [],
        'learningJourneys': [
          {
            'title': '天地人',
            'status': 'needs_support',
            'parentNeeded': true,
            'nextStep': '请在孩子休息后陪同确认题意，再进入课堂完成短练习。',
            'independentBefore': 4,
            'verifiedCount': 5,
            'remainingSkills': ['你'],
            'diagnoses': ['你：说话、听话和谈到的人还需区分'],
            'reviewDueAt': null,
          },
        ],
      });
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            schoolTextbooksProvider(
              'child',
            ).overrideWith((ref) async => catalog),
          ],
          child: const MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: DecoratedBox(
                  decoration: BoxDecoration(color: Colors.white),
                  child: TextbookLearningSummary(childId: 'child'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('天地人 · 需要您留意'), findsOneWidget);
      expect(find.text('前测独立 4/6 → 本轮新情境独立 5/6'), findsOneWidget);
      expect(find.text('仍需练习：你'), findsOneWidget);
      expect(find.textContaining('陪同确认题意'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
