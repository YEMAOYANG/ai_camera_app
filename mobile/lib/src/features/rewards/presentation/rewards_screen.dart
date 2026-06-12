import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/points/application/point_settings.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/application/reward_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/domain/reward_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_text_field.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class RewardsScreen extends ConsumerWidget {
  const RewardsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(rewardsSummaryProvider);
    final points = ref.watch(pointsSummaryProvider);
    final pointSettingsValue = ref.watch(pointRewardSettingsProvider);
    final pointSettings =
        pointSettingsValue.asData?.value ?? PointRewardSettings.fallback;
    final canManageRewards =
        ref.watch(profileSummaryProvider).asData?.value.can('manage_rewards') ??
        false;

    return AppScreen(
      title: '奖励商店',
      subtitle: '兑换、兑现和奖励建议',
      fixedHeader: true,
      backLabel: '返回我的',
      onBack: () => context.go(AppRoute.profile.path),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (canManageRewards)
            AppIconButton(
              icon: Icons.add,
              label: '新增积分商品',
              onTap: () => _showRewardItemSheet(context, pointSettings),
            ),
        ],
      ),
      children: [
        _RewardBalancePanel(
          balance: points.asData?.value.account.balance,
          settings: pointSettings,
          pointsLoading: points.isLoading,
          redemptions: summary.asData?.value.redemptions ?? const [],
          onOpenPoints: () => context.go(pointsPath),
        ),
        const SizedBox(height: 14),
        ...summary.when(
          data: (data) {
            final activeItems = _activeRewardItems(data.items);
            final pending = _pendingRedemptions(data.redemptions);
            return [
              if (pending.isNotEmpty) ...[
                _PendingRedemptionsPanel(
                  redemptions: pending,
                  settings: pointSettings,
                  canManage: canManageRewards,
                ),
                const SizedBox(height: 14),
              ],
              const _RewardSuggestionPanel(),
              if (activeItems.isNotEmpty) ...[
                const SizedBox(height: 14),
                _RewardItemsPanel(
                  items: activeItems,
                  settings: pointSettings,
                  balance: points.asData?.value.account.balance ?? 0,
                  pointsReady: points.asData?.value != null,
                ),
              ],
              if (data.redemptions.isNotEmpty) const SizedBox(height: 14),
              _RedemptionsPanel(
                redemptions: data.redemptions,
                settings: pointSettings,
                canManage: canManageRewards,
              ),
            ];
          },
          loading: () => const [_RewardsLoading()],
          error: (error, _) => [
            AppStateView(
              variant: AppStateVariant.serviceUnavailable,
              title: '奖励暂时没有更新',
              message: error is RewardException ? error.message : '请稍后重试。',
              primaryActionLabel: '重新加载',
              onPrimaryAction: () => ref.invalidate(rewardsSummaryProvider),
            ),
          ],
        ),
      ],
    );
  }
}

class _RewardBalancePanel extends StatelessWidget {
  const _RewardBalancePanel({
    required this.balance,
    required this.settings,
    required this.pointsLoading,
    required this.redemptions,
    required this.onOpenPoints,
  });

  final int? balance;
  final PointRewardSettings settings;
  final bool pointsLoading;
  final List<RewardRedemption> redemptions;
  final VoidCallback onOpenPoints;

  @override
  Widget build(BuildContext context) {
    final value = balance ?? 0;
    final threshold = settings.stageThreshold;
    final fullStages = value ~/ threshold;
    final remainder = value % threshold;
    final pendingCount = _pendingRedemptions(redemptions).length;

    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 17),
      onTap: onOpenPoints,
      child: Stack(
        children: [
          Positioned(
            right: -34,
            top: -48,
            width: 156,
            height: 156,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    AppColors.warning.withValues(alpha: 0.23),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.10),
                      borderRadius: BorderRadius.circular(17),
                    ),
                    child: const SizedBox(
                      width: 50,
                      height: 50,
                      child: Center(
                        child: Icon(
                          Icons.redeem_outlined,
                          color: Color(0xFFFDBA74),
                          size: 24,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 13),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          pointsLoading
                              ? '正在同步${settings.unitLabel}'
                              : '当前可兑换${settings.unitLabel}',
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.66),
                            fontFamily: AppTypography.systemFont,
                            fontSize: 12,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0,
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          pointsLoading ? '同步中' : settings.amount(value),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontFamily: AppTypography.systemFont,
                            fontSize: 25,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: _CompactStageDots(
                      threshold: threshold,
                      remainder: remainder,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    '$fullStages 阶段',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.72),
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                pendingCount > 0
                    ? '$pendingCount 个兑换待兑现，先处理再承诺新的奖励。'
                    : '兑换由家长确认并手动兑现，不自动承诺奖励。',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.62),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  height: 1.42,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CompactStageDots extends StatelessWidget {
  const _CompactStageDots({required this.threshold, required this.remainder});

  final int threshold;
  final int remainder;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var index = 0; index < threshold; index++) ...[
          Expanded(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: index < remainder
                    ? const Color(0xFFFDBA74)
                    : Colors.white.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
              child: const SizedBox(height: 7),
            ),
          ),
          if (index != threshold - 1) const SizedBox(width: 4),
        ],
      ],
    );
  }
}

