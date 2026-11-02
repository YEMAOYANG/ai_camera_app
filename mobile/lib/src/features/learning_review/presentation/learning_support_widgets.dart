import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import '../application/learning_review_repository.dart';
import '../domain/learning_review_models.dart';

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

/// The report hub and review detail share the same bounded evidence wording.
class ReviewReportEvidence extends StatelessWidget {
  const ReviewReportEvidence({required this.report, super.key});
  final Json report;

  @override
  Widget build(BuildContext context) {
    final items = jsonList(
      report['items'],
    ).map(ReviewEvidenceItem.new).toList();
    const secondary = TextStyle(color: AppColors.mutedStrong, height: 1.6);
    final independent = number(report['independentFirstCount']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (report.isEmpty)
          const Text('参加测评后，这里会显示具体作答记录。', style: secondary)
        else if (report['notParticipated'] == true)
          const Text('孩子尚未参加。没有作答记录不代表不会。')
        else ...[
          Text(
            '已答 ${number(report['answeredCount'])} / ${number(report['totalQuestions'])} 题',
          ),
          Text(
            independent > 0
                ? '首次独立答对 ${number(report['independentFirstCorrect'])} / $independent 题'
                : '暂无可确认的首次独立作答证据。',
            style: secondary,
          ),
          if (number(report['repeatedPracticeCount']) > 0)
            Text(
              '原题复练 ${number(report['repeatedPracticeCount'])} 题',
              style: secondary,
            ),
        ],
        if (number(report['withdrawnCount']) > 0)
          Text(
            '${number(report['withdrawnCount'])} 题因原始记录更正或删除已撤回，不参与评估。',
            style: secondary,
          ),
        if (textValue(report['assessmentScope']).isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(textValue(report['assessmentScope']), style: secondary),
          ),
        if (items.any((item) => item.assessmentLabel.isNotEmpty))
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text('口语、发音、背诵和纸笔书写未直接测评，不判断是否掌握。', style: secondary),
          ),
        for (final item in items)
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            title: Text(item.goal),
            subtitle: Text(
              [
                item.resultLabel,
                item.supportLabel,
                if (item.assessmentLabel.isNotEmpty) item.assessmentLabel,
                if (item.target.isNotEmpty) '目标字音：${item.target}',
              ].join(' · '),
            ),
            childrenPadding: const EdgeInsets.only(bottom: 16),
            expandedCrossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (item.sourceTitle.isNotEmpty) Text('对应课件：${item.sourceTitle}'),
              Text(textValue(item.data['prompt'])),
              Text(
                '孩子的作答：${textValue(
                      item.data['answerLabel'] ??
                          learningAnswerLabel(
                            item.data['answer'],
                            item.data['options'],
                          ),
                    )}',
              ),
              Text(
                '参考答案：${textValue(
                      item.data['correctAnswerLabel'] ??
                          learningAnswerLabel(
                            item.data['correctAnswer'],
                            item.data['options'],
                          ),
                    )}',
              ),
              if (textValue(item.data['explanation']).isNotEmpty)
                Text(textValue(item.data['explanation'])),
              if (item.claimTexts('observed').isNotEmpty)
                Text(
                  '本次观察：${item.claimTexts('observed').join('；')}',
                  style: secondary,
                ),
              if (item.claimTexts('supports').isNotEmpty)
                Text(
                  '本题可记录：${item.claimTexts('supports').join('；')}',
                  style: secondary,
                ),
              if (item.claimTexts('doesNotSupport').isNotEmpty)
                Text(
                  '尚不能据此判断：${item.claimTexts('doesNotSupport').join('；')}',
                  style: secondary,
                ),
              if (item.repeated)
                const Text('原题再次练习，不计为新的独立表现。', style: secondary),
            ],
          ),
        if (textValue(report['parentAction']).isNotEmpty)
          Text(textValue(report['parentAction']), style: secondary),
      ],
    );
  }
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
