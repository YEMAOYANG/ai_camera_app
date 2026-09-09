import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/home_shared.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/learning/domain/learning_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/learning_preparation_card.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class HomePrimaryLearningPreview extends ConsumerStatefulWidget {
  const HomePrimaryLearningPreview({required this.child, super.key});

  final ChildProfile child;

  @override
  ConsumerState<HomePrimaryLearningPreview> createState() =>
      _HomePrimaryLearningPreviewState();
}

class _HomePrimaryLearningPreviewState
    extends ConsumerState<HomePrimaryLearningPreview>
    with WidgetsBindingObserver {
  Timer? _pollTimer;
  AppLifecycleState _lifecycleState = AppLifecycleState.resumed;
  String? _scheduledPlanId;
  int? _scheduledUpdatedAt;
  var _pollRefreshInFlight = false;
  var _pollSyncFailed = false;
  var _retrying = false;
  LearningPreparation? _lastSuccessfulPreparation;
  LearningAvailability? _lastSuccessfulAvailability;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _lifecycleState =
        WidgetsBinding.instance.lifecycleState ?? AppLifecycleState.resumed;
  }

  @override
  void didUpdateWidget(covariant HomePrimaryLearningPreview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.child.id != widget.child.id ||
        oldWidget.child.gradeCode != widget.child.gradeCode) {
      _cancelPoll();
      _retrying = false;
      _pollSyncFailed = false;
      _lastSuccessfulPreparation = null;
      _lastSuccessfulAvailability = null;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _lifecycleState = state;
    _cancelPoll();
  }

  @override
  void dispose() {
    _cancelPoll();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _cancelPoll() {
    _pollTimer?.cancel();
    _pollTimer = null;
    _scheduledPlanId = null;
    _scheduledUpdatedAt = null;
  }

  void _handlePreparationState(
    AsyncValue<LearningPreparation?>? _,
    AsyncValue<LearningPreparation?> next,
  ) {
    final fresh = next.asData?.value;
    if (fresh != null) {
      final last = _lastSuccessfulPreparation;
      _lastSuccessfulPreparation = fresh;
      _pollSyncFailed = false;
      if (last != null && !last.isReady && fresh.isReady) {
        final gradeCode = _lastSuccessfulAvailability?.gradeCode;
        if (gradeCode != null && gradeCode.isNotEmpty) {
          ref.invalidate(
            todayLearningProvider((
              childId: widget.child.id,
              gradeCode: gradeCode,
            )),
          );
        }
      }
    }
    if (next.isLoading || next.hasError) {
      _cancelPoll();
      return;
    }
    final value = next.asData?.value;
    if (value?.shouldPoll != true ||
        _lifecycleState != AppLifecycleState.resumed) {
      _cancelPoll();
      return;
    }
    if (_pollTimer?.isActive == true &&
        _scheduledPlanId == value!.id &&
        _scheduledUpdatedAt == value.updatedAt) {
      return;
    }
    _cancelPoll();
    _scheduledPlanId = value!.id;
    _scheduledUpdatedAt = value.updatedAt;
    _pollTimer = Timer(value.retryAfter, _runScheduledPoll);
  }

  void _schedulePollRetry(LearningPreparation value) {
    if (_lifecycleState != AppLifecycleState.resumed || !value.shouldPoll) {
      return;
    }
    _cancelPoll();
    _scheduledPlanId = value.id;
    _scheduledUpdatedAt = value.updatedAt;
    _pollTimer = Timer(const Duration(seconds: 30), _runScheduledPoll);
  }

  void _runScheduledPoll() {
    _pollTimer = null;
    _scheduledPlanId = null;
    _scheduledUpdatedAt = null;
    if (!mounted || _lifecycleState != AppLifecycleState.resumed) return;
    unawaited(_refreshPreparationFromPoll());
  }

  Future<void> _refreshPreparationFromPoll() async {
    if (!mounted || _lifecycleState != AppLifecycleState.resumed) return;
    setState(() => _pollRefreshInFlight = true);
    var failed = false;
    try {
      final _ = await ref.refresh(
        currentLearningPreparationProvider(widget.child.id).future,
      );
    } catch (_) {
      failed = true;
    }
    try {
      final _ = await ref.refresh(
        currentLearningAvailabilityProvider(widget.child.id).future,
      );
    } catch (_) {
      failed = true;
    } finally {
      if (mounted) {
        setState(() {
          _pollRefreshInFlight = false;
          _pollSyncFailed = failed;
        });
        if (failed) {
          final snapshot = _lastSuccessfulPreparation;
          if (snapshot != null) _schedulePollRetry(snapshot);
        }
      }
    }
  }

  Future<void> _refreshPreparation() async {
    var failed = false;
    try {
      final _ = await ref.refresh(
        currentLearningPreparationProvider(widget.child.id).future,
      );
    } catch (_) {
      failed = true;
    }
    try {
      final _ = await ref.refresh(
        currentLearningAvailabilityProvider(widget.child.id).future,
      );
    } catch (_) {
      failed = true;
    }
    if (mounted) {
      setState(() => _pollSyncFailed = failed);
    }
  }

  Future<void> _retryPreparation(LearningPreparation preparation) async {
    if (_retrying) return;
    setState(() => _retrying = true);
    final requestId =
        'parent-prep-retry:${preparation.id}:${DateTime.now().millisecondsSinceEpoch}';
    try {
      await ref
          .read(learningPreparationRepositoryProvider)
          .retry(planId: preparation.id, requestId: requestId);
      final _ = await ref.refresh(
        currentLearningPreparationProvider(widget.child.id).future,
      );
      final _ = await ref.refresh(
        currentLearningAvailabilityProvider(widget.child.id).future,
      );
    } catch (error) {
      var reconciled = false;
      try {
        final current = await ref.refresh(
          currentLearningPreparationProvider(widget.child.id).future,
        );
        reconciled = current != null && current.id != preparation.id;
      } catch (_) {
        // Preserve the original safe error when reconciliation is unavailable.
      }
      if (mounted && !reconciled) {
        _notice(_preparationErrorMessage(error), error: true);
      }
    } finally {
      if (mounted) setState(() => _retrying = false);
    }
  }

  void _notice(String message, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? AppColors.danger : AppColors.ink,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AsyncValue<ProfileSummary>>(profileSummaryProvider, (
      previous,
      next,
    ) {
      if (next.isLoading || next.hasError) _cancelPoll();
    });
    final provider = currentLearningPreparationProvider(widget.child.id);
    final availabilityProvider = currentLearningAvailabilityProvider(
      widget.child.id,
    );
    ref.listen<AsyncValue<LearningPreparation?>>(
      provider,
      _handlePreparationState,
    );
    ref.listen<AsyncValue<LearningAvailability>>(availabilityProvider, (
      previous,
      next,
    ) {
      final value = next.asData?.value;
      if (value != null) _lastSuccessfulAvailability = value;
    });
    final preparation = ref.watch(provider);
    final availability = ref.watch(availabilityProvider);
    if (preparation.hasValue) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _handlePreparationState(null, preparation);
      });
    }
    if (availability.hasValue) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final value = availability.asData?.value;
        if (mounted && value != null) _lastSuccessfulAvailability = value;
      });
    }
    final currentPreparation =
        preparation.asData?.value ??
        ((_pollRefreshInFlight || _pollSyncFailed)
            ? _lastSuccessfulPreparation
            : null);
    final currentAvailability =
        availability.asData?.value ?? _lastSuccessfulAvailability;
    final availabilityMatchesChild =
        currentAvailability?.gradeCode == widget.child.gradeCode;
    final hasActiveRelease =
        availabilityMatchesChild &&
        currentAvailability?.hasActiveRelease == true;
    final canLearnNow =
        availabilityMatchesChild && currentAvailability?.canLearnNow == true;
    final preservePollingProgress =
        _pollRefreshInFlight &&
        preparation.isRefreshing &&
        currentPreparation?.shouldPoll == true;
    final readySubtitle = canLearnNow
        ? '${widget.child.grade.isEmpty ? '小学' : widget.child.grade} · 语文、数学、英语智能轮换'
        : null;
    return Column(
      key: const ValueKey('primaryLearningPreview'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        HomeSectionTitle(title: '今日学习', subtitle: readySubtitle),
        const SizedBox(height: 10),
        if (currentAvailability == null && availability.isLoading)
          const LearningPreparationLoadingCard()
        else if (currentAvailability == null || !availabilityMatchesChild)
          LearningPreparationNetworkErrorCard(
            onRetry: () => unawaited(_refreshPreparation()),
          )
        else if (canLearnNow) ...[
          _ReadyPrimaryLearningPreview(
            child: widget.child,
            gradeCode: currentAvailability.gradeCode,
          ),
          if (currentPreparation?.shouldPoll == true) ...[
            const SizedBox(height: 9),
            _BackgroundPreparationHint(
              syncDelayed: _pollSyncFailed,
              hasActiveRelease: hasActiveRelease,
              availableCourseCount: currentAvailability.availableCourseCount,
            ),
          ],
        ] else if (preparation.isLoading && !preservePollingProgress)
          const LearningPreparationLoadingCard()
        else if (preparation.hasError && currentPreparation == null)
          LearningPreparationNetworkErrorCard(
            onRetry: () => unawaited(_refreshPreparation()),
          )
        else if (currentPreparation == null)
          LearningPreparationMissingCard(
            onRefresh: () => unawaited(_refreshPreparation()),
          )
        else ...[
          LearningPreparationCard(
            preparation: currentPreparation,
            awaitingPublication: currentPreparation.isReady,
            onRefresh: () => unawaited(_refreshPreparation()),
            onRetry: currentPreparation.canRetry
                ? () => unawaited(_retryPreparation(currentPreparation))
                : null,
            retrying: _retrying,
          ),
          if (_pollSyncFailed) ...[
            const SizedBox(height: 9),
            const _PreparationSyncDelayedHint(),
          ],
        ],
      ],
    );
  }
}