class _PendingRedemptionsPanel extends ConsumerWidget {
  const _PendingRedemptionsPanel({
    required this.redemptions,
    required this.settings,
    required this.canManage,
  });

  final List<RewardRedemption> redemptions;
  final PointRewardSettings settings;
  final bool canManage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppSurface(
      color: AppColors.warningWash.withValues(alpha: 0.56),
      borderColor: AppColors.warning.withValues(alpha: 0.12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PanelTitle(title: '兑换记录', meta: '待兑现 ${redemptions.length} 个'),
          const SizedBox(height: 8),
          for (final redemption in redemptions)
            AppListRow(
              icon: Icons.redeem_outlined,
              title: redemption.rewardTitle,
              subtitle:
                  '${settings.amount(redemption.pointsCost)} · ${redemption.status.label}',
              tone: AppListRowTone.amber,
              trailing: canManage
                  ? Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _ActionPill(
                          label: '取消',
                          danger: true,
                          onTap: () =>
                              _cancel(context, ref, redemption, settings),
                        ),
                        const SizedBox(width: 7),
                        _ActionPill(
                          label: '兑现',
                          highlight: true,
                          onTap: () => _fulfill(context, ref, redemption),
                        ),
                      ],
                    )
                  : StatusChip(
                      label: redemption.status.label,
                      tone: redemption.status.tone,
                    ),
              onTap: () =>
                  context.go('$rewardDetailPath/${redemption.rewardItemId}'),
            ),
        ],
      ),
    );
  }
}

class _RewardSuggestionPanel extends StatelessWidget {
  const _RewardSuggestionPanel();

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          _PanelTitle(title: '奖励建议', meta: '先轻后重'),
          SizedBox(height: 10),
          _SuggestionItem(
            icon: Icons.diversity_1_outlined,
            title: '亲子活动',
            subtitle: '一起阅读、散步、桌游，优先承接阶段奖励。',
            tone: AppListRowTone.green,
          ),
          _SuggestionItem(
            icon: Icons.workspace_premium_outlined,
            title: '小特权',
            subtitle: '周末菜单选择、睡前故事选择，边界清楚。',
            tone: AppListRowTone.blue,
          ),
          _SuggestionItem(
            icon: Icons.inventory_2_outlined,
            title: '物质奖励限量',
            subtitle: '贴纸、文具、小玩具只作补充，不做唯一目标。',
            tone: AppListRowTone.amber,
          ),
        ],
      ),
    );
  }
}

