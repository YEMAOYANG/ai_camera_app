import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import '../../learning_review/application/learning_review_repository.dart';
import '../../learning_review/domain/learning_review_models.dart';
import '../../learning_review/presentation/learning_support_widgets.dart';
import '../application/homework_photo_picker.dart';
import '../application/homework_repository.dart';
import '../domain/homework_models.dart';
import 'homework_page_editor.dart';

class HomeworkDetailPage extends ConsumerStatefulWidget {
  const HomeworkDetailPage({required this.submissionId, super.key});
  final String submissionId;
  @override
  ConsumerState<HomeworkDetailPage> createState() => _HomeworkDetailPageState();
}

class _AnalysisSubmissionUnconfirmed implements Exception {
  const _AnalysisSubmissionUnconfirmed();
}

class _HomeworkDetailPageState extends ConsumerState<HomeworkDetailPage>
    with WidgetsBindingObserver {
  Timer? timer;
  bool busy = false, foreground = true;
  bool analysisSubmissionUnconfirmed = false;
  String? error, progress;
  bool permissionError = false;
  int pageIndex = 0;
  String? selectedItem;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    ref.listenManual(
      homeworkDetailProvider(widget.submissionId),
      (old, next) => _poll(next.asData?.value),
      fireImmediately: true,
    );
  }

  @override
  void dispose() {
    timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    foreground = state == AppLifecycleState.resumed;
    if (!foreground) {
      timer?.cancel();
      timer = null;
    } else if (mounted && !busy) {
      unawaited(_refresh());
    }
  }

  void _poll(HomeworkSubmission? value) {
    timer?.cancel();
    timer = null;
    if (!mounted || !foreground || busy || value == null || !value.active) {
      return;
    }
    timer = Timer(const Duration(seconds: 4), () {
      if (mounted && foreground && !busy) {
        unawaited(_refresh());
      }
    });
  }

  void _update(HomeworkSubmission result) {
    if (!mounted) return;
    ref
        .read(homeworkDetailProvider(widget.submissionId).notifier)
        .accept(result);
    final list = homeworkListProvider(result.childId);
    if (ref.exists(list)) {
      ref.read(list.notifier).acceptFromDetail(result);
    }
    ref.invalidate(learningWeaknessesProvider(result.childId));
  }

  Future<void> _run(Future<void> Function() operation) async {
    if (busy) return;
    timer?.cancel();
    ref
        .read(homeworkDetailProvider(widget.submissionId).notifier)
        .beginMutation();
    setState(() {
      busy = true;
      error = null;
      permissionError = false;
    });
    try {
      await operation();
    } catch (e) {
      if (mounted) {
        setState(() {
          error = e is _AnalysisSubmissionUnconfirmed
              ? null
              : e is HomeworkPhotoException
              ? e.message
              : learningError(e);
          permissionError = e is HomeworkPhotoException && e.permission;
        });
        showAppToast(context, error ?? '请刷新确认提交状态', tone: AppToastTone.danger);
      }
    } finally {
      if (mounted) {
        setState(() {
          busy = false;
          progress = null;
        });
        _poll(
          ref.read(homeworkDetailProvider(widget.submissionId)).asData?.value,
        );
      }
    }
  }

  Future<void> _refresh({bool explainAvailability = false}) async {
    try {
      final result = await ref
          .read(homeworkDetailProvider(widget.submissionId).notifier)
          .refresh();
      if (!mounted) return;
      setState(() {
        analysisSubmissionUnconfirmed = false;
        error = null;
      });
      if (explainAvailability) {
        showAppToast(
          context,
          result.analysisAvailable
              ? '分析已可用，确认照片后即可提交'
              : 'AI 分析仍未启用，已保存的照片不会自动提交',
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = learningError(e));
        if (explainAvailability) {
          showAppToast(context, error!, tone: AppToastTone.danger);
        }
      }
    } finally {
      if (mounted) {
        _poll(
          ref.read(homeworkDetailProvider(widget.submissionId)).asData?.value,
        );
      }
    }
  }

  Future<void> _analyze(HomeworkSubmission submission) async {
    if (!submission.canAnalyze ||
        analysisSubmissionUnconfirmed ||
        ref
            .read(homeworkPhotoPickerProvider)
            .pending(submission.id)
            .isNotEmpty) {
      return;
    }
    await _run(() async {
      try {
        _update(await ref.read(homeworkRepositoryProvider).analyze(submission));
      } on DioException catch (failure) {
        // A lost response does not prove the queued analysis was rejected.
        // Reconcile with one read; never repeat the paid analysis request.
        if (failure.response != null &&
            (failure.response!.statusCode ?? 500) < 500) {
          rethrow;
        }
        if (!mounted) return;
        setState(() {
          analysisSubmissionUnconfirmed = true;
          progress = '正在读取提交状态…';
        });
        try {
          final result = await ref
              .read(homeworkDetailProvider(widget.submissionId).notifier)
              .refresh();
          if (!mounted) return;
          setState(() => analysisSubmissionUnconfirmed = false);
          _update(result);
        } catch (_) {
          throw const _AnalysisSubmissionUnconfirmed();
        }
      }
    });
  }

  Future<void> _add(HomeworkSubmission s, bool camera) async {
    if (!s.canUpload || analysisSubmissionUnconfirmed) return;
    await _run(() async {
      final picker = ref.read(homeworkPhotoPickerProvider);
      await picker.pick(
        s.id,
        s.childId,
        camera: camera,
        remaining: 10 - s.pages.length,
      );
      if (mounted) setState(() {});
      await _upload(s);
    });
  }

  Future<void> _upload(HomeworkSubmission initial) async {
    final picker = ref.read(homeworkPhotoPickerProvider),
        repo = ref.read(homeworkRepositoryProvider);
    var s = await repo.get(initial.id);
    if (!s.canUpload || analysisSubmissionUnconfirmed) return;
    final pending = picker.pending(s.id);
    for (var index = 0; index < pending.length; index++) {
      if (!mounted) return;
      setState(() => progress = '正在上传第 ${index + 1} / ${pending.length} 页');
      final file = pending[index];
      final photo = await picker.prepare(file);
      s = await repo.upload(
        s,
        bytes: photo.bytes,
        format: photo.format,
        idempotencyKey: file.key,
      );
      _update(s);
      await picker.remove(s.id, file.key);
    }
  }

  Future<bool> _confirmEdit(HomeworkSubmission s) async =>
      s.canEditPages &&
      !analysisSubmissionUnconfirmed &&
      (s.items.isEmpty ||
          await confirmLearningAction(
            context,
            title: '更新作业页面？',
            message: '这份作业的旧分析和相关薄弱点证据会撤销。修改后需要重新提交分析。',
            action: '继续修改',
          ));
  Future<void> _editPage(HomeworkSubmission s, HomeworkPage page) async {
    if (!await _confirmEdit(s) || !mounted) return;
    final result = await Navigator.of(context).push<Json>(
      MaterialPageRoute(
        builder: (_) => HomeworkPageEditor(submission: s, page: page),
      ),
    );
    if (result == null || !mounted) return;
    await _run(() async {
      _update(
        await ref.read(homeworkRepositoryProvider).editPages(s, [
          for (final p in s.pages) p.id == page.id ? result : p.edit,
        ]),
      );
    });
  }

  Future<void> _move(HomeworkSubmission s, int index, int delta) async {
    if (!await _confirmEdit(s) || !mounted) return;
    await _run(() async {
      final pages = s.pages.map((e) => e.edit).toList();
      final value = pages.removeAt(index);
      pages.insert(index + delta, value);
      _update(await ref.read(homeworkRepositoryProvider).editPages(s, pages));
      if (mounted) setState(() => pageIndex = index + delta);
    });
  }

  Future<void> _removePage(HomeworkSubmission s, HomeworkPage p) async {
    if (!s.canEditPages || analysisSubmissionUnconfirmed) return;
    if (!await confirmLearningAction(
          context,
          title: '删除这一页？',
          message: ref.read(homeworkPhotoPickerProvider).pending(s.id).isEmpty
              ? (s.pages.length == 1
                    ? '照片和旧分析会移除，作业保留为空草稿，可以重新拍摄。'
                    : '旧分析会撤销，剩余页面可重新提交分析。')
              : '照片和旧分析会移除。为避免照片重新上传，本次尚未上传的照片也会移除，需要时可重新选择。',
          action: '删除页面',
        ) ||
        !mounted) {
      return;
    }
    await _run(() async {
      _update(
        await ref.read(homeworkRepositoryProvider).editPages(s, [
          for (final page in s.pages)
            if (page.id != p.id) page.edit,
        ]),
      );
      await ref.read(homeworkPhotoPickerProvider).discard(s.id);
      ref.invalidate(homeworkPhotoRecoveryProvider(s.childId));
      if (mounted) {
        setState(() {
          pageIndex = 0;
          selectedItem = null;
        });
        showAppToast(context, '照片已删除', tone: AppToastTone.success);
      }
    });
  }

  Future<void> _delete(HomeworkSubmission s) async {
    if (!await confirmLearningAction(
          context,
          title: '删除这份作业？',
          message: '照片、识别与分析记录将被删除，相关薄弱点证据会撤销。此操作不能恢复。',
          action: '删除作业',
        ) ||
        !mounted) {
      return;
    }
    await _run(() async {
      await ref.read(homeworkRepositoryProvider).delete(s);
      await ref.read(homeworkPhotoPickerProvider).discard(s.id);
      ref.invalidate(homeworkPhotoRecoveryProvider(s.childId));
      ref.invalidate(homeworkListProvider(s.childId));
      ref.invalidate(learningWeaknessesProvider(s.childId));
      if (mounted) {
        showAppToast(context, '作业已删除');
        learningBack(context);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(homeworkDetailProvider(widget.submissionId));
    final s = state.asData?.value;
    final pending = ref
        .read(homeworkPhotoPickerProvider)
        .pending(widget.submissionId);
    return AppScreen(
      title: s?.title ?? '作业详情',
      subtitle: analysisSubmissionUnconfirmed ? '提交状态尚未确认' : s?.statusLabel,
      onBack: busy ? null : () => learningBack(context),
      reserveBottomNavigation: false,
      onRefresh: () async {
        if (!busy) await _refresh();
      },
      trailing: s == null
          ? null
          : IconButton(
              tooltip: '删除作业',
              onPressed: busy ? null : () => _delete(s),
              icon: const Icon(Icons.delete_outline),
            ),
      children: [
        if (error != null) ...[
          Text(
            error!,
            style: const TextStyle(color: AppColors.danger, height: 1.5),
          ),
          if (permissionError)
            TextButton(onPressed: openAppSettings, child: const Text('打开系统设置')),
          const SizedBox(height: 12),
        ],
        if (busy) ...[
          const LinearProgressIndicator(),
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(progress ?? '正在保存…'),
          ),
        ],
        if (pending.isNotEmpty) ...[
          Text('还有 ${pending.length} 张照片尚未上传，请先继续上传或移除，再提交分析。'),
          Wrap(
            spacing: 8,
            children: [
              TextButton(
                onPressed:
                    busy ||
                        s == null ||
                        !s.canUpload ||
                        analysisSubmissionUnconfirmed
                    ? null
                    : () => _run(() => _upload(s)),
                child: const Text('继续上传'),
              ),
              TextButton(
                onPressed: busy
                    ? null
                    : () => _run(() async {
                        if (await confirmLearningAction(
                              context,
                              title: '移除待上传照片？',
                              message: '已上传页面会保留；未上传照片需要重新选择。',
                              action: '移除',
                            ) &&
                            mounted) {
                          await ref
                              .read(homeworkPhotoPickerProvider)
                              .discard(widget.submissionId);
                          if (mounted) setState(() {});
                        }
                      }),
                child: const Text('移除未上传照片'),
              ),
            ],
          ),
        ],
        state.when(
          loading: () => const LearningLoading(),
          error: (e, _) => LearningError(e, () => unawaited(_refresh())),
          data: (value) => _content(value),
        ),
      ],
    );
  }

  Widget _content(HomeworkSubmission s) {
    final current = s.pages.isEmpty
        ? null
        : s.pages[pageIndex.clamp(0, s.pages.length - 1)];
    final items = current == null
        ? <HomeworkItem>[]
        : s.items.where((e) => e.pageId == current.id).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (analysisSubmissionUnconfirmed) ...[
          const Text(
            '提交结果暂未确认，照片已保存。请先刷新确认状态，不要重复提交分析。',
            style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
          ),
          const SizedBox(height: 12),
          AppSecondaryButton(
            label: '刷新提交状态',
            onTap: busy ? null : () => _run(() => _refresh()),
            trailing: const Icon(Icons.refresh, size: 18),
          ),
          const SizedBox(height: 12),
        ],
        if (!s.analysisAvailable && !s.hasUnconfirmedProviderReceipt)
          AppListRow(
            icon: Icons.info_outline,
            title: s.pages.isEmpty ? 'AI 分析尚未启用' : '照片已保存 · AI 分析尚未启用',
            subtitle: s.pages.isEmpty
                ? '可以先上传和整理照片，启用分析后再提交。'
                : '可以继续整理照片。分析服务启用后需由你手动提交，当前不会自动分析。',
            subtitleMaxLines: 4,
          ),
        if (s.active) ...[
          const LinearProgressIndicator(),
          const SizedBox(height: 8),
          Text(
            '${s.statusLabel}，可以先离开。回来后会恢复处理进度。',
            style: const TextStyle(color: AppColors.mutedStrong, height: 1.6),
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: busy ? null : () => _refresh(),
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('刷新状态'),
            ),
          ),
        ],
        if (s.retryAllowed && textValue(s.data['retryReason']).isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(
              textValue(s.data['retryReason']),
              style: const TextStyle(color: AppColors.mutedStrong, height: 1.6),
            ),
          ),
        if (s.hasUnconfirmedProviderReceipt ||
            (s.status == 'failed' && s.recognitionResultNeedsReview)) ...[
          Text(
            s.analysisIssueMessage!,
            style: const TextStyle(color: AppColors.mutedStrong, height: 1.6),
          ),
          const SizedBox(height: 12),
          AppSecondaryButton(
            label: '刷新状态',
            onTap: busy
                ? null
                : () => _run(() async {
                    setState(() => progress = '正在读取状态…');
                    await _refresh();
                  }),
            trailing: const Icon(Icons.refresh, size: 18),
          ),
          const SizedBox(height: 12),
        ],
        if (s.status == 'failed' &&
            !s.hasUnconfirmedProviderReceipt &&
            !s.recognitionResultNeedsReview)
          Text(s.analysisIssueMessage!),
        if (s.items.isNotEmpty) _StudentCorrectionSummary(submission: s),
        if (s.canUpload && !analysisSubmissionUnconfirmed)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                onPressed: busy ? null : () => _add(s, true),
                icon: const Icon(Icons.photo_camera_outlined),
                label: const Text(
                  '拍一页',
                  style: TextStyle(fontFamily: AppTypography.systemFont),
                ),
              ),
              OutlinedButton.icon(
                onPressed: busy ? null : () => _add(s, false),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text(
                  '从相册选多页',
                  style: TextStyle(fontFamily: AppTypography.systemFont),
                ),
              ),
            ],
          ),
        if (s.pages.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 32),
            child: Text(
              '还没有照片\n放平纸张、避开反光，拍下整页题目与答案。',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.mutedStrong, height: 1.8),
            ),
          ),
        if (current != null) ...[
          const SizedBox(height: 12),
          Row(
            children: [
              IconButton(
                tooltip: '上一页',
                onPressed: pageIndex > 0
                    ? () => setState(() {
                        pageIndex--;
                        selectedItem = null;
                      })
                    : null,
                icon: const Icon(Icons.chevron_left),
              ),
              Expanded(
                child: Text(
                  '第 ${pageIndex.clamp(0, s.pages.length - 1) + 1} / ${s.pages.length} 页',
                  textAlign: TextAlign.center,
                ),
              ),
              IconButton(
                tooltip: '下一页',
                onPressed: pageIndex < s.pages.length - 1
                    ? () => setState(() {
                        pageIndex++;
                        selectedItem = null;
                      })
                    : null,
                icon: const Icon(Icons.chevron_right),
              ),
            ],
          ),
          if (current.data['error'] != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                const {
                      'image_too_small': '照片分辨率不足，请移除此页后重新拍摄。',
                      'image_blank_or_unreadable': '照片过亮或内容不清楚，请避开反光后重新拍摄。',
                      'recognition_unreadable': '未能看清完整题目，请重新拍摄这一页。',
                    }[current.data['error']] ??
                    '请补拍清晰的整页，让 AI 老师看清题目和孩子的作答。',
                style: const TextStyle(color: AppColors.danger, height: 1.6),
              ),
            ),
          _AnnotatedPage(
            submission: s,
            page: current,
            items: items,
            selectedId: selectedItem,
            onSelect: (id) => setState(() => selectedItem = id),
          ),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 4,
            children: [
              TextButton.icon(
                onPressed:
                    busy || !s.canEditPages || analysisSubmissionUnconfirmed
                    ? null
                    : () => _editPage(s, current),
                icon: const Icon(Icons.crop_rotate, size: 18),
                label: const Text(
                  '旋转 / 裁剪',
                  style: TextStyle(fontFamily: AppTypography.systemFont),
                ),
              ),
              IconButton(
                tooltip: '向前移一页',
                onPressed:
                    busy ||
                        !s.canEditPages ||
                        analysisSubmissionUnconfirmed ||
                        pageIndex <= 0
                    ? null
                    : () => _move(s, pageIndex, -1),
                icon: const Icon(Icons.arrow_back),
              ),
              IconButton(
                tooltip: '向后移一页',
                onPressed:
                    busy ||
                        !s.canEditPages ||
                        analysisSubmissionUnconfirmed ||
                        pageIndex >= s.pages.length - 1
                    ? null
                    : () => _move(s, pageIndex, 1),
                icon: const Icon(Icons.arrow_forward),
              ),
              IconButton(
                tooltip: '删除这一页',
                onPressed:
                    busy || !s.canEditPages || analysisSubmissionUnconfirmed
                    ? null
                    : () => _removePage(s, current),
                icon: const Icon(Icons.delete_outline),
              ),
            ],
          ),
        ],
        if (!s.analysisAvailable &&
            !s.active &&
            !s.hasUnconfirmedProviderReceipt &&
            !s.recognitionResultNeedsReview &&
            !analysisSubmissionUnconfirmed) ...[
          const SizedBox(height: 8),
          AppSecondaryButton(
            label: '刷新分析状态',
            onTap: busy
                ? null
                : () => _run(() => _refresh(explainAvailability: true)),
            trailing: const Icon(Icons.refresh, size: 18),
          ),
          const SizedBox(height: 12),
        ],
        if (s.canAnalyze &&
            !analysisSubmissionUnconfirmed &&
            ref.read(homeworkPhotoPickerProvider).pending(s.id).isEmpty) ...[
          const SizedBox(height: 8),
          AppPrimaryButton(
            label: s.status == 'received'
                ? '提交分析'
                : s.status == 'media_preparing'
                ? '继续准备讲解'
                : '重试分析',
            loading: busy,
            onTap: busy ? null : () => _analyze(s),
          ),
          const SizedBox(height: 12),
        ],
        if (s.isEssay && s.essayReview.isNotEmpty) ...[
          const LearningHeading('作文修改建议'),
          const Text(
            '对照每页原作文查看建议。这里不生成考试分数，也不计入客观题正确率。',
            style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
          ),
          for (final suggestion in s.essaySuggestions)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (textValue(suggestion['origin']).isNotEmpty)
                    Text('原句：${textValue(suggestion['origin'])}'),
                  if (textValue(suggestion['replace']).isNotEmpty)
                    Text('建议修改：${textValue(suggestion['replace'])}'),
                  if (textValue(suggestion['message']).isNotEmpty)
                    Text(
                      textValue(suggestion['message']),
                      style: const TextStyle(height: 1.6),
                    ),
                ],
              ),
            ),
          if (s.essaySuggestions.isEmpty && !s.active)
            const Text('服务未返回具体句子建议，可请学生端 AI 老师对照原作文讲解。'),
          const SizedBox(height: 16),
        ],
        if (!s.isEssay && s.items.isNotEmpty) ...[
          const LearningHeading('原卷批改结果'),
          Text(
            s.originalPaperSummary.isNotEmpty
                ? '共 ${number(s.originalPaperSummary['total'])} 个作答位置 · 批改正确 ${number(s.originalPaperSummary['correct'])} · 建议订正 ${number(s.originalPaperSummary['incorrect'])}\n空白未作答 ${number(s.originalPaperSummary['blank'])} · 待核实 ${(number(s.originalPaperSummary['unknown']) - number(s.originalPaperSummary['blank'])).clamp(0, number(s.originalPaperSummary['unknown']))}'
                : '共 ${number(s.summary['total'])} 题 · 正确 ${number(s.summary['correct'])} · 需学生订正 ${number(s.summary['incorrect'])}\n空白 ${number(s.summary['blank'])} · 待老师看原图 ${number(s.summary['pending'])} · 暂不支持 ${number(s.summary['unsupported'])}',
            style: const TextStyle(height: 1.7),
          ),
          if (s.provisionalPaperSummary.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              '腾讯初判：正确 ${number(s.provisionalPaperSummary['correct'])} · 建议再看 ${number(s.provisionalPaperSummary['incorrect'])} · 待核验 ${number(s.provisionalPaperSummary['unknown'])}',
              style: const TextStyle(height: 1.7),
            ),
            const Text(
              '初判标记帮助定位原作答，尚未核验，不计入正式错题或能力评分。孩子在学生端跟老师看原图、听讲解。',
              style: TextStyle(
                color: AppColors.mutedStrong,
                fontSize: 13,
                height: 1.6,
              ),
            ),
          ],
          if (s.originalPaperSummary.isNotEmpty)
            const Text(
              '原卷批改由腾讯 AI 提供。AI 老师在学生端结合照片讲解；批改建议与孩子独立掌握的评估分开记录。',
              style: TextStyle(
                color: AppColors.mutedStrong,
                fontSize: 13,
                height: 1.6,
              ),
            ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text(
              '点原图题号查看批改结果和解析。孩子在学生端跟 AI 老师订正，家长只需上传照片、查看报告。',
              style: TextStyle(
                color: AppColors.mutedStrong,
                fontSize: 13,
                height: 1.6,
              ),
            ),
          ),
          for (var index = 0; index < items.length; index++)
            _ItemResult(
              key: ValueKey(
                '${items[index].id}-${items[index].revision}-${selectedItem == items[index].id}',
              ),
              item: items[index],
              ordinal: index + 1,
              expanded: selectedItem == items[index].id,
            ),
          const Padding(
            padding: EdgeInsets.only(top: 16),
            child: Text(
              '这里记录孩子在学生端的订正进度。订正原题后还需结合后续独立练习判断掌握情况。',
              style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
            ),
          ),
        ],
      ],
    );
  }
}

