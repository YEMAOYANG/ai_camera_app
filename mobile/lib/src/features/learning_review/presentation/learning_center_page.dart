import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/homework/application/homework_repository.dart';
import 'package:warm_sight/src/features/homework/application/homework_photo_picker.dart';
import 'package:warm_sight/src/features/homework/domain/homework_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import '../application/learning_review_repository.dart';
import '../domain/learning_review_models.dart';
import 'learning_support_widgets.dart';

class LearningCenterPage extends ConsumerWidget {
  const LearningCenterPage({this.childId, super.key});
  final String? childId;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (childId case final id? when id.isNotEmpty) return _Center(childId: id);
    final child = ref.watch(currentChildProvider);
    return child.when(
      data: (value) => value == null
          ? AppScreen(
              title: '学习与作业',
              onBack: () => learningBack(context),
              children: const [Text('请先在孩子资料中添加孩子。')],
            )
          : _Center(childId: value.id),
      loading: () => AppScreen(
        title: '学习与作业',
        onBack: () => learningBack(context),
        children: const [LearningLoading()],
      ),
      error: (e, _) => AppScreen(
        title: '学习与作业',
        onBack: () => learningBack(context),
        children: [
          LearningError(e, () => ref.invalidate(currentChildProvider)),
        ],
      ),
    );
  }
}

class _Center extends ConsumerStatefulWidget {
  const _Center({required this.childId});
  final String childId;
  @override
  ConsumerState<_Center> createState() => _CenterState();
}

class _CenterState extends ConsumerState<_Center> with WidgetsBindingObserver {
  Timer? _timer;
  ProviderSubscription<AsyncValue<List<HomeworkSubmission>>>? _subscription;
  bool _foreground = true, _navigating = false;
  String? _homeworkSyncError;
  String get childId => widget.childId;
  String get query => '?childId=${Uri.encodeQueryComponent(childId)}';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _listenHomework();
  }

  void _listenHomework() {
    _subscription = ref.listenManual(
      homeworkListProvider(childId),
      (old, next) => _poll(next.asData?.value),
      fireImmediately: true,
    );
  }

  @override
  void didUpdateWidget(_Center oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.childId != childId) {
      _timer?.cancel();
      _subscription?.close();
      _homeworkSyncError = null;
      _listenHomework();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _subscription?.close();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _timer?.cancel();
    _timer = null;
    if (_foreground && mounted && !_navigating) {
      unawaited(_refreshHomework());
    }
  }

  void _poll(List<HomeworkSubmission>? values) {
    _timer?.cancel();
    _timer = null;
    if (!mounted ||
        !_foreground ||
        _navigating ||
        values == null ||
        !values.any((value) => value.active)) {
      return;
    }
    _timer = Timer(const Duration(seconds: 4), () {
      if (mounted && _foreground && !_navigating) {
        unawaited(_refreshHomework());
      }
    });
  }

  Future<void> _refreshHomework() async {
    try {
      await ref.read(homeworkListProvider(childId).notifier).refresh();
      if (mounted) setState(() => _homeworkSyncError = null);
    } catch (error) {
      if (mounted) {
        setState(() => _homeworkSyncError = learningError(error));
      }
    } finally {
      if (mounted) {
        _poll(ref.read(homeworkListProvider(childId)).asData?.value);
      }
    }
  }

  Future<void> _refresh() async {
    ref.invalidate(reviewListProvider(childId));
    ref.invalidate(learningWeaknessesProvider(childId));
    await _refreshHomework();
  }

  Future<void> _open(String path) async {
    _navigating = true;
    _timer?.cancel();
    _timer = null;
    try {
      await context.push('$path$query');
    } finally {
      _navigating = false;
      if (mounted && _foreground) await _refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    final recovery = ref.watch(homeworkPhotoRecoveryProvider(childId));
    final reviews = ref.watch(reviewListProvider(childId));
    final homework = ref.watch(homeworkListProvider(childId));
    final weaknesses = ref.watch(learningWeaknessesProvider(childId));
    return AppScreen(
      title: '学习与作业',
      subtitle: '看见具体困难，让孩子自己练习',
      reserveBottomNavigation: false,
      onBack: () => learningBack(context),
      onRefresh: _refresh,
      children: [
        if (recovery.asData?.value case final id?)
          AppListRow(
            icon: Icons.restore,
            title: '继续上次选图',
            subtitle: '系统已恢复被中断的照片，点击继续上传',
            onTap: () =>
                _open('$homeworkDetailPath/${Uri.encodeComponent(id)}'),
          ),
        if (recovery.hasError)
          LearningError(
            recovery.error!,
            () => ref.invalidate(homeworkPhotoRecoveryProvider(childId)),
          ),
        AppListRow(
          icon: Icons.add_a_photo_outlined,
          title: '拍作业或试卷',
          subtitle: '家长上传照片，孩子在学生端跟老师订正',
          onTap: () => _open(homeworkCreatePath),
          trailing: const Icon(Icons.chevron_right),
        ),
        AppListRow(
          icon: Icons.photo_camera_back_outlined,
          title: '设备拍作业授权',
          subtitle: '指定任务、有效期与可用设备',
          onTap: () => _open(homeworkCaptureAuthorizationPath),
          trailing: const Icon(Icons.chevron_right),
        ),
        const Divider(),
        LearningHeading(
          '周末小复习',
          trailing: TextButton(
            onPressed: () => _open(reviewPreferencesPath),
            child: const Text(
              '安排设置',
              style: TextStyle(fontFamily: AppTypography.systemFont),
            ),
          ),
        ),
        reviews.when(
          loading: () => const LearningLoading(),
          error: (e, _) => LearningError(
            e,
            () => ref.invalidate(reviewListProvider(childId)),
          ),
          data: (items) => items.isEmpty
              ? const Text(
                  '本周还没有复习安排。系统会根据已完成课程的作答记录准备短复习。',
                  style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
                )
              : Column(
                  children: [
                    for (final run in items)
                      AppListRow(
                        icon: run.status == 'completed'
                            ? Icons.task_alt
                            : Icons.event_available_outlined,
                        title: run.title,
                        subtitle:
                            '${run.statusLabel} · ${learningDate(run.scheduledAt)}\n${run.questionCount} 题 · 约 ${run.estimatedMinutes} 分钟',
                        onTap: () => _open(
                          '$learningReviewDetailPath/${Uri.encodeComponent(run.id)}',
                        ),
                        trailing: const Icon(Icons.chevron_right),
                      ),
                  ],
                ),
        ),
        const LearningHeading('作业与试卷'),
        if (_homeworkSyncError != null)
          Text(
            '状态暂未更新。$_homeworkSyncError',
            style: const TextStyle(color: AppColors.danger, height: 1.6),
          ),
        homework.when(
          loading: () => const LearningLoading(),
          error: (e, _) =>
              LearningError(e, () => unawaited(_refreshHomework())),
          data: (items) => items.isEmpty
              ? const Text(
                  '还没有上传记录。先拍清楚整张纸，分析结果会保留在这里。',
                  style: TextStyle(color: AppColors.mutedStrong, height: 1.6),
                )
              : Column(
                  children: [
                    for (final item in items)
                      AppListRow(
                        icon: Icons.description_outlined,
                        title: item.title,
                        subtitle:
                            '${item.statusLabel} · ${item.pages.length} 页',
                        onTap: () => _open(
                          '$homeworkDetailPath/${Uri.encodeComponent(item.id)}',
                        ),
                        trailing: const Icon(Icons.chevron_right),
                      ),
                  ],
                ),
        ),
        const LearningHeading('薄弱点与进步'),
        const Text(
          '结合课堂、复习与已确认作业记录。看过提示、原题重做和独立完成会分别记录。',
          style: TextStyle(
            color: AppColors.mutedStrong,
            fontSize: 13,
            height: 1.6,
          ),
        ),
        weaknesses.when(
          loading: () => const LearningLoading(),
          error: (e, _) => LearningError(
            e,
            () => ref.invalidate(learningWeaknessesProvider(childId)),
          ),
          data: (items) => items.isEmpty
              ? const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text('还需要更多作答记录，暂不判断孩子的薄弱点。'),
                )
              : Column(children: items.map((e) => _Weakness(e)).toList()),
        ),
      ],
    );
  }
}