class _SuggestionItem extends StatelessWidget {
  const _SuggestionItem({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.tone,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final AppListRowTone tone;

  @override
  Widget build(BuildContext context) {
    return AppListRow(icon: icon, title: title, subtitle: subtitle, tone: tone);
  }
}

class _RewardItemsPanel extends StatelessWidget {
  const _RewardItemsPanel({
    required this.items,
    required this.settings,
    required this.balance,
    required this.pointsReady,
  });

  final List<RewardItem> items;
  final PointRewardSettings settings;
  final int balance;
  final bool pointsReady;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PanelTitle(title: '可兑换奖励', meta: '${items.length} 项'),
          const SizedBox(height: 8),
          for (final item in items)
            AppListRow(
              icon: _iconForReward(item),
              title: item.title,
              subtitle: item.description.isEmpty
                  ? '${settings.amount(item.pointsCost)}兑换'
                  : '${item.description} · ${settings.amount(item.pointsCost)}',
              tone: item.pointsCost <= balance
                  ? AppListRowTone.green
                  : AppListRowTone.blue,
              trailing: StatusChip(
                label: !pointsReady
                    ? '同步中'
                    : item.pointsCost <= balance
                    ? '可兑换'
                    : '差 ${item.pointsCost - balance}',
                tone: !pointsReady
                    ? StatusTone.neutral
                    : item.pointsCost <= balance
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

class _RedemptionsPanel extends ConsumerWidget {
  const _RedemptionsPanel({
    required this.redemptions,
    required this.settings,
    required this.canManage,
  });

  final List<RewardRedemption> redemptions;
  final PointRewardSettings settings;
  final bool canManage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (redemptions.isEmpty) {
      return const AppStateView(
        variant: AppStateVariant.emptyRewards,
        title: '还没有兑换记录',
        message: '兑换奖励后，兑现进度会在这里清楚展示。',
        compact: true,
      );
    }

    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PanelTitle(title: '兑现历史'),
          const SizedBox(height: 8),
          for (final redemption in redemptions.take(6))
            AppListRow(
              icon: Icons.history_outlined,
              title: redemption.rewardTitle,
              subtitle:
                  '${settings.amount(redemption.pointsCost)} · ${redemption.status.label}',
              tone: redemption.status == RedemptionStatus.fulfilled
                  ? AppListRowTone.green
                  : redemption.status == RedemptionStatus.cancelled
                  ? AppListRowTone.neutral
                  : AppListRowTone.amber,
              trailing: redemption.canFulfill && canManage
                  ? Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _ActionPill(
                          label: '取消',
                          danger: true,
                          onTap: () =>
                              _cancel(context, ref, redemption, settings),
                        ),
                        const SizedBox(width: 7),
                        _ActionPill(
                          label: '兑现',
                          highlight: true,
                          onTap: () => _fulfill(context, ref, redemption),
                        ),
                      ],
                    )
                  : StatusChip(
                      label: redemption.status.label,
                      tone: redemption.status.tone,
                    ),
            ),
        ],
      ),
    );
  }
}

class _PanelTitle extends StatelessWidget {
  const _PanelTitle({required this.title, this.meta});

  final String title;
  final String? meta;

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
        if (meta != null) StatusChip(label: meta!, tone: StatusTone.neutral),
      ],
    );
  }
}

