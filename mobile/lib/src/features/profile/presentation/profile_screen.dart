import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/auth/application/auth_repository.dart';
import 'package:mira_guardian_app/src/features/mvp/application/mvp_mock_provider.dart';
import 'package:mira_guardian_app/src/features/mvp/domain/mvp_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final snapshot = ref.watch(guardianMvpSnapshotProvider);

    return MiraScreen(
      title: '我的',
      subtitle: '家庭、设备、AI 规则和隐私权限',
      children: [
        _FamilyAccountPanel(snapshot: snapshot),
        const SizedBox(height: 14),
        _SettingsGroup(
          title: '家庭管理',
          entries: snapshot.settings.take(5).toList(),
        ),
        const SizedBox(height: 14),
        _SettingsGroup(
          title: '法律与隐私',
          entries: snapshot.settings.skip(5).toList(),
        ),
        const SizedBox(height: 16),
        MiraSecondaryButton(
          label: '退出登录',
          trailing: const Icon(Icons.logout_outlined, size: 18),
          onTap: () => _showLogoutDialog(context, ref),
        ),
      ],
    );
  }
}

class _FamilyAccountPanel extends StatelessWidget {
  const _FamilyAccountPanel({required this.snapshot});

  final GuardianMvpSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const SizedBox(
                  width: 48,
                  height: 48,
                  child: Center(
                    child: Icon(
                      Icons.family_restroom_outlined,
                      color: Colors.white,
                      size: 24,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '妈妈的家庭',
                      style: TextStyle(
                        color: Colors.white,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${snapshot.child.name} · ${snapshot.child.stage}${snapshot.child.grade}',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.64),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
              StatusChip(label: '管理员', tone: StatusTone.neutral),
            ],
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              _ProfileMetric(
                label: '家庭成员',
                value: '${snapshot.familyMembers.length}',
              ),
              const SizedBox(width: 8),
              _ProfileMetric(label: '设备', value: '1'),
              const SizedBox(width: 8),
              _ProfileMetric(
                label: '待处理',
                value: '${snapshot.pendingItems.length}',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ProfileMetric extends StatelessWidget {
  const _ProfileMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(13),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 11),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  height: 1,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                label,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.6),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SettingsGroup extends StatelessWidget {
  const _SettingsGroup({required this.title, required this.entries});

  final String title;
  final List<MvpSettingEntry> entries;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 8),
          for (final entry in entries)
            MiraListRow(
              icon: _iconFor(entry.kind),
              title: entry.title,
              subtitle: entry.subtitle,
              tone: _toneFor(entry.kind),
              onTap: () => _handleSettingTap(context, entry),
            ),
        ],
      ),
    );
  }

  IconData _iconFor(MvpSettingKind kind) {
    return switch (kind) {
      MvpSettingKind.family => Icons.groups_outlined,
      MvpSettingKind.child => Icons.child_care_outlined,
      MvpSettingKind.device => Icons.videocam_outlined,
      MvpSettingKind.aiRules => Icons.auto_awesome_outlined,
      MvpSettingKind.privacy => Icons.privacy_tip_outlined,
      MvpSettingKind.userAgreement => Icons.description_outlined,
      MvpSettingKind.privacyPolicy => Icons.lock_outline,
      MvpSettingKind.logout => Icons.logout_outlined,
    };
  }

  MiraListRowTone _toneFor(MvpSettingKind kind) {
    return switch (kind) {
      MvpSettingKind.device => MiraListRowTone.green,
      MvpSettingKind.aiRules => MiraListRowTone.blue,
      MvpSettingKind.privacy => MiraListRowTone.amber,
      MvpSettingKind.userAgreement ||
      MvpSettingKind.privacyPolicy => MiraListRowTone.neutral,
      _ => MiraListRowTone.blue,
    };
  }
}

void _handleSettingTap(BuildContext context, MvpSettingEntry entry) {
  switch (entry.kind) {
    case MvpSettingKind.userAgreement:
      context.push(userAgreementPath);
    case MvpSettingKind.privacyPolicy:
      context.push(privacyPolicyPath);
    case MvpSettingKind.child:
      _showProfileSheet(
        context,
        '孩子资料',
        '小宇，小学一年级。生日、年级和班级会影响任务模板、小书包规则和提醒语气。首版先展示摘要，编辑页留到后续完善。',
      );
    case MvpSettingKind.device:
      _showProfileSheet(
        context,
        '设备管理',
        '客厅米拉在线，网络良好。首版展示设备状态、隐私灯和解绑说明，不做多设备高级管理。',
      );
    case MvpSettingKind.family:
      _showProfileSheet(
        context,
        '家庭成员',
        '妈妈为管理员，爸爸为监护人，奶奶为临时查看者。首版支持查看权限摘要，不做复杂角色编辑。',
      );
    case MvpSettingKind.aiRules:
      _showProfileSheet(
        context,
        'AI 规则设置',
        '作业模式仅允许任务相关问答和温和提示。AI 判断需要家长确认，不自动承诺奖励。',
      );
    case MvpSettingKind.privacy:
      _showProfileSheet(
        context,
        '隐私权限',
        '音视频采集会在设备绑定和看护功能中单独授权。儿童数据删除和导出保留入口。',
      );
    case MvpSettingKind.logout:
      break;
  }
}

void _showProfileSheet(BuildContext context, String title, String body) {
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
              title,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              body,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.55,
              ),
            ),
            const SizedBox(height: 16),
            MiraPrimaryButton(
              label: '知道了',
              onTap: () => Navigator.of(context).pop(),
            ),
          ],
        ),
      );
    },
  );
}

void _showLogoutDialog(BuildContext context, WidgetRef ref) {
  showDialog<void>(
    context: context,
    builder: (context) {
      return AlertDialog(
        title: const Text('退出登录'),
        content: const Text('退出后再次进入 App 需要手机号验证码。摄像头会继续执行已配置的任务和提醒。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () async {
              await ref.read(authRepositoryProvider).logout();
              if (!context.mounted) return;
              Navigator.of(context).pop();
              context.go(loginPath);
            },
            child: const Text('退出'),
          ),
        ],
      );
    },
  );
}
