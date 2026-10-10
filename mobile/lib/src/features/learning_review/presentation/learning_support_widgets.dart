import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import '../application/learning_review_repository.dart';

String learningDate(DateTime? value) =>
    value == null ? '待安排' : DateFormat('M月d日 HH:mm').format(value);
void learningBack(BuildContext context) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go(profileReportsHubPath);
  }
}

class LearningLoading extends StatelessWidget {
  const LearningLoading({super.key});
  @override
  Widget build(BuildContext context) => const Padding(
    padding: EdgeInsets.all(24),
    child: Center(child: CircularProgressIndicator()),
  );
}

class LearningError extends StatelessWidget {
  const LearningError(this.error, this.retry, {super.key});
  final Object error;
  final VoidCallback retry;
  @override
  Widget build(BuildContext context) => AppStateView(
    variant: AppStateVariant.serviceUnavailable,
    title: '暂时无法读取',
    message: learningError(error),
    primaryActionLabel: '重新加载',
    onPrimaryAction: retry,
    compact: true,
  );
}

class LearningHeading extends StatelessWidget {
  const LearningHeading(this.title, {this.trailing, super.key});
  final String title;
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 20, bottom: 8),
    child: Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: AppColors.ink,
            ),
          ),
        ),
        ?trailing,
      ],
    ),
  );
}

Future<bool> confirmLearningAction(
  BuildContext context, {
  required String title,
  required String message,
  required String action,
}) async =>
    await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(action),
          ),
        ],
      ),
    ) ??
    false;
Future<DateTime?> pickLearningAppointment(
  BuildContext context,
  DateTime? initial,
) async {
  final now = DateTime.now();
  final date = await showDatePicker(
    context: context,
    initialDate: initial != null && initial.isAfter(now) ? initial : now,
    firstDate: now,
    lastDate: now.add(const Duration(days: 90)),
    helpText: '选择复习日期',
  );
  if (date == null || !context.mounted) return null;
  final time = await showTimePicker(
    context: context,
    initialTime: TimeOfDay.fromDateTime(
      initial ?? DateTime(now.year, now.month, now.day, 10),
    ),
    helpText: '选择复习时间',
  );
  return time == null
      ? null
      : DateTime(date.year, date.month, date.day, time.hour, time.minute);
}
