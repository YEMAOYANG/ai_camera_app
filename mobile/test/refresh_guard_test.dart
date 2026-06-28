import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/state/refresh_guard.dart';

void main() {
  test('RefreshGuard merges concurrent light refreshes', () async {
    final guard = RefreshGuard();
    var runs = 0;

    await Future.wait([
      guard.runLight(() async {
        runs++;
        await Future<void>.delayed(const Duration(milliseconds: 30));
      }),
      guard.runLight(() async {
        runs++;
      }),
    ]);

    expect(runs, 2);
  });

  test('MonitorAnalysisGuard ignores heavy refresh within cooldown', () async {
    final guard = MonitorAnalysisGuard(minInterval: const Duration(seconds: 3));
    var runs = 0;

    final first = await guard.runHeavy(() async {
      runs++;
    });
    final second = await guard.runHeavy(() async {
      runs++;
    });

    expect(first, isTrue);
    expect(second, isFalse);
    expect(runs, 1);
  });
}
