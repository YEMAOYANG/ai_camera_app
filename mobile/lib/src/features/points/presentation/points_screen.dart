import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/points/application/point_settings.dart';
import 'package:warm_sight/src/features/points/domain/point_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/rewards/domain/reward_models.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_text_field.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

class PointsScreen extends ConsumerWidget {
  const PointsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final points = ref.watch(pointsSummaryProvider);
    final rewards = ref.watch(rewardsSummaryProvider);
    final pointSettingsValue = ref.watch(pointRewardSettingsProvider);
    final pointSettings =
        pointSettingsValue.asData?.value ?? PointRewardSettings.fallback;
    final pointSettingsReady = pointSettingsValue.asData?.value != null;
    final canManageRewards =
        ref.watch(profileSummaryProvider).asData?.value.can('manage_rewards') ??
        false;

    return AppScreen(
      title: '正向激励',
      subtitle: '${pointSettings.unitLabel}、阶段和奖励兑现',
      fixedHeader: true,
      backLabel: '返回我的',
      onBack: () => context.go(AppRoute.profile.path),
      trailing: AppIconButton(
        icon: Icons.card_giftcard_outlined,
        label: '奖励商店',
        onTap: () => context.go(rewardsPath),
      ),
      children: points.when(
        data: (data) {
          final rewardData = rewards.asData?.value;
          final activeItems = _activeRewardItems(rewardData?.items ?? const []);
          final pendingRedemptions = _pendingRedemptions(
            rewardData?.redemptions ?? const [],
          );
          final stage = _StageProgress.fromBalance(
            data.account.balance,
            threshold: pointSettings.stageThreshold,
          );
          final stageNoticePending = _stageNoticePending(data.account, stage);
          return [
            _IncentiveHero(
              summary: data,
              stage: stage,
              settings: pointSettings,
              stageNoticePending: stageNoticePending,
              pendingCount: pendingRedemptions.length,
              canManageRewards: canManageRewards,
              rewardsReady: rewardData != null,
              onOpenRewards: () => context.go(rewardsPath),
              onOpenRuleSettings: pointSettingsReady
                  ? () => _showPointRuleSheet(
                      context,
                      initialSettings: pointSettings,
                    )
                  : () => _showToast(context, '正在同步积分设置，请稍后再试。'),
              onStageHandle: () => _showStageFullSheet(
                context,
                ref,
                summary: data,
                stage: stage,
                settings: pointSettings,
                items: activeItems,
                canManage: canManageRewards,
              ),
              onRedeem: () => _showRedeemSheet(
                context,
                ref,
                items: activeItems,
                balance: data.account.balance,
                canManage: canManageRewards,
                settings: pointSettings,
              ),
              onAdjust: data.account.childId.isEmpty
                  ? () => _showToast(
                      context,
                      '还没有可调整的${pointSettings.unitLabel}账户，完成任务确认后会自动准备。',
                    )
                  : () =>
                        _showAdjustSheet(context, data.account, pointSettings),
            ),
            if (rewards.isLoading || pendingRedemptions.isNotEmpty) ...[
              const SizedBox(height: 14),
              _PendingRedemptionsPanel(
                redemptions: pendingRedemptions,
                settings: pointSettings,
                rewardsLoading: rewards.isLoading,
                onOpenRewards: () => context.go(rewardsPath),
              ),
            ],
            const SizedBox(height: 14),
            _RewardPreviewPanel(
              items: activeItems,
              balance: data.account.balance,
              settings: pointSettings,
              canManage: canManageRewards,
              rewardsLoading: rewards.isLoading,
              onOpenRewards: () => context.go(rewardsPath),
            ),
            const SizedBox(height: 10),
            _LedgerPanel(entries: data.ledger, settings: pointSettings),
          ];
        },
        loading: () => [_PointsLoading(settings: pointSettings)],
        error: (error, _) => [
          AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '${pointSettings.unitLabel}暂时没有更新',
            message: error is PointException ? error.message : '请稍后重试。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: () {
              ref
                ..invalidate(pointRewardSettingsProvider)
                ..invalidate(pointsSummaryProvider)
                ..invalidate(rewardsSummaryProvider);
            },
          ),
        ],
      ),
    );
  }
}

