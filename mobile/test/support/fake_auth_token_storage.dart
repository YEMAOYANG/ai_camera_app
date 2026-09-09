import 'package:warm_sight/src/core/storage/auth_token_storage.dart';

class FakeAuthSecureSessionStorage implements AuthSecureSessionStorage {
  FakeAuthSecureSessionStorage({this.envelope});

  String? envelope;

  @override
  Future<void> delete() async {
    envelope = null;
  }

  @override
  Future<String?> read() async => envelope;

  @override
  Future<void> write(String envelope) async {
    this.envelope = envelope;
  }
}