class _Weakness extends StatelessWidget {
  const _Weakness(this.value);
  final LearningWeakness value;
  @override
  Widget build(BuildContext context) {
    final d = value.data, e = value.example, q = jsonMap(e['question']);
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text(
        value.label,
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
      subtitle: Text(
        '${value.statusLabel} · ${number(d['sampleCount'])} 次已确认作答 · ${number(d['wrongCount'])} 次答错',
      ),
      childrenPadding: const EdgeInsets.only(bottom: 16),
      expandedCrossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '独立答对 ${number(d['independentCorrect'])} / ${number(d['independentCount'])} 次 · 使用帮助 ${number(d['helpCount'])} 次 · 待确认 ${number(d['pendingCount'])} 次',
        ),
        const SizedBox(height: 10),
        Text(
          '具体例子：${textValue(q['prompt'])}',
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        Text('孩子的作答：${learningAnswerLabel(e['answer'], q['options'])}'),
        Text(
          '来源：${const {'textbook_play': '互动课堂', 'classroom': '课程练习', 'weekly_review': '周末复习', 'review': '周末复习', 'homework': '作业检查'}[e['source']] ?? '学习记录'} · ${learningDate(e['occurredAt'] is num ? DateTime.fromMillisecondsSinceEpoch(number(e['occurredAt'])) : null)}',
          style: const TextStyle(color: AppColors.mutedStrong, fontSize: 12),
        ),
        const SizedBox(height: 10),
        Text(textValue(d['nextStep']), style: const TextStyle(height: 1.6)),
      ],
    );
  }
}
