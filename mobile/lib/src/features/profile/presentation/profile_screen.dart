import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/auth/application/auth_repository.dart';
import 'package:mira_guardian_app/src/features/profile/application/profile_repository.dart';
import 'package:mira_guardian_app/src/features/profile/domain/profile_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(profileSummaryProvider);

    return MiraScreen(
      title: '我的',
      fixedHeader: false,
      showHeader: false,
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
      children: [
        summary.when(
          data: (data) => _FamilySpaceCard(summary: data),
          loading: () => const _FamilySpaceLoading(),
          error: (error, _) => MiraStateView(
            variant: MiraStateVariant.serviceUnavailable,
            title: '家庭空间暂时无法同步',
            message: error is ProfileException ? error.message : '请稍后重试。',
            primaryActionLabel: '重新加载',
            onPrimaryAction: () => ref.invalidate(profileSummaryProvider),
            compact: true,
          ),
        ),
        const SizedBox(height: 14),
        _ProfileGroup(
          title: '家庭与孩子',
          rows: [
            _ProfileRow(
              icon: Icons.groups_outlined,
              title: '家庭成员',
              subtitle: '照护人、查看权限和通知',
              path: profileFamilyMembersPath,
              tone: MiraListRowTone.green,
            ),
            _ProfileRow(
              icon: Icons.child_care_outlined,
              title: '孩子资料',
              subtitle: '阶段、兴趣和任务偏好',
              path: profileChildPath,
            ),
            _ProfileRow(
              icon: Icons.contact_phone_outlined,
              title: '紧急联系人',
              subtitle: '重要情况的通知对象',
              path: profileContactsPath,
            ),
          ],
        ),
        const SizedBox(height: 14),
        _ProfileGroup(
          title: '设备与看护',
          rows: [
            _ProfileRow(
              icon: Icons.videocam_outlined,
              title: '设备管理',
              subtitle: '名称、房间、网络和解绑',
              path: profileDevicesPath,
              tone: MiraListRowTone.blue,
            ),
            _ProfileRow(
              icon: Icons.shield_outlined,
              title: '摄像头与看护状态',
              subtitle: '画面、语音和观察能力',
              path: profileCameraStatusPath,
            ),
            _ProfileRow(
              icon: Icons.auto_awesome_outlined,
              title: 'AI 看护规则',
              subtitle: '任务观察、语音提醒和拖拉提醒',
              path: profileAiRulesPath,
            ),
          ],
        ),
        const SizedBox(height: 14),
        _ProfileGroup(
          title: '积分与奖励',
          rows: [
            _ProfileRow(
              icon: Icons.stars_outlined,
              title: '积分账户',
              subtitle: '积分余额和流水',
              path: pointsPath,
              tone: MiraListRowTone.amber,
            ),
            _ProfileRow(
              icon: Icons.card_giftcard_outlined,
              title: '奖励中心',
              subtitle: '添加、编辑和兑换奖励',
              path: rewardsPath,
            ),
            _ProfileRow(
              icon: Icons.history_outlined,
              title: '兑换记录',
              subtitle: '待兑现、已兑现和取消记录',
              path: redemptionsPath,
            ),
          ],
        ),
        const SizedBox(height: 14),
        _ProfileGroup(
          title: '报告与成长',
          rows: [
            _ProfileRow(
              icon: Icons.today_outlined,
              title: '今日报告',
              subtitle: '今天的任务、积分和待处理',
              path: profileDailyReportPath,
            ),
            _ProfileRow(
              icon: Icons.calendar_month_outlined,
              title: '周报',
              subtitle: '本周完成节奏和积分',
              path: profileWeeklyReportPath,
            ),
            _ProfileRow(
              icon: Icons.bookmark_outline,
              title: '成长时刻',
              subtitle: '家长保存的积极片段',
              path: profileMomentsPath,
            ),
          ],
        ),
        const SizedBox(height: 14),
        _ProfileGroup(
          title: '偏好与权限',
          rows: [
            _ProfileRow(
              icon: Icons.notifications_outlined,
              title: '通知与提醒',
              subtitle: '任务、设备和积分提醒',
              path: profileNotificationsPath,
            ),
            _ProfileRow(
              icon: Icons.lock_outline,
              title: '隐私与权限',
              subtitle: '采集授权、语音播报和数据保留',
              path: profilePrivacyPath,
            ),
            _ProfileRow(
              icon: Icons.record_voice_over_outlined,
              title: '对话与人设',
              subtitle: '唤醒名、语音风格和对话边界',
              path: profileConversationPath,
            ),
            _ProfileRow(
              icon: Icons.menu_book_outlined,
              title: '学习内容',
              subtitle: '小书包、课程表和内容偏好',
              path: profileEducationPath,
            ),
          ],
        ),
        const SizedBox(height: 14),
        _ProfileGroup(
          title: '账号与服务',
          rows: [
            _ProfileRow(
              icon: Icons.person_outline,
              title: '个人信息',
              subtitle: '称呼和家庭空间名称',
              path: profileAccountPath,
            ),
            _ProfileRow(
              icon: Icons.verified_user_outlined,
              title: '账号安全',
              subtitle: '手机号、登录方式和登录设备',
              path: profileSecurityPath,
            ),
            _ProfileRow(
              icon: Icons.workspace_premium_outlined,
              title: '订阅与套餐',
              subtitle: '基础能力和后续套餐',
              path: profileSubscriptionPath,
            ),
            _ProfileRow(
              icon: Icons.info_outline,
              title: '关于',
              subtitle: '版本、协议和帮助反馈',
              path: profileAboutPath,
            ),
          ],
        ),
        const SizedBox(height: 16),
        MiraSecondaryButton(
          label: '退出登录',
          trailing: const Icon(Icons.logout_outlined, size: 18),
          onTap: () => _confirmLogout(context, ref),
        ),
      ],
    );
  }
}

