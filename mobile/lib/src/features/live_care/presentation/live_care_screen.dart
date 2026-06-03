import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class LiveCareScreen extends ConsumerStatefulWidget {
  const LiveCareScreen({super.key});

  @override
  ConsumerState<LiveCareScreen> createState() => _LiveCareScreenState();
}

class _LiveCareScreenState extends ConsumerState<LiveCareScreen> {
  var _state = _LiveState.online;

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);

    return MiraScreen(
      title: '实时看护',
      subtitle: '${snapshot.device.room} · ${snapshot.device.name}',
      children: [
        _LiveViewport(state: _state),
        const SizedBox(height: 14),
        _StateSwitcher(
          selected: _state,
          onSelect: (value) => setState(() => _state = value),
        ),
        const SizedBox(height: 14),
        _LiveActions(state: _state),
        const SizedBox(height: 14),
        MiraSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionTitle('AI 观察摘要'),
              const SizedBox(height: 10),
              Text(
                _state.summary,
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
              MiraListRow(
                icon: Icons.fact_check_outlined,
                title: '家长确认入口',
                subtitle: _state == _LiveState.offline
                    ? '设备离线时只能查看最后一次摘要'
                    : '确认当前观察，或标记 AI 判断需要调整',
                tone: _state == _LiveState.error
                    ? MiraListRowTone.red
                    : MiraListRowTone.blue,
                onTap: () => _showLiveConfirmSheet(context, _state),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        MiraSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionTitle('设备状态'),
              const SizedBox(height: 8),
              MiraListRow(
                icon: Icons.wifi_outlined,
                title: snapshot.device.networkLabel,
                subtitle: snapshot.device.lastOnlineLabel,
                tone: snapshot.device.online
                    ? MiraListRowTone.green
                    : MiraListRowTone.red,
                trailing: StatusChip(label: _state.label, tone: _state.tone),
              ),
              MiraListRow(
                icon: Icons.privacy_tip_outlined,
                title: snapshot.device.privacyLightOn ? '隐私灯亮起' : '隐私灯待确认',
                subtitle: '家长查看实时画面时，设备端会显示工作状态。',
                tone: MiraListRowTone.blue,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _LiveViewport extends StatelessWidget {
  const _LiveViewport({required this.state});

  final _LiveState state;

  @override
  Widget build(BuildContext context) {
    final online = state == _LiveState.online || state == _LiveState.connecting;

    return MiraSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: EdgeInsets.zero,
      child: AspectRatio(
        aspectRatio: 16 / 11.2,
        child: Stack(
          children: [
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: const Color(0xFF101A28),
                  borderRadius: BorderRadius.circular(24),
                  gradient: online
                      ? const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [Color(0xFF182A3E), Color(0xFF0F172A)],
                        )
                      : null,
                ),
              ),
            ),
            Positioned.fill(
              child: Center(
                child: Icon(
                  state.icon,
                  color: Colors.white.withValues(alpha: 0.68),
                  size: 54,
                ),
              ),
            ),
            Positioned(
              left: 16,
              top: 16,
              child: StatusChip(label: state.label, tone: state.tone),
            ),
            Positioned(
              left: 16,
              right: 16,
              bottom: 16,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.26),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(13),
                  child: Text(
                    state.viewportCopy,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.82),
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      height: 1.45,
                      letterSpacing: 0,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StateSwitcher extends StatelessWidget {
  const _StateSwitcher({required this.selected, required this.onSelect});

  final _LiveState selected;
  final ValueChanged<_LiveState> onSelect;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final state in _LiveState.values) ...[
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => onSelect(state),
              child: AnimatedContainer(
                duration: AppMotion.duration(context, 160),
                constraints: const BoxConstraints(minHeight: 40),
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 9,
                ),
                decoration: BoxDecoration(
                  color: selected == state
                      ? AppColors.ink
                      : Colors.white.withValues(alpha: 0.72),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Text(
                  state.label,
                  style: TextStyle(
                    color: selected == state ? Colors.white : AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
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

class _LiveActions extends StatelessWidget {
  const _LiveActions({required this.state});

  final _LiveState state;

  @override
  Widget build(BuildContext context) {
    final available = state == _LiveState.online;

    return Row(
      children: [
        Expanded(
          child: MiraSecondaryButton(
            label: '通话',
            trailing: const Icon(Icons.phone_outlined, size: 18),
            onTap: available ? () => _showToast(context, '已发起 mock 通话') : null,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: MiraSecondaryButton(
            label: '截图',
            trailing: const Icon(Icons.camera_alt_outlined, size: 18),
            onTap: available ? () => _showToast(context, '截图已保存到事件证据') : null,
          ),
        ),
      ],
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

enum _LiveState {
  online(
    '在线',
    StatusTone.success,
    Icons.videocam_outlined,
    '设备端正在显示远程查看状态，当前只保存任务和告警相关截图。',
    '孩子在书桌区写作业，坐姿正常。当前建议继续低打扰观察。',
  ),
  connecting(
    '连接中',
    StatusTone.warning,
    Icons.sync_outlined,
    '正在连接设备画面，网络恢复后会自动进入实时看护。',
    '正在获取最新状态。若超过 20 秒未恢复，建议查看设备网络。',
  ),
  offline(
    '离线',
    StatusTone.danger,
    Icons.wifi_off_outlined,
    '设备离线，无法查看实时画面。',
    '设备最后在线于刚刚，仍可查看最后一次任务摘要和告警记录。',
  ),
  error(
    '异常',
    StatusTone.danger,
    Icons.error_outline,
    '设备连接异常，画面暂不可用。',
    '建议检查电源和网络；首版只提供普通异常摘要，不进入复杂安全事件流。',
  );

  const _LiveState(
    this.label,
    this.tone,
    this.icon,
    this.viewportCopy,
    this.summary,
  );

  final String label;
  final StatusTone tone;
  final IconData icon;
  final String viewportCopy;
  final String summary;
}

void _showLiveConfirmSheet(BuildContext context, _LiveState state) {
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
              '家长确认',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              state.summary,
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
              title: '确认当前状态',
              subtitle: '写入今日看护记录',
              tone: MiraListRowTone.green,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已确认当前观察');
              },
            ),
            MiraListRow(
              icon: Icons.report_outlined,
              title: '标记 AI 判断不准',
              subtitle: '作为后续规则调整样例',
              tone: MiraListRowTone.amber,
              onTap: () {
                Navigator.of(context).pop();
                _showToast(context, '已记录 AI 判断反馈');
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
