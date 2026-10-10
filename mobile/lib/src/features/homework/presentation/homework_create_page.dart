import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import '../../learning_review/application/learning_review_repository.dart';
import '../../learning_review/presentation/learning_support_widgets.dart';
import '../application/homework_repository.dart';

class HomeworkCreatePage extends ConsumerStatefulWidget {
  const HomeworkCreatePage({required this.childId, super.key});
  final String childId;
  @override
  ConsumerState<HomeworkCreatePage> createState() => _HomeworkCreatePageState();
}

class _HomeworkCreatePageState extends ConsumerState<HomeworkCreatePage> {
  final title = TextEditingController();
  String subject = 'math';
  String analysisKind = 'questions';
  bool consent = false, busy = false;
  String? error;
  final requestId = learningRequestId();
  @override
  void dispose() {
    title.dispose();
    super.dispose();
  }

  Future<void> create() async {
    const subjectTitles = {
      'math': '数学作业',
      'chinese': '语文作业',
      'english': '英语作业',
      'science': '科学作业',
      'other': '学习作业',
    };
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final value = await ref
          .read(homeworkRepositoryProvider)
          .create(
            widget.childId,
            title: title.text.trim().isEmpty
                ? analysisKind == 'essay'
                      ? subject == 'english'
                            ? '英语作文'
                            : '语文作文'
                      : subjectTitles[subject] ?? '学习作业'
                : title.text.trim(),
            subject: subject,
            analysisKind: analysisKind,
            idempotencyKey: requestId,
          );
      ref.invalidate(homeworkListProvider(widget.childId));
      if (mounted) {
        context.pushReplacement(
          '$homeworkDetailPath/${Uri.encodeComponent(value.id)}?childId=${Uri.encodeQueryComponent(widget.childId)}',
        );
      }
    } catch (e) {
      if (mounted) setState(() => error = learningError(e));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => AppScreen(
    title: '上传作业',
    subtitle: '家长上传照片，孩子在学生端跟 AI 老师订正',
    reserveBottomNavigation: false,
    onBack: () => learningBack(context),
    children: [
      TextField(
        controller: title,
        maxLength: 80,
        enabled: !busy,
        decoration: const InputDecoration(
          labelText: '作业名称',
          hintText: '例如：周三数学练习',
        ),
      ),
      const SizedBox(height: 16),
      DropdownButtonFormField<String>(
        initialValue: subject,
        decoration: const InputDecoration(labelText: '学科'),
        items: const [
          DropdownMenuItem(value: 'math', child: Text('数学')),
          DropdownMenuItem(value: 'chinese', child: Text('语文')),
          DropdownMenuItem(value: 'english', child: Text('英语')),
          DropdownMenuItem(value: 'science', child: Text('科学')),
          DropdownMenuItem(value: 'other', child: Text('其他学科')),
        ],
        onChanged: busy
            ? null
            : (v) => setState(() {
                subject = v!;
                if (!{'chinese', 'english'}.contains(subject)) {
                  analysisKind = 'questions';
                }
              }),
      ),
      if ({'chinese', 'english'}.contains(subject)) ...[
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          key: ValueKey(analysisKind),
          initialValue: analysisKind,
          decoration: const InputDecoration(labelText: '分析内容'),
          items: const [
            DropdownMenuItem(value: 'questions', child: Text('作业 / 试卷题目')),
            DropdownMenuItem(value: 'essay', child: Text('作文修改建议')),
          ],
          onChanged: busy ? null : (v) => setState(() => analysisKind = v!),
        ),
      ],
      Padding(
        padding: EdgeInsets.symmetric(vertical: 20),
        child: Text(
          analysisKind == 'essay'
              ? '上传作文照片后，查看原句和修改建议。孩子也能在学生端请 AI 老师对照原作文讲解、用语音继续提问。\n\n作文建议不作为考试分数或独立掌握成绩；多页逐页分析，保留每页原图。'
              : '上传并分析后，题目会同步到学生端“作业与试卷”。孩子可以看原题、听 AI 老师讲解，并继续用语音提问；家长无需输入正确答案。\n\nAI 老师会对照原图讲解，不需要家长填写题目或核对答案。看不清的题目不强行判错，照片不清晰时才需要补拍。报告会区分老师指导和独立掌握。',
          style: TextStyle(color: AppColors.mutedStrong, height: 1.7),
        ),
      ),
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        value: consent,
        onChanged: busy ? null : (v) => setState(() => consent = v == true),
        title: const Text('同意分析本次上传的照片'),
        subtitle: const Text('照片将提交给所配置的 AI 批改与讲解服务，分析记录仅本家庭可查看，可随时删除该份作业。'),
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(error!, style: const TextStyle(color: AppColors.danger)),
        ),
      const SizedBox(height: 16),
      AppPrimaryButton(
        label: '创建并添加照片',
        loading: busy,
        onTap: !consent || busy ? null : create,
      ),
    ],
  );
}
