import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/report_learning_models.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';

/// Optional self-report. Never infer caregiver effort from the child's score.
class LearningCoachingForm extends ConsumerStatefulWidget {
  const LearningCoachingForm({super.key, required this.lesson});
  final ReportLearningLesson lesson;

  @override
  ConsumerState<LearningCoachingForm> createState() =>
      _LearningCoachingFormState();
}

class _LearningCoachingFormState extends ConsumerState<LearningCoachingForm> {
  final _minutes = TextEditingController();
  final _usual = TextEditingController();
  String _reason = 'none';
  int _revision = 0;
  int? _recordedMinutes;
  bool _busy = false;
  String? _message;
  bool _success = false;

  static const _reasons = {
    'none': '没有介入',
    'navigation': '帮忙操作界面',
    'understanding': '解释题意',
    'technical': '处理声音或连接',
    'company': '陪伴鼓励',
    'other': '其他帮助',
  };

  @override
  void initState() {
    super.initState();
    _load(widget.lesson.coaching);
  }

  void _load(Map<String, dynamic> record) {
    _minutes.text = record['minutes']?.toString() ?? '';
    _usual.text = record['usualMinutes']?.toString() ?? '';
    _reason = _reasons.containsKey(record['reason'])
        ? record['reason'] as String
        : 'none';
    _revision = (record['revision'] as num?)?.toInt() ?? 0;
    _recordedMinutes = (record['minutes'] as num?)?.toInt();
  }

  @override
  void dispose() {
    _minutes.dispose();
    _usual.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final record = await ref
          .read(profileRepositoryProvider)
          .learningCoaching(widget.lesson.sessionId, widget.lesson.recordDate);
      if (!mounted) {
        return;
      }
      setState(() {
        _load(record);
        _message = '已读取最新记录，请核对后保存。';
        _success = true;
      });
    } catch (_) {
      if (mounted) {
        setState(() {
          _message = '暂时没取到记录，请稍后重试。';
          _success = false;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _save() async {
    final minutes = int.tryParse(_minutes.text);
    final usual = _usual.text.isEmpty ? null : int.tryParse(_usual.text);
    if (minutes == null ||
        minutes < 0 ||
        minutes > 180 ||
        (_usual.text.isNotEmpty &&
            (usual == null || usual < 0 || usual > 180)) ||
        (minutes > 0 && _reason == 'none')) {
      setState(() {
        _message = '请填写 0—180 分钟；有辅导时选一下主要原因。';
        _success = false;
      });
      return;
    }
    final body = <String, dynamic>{
      'recordDate': widget.lesson.recordDate,
      'minutes': minutes,
      'usualMinutes': usual,
      'reason': minutes == 0 ? 'none' : _reason,
      'revision': _revision,
    };
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final record = await ref
          .read(profileRepositoryProvider)
          .saveLearningCoaching(widget.lesson.sessionId, body);
      if (!mounted) {
        return;
      }
      setState(() {
        _load(record);
        _message = '已记录。这不会改变孩子的成绩。';
        _success = true;
      });
      for (final provider in [dailyReportProvider, weeklyReportProvider]) {
        // Avoid cancelling a report request already in flight.
        if (!ref.read(provider).isLoading) {
          ref.invalidate(provider);
        }
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _message = error is ProfileException
              ? error.message
              : '保存结果未确认，请先读取最新记录。';
          _success = false;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canManage =
        ref.watch(profileSummaryProvider).asData?.value.can('manage_tasks') ??
        false;
    if (!canManage) {
      return Text(
        widget.lesson.coaching.isEmpty
            ? '辅导用时尚未记录'
            : '家长自报辅导 ${widget.lesson.coaching['minutes']} 分钟',
      );
    }
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text(
        _recordedMinutes == null ? '记录辅导用时（自愿）' : '辅导用时 · $_recordedMinutes 分钟',
      ),
      subtitle: const Text('没有记录不会按 0 分钟计算'),
      children: [
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '只记您实际帮忙的时间，不是孩子的上课时长。',
              style: TextStyle(color: AppColors.mutedStrong),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final value in [0, 2, 5, 10])
                  ChoiceChip(
                    labelStyle: const TextStyle(
                      fontFamily: AppTypography.systemFont,
                    ),
                    label: Text(value == 0 ? '没有辅导' : '$value 分钟'),
                    selected: _minutes.text == '$value',
                    onSelected: _busy
                        ? null
                        : (_) => setState(() {
                            _minutes.text = '$value';
                            _reason = value == 0 ? 'none' : 'understanding';
                          }),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _minutes,
              enabled: !_busy,
              keyboardType: TextInputType.number,
              onChanged: (_) => setState(() {}),
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(3),
              ],
              decoration: const InputDecoration(
                labelText: '本次辅导分钟数',
                suffixText: '分钟',
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _reason,
              key: ValueKey(_reason),
              isExpanded: true,
              decoration: const InputDecoration(labelText: '主要介入原因'),
              items: [
                for (final entry in _reasons.entries)
                  DropdownMenuItem(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: _busy
                  ? null
                  : (value) => setState(() => _reason = value ?? 'none'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _usual,
              enabled: !_busy,
              keyboardType: TextInputType.number,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(3),
              ],
              decoration: const InputDecoration(
                labelText: '以往相近任务用时（选填）',
                suffixText: '分钟',
              ),
            ),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                '比较来自您的回忆，仅供观察变化，不作为学习效果证明。',
                style: TextStyle(color: AppColors.mutedStrong, fontSize: 12),
              ),
            ),
            if (_message != null)
              Semantics(
                liveRegion: true,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    _message!,
                    style: TextStyle(
                      color: _success ? AppColors.brandSage : AppColors.danger,
                    ),
                  ),
                ),
              ),
            FilledButton(
              onPressed: _busy ? null : _save,
              child: Text(
                _busy ? '正在保存…' : '保存记录',
                style: const TextStyle(fontFamily: AppTypography.systemFont),
              ),
            ),
            TextButton(
              onPressed: _busy ? null : _reload,
              child: const Text(
                '读取最新记录',
                style: TextStyle(fontFamily: AppTypography.systemFont),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
