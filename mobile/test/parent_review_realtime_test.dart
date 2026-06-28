import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/care/application/parent_review_realtime.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';

void main() {
  test('parentReviewFromRealtimeEvent parses reviewType and itemType', () {
    final fromReviewType = parentReviewFromRealtimeEvent({
      'id': 'rev_1',
      'status': 'pending',
      'summary': ' bedtime needs review',
      'reviewType': 'care_notify',
      'createdAt': 1,
    });
    expect(fromReviewType?.reviewType, 'care_notify');

    final fromItemType = parentReviewFromRealtimeEvent({
      'id': 'rev_2',
      'status': 'pending',
      'summary': 'meal habit',
      'itemType': 'meal_habit',
      'createdAt': 2,
    });
    expect(fromItemType?.reviewType, 'meal_habit');
  });

  test('mergeParentReviews dedupes override and server pending items', () {
    final now = DateTime.now().millisecondsSinceEpoch;
    const server = [
      ParentReviewItem(
        id: 'a',
        childId: 'child_1',
        scenario: 'bedtime',
        summary: 'server',
        reviewType: 'care',
        status: 'pending',
        createdAt: 1,
      ),
    ];
    final override = [
      ParentReviewItem(
        id: 'b',
        childId: 'child_1',
        scenario: 'meal_habit',
        summary: 'ws',
        reviewType: 'care',
        status: 'pending',
        createdAt: now,
      ),
      ParentReviewItem(
        id: 'a',
        childId: 'child_1',
        scenario: 'bedtime',
        summary: 'override wins',
        reviewType: 'care',
        status: 'pending',
        createdAt: now,
      ),
    ];

    final merged = mergeParentReviews(
      overrideItems: override,
      serverItems: server,
      nowMs: now,
    );
    expect(merged.length, 2);
    expect(merged.map((item) => item.id).toSet(), {'a', 'b'});
    expect(merged.singleWhere((item) => item.id == 'a').summary, 'override wins');
  });

  test('mergeParentReviews drops stale optimistic items after server sync', () {
    const server = <ParentReviewItem>[];
    final now = DateTime.now().millisecondsSinceEpoch;
    final override = [
      ParentReviewItem(
        id: 'stale',
        childId: 'child_1',
        scenario: 'bedtime',
        summary: 'old ws',
        reviewType: 'care',
        status: 'pending',
        createdAt: 1,
      ),
      ParentReviewItem(
        id: 'fresh',
        childId: 'child_1',
        scenario: 'meal_habit',
        summary: 'new ws',
        reviewType: 'care',
        status: 'pending',
        createdAt: now,
      ),
    ];

    final merged = mergeParentReviews(
      overrideItems: override,
      serverItems: server,
      nowMs: now,
    );
    expect(merged.length, 1);
    expect(merged.first.id, 'fresh');
  });
}