class _FamilySpaceCard extends StatelessWidget {
  const _FamilySpaceCard({required this.summary});

  final ProfileSummary summary;

  @override
  Widget build(BuildContext context) {
    final child = summary.child;
    final childText = child == null
        ? '孩子资料待完善'
        : '${child.name} · ${child.displayStage}';
    final displayName = summary.displayName.isEmpty
        ? '家长'
        : summary.displayName;

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
                  color: Colors.white.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const SizedBox(
                  width: 48,
                  height: 48,
                  child: Center(
                    child: Icon(
                      Icons.home_outlined,
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
                    Text(summary.spaceTitle, style: _darkTitle),
                    const SizedBox(height: 5),
                    Text(
                      '$displayName · ${_phoneMask(summary.phone)}',
                      style: _darkSub,
                    ),
                  ],
                ),
              ),
              StatusChip(label: summary.roleLabel, tone: StatusTone.neutral),
            ],
          ),
          const SizedBox(height: 12),
          Text(childText, style: _darkSub),
          const SizedBox(height: 18),
          Row(
            children: [
              _ProfileMetric(label: '家庭成员', value: '${summary.memberCount}'),
              const SizedBox(width: 8),
              _ProfileMetric(label: '已绑定设备', value: '${summary.deviceCount}'),
              const SizedBox(width: 8),
              _ProfileMetric(
                label: '待处理',
                value: '${summary.pendingItemCount}',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _FamilySpaceLoading extends StatelessWidget {
  const _FamilySpaceLoading();

  @override
  Widget build(BuildContext context) {
    return const MiraLoadingState(title: '正在同步家庭空间', message: '请稍候。');
  }
}

class _ProfileGroup extends StatelessWidget {
  const _ProfileGroup({required this.title, required this.rows});

  final String title;
  final List<_ProfileRow> rows;

  @override
  Widget build(BuildContext context) {
    return MiraSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PanelTitle(title),
          const SizedBox(height: 8),
          for (final row in rows)
            MiraListRow(
              icon: row.icon,
              title: row.title,
              subtitle: row.subtitle,
              tone: row.tone,
              onTap: () => context.push(row.path),
            ),
        ],
      ),
    );
  }
}

class _ProfileRow {
  const _ProfileRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.path,
    this.tone = MiraListRowTone.neutral,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String path;
  final MiraListRowTone tone;
}

class _PanelTitle extends StatelessWidget {
  const _PanelTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
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

class _ProfileMetric extends StatelessWidget {
  const _ProfileMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(14),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.62),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

void _confirmLogout(BuildContext context, WidgetRef ref) {
  showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('退出登录'),
      content: const Text('退出后再次进入需要手机号验证码，设备会继续执行已配置的任务和提醒。'),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () async {
            await ref.read(authRepositoryProvider).logout();
            if (dialogContext.mounted) {
              Navigator.of(dialogContext).pop();
            }
            if (context.mounted) {
              context.go(loginPath);
            }
          },
          child: const Text('退出'),
        ),
      ],
    ),
  );
}

String _phoneMask(String phone) {
  if (phone.length < 7) return phone.isEmpty ? '手机号待同步' : phone;
  return '${phone.substring(0, 3)} **** ${phone.substring(phone.length - 4)}';
}

const _darkTitle = TextStyle(
  color: Colors.white,
  fontFamily: AppTypography.systemFont,
  fontSize: 18,
  fontWeight: FontWeight.w800,
  letterSpacing: 0,
);

final _darkSub = TextStyle(
  color: Colors.white.withValues(alpha: 0.66),
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w700,
  height: 1.45,
  letterSpacing: 0,
);
