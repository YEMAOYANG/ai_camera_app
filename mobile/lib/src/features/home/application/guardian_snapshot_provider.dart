import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/features/home/domain/guardian_snapshot.dart';

final guardianSnapshotProvider = Provider<GuardianSnapshot>((ref) {
  return GuardianSnapshot.demo();
});
