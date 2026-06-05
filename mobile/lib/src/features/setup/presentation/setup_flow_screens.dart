import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/platform/native_date_picker.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/setup/application/setup_repository.dart';
import 'package:guardian_parent_app/src/features/setup/application/wifi_network_repository.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';

final setupDraftProvider = StateProvider<SetupDraft>((ref) {
  return const SetupDraft();
});

class SetupDraft {
  const SetupDraft({
    this.parentIdentity = '妈妈',
    this.parentName = '妈妈',
    this.familyRole = '管理员',
    this.deviceName = '客厅设备',
    this.room = '客厅书桌区',
    this.wifiName = '',
    this.wifiPassword = '',
    this.childName = '',
    this.childBirthday = '',
    this.childStage = '小学',
    this.childGrade = '一年级',
    this.emergencyName = '爸爸',
    this.emergencyPhone = '13800002026',
  });

  final String parentIdentity;
  final String parentName;
  final String familyRole;
  final String deviceName;
  final String room;
  final String wifiName;
  final String wifiPassword;
  final String childName;
  final String childBirthday;
  final String childStage;
  final String childGrade;
  final String emergencyName;
  final String emergencyPhone;

  SetupDraft copyWith({
    String? parentIdentity,
    String? parentName,
    String? familyRole,
    String? deviceName,
    String? room,
    String? wifiName,
    String? wifiPassword,
    String? childName,
    String? childBirthday,
    String? childStage,
    String? childGrade,
    String? emergencyName,
    String? emergencyPhone,
  }) {
    return SetupDraft(
      parentIdentity: parentIdentity ?? this.parentIdentity,
      parentName: parentName ?? this.parentName,
      familyRole: familyRole ?? this.familyRole,
      deviceName: deviceName ?? this.deviceName,
      room: room ?? this.room,
      wifiName: wifiName ?? this.wifiName,
      wifiPassword: wifiPassword ?? this.wifiPassword,
      childName: childName ?? this.childName,
      childBirthday: childBirthday ?? this.childBirthday,
      childStage: childStage ?? this.childStage,
      childGrade: childGrade ?? this.childGrade,
      emergencyName: emergencyName ?? this.emergencyName,
      emergencyPhone: emergencyPhone ?? this.emergencyPhone,
    );
  }
}

class ParentIdentitySetupScreen extends ConsumerWidget {
  const ParentIdentitySetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(setupDraftProvider);

    return _SetupScreenShell(
      step: 1,
      title: '确认家长身份',
      subtitle: '身份用于通知分发、家庭协作记录和权限判断。',
      leadingIcon: Icons.supervisor_account_outlined,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ChoiceGrid(
            label: '你在家庭中的身份',
            options: const ['妈妈', '爸爸', '祖辈', '保姆', '其他照护人'],
            selected: draft.parentIdentity,
            onSelect: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                parentIdentity: value,
                parentName: value,
              );
            },
          ),
          const SizedBox(height: 18),
          _SetupTextField(
            label: '家庭显示名',
            value: draft.parentName,
            icon: Icons.badge_outlined,
            onChanged: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                parentName: value,
              );
            },
          ),
          const SizedBox(height: 18),
          _ChoiceGrid(
            label: '家庭角色',
            options: const ['管理员', '监护人', '临时查看者'],
            selected: draft.familyRole,
            onSelect: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                familyRole: value,
              );
            },
          ),
        ],
      ),
      primaryLabel: '继续绑定设备',
      onPrimary: draft.parentName.trim().isEmpty
          ? null
          : () async {
              final saved = await _submitSetupStep(
                context,
                ref,
                () => ref
                    .read(setupRepositoryProvider)
                    .saveParentIdentity(
                      displayName: draft.parentName,
                      relationship: draft.parentIdentity,
                    ),
              );
              if (saved && context.mounted) {
                context.go(setupDevicePath);
              }
            },
    );
  }
}

class DeviceEntrySetupScreen extends ConsumerWidget {
  const DeviceEntrySetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(setupDraftProvider);

