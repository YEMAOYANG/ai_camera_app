import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/application/textbook_repository.dart';
import 'package:warm_sight/src/features/learning/domain/textbook_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/textbook_cover.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';

const _subjects = [
  ('chinese', '语文', '文'),
  ('math', '数学', '数'),
  ('english', '英语', 'Aa'),
  ('science', '科学', '科'),
];

/// First-time setup and profile editing share the same selection flow.
class SchoolTextbooksPage extends ConsumerWidget {
  const SchoolTextbooksPage({this.setupMode = false, super.key});
  final bool setupMode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final account = ref.watch(accountProfileProvider);
    final child = ref.watch(currentChildProvider);
    Widget? state;
    if (account.isLoading || child.isLoading) {
      state = const _LoadingBooks();
    } else if (account.hasError || child.hasError) {
      state = AppStateView(
        variant: AppStateVariant.networkUnavailable,
        title: '资料暂时未加载',
        message: '刷新后继续选择教材。',
        primaryActionLabel: '重新加载',
        onPrimaryAction: () {
          ref.invalidate(accountProfileProvider);
          ref.invalidate(currentChildProvider);
        },
      );
    } else if (!(account.asData?.value.can('manage_child_profile') ?? false)) {
      state = const AppStateView(
        variant: AppStateVariant.permission,
        title: '请家庭管理员确认教材',
        message: '教材选择跟随孩子资料的管理权限。',
      );
    } else if (child.asData?.value == null) {
      state = const AppStateView(
        variant: AppStateVariant.noData,
        title: '请先完善孩子资料',
        message: '确认年级后，再选择学校使用的教材。',
      );
    }
    if (state != null) {
      return AppScreen(
        title: '学校教材',
        fixedHeader: true,
        reserveBottomNavigation: false,
        onBack: setupMode ? null : () => _exit(context, false),
        backLabel: setupMode ? '稍后设置' : '孩子资料',
        trailing: setupMode
            ? TextButton(
                onPressed: () => _exit(context, true),
                child: const Text(
                  '稍后设置',
                  style: TextStyle(fontFamily: AppTypography.systemFont),
                ),
              )
            : null,
        children: [state],
      );
    }
    final value = child.asData!.value!;
    return _TextbookChoices(
      key: ValueKey(
        '${value.id}:${value.gradeCode}:${value.schoolYearStartYear}',
      ),
      child: value,
      setupMode: setupMode,
    );
  }
}

void _exit(BuildContext context, bool setupMode) {
  if (setupMode) {
    context.go(AppRoute.home.path);
  } else if (context.canPop()) {
    context.pop();
  } else {
    context.go(profileChildPath);
  }
}

class _TextbookChoices extends ConsumerStatefulWidget {
  const _TextbookChoices({
    required this.child,
    required this.setupMode,
    super.key,
  });
  final ChildProfile child;
  final bool setupMode;
  @override
  ConsumerState<_TextbookChoices> createState() => _TextbookChoicesState();
}

class _TextbookChoicesState extends ConsumerState<_TextbookChoices> {
  final _drafts = <String, SchoolTextbook>{};
  bool _saving = false;
  bool _allowExit = false;
  bool _failed = false;
  String? _message;

