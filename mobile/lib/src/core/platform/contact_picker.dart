import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';

class PickedPhoneContact {
  const PickedPhoneContact({required this.name, required this.phone});

  final String name;
  final String phone;
}

class ContactPickerException implements Exception {
  const ContactPickerException(this.message);

  final String message;

  @override
  String toString() => message;
}

Future<PickedPhoneContact?> pickPhoneContact() async {
  final status = await FlutterContacts.permissions.request(PermissionType.read);
  if (status != PermissionStatus.granted &&
      status != PermissionStatus.limited) {
    if (status == PermissionStatus.permanentlyDenied ||
        status == PermissionStatus.restricted) {
      throw const ContactPickerException('请在系统设置中允许访问通讯录后再选择联系人');
    }
    throw const ContactPickerException('需要通讯录权限，才能从手机联系人中选择号码');
  }

  try {
    final contact = await FlutterContacts.native.showPicker(
      properties: const {ContactProperty.phone},
    );
    if (contact == null) return null;
    final phone = _normalizePhone(
      contact.phones.isNotEmpty ? contact.phones.first.number : '',
    );
    return PickedPhoneContact(
      name: (contact.displayName ?? '').trim(),
      phone: phone,
    );
  } on PlatformException catch (error) {
    if (error.code == 'not_available') {
      throw const ContactPickerException('当前设备暂不支持从通讯录选择联系人');
    }
    throw ContactPickerException(error.message ?? '通讯录暂时无法打开，请稍后再试');
  }
}

String _normalizePhone(String value) {
  var digits = value.replaceAll(RegExp(r'\D'), '');
  if (digits.startsWith('86') && digits.length == 13) {
    digits = digits.substring(2);
  }
  return digits;
}
