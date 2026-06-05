import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/devices/application/device_repository.dart';
import 'package:guardian_parent_app/src/features/devices/domain/device_models.dart';
import 'package:guardian_parent_app/src/features/auth/application/auth_repository.dart';
import 'package:guardian_parent_app/src/features/live_care/application/camera_repository.dart';
import 'package:guardian_parent_app/src/features/points/application/point_repository.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/features/rewards/application/reward_repository.dart';
import 'package:guardian_parent_app/src/features/rewards/domain/reward_models.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_list_row.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_screen.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_state_view.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_surface.dart';
import 'package:guardian_parent_app/src/shared/widgets/status_chip.dart';

class AccountProfilePage extends ConsumerWidget {
  const AccountProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(accountProfileProvider);
    return _Page(
      title: '个人信息',
      children: profile.when(
        data: (data) => [_AccountProfileForm(profile: data)],
        loading: () => const [_Loading(title: '正在同步个人信息')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(accountProfileProvider),
          ),
        ],
      ),
    );
  }
}

class _AccountProfileForm extends ConsumerStatefulWidget {
  const _AccountProfileForm({required this.profile});

  final AccountProfile profile;

  @override
  ConsumerState<_AccountProfileForm> createState() =>
      _AccountProfileFormState();
}

class _AccountProfileFormState extends ConsumerState<_AccountProfileForm> {
  late final TextEditingController _name;
  late final TextEditingController _family;
  late String _relationship;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.profile.displayName);
    _family = TextEditingController(text: widget.profile.familyName);
    _relationship = _normalizeParentIdentity(widget.profile.relationship);
    _name.addListener(_refreshPreview);
    _family.addListener(_refreshPreview);
  }

  @override
  void dispose() {
    _name.removeListener(_refreshPreview);
    _family.removeListener(_refreshPreview);
    _name.dispose();
    _family.dispose();
    super.dispose();
  }

  void _refreshPreview() {
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final displayName = _name.text.trim().isEmpty ? '家长' : _name.text.trim();
    final familyName = _family.text.trim().isEmpty
        ? '我的家庭空间'
        : _family.text.trim();
    final canSave =
        !_saving &&
        _name.text.trim().isNotEmpty &&
        _family.text.trim().isNotEmpty;

    return Column(
      children: [
        AppSurface(
          color: AppColors.ink,
          borderColor: AppColors.ink,
          radius: 26,
          padding: const EdgeInsets.fromLTRB(17, 17, 17, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _DarkIcon(Icons.person_outline),
                  const SizedBox(width: 13),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(displayName, style: _darkTitle),
                        const SizedBox(height: 5),
                        Text(_phoneMask(widget.profile.phone), style: _darkSub),
                      ],
                    ),
                  ),
                  StatusChip(label: '管理员', tone: StatusTone.neutral),
                ],
              ),
              const SizedBox(height: 16),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.06),
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: _DarkProfileFact(
                          label: '家庭空间',
                          value: familyName,
                        ),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: _DarkProfileFact(
                          label: '家庭身份',
                          value: _relationship,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppSurface(
          radius: 24,
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionTitle('资料设置'),
              const SizedBox(height: 12),
              _ProfileTextField(
                icon: Icons.badge_outlined,
                label: '显示称呼',
                controller: _name,
                hint: '例如：家长、爸爸、外婆',
              ),
              const SizedBox(height: 10),
              _ProfileTextField(
                icon: Icons.home_work_outlined,
                label: '家庭空间名称',
                controller: _family,
                hint: '例如：我的家庭空间',
              ),
              const SizedBox(height: 10),
              _ProfileSelectField(
                icon: Icons.supervisor_account_outlined,
                label: '家庭身份',
                value: _relationship,
                subtitle: '用于通知分发、家庭协作记录和权限判断。',
                onTap: _pickRelationship,
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppPrimaryButton(
          label: _saving ? '保存中' : '保存',
          loading: _saving,
          onTap: canSave ? _save : null,
        ),
      ],
    );
  }

  Future<void> _pickRelationship() async {
    final selected = await showAppPickerSheet<String>(
      context: context,
      title: '选择家庭身份',
      subtitle: '和初始设置保持一致，后续会用于通知和家庭协作记录。',
      selected: _relationship,
      options: const [
        AppPickerOption(
          value: '妈妈',
          label: '妈妈',
          description: '主要照护人或家庭管理员。',
          icon: Icons.face_3_outlined,
        ),
        AppPickerOption(
          value: '爸爸',
          label: '爸爸',
          description: '主要照护人或家庭管理员。',
          icon: Icons.face_outlined,
        ),
        AppPickerOption(
          value: '祖辈',
          label: '祖辈',
          description: '爷爷奶奶、外公外婆等家庭成员。',
          icon: Icons.elderly_outlined,
        ),
        AppPickerOption(
          value: '保姆',
          label: '保姆',
          description: '日常照护协助人员。',
          icon: Icons.diversity_1_outlined,
        ),
        AppPickerOption(
          value: '其他照护人',
          label: '其他照护人',
          description: '其他被授权参与看护的成年人。',
          icon: Icons.person_add_alt_1_outlined,
        ),
      ],
    );
    if (selected != null && mounted) {
      setState(() => _relationship = selected);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .updateAccountProfile(
            displayName: _name.text.trim(),
            familyName: _family.text.trim(),
            relationship: _relationship,
          );
      ref.invalidate(accountProfileProvider);
      ref.invalidate(profileSummaryProvider);
      if (mounted) _toast(context, '已保存');
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _DarkProfileFact extends StatelessWidget {
  const _DarkProfileFact({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.54),
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
            fontWeight: FontWeight.w700,
            height: 1.2,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white,
            fontFamily: AppTypography.systemFont,
            fontSize: 13,
            fontWeight: FontWeight.w900,
            height: 1.2,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

class _ProfileTextField extends StatelessWidget {
  const _ProfileTextField({
    required this.icon,
    required this.label,
    required this.controller,
    this.hint,
  });

  final IconData icon;
  final String label;
  final TextEditingController controller;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(13, 10, 13, 10),
        child: Row(
          children: [
            _SoftFieldIcon(icon),
            const SizedBox(width: 11),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: _fieldLabelStyle),
                  TextField(
                    controller: controller,
                    maxLines: 1,
                    decoration: InputDecoration(
                      hintText: hint,
                      border: InputBorder.none,
                      enabledBorder: InputBorder.none,
                      focusedBorder: InputBorder.none,
                      isDense: true,
                      contentPadding: const EdgeInsets.only(top: 5),
                    ),
                    style: _fieldValueStyle,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileSelectField extends StatelessWidget {
  const _ProfileSelectField({
    required this.icon,
    required this.label,
    required this.value,
    required this.onTap,
    this.subtitle,
  });

  final IconData icon;
  final String label;
  final String value;
  final String? subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: 18,
      color: AppColors.surface,
      borderColor: AppColors.borderSoft,
      padding: const EdgeInsets.fromLTRB(13, 12, 12, 12),
      onTap: onTap,
      child: Row(
        children: [
          _SoftFieldIcon(icon),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: _fieldLabelStyle),
                const SizedBox(height: 5),
                Text(value, style: _fieldValueStyle),
                if (subtitle != null) ...[
                  const SizedBox(height: 5),
                  Text(subtitle!, style: _mutedText),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          const Icon(Icons.chevron_right, color: AppColors.subtle, size: 20),
        ],
      ),
    );
  }
}

class _SoftFieldIcon extends StatelessWidget {
  const _SoftFieldIcon(this.icon);

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brand.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(14),
      ),
      child: SizedBox(
        width: 38,
        height: 38,
        child: Center(child: Icon(icon, color: AppColors.brand, size: 19)),
      ),
    );
  }
}

String _normalizeParentIdentity(String value) {
  final normalized = value.trim();
  const options = ['妈妈', '爸爸', '祖辈', '保姆', '其他照护人'];
  if (options.contains(normalized)) return normalized;
  if (const ['爷爷', '奶奶', '外公', '外婆'].contains(normalized)) {
    return '祖辈';
  }
  return '其他照护人';
}

class AccountSecurityPage extends ConsumerWidget {
  const AccountSecurityPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final security = ref.watch(accountSecurityProvider);
    return _Page(
      title: '账号安全',
      children: security.when(
        data: (data) => [
          AppSurface(
            child: Column(
              children: [
                AppListRow(
                  icon: Icons.smartphone_outlined,
                  title: '登录手机号',
                  subtitle: _phoneMask(data.phone),
                  tone: AppListRowTone.blue,
                ),
                AppListRow(
                  icon: Icons.verified_user_outlined,
                  title: '登录方式',
                  subtitle: '手机号验证码',
                  tone: AppListRowTone.green,
                  trailing: StatusChip(label: '正常', tone: StatusTone.success),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          AppSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionTitle('登录设备'),
                const SizedBox(height: 8),
                if (data.loginDevices.isEmpty)
                  const Text('暂无其他登录设备记录。', style: _mutedText)
                else
                  for (final device in data.loginDevices)
                    AppListRow(
                      icon: Icons.devices_outlined,
                      title: device.label,
                      subtitle: device.active ? '当前有效' : '已失效',
                      tone: device.active
                          ? AppListRowTone.green
                          : AppListRowTone.neutral,
                    ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          AppSecondaryButton(
            label: '退出登录',
            trailing: const Icon(Icons.logout_outlined, size: 18),
            onTap: () => _confirmLogout(context, ref),
          ),
        ],
        loading: () => const [_Loading(title: '正在同步账号安全')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(accountSecurityProvider),
          ),
        ],
      ),
    );
  }
}

class FamilyHubPage extends StatelessWidget {
  const FamilyHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _HubPage(
      title: '家庭与成员',
      sections: [
        _HubSection(
          title: '家庭协作',
          rows: [
            _HubRow(
              icon: Icons.groups_outlined,
              title: '家庭成员',
              subtitle: '成员邀请、权限和通知范围',
              path: profileFamilyMembersPath,
              tone: AppListRowTone.green,
            ),
            _HubRow(
              icon: Icons.child_care_outlined,
              title: '孩子资料',
              subtitle: '阶段、兴趣和任务偏好',
              path: profileChildPath,
            ),
            _HubRow(
              icon: Icons.contact_phone_outlined,
              title: '紧急联系人',
              subtitle: '重要情况的通知对象',
              path: profileContactsPath,
            ),
          ],
        ),
      ],
    );
  }
}

class DeviceCareHubPage extends StatelessWidget {
  const DeviceCareHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _HubPage(
      title: '设备与看护',
      sections: [
        _HubSection(
          title: '设备',
          rows: [
            _HubRow(
              icon: Icons.videocam_outlined,
              title: '设备管理',
              subtitle: '设备名称、房间、网络、解绑和状态',
              path: profileDevicesPath,
              tone: AppListRowTone.blue,
            ),
            _HubRow(
              icon: Icons.lock_outline,
              title: '看护采集授权',
              subtitle: '摄像头、语音播报和数据保留',
              path: profilePrivacyPath,
            ),
          ],
        ),
      ],
    );
  }
}

class TaskRewardHubPage extends StatelessWidget {
  const TaskRewardHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _HubPage(
      title: '积分与奖励',
      sections: [
        _HubSection(
          title: '积分与奖励',
          rows: [
            _HubRow(
              icon: Icons.stars_outlined,
              title: '积分账户',
              subtitle: '当前积分和积分流水',
              path: pointsPath,
              tone: AppListRowTone.amber,
            ),
            _HubRow(
              icon: Icons.card_giftcard_outlined,
              title: '奖励中心',
              subtitle: '创建、编辑和兑换奖励项',
              path: rewardsPath,
            ),
            _HubRow(
              icon: Icons.history_outlined,
              title: '兑换记录',
              subtitle: '待兑现、已兑现和取消记录',
              path: redemptionsPath,
            ),
          ],
        ),
        _HubSection(
          title: '记录',
          rows: [
            _HubRow(
              icon: Icons.today_outlined,
              title: '今日报告',
              subtitle: '今天的任务、积分和待处理',
              path: profileDailyReportPath,
            ),
            _HubRow(
              icon: Icons.calendar_month_outlined,
              title: '周报',
              subtitle: '本周完成节奏和积分',
              path: profileWeeklyReportPath,
            ),
            _HubRow(
              icon: Icons.bookmark_outline,
              title: '成长时刻',
              subtitle: '家长保存的积极片段',
              path: profileMomentsPath,
            ),
          ],
        ),
      ],
    );
  }
}

class RulesReminderHubPage extends StatelessWidget {
  const RulesReminderHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _HubPage(
      title: 'AI 规则与提醒',
      sections: [
        _HubSection(
          title: '规则',
          rows: [
            _HubRow(
              icon: Icons.auto_awesome_outlined,
              title: 'AI 看护规则',
              subtitle: '任务观察、拖拉提醒和语音播报',
              path: profileAiRulesPath,
            ),
            _HubRow(
              icon: Icons.notifications_outlined,
              title: '通知与提醒',
              subtitle: '任务、设备和积分提醒',
              path: profileNotificationsPath,
            ),
            _HubRow(
              icon: Icons.record_voice_over_outlined,
              title: '对话与人设',
              subtitle: '唤醒名、语音风格和对话边界',
              path: profileConversationPath,
            ),
            _HubRow(
              icon: Icons.menu_book_outlined,
              title: '学习内容',
              subtitle: '小书包、课程表和内容偏好',
              path: profileEducationPath,
            ),
          ],
        ),
      ],
    );
  }
}

class PrivacyAuthorizationHubPage extends StatelessWidget {
  const PrivacyAuthorizationHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _HubPage(
      title: '隐私与授权',
      sections: [
        _HubSection(
          title: '授权',
          rows: [
            _HubRow(
              icon: Icons.lock_outline,
              title: '隐私与权限',
              subtitle: '采集授权、语音播报和数据保留',
              path: profilePrivacyPath,
            ),
            _HubRow(
              icon: Icons.child_care_outlined,
              title: '儿童隐私授权说明',
              subtitle: '儿童数据处理和家长授权说明',
              path: profileChildPrivacyPath,
            ),
          ],
        ),
        _HubSection(
          title: '协议',
          rows: [
            _HubRow(
              icon: Icons.description_outlined,
              title: '用户协议',
              subtitle: '使用规则和服务说明',
              path: userAgreementPath,
            ),
            _HubRow(
              icon: Icons.privacy_tip_outlined,
              title: '隐私政策',
              subtitle: '数据收集、使用和保护说明',
              path: privacyPolicyPath,
            ),
          ],
        ),
      ],
    );
  }
}

