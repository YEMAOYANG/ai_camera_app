import 'package:flutter/material.dart';
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
import 'package:guardian_parent_app/src/shared/widgets/app_toast.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class RewardDetailScreen extends ConsumerWidget {
  const RewardDetailScreen({required this.itemId, super.key});

  final String itemId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itemValue = ref.watch(rewardDetailProvider(itemId));
    final points = ref.watch(pointsSummaryProvider);
    final pointSettingsValue = ref.watch(pointRewardSettingsProvider);
    final pointSettings =
        pointSettingsValue.asData?.value ?? PointRewardSettings.fallback;
    final canManageRewards =
        ref.watch(profileSummaryProvider).asData?.value.can('manage_rewards') ??
        false;

    return itemValue.when(
      data: (item) {
        final balance = points.asData?.value.account.balance ?? 0;
        final canRedeem =
            canManageRewards &&
            item.available &&
            points.asData?.value != null &&
            balance >= item.pointsCost;

        return AppScreen(
          title: item.title,
          subtitle: '${pointSettings.amount(item.pointsCost)}兑换',
          fixedHeader: true,
          backLabel: '返回奖励',
          onBack: () => context.go(rewardsPath),
          trailing: canManageRewards
              ? AppIconButton(
                  icon: Icons.edit_outlined,
                  label: '编辑奖励',
                  onTap: () => context.push('$rewardEditPath/${item.id}'),
                )
              : null,
          children: [
            _RewardHero(item: item, balance: balance, settings: pointSettings),
            const SizedBox(height: 14),
            AppSurface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _SectionTitle('兑换说明'),
                  const SizedBox(height: 10),
                  Text(
                    item.description.isEmpty
                        ? '该奖励由家长确认并手动兑现。'
                        : item.description,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                      height: 1.55,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 10),
                  AppListRow(
                    icon: Icons.stars_outlined,
                    title: '所需${pointSettings.unitLabel}',
                    subtitle: '兑换后会立即扣减${pointSettings.unitLabel}，并留下清楚记录。',
                    tone: AppListRowTone.amber,
                    trailing: Text(
                      '${item.pointsCost}',
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 16,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            if (canManageRewards) ...[
              AppPrimaryButton(
                label: canRedeem ? '兑换奖励' : '${pointSettings.unitLabel}不足',
                trailing: const AppButtonGlyph(icon: Icons.redeem_outlined),
                onTap: canRedeem
                    ? () => _showRedeemDialog(context, ref, item, pointSettings)
                    : null,
              ),
              const SizedBox(height: 10),
            ],
            AppSecondaryButton(
              label: '查看兑换记录',
              trailing: const Icon(Icons.history_outlined, size: 18),
              onTap: () => context.go(rewardsPath),
            ),
          ],
        );
      },
      loading: () => AppScreen(
        title: '奖励详情',
        fixedHeader: true,
        backLabel: '返回奖励',
        onBack: () => context.go(rewardsPath),
        children: const [_RewardDetailLoading()],
      ),
      error: (error, _) => AppScreen(
        title: '奖励详情',
        fixedHeader: true,
        backLabel: '返回奖励',
        onBack: () => context.go(rewardsPath),
        children: [
          AppStateView(
            variant: AppStateVariant.serviceUnavailable,
            title: '奖励详情暂时打不开',
            message: error is RewardException ? error.message : '请稍后重试。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: () => ref.invalidate(rewardDetailProvider(itemId)),
          ),
        ],
      ),
    );
  }
}

class _RewardHero extends StatelessWidget {
  const _RewardHero({
    required this.item,
    required this.balance,
    required this.settings,
  });

  final RewardItem item;
  final int balance;
  final PointRewardSettings settings;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
      child: Stack(
        children: [
          Positioned(
            right: -42,
            bottom: -50,
            width: 150,
            height: 150,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  colors: [
                    AppColors.brandSoft.withValues(alpha: 0.24),
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
                  StatusChip(label: item.statusLabel),
                  const Spacer(),
                  Text(
                    '余额 ${settings.amount(balance)}',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.68),
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              Text(
                item.title,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 26,
                  fontWeight: FontWeight.w900,
                  height: 1.16,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                '${settings.amount(item.pointsCost)}兑换，家长手动兑现。',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.72),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  height: 1.55,
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

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title);

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

class _RewardDetailLoading extends StatelessWidget {
  const _RewardDetailLoading();

  @override
  Widget build(BuildContext context) {
    return const AppLoadingState(title: '正在加载奖励', message: '正在确认积分余额和兑换规则。');
  }
}

Future<void> _showRedeemDialog(
  BuildContext context,
  WidgetRef ref,
  RewardItem item,
  PointRewardSettings settings,
) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '确认兑换',
    message:
        '将使用 ${settings.amount(item.pointsCost)}兑换「${item.title}」。兑换后会生成待兑现记录。',
    confirmLabel: '确认兑换',
  );
  if (!confirmed || !context.mounted) return;
  await _redeem(context, ref, item);
}

Future<void> _redeem(
  BuildContext context,
  WidgetRef ref,
  RewardItem item,
) async {
  try {
    await ref.read(rewardRepositoryProvider).createRedemption(item.id);
    ref
      ..invalidate(rewardsSummaryProvider)
      ..invalidate(rewardRedemptionsProvider)
      ..invalidate(pointsSummaryProvider);
    if (context.mounted) {
      _showToast(context, '兑换成功，已生成待兑现记录');
      context.go(rewardsPath);
    }
  } on RewardException catch (error) {
    if (context.mounted) _showToast(context, error.message);
  }
}

void _showToast(BuildContext context, String message) {
  showAppToast(context, message);
}
