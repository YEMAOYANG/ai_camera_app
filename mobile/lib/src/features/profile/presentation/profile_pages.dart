import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/theme/app_tokens.dart';
import 'package:mira_guardian_app/src/features/devices/application/device_repository.dart';
import 'package:mira_guardian_app/src/features/devices/domain/device_models.dart';
import 'package:mira_guardian_app/src/features/auth/application/auth_repository.dart';
import 'package:mira_guardian_app/src/features/live_care/application/camera_repository.dart';
import 'package:mira_guardian_app/src/features/points/application/point_repository.dart';
import 'package:mira_guardian_app/src/features/profile/application/profile_repository.dart';
import 'package:mira_guardian_app/src/features/profile/domain/profile_models.dart';
import 'package:mira_guardian_app/src/features/rewards/application/reward_repository.dart';
import 'package:mira_guardian_app/src/features/rewards/domain/reward_models.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_button.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_list_row.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_screen.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_surface.dart';
import 'package:mira_guardian_app/src/shared/widgets/status_chip.dart';

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
  late final TextEditingController _relationship;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.profile.displayName);
    _family = TextEditingController(text: widget.profile.familyName);
    _relationship = TextEditingController(text: widget.profile.relationship);
  }

  @override
  void dispose() {
    _name.dispose();
    _family.dispose();
    _relationship.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        MiraSurface(
          color: AppColors.ink,
          borderColor: AppColors.ink,
          radius: 24,
          child: Row(
            children: [
              _DarkIcon(Icons.person_outline),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _name.text.isEmpty ? '家长' : _name.text,
                      style: _darkTitle,
                    ),
                    const SizedBox(height: 5),
                    Text(
                      '${_phoneMask(widget.profile.phone)} · 管理员',
                      style: _darkSub,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        MiraSurface(
          child: Column(
            children: [
              _Input(label: '显示称呼', controller: _name),
              const SizedBox(height: 12),
              _Input(label: '家庭空间名称', controller: _family),
              const SizedBox(height: 12),
              _Input(label: '家庭身份', controller: _relationship),
            ],
          ),
        ),
        const SizedBox(height: 14),
        MiraPrimaryButton(
          label: _saving ? '保存中' : '保存',
          onTap: _saving ? null : _save,
        ),
      ],
    );
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .updateAccountProfile(
            displayName: _name.text.trim(),
            familyName: _family.text.trim(),
            relationship: _relationship.text.trim(),
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

class AccountSecurityPage extends ConsumerWidget {
  const AccountSecurityPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final security = ref.watch(accountSecurityProvider);
    return _Page(
      title: '账号安全',
      children: security.when(
        data: (data) => [
          MiraSurface(
            child: Column(
              children: [
                MiraListRow(
                  icon: Icons.smartphone_outlined,
                  title: '登录手机号',
                  subtitle: _phoneMask(data.phone),
                  tone: MiraListRowTone.blue,
                ),
                MiraListRow(
                  icon: Icons.verified_user_outlined,
                  title: '登录方式',
                  subtitle: '手机号验证码',
                  tone: MiraListRowTone.green,
                  trailing: StatusChip(label: '正常', tone: StatusTone.success),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          MiraSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const _SectionTitle('登录设备'),
                const SizedBox(height: 8),
                if (data.loginDevices.isEmpty)
                  const Text('暂无其他登录设备记录。', style: _mutedText)
                else
                  for (final device in data.loginDevices)
                    MiraListRow(
                      icon: Icons.devices_outlined,
                      title: device.label,
                      subtitle: device.active ? '当前有效' : '已失效',
                      tone: device.active
                          ? MiraListRowTone.green
                          : MiraListRowTone.neutral,
                    ),
              ],
            ),
          ),
          const SizedBox(height: 14),
          MiraSecondaryButton(
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

class FamilyMembersPage extends ConsumerWidget {
  const FamilyMembersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(familyMembersProvider);
    return _Page(
      title: '家庭成员',
      trailing: MiraIconButton(
        icon: Icons.person_add_outlined,
        label: '新增成员',
        onTap: () => _editMember(context, ref),
      ),
      children: members.when(
        data: (items) => [
          if (items.isEmpty)
            const MiraStateView(
              variant: MiraStateVariant.noData,
              title: '还没有家庭成员',
              message: '添加照护人后，可一起处理任务确认和重要提醒。',
              compact: true,
            )
          else
            MiraSurface(
              child: Column(
                children: [
                  for (final member in items)
                    MiraListRow(
                      icon: Icons.group_outlined,
                      title: member.name,
                      subtitle:
                          '${member.roleLabel} · ${member.statusLabel}${member.phone.isEmpty ? '' : ' · ${_phoneMask(member.phone)}'}',
                      tone: member.role == 'admin'
                          ? MiraListRowTone.green
                          : MiraListRowTone.blue,
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
                const MiraStateView(
                  variant: MiraStateVariant.noData,
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
        MiraSurface(
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
        MiraPrimaryButton(
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
      trailing: MiraIconButton(
        icon: Icons.add,
        label: '新增联系人',
        onTap: () => _editContact(context, ref),
      ),
      children: contacts.when(
        data: (items) => [
          if (items.isEmpty)
            const MiraStateView(
              variant: MiraStateVariant.noData,
              title: '还没有紧急联系人',
              message: '添加后，重要情况可同步通知到指定照护人。',
              compact: true,
            )
          else
            MiraSurface(
              child: Column(
                children: [
                  for (final contact in items)
                    MiraListRow(
                      icon: Icons.contact_phone_outlined,
                      title: contact.name,
                      subtitle:
                          '${contact.relationship.isEmpty ? '联系人' : contact.relationship} · ${_phoneMask(contact.phone)}',
                      tone: contact.defaultNotify
                          ? MiraListRowTone.green
                          : MiraListRowTone.neutral,
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
            const MiraStateView(
              variant: MiraStateVariant.deviceOffline,
              title: '还没有绑定设备',
              message: '完成设备绑定后，可以在这里查看状态和管理设备。',
              compact: true,
            )
          else
            MiraSurface(
              child: Column(
                children: [
                  for (final device in items)
                    MiraListRow(
                      icon: Icons.videocam_outlined,
                      title: device.displayName,
                      subtitle: device.displayLocation,
                      tone: device.isOnlineLike
                          ? MiraListRowTone.green
                          : MiraListRowTone.neutral,
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
          MiraSecondaryButton(
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
        MiraSurface(
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
        MiraSurface(
          child: Column(
            children: [
              _Input(label: '设备名称', controller: name),
              const SizedBox(height: 12),
              _Input(label: '房间位置', controller: location),
              const SizedBox(height: 12),
              MiraListRow(
                icon: Icons.wifi_outlined,
                title: '网络状态',
                subtitle: status?.networkLabel ?? '等待同步',
                tone: MiraListRowTone.green,
              ),
              MiraListRow(
                icon: Icons.camera_alt_outlined,
                title: '摄像头',
                subtitle: status?.snapshotSupported == true
                    ? '可查看画面和快照'
                    : '暂不可用',
                tone: status?.snapshotSupported == true
                    ? MiraListRowTone.green
                    : MiraListRowTone.neutral,
              ),
              MiraListRow(
                icon: Icons.volume_up_outlined,
                title: '扬声器',
                subtitle: status?.twoWayAudioSupported == true
                    ? '可语音提醒'
                    : '暂不可用',
                tone: status?.twoWayAudioSupported == true
                    ? MiraListRowTone.green
                    : MiraListRowTone.neutral,
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        MiraPrimaryButton(
          label: saving ? '保存中' : '保存设备信息',
          onTap: saving ? null : onSave,
        ),
        const SizedBox(height: 10),
        MiraSecondaryButton(
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
          data: (data) => MiraSurface(
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
          data: (data) => MiraSurface(
            child: MiraListRow(
              icon: Icons.health_and_safety_outlined,
              title: data.label,
              subtitle: data.message,
              tone: data.reachable
                  ? MiraListRowTone.green
                  : MiraListRowTone.red,
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
            MiraSurface(
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
              MiraSecondaryButton(
                label: '儿童隐私授权说明',
                trailing: const Icon(Icons.description_outlined, size: 18),
                onTap: () => context.push(profileChildPrivacyPath),
              ),
            ],
            const SizedBox(height: 14),
            MiraPrimaryButton(
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
          MiraSurface(child: Text(data.summary, style: _bodyText)),
          const SizedBox(height: 14),
          for (final section in data.sections) ...[
            MiraSurface(
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
          MiraSurface(
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
          MiraSurface(
            child: Column(
              children: [
                MiraListRow(
                  icon: Icons.info_outline,
                  title: '当前版本',
                  subtitle: data.version,
                  tone: MiraListRowTone.blue,
                ),
                MiraListRow(
                  icon: Icons.feedback_outlined,
                  title: '帮助与反馈',
                  subtitle: '问题、建议和误判样例',
                  tone: MiraListRowTone.green,
                  onTap: () => context.push(profileFeedbackPath),
                ),
                MiraListRow(
                  icon: Icons.description_outlined,
                  title: '用户协议',
                  subtitle: '服务条款和使用边界',
                  onTap: () => context.push(userAgreementPath),
                ),
                MiraListRow(
                  icon: Icons.lock_outline,
                  title: '隐私政策',
                  subtitle: '数据、权限和儿童隐私',
                  onTap: () => context.push(privacyPolicyPath),
                ),
                MiraListRow(
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

class SubscriptionPage extends ConsumerWidget {
  const SubscriptionPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final subscription = ref.watch(subscriptionStatusProvider);
    return _Page(
      title: '订阅与套餐',
      children: subscription.when(
        data: (data) => [
          MiraSurface(
            color: AppColors.ink,
            borderColor: AppColors.ink,
            radius: 24,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(data.planLabel, style: _darkTitle),
                const SizedBox(height: 6),
                Text(data.renewalText, style: _darkSub),
              ],
            ),
          ),
          const SizedBox(height: 14),
          MiraSurface(
            child: Column(
              children: [
                for (final item in data.entitlements)
                  MiraListRow(
                    icon: item.enabled
                        ? Icons.check_circle_outline
                        : Icons.lock_outline,
                    title: item.name,
                    subtitle: item.enabled ? '已包含' : '暂未启用',
                    tone: item.enabled
                        ? MiraListRowTone.green
                        : MiraListRowTone.neutral,
                  ),
              ],
            ),
          ),
        ],
        loading: () => const [_Loading(title: '正在同步套餐')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () => ref.invalidate(subscriptionStatusProvider),
          ),
        ],
      ),
    );
  }
}

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
          MiraSurface(
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
            const MiraStateView(
              variant: MiraStateVariant.noData,
              title: '还没有成长时刻',
              message: '家长保存后的积极片段会显示在这里。',
              compact: true,
            )
          else
            MiraSurface(
              child: Column(
                children: [
                  for (final item in items)
                    MiraListRow(
                      icon: Icons.auto_awesome_outlined,
                      title: item.title,
                      subtitle: '已保存',
                      tone: MiraListRowTone.green,
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
        MiraSurface(
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
        MiraPrimaryButton(
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
            const MiraStateView(
              variant: MiraStateVariant.emptyRewards,
              title: '还没有兑换记录',
              message: '家长兑换或兑现奖励后，会在这里留下记录。',
              compact: true,
            )
          else
            MiraSurface(
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
    return MiraListRow(
      icon: Icons.redeem_outlined,
      title: item.rewardTitle,
      subtitle: '${item.pointsCost} 分 · ${item.status.label}',
      tone: item.status == RedemptionStatus.fulfilled
          ? MiraListRowTone.green
          : MiraListRowTone.amber,
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
        MiraSurface(
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
        MiraPrimaryButton(
          label: _saving ? '保存中' : '保存奖励',
          onTap: _saving ? null : () => _save(item),
        ),
        if (item != null) ...[
          const SizedBox(height: 10),
          MiraSecondaryButton(
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
  const _Page({required this.title, required this.children, this.trailing});

  final String title;
  final List<Widget> children;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return MiraScreen(
      title: title,
      fixedHeader: true,
      backLabel: '返回我的',
      onBack: () => context.pop(),
      trailing: trailing,
      children: children,
    );
  }
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
      MiraLoadingState(title: title, message: '请稍候。');
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return MiraStateView(
      variant: MiraStateVariant.serviceUnavailable,
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
  final name = TextEditingController(text: member?.name ?? '');
  final phone = TextEditingController(text: member?.phone ?? '');
  var role = member?.role ?? 'guardian';
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(member == null ? '新增成员' : '编辑成员'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: name,
            decoration: const InputDecoration(labelText: '姓名'),
          ),
          TextField(
            controller: phone,
            decoration: const InputDecoration(labelText: '手机号'),
            keyboardType: TextInputType.phone,
          ),
          DropdownButtonFormField<String>(
            initialValue: role,
            items: const [
              DropdownMenuItem(value: 'guardian', child: Text('监护人')),
              DropdownMenuItem(value: 'caregiver', child: Text('照护人')),
              DropdownMenuItem(value: 'viewer', child: Text('查看者')),
            ],
            onChanged: (value) => role = value ?? role,
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('保存'),
        ),
      ],
    ),
  );
  if (result != true) return;
  try {
    await ref
        .read(profileRepositoryProvider)
        .saveFamilyMember(
          id: member?.id,
          name: name.text.trim(),
          phone: phone.text.trim(),
          role: role,
        );
    ref.invalidate(familyMembersProvider);
    ref.invalidate(profileSummaryProvider);
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _editContact(
  BuildContext context,
  WidgetRef ref, {
  EmergencyContact? contact,
}) async {
  final name = TextEditingController(text: contact?.name ?? '');
  final phone = TextEditingController(text: contact?.phone ?? '');
  final relationship = TextEditingController(text: contact?.relationship ?? '');
  var notify = contact?.defaultNotify ?? true;
  final result = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text(contact == null ? '新增联系人' : '编辑联系人'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: name,
            decoration: const InputDecoration(labelText: '姓名'),
          ),
          TextField(
            controller: phone,
            decoration: const InputDecoration(labelText: '手机号'),
            keyboardType: TextInputType.phone,
          ),
          TextField(
            controller: relationship,
            decoration: const InputDecoration(labelText: '关系'),
          ),
          SwitchListTile(
            title: const Text('默认通知'),
            value: notify,
            onChanged: (value) => notify = value,
          ),
        ],
      ),
      actions: [
        if (contact != null)
          TextButton(
            onPressed: () async {
              final confirmed = await _confirm(
                context,
                title: '删除联系人',
                message: '确认删除这个紧急联系人吗？',
                danger: true,
              );
              if (!confirmed) return;
              await ref
                  .read(profileRepositoryProvider)
                  .deleteEmergencyContact(contact.id);
              ref.invalidate(emergencyContactsProvider);
              if (context.mounted) Navigator.of(context).pop(false);
            },
            child: const Text('删除'),
          ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('保存'),
        ),
      ],
    ),
  );
  if (result != true) return;
  try {
    await ref
        .read(profileRepositoryProvider)
        .saveEmergencyContact(
          id: contact?.id,
          name: name.text.trim(),
          phone: phone.text.trim(),
          relationship: relationship.text.trim(),
          defaultNotify: notify,
        );
    ref.invalidate(emergencyContactsProvider);
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<bool> _confirm(
  BuildContext context, {
  required String title,
  required String message,
  bool danger = false,
}) async {
  return await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(danger ? '确认' : '确定'),
            ),
          ],
        ),
      ) ??
      false;
}

void _confirmLogout(BuildContext context, WidgetRef ref) {
  showDialog<void>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('退出登录'),
      content: const Text('退出后再次进入需要手机号验证码，设备会继续执行已配置的任务和提醒。'),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('取消'),
        ),
        FilledButton(
          onPressed: () async {
            await ref.read(authRepositoryProvider).logout();
            if (context.mounted) {
              Navigator.of(context).pop();
              context.go(loginPath);
            }
          },
          child: const Text('退出'),
        ),
      ],
    ),
  );
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
