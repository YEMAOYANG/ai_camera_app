import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';

class SchoolTextbooksPage extends ConsumerWidget {
  const SchoolTextbooksPage({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final child = ref.watch(currentChildProvider);
    return AppScreen(
      title: '学校教材',
      reserveBottomNavigation: false,
      backLabel: '孩子资料',
      onBack: () =>
          context.canPop() ? context.pop() : context.go(profileChildPath),
      children: [
        child.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (_, _) => AppStateView(
            variant: AppStateVariant.networkUnavailable,
            title: '孩子资料未加载',
            message: '请刷新后再试。',
            primaryActionLabel: '刷新',
            onPrimaryAction: () => ref.invalidate(currentChildProvider),
          ),
          data: (value) => value == null
              ? const AppStateView(
                  variant: AppStateVariant.noData,
                  title: '请先完善孩子资料',
                  message: '确认年级后，再选择学校使用的教材。',
                )
              : _TextbookChoices(key: ValueKey(value.id), childId: value.id),
        ),
      ],
    );
  }
}

class _TextbookChoices extends ConsumerStatefulWidget {
  const _TextbookChoices({required this.childId, super.key});
  final String childId;
  @override
  ConsumerState<_TextbookChoices> createState() => _TextbookChoicesState();
}

class _TextbookChoicesState extends ConsumerState<_TextbookChoices> {
  String? _saving;
  String? _message;
  bool _failed = false;
  Future<void> _select(
    SchoolTextbookCatalog catalog,
    SchoolTextbook book,
  ) async {
    if (_saving != null) return;
    setState(() {
      _saving = book.key;
      _message = null;
    });
    try {
      await ref
          .read(textbookRepositoryProvider)
          .select(widget.childId, catalog, book);
      if (!mounted) return;
      setState(() {
        _message = '${book.subjectLabel}教材已确认，学生端刷新后可见';
        _failed = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = error is TextbookException ? error.message : '保存未确认，请刷新后核对';
        _failed = true;
      });
    } finally {
      if (mounted) {
        // Re-read after transport uncertainty, without replaying a write.
        ref.invalidate(schoolTextbooksProvider(widget.childId));
        setState(() {
          _saving = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final account = ref.watch(accountProfileProvider);
    final canManage =
        account.asData?.value.can('manage_child_profile') ?? false;
    if (account.isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (account.hasError) {
      return AppStateView(
        variant: AppStateVariant.networkUnavailable,
        title: '权限暂时未加载',
        message: '刷新后继续选书。',
        primaryActionLabel: '刷新',
        onPrimaryAction: () => ref.invalidate(accountProfileProvider),
      );
    }
    if (!canManage) {
      return const AppStateView(
        variant: AppStateVariant.permission,
        title: '请家庭管理员确认教材',
        message: '教材选择跟随孩子资料的管理权限。',
      );
    }
    final books = ref.watch(schoolTextbooksProvider(widget.childId));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text(
          '按孩子正在使用的课本确认出版社和册次。',
          style: TextStyle(fontSize: 16, height: 1.6),
        ),
        const SizedBox(height: 8),
        const Text(
          '同一地区可能使用不同版本，请以学校课本为准。',
          style: TextStyle(color: AppColors.muted, height: 1.6),
        ),
        if (_message != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Semantics(
              liveRegion: true,
              child: Text(
                _message!,
                style: TextStyle(
                  color: _failed ? AppColors.danger : AppColors.brand,
                  height: 1.5,
                ),
              ),
            ),
          ),
        books.when(
          skipLoadingOnRefresh: false,
          loading: () => const Padding(
            padding: EdgeInsets.all(32),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (_, _) => AppStateView(
            variant: AppStateVariant.networkUnavailable,
            title: '教材目录未加载',
            message: '请刷新后重试。',
            primaryActionLabel: '刷新目录',
            onPrimaryAction: () =>
                ref.invalidate(schoolTextbooksProvider(widget.childId)),
          ),
          data: (catalog) {
            if (catalog.books.isEmpty) {
              return const AppStateView(
                variant: AppStateVariant.noData,
                title: '本年级教材正在整理',
                message: '目录就绪后可在这里确认，尚未提供的版本不会自动替换。',
                compact: true,
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 20),
                  child: Text(
                    '${catalog.year}—${catalog.year + 1} 学年 · ${catalog.semester == 'upper' ? '上学期' : '下学期'}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                for (final book in catalog.books) _book(catalog, book),
              ],
            );
          },
        ),
      ],
    );
  }

  Widget _book(SchoolTextbookCatalog catalog, SchoolTextbook book) {
    final currentTerm =
        book.volume == 'full' || book.volume == catalog.semester;
    return Padding(
      padding: const EdgeInsets.only(bottom: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Divider(),
          Text(
            '${book.subjectLabel} · ${book.volumeLabel} · ${book.schoolSystem == 'six_year' ? '六年制' : '五四制'}',
            style: const TextStyle(color: AppColors.muted, height: 1.6),
          ),
          const SizedBox(height: 8),
          Text(
            book.title,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          Text(
            '${book.publisher}\n${book.editionLabel}',
            style: const TextStyle(height: 1.7),
          ),
          Text(
            book.indexOnly
                ? '版本已收录，单元与课次目录正在核对'
                : '${book.partial ? '部分目录' : '目录已整理'} · ${book.lessonCount} 课，课程陆续准备',
            style: const TextStyle(color: AppColors.muted, height: 1.7),
          ),
          const SizedBox(height: 14),
          AppPrimaryButton(
            label: book.selected
                ? '已确认使用'
                : !currentTerm
                ? '不属于本学期'
                : _saving == book.key
                ? '正在保存'
                : '使用这本教材',
            loading: _saving == book.key,
            onTap: book.selected || !currentTerm || _saving != null
                ? null
                : () => _select(catalog, book),
          ),
        ],
      ),
    );
  }
}
