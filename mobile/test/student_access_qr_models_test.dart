import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';

void main() {
  group('StudentQrChallengeLink', () {
    const baseUrl = 'https://student.example.test';

    test('accepts only the configured origin and exact QR path', () {
      final result = StudentQrChallengeLink.tryParse(
        rawValue:
            'https://student.example.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
        studentWebBaseUrl: baseUrl,
      );

      expect(
        result?.challengeId,
        'msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
      );
    });

    test('rejects a lookalike host and an arbitrary path', () {
      expect(
        StudentQrChallengeLink.tryParse(
          rawValue:
              'https://student.example.test.evil.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
          studentWebBaseUrl: baseUrl,
        ),
        isNull,
      );
      expect(
        StudentQrChallengeLink.tryParse(
          rawValue:
              'https://student.example.test/redirect?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd',
          studentWebBaseUrl: baseUrl,
        ),
        isNull,
      );
    });

    test('rejects fragments, extra parameters, and duplicate IDs', () {
      for (final value in [
        'https://student.example.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd#next',
        'https://student.example.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd&next=https://evil.test',
        'https://student.example.test/pair/qr?challengeId=msc_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcd&challengeId=msc_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn',
      ]) {
        expect(
          StudentQrChallengeLink.tryParse(
            rawValue: value,
            studentWebBaseUrl: baseUrl,
          ),
          isNull,
          reason: value,
        );
      }
    });
  });
}
