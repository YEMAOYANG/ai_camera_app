import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';

SchoolTextbook fixtureBook(
  String subject, {
  bool selected = true,
  TextbookLearningStatus? learningStatus,
}) => SchoolTextbook(
  editionId: 'fixture-$subject',
  revisionId: 'fixture-1',
  title: '测试用一年级上册',
  publisher: '测试出版社',
  editionLabel: subject == 'chinese' ? '统编版 · 测试记录' : '测试版 · 测试记录',
  subject: subject,
  volume: 'upper',
  schoolSystem: 'six_year',
  partial: false,
  indexOnly:
      learningStatus?.available == null || learningStatus!.available == 0,
  lessonCount: learningStatus?.available ?? 0,
  selected: selected,
  selectionRevision: selected ? 1 : 0,
  learningStatus: learningStatus,
);

SchoolTextbookCatalog fixtureCatalog({bool selected = false}) =>
    SchoolTextbookCatalog(
      year: 2026,
      semester: 'upper',
      books: [
        for (final subject in ['chinese', 'math', 'english', 'science'])
          fixtureBook(
            subject,
            selected: selected,
            learningStatus: selected
                ? const TextbookLearningStatus(status: 'unpublished')
                : null,
          ),
      ],
    );