class _ReadyPrimaryLearningPreview extends ConsumerStatefulWidget {
  const _ReadyPrimaryLearningPreview({
    required this.child,
    required this.gradeCode,
  });

  final ChildProfile child;
  final String gradeCode;

  @override
  ConsumerState<_ReadyPrimaryLearningPreview> createState() =>
      _ReadyPrimaryLearningPreviewState();
}

class _ReadyPrimaryLearningPreviewState
    extends ConsumerState<_ReadyPrimaryLearningPreview>
    with WidgetsBindingObserver {
  var _working = false;
  var _syncing = false;
  Timer? _resultSyncTimer;

  LearningTodayRequestKey get _todayKey =>
      (childId: widget.child.id, gradeCode: widget.gradeCode);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _scheduleResultSync();
  }

  void _scheduleResultSync() {
    _resultSyncTimer?.cancel();
    _resultSyncTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      unawaited(_syncResult());
    });
  }

  Future<void> _syncResult() async {
    if (!mounted || _syncing || ModalRoute.of(context)?.isCurrent == false) {
      return;
    }
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    if (lifecycle != null && lifecycle != AppLifecycleState.resumed) return;
    _syncing = true;
    try {
      final _ = await ref.refresh(todayLearningProvider(_todayKey).future);
    } catch (_) {
      // Keep the last result visible; foreground polling and WS can retry.
    } finally {
      _syncing = false;
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _resultSyncTimer?.cancel();
    if (state == AppLifecycleState.resumed) {
      _scheduleResultSync();
      unawaited(_syncResult());
    }
  }

  @override
  void dispose() {
    _resultSyncTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final today = ref.watch(todayLearningProvider(_todayKey));
    return today.when(
      skipLoadingOnRefresh: true,
      skipError: true,
      loading: () => const _LearningLoadingCard(),
      error: (error, _) =>
          _LearningErrorCard(message: _errorMessage(error), onRetry: _refresh),
      data: _buildTodayContent,
    );
  }

  Widget _buildTodayContent(LearningToday day) {
    final items = day.items.isEmpty ? [day] : day.items;
    return Column(
      children: [
        for (var index = 0; index < items.length; index++) ...[
          if (index > 0) const SizedBox(height: 10),
          _buildTodayCard(items[index]),
        ],
      ],
    );
  }

  Widget _buildTodayCard(LearningToday today) {
    return switch (today.state) {
      LearningTodayState.preparing => _LearningPreparingCard(today: today),
      LearningTodayState.recommended => _LearningTodayCard(
        today: today,
        statusLabel: '课程已就绪',
        tone: StatusTone.neutral,
      ),
      LearningTodayState.scheduled => _LearningTodayCard(
        today: today,
        statusLabel: '今日课程已准备',
        tone: StatusTone.neutral,
      ),
      LearningTodayState.inProgress => _LearningTodayCard(
        today: today,
        statusLabel: '学习中',
        tone: StatusTone.warning,
      ),
      LearningTodayState.completed => _LearningTodayCard(
        today: today,
        statusLabel: '已完成',
        tone: StatusTone.success,
        actionLabel: '查看学习报告',
        actionLoading: _working,
        onAction: _working ? null : () => _showReport(today),
      ),
      LearningTodayState.unavailable => _LearningEmptyCard(
        message: today.message,
        onRetry: _refresh,
      ),
    };
  }

  void _refresh() {
    ref.invalidate(todayLearningProvider(_todayKey));
  }

  Future<void> _showReport(LearningToday today) async {
    setState(() => _working = true);
    try {
      final report =
          today.report ??
          await ref
              .read(learningRepositoryProvider)
              .latestReport(
                widget.child.id,
                subject: today.lesson?.subjectCode,
              );
      if (!mounted) return;
      await _showLearningReportSheet(context, report);
    } catch (error) {
      if (mounted) _notice(_errorMessage(error), error: true);
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  void _notice(String message, {bool error = false}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? AppColors.danger : AppColors.ink,
      ),
    );
  }
}

