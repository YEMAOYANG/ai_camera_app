import 'package:flutter_riverpod/legacy.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';

/// WS reminder_decision 乐观待办；careSummary 对齐成功后清空。
final pendingParentReviewsOverrideProvider =
    StateProvider<List<ParentReviewItem>>((ref) => const []);

const _optimisticParentReviewTtlMs = 2 * 60 * 1000;

List<ParentReviewItem> mergeParentReviews({
  List<ParentReviewItem>? overrideItems,
  List<ParentReviewItem>? serverItems,
  int? nowMs,
}) {
  final now = nowMs ?? DateTime.now().millisecondsSinceEpoch;
  final merged = <String, ParentReviewItem>{};
  final serverSynced = serverItems != null;
  for (final item in serverItems ?? const <ParentReviewItem>[]) {
    if (item.status == 'pending') merged[item.id] = item;
  }
  for (final item in overrideItems ?? const <ParentReviewItem>[]) {
    if (item.status != 'pending') continue;
    if (serverSynced && !merged.containsKey(item.id)) {
      final age = item.createdAt > 0 ? now - item.createdAt : 0;
      if (age > _optimisticParentReviewTtlMs) continue;
    }
    merged[item.id] = item;
  }
  return merged.values.toList()
    ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
}

ParentReviewItem? parentReviewFromRealtimeEvent(Map<String, dynamic>? payload) {
  if (payload == null || payload.isEmpty) return null;
  final status = _string(payload['status']);
  if (status.isNotEmpty && status != 'pending') return null;
  final id = _string(payload['id']);
  if (id.isEmpty) return null;
  return ParentReviewItem.fromJson(payload);
}

String _string(Object? value) {
  if (value is String) return value.trim();
  return '';
}