    return _SetupScreenShell(
      step: 2,
      title: '绑定看护设备',
      subtitle: '先确认设备和房间，摄像头绑定成功后再单独授权音视频采集。',
      leadingIcon: Icons.qr_code_scanner_outlined,
      body: Column(
        children: [
          _SetupStatusPanel(
            icon: Icons.sensors_outlined,
            title: '已发现附近设备',
            detail: '待绑定设备 · 等待加入家庭账户',
            tone: _SetupTone.blue,
          ),
          const SizedBox(height: 18),
          _SetupTextField(
            label: '设备名称',
            value: draft.deviceName,
            icon: Icons.videocam_outlined,
            onChanged: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                deviceName: value,
              );
            },
          ),
          const SizedBox(height: 12),
          _SetupTextField(
            label: '房间位置',
            value: draft.room,
            icon: Icons.meeting_room_outlined,
            onChanged: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                room: value,
              );
            },
          ),
          const SizedBox(height: 14),
          const _SetupNote(text: '当前先保存设备名称和位置，后续可继续补充扫码、蓝牙发现等绑定方式。'),
        ],
      ),
      primaryLabel: '配置 Wi-Fi',
      secondaryLabel: '重新扫描',
      onSecondary: () => _showSetupToast(context, '已重新扫描附近设备'),
      onPrimary: draft.deviceName.trim().isEmpty || draft.room.trim().isEmpty
          ? null
          : () async {
              final saved = await _submitSetupStep(
                context,
                ref,
                () => ref
                    .read(setupRepositoryProvider)
                    .saveDevice(
                      deviceName: draft.deviceName,
                      location: draft.room,
                    ),
              );
              if (saved && context.mounted) {
                context.go(setupWifiPath);
              }
            },
    );
  }
}

class WifiSetupScreen extends ConsumerStatefulWidget {
  const WifiSetupScreen({super.key});

  @override
  ConsumerState<WifiSetupScreen> createState() => _WifiSetupScreenState();
}

class _WifiSetupScreenState extends ConsumerState<WifiSetupScreen> {
  var _connecting = false;
  var _detectingWifi = true;
  String? _wifiNameErrorText;
  String? _wifiPasswordErrorText;
  WifiNetworkResult? _wifiResult;

  @override
  void initState() {
    super.initState();
    Future.microtask(_detectCurrentWifi);
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(setupDraftProvider);

    return _SetupScreenShell(
      step: 3,
      title: 'Wi-Fi 配网',
      subtitle: '配网只用于让设备接入家庭网络，不会自动开始录像或录音。',
      leadingIcon: Icons.wifi_outlined,
      body: Column(
        children: [
          _WifiDetectionPanel(
            detecting: _detectingWifi,
            result: _wifiResult,
            onRetry: _detectCurrentWifi,
          ),
          const SizedBox(height: 14),
          const _SetupNote(
            text: '请确认手机已连接要给设备使用的家庭网络。若设备提示仅支持 2.4GHz，请先切换到 2.4GHz Wi-Fi。',
          ),
          const SizedBox(height: 14),
          _SetupTextField(
            label: 'Wi-Fi 名称',
            value: draft.wifiName,
            icon: Icons.router_outlined,
            errorText: _wifiNameErrorText,
            onChanged: (value) {
              setState(() => _wifiNameErrorText = null);
              final latest = ref.read(setupDraftProvider);
              ref.read(setupDraftProvider.notifier).state = latest.copyWith(
                wifiName: value,
              );
            },
          ),
          const SizedBox(height: 12),
          _SetupTextField(
            label: 'Wi-Fi 密码',
            value: draft.wifiPassword,
            icon: Icons.lock_outline,
            obscureText: true,
            errorText: _wifiPasswordErrorText,
            onChanged: (value) {
              setState(() => _wifiPasswordErrorText = null);
              final latest = ref.read(setupDraftProvider);
              ref.read(setupDraftProvider.notifier).state = latest.copyWith(
                wifiPassword: value,
              );
            },
          ),
          const SizedBox(height: 16),
          AnimatedSwitcher(
            duration: AppMotion.duration(context, 180),
            child: _connecting
                ? const _SetupStatusPanel(
                    key: ValueKey('connecting'),
                    icon: Icons.sync_outlined,
                    title: '正在连接设备',
                    detail: '通常需要 10 至 20 秒，期间请保持设备通电。',
                    tone: _SetupTone.blue,
                  )
                : const _SetupStatusPanel(
                    key: ValueKey('ready'),
                    icon: Icons.privacy_tip_outlined,
                    title: '配网前隐私说明',
                    detail: '设备加入家庭后，音视频采集会在后续看护功能里单独提示。',
                    tone: _SetupTone.neutral,
                  ),
          ),
        ],
      ),
      primaryLabel: _connecting ? '正在绑定' : '开始绑定',
      loading: _connecting,
      onPrimary: _connecting ? null : () => _connect(draft),
    );
  }