class _BackgroundPreparationHint extends StatelessWidget {
  const _BackgroundPreparationHint({
    required this.syncDelayed,
    required this.hasActiveRelease,
    required this.availableCourseCount,
  });

  final bool syncDelayed;
  final bool hasActiveRelease;
  final int availableCourseCount;

  @override
  Widget build(BuildContext context) {
    final availableText = hasActiveRelease
        ? '现有课程可正常使用'
        : '已就绪 $availableCourseCount 门课程';
    final message = syncDelayed
        ? '$availableText，进度同步稍慢，已保留上次结果'
        : '$availableText，新课准备好后会自动出现';
    return Text(message, style: _backgroundHintStyle);
  }
}

class _PreparationSyncDelayedHint extends StatelessWidget {
  const _PreparationSyncDelayedHint();

  @override
  Widget build(BuildContext context) {
    return const Text('状态同步稍慢，已保留上次进度并将在后台重试。', style: _backgroundHintStyle);
  }
}

String _preparationErrorMessage(Object error) {
  if (error is LearningPreparationException) return error.message;
  return '课程重新准备失败，请稍后重试';
}

class _LearningLoadingCard extends StatelessWidget {
  const _LearningLoadingCard();

  @override
  Widget build(BuildContext context) {
    return const HomeSoftPanel(
      child: SizedBox(
        height: 116,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2.2),
              ),
              SizedBox(height: 10),
              Text('正在准备今日适龄课程…'),
            ],
          ),
        ),
      ),
    );
  }
}

