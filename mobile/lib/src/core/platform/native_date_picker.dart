import 'package:flutter/services.dart';

class NativeDatePicker {
  const NativeDatePicker._();

  static const MethodChannel _channel = MethodChannel(
    'ai_camera_app/native_date_picker',
  );

  static Future<DateTime?> pickDate({
    required DateTime initialDate,
    required DateTime minDate,
    required DateTime maxDate,
    String title = '选择日期',
  }) async {
    try {
      final value = await _channel.invokeMethod<String>('pickDate', {
        'title': title,
        'initialDate': _formatDate(initialDate),
        'minDate': _formatDate(minDate),
        'maxDate': _formatDate(maxDate),
        'locale': 'zh_CN',
      });
      if (value == null || value.isEmpty) return null;
      return _parseDate(value);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  static String _formatDate(DateTime value) {
    final month = value.month.toString().padLeft(2, '0');
    final day = value.day.toString().padLeft(2, '0');
    return '${value.year}-$month-$day';
  }

  static DateTime? _parseDate(String value) {
    final parts = value.split('-');
    if (parts.length != 3) return null;

    final year = int.tryParse(parts[0]);
    final month = int.tryParse(parts[1]);
    final day = int.tryParse(parts[2]);
    if (year == null || month == null || day == null) return null;

    final parsed = DateTime(year, month, day);
    if (parsed.year != year || parsed.month != month || parsed.day != day) {
      return null;
    }
    return parsed;
  }
}
