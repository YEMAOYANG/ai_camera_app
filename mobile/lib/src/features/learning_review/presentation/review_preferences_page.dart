import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import '../application/learning_review_repository.dart';
import '../domain/learning_review_models.dart';
import 'learning_support_widgets.dart';

class ReviewPreferencesPage extends ConsumerWidget {
  const ReviewPreferencesPage({required this.childId, super.key});
  final String childId;
  @override
  Widget build(BuildContext context, WidgetRef ref) => ref
      .watch(reviewPreferencesProvider(childId))
      .when(
        data: (value) => _PreferencesForm(
          key: ValueKey(number(value.data['revision'])),
          childId: childId,
          value: value,
        ),
        loading: () => AppScreen(
          title: '复习安排',
          onBack: () => learningBack(context),
          children: const [LearningLoading()],
        ),
        error: (e, _) => AppScreen(
          title: '复习安排',
          onBack: () => learningBack(context),
          children: [
            LearningError(
              e,
              () => ref.invalidate(reviewPreferencesProvider(childId)),
            ),
          ],
        ),
      );
}

class _PreferencesForm extends ConsumerStatefulWidget {
  const _PreferencesForm({
    required this.childId,
    required this.value,
    super.key,
  });
  final String childId;
  final ReviewPreferences value;
  @override
  ConsumerState<_PreferencesForm> createState() => _PreferencesFormState();
}

class _PreferencesFormState extends ConsumerState<_PreferencesForm> {
  late Json values = Map.of(widget.value.data);
  bool busy = false;
  String? error;
  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await ref
          .read(learningReviewRepositoryProvider)
          .savePreferences(widget.childId, values);
      if (!mounted) return;
      ref.invalidate(reviewListProvider(widget.childId));
      showAppToast(context, '复习安排已保存', tone: AppToastTone.success);
      learningBack(context);
    } catch (e) {
      if (mounted) setState(() => error = learningError(e));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> chooseTime(String key) async {
    final pieces = textValue(values[key]).split(':');
    final t = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(
        hour: int.tryParse(pieces.first) ?? 10,
        minute: int.tryParse(pieces.last) ?? 0,
      ),
    );
    if (t != null && mounted) {
      setState(
        () => values[key] =
            '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}',
      );
    }
  }

  @override
  Widget build(BuildContext context) => AppScreen(
    title: '复习安排',
    subtitle: '每周一次，按已有题目安排约十分钟',
    reserveBottomNavigation: false,
    onBack: () => learningBack(context),
    children: [
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('每周安排短复习'),
        subtitle: const Text('关闭不会删除历史记录'),
        value: values['enabled'] == true,
        onChanged: busy ? null : (v) => setState(() => values['enabled'] = v),
      ),
      SegmentedButton<int>(
        segments: const [
          ButtonSegment(value: 6, label: Text('周六')),
          ButtonSegment(value: 7, label: Text('周日')),
        ],
        selected: {number(values['weekday'])},
        onSelectionChanged: busy
            ? null
            : (v) => setState(() => values['weekday'] = v.first),
      ),
      ListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('预约时间'),
        trailing: Text(textValue(values['time'])),
        onTap: busy ? null : () => chooseTime('time'),
      ),
      Text('时区：${textValue(values['timezone'])}'),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('温和提醒'),
        subtitle: const Text('每天最多两次，忙碌时可以延后'),
        value: values['reminderEnabled'] == true,
        onChanged: busy
            ? null
            : (v) => setState(() => values['reminderEnabled'] = v),
      ),
      DropdownButtonFormField<int>(
        initialValue: number(values['dailyReminderLimit']),
        decoration: const InputDecoration(labelText: '每日提醒上限'),
        items: [
          for (final n in [0, 1, 2])
            DropdownMenuItem(value: n, child: Text('$n 次')),
        ],
        onChanged: busy
            ? null
            : (v) => setState(() => values['dailyReminderLimit'] = v),
      ),
      ListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('允许提醒的开始时间'),
        trailing: Text(textValue(values['allowedStart'])),
        onTap: busy ? null : () => chooseTime('allowedStart'),
      ),
      ListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('允许提醒的结束时间'),
        trailing: Text(textValue(values['allowedEnd'])),
        onTap: busy ? null : () => chooseTime('allowedEnd'),
      ),
      ListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('暂时暂停'),
        subtitle: Text(
          values['pausedUntil'] == null
              ? '未暂停'
              : '暂停至 ${values['pausedUntil']}（含当天）',
        ),
        trailing: values['pausedUntil'] == null
            ? const Icon(Icons.calendar_month_outlined)
            : TextButton(
                onPressed: busy
                    ? null
                    : () => setState(() => values['pausedUntil'] = null),
                child: const Text('恢复'),
              ),
        onTap: busy
            ? null
            : () async {
                final now = DateTime.now();
                final d = await showDatePicker(
                  context: context,
                  initialDate: now,
                  firstDate: now,
                  lastDate: now.add(const Duration(days: 90)),
                );
                if (d != null && mounted) {
                  setState(
                    () => values['pausedUntil'] =
                        '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}',
                  );
                }
              },
      ),
      const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Text('修改默认时间用于后续安排；本周已经预约的复习，请进入详情单独改期。恢复开关后，已暂停的本周安排也请在详情中恢复。'),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(
            error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ),
      AppPrimaryButton(label: '保存安排', onTap: busy ? null : save, loading: busy),
      if (error != null)
        TextButton(
          onPressed: busy
              ? null
              : () => ref.invalidate(reviewPreferencesProvider(widget.childId)),
          child: const Text('重新读取最新安排'),
        ),
    ],
  );
}
