import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:warm_sight/src/features/student_access/application/student_qr_scanner_lifecycle.dart';

void main() {
  test('duplicate visibility events do not start the camera twice', () async {
    final calls = <String>[];
    final start = Completer<void>();
    final lifecycle = StudentQrScannerLifecycle(
      startCamera: () async {
        calls.add('start');
        await start.future;
      },
      stopCamera: () async => calls.add('stop'),
      disposeCamera: () async => calls.add('dispose'),
    );
    final first = lifecycle.setRouteCurrent(true);
    final duplicate = lifecycle.setRouteCurrent(true);
    final resumed = lifecycle.setAppActive(true);
    await Future<void>.delayed(Duration.zero);
    expect(calls, ['start']);
    start.complete();
    await Future.wait([first, duplicate, resumed]);
    expect(calls, ['start']);
    await lifecycle.close();
    expect(calls, ['start', 'stop', 'dispose']);
  });

  test('failed camera start can still be retried', () async {
    var starts = 0;
    final lifecycle = StudentQrScannerLifecycle(
      startCamera: () async {
        if (++starts == 1) throw StateError('camera unavailable');
      },
      stopCamera: () async {},
      disposeCamera: () async {},
    );
    await expectLater(lifecycle.setRouteCurrent(true), throwsStateError);
    await lifecycle.retry();
    await lifecycle.resume();
    expect(starts, 2);
    await lifecycle.close();
  });

  test(
    'camera follows app and route visibility without hidden restarts',
    () async {
      final calls = <String>[];
      final lifecycle = StudentQrScannerLifecycle(
        startCamera: () async => calls.add('start'),
        stopCamera: () async => calls.add('stop'),
        disposeCamera: () async => calls.add('dispose'),
      );

      await lifecycle.setRouteCurrent(true);
      calls.clear();
      await lifecycle.resume();
      await lifecycle.setAppActive(false);
      await lifecycle.setRouteCurrent(false);
      await lifecycle.setAppActive(true);
      expect(calls, ['stop']);

      await lifecycle.setRouteCurrent(true);
      expect(calls.last, 'start');
    },
  );

  test('delivery stops first and close awaits stop before dispose', () async {
    final calls = <String>[];
    final stopCompleter = Completer<void>();
    final lifecycle = StudentQrScannerLifecycle(
      startCamera: () async => calls.add('start'),
      stopCamera: () async {
        calls.add('stop');
        await stopCompleter.future;
      },
      disposeCamera: () async => calls.add('dispose'),
    );

    await lifecycle.setRouteCurrent(true);
    calls.clear();
    final delivery = lifecycle.markDelivered();
    await Future<void>.delayed(Duration.zero);
    expect(calls, ['stop']);
    final closing = lifecycle.close();
    expect(calls, ['stop']);

    stopCompleter.complete();
    await delivery;
    await closing;
    expect(calls, ['stop', 'dispose']);

    await lifecycle.retry();
    expect(calls, ['stop', 'dispose']);
  });
}
