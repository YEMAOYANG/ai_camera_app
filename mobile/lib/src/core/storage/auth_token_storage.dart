import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const secureAuthSessionEnvelopeKey = 'auth.secure.session.v1';

abstract interface class AuthSecureSessionStorage {
  Future<String?> read();

  Future<void> write(String envelope);

  Future<void> delete();
}

class FlutterSecureAuthSessionStorage implements AuthSecureSessionStorage {
  const FlutterSecureAuthSessionStorage({
    this.storage = const FlutterSecureStorage(
      aOptions: AndroidOptions(resetOnError: false),
    ),
  });

  final FlutterSecureStorage storage;

  @override
  Future<String?> read() {
    return storage.read(key: secureAuthSessionEnvelopeKey);
  }

  @override
  Future<void> write(String envelope) {
    return storage.write(key: secureAuthSessionEnvelopeKey, value: envelope);
  }

  @override
  Future<void> delete() {
    return storage.delete(key: secureAuthSessionEnvelopeKey);
  }
}