class _IncentiveHero extends StatelessWidget {
  const _IncentiveHero({
    required this.summary,
    required this.stage,
    required this.settings,
    required this.stageNoticePending,
    required this.pendingCount,
    required this.canManageRewards,
    required this.rewardsReady,
    required this.onOpenRewards,
    required this.onOpenRuleSettings,
    required this.onStageHandle,
    required this.onRedeem,
    required this.onAdjust,
  });

  final PointsSummary summary;
  final _StageProgress stage;
  final PointRewardSettings settings;
  final bool stageNoticePending;
  final int pendingCount;
  final bool canManageRewards;
  final bool rewardsReady;
  final VoidCallback onOpenRewards;
  final VoidCallback onOpenRuleSettings;
  final VoidCallback onStageHandle;
  final VoidCallback onRedeem;
  final VoidCallback onAdjust;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.surfaceElevated,
      borderColor: AppColors.borderSoft,
      radius: 24,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '当前${settings.unitLabel}',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
              StatusChip(label: '${stage.fullStages} 个阶段已满'),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${summary.account.balance}',
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 48,
              fontWeight: FontWeight.w900,
              height: 0.95,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 16),
          _StageDots(stage: stage),
          const SizedBox(height: 11),
          Text(
            '${settings.amount(settings.stageThreshold)}为一个阶段，本轮 ${settings.amount(stage.remainder)}/${settings.amount(settings.stageThreshold)}。',
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              height: 1.38,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _HeroActionTile(
                  icon: Icons.flag_outlined,
                  title: '阶段设置',
                  subtitle: '单位和阈值',
                  onTap: onOpenRuleSettings,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _HeroActionTile(
                  icon: Icons.redeem_outlined,
                  title: '主动兑换',
                  subtitle: rewardsReady ? '选择奖励' : '同步中',
                  onTap: canManageRewards && rewardsReady ? onRedeem : null,
                ),
              ),
            ],
          ),
          if (stageNoticePending || pendingCount > 0) ...[
            const SizedBox(height: 14),
            _ActionNotice(
              icon: pendingCount > 0
                  ? Icons.hourglass_bottom_outlined
                  : Icons.flag_outlined,
              title: pendingCount > 0
                  ? '$pendingCount 个兑换待处理'
                  : '已积满 ${stage.fullStages} 个阶段',
              subtitle: pendingCount > 0
                  ? '先兑现或取消，再继续承诺新的奖励。'
                  : '可以选择兑换奖励，也可以继续累计。',
              actionLabel: pendingCount > 0 ? '去奖励商店' : '处理',
              onAction: pendingCount > 0 ? onOpenRewards : onStageHandle,
            ),
          ],
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: AppSecondaryButton(
                  label: '补发或更正积分',
                  height: 42,
                  trailing: const Icon(Icons.tune_outlined, size: 17),
                  onTap: onAdjust,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeroActionTile extends StatelessWidget {
  const _HeroActionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Opacity(
        opacity: enabled ? 1 : 0.54,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceSoft,
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: AppColors.borderSoft),
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 11, 12, 11),
            child: Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: enabled
                        ? AppColors.brandWash
                        : AppColors.disabledFill,
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: SizedBox(
                    width: 36,
                    height: 36,
                    child: Center(
                      child: Icon(
                        icon,
                        color: enabled ? AppColors.brandDeep : AppColors.subtle,
                        size: 19,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 9),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 13,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 0,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.muted,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 11.5,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0,
                        ),
                      ),
                    ],
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

class _StageDots extends StatelessWidget {
  const _StageDots({required this.stage});

  final _StageProgress stage;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var index = 0; index < stage.threshold; index++) ...[
          Expanded(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: index < stage.remainder
                    ? AppColors.warning
                    : AppColors.border,
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
              child: const SizedBox(height: 9),
            ),
          ),
          if (index != stage.threshold - 1) const SizedBox(width: 5),
        ],
      ],
    );
  }
}

class _ActionNotice extends StatelessWidget {
  const _ActionNotice({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.actionLabel,
    this.onAction,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.warningWash.withValues(alpha: 0.58),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.warning.withValues(alpha: 0.10)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
        child: Row(
          children: [
            Icon(icon, color: AppColors.warning, size: 22),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.35,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            _InlineAction(label: actionLabel, onTap: onAction),
          ],
        ),
      ),
    );
  }
}

class _PendingRedemptionsPanel extends StatelessWidget {
  const _PendingRedemptionsPanel({
    required this.redemptions,
    required this.settings,
    required this.rewardsLoading,
    required this.onOpenRewards,
  });

