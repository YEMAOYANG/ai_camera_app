import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/points/application/point_repository.dart';
import 'package:mira_guardian_app/src/features/points/domain/point_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';

class PointsScreen extends ConsumerWidget {
  const PointsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(pointsSummaryProvider);

    return MiraScreen(
      title: '积分',
      subtitle: '余额、任务奖励和兑换流水',
      fixedHeader: true,
      backLabel: '返回我的',
      onBack: () => context.go(AppRoute.profile.path),
      trailing: MiraIconButton(
        icon: Icons.card_giftcard_outlined,
        label: '奖励',
        onTap: () => context.go(rewardsPath),
      ),
      children: summary.when(
        data: (data) => [
          _BalancePanel(summary: data),
          const SizedBox(height: 14),
          _LedgerPanel(entries: data.ledger),
          const SizedBox(height: 14),
          MiraSecondaryButton(
            label: '补发或更正积分',
            trailing: const Icon(Icons.tune_outlined, size: 18),
            onTap: data.account.childId.isEmpty
                ? () => _showToast(context, '还没有可调整的积分账户，完成任务确认后会自动准备。')
                : () => _showAdjustSheet(context, ref, data.account),
          ),
        ],
        loading: () => const [_PointsLoading()],
        error: (error, _) => [
          MiraStateView(
            variant: MiraStateVariant.serviceUnavailable,
            title: '积分暂时没有更新',
            message: error is PointException ? error.message : '请稍后重试。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: () => ref.invalidate(pointsSummaryProvider),
          ),
        ],
      ),
    );
  }
}

class _BalancePanel extends StatelessWidget {
  const _BalancePanel({required this.summary});

  final PointsSummary summary;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '当前可用积分',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.66),
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '${summary.account.balance}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 42,
                    fontWeight: FontWeight.w900,
                    height: 1,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '每一次奖励和兑换都会留下记录。',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.62),
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(18),
            ),
            child: const SizedBox(
              width: 56,
              height: 56,
              child: Center(
                child: Icon(Icons.stars_outlined, color: Colors.white),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LedgerPanel extends StatelessWidget {
  const _LedgerPanel({required this.entries});

  final List<PointLedgerEntry> entries;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return const MiraStateView(
        variant: MiraStateVariant.emptyLedger,
        title: '还没有积分流水',
        message: '家长确认任务或兑换奖励后，积分变化会显示在这里。',
        compact: true,
      );
    }

    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '积分流水',
            style: TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 8),
          for (final entry in entries)
            MiraListRow(
              icon: entry.delta >= 0
                  ? Icons.add_circle_outline
                  : Icons.remove_circle_outline,
              title: entry.typeLabel,
              subtitle: entry.note.isEmpty
                  ? '余额 ${entry.balanceAfter}'
                  : '${entry.note} · 余额 ${entry.balanceAfter}',
              tone: entry.delta >= 0
                  ? MiraListRowTone.green
                  : MiraListRowTone.amber,
              trailing: Text(
                '${entry.delta >= 0 ? '+' : ''}${entry.delta}',
                style: TextStyle(
                  color: entry.delta >= 0
                      ? const Color(0xFF2F8F68)
                      : const Color(0xFFD8922B),
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
  const _PointsLoading();

  @override
  Widget build(BuildContext context) {
    return const MiraLoadingState(title: '正在同步积分', message: '正在整理余额和最近的积分变化。');
  }
}

void _showAdjustSheet(
  BuildContext context,
  WidgetRef ref,
  PointAccount account,
) {
  showModalBottomSheet<void>(
    context: context,
    useRootNavigator: true,
    showDragHandle: true,
    backgroundColor: AppColors.appBackgroundWarm,
    builder: (context) {
      return Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              '补发或更正积分',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '用于家长临时补发或扣回积分，调整记录会保留在这里。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 16),
            MiraListRow(
              icon: Icons.add_circle_outline,
              title: '补发 5 分',
              subtitle: '家长手动补发',
              tone: MiraListRowTone.green,
              onTap: () => _adjust(context, ref, account, 5),
            ),
            MiraListRow(
              icon: Icons.remove_circle_outline,
              title: '扣回 5 分',
              subtitle: '更正误发积分',
              tone: MiraListRowTone.amber,
              onTap: () => _adjust(context, ref, account, -5),
            ),
          ],
        ),
      );
    },
  );
}

Future<void> _adjust(
  BuildContext context,
  WidgetRef ref,
  PointAccount account,
  int delta,
) async {
  try {
    await ref
        .read(pointRepositoryProvider)
        .adjust(
          childId: account.childId,
          delta: delta,
          note: delta > 0 ? '家长手动补发' : '家长更正扣回',
        );
    ref.invalidate(pointsSummaryProvider);
    if (context.mounted) {
      Navigator.of(context).pop();
      _showToast(context, '积分已调整');
    }
  } on PointException catch (error) {
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