class _StudentCorrectionSummary extends StatelessWidget {
  const _StudentCorrectionSummary({required this.submission});
  final HomeworkSubmission submission;

  @override
  Widget build(BuildContext context) {
    final s = submission;
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const LearningHeading('学生端跟老师订正'),
          if (s.data['tutorAvailable'] == true) ...[
            Text('在孩子的学生端打开“作业与试卷”，选择“${s.title}”。'),
            const Text(
              'AI 老师会看原图、指出问题、讲解解法，孩子可用语音连续提问并自己订正。这里查看孩子的学习进度，无需填写题目或答案。',
              style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
            ),
            if (number(jsonMap(s.data['tutorSummary'])['readyTurnCount']) > 0)
              Text(
                'AI 老师已完成 ${number(jsonMap(s.data['tutorSummary'])['readyTurnCount'])} 次指导。指导与 AI 判断不计为已验证的独立掌握成绩。',
              ),
            const SizedBox(height: 8),
          ],
          if (s.studentCorrectionCount > 0) ...[
            Text(
              '孩子已订正 ${s.studentCorrectedCount} / ${s.studentCorrectionCount} 题',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (s.studentSelfReportedCompletedCount > 0)
              Text(
                '另有 ${s.studentSelfReportedCompletedCount} 题自行完成，未复测',
                style: const TextStyle(color: AppColors.mutedStrong),
              ),
            if (s.studentReadyCount > 0)
              Text('有 ${s.studentReadyCount} 道错题可以跟老师订正。'),
            if (s.studentPreparingCount > 0)
              Text('还有 ${s.studentPreparingCount} 道错题的图片和语音尚未准备好。'),
            if (s.studentUnsupportedCount > 0 &&
                s.data['tutorAvailable'] != true)
              Text('有 ${s.studentUnsupportedCount} 道错题暂不支持学生端自动讲解，已保留分析记录。'),
            if (s.data['tutorAvailable'] != true &&
                s.studentReadyCount +
                        s.studentPreparingCount +
                        s.studentCorrectedCount >
                    0) ...[
              const SizedBox(height: 8),
              Text('在孩子的学生端打开“作业与试卷”，选择“${s.title}”。'),
              const Text(
                'AI 老师会讲解、给提示，再让孩子自己作答。家长不需要输入正确答案。',
                style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
              ),
            ],
          ] else if (s.data['tutorAvailable'] != true)
            const Text('已识别的题目暂无需订正的错题。'),
          if (s.originalPaperSummary.isNotEmpty &&
              number(s.originalPaperSummary['incorrect']) > 0)
            Text(
              '有 ${number(s.originalPaperSummary['incorrect'])} 处 AI 批改建议订正，孩子在学生端跟老师一起看。',
              style: const TextStyle(color: AppColors.mutedStrong, height: 1.6),
            ),
          if (s.originalPaperSummary.isEmpty &&
              number(s.summary['pending']) > 0) ...[
            const SizedBox(height: 8),
            Text(
              s.data['tutorAvailable'] == true
                  ? '有 ${number(s.summary['pending'])} 处批改尚不确定，由学生端 AI 老师对照原图讲解。这些题不会直接计为错题。'
                  : '有 ${number(s.summary['pending'])} 处批改尚不确定，目前 AI 讲解尚未可用；无需家长填写答案，可稍后刷新查看。',
              style: const TextStyle(color: AppColors.mutedStrong, height: 1.6),
            ),
          ],
        ],
      ),
    );
  }
}

