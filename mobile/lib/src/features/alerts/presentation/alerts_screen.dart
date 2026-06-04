import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/features/mvp/domain/mvp_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class AlertsScreen extends ConsumerStatefulWidget {
  const AlertsScreen({super.key});

  @override
  ConsumerState<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends ConsumerState<AlertsScreen> {
  AlertState? _filter;

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);
    final alerts = _filter == null
        ? snapshot.alerts
        : snapshot.alerts.where((alert) => alert.state == _filter).toList();

    return MiraScreen(
      title: '告警',
      subtitle: '普通告警摘要和处理状态',
      children: [
        _AlertSummary(alerts: snapshot.alerts),
        const SizedBox(height: 14),
        _AlertFilter(
          selected: _filter,
          onSelect: (value) => setState(() => _filter = value),
        ),
        const SizedBox(height: 14),
        if (alerts.isEmpty)
          MiraStateView(
            variant: MiraStateVariant.noData,
            title: '没有这类告警',
            message: '当前筛选下没有需要处理的提醒。',
            primaryActionLabel: '查看全部',
            onPrimaryAction: () => setState(() => _filter = null),
            compact: true,
          )
        else
          MiraSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionTitle('告警列表'),
                const SizedBox(height: 8),
                for (final alert in alerts)
                  MiraListRow(
                    icon: _iconForAlert(alert),
                    title: alert.title,
                    subtitle: '${alert.timeLabel} · ${alert.summary}',
                    tone: _toneForAlert(alert),
                    trailing: StatusChip(
                      label: alert.state.label,
                      tone: alert.state.tone,
                    ),
                    onTap: () => _showAlertSheet(context, alert),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  IconData _iconForAlert(MvpAlert alert) {
    return switch (alert.state) {
      AlertState.unread => Icons.notification_important_outlined,
      AlertState.processing => Icons.pending_actions_outlined,
      AlertState.handled => Icons.check_circle_outline,
      AlertState.falseAlarm => Icons.rule_outlined,
      AlertState.read => Icons.notifications_outlined,
    };
  }

  MiraListRowTone _toneForAlert(MvpAlert alert) {
    return switch (alert.state) {
      AlertState.unread => MiraListRowTone.red,
      AlertState.processing => MiraListRowTone.amber,
      AlertState.handled => MiraListRowTone.green,
      AlertState.falseAlarm => MiraListRowTone.neutral,
      AlertState.read => MiraListRowTone.blue,
    };
  }
}

class _AlertSummary extends StatelessWidget {
  const _AlertSummary({required this.alerts});

  final List<MvpAlert> alerts;

  @override
  Widget build(BuildContext context) {
    final active = alerts
        .where(
          (alert) =>
              alert.state == AlertState.unread ||
              alert.state == AlertState.processing,
        )
        .length;

    return MiraSurface(
      color: active > 0 ? const Color(0xFFFFF1D8) : const Color(0xFFE9F6EF),
      borderColor: Colors.transparent,
      radius: 22,
      child: Row(
        children: [
          Icon(
            active > 0
                ? Icons.notification_important_outlined
                : Icons.shield_outlined,
            color: active > 0
                ? const Color(0xFFD8922B)
                : const Color(0xFF2F8F68),
            size: 26,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  active > 0 ? '$active 项需要跟进' : '今日无紧急告警',
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  '第一版不进入复杂安全事件详情，只保留摘要、状态和处理动作。',
                  style: TextStyle(
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
          ),
        ],
      ),
    );
  }
}

class _AlertFilter extends StatelessWidget {
  const _AlertFilter({required this.selected, required this.onSelect});

  final AlertState? selected;
  final ValueChanged<AlertState?> onSelect;

  @override
  Widget build(BuildContext context) {
    final items = <(String, AlertState?)>[
      ('全部', null),
      for (final state in AlertState.values) (state.label, state),
    ];

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final item in items) ...[
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onSelect(item.$2),
              child: AnimatedContainer(
                duration: AppMotion.duration(context, 160),
                constraints: const BoxConstraints(minHeight: 40),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 9,
                ),
                decoration: BoxDecoration(
                  color: selected == item.$2
                      ? AppColors.brandWash
                      : AppColors.surfaceSoft,
                  borderRadius: BorderRadius.circular(AppRadii.control),
                  border: Border.all(
                    color: selected == item.$2
                        ? AppColors.brand.withValues(alpha: 0.18)
                        : AppColors.borderSoft,
                  ),
                ),
                child: Text(
                  item.$1,
                  style: TextStyle(
                    color: selected == item.$2
                        ? AppColors.brandDeep
                        : AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
          ],
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

void _showAlertSheet(BuildContext context, MvpAlert alert) {
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
            Text(
              alert.title,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${alert.summary}\n建议：${alert.suggestedAction}',
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
              ),
            ),
            const SizedBox(height: 16),
            MiraListRow(
              icon: Icons.check_circle_outline,
              title: '标记已处理',
              subtitle: '写入处理记录',
              tone: MiraListRowTone.green,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已标记为已处理');
              },
            ),
            MiraListRow(
              icon: Icons.rule_outlined,
              title: '标记误报',
              subtitle: '后续降低同类提醒权重',
              tone: MiraListRowTone.amber,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已标记为误报');
              },
            ),
          ],
        ),
      );
    },
  );
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