  final List<RewardRedemption> redemptions;
  final PointRewardSettings settings;
  final bool rewardsLoading;
  final VoidCallback onOpenRewards;

  @override
  Widget build(BuildContext context) {
    if (rewardsLoading) {
      return const AppSurface(
        child: AppLoadingState(title: '正在同步兑现状态', message: '正在确认是否有待处理奖励。'),
      );
    }

    if (redemptions.isEmpty) {
      return const SizedBox.shrink();
    }

    final first = redemptions.first;
    return AppSurface(
      padding: const EdgeInsets.fromLTRB(16, 15, 16, 15),
      onTap: onOpenRewards,
      child: Row(
        children: [
          const _SoftIcon(
            icon: Icons.redeem_outlined,
            color: AppColors.warning,
            background: AppColors.warningWash,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  redemptions.length == 1
                      ? '待兑现：${first.rewardTitle}'
                      : '${redemptions.length} 个兑换待处理',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  '${settings.amount(first.pointsCost)} · 需要家长确认兑现',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12.5,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          const Icon(Icons.chevron_right, color: AppColors.muted, size: 19),
        ],
      ),
    );
  }
}

class _RewardPreviewPanel extends StatelessWidget {
  const _RewardPreviewPanel({
    required this.items,
    required this.balance,
    required this.settings,
    required this.canManage,
    required this.rewardsLoading,
    required this.onOpenRewards,
  });

  final List<RewardItem> items;
  final int balance;
  final PointRewardSettings settings;
  final bool canManage;
  final bool rewardsLoading;
  final VoidCallback onOpenRewards;

  @override
  Widget build(BuildContext context) {
    if (rewardsLoading) {
      return const AppSurface(
        child: AppLoadingState(title: '正在同步奖励商店', message: '正在读取可兑换奖励。'),
      );
    }

    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    final previewItems = items.take(3).toList();
    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PanelTitle(
            title: '可兑换奖励',
            trailing: _InlineAction(label: '全部', onTap: onOpenRewards),
          ),
          const SizedBox(height: 8),
          for (final item in previewItems)
            AppListRow(
              icon: _iconForReward(item),
              title: item.title,
              subtitle: item.description.isEmpty
                  ? '${settings.amount(item.pointsCost)}兑换'
                  : '${item.description} · ${settings.amount(item.pointsCost)}',
              tone: item.pointsCost <= balance
                  ? AppListRowTone.green
                  : AppListRowTone.amber,
              trailing: StatusChip(
                label: item.pointsCost <= balance
                    ? '可兑换'
                    : '差 ${item.pointsCost - balance}',
                tone: item.pointsCost <= balance
                    ? StatusTone.success
                    : StatusTone.warning,
              ),
              onTap: () => context.go('$rewardDetailPath/${item.id}'),
            ),
        ],
      ),
    );
  }
}

class _LedgerPanel extends StatelessWidget {
  const _LedgerPanel({required this.entries, required this.settings});

  final List<PointLedgerEntry> entries;
  final PointRewardSettings settings;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return AppStateView(
        variant: AppStateVariant.emptyLedger,
        title: '还没有积分流水',
        message: '家长确认任务或兑换奖励后，${settings.unitLabel}变化会显示在这里。',
        compact: true,
      );
    }

    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PanelTitle(title: '积分流水'),
          const SizedBox(height: 8),
          for (final entry in entries.take(5))
            AppListRow(
              icon: entry.delta >= 0
                  ? Icons.add_circle_outline
                  : Icons.remove_circle_outline,
              title: entry.typeLabel,
              subtitle: entry.note.isEmpty
                  ? '余额 ${settings.amount(entry.balanceAfter)}'
                  : '${entry.note} · 余额 ${settings.amount(entry.balanceAfter)}',
              tone: entry.delta >= 0
                  ? AppListRowTone.green
                  : AppListRowTone.amber,
              trailing: Text(
                '${entry.delta >= 0 ? '+' : ''}${entry.delta}',
                style: TextStyle(
                  color: entry.delta >= 0
                      ? AppColors.success
                      : AppColors.warning,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _PointsLoading extends StatelessWidget {
  const _PointsLoading({required this.settings});

  final PointRewardSettings settings;

  @override
  Widget build(BuildContext context) {
    return AppLoadingState(
      title: '正在同步${settings.unitLabel}',
      message: '正在整理余额、阶段和最近变化。',
    );
  }
}

class _PanelTitle extends StatelessWidget {
  const _PanelTitle({required this.title, this.trailing});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ),
        ?trailing,
      ],
    );
  }
}