  Future<void> _detectCurrentWifi() async {
    setState(() => _detectingWifi = true);
    final result = await ref.read(wifiNetworkRepositoryProvider).currentWifi();
    if (!mounted) return;

    final currentDraft = ref.read(setupDraftProvider);
    if (result.hasSsid && currentDraft.wifiName.trim().isEmpty) {
      ref.read(setupDraftProvider.notifier).state = currentDraft.copyWith(
        wifiName: result.ssid,
      );
    }

    setState(() {
      _wifiResult = result;
      _detectingWifi = false;
    });
  }

  Future<void> _connect(SetupDraft draft) async {
    if (draft.wifiName.trim().isEmpty) {
      setState(() => _wifiNameErrorText = '请输入 Wi-Fi 名称');
      return;
    }
    if (draft.wifiPassword.length < 6) {
      setState(() => _wifiPasswordErrorText = '请输入至少 6 位 Wi-Fi 密码');
      return;
    }

    FocusScope.of(context).unfocus();
    setState(() => _connecting = true);
    try {
      await ref
          .read(setupRepositoryProvider)
          .saveWifi(ssid: draft.wifiName, password: draft.wifiPassword);
      await Future<void>.delayed(const Duration(milliseconds: 420));
      if (!mounted) return;
      context.go(setupBindSuccessPath);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _connecting = false;
        _wifiPasswordErrorText = error.message;
      });
      _showSetupToast(context, error.message);
    }
  }
}

class _WifiDetectionPanel extends StatelessWidget {
  const _WifiDetectionPanel({
    required this.detecting,
    required this.result,
    required this.onRetry,
  });

  final bool detecting;
  final WifiNetworkResult? result;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final current = result;
    final title = detecting
        ? '正在识别当前 Wi-Fi'
        : current?.hasSsid == true
        ? '已识别当前 Wi-Fi'
        : '未自动识别 Wi-Fi';
    final detail = detecting
        ? '真机会尝试读取当前连接的家庭网络；模拟器通常无法返回真实 Wi-Fi。'
        : current?.hasSsid == true
        ? '${current!.ssid} · 请确认这是设备要加入的家庭网络'
        : current?.message ?? '你可以直接手动输入 Wi-Fi 名称。';
    final tone = detecting
        ? _SetupTone.blue
        : current?.hasSsid == true
        ? _SetupTone.green
        : _SetupTone.neutral;

    return _SetupStatusPanel(
      icon: detecting
          ? Icons.sync_outlined
          : current?.hasSsid == true
          ? Icons.wifi_outlined
          : Icons.edit_outlined,
      title: title,
      detail: detail,
      tone: tone,
      actionLabel: detecting ? null : '重新识别',
      onAction: detecting ? null : onRetry,
    );
  }
}

class BindSuccessSetupScreen extends ConsumerWidget {
  const BindSuccessSetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(setupDraftProvider);

    return _SetupScreenShell(
      step: 4,
      title: '设备绑定成功',
      subtitle: '${draft.deviceName} 已加入家庭账户，接下来创建孩子资料。',
      leadingIcon: Icons.check_circle_outline,
      body: Column(
        children: [
          _SuccessOrb(label: '已连接'),
          const SizedBox(height: 18),
          _SetupStatusPanel(
            icon: Icons.shield_outlined,
            title: '隐私灯测试通过',
            detail: '家长远程查看时，设备端会显示工作状态。',
            tone: _SetupTone.green,
          ),
          const SizedBox(height: 12),
          _SetupStatusPanel(
            icon: Icons.wifi_outlined,
            title: draft.wifiName,
            detail: '${draft.room} · 信号良好 · 在线',
            tone: _SetupTone.blue,
          ),
        ],
      ),
      primaryLabel: '创建孩子资料',
      onPrimary: () => context.go(setupChildProfilePath),
    );
  }
}

