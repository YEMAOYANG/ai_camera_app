import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import '../application/learning_review_repository.dart';
import '../domain/learning_review_models.dart';
import 'learning_support_widgets.dart';

class ReviewDetailPage extends ConsumerStatefulWidget {
  const ReviewDetailPage({
    required this.childId,
    required this.reviewId,
    super.key,
  });
  final String childId, reviewId;
  @override
  ConsumerState<ReviewDetailPage> createState() => _ReviewDetailPageState();
}

class _ReviewDetailPageState extends ConsumerState<ReviewDetailPage> {
  bool busy = false;
  String? error;
  String? requestId;
  String? actionSignature;
  ({String childId, String reviewId}) get keyValue =>
      (childId: widget.childId, reviewId: widget.reviewId);
  Future<void> act(ReviewRun run, String action) async {
    DateTime? when;
    if (action == 'reschedule') {
      when = await pickLearningAppointment(context, run.scheduledAt);
      if (when == null) return;
    }
    if (!mounted) return;
    if (action == 'skip' &&
        !await confirmLearningAction(
          context,
          title: '跳过这次复习？',
          message: '会记录为本周未参加，不会记作答错，也不影响已有学习成果。',
          action: '跳过本周',
        )) {
      return;
    }
    if (!mounted) return;
    final signature =
        '$action:${run.appointmentRevision}:${when?.millisecondsSinceEpoch}';
    if (signature != actionSignature) {
      actionSignature = signature;
      requestId = learningRequestId();
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await ref
          .read(learningReviewRepositoryProvider)
          .schedule(
            widget.childId,
            run,
            action,
            scheduledAt: when,
            requestId: requestId!,
          );
      ref.invalidate(reviewDetailProvider(keyValue));
      ref.invalidate(reviewListProvider(widget.childId));
      if (mounted) showAppToast(context, '安排已更新', tone: AppToastTone.success);
    } catch (e) {
      if (mounted) setState(() => error = learningError(e));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final value = ref.watch(reviewDetailProvider(keyValue));
    return AppScreen(
      title: '周末复习详情',
      onBack: () => learningBack(context),
      reserveBottomNavigation: false,
      onRefresh: () async {
        ref.invalidate(reviewDetailProvider(keyValue));
      },
      children: [
        value.when(
          loading: () => const LearningLoading(),
          error: (e, _) => LearningError(
            e,
            () => ref.invalidate(reviewDetailProvider(keyValue)),
          ),
          data: (detail) {
            final run = detail.run, r = detail.report;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  run.title,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text('${run.statusLabel} · ${learningDate(run.scheduledAt)}'),
                Text('${run.questionCount} 题 · 约 ${run.estimatedMinutes} 分钟'),
                for (final note in (run.coverage['notes'] as List? ?? []))
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      textValue(note),
                      style: const TextStyle(color: AppColors.mutedStrong),
                    ),
                  ),
                if (run.canSchedule) ...[
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      OutlinedButton(
                        onPressed: busy ? null : () => act(run, 'reschedule'),
                        child: const Text('改期'),
                      ),
                      OutlinedButton(
                        onPressed: busy
                            ? null
                            : () => act(
                                run,
                                run.status == 'paused' ? 'resume' : 'pause',
                              ),
                        child: Text(run.status == 'paused' ? '恢复' : '暂停'),
                      ),
                      TextButton(
                        onPressed: busy ? null : () => act(run, 'skip'),
                        child: const Text('本周跳过'),
                      ),
                    ],
                  ),
                ],
                if (busy) const LinearProgressIndicator(),
                if (error != null)
                  Text(error!, style: const TextStyle(color: AppColors.danger)),
                const LearningHeading('具体学习记录'),
                ReviewReportEvidence(report: r),
                const SizedBox(height: 16),
                AppSecondaryButton(
                  label: '刷新进度',
                  onTap: busy
                      ? null
                      : () => ref.invalidate(reviewDetailProvider(keyValue)),
                ),
              ],
            );
          },
        ),
      ],
    );
  }
}
