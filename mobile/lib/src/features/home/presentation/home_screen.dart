import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/features/home/application/guardian_snapshot_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/info_card.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianSnapshotProvider);
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      children: [
        Text('米拉', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 4),
        Text(
          '${snapshot.childName}现在在${snapshot.location}',
          style: theme.textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        InfoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.child_care, size: 24),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      snapshot.activity,
                      style: theme.textTheme.titleLarge,
                    ),
                  ),
                  const StatusChip(label: '正常', tone: StatusTone.success),
                ],
              ),
              const SizedBox(height: 14),
              Text(snapshot.currentTask, style: theme.textTheme.bodyLarge),
              const SizedBox(height: 4),
              Text(snapshot.nextCareAction, style: theme.textTheme.bodyMedium),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _DeviceMetric(
                label: '设备',
                value: snapshot.device.online ? '在线' : '离线',
                icon: Icons.sensors,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _DeviceMetric(
                label: '隐私',
                value: snapshot.device.privacyMode ? '开启' : '关闭',
                icon: Icons.privacy_tip_outlined,
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        _SectionTitle(
          title: '家长待处理',
          actionLabel: '${snapshot.pendingReviews.length} 项',
        ),
        const SizedBox(height: 10),
        for (final review in snapshot.pendingReviews) ...[
          InfoCard(
            child: Row(
              children: [
                Icon(
                  review.level == StatusToneMapper.watchLevel
                      ? Icons.assignment_late_outlined
                      : Icons.task_alt,
                  color: StatusToneMapper.colorFor(context, review.level),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(review.title, style: theme.textTheme.titleMedium),
                      const SizedBox(height: 2),
                      Text(review.detail, style: theme.textTheme.bodyMedium),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 10),
        ],
        const SizedBox(height: 10),
        _SectionTitle(title: '今天任务', actionLabel: '查看全部'),
        const SizedBox(height: 10),
        for (final task in snapshot.tasks.take(2)) ...[
          InfoCard(
            child: Row(
              children: [
                const Icon(Icons.check_circle_outline),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(task.title, style: theme.textTheme.titleMedium),
                      const SizedBox(height: 2),
                      Text(task.timeLabel, style: theme.textTheme.bodyMedium),
                    ],
                  ),
                ),
                StatusChip(label: task.status),
              ],
            ),
          ),
          const SizedBox(height: 10),
        ],
      ],
    );
  }
}

class _DeviceMetric extends StatelessWidget {
  const _DeviceMetric({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return InfoCard(
      child: Row(
        children: [
          Icon(icon, size: 20),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: theme.textTheme.bodyMedium),
              Text(value, style: theme.textTheme.titleMedium),
            ],
          ),
        ],
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle({required this.title, required this.actionLabel});

  final String title;
  final String actionLabel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      children: [
        Expanded(child: Text(title, style: theme.textTheme.titleLarge)),
        Text(actionLabel, style: theme.textTheme.bodyMedium),
      ],
    );
  }
}