class _SoftIcon extends StatelessWidget {
  const _SoftIcon({
    required this.icon,
    this.color = AppColors.brand,
    this.background = AppColors.brandWash,
  });

  final IconData icon;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(15),
      ),
      child: SizedBox(
        width: 42,
        height: 42,
        child: Center(child: Icon(icon, color: color, size: 21)),
      ),
    );
  }
}

class _InlineAction extends StatelessWidget {
  const _InlineAction({required this.label, required this.onTap});

  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Opacity(
        opacity: onTap == null ? 0.54 : 1,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surfaceElevated,
            borderRadius: BorderRadius.circular(AppRadii.full),
            border: Border.all(color: AppColors.borderSoft),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            child: Text(
              label,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _StageProgress {
  const _StageProgress({
    required this.threshold,
    required this.fullStages,
    required this.remainder,
    required this.toNextStage,
  });

  final int threshold;
  final int fullStages;
  final int remainder;
  final int toNextStage;

  factory _StageProgress.fromBalance(int rawBalance, {required int threshold}) {
    final balance = rawBalance < 0 ? 0 : rawBalance;
    final safeThreshold = threshold.clamp(1, 999);
    final remainder = balance % safeThreshold;
    return _StageProgress(
      threshold: safeThreshold,
      fullStages: balance ~/ safeThreshold,
      remainder: remainder,
      toNextStage: remainder == 0 ? safeThreshold : safeThreshold - remainder,
    );
  }
}

List<RewardItem> _activeRewardItems(List<RewardItem> items) {
  final activeItems = items.where((item) => item.available).toList();
  activeItems.sort((a, b) => a.pointsCost.compareTo(b.pointsCost));
  return activeItems;
}

List<RewardRedemption> _pendingRedemptions(List<RewardRedemption> redemptions) {
  return redemptions.where((redemption) => redemption.canFulfill).toList();
}

bool _stageNoticePending(PointAccount account, _StageProgress stage) {
  if (stage.fullStages <= 0) return false;
  final handled = account.stageNoticeHandledBalance;
  final effectiveHandled = handled > account.balance
      ? 0
      : handled.clamp(0, account.balance).toInt();
  return account.balance - effectiveHandled >= stage.threshold;
}

IconData _iconForReward(RewardItem item) {
  return switch (item.icon) {
    'book' => Icons.menu_book_outlined,
    'park' => Icons.park_outlined,
    'game' || 'sports' => Icons.sports_esports_outlined,
    _ => Icons.card_giftcard_outlined,
  };
}

void _showStageFullSheet(
  BuildContext context,
  WidgetRef ref, {
  required PointsSummary summary,
  required _StageProgress stage,
  required PointRewardSettings settings,
  required List<RewardItem> items,
  required bool canManage,
}) {
  showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.38,
    child: _StageFullSheet(
      hostContext: context,
      ref: ref,
      summary: summary,
      stage: stage,
      settings: settings,
      items: items,
      canManage: canManage,
    ),
  );
}

class _StageFullSheet extends StatefulWidget {
  const _StageFullSheet({
    required this.hostContext,
    required this.ref,
    required this.summary,
    required this.stage,
    required this.settings,
    required this.items,
    required this.canManage,
  });

  final BuildContext hostContext;
  final WidgetRef ref;
  final PointsSummary summary;
  final _StageProgress stage;
  final PointRewardSettings settings;
  final List<RewardItem> items;
  final bool canManage;

  @override
  State<_StageFullSheet> createState() => _StageFullSheetState();
}

class _StageFullSheetState extends State<_StageFullSheet> {
  var _savingContinue = false;

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: '${widget.settings.unitLabel}已积满',
      subtitle:
          '当前 ${widget.settings.amount(widget.summary.account.balance)}，按 ${widget.settings.amount(widget.settings.stageThreshold)}为一个阶段，已经积满 ${widget.stage.fullStages} 个阶段。家长可以现在兑换奖品，也可以继续累积到更大的奖励。',
      scrollable: false,
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: AppPrimaryButton(
                  label: '选择奖品',
                  onTap: widget.canManage && !_savingContinue
                      ? () {
                          Navigator.of(context).pop();
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            if (!widget.hostContext.mounted) return;
                            _showRedeemSheet(
                              widget.hostContext,
                              widget.ref,
                              items: widget.items,
                              balance: widget.summary.account.balance,
                              canManage: widget.canManage,
                              settings: widget.settings,
                            );
                          });
                        }
                      : null,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: AppSecondaryButton(
                  label: _savingContinue ? '处理中' : '继续累积',
                  onTap: widget.canManage && !_savingContinue
                      ? _continueAccumulating
                      : null,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          AppSecondaryButton(
            label: '调整阶段阈值',
            onTap: () {
              Navigator.of(context).pop();
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (!widget.hostContext.mounted) return;
                _showPointRuleSheet(
                  widget.hostContext,
                  initialSettings: widget.settings,
                );
              });
            },
          ),
        ],
      ),
    );
  }

  Future<void> _continueAccumulating() async {
    final childId = widget.summary.account.childId;
    if (childId.isEmpty) {
      showAppToast(context, '还没有可处理的积分账户。');
      return;
    }

    setState(() => _savingContinue = true);
    try {
      await widget.ref
          .read(pointRepositoryProvider)
          .acknowledgeStageNotice(childId: childId);
      widget.ref.invalidate(pointsSummaryProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      if (widget.hostContext.mounted) {
        showAppToast(widget.hostContext, '已继续累积，达到下一阶段再提醒。');
      }
    } on PointException catch (error) {
      if (mounted) showAppToast(context, error.message);
    } finally {
      if (mounted) setState(() => _savingContinue = false);
    }
  }
}

