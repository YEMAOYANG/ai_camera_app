import 'package:flutter/material.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class LearningPreparationCard extends StatelessWidget {
  const LearningPreparationCard({
    required this.preparation,
    this.onRefresh,
    this.onRetry,
    this.retrying = false,
    this.awaitingPublication = false,
    super.key,
  });

  final LearningPreparation preparation;
  final VoidCallback? onRefresh;
  final VoidCallback? onRetry;
  final bool retrying;
  final bool awaitingPublication;

  @override
  Widget build(BuildContext context) {
    final stage = _stagePresentation(preparation);
    final canRestart =
        preparation.isFailed && preparation.canRetry && onRetry != null;
    final supplyPaused = preparation.courseSupply?.paused == true;
    final supplyDelayed = preparation.courseSupply?.delayed == true;
    final title = supplyPaused
        ? '新课准备暂时停在这里'
        : supplyDelayed
        ? '新课准备时间较长'
        : awaitingPublication
        ? '正在发布今日课程'
        : preparation.isReady
        ? '学习空间已准备'
        : preparation.isFailed
        ? canRestart
              ? '课程准备需要重新启动'
              : '本次课程准备已暂停'
        : preparation.status == 'superseded'
        ? '年级已变更'
        : '首门课程准备好就能学';
    final displayStageLabel = supplyPaused
        ? '等待恢复'
        : awaitingPublication
        ? '正式发布校验中'
        : stage.label;
    final statusLabel = '课程状态，$displayStageLabel';
    final safeMessage = supplyPaused || supplyDelayed
        ? preparation.courseSupply!.message
        : awaitingPublication
        ? '课程已准备好，正在做最后检查，完成后会自动出现在“今日学习”。'
        : preparation.isReady
        ? '每天会按孩子的年级和学习进度自动安排语文、数学和英语课程。'
        : preparation.isFailed
        ? canRestart
              ? '本次准备已安全停止，可以重新发起课程准备。'
              : '为避免重复生成，系统没有自动重试。本次计划需要重新发起课程准备。'
        : preparation.status == 'superseded'
        ? '已停止旧年级课程准备，系统会按新年级自动安排。'
        : '老师正在为${preparation.gradeLabel}准备课程，准备好后会自动更新。之后每天安排 3 节小课，内容每天轮换。';
    final action = canRestart ? onRetry : onRefresh;
    final checking = canRestart && retrying;
    final actionLabel = canRestart ? '重新准备课程' : '检查状态';

    return Semantics(
      container: true,
      explicitChildNodes: true,
      liveRegion: true,
      label: statusLabel,
      child: AppSurface(
        color: stage.surface,
        borderColor: stage.border,
        radius: AppRadii.cardLarge,
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 15),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _PreparationMark(
                    icon: stage.icon,
                    foreground: stage.foreground,
                    background: stage.markBackground,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: _titleStyle),
                        const SizedBox(height: 7),
                        Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: StatusChip(
                            label: displayStageLabel,
                            tone: stage.tone,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            if (preparation.status != 'superseded') ...[
              const SizedBox(height: 16),
              LearningPreparationProgress(
                preparation: preparation,
                awaitingPublication: awaitingPublication,
              ),
            ],
            if (safeMessage.trim().isNotEmpty) ...[
              const SizedBox(height: 13),
              Text(safeMessage, style: _bodyStyle),
            ],
            if (action != null && preparation.isFailed) ...[
              const SizedBox(height: 15),
              Semantics(
                container: true,
                button: true,
                enabled: !checking,
                label: checking ? '正在重新准备课程' : actionLabel,
                onTap: checking ? null : action,
                child: ExcludeSemantics(
                  child: AppSecondaryButton(
                    key: const ValueKey('learningPreparationRefresh'),
                    label: checking ? '正在重新准备' : actionLabel,
                    trailing: checking
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : null,
                    onTap: checking ? null : action,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class LearningPreparationProgress extends StatelessWidget {
  const LearningPreparationProgress({
    required this.preparation,
    this.awaitingPublication = false,
    super.key,
  });

  final LearningPreparation preparation;
  final bool awaitingPublication;

  @override
  Widget build(BuildContext context) {
    final percent = preparation.progressPercent.clamp(
      0,
      preparation.isReady && !awaitingPublication ? 100 : 99,
    );
    final paused =
        preparation.isFailed || preparation.courseSupply?.paused == true;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(paused ? '准备已暂停' : '新课准备进度', style: _bodyStrongStyle),
            ),
            Text('$percent%', style: _titleStyle),
          ],
        ),
        const SizedBox(height: 9),
        LinearProgressIndicator(
          value: percent / 100,
          minHeight: 8,
          borderRadius: BorderRadius.circular(AppRadii.cardLarge),
          backgroundColor: AppColors.brandWash,
          color: paused ? AppColors.muted : AppColors.brand,
          semanticsLabel: paused ? '课程准备已暂停' : '新课准备进度',
          semanticsValue: '$percent%',
        ),
        const SizedBox(height: 7),
        const Text('整批新课的准备进度，每完成一节就能先学。', style: _bodyStyle),
      ],
    );
  }
}

class LearningPreparationLoadingCard extends StatelessWidget {
  const LearningPreparationLoadingCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      explicitChildNodes: true,
      liveRegion: true,
      label: '正在获取课程准备状态',
      child: AppSurface(
        radius: AppRadii.cardLarge,
        child: Row(
          children: [
            Semantics(
              container: true,
              label: '课程准备状态加载中',
              child: ExcludeSemantics(
                child: SizedBox(
                  width: 22,
                  height: 22,
                  child: CircularProgressIndicator(strokeWidth: 2.2),
                ),
              ),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: ExcludeSemantics(
                child: Text('正在获取课程准备状态…', style: _bodyStrongStyle),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class LearningPreparationNetworkErrorCard extends StatelessWidget {
  const LearningPreparationNetworkErrorCard({required this.onRetry, super.key});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return _PreparationNoticeCard(
      icon: Icons.cloud_off_outlined,
      title: '课程状态暂时无法同步',
      message: '请检查网络后重新获取，这不会重复发起课程准备。',
      actionLabel: '重新获取状态',
      semanticsLabel: '课程准备状态同步失败',
      onAction: onRetry,
    );
  }
}

class LearningPreparationMissingCard extends StatelessWidget {
  const LearningPreparationMissingCard({required this.onRefresh, super.key});

  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return _PreparationNoticeCard(
      icon: Icons.school_outlined,
      title: '正在同步年级课程',
      message: '保存年级后会在后台逐门生成，完成一门就能先学；之后每天自动安排 3 门，内容每天轮换。',
      actionLabel: '检查状态',
      semanticsLabel: '正在同步年级课程',
      onAction: onRefresh,
    );
  }
}

class _PreparationNoticeCard extends StatelessWidget {
  const _PreparationNoticeCard({
    required this.icon,
    required this.title,
    required this.message,
    required this.actionLabel,
    required this.semanticsLabel,
    required this.onAction,
  });

  final IconData icon;
  final String title;
  final String message;
  final String actionLabel;
  final String semanticsLabel;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      explicitChildNodes: true,
      liveRegion: true,
      label: semanticsLabel,
      child: AppSurface(
        radius: AppRadii.cardLarge,
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 15),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _PreparationMark(
                    icon: icon,
                    foreground: AppColors.brandDeep,
                    background: AppColors.brandWash,
                  ),
                  const SizedBox(width: 12),
                  Expanded(child: Text(title, style: _titleStyle)),
                ],
              ),
            ),
            const SizedBox(height: 11),
            Semantics(
              container: true,
              label: message,
              child: ExcludeSemantics(child: Text(message, style: _bodyStyle)),
            ),
            const SizedBox(height: 15),
            Semantics(
              container: true,
              button: true,
              enabled: true,
              label: '检查课程状态',
              onTap: onAction,
              child: ExcludeSemantics(
                child: AppSecondaryButton(label: actionLabel, onTap: onAction),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PreparationMark extends StatelessWidget {
  const _PreparationMark({
    required this.icon,
    required this.foreground,
    required this.background,
  });

  final IconData icon;
  final Color foreground;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppRadii.control),
      ),
      child: SizedBox(
        width: 42,
        height: 42,
        child: Icon(icon, size: 22, color: foreground),
      ),
    );
  }
}

({
  String label,
  StatusTone tone,
  IconData icon,
  Color foreground,
  Color surface,
  Color border,
  Color markBackground,
})
_stagePresentation(LearningPreparation preparation) {
  if (!preparation.supportedStage) {
    return (
      label: '课程状态待更新',
      tone: StatusTone.warning,
      icon: Icons.sync_problem_outlined,
      foreground: AppColors.warning,
      surface: AppColors.brandWarmWash,
      border: AppColors.warning.withValues(alpha: 0.18),
      markBackground: AppColors.warningWash,
    );
  }
  if (preparation.isReady) {
    return (
      label: '可开始学习',
      tone: StatusTone.success,
      icon: Icons.check_circle_outline,
      foreground: AppColors.success,
      surface: AppColors.brandSageWash,
      border: AppColors.success.withValues(alpha: 0.16),
      markBackground: AppColors.successWash,
    );
  }
  if (preparation.isFailed) {
    return (
      label: '后台处理中',
      tone: StatusTone.warning,
      icon: Icons.schedule_outlined,
      foreground: AppColors.warning,
      surface: AppColors.brandWarmWash.withValues(alpha: 0.65),
      border: AppColors.warning.withValues(alpha: 0.14),
      markBackground: AppColors.warningWash,
    );
  }

  final label = switch (preparation.stage) {
    LearningPreparationStage.retryWait => '稍后继续',
    LearningPreparationStage.completed =>
      preparation.status == 'superseded' ? '年级已变更' : '准备完成',
    _ => '后台准备中',
  };
  return (
    label: label,
    tone: preparation.stage == LearningPreparationStage.retryWait
        ? StatusTone.warning
        : StatusTone.neutral,
    icon: preparation.stage == LearningPreparationStage.retryWait
        ? Icons.schedule_outlined
        : Icons.auto_stories_outlined,
    foreground: preparation.stage == LearningPreparationStage.retryWait
        ? AppColors.warning
        : AppColors.brandDeep,
    surface: preparation.stage == LearningPreparationStage.retryWait
        ? AppColors.brandWarmWash.withValues(alpha: 0.65)
        : AppColors.brandWash.withValues(alpha: 0.54),
    border: preparation.stage == LearningPreparationStage.retryWait
        ? AppColors.warning.withValues(alpha: 0.14)
        : AppColors.brand.withValues(alpha: 0.12),
    markBackground: preparation.stage == LearningPreparationStage.retryWait
        ? AppColors.warningWash
        : AppColors.brandWash,
  );
}

const _titleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 16,
  fontWeight: FontWeight.w700,
  height: 1.32,
);

const _bodyStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 13,
  fontWeight: FontWeight.w500,
  height: 1.5,
);

const _bodyStrongStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w600,
  height: 1.4,
);