class _ActionPill extends StatelessWidget {
  const _ActionPill({
    required this.label,
    required this.onTap,
    this.highlight = false,
    this.danger = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool highlight;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: danger
              ? AppColors.dangerWash
              : highlight
              ? AppColors.brandWash
              : AppColors.surfaceSoft,
          borderRadius: BorderRadius.circular(AppRadii.full),
          border: Border.all(
            color: danger
                ? AppColors.danger.withValues(alpha: 0.16)
                : highlight
                ? AppColors.brand.withValues(alpha: 0.18)
                : AppColors.borderSoft,
          ),
        ),
        child: SizedBox(
          height: AppControls.buttonHeight,
          child: Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 10),
              child: Text(
                label,
                style: TextStyle(
                  color: danger
                      ? AppColors.danger
                      : highlight
                      ? AppColors.brandDeep
                      : AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: danger ? FontWeight.w800 : FontWeight.w600,
                  letterSpacing: 0,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RewardsLoading extends StatelessWidget {
  const _RewardsLoading();

  @override
  Widget build(BuildContext context) {
    return const AppLoadingState(title: '正在同步奖励', message: '正在整理奖励项和兑现进度。');
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

IconData _iconForReward(RewardItem item) {
  return switch (item.icon) {
    'book' => Icons.menu_book_outlined,
    'park' => Icons.park_outlined,
    'game' || 'sports' => Icons.sports_esports_outlined,
    _ => Icons.card_giftcard_outlined,
  };
}

Future<void> _fulfill(
  BuildContext context,
  WidgetRef ref,
  RewardRedemption redemption,
) async {
  try {
    await ref.read(rewardRepositoryProvider).fulfillRedemption(redemption.id);
    ref
      ..invalidate(rewardsSummaryProvider)
      ..invalidate(rewardRedemptionsProvider);
    if (context.mounted) _showToast(context, '已标记为兑现');
  } on RewardException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _cancel(
  BuildContext context,
  WidgetRef ref,
  RewardRedemption redemption,
  PointRewardSettings settings,
) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '取消兑换',
    message:
        '确认取消「${redemption.rewardTitle}」？取消后${settings.unitLabel}会返还到孩子账户。',
    confirmLabel: '确认取消',
    cancelLabel: '先不取消',
    danger: true,
  );
  if (!confirmed) return;

  try {
    await ref.read(rewardRepositoryProvider).cancelRedemption(redemption.id);
    ref
      ..invalidate(rewardsSummaryProvider)
      ..invalidate(rewardRedemptionsProvider)
      ..invalidate(pointsSummaryProvider);
    if (context.mounted) _showToast(context, '已取消兑换，${settings.unitLabel}已返还');
  } on RewardException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

void _showToast(BuildContext context, String message) {
  showAppToast(context, message);
}

void _showRewardItemSheet(BuildContext context, PointRewardSettings settings) {
  showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.76,
    child: _RewardItemCreateSheet(toastContext: context, settings: settings),
  );
}

class _RewardItemCreateSheet extends ConsumerStatefulWidget {
  const _RewardItemCreateSheet({
    required this.toastContext,
    required this.settings,
  });

  final BuildContext toastContext;
  final PointRewardSettings settings;

  @override
  ConsumerState<_RewardItemCreateSheet> createState() =>
      _RewardItemCreateSheetState();
}

class _RewardItemCreateSheetState
    extends ConsumerState<_RewardItemCreateSheet> {
  final _title = TextEditingController();
  final _cost = TextEditingController(text: '10');
  final _description = TextEditingController();
  String? _titleError;
  String? _costError;
  var _saving = false;

  @override
  void dispose() {
    _title.dispose();
    _cost.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: '新增积分商品',
      subtitle: '用于孩子用${widget.settings.unitLabel}兑换，保存后会出现在奖励商店。',
      footer: AppPrimaryButton(
        label: _saving ? '保存中' : '保存商品',
        trailing: const AppButtonGlyph(icon: Icons.check),
        onTap: _saving ? null : _save,
      ),
      child: Column(
        children: [
          AppTextField(
            label: '商品名称',
            icon: Icons.card_giftcard_outlined,
            controller: _title,
            hintText: '例如：周末亲子游戏 20 分钟',
            errorText: _titleError,
            onChanged: (_) {
              if (_titleError != null) setState(() => _titleError = null);
            },
          ),
          const SizedBox(height: 12),
          AppTextField(
            label: '所需${widget.settings.unitLabel}',
            icon: Icons.stars_outlined,
            controller: _cost,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            hintText: '例如：10',
            errorText: _costError,
            onChanged: (_) {
              if (_costError != null) setState(() => _costError = null);
            },
          ),
          const SizedBox(height: 12),
          AppTextField(
            label: '兑现说明',
            icon: Icons.notes_outlined,
            controller: _description,
            hintText: '说明边界和兑现方式，避免承诺不清楚',
            minLines: 3,
          ),
          const SizedBox(height: 12),
          const _RewardSheetHint(),
        ],
      ),
    );
  }

  Future<void> _save() async {
    final title = _title.text.trim();
    final cost = int.tryParse(_cost.text.trim()) ?? 0;
    setState(() {
      _titleError = title.isEmpty ? '请输入商品名称' : null;
      _costError = cost <= 0 ? '请输入大于 0 的${widget.settings.unitLabel}数量' : null;
    });
    if (_titleError != null || _costError != null) return;

    setState(() => _saving = true);
    try {
      final account = (await ref.read(pointsSummaryProvider.future)).account;
      if (account.childId.isEmpty) {
        throw const RewardException('还没有可用的孩子账户，完成家庭设置后再添加商品。');
      }
      await ref
          .read(rewardRepositoryProvider)
          .createItem(
            childId: account.childId,
            title: title,
            pointsCost: cost,
            description: _description.text.trim(),
          );
      ref
        ..invalidate(rewardsSummaryProvider)
        ..invalidate(rewardItemsProvider);
      if (!mounted) return;
      Navigator.of(context).pop();
      if (widget.toastContext.mounted) {
        showAppToast(widget.toastContext, '积分商品已添加');
      }
    } on Object catch (error) {
      if (mounted) {
        showAppToast(
          context,
          error is RewardException ? error.message : '积分商品保存失败',
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _RewardSheetHint extends StatelessWidget {
  const _RewardSheetHint();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brandWash.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.brand.withValues(alpha: 0.10)),
      ),
      child: const Padding(
        padding: EdgeInsets.fromLTRB(12, 11, 12, 11),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              Icons.tips_and_updates_outlined,
              color: AppColors.brand,
              size: 19,
            ),
            SizedBox(width: 9),
            Expanded(
              child: Text(
                '建议优先添加亲子活动或小特权，物质奖励保持低频、边界清楚。',
                style: TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  height: 1.45,
                  letterSpacing: 0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