class _LearningErrorCard extends StatelessWidget {
  const _LearningErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return HomeSoftPanel(
      tone: StatusTone.danger,
      child: Row(
        children: [
          const HomeToneIcon(
            icon: Icons.cloud_off_outlined,
            tone: StatusTone.danger,
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('今日课程加载失败', style: _cardTitleStyle),
                const SizedBox(height: 4),
                Text(message, style: _cardBodyStyle),
              ],
            ),
          ),
          TextButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    );
  }
}

class _LearningEmptyCard extends StatelessWidget {
  const _LearningEmptyCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return HomeSoftPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              HomeToneIcon(
                icon: Icons.auto_stories_outlined,
                tone: StatusTone.neutral,
              ),
              SizedBox(width: 11),
              Expanded(child: Text('今天暂时没有可用课程', style: _cardTitleStyle)),
            ],
          ),
          const SizedBox(height: 9),
          Text(
            message.isEmpty ? '课程服务正在根据孩子年级准备内容，请稍后刷新。' : message,
            style: _cardBodyStyle,
          ),
          const SizedBox(height: 12),
          AppSecondaryButton(label: '重新获取课程', onTap: onRetry),
        ],
      ),
    );
  }
}

class _LearningPreparingCard extends StatelessWidget {
  const _LearningPreparingCard({required this.today});