class AccountSettingsHubPage extends StatelessWidget {
  const AccountSettingsHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return const _HubPage(
      title: '账号设置',
      sections: [
        _HubSection(
          title: '资料与安全',
          rows: [
            _HubRow(
              icon: Icons.account_circle_outlined,
              title: '个人信息',
              subtitle: '显示名、家庭名称和家庭身份',
              path: profileAccountPath,
            ),
            _HubRow(
              icon: Icons.verified_user_outlined,
              title: '账号安全',
              subtitle: '手机号、登录方式和登录设备',
              path: profileSecurityPath,
              tone: AppListRowTone.green,
            ),
          ],
        ),
        _HubSection(
          title: '支持',
          rows: [
            _HubRow(
              icon: Icons.info_outline,
              title: '关于',
              subtitle: '帮助反馈、当前版本和协议政策',
              path: profileAboutPath,
            ),
          ],
        ),
      ],
    );
  }
}

class FamilyMembersPage extends ConsumerWidget {
  const FamilyMembersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(familyMembersProvider);
    final invitations = ref.watch(familyInvitationsProvider);
    return _Page(
      title: '家庭成员',
      trailing: AppIconButton(
        icon: Icons.person_add_outlined,
        label: '新增成员',
        onTap: () => _editMember(context, ref),
      ),
      children: members.when(
        data: (items) => [
          if (items.isEmpty)
            const AppStateView(
              variant: AppStateVariant.noData,
              title: '还没有家庭成员',
              message: '添加照护人后，可一起处理任务确认和重要提醒。',
              compact: true,
            )
          else
            AppSurface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const _SectionTitle('家庭成员'),
                  const SizedBox(height: 8),
                  for (final member in items)
                    AppListRow(
                      icon: Icons.group_outlined,
                      title: member.name,
                      subtitle:
                          '${member.roleLabel} · ${member.statusLabel}${member.phone.isEmpty ? '' : ' · ${_phoneMask(member.phone)}'}',
                      tone: member.role == 'admin'
                          ? AppListRowTone.green
                          : AppListRowTone.blue,
                      trailing: member.userId.isEmpty
                          ? TextButton(
                              onPressed: () =>
                                  _editMember(context, ref, member: member),
                              child: const Text('编辑'),
                            )
                          : const StatusChip(
                              label: '本人',
                              tone: StatusTone.success,
                            ),
                    ),
                ],
              ),
            ),
          invitations.when(
            data: (items) => items.isEmpty
                ? const SizedBox.shrink()
                : AppSurface(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const _SectionTitle('待接受邀请'),
                        const SizedBox(height: 8),
                        for (final invitation in items)
                          AppListRow(
                            icon: Icons.mail_outline,
                            title: invitation.name,
                            subtitle:
                                '${invitation.roleLabel} · ${invitation.statusLabel}${invitation.phone.isEmpty ? '' : ' · ${_phoneMask(invitation.phone)}'}',
                            tone: AppListRowTone.amber,
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                TextButton(
                                  onPressed: () => _resendInvitation(
                                    context,
                                    ref,
                                    invitation,
                                  ),
                                  child: const Text('重发'),
                                ),
                                TextButton(
                                  onPressed: () => _cancelInvitation(
                                    context,
                                    ref,
                                    invitation,
                                  ),
                                  child: const Text('取消'),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ),
                  ),
            loading: () =>
                const AppLoadingState(title: '正在同步邀请', message: '请稍候。'),
            error: (error, _) => AppStateView(
              variant: AppStateVariant.serviceUnavailable,
              title: '邀请暂时无法同步',
              message: error is ProfileException ? error.message : '请稍后重试。',
              primaryActionLabel: '重新加载',
              onPrimaryAction: () => ref.invalidate(familyInvitationsProvider),
              compact: true,
            ),
          ),
        ],
        loading: () => const [_Loading(title: '正在同步家庭成员')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(familyMembersProvider),
          ),
        ],
      ),
    );
  }
}

class ChildProfilePage extends ConsumerWidget {
  const ChildProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final child = ref.watch(currentChildProvider);
    return _Page(
      title: '孩子资料',
      children: child.when(
        data: (data) => data == null
            ? [
                const AppStateView(
                  variant: AppStateVariant.noData,
                  title: '还没有孩子资料',
                  message: '请先完成首次设置，之后可以在这里维护资料。',
                  compact: true,
                ),
              ]
            : [_ChildProfileForm(child: data)],
        loading: () => const [_Loading(title: '正在同步孩子资料')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(currentChildProvider),
          ),
        ],
      ),
    );
  }
}

class _ChildProfileForm extends ConsumerStatefulWidget {
  const _ChildProfileForm({required this.child});

  final ChildProfile child;

  @override
  ConsumerState<_ChildProfileForm> createState() => _ChildProfileFormState();
}

class _ChildProfileFormState extends ConsumerState<_ChildProfileForm> {
  late ChildProfile _draft;
  late final TextEditingController _name;
  late final TextEditingController _nickname;
  late final TextEditingController _birthday;
  late final TextEditingController _stage;
  late final TextEditingController _grade;
  late final TextEditingController _school;
  late final TextEditingController _interests;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    _draft = widget.child;
    _name = TextEditingController(text: _draft.name);
    _nickname = TextEditingController(text: _draft.nickname);
    _birthday = TextEditingController(text: _draft.birthday);
    _stage = TextEditingController(text: _draft.educationStage);
    _grade = TextEditingController(text: _draft.grade);
    _school = TextEditingController(text: _draft.schoolName);
    _interests = TextEditingController(text: _draft.interests.join('、'));
  }

  @override
  void dispose() {
    _name.dispose();
    _nickname.dispose();
    _birthday.dispose();
    _stage.dispose();
    _grade.dispose();
    _school.dispose();
    _interests.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        AppSurface(
          child: Column(
            children: [
              _Input(label: '姓名', controller: _name),
              const SizedBox(height: 12),
              _Input(label: '昵称', controller: _nickname),
              const SizedBox(height: 12),
              _Input(label: '生日', controller: _birthday, hint: '例如：2019-08-18'),
              const SizedBox(height: 12),
              _Input(label: '就读阶段', controller: _stage),
              const SizedBox(height: 12),
              _Input(label: '年级/班级', controller: _grade),
              const SizedBox(height: 12),
              _Input(label: '学校', controller: _school),
              const SizedBox(height: 12),
              _Input(label: '兴趣', controller: _interests, hint: '用顿号分隔'),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppPrimaryButton(
          label: _saving ? '保存中' : '保存资料',
          onTap: _saving ? null : _save,
        ),
      ],
    );
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final next = ChildProfile(
      id: _draft.id,
      name: _name.text.trim(),
      nickname: _nickname.text.trim(),
      birthday: _birthday.text.trim(),
      ageStage: _stage.text.trim(),
      educationStage: _stage.text.trim(),
      grade: _grade.text.trim(),
      schoolName: _school.text.trim(),
      interests: _interests.text
          .split(RegExp('[、,，]'))
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(),
      taskPreferences: _draft.taskPreferences,
    );
    try {
      _draft = await ref.read(profileRepositoryProvider).updateChild(next);
      ref.invalidate(currentChildProvider);
      ref.invalidate(profileSummaryProvider);
      if (mounted) _toast(context, '孩子资料已保存');
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class EmergencyContactsPage extends ConsumerWidget {
  const EmergencyContactsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final contacts = ref.watch(emergencyContactsProvider);
    return _Page(
      title: '紧急联系人',
      trailing: AppIconButton(
        icon: Icons.add,
        label: '新增联系人',
        onTap: () => _editContact(context, ref),
      ),
      children: contacts.when(
        data: (items) => [
          if (items.isEmpty)
            const AppStateView(
              variant: AppStateVariant.noData,
              title: '还没有紧急联系人',
              message: '添加后，重要情况可同步通知到指定照护人。',
              compact: true,
            )
          else
            AppSurface(
              child: Column(
                children: [
                  for (final contact in items)
                    AppListRow(
                      icon: Icons.contact_phone_outlined,
                      title: contact.name,
                      subtitle:
                          '${contact.relationship.isEmpty ? '联系人' : contact.relationship} · ${_phoneMask(contact.phone)}',
                      tone: contact.defaultNotify
                          ? AppListRowTone.green
                          : AppListRowTone.neutral,
                      trailing: TextButton(
                        onPressed: () =>
                            _editContact(context, ref, contact: contact),
                        child: const Text('编辑'),
                      ),
                    ),
                ],
              ),
            ),
        ],
        loading: () => const [_Loading(title: '正在同步紧急联系人')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(emergencyContactsProvider),
          ),
        ],
      ),
    );
  }
}

class DeviceManagementPage extends ConsumerWidget {
  const DeviceManagementPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devices = ref.watch(devicesProvider);
    return _Page(
      title: '设备管理',
      children: devices.when(
        data: (items) => [
          if (items.isEmpty)
            const AppStateView(
              variant: AppStateVariant.deviceOffline,
              title: '还没有绑定设备',
              message: '完成设备绑定后，可以在这里查看状态和管理设备。',
              compact: true,
            )
          else
            AppSurface(
              child: Column(
                children: [
                  for (final device in items)
                    AppListRow(
                      icon: Icons.videocam_outlined,
                      title: device.displayName,
                      subtitle: device.displayLocation,
                      tone: device.isOnlineLike
                          ? AppListRowTone.green
                          : AppListRowTone.neutral,
                      trailing: StatusChip(
                        label: device.status == 'unbound' ? '已解绑' : '已绑定',
                        tone: device.status == 'unbound'
                            ? StatusTone.neutral
                            : StatusTone.success,
                      ),
                      onTap: () =>
                          context.push('$profileDeviceDetailPath/${device.id}'),
                    ),
                ],
              ),
            ),
          const SizedBox(height: 14),
          AppSecondaryButton(
            label: '摄像头与看护状态',
            trailing: const Icon(Icons.shield_outlined, size: 18),
            onTap: () => context.push(profileCameraStatusPath),
          ),
        ],
        loading: () => const [_Loading(title: '正在同步设备')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(devicesProvider),
          ),
        ],
      ),
    );
  }
}

