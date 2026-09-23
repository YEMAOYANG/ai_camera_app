import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/application/learning_observation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_observation_models.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';

class ParentLearningObservationEntry extends StatelessWidget {
  const ParentLearningObservationEntry({
    required this.childId,
    required this.childName,
    super.key,
  });
  final String childId;
  final String childName;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: TextButton.icon(
        key: const ValueKey('parentLearningObservationEntry'),
        onPressed: () => showAppBottomSheet<void>(
          context: context,
          maxHeightFactor: 0.84,
          child: ParentLearningObservationSheet(
            childId: childId,
            childName: childName,
          ),
        ),
        icon: const Icon(Icons.fact_check_outlined, size: 19),
        label: const Text('确认孩子的学习表现'),
      ),
    );
  }
}

class ParentLearningObservationSheet extends ConsumerStatefulWidget {
  const ParentLearningObservationSheet({
    required this.childId,
    required this.childName,
    super.key,
  });
  final String childId;
  final String childName;

  @override
  ConsumerState<ParentLearningObservationSheet> createState() =>
      _ParentLearningObservationSheetState();
}

class _ParentLearningObservationSheetState
    extends ConsumerState<ParentLearningObservationSheet> {
  String? _selectedId;
  String? _error;
  String? _success;
  bool _submitting = false;

  void _refresh() {
    setState(() {
      _error = null;
      _selectedId = null;
    });
    ref.invalidate(pendingLearningObservationsProvider(widget.childId));
  }

  Future<void> _confirm(ParentObservationLesson lesson, bool confirmed) async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await ref
          .read(parentObservationRepositoryProvider)
          .confirm(
            childId: widget.childId,
            lesson: lesson,
            confirmed: confirmed,
          );
      if (!mounted) return;
      ref.invalidate(pendingLearningObservationsProvider(widget.childId));
      setState(
        () => _success = confirmed
            ? '已记录为能独立完成，学习路线会按掌握情况继续。'
            : '已记录为还需练习。练习后可以重新观察并确认。',
      );
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is ParentObservationException
              ? error.message
              : '确认没有完成，请稍后重试',
        );
      }
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pending = ref.watch(
      pendingLearningObservationsProvider(widget.childId),
    );
    final lessons = pending.asData?.value ?? const <ParentObservationLesson>[];
    final selected =
        lessons.where((lesson) => lesson.lessonId == _selectedId).firstOrNull ??
        (lessons.length == 1 ? lessons.first : null);
    Widget content;
    Widget? footer;
    if (_success != null) {
      content = _SheetNotice(icon: Icons.task_alt, text: _success!);
      footer = AppSheetPrimaryButton(
        label: '完成',
        onTap: () => Navigator.of(context).pop(),
      );
    } else if (pending.isLoading) {
      content = const Padding(
        padding: EdgeInsets.symmetric(vertical: 40),
        child: Center(child: CircularProgressIndicator()),
      );
    } else if (pending.hasError) {
      content = _SheetNotice(
        icon: Icons.wifi_off_outlined,
        text: pending.error is ParentObservationException
            ? (pending.error as ParentObservationException).message
            : '暂时无法读取学习表现',
      );
      footer = AppSheetSecondaryButton(label: '重新获取', onTap: _refresh);
    } else if (lessons.isEmpty) {
      content = const _SheetNotice(
        icon: Icons.menu_book_outlined,
        text: '暂时没有需要确认的课程。朗读、书写等课程完成后，会出现在这里。',
      );
      footer = AppSheetSecondaryButton(
        label: '关闭',
        onTap: () => Navigator.of(context).pop(),
      );
    } else if (selected == null) {
      content = Column(
        children: [
          for (final lesson in lessons)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(lesson.title),
              subtitle: Text('${lesson.subjectLabel} · ${lesson.unitTitle}'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => setState(() {
                _selectedId = lesson.lessonId;
                _error = null;
              }),
            ),
        ],
      );
    } else {
      content = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (lessons.length > 1)
            TextButton(
              onPressed: _submitting
                  ? null
                  : () => setState(() => _selectedId = null),
              child: const Text('返回待确认课程'),
            ),
          Text(selected.title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 6),
          Text(
            '${selected.subjectLabel} · ${selected.unitTitle}',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 22),
          Text('请按本课要求观察', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          for (final (index, criterion) in selected.criteria.indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${index + 1}. ',
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                  Expanded(
                    child: Text(
                      criterion,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                  ),
                ],
              ),
            ),
          if (_error != null) ...[
            Text(_error!, style: const TextStyle(color: AppColors.danger)),
            TextButton(
              onPressed: _submitting ? null : _refresh,
              child: const Text('刷新确认状态'),
            ),
          ],
        ],
      );
      footer = Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(
            label: '能独立完成',
            loading: _submitting,
            onTap: _submitting ? null : () => _confirm(selected, true),
          ),
          const SizedBox(height: 10),
          AppSheetSecondaryButton(
            label: '还需练习',
            onTap: _submitting ? null : () => _confirm(selected, false),
          ),
        ],
      );
    }
    return AppBottomSheetBody(
      title: '确认学习表现',
      subtitle: '${widget.childName} · 只记录本课实际表现',
      footer: footer,
      child: content,
    );
  }
}

class _SheetNotice extends StatelessWidget {
  const _SheetNotice({required this.icon, required this.text});
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 32, color: AppColors.brandSage),
        const SizedBox(height: 16),
        Text(text, style: Theme.of(context).textTheme.bodyLarge),
      ],
    ),
  );
}
