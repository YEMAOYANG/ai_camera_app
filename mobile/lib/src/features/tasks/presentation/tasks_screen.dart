import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/features/home/application/guardian_snapshot_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/info_card.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class TasksScreen extends ConsumerWidget {
  const TasksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianSnapshotProvider);
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      children: [
        Row(
          children: [
            Expanded(child: Text('任务', style: theme.textTheme.headlineSmall)),
            FilledButton.icon(
              onPressed: () {},
              icon: const Icon(Icons.add),
              label: const Text('新建'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text('今天 · 明天 · 本周', style: theme.textTheme.bodyMedium),
        const SizedBox(height: 16),
        for (final task in snapshot.tasks) ...[
          InfoCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        task.title,
                        style: theme.textTheme.titleLarge,
                      ),
                    ),
                    StatusChip(label: task.status),
                  ],
                ),
                const SizedBox(height: 8),
                Text(task.timeLabel, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 14),
                Row(
                  children: [
                    _TaskPill(
                      icon: Icons.stars_outlined,
                      label: '+${task.points}',
                    ),
                    const SizedBox(width: 8),
                    if (task.evidenceRequired)
                      const _TaskPill(
                        icon: Icons.image_outlined,
                        label: '证据确认',
                      ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
      ],
    );
  }
}

class _TaskPill extends StatelessWidget {
  const _TaskPill({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: colorScheme.onSecondaryContainer),
            const SizedBox(width: 4),
            Text(label),
          ],
        ),
      ),
    );
  }
}