  final LearningToday today;

  @override
  Widget build(BuildContext context) {
    final slotLabel = switch (today.slot) {
      'rotation' => '今日第 2 课',
      'extension' => '今日第 3 课',
      _ => '今日第 1 课',
    };
    return HomeSoftPanel(
      child: Row(
        children: [
          const HomeToneIcon(
            icon: Icons.hourglass_top_rounded,
            tone: StatusTone.neutral,
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$slotLabel · 准备中', style: _cardTitleStyle),
                const SizedBox(height: 4),
                Text(
                  today.message.isEmpty ? '完成正式发布校验后会自动出现在这里。' : today.message,
                  style: _cardBodyStyle,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _LearningTodayCard extends StatelessWidget {
  const _LearningTodayCard({
    required this.today,
    required this.statusLabel,
    required this.tone,
    this.actionLabel,
    this.actionLoading = false,
    this.onAction,
  });

  final LearningToday today;
  final String statusLabel;
  final StatusTone tone;
  final String? actionLabel;
  final bool actionLoading;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final lesson = today.lesson;
    final report = today.report;
    final title = lesson?.title.isNotEmpty == true
        ? lesson!.title
        : report?.summary.isNotEmpty == true
        ? report!.summary
        : '今日能力练习';
    final skill = lesson?.skill ?? '';
    final subjectLabel = _subjectLabel(lesson);
    final slotLabel = switch (today.slot) {
      'rotation' => '今日第 2 课',
      'extension' => '今日第 3 课',
      _ => '今日第 1 课',
    };
    return HomeSoftPanel(
      tone: tone,
      padding: const EdgeInsets.fromLTRB(15, 14, 15, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              HomeToneIcon(icon: _subjectIcon(lesson), tone: tone),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$slotLabel · $subjectLabel',
                      style: _metricLabelStyle,
                    ),
                    const SizedBox(height: 3),
                    Text(title, style: _cardTitleStyle),
                    if (skill.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text('能力目标：$skill', style: _cardBodyStyle),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              StatusChip(label: statusLabel, tone: tone),
            ],
          ),
          const SizedBox(height: 13),
          if (today.state == LearningTodayState.completed && report != null)
            _ReportMetrics(report: report)
          else
            Row(
              children: [
                Expanded(
                  child: _LearningMetric(
                    label: '预计时长',
                    value: lesson?.estimatedMinutes == 0
                        ? '约 10 分钟'
                        : '${lesson?.estimatedMinutes} 分钟',
                    icon: Icons.schedule_outlined,
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: _LearningMetric(
                    label: '练习数量',
                    value: lesson?.questionCount == 0
                        ? '按掌握度调整'
                        : '${lesson?.questionCount} 题',
                    icon: Icons.fact_check_outlined,
                  ),
                ),
              ],
            ),
          if (today.needsPreparationRetry) ...[
            const SizedBox(height: 10),
            Text(
              '${today.preparationError}。推荐课程已保留，可直接重试准备。',
              key: const ValueKey('learningPreparationError'),
              style: const TextStyle(
                color: AppColors.danger,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w600,
                height: 1.4,
              ),
            ),
          ],
          if (actionLabel != null) ...[
            const SizedBox(height: 12),
            AppPrimaryButton(
              key: ValueKey('learningPrimaryAction_${today.slot}'),
              label: actionLabel!,
              loading: actionLoading,
              onTap: onAction,
            ),
            const SizedBox(height: 9),
          ] else
            const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.videocam_outlined,
                size: 16,
                color: AppColors.muted,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '课程在学生学习空间完成；家长端只展示准备状态与学习结果。',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 11.5,
                    fontWeight: FontWeight.w600,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

String _subjectLabel(LearningLesson? lesson) {
  if (lesson == null) return '综合';
  if (lesson.subject.isNotEmpty && lesson.subject != lesson.subjectCode) {
    return lesson.subject;
  }
  return switch (lesson.subjectCode) {
    'chinese' => '语文',
    'math' => '数学',
    'english' => '英语',
    _ => lesson.subject.isEmpty ? '综合' : lesson.subject,
  };
}

IconData _subjectIcon(LearningLesson? lesson) {
  return switch (lesson?.subjectCode) {
    'chinese' => Icons.menu_book_outlined,
    'math' => Icons.calculate_outlined,
    'english' => Icons.translate_outlined,
    _ => Icons.auto_stories_outlined,
  };
}

class _LearningMetric extends StatelessWidget {
  const _LearningMetric({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
        child: Row(
          children: [
            Icon(icon, size: 17, color: AppColors.brandDeep),
            const SizedBox(width: 7),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: _metricLabelStyle),
                  const SizedBox(height: 2),
                  Text(
                    value,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: _metricValueStyle,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ReportMetrics extends StatelessWidget {
  const _ReportMetrics({required this.report});

  final LearningReport report;

  @override
  Widget build(BuildContext context) {
    if (!report.isScored) {
      return const _LearningMetric(
        label: '活动结果',
        value: '已参与并完成',
        icon: Icons.task_alt_outlined,
      );
    }
    return Row(
      children: [
        Expanded(
          child: _LearningMetric(
            label: '首次独立答对',
            value: '${report.independentCorrectCount} 题',
            icon: Icons.check_circle_outline,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _LearningMetric(
            label: '掌握情况',
            value: report.masteryDisplayLabel.isEmpty
                ? '已完成'
                : report.masteryDisplayLabel,
            icon: Icons.insights_outlined,
          ),
        ),
      ],
    );
  }
}

class _LearningReportContent extends StatelessWidget {
  const _LearningReportContent({required this.report});

  final LearningReport report;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const ValueKey('learningReport'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ReportMetrics(report: report),
        const SizedBox(height: 14),
        if (report.summary.isNotEmpty)
          _ReportParagraph(title: '本次总结', content: report.summary),
        if (report.nextSuggestion.isNotEmpty) ...[
          const SizedBox(height: 10),
          _ReportParagraph(title: '下一步建议', content: report.nextSuggestion),
        ],
      ],
    );
  }
}

class _ReportParagraph extends StatelessWidget {
  const _ReportParagraph({required this.title, required this.content});

  final String title;
  final String content;

  @override
  Widget build(BuildContext context) {
    return HomeSoftPanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: _cardTitleStyle),
          const SizedBox(height: 6),
          Text(content, style: _cardBodyStyle),
        ],
      ),
    );
  }
}

class _InlineState extends StatelessWidget {
  const _InlineState({
    required this.icon,
    required this.title,
    required this.detail,
  });

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 36, color: AppColors.brandDeep),
            const SizedBox(height: 12),
            Text(title, style: _cardTitleStyle),
            const SizedBox(height: 6),
            Text(detail, textAlign: TextAlign.center, style: _cardBodyStyle),
          ],
        ),
      ),
    );
  }
}

Future<void> _showLearningReportSheet(
  BuildContext context,
  LearningReport? report,
) {
  return showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.74,
    child: AppBottomSheetBody(
      title: '最近一次学习报告',
      subtitle: '报告由真实答题记录生成，不使用示例数据。',
      footer: AppPrimaryButton(
        label: '知道了',
        onTap: () => Navigator.of(context, rootNavigator: true).pop(),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (report == null)
            const _InlineState(
              icon: Icons.description_outlined,
              title: '报告还在生成',
              detail: '稍后回到首页即可重新查看。',
            )
          else
            _LearningReportContent(report: report),
        ],
      ),
    ),
  );
}

String _errorMessage(Object error) {
  if (error is LearningException) return error.message;
  return '学习服务暂时不可用，请稍后再试';
}

const _cardTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 15,
  fontWeight: FontWeight.w900,
  height: 1.25,
);

const _cardBodyStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 12.5,
  fontWeight: FontWeight.w600,
  height: 1.45,
);

const _metricLabelStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 10.5,
  fontWeight: FontWeight.w600,
);

const _backgroundHintStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 11.5,
  fontWeight: FontWeight.w600,
  height: 1.35,
);

const _metricValueStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 12.5,
  fontWeight: FontWeight.w800,
);
