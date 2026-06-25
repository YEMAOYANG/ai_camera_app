import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/home/domain/home_models.dart';
import 'package:guardian_parent_app/src/features/home/presentation/widgets/home_shared.dart';
import 'package:guardian_parent_app/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class HomeRhythmRail extends StatelessWidget {
  const HomeRhythmRail({
    super.key,
    required this.mode,
    required this.nodes,
    required this.isLoading,
    required this.hasTaskError,
    required this.hasNoDevice,
  });

  final HomeRhythmMode mode;
  final List<RhythmNode> nodes;
  final bool isLoading;
  final bool hasTaskError;
  final bool hasNoDevice;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        HomeSectionTitle(
          title: _title,
          subtitle: _subtitle,
          actionLabel: nodes.isEmpty ? null : '查看全部',
          onAction: nodes.isEmpty
              ? null
              : () => context.go(AppRoute.tasks.path),
        ),
        const SizedBox(height: 10),
        if (isLoading)
          const HomeSoftPanel(
            child: Text(
              '正在整理今天安排…',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          )
        else if (hasTaskError)
          const HomeSoftPanel(
            tone: StatusTone.warning,
            child: Text(
              '今天暂时没更新，稍后可以去任务页查看。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          )
        else if (nodes.isEmpty)
          _EmptyRhythmPanel(hasNoDevice: hasNoDevice)
        else
          Column(
            children: [
              for (var index = 0; index < nodes.length; index++) ...[
                _RhythmNodeRow(node: nodes[index]),
                if (index != nodes.length - 1) const SizedBox(height: 8),
              ],
            ],
          ),
      ],
    );
  }

  String get _title {
    return switch (mode) {
      HomeRhythmMode.review => '今日回顾',
      HomeRhythmMode.empty => '今日安排',
      HomeRhythmMode.rhythm => '今日节奏',
    };
  }

  String? get _subtitle {
    if (nodes.isEmpty) return null;
    return switch (mode) {
      HomeRhythmMode.review => '今天完成了这些安排',
      HomeRhythmMode.empty => null,
      HomeRhythmMode.rhythm => '最近几个重要节点',
    };
  }
}

class _EmptyRhythmPanel extends StatelessWidget {
  const _EmptyRhythmPanel({required this.hasNoDevice});

  final bool hasNoDevice;

  @override
  Widget build(BuildContext context) {
    return HomeSoftPanel(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: Image.asset(
              'assets/images/empty_states/home_today_plan_empty.png',
              height: 132,
              fit: BoxFit.cover,
              alignment: Alignment.center,
            ),
          ),
          const SizedBox(height: 13),
          const Text(
            '今天还没有安排',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 17,
              fontWeight: FontWeight.w900,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 5),
          const Text(
            '可以先加一个生活小节奏，晚点再慢慢补充。',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              height: 1.35,
            ),
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: _RhythmActionButton(
                  label: '添加安排',
                  icon: Icons.add_rounded,
                  primary: true,
                  onTap: () => context.go(AppRoute.tasks.path),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _RhythmActionButton(
                  label: '选个模板',
                  icon: Icons.auto_awesome_motion_outlined,
                  onTap: () =>
                      context.go('${AppRoute.tasks.path}?open=templates'),
                ),
              ),
            ],
          ),
          if (hasNoDevice) ...[
            const SizedBox(height: 10),
            _RhythmCameraLink(onTap: () => showAddCameraSheet(context)),
          ],
        ],
      ),
    );
  }
}

class _RhythmActionButton extends StatelessWidget {
  const _RhythmActionButton({
    required this.label,
    required this.icon,
    required this.onTap,
    this.primary = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final background = primary
        ? AppColors.primaryButtonStart
        : AppColors.ink.withValues(alpha: 0.055);
    final foreground = primary ? Colors.white : AppColors.ink;
    return HomePressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: label,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(AppRadii.button),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 16, color: foreground),
                const SizedBox(width: 5),
                Flexible(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: foreground,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RhythmCameraLink extends StatelessWidget {
  const _RhythmCameraLink({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return HomePressable(
      onTap: onTap,
      child: Semantics(
        button: true,
        label: '连接看护摄像头',
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.brandWash.withValues(alpha: 0.72),
            borderRadius: BorderRadius.circular(AppRadii.button),
          ),
          child: const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 11),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.videocam_outlined,
                  size: 16,
                  color: AppColors.brandDeep,
                ),
                SizedBox(width: 6),
                Flexible(
                  child: Text(
                    '连接看护摄像头',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: AppColors.brandDeep,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RhythmNodeRow extends StatelessWidget {
  const _RhythmNodeRow({required this.node});

  final RhythmNode node;

  @override
  Widget build(BuildContext context) {
    final isCurrent = node.state == RhythmNodeState.current;
    final isCompleted = node.state == RhythmNodeState.completed;
    final tone = isCurrent ? StatusTone.success : node.tone;

    return HomePressable(
      onTap: () => context.go('$taskDetailPath/${node.taskId}'),
      child: Semantics(
        button: true,
        label: '${node.title}，${node.timeLabel}',
        child: HomeSoftPanel(
          tone: tone,
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          child: Row(
            children: [
              SizedBox(
                width: 52,
                child: Text(
                  node.timeLabel,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: homeToneColor(tone),
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      node.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: AppColors.ink.withValues(
                          alpha: isCompleted ? 0.62 : 1,
                        ),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      node.subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: AppColors.muted.withValues(
                          alpha: isCompleted ? 0.72 : 1,
                        ),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w600,
                        height: 1.25,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