class ChildProfileSetupScreen extends ConsumerWidget {
  const ChildProfileSetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(setupDraftProvider);
    final recommended = _educationRecommendationFromBirthday(
      draft.childBirthday,
    );
    final gradeOptions = _gradesForStage(draft.childStage);
    final selectedGrade = gradeOptions.contains(draft.childGrade)
        ? draft.childGrade
        : gradeOptions.first;

    return _SetupScreenShell(
      step: 5,
      title: '孩子资料',
      subtitle: '资料只用于任务模板、提醒语气、小书包和紧急联系人策略。',
      leadingIcon: Icons.child_care_outlined,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _SetupTextField(
            label: '孩子称呼',
            value: draft.childName,
            icon: Icons.person_outline,
            onChanged: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                childName: value,
              );
            },
          ),
          const SizedBox(height: 12),
          _SetupTextField(
            label: '出生日期',
            value: draft.childBirthday,
            icon: Icons.cake_outlined,
            readOnly: true,
            suffixIcon: Icons.calendar_month_outlined,
            onTap: () async {
              FocusScope.of(context).unfocus();
              final picked = await _pickBirthday(context, draft.childBirthday);
              if (picked == null || !context.mounted) return;

              final value = _formatBirthday(picked);
              final latest = ref.read(setupDraftProvider);
              final next = _educationRecommendationFromBirthday(value);
              ref.read(setupDraftProvider.notifier).state = next == null
                  ? latest.copyWith(childBirthday: value)
                  : latest.copyWith(
                      childBirthday: value,
                      childStage: next.stage,
                      childGrade: next.grade,
                    );
            },
            onChanged: (_) {},
          ),
          if (recommended != null) ...[
            const SizedBox(height: 12),
            _SetupStatusPanel(
              icon: Icons.auto_awesome_outlined,
              title: '已根据生日推荐',
              detail: '${recommended.stage} · ${recommended.grade}，你也可以手动调整。',
              tone: _SetupTone.blue,
            ),
          ],
          const SizedBox(height: 18),
          _ChoiceGrid(
            label: '就读阶段',
            options: const ['幼儿园', '小学', '初中'],
            selected: draft.childStage,
            onSelect: (value) {
              final next = _educationRecommendationFromBirthday(
                draft.childBirthday,
              );
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                childStage: value,
                childGrade: next != null && next.stage == value
                    ? next.grade
                    : _defaultGradeForStage(value),
              );
            },
          ),
          const SizedBox(height: 18),
          _ChoiceGrid(
            label: '年级',
            options: gradeOptions,
            selected: selectedGrade,
            onSelect: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                childGrade: value,
              );
            },
          ),
          const SizedBox(height: 14),
          const _SetupNote(text: '系统会根据生日、当前学年和学段推荐任务模板，档案页不展示作息建议等中间参数。'),
        ],
      ),
      primaryLabel: '设置紧急联系人',
      onPrimary: draft.childName.trim().isEmpty
          ? null
          : () async {
              final saved = await _submitSetupStep(
                context,
                ref,
                () => ref
                    .read(setupRepositoryProvider)
                    .saveChild(
                      name: draft.childName,
                      nickname: draft.childName,
                      ageStage: '${draft.childStage} $selectedGrade',
                      birthday: draft.childBirthday,
                    ),
              );
              if (saved && context.mounted) {
                context.go(setupEmergencyContactsPath);
              }
            },
    );
  }

  static List<String> _gradesForStage(String stage) {
    return switch (stage) {
      '幼儿园' => const ['小班', '中班', '大班'],
      '初中' => const ['初一', '初二', '初三'],
      _ => const ['一年级', '二年级', '三年级', '四年级', '五年级', '六年级'],
    };
  }

  static String _defaultGradeForStage(String stage) {
    return switch (stage) {
      '幼儿园' => '大班',
      '初中' => '初一',
      _ => '一年级',
    };
  }

  static Future<DateTime?> _pickBirthday(
    BuildContext context,
    String currentValue,
  ) {
    final now = DateTime.now();
    final firstDate = DateTime(now.year - 18, now.month, now.day);
    final fallbackDate = DateTime(now.year - 7, now.month, now.day);
    final parsed = _parseBirthday(currentValue);
    final initialDate = _clampDate(parsed ?? fallbackDate, firstDate, now);

    return NativeDatePicker.pickDate(
      title: '选择出生日期',
      initialDate: initialDate,
      minDate: firstDate,
      maxDate: now,
    );
  }

  static DateTime _clampDate(
    DateTime value,
    DateTime firstDate,
    DateTime lastDate,
  ) {
    if (value.isBefore(firstDate)) return firstDate;
    if (value.isAfter(lastDate)) return lastDate;
    return value;
  }

  static String _formatBirthday(DateTime value) {
    final month = value.month.toString().padLeft(2, '0');
    final day = value.day.toString().padLeft(2, '0');
    return '${value.year}-$month-$day';
  }

  static _EducationRecommendation? _educationRecommendationFromBirthday(
    String value,
  ) {
    final birthday = _parseBirthday(value);
    if (birthday == null) return null;

    final now = DateTime.now();
    final schoolYearStart = DateTime(
      now.month >= 9 ? now.year : now.year - 1,
      9,
      1,
    );
    final age = _ageAt(birthday, schoolYearStart);
    if (age < 0) return null;

    if (age <= 5) {
      final kindergarten = _gradesForStage('幼儿园');
      final index = (age - 3).clamp(0, kindergarten.length - 1).toInt();
      return _EducationRecommendation(stage: '幼儿园', grade: kindergarten[index]);
    }

    if (age <= 11) {
      final primary = _gradesForStage('小学');
      return _EducationRecommendation(
        stage: '小学',
        grade: primary[(age - 6).clamp(0, primary.length - 1).toInt()],
      );
    }

    final junior = _gradesForStage('初中');
    return _EducationRecommendation(
      stage: '初中',
      grade: junior[(age - 12).clamp(0, junior.length - 1).toInt()],
    );
  }

  static DateTime? _parseBirthday(String value) {
    final trimmed = value.trim();
    final match = RegExp(r'^(\d{4})-(\d{1,2})-(\d{1,2})$').firstMatch(trimmed);
    if (match == null) return null;

    final year = int.tryParse(match.group(1)!);
    final month = int.tryParse(match.group(2)!);
    final day = int.tryParse(match.group(3)!);
    if (year == null || month == null || day == null) return null;

    final parsed = DateTime(year, month, day);
    if (parsed.year != year || parsed.month != month || parsed.day != day) {
      return null;
    }
    return parsed;
  }

  static int _ageAt(DateTime birthday, DateTime date) {
    var age = date.year - birthday.year;
    final birthdayThisYear = DateTime(date.year, birthday.month, birthday.day);
    if (birthdayThisYear.isAfter(date)) age -= 1;
    return age;
  }
}

