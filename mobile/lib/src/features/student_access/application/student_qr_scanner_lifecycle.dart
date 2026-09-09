typedef StudentQrScannerAction = Future<void> Function();

/// Serializes camera start/stop/dispose and applies app + route visibility.
///
/// State changes are recorded synchronously, so a queued start is skipped when
/// the app or route becomes inactive before the native camera call begins.
class StudentQrScannerLifecycle {
  StudentQrScannerLifecycle({
    required this.startCamera,
    required this.stopCamera,
    required this.disposeCamera,
  });

  final StudentQrScannerAction startCamera;
  final StudentQrScannerAction stopCamera;
  final StudentQrScannerAction disposeCamera;

  Future<void> _barrier = Future<void>.value();
  Future<void>? _closeFuture;
  bool _appActive = true;
  bool _routeCurrent = false;
  bool _delivered = false;
  bool _closed = false;
  bool _running = false;

  Future<void> setAppActive(bool value) {
    _appActive = value;
    return value ? resume() : pause();
  }

  Future<void> setRouteCurrent(bool value) {
    _routeCurrent = value;
    return value ? resume() : pause();
  }

  Future<void> markDelivered() {
    _delivered = true;
    return pause();
  }

  Future<void> retry() {
    _delivered = false;
    return resume();
  }

  Future<void> resume() {
    return _enqueue(() async {
      if (_closed || !_appActive || !_routeCurrent || _delivered || _running) {
        return;
      }
      await startCamera();
      _running = true;
    });
  }

  Future<void> pause() {
    return _enqueue(() async {
      if (_closed || !_running) return;
      await stopCamera();
      _running = false;
    });
  }

  Future<void> close() {
    final existing = _closeFuture;
    if (existing != null) return existing;
    _closed = true;
    final closing = _enqueue(() async {
      if (_running) {
        await stopCamera();
        _running = false;
      }
      await disposeCamera();
    });
    _closeFuture = closing;
    return closing;
  }

  Future<void> _enqueue(StudentQrScannerAction action) {
    final next = _barrier.then<void>((_) => action());
    _barrier = next.then<void>((_) {}, onError: (Object _, StackTrace _) {});
    return next;
  }
}
