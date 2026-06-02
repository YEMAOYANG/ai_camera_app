import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/features/home/application/guardian_snapshot_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/info_card.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianSnapshotProvider);
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      children: [
        Text('告警', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 4),
        Text('安全事件、离座提醒和设备异常', style: theme.textTheme.bodyMedium),
        const SizedBox(height: 16),
        for (final event in snapshot.safetyEvents) ...[
          InfoCard(
            child: Row(
              children: [
                const Icon(Icons.shield_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(event.title, style: theme.textTheme.titleMedium),
                      const SizedBox(height: 2),
                      Text(event.timeLabel, style: theme.textTheme.bodyMedium),
                    ],
                  ),
                ),
                StatusChip(label: event.status),
              ],
            ),
          ),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}
