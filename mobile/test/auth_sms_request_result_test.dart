import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/auth/application/auth_repository.dart';

void main() {
  test('SMS request result requires an explicit successful send flag', () {
    expect(
      SmsCodeRequestResult.fromJson(const {'message': 'missing'}).codeSent,
      isFalse,
    );
    expect(
      SmsCodeRequestResult.fromJson(const {
        'codeSent': false,
        'message': 'not sent',
      }).codeSent,
      isFalse,
    );
    expect(
      SmsCodeRequestResult.fromJson(const {
        'codeSent': true,
        'message': 'sent',
      }).codeSent,
      isTrue,
    );
  });

  test('SMS retry delay uses server value with a safe fallback and bounds', () {
    SmsCodeRequestResult parse(dynamic value) => SmsCodeRequestResult.fromJson({
      'codeSent': true,
      'message': 'sent',
      'retryAfterSeconds': value,
    });

    expect(parse(75).retryAfterSeconds, 75);
    expect(parse('42').retryAfterSeconds, 42);
    expect(parse(null).retryAfterSeconds, 60);
    expect(parse(0).retryAfterSeconds, 1);
    expect(parse(9999).retryAfterSeconds, 300);
    expect(parse('invalid').retryAfterSeconds, 60);
  });

  test('SMS request result preserves development debug code', () {
    final result = SmsCodeRequestResult.fromJson(const {
      'codeSent': true,
      'message': 'sent',
      'debugCode': '042731',
      'retryAfterSeconds': 60,
    });

    expect(result.debugCode, '042731');
  });
}
