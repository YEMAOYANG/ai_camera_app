import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/live_care/domain/camera_models.dart';

void main() {
  test('keeps loopback signaling url when api base is loopback', () {
    const session = CameraWebRtcSession(
      signalingUrl: 'ws://127.0.0.1:1984/api/ws?src=ipc45aw_hd',
      message: '实时画面连接已准备好。',
    );

    final normalized = session.normalizedForApiBase(
      'http://127.0.0.1:8000/api',
    );

    expect(normalized.signalingUrl, session.signalingUrl);
  });

  test('rewrites loopback signaling host for physical device lan api base', () {
    const session = CameraWebRtcSession(
      signalingUrl: 'ws://127.0.0.1:1984/api/ws?src=ipc45aw_hd',
      message: '实时画面连接已准备好。',
    );

    final normalized = session.normalizedForApiBase(
      'http://backend.lan.example:8000/api',
    );

    expect(
      normalized.signalingUrl,
      'ws://backend.lan.example:1984/api/ws?src=ipc45aw_hd',
    );
  });

  test('uses secure websocket scheme when api base is https', () {
    const session = CameraWebRtcSession(
      signalingUrl: 'ws://localhost:1984/api/ws?src=ipc45aw_hd',
      message: '实时画面连接已准备好。',
    );

    final normalized = session.normalizedForApiBase(
      'https://app.example.com/api',
    );

    expect(
      normalized.signalingUrl,
      'wss://app.example.com:1984/api/ws?src=ipc45aw_hd',
    );
  });
}
