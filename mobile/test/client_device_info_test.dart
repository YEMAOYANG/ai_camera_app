import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/core/platform/client_device_info.dart';

void main() {
  test('device headers use ASCII-safe values for iOS URLSession', () {
    const info = ClientDeviceInfo(
      label: '本机 iPhone',
      type: 'phone',
      platform: 'ios',
      model: 'iPhone',
      hardware: 'iPhone10,1',
      osVersion: 'iOS 16.7.16',
      appVersion: '1.0.0+1',
    );

    final headers = info.headers;

    for (final value in headers.values) {
      expect(
        value.runes.every((codePoint) => codePoint <= 0x7F),
        isTrue,
        reason: 'header value must be ASCII: $value',
      );
    }
    expect(headers['X-Mira-Device-Label'], 'iPhone10,1');
  });
}