class DeviceDetailPage extends ConsumerStatefulWidget {
  const DeviceDetailPage({required this.deviceId, super.key});

  final String deviceId;

  @override
  ConsumerState<DeviceDetailPage> createState() => _DeviceDetailPageState();
}

class _DeviceDetailPageState extends ConsumerState<DeviceDetailPage> {
  final _name = TextEditingController();
  final _location = TextEditingController();
  var _initialized = false;
  var _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _location.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final overview = ref.watch(deviceOverviewProvider(widget.deviceId));
    return _Page(
      title: '设备详情',
      children: overview.when(
        data: (data) {
          if (!_initialized) {
            _name.text = data.device.name;
            _location.text = data.device.location;
            _initialized = true;
          }
          return [
            _DeviceDetailBody(
              overview: data,
              name: _name,
              location: _location,
              saving: _saving,
              onSave: _save,
              onUnbind: _unbind,
            ),
          ];
        },
        loading: () => const [_Loading(title: '正在同步设备详情')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () =>
                ref.invalidate(deviceOverviewProvider(widget.deviceId)),
          ),
        ],
      ),
    );
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(deviceRepositoryProvider)
          .updateDevice(
            deviceId: widget.deviceId,
            name: _name.text.trim(),
            location: _location.text.trim(),
          );
      ref.invalidate(deviceOverviewProvider(widget.deviceId));
      ref.invalidate(devicesProvider);
      if (mounted) _toast(context, '设备信息已保存');
    } on DeviceException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _unbind() async {
    final confirmed = await _confirm(
      context,
      title: '解绑设备',
      message: '解绑后将停止远程看护和任务提醒，确认继续吗？',
      danger: true,
    );
    if (!confirmed) return;
    try {
      await ref.read(deviceRepositoryProvider).unbindDevice(widget.deviceId);
      ref.invalidate(devicesProvider);
      if (mounted) context.pop();
    } on DeviceException catch (error) {
      if (mounted) _toast(context, error.message);
    }
  }
}

class _DeviceDetailBody extends StatelessWidget {
  const _DeviceDetailBody({
    required this.overview,
    required this.name,
    required this.location,
    required this.saving,
    required this.onSave,
    required this.onUnbind,
  });

  final DeviceOverview overview;
  final TextEditingController name;
  final TextEditingController location;
  final bool saving;
  final VoidCallback onSave;
  final VoidCallback onUnbind;

  @override
  Widget build(BuildContext context) {
    final status = overview.status;
    return Column(
      children: [
        AppSurface(
          color: AppColors.ink,
          borderColor: AppColors.ink,
          radius: 24,
          child: Row(
            children: [
              _DarkIcon(Icons.videocam_outlined),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(overview.device.displayName, style: _darkTitle),
                    const SizedBox(height: 5),
                    Text(
                      status?.message.isNotEmpty == true
                          ? status!.message
                          : overview.subtitle,
                      style: _darkSub,
                    ),
                  ],
                ),
              ),
              StatusChip(label: overview.connectionLabel, tone: overview.tone),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppSurface(
          child: Column(
            children: [
              _Input(label: '设备名称', controller: name),
              const SizedBox(height: 12),
              _Input(label: '房间位置', controller: location),
              const SizedBox(height: 12),
              AppListRow(
                icon: Icons.wifi_outlined,
                title: '网络状态',
                subtitle: status?.networkLabel ?? '等待同步',
                tone: AppListRowTone.green,
              ),
              AppListRow(
                icon: Icons.camera_alt_outlined,
                title: '摄像头',
                subtitle: status?.snapshotSupported == true
                    ? '可查看画面和快照'
                    : '暂不可用',
                tone: status?.snapshotSupported == true
                    ? AppListRowTone.green
                    : AppListRowTone.neutral,
              ),
              AppListRow(
                icon: Icons.volume_up_outlined,
                title: '扬声器',
                subtitle: status?.twoWayAudioSupported == true
                    ? '可语音提醒'
                    : '暂不可用',
                tone: status?.twoWayAudioSupported == true
                    ? AppListRowTone.green
                    : AppListRowTone.neutral,
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppPrimaryButton(
          label: saving ? '保存中' : '保存设备信息',
          onTap: saving ? null : onSave,
        ),
        const SizedBox(height: 10),
        AppSecondaryButton(
          label: '解绑设备',
          trailing: const Icon(Icons.power_settings_new_outlined, size: 18),
          onTap: onUnbind,
        ),
      ],
    );
  }
}

class CameraCareStatusPage extends ConsumerWidget {
  const CameraCareStatusPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(cameraStatusProvider);
    final health = ref.watch(cameraHealthProvider);
    return _Page(
      title: '摄像头与看护',
      children: [
        status.when(
          data: (data) => AppSurface(
            color: AppColors.ink,
            borderColor: AppColors.ink,
            radius: 24,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(data.label, style: _darkTitle),
                const SizedBox(height: 7),
                Text(data.message, style: _darkSub),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    StatusChip(
                      label: data.snapshotAvailable ? '摄像头可达' : '摄像头离线',
                      tone: data.snapshotAvailable
                          ? StatusTone.success
                          : StatusTone.danger,
                    ),
                    StatusChip(
                      label: data.speakerAvailable ? '语音可用' : '语音暂不可用',
                      tone: data.speakerAvailable
                          ? StatusTone.success
                          : StatusTone.neutral,
                    ),
                    StatusChip(
                      label: data.monitorAvailable ? '看护可用' : '看护待同步',
                      tone: data.monitorAvailable
                          ? StatusTone.success
                          : StatusTone.neutral,
                    ),
                  ],
                ),
              ],
            ),
          ),
          loading: () => const _Loading(title: '正在同步摄像头状态'),
          error: (error, _) => _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(cameraStatusProvider),
          ),
        ),
        const SizedBox(height: 14),
        health.when(
          data: (data) => AppSurface(
            child: AppListRow(
              icon: Icons.health_and_safety_outlined,
              title: data.label,
              subtitle: data.message,
              tone: data.reachable ? AppListRowTone.green : AppListRowTone.red,
            ),
          ),
          loading: () => const SizedBox.shrink(),
          error: (_, _) => const SizedBox.shrink(),
        ),
      ],
    );
  }
}

class AiCareRulesPage extends StatelessWidget {
  const AiCareRulesPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: 'AI 看护规则',
    settingKey: 'ai-care-rules',
    rows: [
      _SettingRowSpec('taskObservationEnabled', '任务观察', '观察任务开始、进行和结束状态。'),
      _SettingRowSpec('voiceReminderEnabled', '语音提醒', '到点后由设备温和提醒孩子。'),
      _SettingRowSpec('delayReminderEnabled', '拖拉提醒', '还没开始时，按规则继续温和提醒。'),
    ],
  );
}

class NotificationSettingsPage extends StatelessWidget {
  const NotificationSettingsPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '通知与提醒',
    settingKey: 'notifications',
    rows: [
      _SettingRowSpec('taskReminder', '任务提醒', '任务开始前提醒家长和设备。'),
      _SettingRowSpec('taskEndReminder', '任务结束提醒', '结束后提醒家长确认。'),
      _SettingRowSpec('deviceOfflineReminder', '设备离线提醒', '设备离线时通知家长。'),
      _SettingRowSpec('pointsRewardReminder', '积分奖励提醒', '积分发放和奖励兑现时提醒。'),
    ],
  );
}

class PrivacyPermissionsPage extends StatelessWidget {
  const PrivacyPermissionsPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '隐私与权限',
    settingKey: 'privacy',
    rows: [
      _SettingRowSpec(
        'cameraCollectionAuthorized',
        '摄像头采集授权',
        '允许设备为任务和看护采集必要画面。',
      ),
      _SettingRowSpec('voiceBroadcastAuthorized', '语音播报授权', '允许设备进行任务提醒和温和提示。'),
      _SettingRowSpec('childPrivacyAuthorized', '儿童隐私授权', '确认监护人已授权儿童数据处理。'),
      _SettingRowSpec(
        'remoteViewingNoticeEnabled',
        '远程查看提示',
        '家长查看时设备端显示工作状态。',
      ),
      _SettingRowSpec('storeEventSnapshotsOnly', '只保存事件截图', '不默认保存全天连续录像。'),
    ],
    extraLegalLink: true,
  );
}

class ConversationRulesPage extends StatelessWidget {
  const ConversationRulesPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '对话与人设',
    settingKey: 'conversation',
    rows: [
      _SettingRowSpec('freeChatEnabled', '自由聊天', '允许短时间普通对话。'),
      _SettingRowSpec('homeworkModeRestricted', '作业模式限制', '作业中只回答任务相关问题。'),
      _SettingRowSpec('bedtimeQuietEnabled', '睡前安静模式', '睡前不主动开启长时间聊天。'),
      _SettingRowSpec('detailedTranscriptEnabled', '逐字记录', '默认只保留主题摘要。'),
    ],
  );
}

