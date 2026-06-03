import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/features/mvp/domain/mvp_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class TaskDetailScreen extends ConsumerWidget {
  const TaskDetailScreen({required this.taskId, super.key});

  final String taskId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final task = snapshot.taskById(taskId);

    return MiraScreen(
      title: task.title,
      subtitle: '${task.type} · ${task.timeLabel}',
      fixedHeader: true,
      backLabel: '返回任务',
      onBack: () => context.go(AppRoute.tasks.path),
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 118),
      children: [
        _EvidencePanel(task: task),
        const SizedBox(height: 14),
        MiraSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionTitle('AI 判断建议'),
              const SizedBox(height: 10),
              Text(
                task.aiAdvice,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  height: 1.55,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        MiraSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionTitle('任务记录'),
              const SizedBox(height: 8),
              MiraListRow(
                icon: Icons.timer_outlined,
                title: task.durationLabel,
                subtitle: task.nextStep,
                tone: MiraListRowTone.blue,
              ),
              MiraListRow(
                icon: Icons.event_note_outlined,
                title: '家长确认',
                subtitle: task.evidence.parentDecision,
                tone: task.status == MvpTaskStatus.needsConfirmation
                    ? MiraListRowTone.amber
                    : MiraListRowTone.neutral,
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        MiraPrimaryButton(
          label: task.status == MvpTaskStatus.needsConfirmation
              ? '处理证据'
              : '查看证据',
          trailing: const MiraButtonGlyph(icon: Icons.fact_check_outlined),
          onTap: () => _showEvidenceSheet(context, task),
        ),
        const SizedBox(height: 10),
        MiraSecondaryButton(
          label: '提醒孩子收尾',
          trailing: const Icon(Icons.volume_up_outlined, size: 18),
          onTap: () => _showToast(context, '已发送温和提醒'),
        ),
      ],
    );
  }
}

class _EvidencePanel extends StatelessWidget {
  const _EvidencePanel({required this.task});

  final MvpTask task;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              StatusChip(label: task.status.label, tone: task.status.tone),
              const Spacer(),
              Text(
                '+${task.points} 分',
                style: const TextStyle(
                  color: Color(0xFFFDBA74),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(16),
            ),
            child: SizedBox(
              height: 132,
              width: double.infinity,
              child: Center(
                child: Icon(
                  Icons.image_outlined,
                  color: Colors.white.withValues(alpha: 0.72),
                  size: 42,
                ),
              ),
            ),
          ),
          const SizedBox(height: 14),
          Text(
            task.evidence.summary,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.78),
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.55,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _EvidenceMetric(
                label: '置信度',
                value: task.evidence.confidenceLabel,
              ),
              const SizedBox(width: 8),
              _EvidenceMetric(
                label: '离座',
                value: '${task.evidence.leaveSeatCount} 次',
              ),
              const SizedBox(width: 8),
              _EvidenceMetric(label: '结果', value: task.evidence.parentDecision),
            ],
          ),
        ],
      ),
    );
  }
}

class _EvidenceMetric extends StatelessWidget {
  const _EvidenceMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(13),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.58),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 16,
        fontWeight: FontWeight.w800,
        letterSpacing: 0,
      ),
    );
  }
}

void _showEvidenceSheet(BuildContext context, MvpTask task) {
  showModalBottomSheet<void>(
    context: context,
    useRootNavigator: true,
    showDragHandle: true,
    backgroundColor: AppColors.appBackgroundWarm,
    builder: (context) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '处理任务证据',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              task.evidence.summary,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
              ),
            ),
            const SizedBox(height: 16),
            MiraListRow(
              icon: Icons.check_circle_outline,
              title: '确认完成',
              subtitle: '进入日报和奖励流水',
              tone: MiraListRowTone.green,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已确认任务完成');
              },
            ),
            MiraListRow(
              icon: Icons.rule_outlined,
              title: '改为部分完成',
              subtitle: '减少积分并记录家长改判',
              tone: MiraListRowTone.amber,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已改为部分完成');
              },
            ),
            MiraListRow(
              icon: Icons.report_outlined,
              title: '标记误判',
              subtitle: '不会进入孩子奖励记录',
              tone: MiraListRowTone.red,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已标记为 AI 误判');
              },
            ),
          ],
        ),
      );
    },
  );
}

void _showToast(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.ink,
      ),
    );
}
