import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/features/home/application/guardian_snapshot_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/info_card.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianSnapshotProvider);
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      children: [
        Text('我的', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 4),
        Text('家庭、孩子档案、设备与隐私', style: theme.textTheme.bodyMedium),
        const SizedBox(height: 16),
        InfoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('孩子档案', style: theme.textTheme.titleLarge),
              const SizedBox(height: 10),
              Text(
                '${snapshot.childName} · 小学低年级',
                style: theme.textTheme.bodyLarge,
              ),
              const SizedBox(height: 4),
              Text('作息、任务模板和提醒语气由档案驱动', style: theme.textTheme.bodyMedium),
            ],
          ),
        ),
        const SizedBox(height: 12),
        InfoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('家庭成员', style: theme.textTheme.titleLarge),
              const SizedBox(height: 10),
              for (final member in snapshot.familyMembers)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    children: [
                      Expanded(child: Text('${member.name} · ${member.role}')),
                      StatusChip(label: member.active ? '可通知' : '暂停'),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        InfoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('隐私与权限', style: theme.textTheme.titleLarge),
              const SizedBox(height: 10),
              const _SettingsRow(icon: Icons.history, label: '事件记录保留'),
              const _SettingsRow(
                icon: Icons.download_outlined,
                label: '儿童数据导出',
              ),
              const _SettingsRow(icon: Icons.delete_outline, label: '删除申请'),
            ],
          ),
        ),
      ],
    );
  }
}

class _SettingsRow extends StatelessWidget {
  const _SettingsRow({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(icon, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(label)),
          const Icon(Icons.chevron_right, size: 20),
        ],
      ),
    );
  }
}