class EducationContentPage extends StatelessWidget {
  const EducationContentPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '学习内容',
    settingKey: 'education',
    rows: [
      _SettingRowSpec('schoolbagEnabled', '小书包提醒', '按课程表和家长设置准备物品。'),
      _SettingRowSpec('courseScheduleEnabled', '课程表', '用于辅助生成准备提醒。'),
      _SettingRowSpec('partnerContentEnabled', '合作内容', '仅在授权后接入第三方内容。'),
      _SettingRowSpec('learningDiagnosisEnabled', '学习诊断', '长期数据积累后再开启。'),
    ],
  );
}

class _BooleanSettingsPage extends ConsumerStatefulWidget {
  const _BooleanSettingsPage({
    required this.title,
    required this.settingKey,
    required this.rows,
    this.extraLegalLink = false,
  });

  final String title;
  final String settingKey;
  final List<_SettingRowSpec> rows;
  final bool extraLegalLink;

  @override
  ConsumerState<_BooleanSettingsPage> createState() =>
      _BooleanSettingsPageState();
}

class _BooleanSettingsPageState extends ConsumerState<_BooleanSettingsPage> {
  Map<String, dynamic>? _draft;
  var _saving = false;

  @override
  Widget build(BuildContext context) {
    final setting = ref.watch(profileSettingProvider(widget.settingKey));
    return _Page(
      title: widget.title,
      children: setting.when(
        data: (data) {
          _draft ??= Map<String, dynamic>.from(data.value);
          return [
            AppSurface(
              child: Column(
                children: [
                  for (final row in widget.rows)
                    _SwitchRow(
                      title: row.title,
                      subtitle: row.subtitle,
                      value: _draft![row.key] == true,
                      onChanged: (value) =>
                          setState(() => _draft![row.key] = value),
                    ),
                ],
              ),
            ),
            if (widget.extraLegalLink) ...[
              const SizedBox(height: 14),
              AppSecondaryButton(
                label: '儿童隐私授权说明',
                trailing: const Icon(Icons.description_outlined, size: 18),
                onTap: () => context.push(profileChildPrivacyPath),
              ),
            ],
            const SizedBox(height: 14),
            AppPrimaryButton(
              label: _saving ? '保存中' : '保存设置',
              onTap: _saving ? null : _save,
            ),
          ];
        },
        loading: () => const [_Loading(title: '正在同步设置')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () =>
                ref.invalidate(profileSettingProvider(widget.settingKey)),
          ),
        ],
      ),
    );
  }

  Future<void> _save() async {
    final value = _draft;
    if (value == null) return;
    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .updateSetting(widget.settingKey, value);
      ref.invalidate(profileSettingProvider(widget.settingKey));
      if (mounted) _toast(context, '设置已保存');
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class LegalRemoteDocumentPage extends ConsumerWidget {
  const LegalRemoteDocumentPage({required this.documentKey, super.key});

  final String documentKey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final document = ref.watch(legalDocumentProvider(documentKey));
    return _Page(
      title: document.when(
        data: (data) => data.title,
        loading: () => '法律文档',
        error: (_, _) => '法律文档',
      ),
      children: document.when(
        data: (data) => [
          AppSurface(child: Text(data.summary, style: _bodyText)),
          const SizedBox(height: 14),
          for (final section in data.sections) ...[
            AppSurface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(section.title, style: _sectionTitleStyle),
                  const SizedBox(height: 8),
                  for (final paragraph in section.paragraphs)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(paragraph, style: _bodyText),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],
          Text(
            '版本 ${data.version} · ${data.effectiveDate}',
            textAlign: TextAlign.center,
            style: _mutedText,
          ),
        ],
        loading: () => const [_Loading(title: '正在打开文档')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(legalDocumentProvider(documentKey)),
          ),
        ],
      ),
    );
  }
}

class AboutPage extends ConsumerWidget {
  const AboutPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final about = ref.watch(aboutInfoProvider);
    return _Page(
      title: '关于',
      children: about.when(
        data: (data) => [
          AppSurface(
            color: AppColors.ink,
            borderColor: AppColors.ink,
            radius: 24,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _DarkIcon(Icons.apartment_outlined),
                    const SizedBox(width: 13),
                    Expanded(child: Text(data.displayName, style: _darkTitle)),
                  ],
                ),
                const SizedBox(height: 10),
                Text(data.description, style: _darkSub),
              ],
            ),
          ),
          const SizedBox(height: 14),
          AppSurface(
            child: Column(
              children: [
                AppListRow(
                  icon: Icons.info_outline,
                  title: '当前版本',
                  subtitle: data.version,
                  tone: AppListRowTone.blue,
                ),
                AppListRow(
                  icon: Icons.feedback_outlined,
                  title: '帮助与反馈',
                  subtitle: '问题、建议和误判样例',
                  tone: AppListRowTone.green,
                  onTap: () => context.push(profileFeedbackPath),
                ),
                AppListRow(
                  icon: Icons.description_outlined,
                  title: '用户协议',
                  subtitle: '服务条款和使用边界',
                  onTap: () => context.push(userAgreementPath),
                ),
                AppListRow(
                  icon: Icons.lock_outline,
                  title: '隐私政策',
                  subtitle: '数据、权限和儿童隐私',
                  onTap: () => context.push(privacyPolicyPath),
                ),
                AppListRow(
                  icon: Icons.child_care_outlined,
                  title: '儿童隐私授权说明',
                  subtitle: '监护人授权和最小必要原则',
                  onTap: () => context.push(profileChildPrivacyPath),
                ),
              ],
            ),
          ),
        ],
        loading: () => const [_Loading(title: '正在同步应用信息')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(aboutInfoProvider),
          ),
        ],
      ),
    );
  }
}

class SubscriptionPage extends ConsumerStatefulWidget {
  const SubscriptionPage({super.key});

  @override
  ConsumerState<SubscriptionPage> createState() => _SubscriptionPageState();
}

class _SubscriptionPageState extends ConsumerState<SubscriptionPage> {
  final _planController = PageController(viewportFraction: 0.88);
  var _selectedPlanIndex = 0;
  String? _loadingPlanId;
  var _restoring = false;

  @override
  void dispose() {
    _planController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final subscription = ref.watch(subscriptionStatusProvider);
    final plans = ref.watch(subscriptionPlansProvider);
    final entitlements = ref.watch(subscriptionEntitlementsProvider);
    return _subscriptionScreen(subscription, plans, entitlements);
  }

  Widget _subscriptionScreen(
    AsyncValue<SubscriptionStatus> subscription,
    AsyncValue<List<SubscriptionPlan>> plans,
    AsyncValue<List<SubscriptionFeatureComparison>> entitlements,
  ) {
    final loading =
        subscription.isLoading || plans.isLoading || entitlements.isLoading;
    final error = subscription.error ?? plans.error ?? entitlements.error;
    if (loading && !subscription.hasValue) {
      return _Page(
        title: '订阅与套餐',
        children: const [_Loading(title: '正在同步套餐')],
      );
    }
    if (error != null && !subscription.hasValue) {
      return _Page(
        title: '订阅与套餐',
        children: [
          _ErrorState(
            error: error,
            onRetry: () {
              ref.invalidate(subscriptionStatusProvider);
              ref.invalidate(subscriptionPlansProvider);
              ref.invalidate(subscriptionEntitlementsProvider);
            },
          ),
        ],
      );
    }

    final current = subscription.asData?.value;
    final planList = plans.asData?.value ?? const [];
    final comparisons = entitlements.asData?.value ?? const [];
    if (current == null || planList.isEmpty) {
      return _Page(
        title: '订阅与套餐',
        children: const [_Loading(title: '正在同步套餐')],
      );
    }

    final basic = _findPlan(planList, 'basic');
    final member = _findPlan(planList, 'member');
    final family = _findPlan(planList, 'family_plus');
    final paidPlans = [?member, ?family];
    final visiblePlans = paidPlans.isNotEmpty ? paidPlans : [?basic];
    if (visiblePlans.isEmpty) {
      return _Page(
        title: '订阅与套餐',
        children: const [_Loading(title: '正在同步套餐')],
      );
    }

    final safeIndex = _selectedPlanIndex.clamp(0, visiblePlans.length - 1);
    final selectedPlan = visiblePlans[safeIndex];

    return _SubscriptionPaywallScaffold(
      current: current,
      basicPlan: basic,
      plans: visiblePlans,
      selectedIndex: safeIndex,
      selectedPlan: selectedPlan,
      planController: _planController,
      loadingPlanId: _loadingPlanId,
      restoring: _restoring,
      comparisonItems: comparisons,
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoute.profile.path);
        }
      },
      onPlanChanged: (index) => setState(() => _selectedPlanIndex = index),
      onCheckout: () => _startCheckout(selectedPlan),
      onRestore: _restore,
      onUserAgreement: () => context.push(userAgreementPath),
      onPrivacyPolicy: () => context.push(privacyPolicyPath),
      onChildPrivacy: () => context.push(profileChildPrivacyPath),
    );
  }

  SubscriptionPlan? _findPlan(List<SubscriptionPlan> plans, String id) {
    for (final plan in plans) {
      if (plan.id == id) return plan;
    }
    return null;
  }

  Future<void> _startCheckout(SubscriptionPlan plan) async {
    if (_loadingPlanId != null || _restoring) return;
    setState(() => _loadingPlanId = plan.id);
    try {
      final result = await ref
          .read(profileRepositoryProvider)
          .startSubscriptionCheckout(plan.id);
      if (!mounted) return;
      await _showSubscriptionResult(
        context,
        title: result.planTitle.isEmpty ? plan.title : result.planTitle,
        message: result.message,
      );
    } catch (error) {
      if (mounted) {
        await _showSubscriptionResult(
          context,
          title: plan.title,
          message: _errorMessage(error),
        );
      }
    } finally {
      if (mounted) setState(() => _loadingPlanId = null);
    }
  }

  Future<void> _restore() async {
    if (_restoring || _loadingPlanId != null) return;
    setState(() => _restoring = true);
    try {
      final result = await ref
          .read(profileRepositoryProvider)
          .restoreSubscription();
      if (!mounted) return;
      await _showSubscriptionResult(
        context,
        title: '恢复购买',
        message: result.message,
      );
      ref.invalidate(subscriptionStatusProvider);
      ref.invalidate(subscriptionEntitlementsProvider);
    } catch (error) {
      if (mounted) {
        await _showSubscriptionResult(
          context,
          title: '恢复购买',
          message: _errorMessage(error),
        );
      }
    } finally {
      if (mounted) setState(() => _restoring = false);
    }
  }
}

class _SubscriptionPaywallScaffold extends StatelessWidget {
  const _SubscriptionPaywallScaffold({
    required this.current,
    required this.basicPlan,
    required this.plans,
    required this.selectedIndex,
    required this.selectedPlan,
    required this.planController,
    required this.loadingPlanId,
    required this.restoring,
    required this.comparisonItems,
    required this.onBack,
    required this.onPlanChanged,
    required this.onCheckout,
    required this.onRestore,
    required this.onUserAgreement,
    required this.onPrivacyPolicy,
    required this.onChildPrivacy,
  });