  @override
  void initState() {
    super.initState();
    final provider = schoolTextbooksProvider(widget.child.id);
    // Home/profile can keep this autoDispose provider alive with an older
    // catalog. Refresh when entering the picker, without duplicating a load.
    if (!ref.read(provider).isLoading) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !ref.read(provider).isLoading) {
          ref.invalidate(provider);
        }
      });
    }
  }

  SchoolTextbook? _saved(SchoolTextbookCatalog catalog, String subject) {
    for (final book in catalog.books) {
      if (book.subject == subject && book.selected) return book;
    }
    return null;
  }

  List<SchoolTextbook> _changes(SchoolTextbookCatalog catalog) => [
    for (final entry in _drafts.entries)
      if (entry.value.key != _saved(catalog, entry.key)?.key) entry.value,
  ];

  Future<void> _leave(SchoolTextbookCatalog? catalog) async {
    if (_saving) return;
    if (_drafts.isNotEmpty &&
        (catalog == null || _changes(catalog).isNotEmpty)) {
      final leave = await showAppConfirmSheet(
        context: context,
        title: '教材还未保存',
        message: '离开后，这次选择不会保存。已确认的教材不受影响。',
        confirmLabel: '暂不保存',
        cancelLabel: '继续选择',
      );
      if (!leave || !mounted) return;
    }
    if (!mounted) return;
    setState(() => _allowExit = true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _exit(context, widget.setupMode);
    });
  }

  Future<void> _chooseTerm(SchoolTextbookCatalog catalog) async {
    final value = await showAppPickerSheet<String>(
      context: context,
      title: '孩子当前的学期',
      subtitle: '日期仅供参考，以学校实际进度为准。切换后保留原学期的选书和学习记录。',
      selected: catalog.termSource == 'calendar' ? 'auto' : catalog.semester,
      options: const [
        AppPickerOption(value: 'upper', label: '上学期', description: '使用上册教材'),
        AppPickerOption(value: 'lower', label: '下学期', description: '使用下册教材'),
        AppPickerOption(
          value: 'auto',
          label: '按日期自动判断',
          description: '9—1 月上学期，2—8 月下学期',
        ),
      ],
    );
    if (value == null || !mounted) return;
    await _updateContext(catalog, semester: value == 'auto' ? null : value);
  }

  Future<bool> _updateContext(
    SchoolTextbookCatalog catalog, {
    required String? semester,
  }) async {
    if (_saving) return false;
    if (_changes(catalog).isNotEmpty) {
      final change = await showAppConfirmSheet(
        context: context,
        title: '教材还未保存',
        message: '修改学期会清除这次未保存的选择，已确认的教材会保留。',
        confirmLabel: '继续修改',
        cancelLabel: '继续选书',
      );
      if (!change || !mounted) return false;
    }
    setState(() {
      _saving = true;
      _message = null;
    });
    final gateway = ref.read(textbookRepositoryProvider);
    var saved = false;
    try {
      await gateway.updateContext(widget.child.id, catalog, semester: semester);
      saved = true;
    } catch (error) {
      // Reconcile a response lost after commit; never replay a write automatically.
      try {
        final fresh = await gateway.catalog(widget.child.id);
        saved =
            fresh.year == catalog.year &&
            fresh.gradeRevision == catalog.gradeRevision &&
            fresh.contextRevision > catalog.contextRevision &&
            fresh.manualSemester == semester;
      } catch (_) {
        /* Leave the original input intact. */
      }
      if (!saved && mounted) {
        setState(
          () => _message = error is TextbookException
              ? error.message
              : '设置未能确认，请刷新后重试',
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
          if (saved) _drafts.clear();
        });
        if (saved) ref.invalidate(schoolTextbooksProvider(widget.child.id));
      }
    }
    return saved;
  }

  Future<void> _pick(
    SchoolTextbookCatalog catalog,
    String subject,
    String label,
  ) async {
    final books = catalog.books
        .where(
          (book) =>
              book.subject == subject &&
              (book.volume == catalog.semester || book.volume == 'full'),
        )
        .toList();
    final selected = _drafts[subject] ?? _saved(catalog, subject);
    final picked = await showAppBottomSheet<SchoolTextbook>(
      context: context,
      maxHeightFactor: 0.86,
      child: _BookPicker(
        label: label,
        books: books,
        selectedKey: selected?.key,
      ),
    );
    if (!mounted || picked == null) return;
    setState(() {
      _drafts[subject] = picked;
      _message = null;
    });
  }

  Future<void> _save(SchoolTextbookCatalog catalog) async {
    if (_saving) return;
    final changes = _changes(catalog);
    if (changes.isEmpty) {
      if (widget.setupMode) _leave(catalog);
      return;
    }
    final currentBooks = <SchoolTextbook>[];
    for (final draft in changes) {
      final matches = catalog.books.where(
        (book) =>
            book.key == draft.key &&
            (book.volume == catalog.semester || book.volume == 'full'),
      );
      if (matches.isEmpty) {
        setState(() {
          _message = '${draft.subjectLabel}教材信息已更新，请重新选择';
          _failed = true;
        });
        return;
      }
      currentBooks.add(matches.first);
    }
    setState(() {
      _saving = true;
      _message = null;
    });
    try {
      await ref
          .read(textbookRepositoryProvider)
          .selectMany(widget.child.id, catalog, currentBooks);
      if (!mounted) return;
      setState(() {
        _drafts.clear();
        _message = '教材已保存，学生端刷新书包后可见';
        _failed = false;
      });
      ref.invalidate(schoolTextbooksProvider(widget.child.id));
      if (widget.setupMode) _exit(context, true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _message = error is TextbookException
            ? error.message
            : '保存结果尚未确认，请核对后再试';
        _failed = true;
      });
      // Read back uncertain writes, retaining the draft; never replay a write.
      try {
        final latest = await ref.refresh(
          schoolTextbooksProvider(widget.child.id).future,
        );
        if (!mounted) return;
        if (_changes(latest).isEmpty) {
          setState(() {
            _drafts.clear();
            _message = '已核对，教材已保存';
            _failed = false;
          });
          if (widget.setupMode) _exit(context, true);
        }
      } catch (_) {
        // Keep the original error and drafts when the read-back also fails.
      }
      if (mounted && _failed) {
        showAppToast(context, _message!, tone: AppToastTone.danger);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final books = ref.watch(schoolTextbooksProvider(widget.child.id));
    final catalog = books.asData?.value;
    final dirty = catalog != null && _changes(catalog).isNotEmpty;
    final nickname = widget.child.nickname.trim().isEmpty
        ? widget.child.name
        : widget.child.nickname;
    return PopScope(
      canPop:
          _allowExit ||
          (!widget.setupMode && !_saving && !dirty && _drafts.isEmpty),
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _leave(catalog);
      },
      child: AppScreen(
        plainBackground: true,
        avoidFooterOverlap: true,
        pinnedHeaderHeight: 56,
        headerContent: const Text(
          '教材设置',
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            color: AppColors.ink,
          ),
        ),
        title: '学校教材',
        fixedHeader: true,
        reserveBottomNavigation: false,
        onBack: widget.setupMode || _saving ? null : () => _leave(catalog),
        backLabel: widget.setupMode ? '稍后设置' : '孩子资料',
        trailing: widget.setupMode
            ? TextButton(
                onPressed: _saving ? null : () => _leave(catalog),
                child: const Text(
                  '稍后设置',
                  style: TextStyle(
                    fontSize: 13,
                    fontFamily: AppTypography.systemFont,
                  ),
                ),
              )
            : null,
        footer: catalog == null
            ? null
            : AppPrimaryButton(
                label: _saving
                    ? '正在保存'
                    : widget.setupMode
                    ? dirty
                          ? '保存并进入首页'
                          : '进入首页'
                    : '保存教材',
                loading: _saving,
                onTap: !_saving && (dirty || widget.setupMode)
                    ? () => _save(catalog)
                    : null,
              ),
        children: [
          Text(
            widget.setupMode ? '和学校用同一套课本' : '$nickname的学校课本',
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w600,
              height: 1.35,
              color: AppColors.ink,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            '按学校课本选择版本，不确定的可以稍后补充。',
            style: TextStyle(
              color: AppColors.mutedStrong,
              fontSize: 13,
              height: 1.6,
            ),
          ),
          const SizedBox(height: 20),
          books.when(
            skipLoadingOnRefresh: false,
            loading: () => const _LoadingBooks(),
            error: (_, _) => AppStateView(
              variant: AppStateVariant.networkUnavailable,
              title: '教材目录未加载',
              message: '已选内容会保留，连接后可以继续。',
              primaryActionLabel: '刷新目录',
              onPrimaryAction: () =>
                  ref.invalidate(schoolTextbooksProvider(widget.child.id)),
            ),
            data: (catalog) {
              final chosen = [
                for (final subject in _subjects)
                  _drafts[subject.$1] ?? _saved(catalog, subject.$1),
              ].whereType<SchoolTextbook>().length;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _SchoolTerm(
                    grade: widget.child.grade,
                    catalog: catalog,
                    onTap: _saving ? null : () => _chooseTerm(catalog),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          '本学期课本',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                            color: AppColors.ink,
                          ),
                        ),
                      ),
                      Text(
                        '已选 $chosen / ${_subjects.length} 科',
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.mutedStrong,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Material(
                    color: AppColors.surfaceElevated,
                    borderRadius: BorderRadius.circular(AppRadii.cardMedium),
                    clipBehavior: Clip.antiAlias,
                    child: Column(
                      children: [
                        for (
                          var index = 0;
                          index < _subjects.length;
                          index++
                        ) ...[
                          if (index > 0)
                            const Divider(
                              height: 1,
                              indent: 76,
                              color: AppColors.borderSoft,
                            ),
                          _SubjectRow(
                            subject: _subjects[index],
                            book:
                                _drafts[_subjects[index].$1] ??
                                _saved(catalog, _subjects[index].$1),
                            changed: _changes(catalog).any(
                              (book) => book.subject == _subjects[index].$1,
                            ),
                            available: catalog.books.any(
                              (book) =>
                                  book.subject == _subjects[index].$1 &&
                                  (book.volume == catalog.semester ||
                                      book.volume == 'full'),
                            ),
                            onTap: _saving
                                ? null
                                : () => _pick(
                                    catalog,
                                    _subjects[index].$1,
                                    _subjects[index].$2,
                                  ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  if (dirty)
                    const Padding(
                      padding: EdgeInsets.only(top: 12),
                      child: Text(
                        '已选择的版本将在保存后生效',
                        style: TextStyle(
                          color: AppColors.brandDeep,
                          fontSize: 12,
                          height: 1.5,
                        ),
                      ),
                    ),
                  const SizedBox(height: 14),
                  Theme(
                    data: Theme.of(
                      context,
                    ).copyWith(dividerColor: Colors.transparent),
                    child: ExpansionTile(
                      tilePadding: const EdgeInsets.symmetric(horizontal: 2),
                      childrenPadding: const EdgeInsets.fromLTRB(2, 0, 2, 12),
                      leading: const Icon(
                        Icons.help_outline,
                        size: 19,
                        color: AppColors.mutedStrong,
                      ),
                      title: const Text(
                        '如何确认教材版本？',
                        style: TextStyle(
                          fontSize: 13,
                          color: AppColors.mutedStrong,
                        ),
                      ),
                      children: const [
                        Text(
                          '查看课本封面的出版社、年级与上下册。英语还需核对起始年级；以学校发的课本为准。',
                          style: TextStyle(
                            color: AppColors.mutedStrong,
                            fontSize: 13,
                            height: 1.7,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: _saving
                          ? null
                          : () => ref.invalidate(
                              schoolTextbooksProvider(widget.child.id),
                            ),
                      icon: const Icon(Icons.refresh, size: 16),
                      label: const Text(
                        '刷新教材目录',
                        style: TextStyle(
                          fontSize: 12,
                          fontFamily: AppTypography.systemFont,
                        ),
                      ),
                      style: TextButton.styleFrom(
                        foregroundColor: AppColors.mutedStrong,
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
          if (_message != null)
            Padding(
              padding: const EdgeInsets.only(top: 14),
              child: Semantics(
                liveRegion: true,
                child: Text(
                  _message!,
                  style: TextStyle(
                    color: _failed ? AppColors.danger : AppColors.brandDeep,
                    fontSize: 14,
                    height: 1.6,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _SchoolTerm extends StatelessWidget {
  const _SchoolTerm({required this.grade, required this.catalog, this.onTap});
  final String grade;
  final SchoolTextbookCatalog catalog;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Material(
    color: AppColors.surfaceStrong,
    borderRadius: BorderRadius.circular(AppRadii.card),
    child: Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 4, 12),
      child: Row(
        children: [
          const Icon(
            Icons.calendar_today_outlined,
            size: 20,
            color: AppColors.mutedStrong,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$grade · ${catalog.semester == 'upper' ? '上学期' : '下学期'}',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: AppColors.ink,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '${catalog.year}—${catalog.year + 1} · ${catalog.termSource == 'parent' ? '家长已确认' : '按日期建议'}',
                  style: const TextStyle(
                    fontSize: 11,
                    height: 1.5,
                    color: AppColors.mutedStrong,
                  ),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: onTap,
            style: TextButton.styleFrom(foregroundColor: AppColors.brandDeep),
            child: const Text(
              '修改学期',
              style: TextStyle(
                fontSize: 12,
                fontFamily: AppTypography.systemFont,
              ),
            ),
          ),
        ],
      ),
    ),
  );
}

class _SubjectRow extends StatelessWidget {
  const _SubjectRow({
    required this.subject,
    required this.book,
    required this.changed,
    required this.available,
    required this.onTap,
  });
  final (String, String, String) subject;
  final SchoolTextbook? book;
  final bool changed, available;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final status = changed
        ? '待保存'
        : book != null
        ? '已确认'
        : available
        ? '选择版本'
        : '暂未收录';
    return Semantics(
      button: true,
      enabled: onTap != null,
      label: '${subject.$2}教材，$status',
      child: InkWell(
        key: ValueKey('textbookSubject_${subject.$1}'),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          child: Row(
            children: [
              TextbookCover(
                subject: subject.$1,
                volumeLabel: book?.volumeLabel,
                placeholder: book == null,
                width: 46,
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Wrap(
                      spacing: 8,
                      runSpacing: 4,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(
                          subject.$2,
                          style: const TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                            color: AppColors.ink,
                          ),
                        ),
                        if (book != null)
                          Text(
                            status,
                            style: TextStyle(
                              fontSize: 11,
                              color: changed
                                  ? AppColors.brandDeep
                                  : AppColors.mutedStrong,
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      book?.versionLabel ??
                          (available ? '与学校发的课本保持一致' : '本年级教材暂未收录'),
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.mutedStrong,
                        height: 1.5,
                      ),
                    ),
                    if (book != null)
                      Text(
                        '${book!.schoolSystem == 'six_year' ? '六年制' : '五四制'} · ${book!.volumeLabel}',
                        style: const TextStyle(
                          fontSize: 11,
                          color: AppColors.mutedStrong,
                          height: 1.6,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Icon(
                book == null && available
                    ? Icons.add_circle_outline
                    : Icons.chevron_right,
                size: 21,
                color: book == null && available
                    ? AppColors.brandDeep
                    : AppColors.mutedStrong,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BookPicker extends StatefulWidget {
  const _BookPicker({
    required this.label,
    required this.books,
    required this.selectedKey,
  });
  final String label;
  final List<SchoolTextbook> books;
  final String? selectedKey;
  @override
  State<_BookPicker> createState() => _BookPickerState();
}

class _BookPickerState extends State<_BookPicker> {
  final _search = TextEditingController();
  String _query = '';
  late String _system;

  @override
  void initState() {
    super.initState();
    final selected = widget.books
        .where((b) => b.key == widget.selectedKey)
        .firstOrNull;
    _system =
        selected?.schoolSystem ??
        (widget.books.any((b) => b.schoolSystem == 'six_year')
            ? 'six_year'
            : 'five_four');
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final systems = widget.books.map((b) => b.schoolSystem).toSet();
    final books =
        widget.books
            .where(
              (book) =>
                  book.schoolSystem == _system &&
                  '${book.editionLabel} ${book.publisher} ${book.title}'
                      .toLowerCase()
                      .contains(_query.trim().toLowerCase()),
            )
            .toList()
          ..sort((a, b) => a.versionLabel.compareTo(b.versionLabel));
    return Material(
      color: AppColors.appBackground,
      borderRadius: const BorderRadius.vertical(
        top: Radius.circular(AppRadii.cardLarge),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 32,
              height: 4,
              margin: const EdgeInsets.only(top: 10),
              decoration: BoxDecoration(
                color: AppColors.border,
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 8, 0),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '选择${widget.label}教材',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                      color: AppColors.ink,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: '关闭',
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close, size: 21),
                ),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 20),
            child: Text(
              '与学校课本的版本、主编和册次保持一致。',
              style: TextStyle(
                color: AppColors.mutedStrong,
                fontSize: 12,
                height: 1.5,
              ),
            ),
          ),
          if (widget.books.length > 6)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
              child: TextField(
                key: const ValueKey('textbookVersionSearch'),
                controller: _search,
                onChanged: (value) => setState(() => _query = value),
                style: const TextStyle(fontSize: 14, color: AppColors.ink),
                decoration: InputDecoration(
                  hintText: '搜索版本、出版社或主编',
                  hintStyle: const TextStyle(
                    fontSize: 13,
                    color: AppColors.mutedStrong,
                  ),
                  fillColor: AppColors.surfaceStrong,
                  prefixIcon: const Icon(
                    Icons.search,
                    size: 20,
                    color: AppColors.mutedStrong,
                  ),
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          tooltip: '清除搜索',
                          onPressed: () {
                            _search.clear();
                            setState(() => _query = '');
                          },
                          icon: const Icon(Icons.close, size: 18),
                        ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppRadii.card),
                    borderSide: BorderSide.none,
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(AppRadii.card),
                    borderSide: BorderSide.none,
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                ),
              ),
            ),
          if (systems.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
              child: SegmentedButton<String>(
                showSelectedIcon: false,
                segments: const [
                  ButtonSegment(value: 'six_year', label: Text('六年制小学')),
                  ButtonSegment(value: 'five_four', label: Text('五四学制')),
                ],
                selected: {_system},
                onSelectionChanged: (value) =>
                    setState(() => _system = value.single),
                style: ButtonStyle(
                  textStyle: const WidgetStatePropertyAll(
                    TextStyle(
                      fontSize: 12,
                      fontFamily: AppTypography.systemFont,
                    ),
                  ),
                  minimumSize: const WidgetStatePropertyAll(Size(0, 44)),
                  side: const WidgetStatePropertyAll(
                    BorderSide(color: AppColors.border),
                  ),
                  shape: WidgetStatePropertyAll(
                    RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(AppRadii.card),
                    ),
                  ),
                  backgroundColor: WidgetStateProperty.resolveWith(
                    (states) => states.contains(WidgetState.selected)
                        ? AppColors.ink
                        : AppColors.surfaceElevated,
                  ),
                  foregroundColor: WidgetStateProperty.resolveWith(
                    (states) => states.contains(WidgetState.selected)
                        ? Colors.white
                        : AppColors.mutedStrong,
                  ),
                ),
              ),
            ),
          if (widget.books.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 10),
              child: Text(
                '${books.length} 个可选版本',
                style: const TextStyle(
                  fontSize: 11,
                  color: AppColors.mutedStrong,
                ),
              ),
            ),
          Flexible(
            child: widget.books.isEmpty
                ? const SingleChildScrollView(
                    child: Padding(
                      padding: EdgeInsets.fromLTRB(20, 16, 20, 24),
                      child: AppStateView(
                        variant: AppStateVariant.noData,
                        title: '这科教材正在整理',
                        message: '当前年级、本学期的版本尚未收录。可以先保存其他学科；学校未开设的科目可暂不选择。',
                        compact: true,
                      ),
                    ),
                  )
                : books.isEmpty
                ? const SingleChildScrollView(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        '没有找到这个版本，请试试出版社或主编姓名。',
                        style: TextStyle(
                          color: AppColors.mutedStrong,
                          fontSize: 14,
                          height: 1.5,
                        ),
                      ),
                    ),
                  )
                : ListView.separated(
                    shrinkWrap: true,
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
                    padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                    itemCount: books.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 8),
                    itemBuilder: (context, index) => _VersionOption(
                      book: books[index],
                      selected: books[index].key == widget.selectedKey,
                      onTap: () => Navigator.pop(context, books[index]),
                    ),
                  ),
          ),
          if (widget.books.isNotEmpty)
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 4, 20, 16),
              child: Text(
                '选择后统一保存，课程以学生端实际开放为准。',
                style: TextStyle(
                  fontSize: 11,
                  height: 1.5,
                  color: AppColors.mutedStrong,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _VersionOption extends StatelessWidget {
  const _VersionOption({
    required this.book,
    required this.selected,
    required this.onTap,
  });
  final SchoolTextbook book;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    selected: selected,
    button: true,
    child: Material(
      color: selected ? AppColors.brandWash : AppColors.surfaceElevated,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadii.card),
        side: BorderSide(
          color: selected ? AppColors.brandDeep : AppColors.borderSoft,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: ValueKey('textbookOption_${book.key}'),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              TextbookCover(
                subject: book.subject,
                volumeLabel: book.volumeLabel,
                width: 42,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      book.versionLabel,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        height: 1.45,
                        color: AppColors.ink,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      book.title,
                      style: const TextStyle(
                        fontSize: 12,
                        height: 1.5,
                        color: AppColors.mutedStrong,
                      ),
                    ),
                    Text(
                      book.publisher,
                      style: const TextStyle(
                        fontSize: 11,
                        height: 1.5,
                        color: AppColors.mutedStrong,
                      ),
                    ),
                    if (book.versionDetail.contains('起点') ||
                        book.versionDetail.contains('课标'))
                      Text(
                        book.versionDetail,
                        style: const TextStyle(
                          fontSize: 11,
                          height: 1.5,
                          color: AppColors.mutedStrong,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Icon(
                selected ? Icons.check_circle : Icons.radio_button_unchecked,
                color: selected ? AppColors.brandDeep : AppColors.mutedStrong,
                size: 21,
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

class _LoadingBooks extends StatelessWidget {
  const _LoadingBooks();
  @override
  Widget build(BuildContext context) => Semantics(
    label: '正在读取教材',
    child: Column(
      children: [
        for (var i = 0; i < _subjects.length; i++)
          Container(
            height: 88,
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              color: AppColors.surfaceStrong,
              borderRadius: BorderRadius.circular(AppRadii.input),
            ),
          ),
      ],
    ),
  );
}
