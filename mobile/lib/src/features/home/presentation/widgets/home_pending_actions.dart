import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/home/application/home_summary.dart';
import 'package:warm_sight/src/features/home/domain/home_models.dart';
import 'package:warm_sight/src/features/home/presentation/widgets/parent_review_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';

Future<void> openHomePendingItem(
  BuildContext context,
  WidgetRef ref,
  PendingItem item,
) async {
  if (item.action == PendingItemAction.reviewCareNotify) {
    await showParentReviewSheet(
      context,
      reviewId: item.id,
      summary: item.title,
    );
    return;
  }
  context.go(item.routePath);
}

Future<void> showHomePendingSheet(
  BuildContext context,
  WidgetRef ref,
  List<PendingItem> items,
) async {
  if (items.isEmpty) return;
  await showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.72,
    child: AppBottomSheetBody(
      title: '需要你处理',
      subtitle: '只放需要家长确认的事',
      wrapScrollableChild: false,
      child: ListView.separated(
        padding: const EdgeInsets.only(bottom: 8),
        itemCount: items.length,
        separatorBuilder: (_, _) => Divider(
          height: 1,
          color: AppColors.ink.withValues(alpha: 0.06),
        ),
        itemBuilder: (context, index) {
          final item = items[index];
          return AppListRow(
            icon: _pendingIcon(item),
            title: item.title,
            subtitle: item.detail,
            tone: _pendingRowTone(item),
            trailing: const Icon(
              Icons.chevron_right_rounded,
              color: AppColors.muted,
              size: 20,
            ),
            onTap: () async {
              Navigator.of(context).pop();
              await openHomePendingItem(context, ref, item);
            },
          );
        },
      ),
    ),
  );
}

IconData _pendingIcon(PendingItem item) {
  return switch (item.kind) {
    PendingItemKind.task => Icons.fact_check_outlined,
    PendingItemKind.redemption => Icons.card_giftcard_outlined,
  };
}

AppListRowTone _pendingRowTone(PendingItem item) {
  if (item.routePath == liveRoutePath) return AppListRowTone.red;
  return AppListRowTone.amber;
}
