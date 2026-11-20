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
              child: Text('教材与课程', style: AppTypography.sectionHeading),
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
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.warningWash.withValues(alpha: .72),
            borderRadius: BorderRadius.circular(AppRadii.cardMedium),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: AppListRow(
              icon: Icons.assignment_outlined,
              tone: AppListRowTone.amber,
              title: '作业检查与周末复习',
              subtitle: '查看具体错题和学习进步',
              onTap: () => context.push(
                '$learningCenterPath?childId=${Uri.encodeQueryComponent(childId)}',
              ),
            ),
          ),
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
              const SizedBox(height: 12),
              Text(data.termLabel, style: AppTypography.caption),

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
              const SizedBox(height: 6),
              const Divider(height: 1),
              for (final subject in const [
                ('chinese', '语文'),
                ('math', '数学'),
                ('english', '英语'),
                ('science', '科学'),
              ]) ...[
                _SubjectBook(subject: subject, catalog: data, onTap: onManage),
                const Divider(height: 1),
              ],
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
    final progress = learning != null && learning.available > 0
        ? (learning.completed / learning.available).clamp(0.0, 1.0)
        : null;
    final ink = TextbookSubjectStyle.forSubject(subject.$1).ink;
    final narrow = MediaQuery.sizeOf(context).width < 370;
    return Semantics(
      container: true,
      button: onTap != null,
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppRadii.card),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Row(
              children: [
                TextbookCover(
                  subject: subject.$1,
                  width: 44,
                  volumeLabel: book?.volumeLabel,
                  placeholder: book == null && !unavailable,
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        subject.$2,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          height: 1.2,
                        ),
                      ),
                      if (book != null) ...[
                        const SizedBox(height: 2),
                        Semantics(
                          label: '${book.versionLabel} · ${book.volumeLabel}',
                          excludeSemantics: true,
                          child: Text(
                            narrow
                                ? book.versionLabel
                                : '${book.versionLabel} · ${book.volumeLabel}',
                            style: AppTypography.caption,
                          ),
                        ),
                      ],
                      const SizedBox(height: 3),
                      Text(
                        status,
                        style: AppTypography.caption.copyWith(
                          color: progress != null
                              ? AppColors.success
                              : AppColors.mutedStrong,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (progress != null) ...[
                        const SizedBox(height: 4),
                        SizedBox(
                          width: 80,
                          child: LinearProgressIndicator(
                            value: progress,
                            minHeight: 2,
                            borderRadius: BorderRadius.circular(AppRadii.full),
                            color: ink,
                            backgroundColor: AppColors.borderSoft,
                            semanticsLabel: '${subject.$2}已开放课程的学习进度',
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (onTap != null)
                  const Padding(
                    padding: EdgeInsets.only(left: 5),
                    child: Icon(
                      Icons.chevron_right,
                      size: 17,
                      color: AppColors.mutedStrong,
                    ),
                  ),
              ],
            ),
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
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        children: [
          for (var row = 0; row < 3; row++) ...[
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 9),
              child: Row(
                children: [
                  _PlaceholderStroke(width: 42, height: 55),
                  SizedBox(width: 13),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _PlaceholderStroke(width: 86, height: 12),
                        SizedBox(height: 8),
                        _PlaceholderStroke(width: 136, height: 9),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
          ],
        ],
      ),
    ),
  );
}

class _PlaceholderStroke extends StatelessWidget {
  const _PlaceholderStroke({required this.width, required this.height});

  final double width;
  final double height;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: AppColors.surfaceStrong,
      borderRadius: BorderRadius.circular(4),
    ),
    child: SizedBox(width: width, height: height),
  );
}
