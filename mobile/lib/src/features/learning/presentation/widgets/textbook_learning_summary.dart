import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/textbook_cover.dart';

/// The same school books and server-owned lesson status on home and profile.
class TextbookLearningSummary extends ConsumerWidget {
  const TextbookLearningSummary({
    super.key,
    required this.childId,
    this.onManage,
    this.disabledHint,
  });
  final String childId;
  final VoidCallback? onManage;
  final String? disabledHint;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final provider = schoolTextbooksProvider(childId);
    final catalog = ref.watch(provider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text(
                '教材与课程',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: AppColors.ink,
                ),
              ),
            ),
            TextButton(
              onPressed: onManage,
              style: TextButton.styleFrom(
                foregroundColor: AppColors.brandDeep,
                minimumSize: const Size(44, 44),
                padding: const EdgeInsets.only(left: 12),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '选教材',
                    style: TextStyle(
                      fontSize: 13,
                      fontFamily: AppTypography.systemFont,
                    ),
                  ),
                  SizedBox(width: 2),
                  Icon(Icons.chevron_right, size: 17),
                ],
              ),
            ),
          ],
        ),
        if (disabledHint != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              disabledHint!,
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.mutedStrong,
              ),
            ),
          ),
        AppListRow(
          icon: Icons.assignment_outlined,
          title: '作业检查与周末复习',
          subtitle: '查看具体错题和学习进步',
          onTap: () => context.push(
            '$learningCenterPath?childId=${Uri.encodeQueryComponent(childId)}',
          ),
          trailing: const Icon(Icons.chevron_right),
        ),
        catalog.when(
          skipLoadingOnRefresh: false,
          loading: () => const _BooksLoading(),
          error: (error, _) => Row(
            children: [
              const Expanded(
                child: Text(
                  '课本状态暂时无法读取',
                  style: TextStyle(fontSize: 13, color: AppColors.mutedStrong),
                ),
              ),
              TextButton(
                onPressed: () => ref.invalidate(provider),
                child: const Text(
                  '重试',
                  style: TextStyle(fontFamily: AppTypography.systemFont),
                ),
              ),
            ],
          ),
          data: (data) => Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                data.termLabel,
                style: const TextStyle(
                  fontSize: 12,
                  color: AppColors.mutedStrong,
                ),
              ),
              for (final journey in data.journeys) ...[
                const SizedBox(height: 12),
                Semantics(
                  label: '${journey.title}学习结果',
                  child: Material(
                    type: MaterialType.transparency,
                    child: ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      childrenPadding: const EdgeInsets.only(bottom: 12),
                      initiallyExpanded: journey.parentNeeded,
                      title: Text(
                        '${journey.title} · ${journey.label}',
                        style: const TextStyle(
                          fontSize: 14,
                          color: AppColors.ink,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      subtitle: Text(
                        journey.nextStep,
                        style: const TextStyle(
                          fontSize: 12,
                          height: 1.5,
                          color: AppColors.mutedStrong,
                        ),
                      ),
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: Text(
                            '前测独立 ${journey.before}/6 → 本轮新情境独立 ${journey.verified}/6',
                            style: const TextStyle(
                              fontSize: 13,
                              color: AppColors.ink,
                            ),
                          ),
                        ),
                        if (journey.parentNeeded &&
                            journey.remaining.isNotEmpty)
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              '仍需练习：${journey.remaining.join('、')}',
                              style: const TextStyle(
                                fontSize: 13,
                                color: AppColors.mutedStrong,
                              ),
                            ),
                          ),
                        for (final diagnosis in journey.diagnoses)
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              diagnosis,
                              style: const TextStyle(
                                fontSize: 12,
                                height: 1.5,
                                color: AppColors.mutedStrong,
                              ),
                            ),
                          ),
                        if (journey.reviewDueAt case final due?)
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              '已安排短复习：${due.month}月${due.day}日 ${due.hour.toString().padLeft(2, '0')}:${due.minute.toString().padLeft(2, '0')}',
                              style: const TextStyle(
                                fontSize: 12,
                                height: 1.5,
                                color: AppColors.mutedStrong,
                              ),
                            ),
                          ),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton(
                            onPressed: () => ref.invalidate(provider),
                            child: const Text('刷新学习结果'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              LayoutBuilder(
                builder: (context, constraints) {
                  final columns =
                      constraints.maxWidth < 310 ||
                          MediaQuery.textScalerOf(context).scale(14) > 19
                      ? 1
                      : 2;
                  return Wrap(
                    spacing: 24,
                    runSpacing: 18,
                    children: [
                      for (final subject in const [
                        ('chinese', '语文'),
                        ('math', '数学'),
                        ('english', '英语'),
                        ('science', '科学'),
                      ])
                        SizedBox(
                          width:
                              (constraints.maxWidth - (columns - 1) * 24) /
                              columns,
                          child: _SubjectBook(
                            subject: subject,
                            catalog: data,
                            onTap: onManage,
                          ),
                        ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 18),
              const Divider(height: 1, color: AppColors.border),
            ],
          ),
        ),
      ],
    );
  }
}

class _SubjectBook extends StatelessWidget {
  const _SubjectBook({
    required this.subject,
    required this.catalog,
    this.onTap,
  });
  final (String, String) subject;
  final SchoolTextbookCatalog catalog;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final book = catalog.books
        .where((book) => book.selected && book.subject == subject.$1)
        .firstOrNull;
    final unavailable = catalog.statusFor(subject.$1) == 'unavailable';
    final learning = book?.learningStatus;
    final status = book == null
        ? unavailable
              ? '本年级教材暂未收录'
              : '待选择学校教材'
        : learning != null &&
              (learning.available > 0 || learning.status == 'locked')
        ? learning.label
        : '课程待上架';
    return Semantics(
      container: true,
      button: onTap != null,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadii.card),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  TextbookCover(
                    subject: subject.$1,
                    volumeLabel: book?.volumeLabel,
                    placeholder: book == null && !unavailable,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          subject.$2,
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                            color: AppColors.ink,
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          book == null
                              ? '学校教材'
                              : '${book.versionLabel} · ${book.volumeLabel}',
                          style: const TextStyle(
                            fontSize: 12,
                            height: 1.45,
                            color: AppColors.mutedStrong,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Text(
                status,
                style: const TextStyle(
                  fontSize: 12,
                  height: 1.5,
                  color: AppColors.mutedStrong,
                ),
              ),
              if (learning != null && learning.available > 0) ...[
                const SizedBox(height: 7),
                LinearProgressIndicator(
                  value: (learning.completed / learning.available).clamp(0, 1),
                  minHeight: 3,
                  borderRadius: BorderRadius.circular(AppRadii.full),
                  color: TextbookSubjectStyle.forSubject(subject.$1).ink,
                  backgroundColor: AppColors.borderSoft,
                  semanticsLabel: '${subject.$2}已开放课程的学习进度',
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _BooksLoading extends StatelessWidget {
  const _BooksLoading();
  @override
  Widget build(BuildContext context) => Semantics(
    label: '正在读取课本状态',
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        children: [
          for (var i = 0; i < 4; i++)
            Expanded(
              child: Container(
                height: 78,
                margin: EdgeInsets.only(right: i == 3 ? 0 : 14),
                decoration: BoxDecoration(
                  color: AppColors.surfaceStrong,
                  borderRadius: BorderRadius.circular(AppRadii.card),
                ),
              ),
            ),
        ],
      ),
    ),
  );
}