  final SubscriptionStatus current;
  final SubscriptionPlan? basicPlan;
  final List<SubscriptionPlan> plans;
  final int selectedIndex;
  final SubscriptionPlan selectedPlan;
  final PageController planController;
  final String? loadingPlanId;
  final bool restoring;
  final List<SubscriptionFeatureComparison> comparisonItems;
  final VoidCallback onBack;
  final ValueChanged<int> onPlanChanged;
  final VoidCallback onCheckout;
  final VoidCallback onRestore;
  final VoidCallback onUserAgreement;
  final VoidCallback onPrivacyPolicy;
  final VoidCallback onChildPrivacy;

  @override
  Widget build(BuildContext context) {
    final safe = MediaQuery.paddingOf(context);
    final size = MediaQuery.sizeOf(context);
    final topSpace = (size.height * 0.43).clamp(302.0, 408.0);
    final bottomInset = safe.bottom + 136;
    final selectedIsCurrent = current.planId == selectedPlan.id;
    final loading = loadingPlanId == selectedPlan.id;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColors.ink,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      child: Scaffold(
        backgroundColor: AppColors.ink,
        body: Stack(
          children: [
            const Positioned.fill(child: _SubscriptionImageBackground()),
            ListView(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: EdgeInsets.fromLTRB(0, 0, 0, bottomInset),
              children: [
                SizedBox(height: topSpace),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 22),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _PaywallStatusLine(current: current),
                      const SizedBox(height: 13),
                      const Text('让看护更完整', style: _paywallLargeTitle),
                      const SizedBox(height: 10),
                      const Text(
                        '长期报告、趋势洞察和更细的任务提醒，帮你少盯屏幕，多看重点。',
                        style: _paywallBody,
                      ),
                      const SizedBox(height: 18),
                      _PaywallValueRail(
                        items: _paywallValueItems(
                          basicPlan: basicPlan,
                          comparisons: comparisonItems,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 22),
                _PaywallPlanPager(
                  plans: plans,
                  currentPlanId: current.planId,
                  selectedIndex: selectedIndex,
                  controller: planController,
                  loadingPlanId: loadingPlanId,
                  onPageChanged: onPlanChanged,
                ),
                const SizedBox(height: 14),
                _PaywallPageDots(count: plans.length, index: selectedIndex),
                const SizedBox(height: 18),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 22),
                  child: _PaywallFinePrint(
                    restoring: restoring,
                    onRestore: onRestore,
                    onUserAgreement: onUserAgreement,
                    onPrivacyPolicy: onPrivacyPolicy,
                    onChildPrivacy: onChildPrivacy,
                  ),
                ),
              ],
            ),
            Positioned(
              left: 0,
              right: 0,
              top: 0,
              child: _PaywallTopBar(safeTop: safe.top, onBack: onBack),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: _PaywallBottomBar(
                safeBottom: safe.bottom,
                plan: selectedPlan,
                active: selectedIsCurrent,
                loading: loading,
                onCheckout: onCheckout,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SubscriptionImageBackground extends StatelessWidget {
  const _SubscriptionImageBackground();

  static const imagePath =
      'assets/images/subscription/subscription-paywall-bg.png';

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Image.asset(
          imagePath,
          key: const ValueKey('subscriptionHeroImage'),
          fit: BoxFit.cover,
          width: double.infinity,
          height: double.infinity,
          alignment: Alignment.topCenter,
          errorBuilder: (_, _, _) => const _HeroImageFallback(),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.04),
                  Colors.black.withValues(alpha: 0.10),
                  Colors.black.withValues(alpha: 0.68),
                  Colors.black.withValues(alpha: 0.98),
                ],
                stops: const [0, 0.36, 0.62, 1],
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(0.70, -0.22),
                radius: 0.92,
                colors: [
                  Colors.transparent,
                  Colors.black.withValues(alpha: 0.25),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _HeroImageFallback extends StatelessWidget {
  const _HeroImageFallback();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(color: AppColors.ink),
      child: Stack(
        children: [
          Positioned(
            left: -40,
            right: -40,
            top: 80,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
              child: const SizedBox(height: 260),
            ),
          ),
          const Center(
            child: Icon(
              Icons.auto_graph_outlined,
              color: Colors.white,
              size: 48,
            ),
          ),
        ],
      ),
    );
  }
}

class _PaywallTopBar extends StatelessWidget {
  const _PaywallTopBar({required this.safeTop, required this.onBack});

  final double safeTop;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(18, safeTop + 10, 18, 0),
      child: Row(
        children: [
          GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onBack,
            child: Semantics(
              button: true,
              label: '返回我的',
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.30),
                  borderRadius: BorderRadius.circular(AppRadii.full),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.12),
                  ),
                ),
                child: const SizedBox(
                  width: AppControls.iconButtonSize,
                  height: AppControls.iconButtonSize,
                  child: Center(
                    child: Icon(
                      Icons.arrow_back_ios_new,
                      color: Colors.white,
                      size: 18,
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: 12),
          const Text(
            '订阅与套餐',
            style: TextStyle(
              color: Colors.white,
              fontFamily: AppTypography.systemFont,
              fontSize: 16,
              fontWeight: FontWeight.w900,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _PaywallStatusLine extends StatelessWidget {
  const _PaywallStatusLine({required this.current});

  final SubscriptionStatus current;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: Colors.white.withValues(alpha: 0.13)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
        child: Text(
          '${current.planLabel} ${current.statusLabel}',
          style: const TextStyle(
            color: Colors.white,
            fontFamily: AppTypography.systemFont,
            fontSize: 12,
            fontWeight: FontWeight.w800,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _PaywallValueRail extends StatelessWidget {
  const _PaywallValueRail({required this.items});

  final List<_PaywallValueItem> items;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        for (var index = 0; index < items.length; index++) ...[
          Expanded(child: _PaywallValueCell(item: items[index])),
          if (index != items.length - 1) const SizedBox(width: 8),
        ],
      ],
    );
  }
}

class _PaywallValueCell extends StatelessWidget {
  const _PaywallValueCell({required this.item});

  final _PaywallValueItem item;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(11, 10, 10, 11),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(item.icon, color: const Color(0xFFB8F2CF), size: 19),
            const SizedBox(height: 7),
            Text(item.title, style: _paywallValueTitle),
          ],
        ),
      ),
    );
  }
}

class _PaywallPlanPager extends StatelessWidget {
  const _PaywallPlanPager({
    required this.plans,
    required this.currentPlanId,
    required this.selectedIndex,
    required this.controller,
    required this.loadingPlanId,
    required this.onPageChanged,
  });

  final List<SubscriptionPlan> plans;
  final String currentPlanId;
  final int selectedIndex;
  final PageController controller;
  final String? loadingPlanId;
  final ValueChanged<int> onPageChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 188,
      child: PageView.builder(
        controller: controller,
        itemCount: plans.length,
        padEnds: true,
        onPageChanged: onPageChanged,
        itemBuilder: (context, index) {
          final selected = index == selectedIndex;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: AnimatedScale(
              scale: selected ? 1 : 0.965,
              duration: AppMotion.duration(context, 190),
              curve: Curves.easeOutCubic,
              child: _PaywallPlanCard(
                plan: plans[index],
                active: currentPlanId == plans[index].id,
                selected: selected,
                loading: loadingPlanId == plans[index].id,
              ),
            ),
          );
        },
      ),
    );
  }
}

class _PaywallPlanCard extends StatelessWidget {
  const _PaywallPlanCard({
    required this.plan,
    required this.active,
    required this.selected,
    required this.loading,
  });

  final SubscriptionPlan plan;
  final bool active;
  final bool selected;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final recommended = plan.recommended;
    final bg = recommended
        ? Colors.white
        : Colors.white.withValues(alpha: 0.90);
    final borderColor = recommended
        ? const Color(0xFFB8F2CF).withValues(alpha: selected ? 0.72 : 0.36)
        : Colors.white.withValues(alpha: 0.18);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: borderColor, width: recommended ? 1.2 : 0.8),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: selected ? 0.22 : 0.10),
            blurRadius: selected ? 26 : 16,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(17, 15, 17, 15),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Row(
                    children: [
                      Flexible(
                        child: Text(plan.title, style: _paywallPlanTitle),
                      ),
                      if (recommended || active) ...[
                        const SizedBox(width: 8),
                        _PaywallMiniBadge(label: active ? '当前' : '推荐'),
                      ],
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                _PaywallPrice(plan: plan),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              plan.subtitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: _paywallPlanSub,
            ),
            const Spacer(),
            Wrap(
              spacing: 7,
              runSpacing: 7,
              children: [
                for (final feature in plan.highlights.take(3))
                  _PaywallFeatureChip(label: feature),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _PaywallPrice extends StatelessWidget {
  const _PaywallPrice({required this.plan});

  final SubscriptionPlan plan;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(plan.price, style: _paywallPrice),
        const SizedBox(height: 3),
        Text(plan.billing, style: _paywallPriceSub),
      ],
    );
  }
}

class _PaywallMiniBadge extends StatelessWidget {
  const _PaywallMiniBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.successWash,
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
        child: Text(label, style: _paywallBadgeText),
      ),
    );
  }
}

class _PaywallFeatureChip extends StatelessWidget {
  const _PaywallFeatureChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.appBackgroundMid.withValues(alpha: 0.70),
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
        child: Text(label, style: _paywallFeatureText),
      ),
    );
  }
}

class _PaywallPageDots extends StatelessWidget {
  const _PaywallPageDots({required this.count, required this.index});

  final int count;
  final int index;

  @override
  Widget build(BuildContext context) {
    if (count <= 1) return const SizedBox.shrink();
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var i = 0; i < count; i++)
          AnimatedContainer(
            duration: AppMotion.duration(context, 180),
            curve: Curves.easeOutCubic,
            width: i == index ? 18 : 6,
            height: 6,
            margin: const EdgeInsets.symmetric(horizontal: 3),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: i == index ? 0.92 : 0.30),
              borderRadius: BorderRadius.circular(AppRadii.full),
            ),
          ),
      ],
    );
  }
}

class _PaywallFinePrint extends StatelessWidget {
  const _PaywallFinePrint({
    required this.restoring,
    required this.onRestore,
    required this.onUserAgreement,
    required this.onPrivacyPolicy,
    required this.onChildPrivacy,
  });

  final bool restoring;
  final VoidCallback onRestore;
  final VoidCallback onUserAgreement;
  final VoidCallback onPrivacyPolicy;
  final VoidCallback onChildPrivacy;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextButton(
          onPressed: restoring ? null : onRestore,
          child: Text(restoring ? '恢复中' : '恢复购买', style: _paywallLinkText),
        ),
        const SizedBox(height: 2),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 12,
          runSpacing: 2,
          children: [
            _PaywallLegalLink(label: '用户协议', onTap: onUserAgreement),
            _PaywallLegalLink(label: '隐私政策', onTap: onPrivacyPolicy),
            _PaywallLegalLink(label: '儿童隐私授权说明', onTap: onChildPrivacy),
          ],
        ),
      ],
    );
  }
}

class _PaywallLegalLink extends StatelessWidget {
  const _PaywallLegalLink({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(label, style: _paywallLegalText),
        ),
      ),
    );
  }
}