void _showPointRuleSheet(
  BuildContext context, {
  required PointRewardSettings initialSettings,
}) {
  showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.72,
    child: _PointRuleSheet(
      hostContext: context,
      initialSettings: initialSettings,
    ),
  );
}

class _PointRuleSheet extends ConsumerStatefulWidget {
  const _PointRuleSheet({
    required this.hostContext,
    required this.initialSettings,
  });

  final BuildContext hostContext;
  final PointRewardSettings initialSettings;

  @override
  ConsumerState<_PointRuleSheet> createState() => _PointRuleSheetState();
}

class _PointRuleSheetState extends ConsumerState<_PointRuleSheet> {
  late final TextEditingController _threshold;
  late PointRewardUnitOption _unit;
  String? _thresholdError;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    _threshold = TextEditingController(
      text: '${widget.initialSettings.stageThreshold}',
    );
    _unit = widget.initialSettings.unit;
  }

  @override
  void dispose() {
    _threshold.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final options = widget.initialSettings.unitOptions;
    return AppBottomSheetBody(
      title: '奖励阶段设置',
      subtitle: '先选择计量类型，再设置每个阶段需要的数量。达到阈值后提醒家长兑换或继续累积。',
      footer: AppPrimaryButton(
        label: _saving ? '保存中' : '保存设置',
        onTap: _saving ? null : _save,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '计量类型',
            style: TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              for (final option in options) ...[
                Expanded(
                  child: _UnitOption(
                    option: option,
                    selected: _unit.key == option.key,
                    onTap: () => setState(() => _unit = option),
                  ),
                ),
                if (option != options.last) const SizedBox(width: 8),
              ],
            ],
          ),
          const SizedBox(height: 16),
          AppTextField(
            label: '每个阶段需要',
            icon: Icons.flag_outlined,
            controller: _threshold,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            suffixIcon: Icons.stars_outlined,
            errorText: _thresholdError,
            onChanged: (_) {
              if (_thresholdError != null) {
                setState(() => _thresholdError = null);
              }
            },
          ),
          const SizedBox(height: 8),
          Text(
            '例如输入 10，就表示达到 ${_unitAmount(10)} 后提醒家长兑换或继续累积。',
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w600,
              height: 1.45,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }

  String _unitAmount(int value) {
    return PointRewardSettings(
      stageThreshold: 10,
      unit: _unit,
      unitOptions: widget.initialSettings.unitOptions,
    ).amount(value);
  }

  Future<void> _save() async {
    final threshold = int.tryParse(_threshold.text.trim()) ?? 0;
    setState(() {
      _thresholdError = threshold <= 0
          ? '请输入大于 0 的阶段阈值'
          : threshold > 99
          ? '阶段阈值不能超过 99'
          : null;
    });
    if (_thresholdError != null) return;

    setState(() => _saving = true);
    try {
      await ref
          .read(pointRewardSettingsRepositoryProvider)
          .save(stageThreshold: threshold, unit: _unit.key);
      ref.invalidate(pointRewardSettingsProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      if (widget.hostContext.mounted) {
        showAppToast(widget.hostContext, '奖励阶段设置已保存');
      }
    } on PointException catch (error) {
      if (mounted) showAppToast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _UnitOption extends StatelessWidget {
  const _UnitOption({
    required this.option,
    required this.selected,
    required this.onTap,
  });

  final PointRewardUnitOption option;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: selected ? AppColors.ink : AppColors.surfaceElevated,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? AppColors.ink : AppColors.borderSoft,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(8, 9, 8, 9),
          child: Column(
            children: [
              SizedBox(
                height: 54,
                child: option.imageAsset.isEmpty
                    ? Icon(
                        Icons.stars_outlined,
                        color: selected ? Colors.white : AppColors.brandDeep,
                      )
                    : Image.asset(option.imageAsset, fit: BoxFit.contain),
              ),
              const SizedBox(height: 8),
              Text(
                option.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: selected ? Colors.white : AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                option.suffix,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: selected
                      ? Colors.white.withValues(alpha: 0.72)
                      : AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

void _showAdjustSheet(
  BuildContext context,
  PointAccount account,
  PointRewardSettings settings,
) {
  showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.58,
    child: _PointsAdjustSheet(account: account, settings: settings),
  );
}

enum _PointAdjustMode { add, deduct }

class _PointsAdjustSheet extends ConsumerStatefulWidget {
  const _PointsAdjustSheet({required this.account, required this.settings});

  final PointAccount account;
  final PointRewardSettings settings;

  @override
  ConsumerState<_PointsAdjustSheet> createState() => _PointsAdjustSheetState();
}

class _PointsAdjustSheetState extends ConsumerState<_PointsAdjustSheet> {
  final _amount = TextEditingController();
  final _note = TextEditingController();
  var _mode = _PointAdjustMode.add;
  String? _amountError;
  var _saving = false;

  @override
  void dispose() {
    _amount.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: '补发或更正积分',
      subtitle: '用于家长临时补发或扣回${widget.settings.unitLabel}，调整记录会保留在流水里。',
      footer: AppPrimaryButton(
        label: _saving
            ? '处理中'
            : _mode == _PointAdjustMode.add
            ? '确认补发'
            : '确认扣回',
        onTap: _saving ? null : _submit,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _AdjustModeButton(
                  label: '补发',
                  icon: Icons.add_circle_outline,
                  selected: _mode == _PointAdjustMode.add,
                  onTap: () => setState(() {
                    _mode = _PointAdjustMode.add;
                    _amountError = null;
                  }),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _AdjustModeButton(
                  label: '扣回',
                  icon: Icons.remove_circle_outline,
                  selected: _mode == _PointAdjustMode.deduct,
                  danger: true,
                  onTap: () => setState(() {
                    _mode = _PointAdjustMode.deduct;
                    _amountError = null;
                  }),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          AppTextField(
            label: '${widget.settings.unitLabel}数量',
            icon: Icons.tune_outlined,
            controller: _amount,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            hintText: '请输入需要调整的数量',
            suffixIcon: Icons.stars_outlined,
            errorText: _amountError,
            onChanged: (_) {
              if (_amountError != null) setState(() => _amountError = null);
            },
          ),
          const SizedBox(height: 8),
          Text(
            _mode == _PointAdjustMode.deduct
                ? '当前余额 ${widget.settings.amount(widget.account.balance)}，扣回不能超过当前余额。'
                : '补发数量不固定，适合补记漏发或临时表扬。',
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w600,
              height: 1.45,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 14),
          AppTextField(
            label: '调整说明',
            icon: Icons.notes_outlined,
            controller: _note,
            hintText: _mode == _PointAdjustMode.add ? '例如：补记阅读奖励' : '例如：更正重复发放',
          ),
        ],
      ),
    );
  }

  Future<void> _submit() async {
    final amount = int.tryParse(_amount.text.trim()) ?? 0;
    setState(() {
      _amountError = amount <= 0
          ? '请输入大于 0 的数量'
          : _mode == _PointAdjustMode.deduct && amount > widget.account.balance
          ? '扣回数量不能超过当前余额'
          : null;
    });
    if (_amountError != null) return;

    final delta = _mode == _PointAdjustMode.add ? amount : -amount;
    if (delta < 0) {
      final confirmed = await showAppConfirmSheet(
        context: context,
        title: '扣回${widget.settings.unitLabel}',
        message: '确认从孩子账户扣回 ${widget.settings.amount(amount)}？扣回后会保留调整流水。',
        confirmLabel: '确认扣回',
        cancelLabel: '先不扣回',
        danger: true,
      );
      if (!confirmed) return;
    }

    setState(() => _saving = true);
    try {
      await ref
          .read(pointRepositoryProvider)
          .adjust(
            childId: widget.account.childId,
            delta: delta,
            note: _note.text.trim().isEmpty
                ? delta > 0
                      ? '家长手动补发'
                      : '家长更正扣回'
                : _note.text.trim(),
          );
      ref.invalidate(pointsSummaryProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      _showToast(context, '${widget.settings.unitLabel}已调整');
    } on PointException catch (error) {
      if (mounted) _showToast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _AdjustModeButton extends StatelessWidget {
  const _AdjustModeButton({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
    this.danger = false,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger ? AppColors.danger : AppColors.success;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: selected ? AppColors.ink : AppColors.surfaceElevated,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? AppColors.ink : AppColors.borderSoft,
          ),
        ),
        child: SizedBox(
          height: 48,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18, color: selected ? Colors.white : color),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  color: selected ? Colors.white : AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

void _showRedeemSheet(
  BuildContext context,
  WidgetRef ref, {
  required List<RewardItem> items,
  required int balance,
  required bool canManage,
  required PointRewardSettings settings,
}) {
  if (!canManage) {
    _showToast(context, '当前角色只能查看${settings.unitLabel}，不能发起兑换。');
    return;
  }

  showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: items.isEmpty ? 0.44 : 0.64,
    child: _RedeemSheet(
      ref: ref,
      items: items,
      balance: balance,
      settings: settings,
    ),
  );
}

class _RedeemSheet extends StatelessWidget {
  const _RedeemSheet({
    required this.ref,
    required this.items,
    required this.balance,
    required this.settings,
  });

  final WidgetRef ref;
  final List<RewardItem> items;
  final int balance;
  final PointRewardSettings settings;

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: '主动兑换',
      subtitle: '家长可以把当前${settings.unitLabel}兑换成一个待兑现奖励。',
      scrollable: items.isNotEmpty,
      child: items.isEmpty
          ? const Center(
              child: Padding(
                padding: EdgeInsets.fromLTRB(0, 4, 0, 10),
                child: AppStateView(
                  variant: AppStateVariant.emptyRewards,
                  title: '还没有可兑换奖励',
                  message: '先去奖励商店添加奖励项，再回到这里兑换。',
                  compact: true,
                ),
              ),
            )
          : Column(
              children: [
                for (final item in items)
                  AppListRow(
                    icon: _iconForReward(item),
                    title: item.title,
                    subtitle: item.description.isEmpty
                        ? settings.amount(item.pointsCost)
                        : '${settings.amount(item.pointsCost)} · ${item.description}',
                    tone: item.pointsCost <= balance
                        ? AppListRowTone.green
                        : AppListRowTone.amber,
                    trailing: StatusChip(
                      label: item.pointsCost <= balance ? '兑换' : '不足',
                      tone: item.pointsCost <= balance
                          ? StatusTone.success
                          : StatusTone.warning,
                    ),
                    onTap: () => _redeem(context, ref, item, balance, settings),
                  ),
              ],
            ),
    );
  }
}

Future<void> _redeem(
  BuildContext context,
  WidgetRef ref,
  RewardItem item,
  int balance,
  PointRewardSettings settings,
) async {
  if (item.pointsCost > balance) {
    _showToast(context, '${settings.unitLabel}还不够兑换「${item.title}」。');
    return;
  }
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '兑换奖励',
    message:
        '将使用 ${settings.amount(item.pointsCost)}兑换「${item.title}」，并生成待兑现记录。',
    confirmLabel: '确认兑换',
    cancelLabel: '先不兑换',
  );
  if (!confirmed) return;

  try {
    await ref.read(rewardRepositoryProvider).createRedemption(item.id);
    ref
      ..invalidate(pointsSummaryProvider)
      ..invalidate(rewardsSummaryProvider)
      ..invalidate(rewardRedemptionsProvider);
    if (context.mounted) {
      Navigator.of(context).pop();
      _showToast(context, '已生成待兑现奖励');
    }
  } on RewardException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

void _showToast(BuildContext context, String message) {
  showAppToast(context, message);
}
