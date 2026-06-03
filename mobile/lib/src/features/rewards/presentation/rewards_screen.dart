import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/points/application/point_repository.dart';
import 'package:mira_guardian_app/src/features/rewards/application/reward_repository.dart';
import 'package:mira_guardian_app/src/features/rewards/domain/reward_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class RewardsScreen extends ConsumerWidget {
  const RewardsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(rewardsSummaryProvider);
    final points = ref.watch(pointsSummaryProvider);

    return MiraScreen(
      title: '奖励',
      subtitle: '奖励项、兑换和兑现记录',
      fixedHeader: true,
      backLabel: '返回我的',
      onBack: () => context.go(AppRoute.profile.path),
      trailing: MiraIconButton(
        icon: Icons.stars_outlined,
        label: '积分',
        onTap: () => context.go(pointsPath),
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
            MiraEmptyState(
              icon: Icons.cloud_off_outlined,
              title: '奖励加载失败',
              message: error is RewardException ? error.message : '请稍后重试。',
              action: TextButton(
                onPressed: () => ref.invalidate(rewardsSummaryProvider),
                child: const Text('重新加载'),
              ),
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
    return MiraSurface(
      color: AppColors.brand.withValues(alpha: 0.1),
      borderColor: AppColors.brand.withValues(alpha: 0.12),
      radius: 24,
      child: Row(
        children: [
          const Icon(Icons.redeem_outlined, color: AppColors.brand, size: 24),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '可用积分',
                  style: TextStyle(
                    color: AppColors.muted,
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
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
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
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PanelTitle('奖励商店'),
          const SizedBox(height: 8),
          if (items.isEmpty)
            const Text(
              '暂无奖励项。后端创建 reward item 后会展示在这里。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
                letterSpacing: 0,
              ),
            ),
          for (final item in items)
            MiraListRow(
              icon: _iconForReward(item),
              title: item.title,
              subtitle: item.description.isEmpty
                  ? '${item.pointsCost} 分兑换'
                  : '${item.description} · ${item.pointsCost} 分',
              tone: MiraListRowTone.blue,
              trailing: StatusChip(label: item.statusLabel),
              onTap: () => context.go('$rewardDetailPath/${item.id}'),
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
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PanelTitle('兑换记录'),
          const SizedBox(height: 8),
          if (redemptions.isEmpty)
            const Text(
              '暂无兑换记录。孩子或家长兑换奖励后会显示兑现状态。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
                letterSpacing: 0,
              ),
            ),
          for (final redemption in redemptions)
            MiraListRow(
              icon: Icons.redeem_outlined,
              title: redemption.rewardTitle,
              subtitle: '${redemption.pointsCost} 分 · ${redemption.status.label}',
              tone: redemption.status == RedemptionStatus.fulfilled
                  ? MiraListRowTone.green
                  : redemption.status == RedemptionStatus.cancelled
                  ? MiraListRowTone.neutral
                  : MiraListRowTone.amber,
              trailing: redemption.canFulfill
                  ? Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        TextButton(
                          onPressed: () => _cancel(context, ref, redemption),
                          child: const Text('取消'),
                        ),
                        TextButton(
                          onPressed: () => _fulfill(context, ref, redemption),
                          child: const Text('兑现'),
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
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: const [
          _PanelTitle('正在同步奖励'),
          SizedBox(height: 12),
          LinearProgressIndicator(minHeight: 3),
        ],
      ),
    );
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
