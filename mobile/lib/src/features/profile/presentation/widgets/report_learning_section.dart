import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/profile/domain/report_learning_models.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/features/profile/presentation/widgets/learning_coaching_form.dart';

class ReportLearningSection extends StatelessWidget {
  const ReportLearningSection({super.key, required this.learning});

  final ReportLearningSummary learning;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.all(16),
      child: Material(
        color: Colors.transparent,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.auto_stories_outlined,
                  color: AppColors.brandDeep,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    '课程学习 · ${learning.lessonCount} 节',
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                      color: AppColors.ink,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              learning.needsSupportCount > 0
                  ? '${learning.needsSupportCount} 节需要您留意，展开查看具体帮助方式。'
                  : '先看孩子的独立表现，再决定是否需要辅导。',
              style: _secondary,
            ),
            if (learning.reviewCount > 0)
              Text('本期完成 ${learning.reviewCount} 次间隔复习', style: _secondary),
            if ((learning.coachingSummary['recordedSessions'] as num? ?? 0) >
                0) ...[
              const SizedBox(height: 8),
              Text(
                '家长自报辅导 ${learning.coachingSummary['totalMinutes']} 分钟 · ${learning.coachingSummary['recordedSessions']} 次记录',
                style: _body,
              ),
              if ((learning.coachingSummary['comparisonCount'] as num? ?? 0) >
                  0)
                Text(
                  '可对比的 ${learning.coachingSummary['comparisonCount']} 次：以往 ${learning.coachingSummary['usualMinutes']} 分钟，本次 ${learning.coachingSummary['currentComparisonMinutes']} 分钟。',
                  style: _secondary,
                ),
              const Text('未记录的课次不计入，以上来自家长自报。', style: _secondary),
            ],
            for (var index = 0; index < learning.lessons.length; index++) ...[
              const Divider(height: 24, color: AppColors.border),
              _LessonEvidence(lesson: learning.lessons[index]),
            ],
          ],
        ),
      ),
    );
  }
}

const _secondary = TextStyle(
  fontSize: 13,
  height: 1.5,
  color: AppColors.mutedStrong,
);
const _body = TextStyle(fontSize: 14, height: 1.5, color: AppColors.ink);

class _LessonEvidence extends StatelessWidget {
  const _LessonEvidence({required this.lesson});
  final ReportLearningLesson lesson;

  @override
  Widget build(BuildContext context) {
    final due = lesson.reviewDueAt;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '${lesson.childName.isEmpty ? '' : '${lesson.childName} · '}${lesson.title}',
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: AppColors.ink,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          lesson.statusLabel,
          style: _body.copyWith(
            color: lesson.needsSupport ? AppColors.danger : AppColors.brandSage,
          ),
        ),
        if (lesson.verificationLabel case final label?)
          Text(label, style: _body),
        if (lesson.parentSupport.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            '只帮这一步 · ${lesson.parentSupport['focus']}',
            style: _body.copyWith(fontWeight: FontWeight.w600),
          ),
          Text('${lesson.parentSupport['action']}', style: _body),
          const SizedBox(height: 4),
          Text('${lesson.parentSupport['handBack']}', style: _secondary),
        ] else if (lesson.nextStep.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(lesson.nextStep, style: _body),
        ],
        if (due != null) ...[
          const SizedBox(height: 6),
          Text(
            '安排复习：${due.month}月${due.day}日 ${due.hour.toString().padLeft(2, '0')}:${due.minute.toString().padLeft(2, '0')}（北京时间）',
            style: _secondary,
          ),
        ],
        ExpansionTile(
          key: ValueKey(
            'learning-evidence-${lesson.childName}-${lesson.title}-${lesson.recordDate}',
          ),
          tilePadding: EdgeInsets.zero,
          childrenPadding: const EdgeInsets.only(bottom: 8),
          initiallyExpanded: lesson.needsSupport,
          title: const Text('查看学习依据', style: _secondary),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${lesson.recordDate} · ${lesson.evidenceLabel}',
                    style: _secondary,
                  ),
                  if (lesson.baselineLabel case final label?)
                    Text(label, style: _body),
                  if (lesson.helpLabel case final label?)
                    Text(label, style: _secondary),
                  if (lesson.remaining.isNotEmpty)
                    Text(
                      '待巩固或继续验证：${lesson.remaining.join('、')}',
                      style: _body,
                    ),
                  for (final diagnosis in lesson.diagnoses)
                    Text(diagnosis, style: _secondary),
                  if (lesson.pictureSupported) ...[
                    const SizedBox(height: 8),
                    const Text('看图理解不等于独立识字，本课未评价朗读和书写。', style: _secondary),
                  ],
                ],
              ),
            ),
          ],
        ),
        if (lesson.sessionId.isNotEmpty)
          LearningCoachingForm(
            key: ValueKey(
              '${lesson.sessionId}-${lesson.recordDate}-${lesson.coaching['revision'] ?? 0}',
            ),
            lesson: lesson,
          ),
      ],
    );
  }
}