class _PaywallBottomBar extends StatelessWidget {
  const _PaywallBottomBar({
    required this.safeBottom,
    required this.plan,
    required this.active,
    required this.loading,
    required this.onCheckout,
  });

  final double safeBottom;
  final SubscriptionPlan plan;
  final bool active;
  final bool loading;
  final VoidCallback onCheckout;

  @override
  Widget build(BuildContext context) {
    final enabled = !active && !loading;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Colors.black.withValues(alpha: 0),
            Colors.black.withValues(alpha: 0.78),
            Colors.black.withValues(alpha: 0.98),
          ],
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(22, 22, 22, safeBottom + 16),
            child: Semantics(
              button: true,
              label: active ? '当前套餐' : plan.ctaLabel,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: enabled ? onCheckout : null,
                child: AnimatedContainer(
                  duration: AppMotion.duration(context, 190),
                  curve: Curves.easeOutCubic,
                  height: 54,
                  decoration: BoxDecoration(
                    color: active
                        ? Colors.white.withValues(alpha: 0.16)
                        : const Color(0xFFB8F2CF),
                    borderRadius: BorderRadius.circular(AppRadii.full),
                    boxShadow: [
                      if (!active)
                        BoxShadow(
                          color: const Color(
                            0xFFB8F2CF,
                          ).withValues(alpha: 0.24),
                          blurRadius: 20,
                          offset: const Offset(0, 10),
                        ),
                    ],
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        loading ? '处理中' : (active ? '当前套餐' : plan.ctaLabel),
                        style: TextStyle(
                          color: active
                              ? Colors.white.withValues(alpha: 0.72)
                              : AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 16,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 0,
                        ),
                      ),
                      if (loading) ...[
                        const SizedBox(width: 10),
                        const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            valueColor: AlwaysStoppedAnimation<Color>(
                              AppColors.ink,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

List<_PaywallValueItem> _paywallValueItems({
  required SubscriptionPlan? basicPlan,
  required List<SubscriptionFeatureComparison> comparisons,
}) {
  final preferred = comparisons
      .where((item) => item.member || item.familyPlus)
      .map((item) => item.name)
      .where((name) => name.isNotEmpty)
      .take(3)
      .toList();
  final labels = preferred.length >= 3 ? preferred : ['长期报告', '趋势洞察', '提醒基线'];
  return [
    _PaywallValueItem(icon: Icons.auto_graph_outlined, title: labels[0]),
    _PaywallValueItem(icon: Icons.insights_outlined, title: labels[1]),
    _PaywallValueItem(
      icon: Icons.notifications_active_outlined,
      title: labels[2],
    ),
  ];
}

class _PaywallValueItem {
  const _PaywallValueItem({required this.icon, required this.title});

  final IconData icon;
  final String title;
}

Future<void> _showSubscriptionResult(
  BuildContext context, {
  required String title,
  required String message,
}) {
  return showAppBottomSheet<void>(
    context: context,
    maxHeightFactor: 0.50,
    child: AppBottomSheetBody(
      title: title,
      subtitle: message.isEmpty ? '当前暂未开放在线付款。' : message,
      scrollable: false,
      footer: AppPrimaryButton(
        label: '知道了',
        onTap: () => Navigator.of(context).pop(),
      ),
      child: const SizedBox.shrink(),
    ),
  );
}

String _errorMessage(Object error) {
  if (error is ProfileException && error.message.isNotEmpty) {
    return error.message;
  }
  return '当前操作没有完成，请稍后再试。';
}

const _paywallLargeTitle = TextStyle(
  color: Colors.white,
  fontFamily: AppTypography.systemFont,
  fontSize: 34,
  fontWeight: FontWeight.w900,
  height: 1.08,
  letterSpacing: 0,
);

const _paywallBody = TextStyle(
  color: Color(0xDFFFFFFF),
  fontFamily: AppTypography.systemFont,
  fontSize: 16,
  fontWeight: FontWeight.w700,
  height: 1.42,
  letterSpacing: 0,
);

const _paywallValueTitle = TextStyle(
  color: Colors.white,
  fontFamily: AppTypography.systemFont,
  fontSize: 12.5,
  fontWeight: FontWeight.w900,
  height: 1.25,
  letterSpacing: 0,
);

const _paywallPlanTitle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 20,
  fontWeight: FontWeight.w900,
  height: 1.15,
  letterSpacing: 0,
);

const _paywallPlanSub = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 13,
  fontWeight: FontWeight.w700,
  height: 1.35,
  letterSpacing: 0,
);

const _paywallPrice = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 25,
  fontWeight: FontWeight.w900,
  height: 1.05,
  letterSpacing: 0,
);

const _paywallPriceSub = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 11.5,
  fontWeight: FontWeight.w800,
  height: 1.1,
  letterSpacing: 0,
);

const _paywallBadgeText = TextStyle(
  color: AppColors.success,
  fontFamily: AppTypography.systemFont,
  fontSize: 11,
  fontWeight: FontWeight.w900,
  letterSpacing: 0,
);

const _paywallFeatureText = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 11.5,
  fontWeight: FontWeight.w800,
  letterSpacing: 0,
);

const _paywallLinkText = TextStyle(
  color: Colors.white,
  fontFamily: AppTypography.systemFont,
  fontSize: 13,
  fontWeight: FontWeight.w900,
  letterSpacing: 0,
);

const _paywallLegalText = TextStyle(
  color: Color(0xBFFFFFFF),
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w700,
  letterSpacing: 0,
);

class DailyReportPage extends ConsumerWidget {
  const DailyReportPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      _ReportPage(title: '今日报告', provider: dailyReportProvider);
}

class WeeklyReportPage extends ConsumerWidget {
  const WeeklyReportPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      _ReportPage(title: '周报', provider: weeklyReportProvider);
}

class _ReportPage extends ConsumerWidget {
  const _ReportPage({required this.title, required this.provider});

  final String title;
  final FutureProvider<ReportData> provider;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final report = ref.watch(provider);
    return _Page(
      title: title,
      children: report.when(
        data: (data) => [
          AppSurface(
            color: AppColors.ink,
            borderColor: AppColors.ink,
            radius: 24,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(data.summary, style: _darkTitle),
                const SizedBox(height: 14),
                Row(
                  children: [
                    _Metric(
                      label: '任务',
                      value: '${data.taskCompleted}/${data.taskTotal}',
                    ),
                    const SizedBox(width: 8),
                    _Metric(label: '积分', value: '+${data.pointsEarned}'),
                    const SizedBox(width: 8),
                    _Metric(label: '待处理', value: '${data.pendingItems}'),
                  ],
                ),
              ],
            ),
          ),
        ],
        loading: () => const [_Loading(title: '正在生成报告')],
        error: (error, _) => [
          _ErrorState(error: error, onRetry: () => ref.invalidate(provider)),
        ],
      ),
    );
  }
}

class GrowthMomentsPage extends ConsumerWidget {
  const GrowthMomentsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final moments = ref.watch(growthMomentsProvider);
    return _Page(
      title: '成长时刻',
      children: moments.when(
        data: (items) => [
          if (items.isEmpty)
            const AppStateView(
              variant: AppStateVariant.noData,
              title: '还没有成长时刻',
              message: '家长保存后的积极片段会显示在这里。',
              compact: true,
            )
          else
            AppSurface(
              child: Column(
                children: [
                  for (final item in items)
                    AppListRow(
                      icon: Icons.auto_awesome_outlined,
                      title: item.title,
                      subtitle: '已保存',
                      tone: AppListRowTone.green,
                    ),
                ],
              ),
            ),
        ],
        loading: () => const [_Loading(title: '正在同步成长时刻')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(growthMomentsProvider),
          ),
        ],
      ),
    );
  }
}

class FeedbackPage extends ConsumerStatefulWidget {
  const FeedbackPage({super.key});

  @override
  ConsumerState<FeedbackPage> createState() => _FeedbackPageState();
}

class _FeedbackPageState extends ConsumerState<FeedbackPage> {
  final _content = TextEditingController();
  var _saving = false;

  @override
  void dispose() {
    _content.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return _Page(
      title: '帮助与反馈',
      children: [
        AppSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('把问题、建议或误判样例告诉我们。', style: _bodyText),
              const SizedBox(height: 14),
              _Input(label: '反馈内容', controller: _content, minLines: 5),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppPrimaryButton(
          label: _saving ? '提交中' : '提交反馈',
          onTap: _saving ? null : _submit,
        ),
      ],
    );
  }

  Future<void> _submit() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .submitFeedback(category: 'general', content: _content.text.trim());
      if (mounted) {
        _content.clear();
        _toast(context, '反馈已提交');
      }
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class RedemptionsPage extends ConsumerWidget {
  const RedemptionsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final redemptions = ref.watch(rewardRedemptionsProvider);
    return _Page(
      title: '兑换记录',
      children: redemptions.when(
        data: (items) => [
          if (items.isEmpty)
            const AppStateView(
              variant: AppStateVariant.emptyRewards,
              title: '还没有兑换记录',
              message: '家长兑换或兑现奖励后，会在这里留下记录。',
              compact: true,
            )
          else
            AppSurface(
              child: Column(
                children: [
                  for (final item in items) _RedemptionRow(item: item),
                ],
              ),
            ),
        ],
        loading: () => const [_Loading(title: '正在同步兑换记录')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(rewardRedemptionsProvider),
          ),
        ],
      ),
    );
  }
}

class _RedemptionRow extends ConsumerWidget {
  const _RedemptionRow({required this.item});

  final RewardRedemption item;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppListRow(
      icon: Icons.redeem_outlined,
      title: item.rewardTitle,
      subtitle: '${item.pointsCost} 分 · ${item.status.label}',
      tone: item.status == RedemptionStatus.fulfilled
          ? AppListRowTone.green
          : AppListRowTone.amber,
      trailing: item.canFulfill
          ? TextButton(onPressed: () => _fulfill(ref), child: const Text('兑现'))
          : StatusChip(label: item.status.label, tone: item.status.tone),
    );
  }

  Future<void> _fulfill(WidgetRef ref) async {
    await ref.read(rewardRepositoryProvider).fulfillRedemption(item.id);
    ref.invalidate(rewardRedemptionsProvider);
  }
}

class RewardEditPage extends ConsumerStatefulWidget {
  const RewardEditPage({this.itemId, super.key});

  final String? itemId;

  @override
  ConsumerState<RewardEditPage> createState() => _RewardEditPageState();
}

class _RewardEditPageState extends ConsumerState<RewardEditPage> {
  final _title = TextEditingController();
  final _cost = TextEditingController();
  final _description = TextEditingController();
  var _initialized = false;
  var _saving = false;

