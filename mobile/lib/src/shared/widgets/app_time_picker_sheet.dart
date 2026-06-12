import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';

Future<String?> showAppTimePickerSheet({
  required BuildContext context,
  required String initialValue,
  int minMinutes = 0,
  int maxMinutes = 23 * 60 + 59,
  String title = '选择时间',
  String? subtitle,
  String invalidMessage = '请选择有效时间',
  double maxHeightFactor = 0.58,
}) {
  return showAppBottomSheet<String>(
    context: context,
    maxHeightFactor: maxHeightFactor,
    child: AppTimePickerSheet(
      title: title,
      subtitle: subtitle,
      initialValue: initialValue,
      minMinutes: minMinutes,
      maxMinutes: maxMinutes,
      invalidMessage: invalidMessage,
    ),
  );
}

class AppTimePickerSheet extends StatefulWidget {
  const AppTimePickerSheet({
    required this.initialValue,
    required this.minMinutes,
    required this.maxMinutes,
    required this.invalidMessage,
    this.title = '选择时间',
    this.subtitle,
    super.key,
  });

  final String title;
  final String? subtitle;
  final String initialValue;
  final int minMinutes;
  final int maxMinutes;
  final String invalidMessage;

  @override
  State<AppTimePickerSheet> createState() => _AppTimePickerSheetState();
}

class _AppTimePickerSheetState extends State<AppTimePickerSheet> {
  late final FixedExtentScrollController _hourController;
  late final FixedExtentScrollController _minuteController;
  late int _hour;
  late int _minute;
  late final int _minMinutes;
  late final int _maxMinutes;

  @override
  void initState() {
    super.initState();
    _minMinutes = widget.minMinutes.clamp(0, 23 * 60 + 59).toInt();
    _maxMinutes = widget.maxMinutes.clamp(_minMinutes, 23 * 60 + 59).toInt();
    final initial = _timeOfDay(
      _minuteText(
        _minutesOfDay(
          widget.initialValue,
        ).clamp(_minMinutes, _maxMinutes).toInt(),
      ),
    );
    _hour = initial.hour;
    _minute = initial.minute;
    _hourController = FixedExtentScrollController(initialItem: _hour);
    _minuteController = FixedExtentScrollController(initialItem: _minute);
  }

  @override
  void dispose() {
    _hourController.dispose();
    _minuteController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final selectedMinutes = _hour * 60 + _minute;
    final valid =
        selectedMinutes >= _minMinutes && selectedMinutes <= _maxMinutes;
    final rangeLabel = _minMinutes == 0 && _maxMinutes == 23 * 60 + 59
        ? null
        : '可选择 ${_minuteText(_minMinutes)} - ${_minuteText(_maxMinutes)}';
    final subtitle = widget.subtitle ?? rangeLabel;

    return AppBottomSheetBody(
      title: widget.title,
      subtitle: subtitle,
      scrollable: false,
      footer: AppSheetFooterActions(
        children: [
          AppSheetSecondaryButton(
            label: '取消',
            onTap: () => Navigator.of(context).pop(),
          ),
          AppSheetPrimaryButton(
            label: '确定',
            trailing: const AppButtonGlyph(icon: Icons.check),
            onTap: valid
                ? () {
                    Navigator.of(
                      context,
                    ).pop(_timeText(TimeOfDay(hour: _hour, minute: _minute)));
                  }
                : null,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AppSurface(
            radius: 20,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            color: AppColors.surfaceSoft,
            borderColor: AppColors.borderSoft,
            child: SizedBox(
              height: 174,
              child: Row(
                children: [
                  Expanded(
                    child: _TimeWheel(
                      controller: _hourController,
                      values: List.generate(24, (index) => index),
                      suffix: '时',
                      onChanged: (value) => setState(() => _hour = value),
                    ),
                  ),
                  Container(
                    width: 1,
                    height: 116,
                    color: AppColors.muted.withValues(alpha: 0.12),
                  ),
                  Expanded(
                    child: _TimeWheel(
                      controller: _minuteController,
                      values: List.generate(60, (index) => index),
                      suffix: '分',
                      onChanged: (value) => setState(() => _minute = value),
                    ),
                  ),
                ],
              ),
            ),
          ),
          if (!valid) ...[
            const SizedBox(height: 9),
            Text(
              widget.invalidMessage,
              style: const TextStyle(
                color: AppColors.danger,
                fontFamily: AppTypography.systemFont,
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 0,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TimeWheel extends StatelessWidget {
  const _TimeWheel({
    required this.controller,
    required this.values,
    required this.suffix,
    required this.onChanged,
  });

  final FixedExtentScrollController controller;
  final List<int> values;
  final String suffix;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return CupertinoPicker(
      scrollController: controller,
      itemExtent: 42,
      diameterRatio: 1.12,
      squeeze: 1.04,
      selectionOverlay: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.primary.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(14),
        ),
      ),
      onSelectedItemChanged: (index) => onChanged(values[index]),
      children: [
        for (final value in values)
          Center(
            child: Text(
              '${value.toString().padLeft(2, '0')} $suffix',
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 19,
                fontWeight: FontWeight.w700,
                letterSpacing: 0,
              ),
            ),
          ),
      ],
    );
  }
}

int _minutesOfDay(String time) {
  final parts = time.split(':');
  final hour = parts.isNotEmpty ? int.tryParse(parts[0]) ?? 0 : 0;
  final minute = parts.length > 1 ? int.tryParse(parts[1]) ?? 0 : 0;
  return hour * 60 + minute;
}

TimeOfDay _timeOfDay(String time) {
  final parts = time.split(':');
  return TimeOfDay(
    hour: parts.isNotEmpty ? int.tryParse(parts[0]) ?? 19 : 19,
    minute: parts.length > 1 ? int.tryParse(parts[1]) ?? 0 : 0,
  );
}

String _timeText(TimeOfDay time) {
  final hour = time.hour.toString().padLeft(2, '0');
  final minute = time.minute.toString().padLeft(2, '0');
  return '$hour:$minute';
}

String _minuteText(int minutes) {
  final safeMinutes = minutes.clamp(0, 23 * 60 + 59).toInt();
  final hour = (safeMinutes ~/ 60).toString().padLeft(2, '0');
  final minute = (safeMinutes % 60).toString().padLeft(2, '0');
  return '$hour:$minute';
}
