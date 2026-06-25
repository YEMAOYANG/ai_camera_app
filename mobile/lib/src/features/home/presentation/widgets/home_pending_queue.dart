import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/home/application/home_summary.dart';
import 'package:guardian_parent_app/src/features/home/domain/home_models.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_shared.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class HomePendingQueue extends StatelessWidget {
  const HomePendingQueue({
    super.key,
    required this.items,
    required this.hasNoDevice,
    required this.isLoading,
    required this.showNoDevicePrompt,
  });

  final List<PendingItem> items;
  final bool hasNoDevice;
  final bool isLoading;
  final bool showNoDevicePrompt;

  @override
  Widget build(BuildContext context) {
    if (hasNoDevice && showNoDevicePrompt) {
      return HomeSoftPanel(
        tone: StatusTone.neutral,
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
        child: Row(
          children: [
            const HomeToneIcon(
              icon: Icons.videocam_outlined,
              tone: StatusTone.neutral,
            ),
            const SizedBox(width: 11),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '摄像头还没连接',
                    style: TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14.5,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    '任务可以先用，连接后再看画面。',
                    style: TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            HomePressable(
              onTap: () => showAddCameraSheet(context),
              child: Semantics(
                button: true,
                label: '连接看护摄像头',
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.brandWash.withValues(alpha: 0.8),
                    borderRadius: BorderRadius.circular(AppRadii.full),
                  ),
                  child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                    child: Text(
                      '连接',
                      style: TextStyle(
                        color: AppColors.brandDeep,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    if (hasNoDevice) return const SizedBox.shrink();

    if (isLoading) {
      return const HomeSoftPanel(
        child: Text(
          '正在整理需要处理的事…',
          style: TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      );
    }

    if (items.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        HomeSectionTitle(
          title: '需要你处理',
          subtitle: '只放需要家长确认的事',
          actionLabel: '全部',
          onAction: () => context.go(AppRoute.alerts.path),
        ),
        const SizedBox(height: 10),
        _PendingPanel(items: items),
      ],
    );
  }
}

class _PendingPanel extends StatelessWidget {
  const _PendingPanel({required this.items});

  final List<PendingItem> items;

  @override
  Widget build(BuildContext context) {
    final visible = items.take(2).toList();
    final tone = visible.any((item) => item.routePath == liveRoutePath)
        ? StatusTone.danger
        : StatusTone.warning;

    return HomeSoftPanel(
      tone: tone,
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
      child: Column(
        children: [
          for (var index = 0; index < visible.length; index++) ...[
            _PendingRow(item: visible[index]),
            if (index != visible.length - 1)
              Divider(height: 14, color: AppColors.ink.withValues(alpha: 0.06)),
          ],
          if (items.length > visible.length) ...[
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                '还有 ${items.length - visible.length} 项，进入对应页面处理。',
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  height: 1.35,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PendingRow extends StatelessWidget {
  const _PendingRow({required this.item});

  final PendingItem item;

  @override
  Widget build(BuildContext context) {
    final icon = switch (item.kind) {
      PendingItemKind.task => Icons.fact_check_outlined,
      PendingItemKind.redemption => Icons.card_giftcard_outlined,
    };
    final tone = item.routePath == liveRoutePath
        ? StatusTone.danger
        : StatusTone.warning;
    final actionLabel = switch (item.action) {
      PendingItemAction.reviewMissedTask => '查看',
      PendingItemAction.checkDevice => '查看',
      _ => '处理',
    };

    return HomePressable(
      onTap: () => context.go(item.routePath),
      child: Semantics(
        button: true,
        label: '${item.title}，$actionLabel',
        child: Row(
          children: [
            HomeToneIcon(icon: icon, tone: tone),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 15,
                      fontWeight: FontWeight.w900,
                      height: 1.18,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    item.detail,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.25,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Text(
              actionLabel,
              style: TextStyle(
                color: homeToneColor(tone),
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w900,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