class _EducationRecommendation {
  const _EducationRecommendation({required this.stage, required this.grade});

  final String stage;
  final String grade;
}

class EmergencyContactsSetupScreen extends ConsumerStatefulWidget {
  const EmergencyContactsSetupScreen({super.key});

  @override
  ConsumerState<EmergencyContactsSetupScreen> createState() =>
      _EmergencyContactsSetupScreenState();
}

class _EmergencyContactsSetupScreenState
    extends ConsumerState<EmergencyContactsSetupScreen> {
  String? _phoneError;
  var _saving = false;

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(setupDraftProvider);

    return _SetupScreenShell(
      step: 6,
      title: '紧急联系人',
      subtitle: '第一版用于告警兜底通知和家庭协作，不接真实短信邀请。',
      leadingIcon: Icons.contact_phone_outlined,
      body: Column(
        children: [
          _SetupTextField(
            label: '联系人姓名',
            value: draft.emergencyName,
            icon: Icons.person_add_alt_outlined,
            onChanged: (value) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                emergencyName: value,
              );
            },
          ),
          const SizedBox(height: 12),
          _SetupTextField(
            label: '手机号',
            value: draft.emergencyPhone,
            icon: Icons.phone_outlined,
            keyboardType: TextInputType.phone,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(11),
            ],
            errorText: _phoneError,
            onChanged: (value) {
              setState(() => _phoneError = null);
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                emergencyPhone: value,
              );
            },
          ),
          const SizedBox(height: 16),
          _SetupStatusPanel(
            icon: Icons.family_restroom_outlined,
            title: '家庭协作已准备',
            detail:
                '${draft.parentName} · ${draft.familyRole}，${draft.childName} 的任务和告警将进入家长端。',
            tone: _SetupTone.green,
          ),
        ],
      ),
      primaryLabel: _saving ? '正在进入首页' : '进入首页',
      loading: _saving,
      onPrimary: _saving ? null : () => _finish(draft),
    );
  }

  Future<void> _finish(SetupDraft draft) async {
    final validPhone = RegExp(r'^1[3-9]\d{9}$').hasMatch(draft.emergencyPhone);
    if (draft.emergencyName.trim().isEmpty || !validPhone) {
      setState(() => _phoneError = validPhone ? null : '请输入正确的 11 位手机号');
      return;
    }

    setState(() => _saving = true);
    try {
      await ref
          .read(setupRepositoryProvider)
          .saveContacts(
            name: draft.emergencyName,
            phone: draft.emergencyPhone,
            relationship: 'guardian',
          );
      final status = await ref.read(setupRepositoryProvider).complete();
      await Future<void>.delayed(const Duration(milliseconds: 320));
      if (!mounted) return;
      context.go(status.completed ? AppRoute.home.path : status.routePath);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() => _saving = false);
      _showSetupToast(context, error.message);
    }
  }
}