  @override
  void dispose() {
    _title.dispose();
    _cost.dispose();
    _description.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final itemId = widget.itemId;
    final detail = itemId == null
        ? null
        : ref.watch(rewardDetailProvider(itemId));
    if (detail == null) {
      return _body(null);
    }
    return detail.when(
      data: (item) {
        if (!_initialized) {
          _title.text = item.title;
          _cost.text = '${item.pointsCost}';
          _description.text = item.description;
          _initialized = true;
        }
        return _body(item);
      },
      loading: () => _Page(
        title: '奖励',
        children: const [_Loading(title: '正在同步奖励')],
      ),
      error: (error, _) => _Page(
        title: '奖励',
        children: [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(rewardDetailProvider(widget.itemId!)),
          ),
        ],
      ),
    );
  }

  Widget _body(RewardItem? item) {
    return _Page(
      title: item == null ? '添加奖励' : '编辑奖励',
      children: [
        AppSurface(
          child: Column(
            children: [
              _Input(label: '奖励名称', controller: _title),
              const SizedBox(height: 12),
              _Input(
                label: '所需积分',
                controller: _cost,
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 12),
              _Input(label: '说明', controller: _description, minLines: 3),
            ],
          ),
        ),
        const SizedBox(height: 14),
        AppPrimaryButton(
          label: _saving ? '保存中' : '保存奖励',
          onTap: _saving ? null : () => _save(item),
        ),
        if (item != null) ...[
          const SizedBox(height: 10),
          AppSecondaryButton(
            label: '删除奖励',
            trailing: const Icon(Icons.delete_outline, size: 18),
            onTap: () => _delete(item),
          ),
        ],
      ],
    );
  }

  Future<void> _save(RewardItem? item) async {
    setState(() => _saving = true);
    try {
      final childId = (await ref.read(
        pointsSummaryProvider.future,
      )).account.childId;
      final cost = int.tryParse(_cost.text.trim()) ?? 0;
      if (item == null) {
        await ref
            .read(rewardRepositoryProvider)
            .createItem(
              childId: childId,
              title: _title.text.trim(),
              pointsCost: cost,
              description: _description.text.trim(),
            );
      } else {
        await ref
            .read(rewardRepositoryProvider)
            .updateItem(
              itemId: item.id,
              title: _title.text.trim(),
              pointsCost: cost,
              description: _description.text.trim(),
            );
      }
      ref.invalidate(rewardsSummaryProvider);
      if (mounted) context.go(rewardsPath);
    } on Object catch (error) {
      if (mounted) {
        _toast(context, error is RewardException ? error.message : '奖励保存失败');
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _delete(RewardItem item) async {
    final confirmed = await _confirm(
      context,
      title: '删除奖励',
      message: '删除后不会影响已经产生的兑换记录。',
      danger: true,
    );
    if (!confirmed) return;
    await ref.read(rewardRepositoryProvider).deleteItem(item.id);
    ref.invalidate(rewardsSummaryProvider);
    if (mounted) context.go(rewardsPath);
  }
}

class _Page extends StatelessWidget {
  const _Page({
    required this.title,
    required this.children,
    this.subtitle,
    this.trailing,
    this.headerContent,
  });

  final String title;
  final String? subtitle;
  final List<Widget> children;
  final Widget? trailing;
  final Widget? headerContent;

  @override
  Widget build(BuildContext context) {
    return AppScreen(
      title: title,
      subtitle: subtitle,
      fixedHeader: true,
      reserveBottomNavigation: false,
      backLabel: '返回我的',
      headerContent: headerContent,
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoute.profile.path);
        }
      },
      trailing: trailing,
      children: children,
    );
  }
}

class _HubPage extends StatelessWidget {
  const _HubPage({required this.title, required this.sections});

  final String title;
  final List<_HubSection> sections;

  @override
  Widget build(BuildContext context) {
    return _Page(
      title: title,
      subtitle: _hubSubtitle(title),
      headerContent: _HubHeaderContent(
        title: title,
        subtitle: _hubSubtitle(title),
      ),
      children: [
        for (var index = 0; index < sections.length; index++)
          Padding(
            padding: EdgeInsets.only(
              bottom: index == sections.length - 1 ? 0 : 18,
            ),
            child: _HubSectionDeck(
              section: sections[index],
              showTitle: sections.length > 1,
            ),
          ),
      ],
    );
  }
}

String _hubSubtitle(String title) {
  return switch (title) {
    '家庭与成员' => '成员协作、孩子资料和紧急联系人',
    '设备与看护' => '设备状态、采集授权和声音能力',
    '任务与奖励' => '积分、奖励和成长记录',
    'AI 规则与提醒' => '观察策略、语音提醒和通知节奏',
    '隐私与授权' => '采集边界、儿童隐私和协议',
    _ => '设置',
  };
}

class _HubHeaderContent extends StatelessWidget {
  const _HubHeaderContent({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 22,
            fontWeight: FontWeight.w900,
            height: 1.12,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          subtitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 12,
            fontWeight: FontWeight.w700,
            height: 1.24,
            letterSpacing: 0,
          ),
        ),
      ],
    );
  }
}

class _HubSectionDeck extends StatelessWidget {
  const _HubSectionDeck({required this.section, required this.showTitle});

  final _HubSection section;
  final bool showTitle;

  @override
  Widget build(BuildContext context) {
    if (section.rows.isEmpty) return const SizedBox.shrink();
    final leading = section.rows.first;
    final remaining = section.rows.skip(1).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (showTitle)
          Padding(
            padding: const EdgeInsets.only(left: 2, bottom: 10),
            child: Text(section.title, style: _hubSectionTitleStyle),
          ),
        _HubFeatureLane(row: leading),
        if (remaining.isNotEmpty) ...[
          const SizedBox(height: 10),
          LayoutBuilder(
            builder: (context, constraints) {
              final useCompactPair =
                  constraints.maxWidth >= 340 && remaining.length == 2;
              if (useCompactPair) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: _HubMiniLane(row: remaining[0])),
                    const SizedBox(width: 10),
                    Expanded(child: _HubMiniLane(row: remaining[1])),
                  ],
                );
              }
              return Column(
                children: [
                  for (var index = 0; index < remaining.length; index++) ...[
                    _HubActionLane(row: remaining[index]),
                    if (index != remaining.length - 1)
                      const SizedBox(height: 10),
                  ],
                ],
              );
            },
          ),
        ],
      ],
    );
  }
}

class _HubFeatureLane extends StatelessWidget {
  const _HubFeatureLane({required this.row});

  final _HubRow row;

  @override
  Widget build(BuildContext context) {
    final color = _toneColor(row.tone);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.push(row.path),
      child: AppSurface(
        radius: 18,
        padding: const EdgeInsets.fromLTRB(16, 16, 14, 15),
        child: Row(
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(16),
              ),
              child: SizedBox(
                width: 48,
                height: 48,
                child: Center(child: Icon(row.icon, color: color, size: 22)),
              ),
            ),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(row.title, style: _hubFeatureTitleStyle),
                  const SizedBox(height: 5),
                  Text(row.subtitle, style: _hubSubtitleStyle),
                ],
              ),
            ),
            const SizedBox(width: 10),
            _HubArrow(color: color),
          ],
        ),
      ),
    );
  }
}

class _HubMiniLane extends StatelessWidget {
  const _HubMiniLane({required this.row});

  final _HubRow row;

  @override
  Widget build(BuildContext context) {
    final color = _toneColor(row.tone);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.push(row.path),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.58),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withValues(alpha: 0.74)),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 14, 12, 13),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.11),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: SizedBox(
                  width: 36,
                  height: 36,
                  child: Center(child: Icon(row.icon, color: color, size: 18)),
                ),
              ),
              const SizedBox(height: 11),
              Text(row.title, style: _hubMiniTitleStyle),
              const SizedBox(height: 5),
              Text(
                row.subtitle,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: _hubMiniSubtitleStyle,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HubActionLane extends StatelessWidget {
  const _HubActionLane({required this.row});

  final _HubRow row;

  @override
  Widget build(BuildContext context) {
    final color = _toneColor(row.tone);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.push(row.path),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.54),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withValues(alpha: 0.72)),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
          child: Row(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: SizedBox(
                  width: 38,
                  height: 38,
                  child: Center(child: Icon(row.icon, color: color, size: 19)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(row.title, style: _hubMiniTitleStyle),
                    const SizedBox(height: 4),
                    Text(row.subtitle, style: _hubSubtitleStyle),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              _HubArrow(color: color),
            ],
          ),
        ),
      ),
    );
  }
}

class _HubArrow extends StatelessWidget {
  const _HubArrow({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
      ),
      child: SizedBox(
        width: 30,
        height: 30,
        child: Center(child: Icon(Icons.chevron_right, color: color, size: 18)),
      ),
    );
  }
}

class _HubSection {
  const _HubSection({required this.title, required this.rows});

  final String title;
  final List<_HubRow> rows;
}

class _HubRow {
  const _HubRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.path,
    this.tone = AppListRowTone.neutral,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String path;
  final AppListRowTone tone;
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.1),
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
                ),
              ),
              const SizedBox(height: 4),
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

class _DarkIcon extends StatelessWidget {
  const _DarkIcon(this.icon);

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(16),
      ),
      child: SizedBox(
        width: 48,
        height: 48,
        child: Center(child: Icon(icon, color: Colors.white, size: 24)),
      ),
    );
  }
}

class _Input extends StatelessWidget {
  const _Input({
    required this.label,
    required this.controller,
    this.hint,
    this.minLines = 1,
    this.keyboardType,
  });

  final String label;
  final TextEditingController controller;
  final String? hint;
  final int minLines;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      minLines: minLines,
      maxLines: minLines == 1 ? 1 : 6,
      keyboardType: keyboardType,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.72),
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  const _SwitchRow({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: _rowTitle),
                const SizedBox(height: 4),
                Text(subtitle, style: _mutedText),
              ],
            ),
          ),
          Switch(value: value, onChanged: onChanged),
        ],
      ),
    );
  }
}

class _SettingRowSpec {
  const _SettingRowSpec(this.key, this.title, this.subtitle);

  final String key;
  final String title;
  final String subtitle;
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(text, style: _sectionTitleStyle);
}

class _Loading extends StatelessWidget {
  const _Loading({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) =>
      AppLoadingState(title: title, message: '请稍候。');
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return AppStateView(
      variant: AppStateVariant.serviceUnavailable,
      title: '暂时无法同步',
      message: error is ProfileException
          ? (error as ProfileException).message
          : '请稍后重试。',
      primaryActionLabel: '重新加载',
      onPrimaryAction: onRetry,
    );
  }
}

