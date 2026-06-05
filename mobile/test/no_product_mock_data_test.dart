import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('product source does not include mock runtime data switches', () {
    final sourceRoot = Directory('lib/src');
    final banned = <RegExp>[
      RegExp(r'useMockData'),
      RegExp(r'AppEnvironment\.mock'),
      RegExp(r'USE_MOCK_DATA'),
      RegExp(r'mock://'),
      RegExp(r'features/mvp'),
      RegExp(r'GuardianSnapshot\.demo'),
      RegExp(r'guardianSnapshotProvider'),
      RegExp(r'guardianMvpSnapshotProvider'),
      RegExp(r'\b_mock[A-Za-z0-9_]*'),
      RegExp(r'mock_access'),
      RegExp(r'mock_refresh'),
    ];

    final violations = <String>[];
    for (final file
        in sourceRoot
            .listSync(recursive: true)
            .whereType<File>()
            .where((file) => file.path.endsWith('.dart'))) {
      final lines = file.readAsLinesSync();
      for (var index = 0; index < lines.length; index += 1) {
        final line = lines[index];
        for (final pattern in banned) {
          if (pattern.hasMatch(line)) {
            violations.add('${file.path}:${index + 1}: ${pattern.pattern}');
          }
        }
      }
    }

    expect(violations, isEmpty, reason: violations.join('\n'));
  });
}