class _SetupScreenShell extends StatelessWidget {
  const _SetupScreenShell({
    required this.step,
    required this.title,
    required this.subtitle,
    required this.leadingIcon,
    required this.body,
    required this.primaryLabel,
    required this.onPrimary,
    this.secondaryLabel,
    this.onSecondary,
    this.loading = false,
  });

  final int step;
  final String title;
  final String subtitle;
  final IconData leadingIcon;
  final Widget body;
  final String primaryLabel;
  final VoidCallback? onPrimary;
  final String? secondaryLabel;
  final VoidCallback? onSecondary;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColors.appBackgroundWarm,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: Scaffold(
        backgroundColor: AppColors.appBackgroundWarm,
        body: Stack(
          children: [
            const Positioned.fill(child: _SetupBackground()),
            SafeArea(
              bottom: false,
              child: Column(
                children: [
                  _SetupTopBar(step: step),
                  Expanded(
                    child: SingleChildScrollView(
                      keyboardDismissBehavior:
                          ScrollViewKeyboardDismissBehavior.onDrag,
                      padding: EdgeInsets.fromLTRB(20, 12, 20, 18),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _SetupHero(
                            icon: leadingIcon,
                            title: title,
                            subtitle: subtitle,
                            step: step,
                          ),
                          const SizedBox(height: 16),
                          _SetupPanel(child: body),
                        ],
                      ),
                    ),
                  ),
                  _SetupActionDock(
                    bottomInset: bottomInset,
                    secondaryLabel: secondaryLabel,
                    onSecondary: onSecondary,
                    primaryLabel: primaryLabel,
                    onPrimary: onPrimary,
                    loading: loading,
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

class _SetupActionDock extends StatelessWidget {
  const _SetupActionDock({
    required this.bottomInset,
    required this.primaryLabel,
    required this.onPrimary,
    required this.loading,
    this.secondaryLabel,
    this.onSecondary,
  });

  final double bottomInset;
  final String primaryLabel;
  final VoidCallback? onPrimary;
  final bool loading;
  final String? secondaryLabel;
  final VoidCallback? onSecondary;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            AppColors.appBackgroundWarm.withValues(alpha: 0),
            AppColors.appBackgroundWarm.withValues(alpha: 0.92),
            AppColors.appBackgroundWarm,
          ],
          stops: const [0, 0.28, 1],
        ),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(20, 12, 20, bottomInset + 12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (secondaryLabel != null && onSecondary != null) ...[
              AppSecondaryButton(label: secondaryLabel!, onTap: onSecondary),
              const SizedBox(height: 10),
            ],
            Opacity(
              opacity: onPrimary == null ? 0.5 : 1,
              child: AppPrimaryButton(
                label: primaryLabel,
                loading: loading,
                trailing: loading
                    ? null
                    : const AppButtonGlyph(icon: Icons.arrow_forward),
                onTap: onPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SetupBackground extends StatelessWidget {
  const _SetupBackground();

  @override
  Widget build(BuildContext context) {
    return const DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            AppColors.appBackground,
            AppColors.appBackgroundMid,
            AppColors.appBackgroundWarm,
            AppColors.appBackgroundWarm,
          ],
          stops: [0, 0.45, 0.78, 1],
        ),
      ),
    );
  }
}

class _SetupTopBar extends StatelessWidget {
  const _SetupTopBar({required this.step});

  final int step;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
      child: Row(
        children: [
          Text(
            '首次设置',
            style: TextStyle(
              color: AppColors.ink.withValues(alpha: 0.88),
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
          const Spacer(),
          Text(
            '$step / 6',
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _SetupHero extends StatelessWidget {
  const _SetupHero({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.step,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final int step;

  @override
  Widget build(BuildContext context) {
    final progress = step / 6;

    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 17),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.brandDeep,
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: SizedBox(
                    width: 36,
                    height: 36,
                    child: Center(
                      child: Icon(icon, color: Colors.white, size: 19),
                    ),
                  ),
                ),
                const Spacer(),
                SizedBox(
                  width: 88,
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(AppRadii.full),
                    child: LinearProgressIndicator(
                      value: progress,
                      minHeight: 6,
                      backgroundColor: AppColors.brandWash,
                      valueColor: const AlwaysStoppedAnimation<Color>(
                        AppColors.brand,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            Text(
              title,
              style: const TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 28,
                fontWeight: FontWeight.w800,
                height: 1.12,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 9),
            Text(
              subtitle,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 14,
                fontWeight: FontWeight.w600,
                height: 1.6,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SetupPanel extends StatelessWidget {
  const _SetupPanel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.54),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.76)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 15),
        child: child,
      ),
    );
  }
}

class _ChoiceGrid extends StatelessWidget {
  const _ChoiceGrid({
    required this.label,
    required this.options,
    required this.selected,
    required this.onSelect,
  });

  final String label;
  final List<String> options;
  final String selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _FieldLabel(label),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final option in options)
              _ChoiceChipButton(
                label: option,
                selected: selected == option,
                onTap: () => onSelect(option),
              ),
          ],
        ),
      ],
    );
  }
}

class _ChoiceChipButton extends StatelessWidget {
  const _ChoiceChipButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: AnimatedContainer(
        duration: AppMotion.duration(context, 160),
        constraints: const BoxConstraints(
          minHeight: AppControls.minTouchTarget,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
        decoration: BoxDecoration(
          color: selected ? AppColors.brandWash : AppColors.surfaceSoft,
          borderRadius: BorderRadius.circular(AppRadii.control),
          border: Border.all(
            color: selected
                ? AppColors.brand.withValues(alpha: 0.18)
                : AppColors.borderSoft,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? AppColors.brandDeep : AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 13,
            fontWeight: FontWeight.w600,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _SetupTextField extends StatefulWidget {
  const _SetupTextField({
    required this.label,
    required this.value,
    required this.icon,
    required this.onChanged,
    this.keyboardType,
    this.inputFormatters,
    this.errorText,
    this.obscureText = false,
    this.readOnly = false,
    this.onTap,
    this.suffixIcon,
  });

  final String label;
  final String value;
  final IconData icon;
  final ValueChanged<String> onChanged;
  final TextInputType? keyboardType;
  final List<TextInputFormatter>? inputFormatters;
  final String? errorText;
  final bool obscureText;
  final bool readOnly;
  final VoidCallback? onTap;
  final IconData? suffixIcon;

  @override
  State<_SetupTextField> createState() => _SetupTextFieldState();
}

class _SetupTextFieldState extends State<_SetupTextField> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.value);
    _focusNode = FocusNode();
  }

  @override
  void didUpdateWidget(covariant _SetupTextField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.value != _controller.text && widget.value != oldWidget.value) {
      _controller.value = TextEditingValue(
        text: widget.value,
        selection: TextSelection.collapsed(offset: widget.value.length),
      );
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasError = widget.errorText != null;

    return ListenableBuilder(
      listenable: Listenable.merge([_controller, _focusNode]),
      builder: (context, _) {
        final focused = _focusNode.hasFocus;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _FieldLabel(widget.label),
            const SizedBox(height: 8),
            AnimatedContainer(
              duration: AppMotion.duration(context, 160),
              decoration: BoxDecoration(
                color: _controller.text.trim().isEmpty
                    ? AppColors.surfaceSoft
                    : AppColors.surfaceElevated,
                borderRadius: BorderRadius.circular(AppRadii.input),
                border: Border.all(
                  color: hasError
                      ? AppColors.danger
                      : focused
                      ? AppColors.focus
                      : AppColors.borderSoft,
                  width: focused ? 1.1 : 1,
                ),
              ),
              child: Row(
                children: [
                  const SizedBox(width: 13),
                  Icon(
                    widget.icon,
                    color: hasError
                        ? AppColors.danger
                        : focused
                        ? AppColors.brandDeep
                        : AppColors.subtle,
                    size: 18,
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      focusNode: _focusNode,
                      obscureText: widget.obscureText,
                      readOnly: widget.readOnly,
                      showCursor: widget.readOnly ? false : null,
                      keyboardType: widget.keyboardType,
                      inputFormatters: widget.inputFormatters,
                      onTap: widget.onTap,
                      onChanged: widget.onChanged,
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        height: 1.2,
                      ),
                      decoration: const InputDecoration(
                        border: InputBorder.none,
                        isCollapsed: true,
                        contentPadding: EdgeInsets.symmetric(vertical: 14),
                      ),
                    ),
                  ),
                  if (widget.suffixIcon != null) ...[
                    const SizedBox(width: 8),
                    Icon(
                      widget.suffixIcon,
                      color: focused ? AppColors.brandDeep : AppColors.subtle,
                      size: 18,
                    ),
                  ],
                  const SizedBox(width: 12),
                ],
              ),
            ),
            AnimatedSwitcher(
              duration: AppMotion.duration(context, 160),
              child: widget.errorText == null
                  ? const SizedBox.shrink()
                  : Padding(
                      key: ValueKey(widget.errorText),
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        widget.errorText!,
                        style: const TextStyle(
                          color: AppColors.danger,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
            ),
          ],
        );
      },
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 13,
        fontWeight: FontWeight.w600,
        letterSpacing: 0,
      ),
    );
  }
}

class _SetupStatusPanel extends StatelessWidget {
  const _SetupStatusPanel({
    required this.icon,
    required this.title,
    required this.detail,
    required this.tone,
    this.actionLabel,
    this.onAction,
    super.key,
  });

  final IconData icon;
  final String title;
  final String detail;
  final _SetupTone tone;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final colors = switch (tone) {
      _SetupTone.green => (
        background: const Color(0xFFE9F6EF),
        foreground: const Color(0xFF236044),
      ),
      _SetupTone.blue => (
        background: AppColors.brand.withValues(alpha: 0.1),
        foreground: AppColors.brand,
      ),
      _SetupTone.neutral => (
        background: AppColors.ink.withValues(alpha: 0.055),
        foreground: AppColors.ink,
      ),
    };

    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.background,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(13, 13, 13, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: colors.foreground, size: 19),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      color: colors.foreground,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      height: 1.2,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    detail,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.45,
                      letterSpacing: 0,
                    ),
                  ),
                ],
              ),
            ),
            if (actionLabel != null && onAction != null) ...[
              const SizedBox(width: 8),
              TextButton(onPressed: onAction, child: Text(actionLabel!)),
            ],
          ],
        ),
      ),
    );
  }
}

class _SetupNote extends StatelessWidget {
  const _SetupNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brand.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Padding(
        padding: const EdgeInsets.all(13),
        child: Text(
          text,
          style: const TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 12,
            fontWeight: FontWeight.w600,
            height: 1.55,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _SuccessOrb extends StatelessWidget {
  const _SuccessOrb({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFE9F6EF),
        borderRadius: BorderRadius.circular(24),
      ),
      child: SizedBox(
        height: 148,
        width: double.infinity,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.check_circle_outline,
                color: Color(0xFF236044),
                size: 48,
              ),
              const SizedBox(height: 10),
              Text(
                label,
                style: const TextStyle(
                  color: Color(0xFF236044),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
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

enum _SetupTone { neutral, blue, green }

Future<bool> _submitSetupStep(
  BuildContext context,
  WidgetRef ref,
  Future<SetupStatus> Function() action,
) async {
  try {
    await action();
    return true;
  } on SetupException catch (error) {
    if (context.mounted) {
      _showSetupToast(context, error.message);
    }
    return false;
  }
}

void _showSetupToast(BuildContext context, String message) {
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
