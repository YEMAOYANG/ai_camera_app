import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/application/reward_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/domain/reward_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class RewardsScreen extends ConsumerWidget {
  const RewardsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(rewardsSummaryProvider);
    final points = ref.watch(pointsSummaryProvider);

    return AppScreen(
      title: '奖励',
      subtitle: '奖励项、兑换和兑现记录',
      fixedHeader: true,
      backLabel: '返回我的',
      onBack: () => context.go(AppRoute.profile.path),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppIconButton(
            icon: Icons.add,
            label: '新增奖励',
            onTap: () => context.push(rewardEditPath),
          ),
          const SizedBox(width: 8),
          AppIconButton(
            icon: Icons.stars_outlined,
            label: '积分',
            onTap: () => context.go(pointsPath),
          ),
        ],
      ),
      children: [
        _RewardBalancePanel(balance: points.asData?.value.account.balance),
        const SizedBox(height: 14),
        ...summary.when(
          data: (data) => [
            _RewardItemsPanel(items: data.items),
            const SizedBox(height: 14),
            _RedemptionsPanel(redemptions: data.redemptions),
          ],
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
  const _RewardBalancePanel({required this.balance});

  final int? balance;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 17),
      child: Stack(
        children: [
          Positioned(
            right: -36,
            top: -46,
            width: 150,
            height: 150,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    const Color(0xFFD8922B).withValues(alpha: 0.24),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),
          Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: const SizedBox(
                  width: 52,
                  height: 52,
                  child: Center(
                    child: Icon(
                      Icons.redeem_outlined,
                      color: Color(0xFFFDBA74),
                      size: 25,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '可用积分',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.66),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      balance == null ? '同步中' : '$balance 分',
                      style: const TextStyle(
                        color: Colors.white,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 25,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '兑换前会给家长确认，不会自动承诺奖励。',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.58),
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
            ],
          ),
        ],
      ),
    );
  }
}

class _RewardItemsPanel extends StatelessWidget {
  const _RewardItemsPanel({required this.items});

  final List<RewardItem> items;

  @override
  Widget build(BuildContext context) {
    final activeItems = items
        .where((item) => item.status != 'archived')
        .toList();
    if (activeItems.isEmpty) {
      return const AppStateView(
        variant: AppStateVariant.emptyRewards,
        title: '还没有奖励项',
        message: '家长添加奖励后，孩子可以用完成任务获得的积分来兑换。',
        compact: true,
      );
    }

    return AppSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PanelTitle('奖励商店'),
          const SizedBox(height: 8),
          for (final item in activeItems)
            AppListRow(
              icon: _iconForReward(item),
              title: item.title,
              subtitle: item.description.isEmpty
                  ? '${item.pointsCost} 分兑换'
                  : '${item.description} · ${item.pointsCost} 分',
              tone: AppListRowTone.blue,
              trailing: StatusChip(label: item.statusLabel),
              onTap: () => context.go('$rewardDetailPath/${item.id}'),
            ),
          const SizedBox(height: 10),
          AppListRow(
            icon: Icons.add_circle_outline,
            title: '添加奖励',
            subtitle: '家长可以创建新的兑换目标',
            tone: AppListRowTone.green,
            onTap: () => context.push(rewardEditPath),
          ),
        ],
      ),
    );
  }

  IconData _iconForReward(RewardItem item) {
    return switch (item.icon) {
      'book' => Icons.menu_book_outlined,
      'park' => Icons.park_outlined,
      'game' => Icons.sports_esports_outlined,
      _ => Icons.card_giftcard_outlined,
    };
  }
}

class _RedemptionsPanel extends ConsumerWidget {
  const _RedemptionsPanel({required this.redemptions});

  final List<RewardRedemption> redemptions;

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
          const _PanelTitle('兑换记录'),
          const SizedBox(height: 8),
          for (final redemption in redemptions)
            AppListRow(
              icon: Icons.redeem_outlined,
              title: redemption.rewardTitle,
              subtitle:
                  '${redemption.pointsCost} 分 · ${redemption.status.label}',
              tone: redemption.status == RedemptionStatus.fulfilled
                  ? AppListRowTone.green
                  : redemption.status == RedemptionStatus.cancelled
                  ? AppListRowTone.neutral
                  : AppListRowTone.amber,
              trailing: redemption.canFulfill
                  ? Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _RedemptionActionButton(
                          label: '取消',
                          onTap: () => _cancel(context, ref, redemption),
                        ),
                        const SizedBox(width: 7),
                        _RedemptionActionButton(
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

class _RedemptionActionButton extends StatelessWidget {
  const _RedemptionActionButton({
    required this.label,
    required this.onTap,
    this.highlight = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: highlight ? AppColors.brandWash : AppColors.surfaceSoft,
          borderRadius: BorderRadius.circular(AppRadii.full),
          border: Border.all(
            color: highlight
                ? AppColors.brand.withValues(alpha: 0.18)
                : AppColors.borderSoft,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          child: Text(
            label,
            style: TextStyle(
              color: highlight ? AppColors.brandDeep : AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w600,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

class _PanelTitle extends StatelessWidget {
  const _PanelTitle(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 16,
        fontWeight: FontWeight.w800,
        letterSpacing: 0,
      ),
    );
  }
}

class _RewardsLoading extends StatelessWidget {
  const _RewardsLoading();

  @override
  Widget build(BuildContext context) {
    return const AppLoadingState(title: '正在同步奖励', message: '正在整理奖励项和兑换进度。');
  }
}

Future<void> _fulfill(
  BuildContext context,
  WidgetRef ref,
  RewardRedemption redemption,
) async {
  try {
    await ref.read(rewardRepositoryProvider).fulfillRedemption(redemption.id);
    ref.invalidate(rewardsSummaryProvider);
    ref.invalidate(rewardRedemptionsProvider);
    if (context.mounted) _showToast(context, '已标记为兑现');
  } on RewardException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

Future<void> _cancel(
  BuildContext context,
  WidgetRef ref,
  RewardRedemption redemption,
) async {
  try {
    await ref.read(rewardRepositoryProvider).cancelRedemption(redemption.id);
    ref
      ..invalidate(rewardsSummaryProvider)
      ..invalidate(rewardRedemptionsProvider)
      ..invalidate(pointsSummaryProvider);
    if (context.mounted) _showToast(context, '已取消兑换，积分已返还');
  } on RewardException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

void _showToast(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.ink,
      ),
    );
}
