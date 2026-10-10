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
                if (r['notParticipated'] == true)
                  const Text('孩子尚未参加。没有作答记录不代表不会。')
                else
                  Text(
                    '已答 ${number(r['answeredCount'])} / ${number(r['totalQuestions'])} 题\n新题独立答对 ${number(r['independentFirstCorrect'])} / ${number(r['independentFirstCount'])} 题\n原题复练 ${number(r['repeatedPracticeCount'])} 题',
                    style: const TextStyle(height: 1.8),
                  ),
                if (number(r['withdrawnCount']) > 0)
                  Text('${number(r['withdrawnCount'])} 题因原始记录更正或删除已撤回，不参与评估。'),
                for (final item in jsonList(r['items']))
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(textValue(item['knowledgeLabel'])),
                    subtitle: Text(
                      '${item['correct'] == true ? '答对' : '需要复习'} · ${item['independent'] == true
                          ? '独立完成'
                          : item['hintUsed'] == true
                          ? '使用提示'
                          : '非独立新题证据'}',
                    ),
                    childrenPadding: const EdgeInsets.only(bottom: 16),
                    expandedCrossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(textValue(item['prompt'])),
                      Text(
                        '孩子的作答：${textValue(item['answerLabel'] ?? learningAnswerLabel(item['answer'], item['options']))}',
                      ),
                      Text(
                        '参考答案：${textValue(item['correctAnswerLabel'] ?? learningAnswerLabel(item['correctAnswer'], item['options']))}',
                      ),
                      Text(textValue(item['explanation'])),
                      if (item['evidenceMode'] == 'repeated_practice')
                        const Text('原题再次练习，不计为新的独立掌握证据。'),
                    ],
                  ),
                const SizedBox(height: 12),
                Text(
                  textValue(r['assessmentScope']),
                  style: const TextStyle(
                    color: AppColors.mutedStrong,
                    height: 1.6,
                  ),
                ),
                Text(
                  textValue(r['parentAction']),
                  style: const TextStyle(height: 1.6),
                ),
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
