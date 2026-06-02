import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/features/home/application/guardian_snapshot_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/info_card.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class LiveCareScreen extends ConsumerWidget {
  const LiveCareScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianSnapshotProvider);
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 28),
      children: [
        Text('实时看护', style: theme.textTheme.headlineSmall),
        const SizedBox(height: 4),
        Text(snapshot.device.name, style: theme.textTheme.bodyMedium),
        const SizedBox(height: 16),
        AspectRatio(
          aspectRatio: 16 / 10,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: const Color(0xFF152330),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Center(
              child: Icon(Icons.videocam, color: Colors.white, size: 42),
            ),
          ),
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: () {},
                icon: const Icon(Icons.call),
                label: const Text('通话'),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () {},
                icon: const Icon(Icons.lock_outline),
                label: const Text('隐私'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),
        InfoCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('设备状态', style: theme.textTheme.titleLarge),
              const SizedBox(height: 12),
              _DeviceRow(
                label: '摄像头',
                chip: snapshot.device.cameraEnabled ? '可用' : '关闭',
              ),
              _DeviceRow(
                label: '麦克风',
                chip: snapshot.device.audioEnabled ? '可用' : '关闭',
              ),
              _DeviceRow(
                label: '隐私模式',
                chip: snapshot.device.privacyMode ? '开启' : '关闭',
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _DeviceRow extends StatelessWidget {
  const _DeviceRow({required this.label, required this.chip});

  final String label;
  final String chip;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(child: Text(label)),
          StatusChip(label: chip),
        ],
      ),
    );
  }
}