Color _paperColor(HomeworkItem item) => switch (item.displayPaperStatus) {
  'correct' => AppColors.success,
  'incorrect' => AppColors.danger,
  _ => AppColors.brandDeep,
};

class _AnnotatedPage extends ConsumerWidget {
  const _AnnotatedPage({
    required this.submission,
    required this.page,
    required this.items,
    required this.selectedId,
    required this.onSelect,
  });
  final HomeworkSubmission submission;
  final HomeworkPage page;
  final List<HomeworkItem> items;
  final String? selectedId;
  final ValueChanged<String> onSelect;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = (
      submissionId: submission.id,
      pageId: page.id,
      revision: submission.revision,
      original: false,
    );
    var ratio = page.rotation % 180 == 0
        ? page.aspectRatio
        : 1 / page.aspectRatio;
    final crop = jsonMap(page.data['crop']);
    if (crop.isNotEmpty) {
      ratio *= ((crop['width'] as num) / (crop['height'] as num));
    }
    return ref
        .watch(homeworkImageProvider(key))
        .when(
          loading: () => const LearningLoading(),
          error: (e, _) => LearningError(
            e,
            () => ref.invalidate(homeworkImageProvider(key)),
          ),
          data: (bytes) => ClipRRect(
            borderRadius: BorderRadius.circular(AppRadii.card),
            child: AspectRatio(
              aspectRatio: ratio,
              child: LayoutBuilder(
                builder: (context, size) => Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.memory(bytes, fit: BoxFit.fill),
                    for (var n = 0; n < items.length; n++)
                      if (items[n].region.isNotEmpty)
                        Positioned(
                          left:
                              (items[n].region['x'] as num).toDouble() *
                              size.maxWidth,
                          top:
                              (items[n].region['y'] as num).toDouble() *
                              size.maxHeight,
                          width:
                              (items[n].region['width'] as num).toDouble() *
                              size.maxWidth,
                          height:
                              (items[n].region['height'] as num).toDouble() *
                              size.maxHeight,
                          child: Semantics(
                            button: true,
                            label: '第 ${n + 1} 题，${items[n].statusLabel}',
                            child: GestureDetector(
                              onTap: () => onSelect(items[n].id),
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  color: AppColors.brandDeep.withValues(
                                    alpha: selectedId == items[n].id
                                        ? 0.18
                                        : 0.02,
                                  ),
                                  border: Border.all(
                                    color: selectedId == items[n].id
                                        ? AppColors.brandDeep
                                        : _paperColor(
                                            items[n],
                                          ).withValues(alpha: 0.8),
                                    width: selectedId == items[n].id ? 3 : 1,
                                  ),
                                ),
                                child: Align(
                                  alignment: Alignment.topLeft,
                                  child: ColoredBox(
                                    color: _paperColor(items[n]),
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 5,
                                        vertical: 2,
                                      ),
                                      child: Text(
                                        '${n + 1} ${items[n].hasProvisionalVerdict
                                            ? items[n].displayPaperStatus == 'correct'
                                                  ? '✓ 初判'
                                                  : '? 再看'
                                            : items[n].paperStatus == 'correct'
                                            ? '✓'
                                            : items[n].paperStatus == 'incorrect'
                                            ? '×'
                                            : '?'}',
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 12,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
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

class _ItemResult extends StatelessWidget {
  const _ItemResult({
    required this.item,
    required this.ordinal,
    required this.expanded,
    super.key,
  });
  final HomeworkItem item;
  final int ordinal;
  final bool expanded;
  @override
  Widget build(BuildContext context) {
    final d = item.data;
    final grading = item.gradingReference;
    final reference = !item.referenceAvailable
        ? ''
        : textValue(grading['referenceAnswer']).isNotEmpty
        ? textValue(grading['referenceAnswer'])
        : textValue(d['expectedAnswer']);
    final analysis = !item.referenceAvailable
        ? ''
        : textValue(grading['analysis']).isNotEmpty
        ? textValue(grading['analysis'])
        : textValue(d['explanation']);
    final knowledge = (grading['knowledgePoints'] is List
        ? (grading['knowledgePoints'] as List)
              .map(textValue)
              .where((v) => v.isNotEmpty)
              .join('、')
        : '');
    final hierarchy = jsonMap(d['sourceHierarchy']);
    final correction = item.correction;
    final guidance = item.latestTutorGuidance;
    final answerCount = number(hierarchy['answerCount']);
    final answerIndex = number(hierarchy['answerIndex']);
    return ExpansionTile(
      initiallyExpanded: expanded,
      tilePadding: EdgeInsets.zero,
      title: Text('$ordinal. ${item.prompt}'),
      subtitle: Text(
        '${item.statusLabel}${item.status == 'incorrect' && correction.status == 'corrected'
            ? ' · 孩子已订正'
            : correction.selfReportedCompleted
            ? ' · 自行完成，未复测'
            : ''}',
      ),
      expandedCrossAxisAlignment: CrossAxisAlignment.start,
      childrenPadding: const EdgeInsets.only(bottom: 12),
      children: [
        Text('孩子原作答：${item.answer.isEmpty ? '空白' : item.answer}'),
        if (item.hasProvisionalVerdict)
          const Text(
            '这是腾讯初判，尚未核验。请孩子在学生端跟老师看原图，家长无需填写正确答案。',
            style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
          ),
        if (answerCount > 1 && answerIndex > 0)
          Text('这道题的第 $answerIndex / $answerCount 个作答位置'),
        if (reference.isNotEmpty)
          Text(
            item.referenceGateStatus == 'human_verified'
                ? '核对参考答案：$reference'
                : grading['provider'] == 'tencent'
                ? '腾讯参考答案：$reference'
                : '正确答案：$reference',
          ),
        if (item.referenceGateStatus == 'provider_consistent')
          const Text(
            '以下是腾讯对原作答的批改建议和解析，用于订正参考，不代表孩子已独立掌握。',
            style: TextStyle(
              color: AppColors.mutedStrong,
              fontSize: 13,
              height: 1.6,
            ),
          ),
        if (knowledge.isNotEmpty)
          Text('知识点：$knowledge')
        else if (d['knowledgeLabel'] != null)
          Text('知识点：${textValue(d['knowledgeLabel'])}'),
        if (analysis.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(analysis, style: const TextStyle(height: 1.6)),
          ),
        if (correction.hasActivity) ...[
          const SizedBox(height: 12),
          Text('学生订正记录', style: Theme.of(context).textTheme.titleSmall),
          if (correction.selfReportedCompleted)
            const Text(
              '孩子已标记在纸上改好：自行完成，未复测。未记为答对，后续仍可复习核验。',
              style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
            ),
          if (correction.lastAnswer.isNotEmpty)
            Text('最近回答：${correction.lastAnswer} · ${correction.answerStatus}'),
          if (correction.attempts > 0) Text('已作答 ${correction.attempts} 次'),
          Text(
            [
              if (correction.hintViewed) '已看提示',
              if (correction.explanationViewed) '已展开解析',
              if (correction.tutorViewed) '已查看老师指导',
              if (!correction.hintViewed &&
                  !correction.explanationViewed &&
                  !correction.tutorViewed)
                '尚未记录查看提示或指导',
            ].join(' · '),
          ),
          const Text(
            '这是原题订正练习，不代表已独立掌握。后续需结合不同题目的独立作答判断。',
            style: TextStyle(
              color: AppColors.mutedStrong,
              fontSize: 13,
              height: 1.6,
            ),
          ),
        ],
        if (d['annotationAmbiguous'] == true)
          const Text('原作答可能被批注遮挡，AI 老师会在学生端对照原图讲解。'),
        if (guidance.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('老师最近指导：$guidance', style: const TextStyle(height: 1.6)),
                const Text(
                  '讲解与原卷批改分开记录，听过讲解不代表独立订正或掌握。',
                  style: TextStyle(
                    color: AppColors.mutedStrong,
                    fontSize: 13,
                    height: 1.6,
                  ),
                ),
              ],
            ),
          ),
        if (d['tutorEnabled'] == true)
          const Text(
            '孩子可在学生端看原题、听 AI 老师讲解，并继续用语音提问。',
            style: TextStyle(color: AppColors.mutedStrong, fontSize: 13),
          )
        else if (item.status == 'incorrect')
          Text(
            d['readyForStudent'] == true
                ? '学生端已可听讲解、看图订正。'
                : {'picture_choice', 'numeric'}.contains(d['answerMode'])
                ? '这道题的图片和语音尚未准备好，准备好后孩子可在学生端订正。'
                : '这道题暂不支持学生端自动讲解，已保留分析记录。',
            style: const TextStyle(color: AppColors.mutedStrong, fontSize: 13),
          ),
      ],
    );
  }
}