Future<void> _editMember(
  BuildContext context,
  WidgetRef ref, {
  FamilyMember? member,
}) async {
  final result = await showAppBottomSheet<_MemberEditResult>(
    context: context,
    maxHeightFactor: 0.64,
    child: _MemberEditSheet(
      member: member,
      submitLabel: member == null ? '发送邀请' : '保存',
    ),
  );
  if (result == null) return;
  try {
    final repository = ref.read(profileRepositoryProvider);
    if (member == null) {
      await repository.sendFamilyInvitation(
        name: result.name,
        phone: result.phone,
        role: result.role,
      );
    } else {
      await repository.saveFamilyMember(
        id: member.id,
        name: result.name,
        phone: result.phone,
        role: result.role,
      );
    }
    ref.invalidate(familyMembersProvider);
    ref.invalidate(familyInvitationsProvider);
    ref.invalidate(profileSummaryProvider);
    if (context.mounted) _toast(context, member == null ? '邀请已发送' : '已保存');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _editContact(
  BuildContext context,
  WidgetRef ref, {
  EmergencyContact? contact,
}) async {
  final result = await showAppBottomSheet<_ContactEditResult>(
    context: context,
    maxHeightFactor: 0.68,
    child: _ContactEditSheet(contact: contact),
  );
  if (result == null) return;
  if (result.deleteRequested && contact != null) {
    if (!context.mounted) return;
    final confirmed = await _confirm(
      context,
      title: '删除联系人',
      message: '确认删除这个紧急联系人吗？',
      danger: true,
    );
    if (!confirmed) return;
    try {
      await ref
          .read(profileRepositoryProvider)
          .deleteEmergencyContact(contact.id);
      ref.invalidate(emergencyContactsProvider);
      if (context.mounted) _toast(context, '联系人已删除');
    } on ProfileException catch (error) {
      if (context.mounted) _toast(context, error.message);
    }
    return;
  }
  try {
    await ref
        .read(profileRepositoryProvider)
        .saveEmergencyContact(
          id: contact?.id,
          name: result.name,
          phone: result.phone,
          relationship: result.relationship,
          defaultNotify: result.defaultNotify,
        );
    ref.invalidate(emergencyContactsProvider);
    if (context.mounted) _toast(context, '已保存');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _resendInvitation(
  BuildContext context,
  WidgetRef ref,
  FamilyInvitation invitation,
) async {
  try {
    await ref
        .read(profileRepositoryProvider)
        .resendFamilyInvitation(invitation.id);
    ref.invalidate(familyInvitationsProvider);
    if (context.mounted) _toast(context, '邀请已重发');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _cancelInvitation(
  BuildContext context,
  WidgetRef ref,
  FamilyInvitation invitation,
) async {
  final confirmed = await _confirm(
    context,
    title: '取消邀请',
    message: '取消后，对方将不能通过这条邀请加入家庭空间。',
    danger: true,
  );
  if (!confirmed) return;
  try {
    await ref
        .read(profileRepositoryProvider)
        .cancelFamilyInvitation(invitation.id);
    ref.invalidate(familyInvitationsProvider);
    if (context.mounted) _toast(context, '邀请已取消');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

class _MemberEditResult {
  const _MemberEditResult({
    required this.name,
    required this.phone,
    required this.role,
  });

  final String name;
  final String phone;
  final String role;
}

class _MemberEditSheet extends StatefulWidget {
  const _MemberEditSheet({required this.submitLabel, this.member});

  final FamilyMember? member;
  final String submitLabel;

  @override
  State<_MemberEditSheet> createState() => _MemberEditSheetState();
}

class _MemberEditSheetState extends State<_MemberEditSheet> {
  late final TextEditingController _name;
  late final TextEditingController _phone;
  late String _role;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.member?.name ?? '');
    _phone = TextEditingController(text: widget.member?.phone ?? '');
    _role = widget.member?.role ?? 'guardian';
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: widget.member == null ? '邀请家庭成员' : '编辑家庭成员',
      subtitle: widget.member == null
          ? '填写手机号后发送邀请，对方接受后加入家庭空间。'
          : '调整称呼和权限范围。',
      footer: Row(
        children: [
          Expanded(
            child: AppSecondaryButton(
              label: '取消',
              onTap: () => Navigator.of(context).pop(),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: AppPrimaryButton(
              label: widget.submitLabel,
              onTap: () => Navigator.of(context).pop(
                _MemberEditResult(
                  name: _name.text.trim(),
                  phone: _phone.text.trim(),
                  role: _role,
                ),
              ),
            ),
          ),
        ],
      ),
      child: Column(
        children: [
          _Input(label: '称呼', controller: _name, hint: '例如：爸爸、外婆'),
          const SizedBox(height: 12),
          _Input(
            label: '手机号',
            controller: _phone,
            keyboardType: TextInputType.phone,
          ),
          const SizedBox(height: 12),
          _PickerField(
            label: '角色',
            value: _memberRoleLabel(_role),
            onTap: _pickRole,
          ),
        ],
      ),
    );
  }

  Future<void> _pickRole() async {
    final selected = await showAppPickerSheet<String>(
      context: context,
      title: '选择角色',
      selected: _role,
      options: const [
        AppPickerOption(
          value: 'admin',
          label: '管理员',
          description: '可管理成员、设备和全部设置。',
        ),
        AppPickerOption(
          value: 'guardian',
          label: '监护人',
          description: '可查看看护状态并处理任务确认。',
        ),
        AppPickerOption(
          value: 'viewer',
          label: '仅接收通知',
          description: '只接收必要提醒，不管理设置。',
        ),
      ],
    );
    if (selected != null && mounted) setState(() => _role = selected);
  }
}

class _ContactEditResult {
  const _ContactEditResult({
    required this.name,
    required this.phone,
    required this.relationship,
    required this.defaultNotify,
    this.deleteRequested = false,
  });

  final String name;
  final String phone;
  final String relationship;
  final bool defaultNotify;
  final bool deleteRequested;
}

class _ContactEditSheet extends StatefulWidget {
  const _ContactEditSheet({this.contact});

  final EmergencyContact? contact;

  @override
  State<_ContactEditSheet> createState() => _ContactEditSheetState();
}

class _ContactEditSheetState extends State<_ContactEditSheet> {
  late final TextEditingController _name;
  late final TextEditingController _phone;
  late String _relationship;
  late bool _notify;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.contact?.name ?? '');
    _phone = TextEditingController(text: widget.contact?.phone ?? '');
    _relationship = widget.contact?.relationship ?? '家人';
    _notify = widget.contact?.defaultNotify ?? true;
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: widget.contact == null ? '添加紧急联系人' : '编辑紧急联系人',
      footer: Row(
        children: [
          if (widget.contact != null) ...[
            Expanded(
              child: AppSecondaryButton(
                label: '删除',
                onTap: () => Navigator.of(context).pop(
                  _ContactEditResult(
                    name: _name.text.trim(),
                    phone: _phone.text.trim(),
                    relationship: _relationship,
                    defaultNotify: _notify,
                    deleteRequested: true,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
          ],
          Expanded(
            child: AppSecondaryButton(
              label: '取消',
              onTap: () => Navigator.of(context).pop(),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: AppPrimaryButton(
              label: '保存',
              onTap: () => Navigator.of(context).pop(
                _ContactEditResult(
                  name: _name.text.trim(),
                  phone: _phone.text.trim(),
                  relationship: _relationship,
                  defaultNotify: _notify,
                ),
              ),
            ),
          ),
        ],
      ),
      child: Column(
        children: [
          _Input(label: '姓名', controller: _name),
          const SizedBox(height: 12),
          _Input(
            label: '手机号',
            controller: _phone,
            keyboardType: TextInputType.phone,
          ),
          const SizedBox(height: 12),
          _PickerField(
            label: '关系',
            value: _relationship,
            onTap: _pickRelationship,
          ),
          const SizedBox(height: 12),
          AppSurface(
            color: AppColors.surfaceSoft,
            borderColor: AppColors.borderSoft,
            padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
            child: Row(
              children: [
                const Expanded(
                  child: Text(
                    '默认通知这个联系人',
                    style: TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0,
                    ),
                  ),
                ),
                Switch(
                  value: _notify,
                  onChanged: (value) => setState(() => _notify = value),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pickRelationship() async {
    final selected = await showAppPickerSheet<String>(
      context: context,
      title: '选择关系',
      selected: _relationship,
      options: const [
        AppPickerOption(value: '爸爸', label: '爸爸'),
        AppPickerOption(value: '妈妈', label: '妈妈'),
        AppPickerOption(value: '爷爷', label: '爷爷'),
        AppPickerOption(value: '奶奶', label: '奶奶'),
        AppPickerOption(value: '外公', label: '外公'),
        AppPickerOption(value: '外婆', label: '外婆'),
        AppPickerOption(value: '家人', label: '其他家人'),
      ],
    );
    if (selected != null && mounted) setState(() => _relationship = selected);
  }
}

class _PickerField extends StatelessWidget {
  const _PickerField({
    required this.label,
    required this.value,
    required this.onTap,
  });

  final String label;
  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.surfaceSoft,
      borderColor: AppColors.borderSoft,
      padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
      onTap: onTap,
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: _mutedText),
                const SizedBox(height: 4),
                Text(value, style: _rowTitle),
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: AppColors.muted, size: 18),
        ],
      ),
    );
  }
}

String _memberRoleLabel(String role) {
  return switch (role) {
    'admin' => '管理员',
    'guardian' => '监护人',
    'viewer' => '仅接收通知',
    'caregiver' => '照护人',
    _ => '监护人',
  };
}

Future<bool> _confirm(
  BuildContext context, {
  required String title,
  required String message,
  bool danger = false,
}) async {
  return showAppConfirmSheet(
    context: context,
    title: title,
    message: message,
    confirmLabel: danger ? '确认' : '确定',
    danger: danger,
  );
}

Future<void> _confirmLogout(BuildContext context, WidgetRef ref) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '退出登录',
    message: '退出后再次进入需要手机号验证码，设备会继续执行已配置的任务和提醒。',
    confirmLabel: '退出',
    danger: true,
  );
  if (!confirmed) return;
  await ref.read(authRepositoryProvider).logout();
  if (context.mounted) context.go(loginPath);
}

void _toast(BuildContext context, String message) {
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

String _phoneMask(String phone) {
  if (phone.length < 7) return phone;
  return '${phone.substring(0, 3)} **** ${phone.substring(phone.length - 4)}';
}

Color _toneColor(AppListRowTone tone) {
  return switch (tone) {
    AppListRowTone.blue => AppColors.brand,
    AppListRowTone.green => AppColors.success,
    AppListRowTone.amber => AppColors.warning,
    AppListRowTone.red => AppColors.danger,
    AppListRowTone.neutral => AppColors.ink,
  };
}

const _hubSectionTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 18,
  fontWeight: FontWeight.w900,
  height: 1.16,
  letterSpacing: 0,
);
const _hubFeatureTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 16,
  fontWeight: FontWeight.w900,
  height: 1.18,
  letterSpacing: 0,
);
const _hubMiniTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w800,
  height: 1.22,
  letterSpacing: 0,
);
const _hubSubtitleStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w600,
  height: 1.4,
  letterSpacing: 0,
);
const _hubMiniSubtitleStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 11.5,
  fontWeight: FontWeight.w600,
  height: 1.35,
  letterSpacing: 0,
);

const _darkTitle = TextStyle(
  color: Colors.white,
  fontFamily: AppTypography.systemFont,
  fontSize: 20,
  fontWeight: FontWeight.w800,
  letterSpacing: 0,
);
final _darkSub = TextStyle(
  color: Colors.white.withValues(alpha: 0.68),
  fontFamily: AppTypography.systemFont,
  fontSize: 13,
  fontWeight: FontWeight.w600,
  height: 1.45,
  letterSpacing: 0,
);
const _sectionTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 17,
  fontWeight: FontWeight.w800,
  letterSpacing: 0,
);
const _rowTitle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w700,
  letterSpacing: 0,
);
const _fieldLabelStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 11.5,
  fontWeight: FontWeight.w700,
  height: 1.2,
  letterSpacing: 0,
);
const _fieldValueStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 15,
  fontWeight: FontWeight.w800,
  height: 1.25,
  letterSpacing: 0,
);
const _bodyText = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w600,
  height: 1.55,
  letterSpacing: 0,
);
const _mutedText = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w600,
  height: 1.45,
  letterSpacing: 0,
);
