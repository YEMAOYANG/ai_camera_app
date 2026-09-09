import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/legacy.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/platform/contact_picker.dart';
import 'package:warm_sight/src/core/platform/native_date_picker.dart';
import 'package:warm_sight/src/core/storage/setup_store.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/auth/application/auth_repository.dart';
import 'package:warm_sight/src/features/auth/application/session_data_invalidation.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/setup/application/setup_draft.dart';
import 'package:warm_sight/src/features/setup/application/setup_repository.dart';
import 'package:warm_sight/src/features/setup/application/wifi_network_repository.dart';
import 'package:warm_sight/src/shared/domain/guardian_identity.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_segmented_control.dart';
import 'package:warm_sight/src/shared/widgets/app_time_picker_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import 'package:warm_sight/src/shared/widgets/guardian_identity_card_selector.dart';
import 'package:warm_sight/src/shared/widgets/guardian_identity_selector.dart';

const _setupTotalSteps = 2;

final _childGradeSavingProvider = StateProvider.autoDispose<bool>(
  (ref) => false,
);

String _setupCollaborationDetail(SetupDraft draft, String roleLabel) {
  final identityParts = [
    draft.parentName.trim(),
    roleLabel.trim(),
  ].where((part) => part.isNotEmpty).toList();
  final identity = identityParts.isEmpty ? '家庭成员' : identityParts.join(' · ');
  final childPrefix = draft.childName.trim().isEmpty
      ? ''
      : '${draft.childName.trim()} 的';
  return '$identity，$childPrefix任务确认会进入家长端。';
}

class ParentIdentitySetupScreen extends ConsumerWidget {
  const ParentIdentitySetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(setupDraftProvider);
    final identityOptions = ref.watch(guardianIdentityOptionsProvider);

    return identityOptions.when(
      data: (options) => _buildWithOptions(context, ref, draft, options),
      loading: () => const _SetupScreenShell(
        step: 1,
        title: '确认家长身份',
        subtitle: '选择家里怎么称呼你。',
        leadingIcon: Icons.supervisor_account_outlined,
        body: _SetupStatusPanel(
          icon: Icons.sync_outlined,
          title: '正在准备身份选项',
          detail: '稍等一下，很快就好。',
          tone: _SetupTone.blue,
        ),
        primaryLabel: '继续设置孩子身份',
        onPrimary: null,
      ),
      error: (error, _) => _SetupScreenShell(
        step: 1,
        title: '确认家长身份',
        subtitle: '选择家里怎么称呼你。',
        leadingIcon: Icons.supervisor_account_outlined,
        body: _SetupStatusPanel(
          icon: Icons.wifi_off_outlined,
          title: '身份选项暂时无法同步',
          detail: '请检查网络后重试。',
          tone: _SetupTone.neutral,
        ),
        primaryLabel: '重新加载',
        onPrimary: () => ref.invalidate(guardianIdentityOptionsProvider),
      ),
    );
  }

  Widget _buildWithOptions(
    BuildContext context,
    WidgetRef ref,
    SetupDraft draft,
    GuardianIdentityOptions options,
  ) {
    final rawIdentity = draft.parentIdentity.isNotEmpty
        ? draft.parentIdentity
        : draft.parentName;
    final resolvedIdentityKey = options.keyForValue(rawIdentity);
    final parentIdentityKey = resolvedIdentityKey.isNotEmpty
        ? resolvedIdentityKey
        : options.defaultKey;
    final parentIdentity = options.labelForStoredValue(
      parentIdentityKey.isNotEmpty ? parentIdentityKey : rawIdentity,
    );
    final identityGroup = options.groupForValue(
      parentIdentityKey.isNotEmpty ? parentIdentityKey : parentIdentity,
    );
    final identityGroupKey = identityGroup?.key ?? options.defaultGroupKey;
    final familyRoleKey = options.roleKeyFor(draft.familyRole);

    return _SetupScreenShell(
      step: 1,
      title: '确认家长身份',
      subtitle: '选择家里怎么称呼你。',
      leadingIcon: Icons.supervisor_account_outlined,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          GuardianIdentityGroupSegmentedControl(
            key: const ValueKey('guardianIdentityGroupSelect'),
            groups: options.identityGroups,
            selectedKey: identityGroupKey,
            onChanged: (groupKey) {
              final nextKey = options.defaultKeyForGroupKey(groupKey);
              final nextLabel = options.labelForStoredValue(nextKey);
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                parentIdentity: nextKey,
                parentName: nextLabel,
              );
            },
          ),
          const SizedBox(height: 12),
          GuardianIdentityCardSelector(
            key: const ValueKey('guardianDisplayNameCards'),
            keyPrefix: 'guardianDisplayNameCard',
            options: identityGroup?.labels ?? const [],
            value: parentIdentityKey,
            onChanged: (value) {
              final label = options.labelForStoredValue(value);
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                parentIdentity: value,
                parentName: label,
              );
            },
          ),
          const SizedBox(height: 14),
          _FamilyRoleSegmentedControl(
            label: '权限角色',
            options: options.familyRoles,
            selected: familyRoleKey,
            onSelect: (role) {
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                familyRole: role,
              );
            },
          ),
          const SizedBox(height: 14),
          _JoinFamilyCodeBanner(
            onTap: () => _showJoinFamilyCodeSheet(context, ref),
          ),
        ],
      ),
      primaryLabel: '继续设置孩子身份',
      onPrimary: parentIdentity.trim().isEmpty
          ? null
          : () async {
              final saved = await _submitSetupStep(
                context,
                ref,
                () => ref
                    .read(setupRepositoryProvider)
                    .saveParentIdentity(
                      displayName: parentIdentity,
                      relationship: parentIdentity,
                      relationshipKey: parentIdentityKey,
                      role: familyRoleKey,
                    ),
              );
              if (saved && context.mounted) {
                context.go(setupChildProfilePath);
              }
            },
    );
  }
}

Future<void> _showJoinFamilyCodeSheet(
  BuildContext context,
  WidgetRef ref,
) async {
  final accepted = await showAppBottomSheet<bool>(
    context: context,
    maxHeightFactor: 0.58,
    child: _JoinFamilyCodeSheet(
      onPreview: (code) =>
          ref.read(profileRepositoryProvider).previewJoinCode(code),
      onAccept: (code) =>
          ref.read(profileRepositoryProvider).acceptJoinCode(code),
    ),
  );
  if (accepted != true || !context.mounted) return;

  try {
    final status = await ref.read(setupRepositoryProvider).status();
    if (!context.mounted) return;
    syncSetupDraftFromStatus(ref, status);
    ref.invalidate(profileSummaryProvider);
    ref.invalidate(accountProfileProvider);
    ref.invalidate(familyMembersProvider);
    context.go(status.routePath);
  } on SetupException catch (error) {
    if (!context.mounted) return;
    showAppToast(context, error.message, tone: AppToastTone.danger);
  }
}

class _JoinFamilyCodeBanner extends StatelessWidget {
  const _JoinFamilyCodeBanner({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.brandWash.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(AppRadii.card),
          border: Border.all(color: AppColors.brand.withValues(alpha: 0.12)),
        ),
        child: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              Icon(Icons.tag_outlined, color: AppColors.brand, size: 18),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  '已有家庭号？输入后可直接加入家庭',
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    height: 1.35,
                    letterSpacing: 0,
                  ),
                ),
              ),
              Icon(Icons.chevron_right, color: AppColors.brand, size: 18),
            ],
          ),
        ),
      ),
    );
  }
}

class _JoinFamilyCodeSheet extends StatefulWidget {
  const _JoinFamilyCodeSheet({required this.onPreview, required this.onAccept});

  final Future<FamilyCodePreview> Function(String code) onPreview;
  final Future<void> Function(String code) onAccept;

  @override
  State<_JoinFamilyCodeSheet> createState() => _JoinFamilyCodeSheetState();
}

class _JoinFamilyCodeSheetState extends State<_JoinFamilyCodeSheet> {
  var _code = '';
  var _loading = false;
  String? _error;
  FamilyCodePreview? _preview;

  String get _normalizedCode {
    return _code.toUpperCase().replaceAll(RegExp(r'[^A-Z0-9]'), '');
  }

  Future<void> _previewCode() async {
    if (_loading) return;
    final code = _normalizedCode;
    if (code.length < 6) {
      setState(() => _error = '请输入完整家庭号');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _preview = null;
    });
    try {
      final preview = await widget.onPreview(code);
      if (!mounted) return;
      setState(() {
        _preview = preview;
        _loading = false;
      });
    } on ProfileException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '家庭号暂时无法验证，请稍后再试。';
      });
    }
  }

  Future<void> _acceptCode() async {
    if (_loading) return;
    final code = _normalizedCode;
    if (_preview == null) {
      await _previewCode();
      if (!mounted || _preview == null) return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.onAccept(code);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } on ProfileException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '暂时无法加入家庭，请稍后再试。';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final preview = _preview;
    return AppBottomSheetBody(
      title: '输入家庭号',
      subtitle: '加入后可在家庭成员中查看你的身份。',
      footer: AppSheetFooterActions(
        children: [
          AppSheetSecondaryButton(
            label: preview == null ? '预览家庭' : '重新预览',
            onTap: _loading
                ? null
                : () {
                    _previewCode();
                  },
          ),
          AppSheetPrimaryButton(
            label: '加入家庭',
            loading: _loading,
            onTap: _loading
                ? null
                : () {
                    _acceptCode();
                  },
          ),
        ],
      ),
      child: Column(
        children: [
          _SetupTextField(
            label: '家庭号',
            value: _code,
            icon: Icons.tag_outlined,
            hintText: '例如 HOME2026',
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[a-zA-Z0-9 -]')),
            ],
            onChanged: (value) {
              setState(() {
                _code = value;
                _preview = null;
                _error = null;
              });
            },
          ),
          if (preview != null) ...[
            const SizedBox(height: 14),
            DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.surfaceElevated,
                borderRadius: BorderRadius.circular(AppRadii.card),
                border: Border.all(color: AppColors.borderSoft),
              ),
              child: AppListRow(
                icon: Icons.home_work_outlined,
                title: preview.familyName,
                subtitle: '${preview.roleLabel} · ${preview.message}',
                tone: AppListRowTone.green,
              ),
            ),
          ],
          if (_error != null) ...[
            const SizedBox(height: 12),
            _SetupInlineError(_error!),
          ],
        ],
      ),
    );
  }
}

class _SetupInlineError extends StatelessWidget {
  const _SetupInlineError(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.dangerWash,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.danger.withValues(alpha: 0.14)),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Row(
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 17),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  color: AppColors.danger,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  height: 1.35,
                  letterSpacing: 0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FamilyRoleSegmentedControl extends StatelessWidget {
  const _FamilyRoleSegmentedControl({
    required this.label,
    required this.options,
    required this.selected,
    required this.onSelect,
  });

  final String label;
  final List<FamilyRoleOption> options;
  final String selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _FieldLabel(label),
        const SizedBox(height: 8),
        LayoutBuilder(
          builder: (context, _) {
            if (options.isEmpty) {
              return const _SetupStatusPanel(
                icon: Icons.manage_accounts_outlined,
                title: '暂未配置家庭角色',
                detail: '请稍后再试。',
                tone: _SetupTone.neutral,
              );
            }

            return AppSegmentedControl<String>(
              value: selected,
              semanticLabel: label,
              onChanged: onSelect,
              options: [
                for (final option in options)
                  AppSegmentOption<String>(
                    value: option.key,
                    label: option.label,
                    key: ValueKey('familyRoleSegment_${option.key}'),
                  ),
              ],
            );
          },
        ),
      ],
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
      // V1 幼儿园首次设置仅保留家长身份和孩子资料；旧配网页保留给后续设备设置入口复用，不显示首次设置步数。
      showSetupProgress: false,
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
      context.go(setupChildProfilePath);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        final deviceName = draft.deviceName.trim();
        final message = deviceName.isEmpty ? '设备已接入家庭网络' : '$deviceName已接入家庭网络';
        _showSetupToast(context, message);
      });
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
        ? '正在读取当前连接的家庭网络，也可以稍后手动输入。'
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

class ChildProfileEditorValue {
  const ChildProfileEditorValue({
    required this.name,
    required this.birthday,
    required this.sleepTime,
    required this.gender,
    required this.stage,
    required this.grade,
    this.schoolName = '',
    this.interestsText = '',
  });

  final String name;
  final String birthday;
  final String sleepTime;
  final String gender;
  final String stage;
  final String grade;
  final String schoolName;
  final String interestsText;

  String get normalizedStage {
    final trimmed = stage.trim();
    return trimmed.isEmpty ? '幼儿园' : trimmed;
  }

  String get normalizedGrade {
    final options = ChildProfileSetupScreen._gradesForStage(normalizedStage);
    final trimmed = grade.trim();
    return options.contains(trimmed) ? trimmed : '';
  }

  String get normalizedGender {
    final trimmed = gender.trim();
    return {'male', 'female', 'unspecified'}.contains(trimmed)
        ? trimmed
        : 'unspecified';
  }

  String get normalizedSleepTime {
    final parsed = ChildProfileSetupScreen._parseSleepTime(sleepTime);
    return parsed == null
        ? '21:00'
        : ChildProfileSetupScreen._formatSleepTime(parsed);
  }

  List<String> get interests {
    return interestsText
        .split(RegExp('[、,，]'))
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList();
  }

  ChildProfileEditorValue copyWith({
    String? name,
    String? birthday,
    String? sleepTime,
    String? gender,
    String? stage,
    String? grade,
    String? schoolName,
    String? interestsText,
  }) {
    return ChildProfileEditorValue(
      name: name ?? this.name,
      birthday: birthday ?? this.birthday,
      sleepTime: sleepTime ?? this.sleepTime,
      gender: gender ?? this.gender,
      stage: stage ?? this.stage,
      grade: grade ?? this.grade,
      schoolName: schoolName ?? this.schoolName,
      interestsText: interestsText ?? this.interestsText,
    );
  }
}

class ChildProfileEditorPanel extends StatelessWidget {
  const ChildProfileEditorPanel({
    super.key,
    required this.value,
    required this.onChanged,
    this.includeExtendedFields = false,
    this.includeGender = true,
    this.includeBirthday = true,
    this.includeSleepTime = true,
    this.stageOptions = const ['幼儿园', '小学', '初中'],
    this.showStageSelector,
    this.recommendEducationFromBirthday = true,
    this.noteText = '性别可以不设置，不会影响任务类型；生日和学段只用于提醒节奏与模板推荐。',
  });

  final ChildProfileEditorValue value;
  final ValueChanged<ChildProfileEditorValue> onChanged;
  final bool includeExtendedFields;
  final bool includeGender;
  final bool includeBirthday;
  final bool includeSleepTime;
  final List<String> stageOptions;
  final bool? showStageSelector;
  final bool recommendEducationFromBirthday;
  final String? noteText;

  @override
  Widget build(BuildContext context) {
    final availableStages = stageOptions.isEmpty ? const ['幼儿园'] : stageOptions;
    final shouldShowStageSelector =
        showStageSelector ?? availableStages.length > 1;
    final recommended = recommendEducationFromBirthday
        ? ChildProfileSetupScreen._educationRecommendationFromBirthday(
            value.birthday,
          )
        : null;
    final stage = availableStages.contains(value.normalizedStage)
        ? value.normalizedStage
        : availableStages.first;
    final gradeOptions = ChildProfileSetupScreen._gradesForStage(stage);
    final selectedGrade = gradeOptions.contains(value.grade.trim())
        ? value.grade.trim()
        : '';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SetupTextField(
          label: '孩子称呼',
          value: value.name,
          icon: Icons.person_outline,
          hintText: '例如：小晨',
          onChanged: (text) => onChanged(value.copyWith(name: text)),
        ),
        if (includeGender) ...[
          const SizedBox(height: 16),
          _ChildGenderSelector(
            selected: value.normalizedGender,
            onSelect: (gender) => onChanged(value.copyWith(gender: gender)),
          ),
        ],
        if (includeBirthday) ...[
          SizedBox(height: includeGender ? 12 : 16),
          _SetupTextField(
            label: '出生日期',
            value: value.birthday,
            icon: Icons.cake_outlined,
            hintText: '选择生日',
            readOnly: true,
            suffixIcon: Icons.calendar_month_outlined,
            onTap: () async {
              FocusScope.of(context).unfocus();
              final picked = await ChildProfileSetupScreen._pickBirthday(
                context,
                value.birthday,
              );
              if (picked == null || !context.mounted) return;

              final birthday = ChildProfileSetupScreen._formatBirthday(picked);
              final next = recommendEducationFromBirthday
                  ? ChildProfileSetupScreen._educationRecommendationFromBirthday(
                      birthday,
                    )
                  : null;
              final nextStage =
                  next != null && availableStages.contains(next.stage)
                  ? next.stage
                  : stage;
              onChanged(
                next == null
                    ? value.copyWith(birthday: birthday)
                    : value.copyWith(
                        birthday: birthday,
                        stage: nextStage,
                        grade: nextStage == next.stage ? next.grade : '',
                      ),
              );
            },
            onChanged: (_) {},
          ),
        ],
        if (includeSleepTime) ...[
          const SizedBox(height: 16),
          _SetupTextField(
            label: '入睡时间',
            value: value.normalizedSleepTime,
            icon: Icons.nights_stay_outlined,
            hintText: '选择孩子通常入睡时间',
            readOnly: true,
            suffixIcon: Icons.schedule_outlined,
            onTap: () async {
              FocusScope.of(context).unfocus();
              final picked = await ChildProfileSetupScreen._pickSleepTime(
                context,
                value.normalizedSleepTime,
              );
              if (picked == null || !context.mounted) return;
              onChanged(value.copyWith(sleepTime: picked));
            },
            onChanged: (_) {},
          ),
        ],
        if (recommended != null &&
            availableStages.contains(recommended.stage)) ...[
          const SizedBox(height: 12),
          _SetupStatusPanel(
            icon: Icons.auto_awesome_outlined,
            title: shouldShowStageSelector ? '已根据生日推荐' : '已推荐班级',
            detail: shouldShowStageSelector
                ? '${recommended.stage} · ${recommended.grade}，你也可以手动调整。'
                : '推荐 ${recommended.grade}，可手动调整。',
            tone: _SetupTone.blue,
          ),
        ],
        // V1 幼儿园版本隐藏学段选择，底层 stage/grade 数据结构保留给后续全年龄段版本复用。
        if (shouldShowStageSelector) ...[
          const SizedBox(height: 18),
          _ChoiceGrid(
            label: '就读阶段',
            options: availableStages,
            selected: stage,
            onSelect: (stage) {
              final recommendation = recommendEducationFromBirthday
                  ? ChildProfileSetupScreen._educationRecommendationFromBirthday(
                      value.birthday,
                    )
                  : null;
              onChanged(
                value.copyWith(
                  stage: stage,
                  grade: recommendation != null && recommendation.stage == stage
                      ? recommendation.grade
                      : ChildProfileSetupScreen._defaultGradeForStage(stage),
                ),
              );
            },
          ),
        ],
        const SizedBox(height: 18),
        _ChoiceGrid(
          label: shouldShowStageSelector ? '年级' : '幼儿园班级',
          options: gradeOptions,
          selected: selectedGrade,
          onSelect: (grade) =>
              onChanged(value.copyWith(stage: stage, grade: grade)),
        ),
        if (includeExtendedFields) ...[
          const SizedBox(height: 18),
          _SetupTextField(
            label: '学校',
            value: value.schoolName,
            icon: Icons.school_outlined,
            hintText: '可不填',
            onChanged: (text) => onChanged(value.copyWith(schoolName: text)),
          ),
          const SizedBox(height: 16),
          _SetupTextField(
            label: '兴趣',
            value: value.interestsText,
            icon: Icons.interests_outlined,
            hintText: '例如：绘本、拼搭、篮球',
            onChanged: (text) => onChanged(value.copyWith(interestsText: text)),
          ),
        ],
        if (noteText != null) ...[
          const SizedBox(height: 14),
          _SetupNote(text: noteText!),
        ],
      ],
    );
  }
}

class ChildProfileSetupScreen extends ConsumerWidget {
  const ChildProfileSetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final draft = ref.watch(setupDraftProvider);
    final saving = ref.watch(_childGradeSavingProvider);
    final setupStore = ref.watch(setupStoreProvider);
    final draftSelected =
        ChildGradeOption.fromCode(draft.childGradeCode) ??
        ChildGradeOption.fromLegacy(
          educationStage: draft.childStage,
          grade: draft.childGrade,
        );
    final selected =
        draftSelected ??
        (draft.childStage.trim().isEmpty
            ? ChildGradeOption.fromCode(setupStore.pendingGradeCode)
            : null);
    final schoolYearStartYear =
        draft.childSchoolYearStartYear ??
        setupStore.pendingSchoolYearStartYear ??
        gradeSchoolYearStartYear();
    final storedNickname = draft.childNickname.trim();
    final storedName = draft.childName.trim();
    final pendingNickname = setupStore.pendingChildNickname.trim();
    final nickname = draft.childNicknameEdited
        ? draft.childNickname
        : pendingNickname.isNotEmpty
        ? pendingNickname
        : storedNickname.isNotEmpty
        ? storedNickname
        : storedName.isNotEmpty && storedName != '小朋友'
        ? storedName
        : '';
    final activeStageCode =
        selected?.stageCode ??
        (draft.childStage.trim() == '幼儿园' ? 'kindergarten' : 'primary');

    return _LearningIdentitySetupShell(
      body: AbsorbPointer(
        absorbing: saving,
        child: _LearningIdentityTimeline(
          nickname: nickname,
          schoolYearStartYear: schoolYearStartYear,
          activeStageCode: activeStageCode,
          selected: selected,
          enabled: !saving,
          onNicknameChanged: (value) {
            final latest = ref.read(setupDraftProvider);
            ref.read(setupDraftProvider.notifier).state = latest.copyWith(
              childNickname: value,
              childNicknameEdited: true,
            );
            unawaited(setupStore.savePendingChildNickname(value));
          },
          onStageChanged: (stageCode) {
            if (stageCode == activeStageCode) return;
            final latest = ref.read(setupDraftProvider);
            ref.read(setupDraftProvider.notifier).state = latest.copyWith(
              childStage: stageCode == 'primary' ? '小学' : '幼儿园',
              childGrade: '',
              childGradeCode: '',
              childSchoolYearStartYear: schoolYearStartYear,
            );
            unawaited(setupStore.clearPendingGrade());
          },
          onGradeSelected: (option) {
            final latest = ref.read(setupDraftProvider);
            ref.read(setupDraftProvider.notifier).state = latest.copyWith(
              childStage: option.stageLabel,
              childGrade: option.gradeLabel,
              childGradeCode: option.code,
              childSchoolYearStartYear: schoolYearStartYear,
            );
            unawaited(
              setupStore.savePendingGrade(
                gradeCode: option.code,
                schoolYearStartYear: schoolYearStartYear,
              ),
            );
          },
        ),
      ),
      onBack: saving ? null : () => context.go(setupParentIdentityPath),
      primaryLabel: saving ? '正在保存' : '完成设置',
      loading: saving,
      onPrimary: nickname.trim().isEmpty || selected == null || saving
          ? null
          : () async {
              ref.read(_childGradeSavingProvider.notifier).state = true;
              try {
                final canonicalName = draft.childName.trim();
                final saved = await _submitSetupStep(
                  context,
                  ref,
                  () => ref
                      .read(setupRepositoryProvider)
                      .saveChild(
                        name: canonicalName.isEmpty || canonicalName == '小朋友'
                            ? nickname.trim()
                            : canonicalName,
                        nickname: nickname.trim(),
                        gradeCode: selected.code,
                        schoolYearStartYear: schoolYearStartYear,
                      ),
                );
                if (saved && context.mounted) {
                  ref.invalidate(profileSummaryProvider);
                  ref.invalidate(currentChildProvider);
                  context.go(AppRoute.home.path);
                }
              } finally {
                if (context.mounted) {
                  ref.read(_childGradeSavingProvider.notifier).state = false;
                }
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

  static Future<String?> _pickSleepTime(
    BuildContext context,
    String currentValue,
  ) {
    final initialTime =
        _parseSleepTime(currentValue) ?? const TimeOfDay(hour: 21, minute: 0);
    return showAppTimePickerSheet(
      context: context,
      title: '选择入睡时间',
      subtitle: '用于睡前聊天边界和看护提醒节奏。',
      initialValue: _formatSleepTime(initialTime),
      invalidMessage: '请选择有效的入睡时间',
    );
  }

  static TimeOfDay? _parseSleepTime(String value) {
    final parts = value.trim().split(':');
    if (parts.length != 2) return null;
    final hour = int.tryParse(parts[0]);
    final minute = int.tryParse(parts[1]);
    if (hour == null || minute == null || hour > 23 || minute > 59) {
      return null;
    }
    return TimeOfDay(hour: hour, minute: minute);
  }

  static String _formatSleepTime(TimeOfDay value) {
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  static int _ageAt(DateTime birthday, DateTime date) {
    var age = date.year - birthday.year;
    final birthdayThisYear = DateTime(date.year, birthday.month, birthday.day);
    if (birthdayThisYear.isAfter(date)) age -= 1;
    return age;
  }
}

class _GradeSelectionPanel extends StatelessWidget {
  const _GradeSelectionPanel({
    required this.stageCode,
    required this.selected,
    required this.enabled,
    required this.onSelect,
  });

  final String stageCode;
  final ChildGradeOption? selected;
  final bool enabled;
  final ValueChanged<ChildGradeOption> onSelect;

  @override
  Widget build(BuildContext context) {
    final options = stageCode == 'primary'
        ? ChildGradeOption.primary
        : ChildGradeOption.kindergarten;
    final stageLabel = stageCode == 'primary' ? '小学' : '幼儿园';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '选择$stageLabel年级',
          style: const TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 16,
            fontWeight: FontWeight.w800,
            height: 1.25,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 16),
        _GradeScale(
          options: options,
          selectedCode: selected?.code ?? '',
          enabled: enabled,
          onSelect: onSelect,
        ),
        const SizedBox(height: 18),
        _SelectedGradeSummary(selected: selected),
      ],
    );
  }
}

class _GradeScale extends StatelessWidget {
  const _GradeScale({
    required this.options,
    required this.selectedCode,
    required this.enabled,
    required this.onSelect,
  });

  final List<ChildGradeOption> options;
  final String selectedCode;
  final bool enabled;
  final ValueChanged<ChildGradeOption> onSelect;

  @override
  Widget build(BuildContext context) {
    final isPrimary = options.length == ChildGradeOption.primary.length;
    final selectedIndex = options.indexWhere(
      (option) => option.code == selectedCode,
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (isPrimary && constraints.maxWidth < 264) {
          return _CompactPrimaryGradeGrid(
            options: options,
            selectedCode: selectedCode,
            enabled: enabled,
            onSelect: onSelect,
            captionStyle: _captionStyle,
          );
        }

        const circleSize = 44.0;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Stack(
              alignment: Alignment.topCenter,
              children: [
                const Positioned(
                  left: circleSize / 2,
                  right: circleSize / 2,
                  top: circleSize / 2 - 1,
                  height: 2,
                  child: DecoratedBox(
                    decoration: BoxDecoration(color: AppColors.border),
                  ),
                ),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    for (var index = 0; index < options.length; index++)
                      _GradeOptionButton(
                        size: circleSize,
                        circleLabel: isPrimary
                            ? '${index + 1}'
                            : options[index].gradeLabel.replaceAll('班', ''),
                        option: options[index],
                        selected: selectedCode == options[index].code,
                        enabled: enabled,
                        onTap: () => onSelect(options[index]),
                      ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 11),
            if (isPrimary)
              Row(
                children: [
                  Text(
                    options.first.displayLabel,
                    style: _captionStyle(selectedCode == options.first.code),
                  ),
                  const Spacer(),
                  if (selectedIndex > 0 && selectedIndex < options.length - 1)
                    Text(
                      options[selectedIndex].displayLabel,
                      style: _captionStyle(true),
                    ),
                  const Spacer(),
                  Text(
                    options.last.displayLabel,
                    style: _captionStyle(selectedCode == options.last.code),
                  ),
                ],
              )
            else
              Row(
                children: [
                  for (var index = 0; index < options.length; index++) ...[
                    if (index > 0) const Spacer(),
                    Text(
                      options[index].displayLabel,
                      style: _captionStyle(selectedCode == options[index].code),
                    ),
                  ],
                ],
              ),
          ],
        );
      },
    );
  }

  TextStyle _captionStyle(bool selected) {
    return TextStyle(
      color: selected ? AppColors.brandDeep : AppColors.muted,
      fontFamily: AppTypography.systemFont,
      fontSize: 12,
      fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
      height: 1.2,
      letterSpacing: 0,
    );
  }
}

class _CompactPrimaryGradeGrid extends StatelessWidget {
  const _CompactPrimaryGradeGrid({
    required this.options,
    required this.selectedCode,
    required this.enabled,
    required this.onSelect,
    required this.captionStyle,
  });

  final List<ChildGradeOption> options;
  final String selectedCode;
  final bool enabled;
  final ValueChanged<ChildGradeOption> onSelect;
  final TextStyle Function(bool selected) captionStyle;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var rowStart = 0; rowStart < options.length; rowStart += 3) ...[
          if (rowStart > 0) const SizedBox(height: 14),
          Row(
            children: [
              for (var index = rowStart; index < rowStart + 3; index++) ...[
                if (index > rowStart) const SizedBox(width: 6),
                Expanded(
                  child: Column(
                    children: [
                      _GradeOptionButton(
                        size: 44,
                        circleLabel: '${index + 1}',
                        option: options[index],
                        selected: selectedCode == options[index].code,
                        enabled: enabled,
                        onTap: () => onSelect(options[index]),
                      ),
                      const SizedBox(height: 7),
                      Text(
                        options[index].displayLabel,
                        maxLines: 1,
                        overflow: TextOverflow.fade,
                        softWrap: false,
                        style: captionStyle(
                          selectedCode == options[index].code,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ],
      ],
    );
  }
}

class _GradeOptionButton extends StatelessWidget {
  const _GradeOptionButton({
    required this.size,
    required this.circleLabel,
    required this.option,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final double size;
  final String circleLabel;
  final ChildGradeOption option;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      enabled: enabled,
      label: '${option.stageLabel}，${option.displayLabel}',
      child: GestureDetector(
        key: ValueKey('gradeOption_${option.code}'),
        behavior: HitTestBehavior.opaque,
        onTap: enabled ? onTap : null,
        child: AnimatedContainer(
          duration: AppMotion.duration(context, 180),
          curve: Curves.easeOutCubic,
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: selected ? AppColors.brandDeep : AppColors.surfaceElevated,
            border: Border.all(
              color: selected ? AppColors.brandDeep : AppColors.border,
              width: selected ? 1.5 : 1,
            ),
            boxShadow: selected
                ? [
                    BoxShadow(
                      color: AppColors.brand.withValues(alpha: 0.16),
                      blurRadius: 12,
                      offset: const Offset(0, 5),
                    ),
                  ]
                : null,
          ),
          child: Center(
            child: Text(
              circleLabel,
              style: TextStyle(
                color: selected ? Colors.white : AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 16,
                fontWeight: FontWeight.w800,
                height: 1,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SelectedGradeSummary extends StatelessWidget {
  const _SelectedGradeSummary({required this.selected});

  final ChildGradeOption? selected;

  @override
  Widget build(BuildContext context) {
    final hasSelection = selected != null;
    return AnimatedContainer(
      key: const ValueKey('selectedGradeSummary'),
      duration: AppMotion.duration(context, 180),
      width: double.infinity,
      constraints: const BoxConstraints(minHeight: 78),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: hasSelection
            ? AppColors.brandWash.withValues(alpha: 0.78)
            : AppColors.surfaceSoft,
        borderRadius: BorderRadius.circular(AppRadii.cardMedium),
        border: Border.all(
          color: hasSelection
              ? AppColors.brand.withValues(alpha: 0.12)
              : AppColors.borderSoft,
        ),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            hasSelection ? '当前选择' : '还未选择年级',
            style: const TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              height: 1.2,
              letterSpacing: 0,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            selected?.displayLabel ?? '请在上方选择',
            style: TextStyle(
              color: hasSelection ? AppColors.brandDeep : AppColors.subtle,
              fontFamily: AppTypography.systemFont,
              fontSize: hasSelection ? 26 : 16,
              fontWeight: FontWeight.w800,
              height: 1.1,
              letterSpacing: 0,
            ),
          ),
        ],
      ),
    );
  }
}

class _LearningIdentitySetupShell extends ConsumerWidget {
  const _LearningIdentitySetupShell({
    required this.body,
    required this.primaryLabel,
    required this.onPrimary,
    required this.onBack,
    required this.loading,
  });

  final Widget body;
  final String primaryLabel;
  final VoidCallback? onPrimary;
  final VoidCallback? onBack;
  final bool loading;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.appBackgroundWarm,
        body: Stack(
          children: [
            const Positioned.fill(child: _SetupBackground()),
            SafeArea(
              bottom: false,
              child: Column(
                children: [
                  _SetupTopBar(
                    step: 2,
                    onBack: loading ? null : onBack,
                    onLogout: () => _confirmSetupLogout(context, ref),
                  ),
                  Expanded(
                    child: SingleChildScrollView(
                      keyboardDismissBehavior:
                          ScrollViewKeyboardDismissBehavior.onDrag,
                      padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '设置孩子的学习身份',
                            style: TextStyle(
                              color: AppColors.ink,
                              fontFamily: AppTypography.systemFont,
                              fontSize: 28,
                              fontWeight: FontWeight.w800,
                              height: 1.12,
                              letterSpacing: 0,
                            ),
                          ),
                          const SizedBox(height: 8),
                          const Text(
                            '用于称呼孩子并匹配适龄内容',
                            style: TextStyle(
                              color: AppColors.muted,
                              fontFamily: AppTypography.systemFont,
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              height: 1.5,
                              letterSpacing: 0,
                            ),
                          ),
                          const SizedBox(height: 26),
                          body,
                          const SizedBox(height: 24),
                          const _LearningIdentityNote(),
                        ],
                      ),
                    ),
                  ),
                  _SetupActionDock(
                    bottomInset: bottomInset,
                    primaryLabel: primaryLabel,
                    onPrimary: onPrimary,
                    loading: loading,
                    showTrailing: false,
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

class _LearningIdentityTimeline extends StatelessWidget {
  const _LearningIdentityTimeline({
    required this.nickname,
    required this.schoolYearStartYear,
    required this.activeStageCode,
    required this.selected,
    required this.enabled,
    required this.onNicknameChanged,
    required this.onStageChanged,
    required this.onGradeSelected,
  });

  final String nickname;
  final int schoolYearStartYear;
  final String activeStageCode;
  final ChildGradeOption? selected;
  final bool enabled;
  final ValueChanged<String> onNicknameChanged;
  final ValueChanged<String> onStageChanged;
  final ValueChanged<ChildGradeOption> onGradeSelected;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        const Positioned(
          left: 21,
          top: 42,
          bottom: 8,
          width: 2,
          child: DecoratedBox(
            decoration: BoxDecoration(color: AppColors.border),
          ),
        ),
        Column(
          children: [
            _LearningIdentityStep(
              number: '01',
              child: Padding(
                padding: const EdgeInsets.only(bottom: 28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const _LearningIdentitySectionTitle('孩子称呼'),
                    const SizedBox(height: 14),
                    _LearningIdentityNameField(
                      value: nickname,
                      enabled: enabled,
                      onChanged: onNicknameChanged,
                    ),
                    const SizedBox(height: 9),
                    const Text(
                      '摄像头老师会这样称呼孩子',
                      style: TextStyle(
                        color: AppColors.muted,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                        height: 1.35,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            _LearningIdentityStep(
              number: '02',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _LearningIdentitySectionTitle(
                    '$schoolYearStartYear 年 9 月开学后',
                  ),
                  const SizedBox(height: 15),
                  _LearningStageControl(
                    selected: activeStageCode,
                    enabled: enabled,
                    onChanged: onStageChanged,
                  ),
                  const SizedBox(height: 24),
                  _GradeSelectionPanel(
                    stageCode: activeStageCode,
                    selected: selected?.stageCode == activeStageCode
                        ? selected
                        : null,
                    enabled: enabled,
                    onSelect: onGradeSelected,
                  ),
                  const SizedBox(height: 8),
                ],
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _LearningIdentityStep extends StatelessWidget {
  const _LearningIdentityStep({required this.number, required this.child});

  final String number;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 48,
          child: DecoratedBox(
            decoration: const BoxDecoration(
              color: AppColors.brandWash,
              shape: BoxShape.circle,
            ),
            child: SizedBox(
              width: 44,
              height: 44,
              child: Center(
                child: Text(
                  number,
                  style: const TextStyle(
                    color: AppColors.brandDeep,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    height: 1,
                    letterSpacing: 0,
                  ),
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(child: child),
      ],
    );
  }
}

class _LearningIdentitySectionTitle extends StatelessWidget {
  const _LearningIdentitySectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: AppColors.ink,
        fontFamily: AppTypography.systemFont,
        fontSize: 17,
        fontWeight: FontWeight.w800,
        height: 1.25,
        letterSpacing: 0,
      ),
    );
  }
}

class _LearningIdentityNameField extends StatefulWidget {
  const _LearningIdentityNameField({
    required this.value,
    required this.enabled,
    required this.onChanged,
  });

  final String value;
  final bool enabled;
  final ValueChanged<String> onChanged;

  @override
  State<_LearningIdentityNameField> createState() =>
      _LearningIdentityNameFieldState();
}

class _LearningIdentityNameFieldState
    extends State<_LearningIdentityNameField> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.value);
    _focusNode = FocusNode();
  }

  @override
  void didUpdateWidget(covariant _LearningIdentityNameField oldWidget) {
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

  void _clear() {
    _controller.clear();
    widget.onChanged('');
    _focusNode.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([_controller, _focusNode]),
      builder: (context, _) {
        final focused = _focusNode.hasFocus;
        return AnimatedContainer(
          key: const ValueKey('setupField_孩子称呼'),
          duration: AppMotion.duration(context, 160),
          constraints: const BoxConstraints(minHeight: 54),
          decoration: BoxDecoration(
            color: _controller.text.trim().isEmpty
                ? AppColors.surfaceSoft
                : AppColors.surfaceElevated,
            borderRadius: BorderRadius.circular(AppRadii.input),
            border: Border.all(
              color: focused ? AppColors.focus : AppColors.border,
              width: focused ? 1.2 : 1,
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  key: const ValueKey('setupInput_孩子称呼'),
                  controller: _controller,
                  focusNode: _focusNode,
                  enabled: widget.enabled,
                  textInputAction: TextInputAction.done,
                  inputFormatters: [LengthLimitingTextInputFormatter(12)],
                  onChanged: widget.onChanged,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    height: 1.2,
                    letterSpacing: 0,
                  ),
                  decoration: const InputDecoration(
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                    hintText: '例如：乐乐',
                    hintStyle: TextStyle(
                      color: AppColors.subtle,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      height: 1.2,
                      letterSpacing: 0,
                    ),
                    isDense: true,
                    contentPadding: EdgeInsets.fromLTRB(16, 17, 10, 17),
                  ),
                ),
              ),
              if (_controller.text.isNotEmpty)
                IconButton(
                  tooltip: '清空孩子称呼',
                  onPressed: widget.enabled ? _clear : null,
                  icon: const Icon(Icons.cancel, size: 20),
                  color: AppColors.subtle,
                )
              else
                const SizedBox(width: 12),
            ],
          ),
        );
      },
    );
  }
}

class _LearningStageControl extends StatelessWidget {
  const _LearningStageControl({
    required this.selected,
    required this.enabled,
    required this.onChanged,
  });

  final String selected;
  final bool enabled;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: AppColors.surfaceStrong,
        borderRadius: BorderRadius.circular(AppRadii.input),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Row(
        children: [
          _LearningStageOption(
            code: 'kindergarten',
            label: '幼儿园',
            selected: selected == 'kindergarten',
            enabled: enabled,
            onTap: () => onChanged('kindergarten'),
          ),
          _LearningStageOption(
            code: 'primary',
            label: '小学',
            selected: selected == 'primary',
            enabled: enabled,
            onTap: () => onChanged('primary'),
          ),
        ],
      ),
    );
  }
}

class _LearningStageOption extends StatelessWidget {
  const _LearningStageOption({
    required this.code,
    required this.label,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final String code;
  final String label;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Semantics(
        button: true,
        selected: selected,
        enabled: enabled,
        label: label,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: enabled ? onTap : null,
          child: AnimatedContainer(
            key: ValueKey('gradeStage_$code'),
            duration: AppMotion.duration(context, 180),
            decoration: BoxDecoration(
              color: selected ? AppColors.brandDeep : Colors.transparent,
              borderRadius: BorderRadius.circular(AppRadii.control),
            ),
            child: Center(
              child: AnimatedDefaultTextStyle(
                duration: AppMotion.duration(context, 180),
                style: TextStyle(
                  color: selected ? Colors.white : AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14,
                  fontWeight: FontWeight.w800,
                  height: 1,
                  letterSpacing: 0,
                ),
                child: Text(label),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LearningIdentityNote extends StatelessWidget {
  const _LearningIdentityNote();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        Divider(height: 1, color: AppColors.borderSoft),
        SizedBox(height: 15),
        Row(
          children: [
            Icon(Icons.info_outline, color: AppColors.muted, size: 19),
            SizedBox(width: 9),
            Text(
              '称呼和年级可随时修改',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.3,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _EducationRecommendation {
  const _EducationRecommendation({required this.stage, required this.grade});

  final String stage;
  final String grade;
}

class _ChildGenderSelector extends StatelessWidget {
  const _ChildGenderSelector({required this.selected, required this.onSelect});

  final String selected;
  final ValueChanged<String> onSelect;

  static const _options = [
    _ChildGenderOption(
      value: 'male',
      label: '男孩',
      assetPath: 'assets/images/children/child_boy_avatar.png',
      tint: Color(0xFFE9F2F5),
    ),
    _ChildGenderOption(
      value: 'female',
      label: '女孩',
      assetPath: 'assets/images/children/child_girl_avatar.png',
      tint: Color(0xFFF4EFE4),
    ),
    _ChildGenderOption(
      value: 'unspecified',
      label: '不设置',
      tint: AppColors.surfaceStrong,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _FieldLabel('性别'),
        const SizedBox(height: 10),
        LayoutBuilder(
          builder: (context, constraints) {
            const gap = 8.0;
            final width = (constraints.maxWidth - gap * 2) / 3;
            return Row(
              children: [
                for (var index = 0; index < _options.length; index++) ...[
                  SizedBox(
                    width: width,
                    child: _ChildGenderCard(
                      option: _options[index],
                      selected: selected == _options[index].value,
                      onTap: () => onSelect(_options[index].value),
                    ),
                  ),
                  if (index < _options.length - 1) const SizedBox(width: gap),
                ],
              ],
            );
          },
        ),
      ],
    );
  }
}

class _ChildGenderOption {
  const _ChildGenderOption({
    required this.value,
    required this.label,
    required this.tint,
    this.assetPath,
  });

  final String value;
  final String label;
  final Color tint;
  final String? assetPath;
}

class _ChildGenderCard extends StatelessWidget {
  const _ChildGenderCard({
    required this.option,
    required this.selected,
    required this.onTap,
  });

  final _ChildGenderOption option;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final duration = AppMotion.duration(context, 160);
    return Semantics(
      button: true,
      selected: selected,
      label: '孩子性别，${option.label}',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: AnimatedContainer(
          duration: duration,
          curve: Curves.easeOutCubic,
          constraints: const BoxConstraints(
            minHeight: AppControls.minTouchTarget,
          ),
          padding: const EdgeInsets.fromLTRB(7, 7, 7, 8),
          decoration: BoxDecoration(
            color: selected
                ? Color.lerp(option.tint, AppColors.surfaceElevated, 0.22)
                : AppColors.surfaceSoft,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: selected
                  ? AppColors.brand.withValues(alpha: 0.30)
                  : AppColors.borderSoft,
              width: selected ? 1.2 : 1,
            ),
          ),
          child: Column(
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: option.tint,
                  borderRadius: BorderRadius.circular(13),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.62),
                  ),
                ),
                child: SizedBox(
                  width: double.infinity,
                  height: 62,
                  child: option.assetPath == null
                      ? const Center(
                          child: Icon(
                            Icons.tune_outlined,
                            size: 23,
                            color: AppColors.muted,
                          ),
                        )
                      : ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: Image.asset(
                            option.assetPath!,
                            fit: BoxFit.contain,
                            alignment: Alignment.bottomCenter,
                            filterQuality: FilterQuality.medium,
                            errorBuilder: (context, error, stackTrace) {
                              return const Center(
                                child: Icon(
                                  Icons.child_care_outlined,
                                  size: 24,
                                  color: AppColors.muted,
                                ),
                              );
                            },
                          ),
                        ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                option.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: selected ? AppColors.brandDeep : AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  height: 1.1,
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

class CameraNameSetupScreen extends ConsumerStatefulWidget {
  const CameraNameSetupScreen({super.key});

  @override
  ConsumerState<CameraNameSetupScreen> createState() =>
      _CameraNameSetupScreenState();
}

class _CameraNameSetupScreenState extends ConsumerState<CameraNameSetupScreen> {
  var _introLoading = false;
  var _previewing = false;
  var _saving = false;
  var _confirmedSimilarName = false;
  String? _wakeNameErrorText;
  String? _voiceMessage;

  @override
  void initState() {
    super.initState();
    Future.microtask(_playIntro);
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(setupDraftProvider);
    final wakeName = draft.cameraWakeName.trim();

    return _SetupScreenShell(
      step: 5,
      // V1 幼儿园首次设置不强制命名摄像头；本页保留给后续设备设置入口复用，不显示首次设置步数。
      showSetupProgress: false,
      title: '给摄像头起名',
      subtitle: '孩子以后可以用这个名字呼唤摄像头。',
      leadingIcon: Icons.record_voice_over_outlined,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _CameraVoicePanel(
            loading: _introLoading,
            message: _voiceMessage ?? '我会先向孩子介绍自己，再等你们一起决定一个好记的名字。',
          ),
          const SizedBox(height: 16),
          _SetupTextField(
            label: '摄像头昵称',
            value: draft.cameraWakeName,
            icon: Icons.sensors_outlined,
            errorText: _wakeNameErrorText,
            inputFormatters: [LengthLimitingTextInputFormatter(12)],
            onChanged: (value) {
              setState(() {
                _wakeNameErrorText = null;
                _confirmedSimilarName = false;
              });
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                cameraWakeName: value,
              );
            },
          ),
          const SizedBox(height: 12),
          _NameSuggestionRow(
            selected: wakeName,
            onSelect: (value) {
              setState(() {
                _wakeNameErrorText = null;
                _confirmedSimilarName = false;
              });
              ref.read(setupDraftProvider.notifier).state = draft.copyWith(
                cameraWakeName: value,
              );
            },
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: AppSecondaryButton(
                  label: _previewing ? '试听中' : '试听声线',
                  height: 44,
                  trailing: _previewing
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 1.6),
                        )
                      : const Icon(
                          Icons.volume_up_outlined,
                          color: AppColors.ink,
                          size: 17,
                        ),
                  onTap: _previewing ? null : () => _previewName(draft),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: AppSecondaryButton(
                  label: '边界说明',
                  height: 44,
                  trailing: const Icon(
                    Icons.info_outline,
                    color: AppColors.ink,
                    size: 17,
                  ),
                  onTap: () {
                    _showSetupToast(context, '摄像头只响应家庭看护相关请求，家长可随时调整规则。');
                  },
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          const _SetupNote(text: '建议使用 2 到 6 个中文字符，避免和家人称呼、孩子姓名太接近。'),
        ],
      ),
      primaryLabel: _saving ? '正在保存' : '设置紧急联系人',
      loading: _saving,
      onPrimary: _saving ? null : () => _saveName(draft),
    );
  }

  Future<void> _playIntro() async {
    setState(() => _introLoading = true);
    try {
      final result = await ref
          .read(setupRepositoryProvider)
          .playCameraNameIntro();
      if (!mounted) return;
      setState(() {
        _introLoading = false;
        _voiceMessage = result.message;
      });
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _introLoading = false;
        _voiceMessage = error.message;
      });
    }
  }

  Future<void> _previewName(SetupDraft draft) async {
    final validated = _validateWakeName(
      draft.cameraWakeName,
      ref.read(guardianIdentityOptionsProvider).asData?.value,
    );
    if (validated == null) return;

    FocusScope.of(context).unfocus();
    setState(() => _previewing = true);
    try {
      final result = await ref
          .read(setupRepositoryProvider)
          .previewCameraName(wakeName: validated);
      if (!mounted) return;
      setState(() {
        _previewing = false;
        _voiceMessage = result.message;
      });
      _showSetupToast(context, result.message);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _previewing = false;
        _voiceMessage = error.message;
      });
      _showSetupToast(context, error.message);
    }
  }

  Future<void> _saveName(SetupDraft draft) async {
    final validated = _validateWakeName(
      draft.cameraWakeName,
      ref.read(guardianIdentityOptionsProvider).asData?.value,
    );
    if (validated == null) return;

    if (_looksLikeFamilyName(validated, draft) && !_confirmedSimilarName) {
      setState(() => _confirmedSimilarName = true);
      _showSetupToast(context, '这个名字和家人称呼接近，再点一次即可确认使用。');
      return;
    }

    FocusScope.of(context).unfocus();
    setState(() => _saving = true);
    try {
      await ref
          .read(setupRepositoryProvider)
          .saveCameraName(wakeName: validated);
      await Future<void>.delayed(const Duration(milliseconds: 240));
      if (!mounted) return;
      context.go(setupEmergencyContactsPath);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _wakeNameErrorText = error.message;
      });
      _showSetupToast(context, error.message);
    }
  }

  String? _validateWakeName(String value, GuardianIdentityOptions? options) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      setState(() => _wakeNameErrorText = '请输入摄像头名字');
      return null;
    }
    final reservedFamilyNames =
        options?.allLabels.map((item) => item.label).toSet() ??
        const <String>{};
    if (reservedFamilyNames.contains(trimmed)) {
      setState(() => _wakeNameErrorText = '这个名字容易和家人称呼混淆');
      return null;
    }
    const blocked = ['笨蛋', '傻瓜', '坏蛋', '讨厌', '滚'];
    if (blocked.any(trimmed.contains)) {
      setState(() => _wakeNameErrorText = '这个名字不太适合孩子使用');
      return null;
    }
    final chineseOnly = RegExp(r'^[\u4e00-\u9fff]{2,6}$').hasMatch(trimmed);
    final shortName = RegExp(
      r'^[\u4e00-\u9fffA-Za-z0-9]{2,12}$',
    ).hasMatch(trimmed);
    if (!chineseOnly && !shortName) {
      setState(() => _wakeNameErrorText = '建议 2 到 6 个中文，或简短好读的名称');
      return null;
    }
    setState(() => _wakeNameErrorText = null);
    return trimmed;
  }

  bool _looksLikeFamilyName(String value, SetupDraft draft) {
    final parentName = draft.parentName.trim();
    final childName = draft.childName.trim();
    return (parentName.isNotEmpty &&
            (value == parentName || parentName.contains(value))) ||
        (childName.isNotEmpty &&
            (value == childName || childName.contains(value)));
  }
}

class _CameraVoicePanel extends StatelessWidget {
  const _CameraVoicePanel({required this.loading, required this.message});

  final bool loading;
  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.ink,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: AppColors.ink.withValues(alpha: 0.10),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(15, 15, 15, 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(AppRadii.full),
              ),
              child: SizedBox(
                width: 34,
                height: 34,
                child: Center(
                  child: loading
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 1.7,
                            valueColor: AlwaysStoppedAnimation<Color>(
                              Colors.white,
                            ),
                          ),
                        )
                      : const Icon(
                          Icons.spatial_audio_off_outlined,
                          color: Colors.white,
                          size: 18,
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
                    '摄像头会这样介绍自己',
                    style: TextStyle(
                      color: Colors.white,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    message,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.74),
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      height: 1.52,
                      letterSpacing: 0,
                    ),
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

class _NameSuggestionRow extends StatelessWidget {
  const _NameSuggestionRow({required this.selected, required this.onSelect});

  final String selected;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _FieldLabel('推荐名字'),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final name in const ['小暖', '小安', '小守'])
              _ChoiceChipButton(
                label: name,
                selected: selected == name,
                onTap: () => onSelect(name),
              ),
          ],
        ),
      ],
    );
  }
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
    final roleLabel =
        ref
            .watch(guardianIdentityOptionsProvider)
            .asData
            ?.value
            .roleLabelFor(draft.familyRole) ??
        draft.familyRole;

    return _SetupScreenShell(
      step: 6,
      // V1 幼儿园首次设置不强制紧急联系人；本页保留给设置入口复用，不显示首次设置步数。
      showSetupProgress: false,
      title: '紧急联系人',
      subtitle: '用于重要通知兜底和家庭协作记录。',
      leadingIcon: Icons.contact_phone_outlined,
      body: Column(
        children: [
          AppSecondaryButton(
            label: '从通讯录选择',
            trailing: const Icon(Icons.contacts_outlined, size: 17),
            onTap: () => _pickFromContacts(draft),
          ),
          const SizedBox(height: 14),
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
            detail: _setupCollaborationDetail(draft, roleLabel),
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

  Future<void> _pickFromContacts(SetupDraft draft) async {
    try {
      final picked = await pickPhoneContact();
      if (!mounted || picked == null) return;
      final nextName = picked.name.isEmpty ? draft.emergencyName : picked.name;
      final nextPhone = picked.phone.isEmpty
          ? draft.emergencyPhone
          : picked.phone;
      ref.read(setupDraftProvider.notifier).state = draft.copyWith(
        emergencyName: nextName,
        emergencyPhone: nextPhone,
      );
      setState(() => _phoneError = null);
      if (picked.phone.isEmpty) {
        _showSetupToast(context, '这个联系人没有可用手机号，请手动填写');
      }
    } on ContactPickerException catch (error) {
      if (mounted) _showSetupToast(context, error.message);
    }
  }
}

class _SetupScreenShell extends ConsumerWidget {
  const _SetupScreenShell({
    required this.step,
    required this.title,
    required this.subtitle,
    required this.leadingIcon,
    required this.body,
    required this.primaryLabel,
    required this.onPrimary,
    this.loading = false,
    this.showSetupProgress = true,
  });

  final int step;
  final String title;
  final String subtitle;
  final IconData leadingIcon;
  final Widget body;
  final String primaryLabel;
  final VoidCallback? onPrimary;
  final bool loading;
  final bool showSetupProgress;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final progressStep = showSetupProgress ? step : null;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.appBackgroundWarm,
        body: Stack(
          children: [
            const Positioned.fill(child: _SetupBackground()),
            SafeArea(
              bottom: false,
              child: Column(
                children: [
                  _SetupTopBar(
                    step: progressStep,
                    onBack: null,
                    onLogout: () => _confirmSetupLogout(context, ref),
                  ),
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
                            step: progressStep,
                          ),
                          const SizedBox(height: 16),
                          _SetupPanel(child: body),
                        ],
                      ),
                    ),
                  ),
                  _SetupActionDock(
                    bottomInset: bottomInset,
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
    this.showTrailing = true,
  });

  final double bottomInset;
  final String primaryLabel;
  final VoidCallback? onPrimary;
  final bool loading;
  final bool showTrailing;

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
            AppPrimaryButton(
              label: primaryLabel,
              loading: loading,
              trailing: loading || !showTrailing
                  ? null
                  : const AppButtonGlyph(icon: Icons.arrow_forward),
              onTap: onPrimary,
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
  const _SetupTopBar({required this.step, required this.onLogout, this.onBack});

  final int? step;
  final VoidCallback? onBack;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 6),
      child: Row(
        children: [
          if (onBack != null) ...[
            AppIconButton(
              icon: Icons.arrow_back,
              label: '返回上一步',
              onTap: onBack!,
            ),
            const SizedBox(width: 10),
          ],
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
          if (step != null) ...[
            const SizedBox(width: 10),
            DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.surfaceSoft.withValues(alpha: 0.78),
                borderRadius: BorderRadius.circular(AppRadii.full),
                border: Border.all(color: AppColors.borderSoft),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
                child: Text(
                  '$step / $_setupTotalSteps',
                  style: const TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
              ),
            ),
          ],
          const Spacer(),
          AppIconButton(
            icon: Icons.logout_outlined,
            label: '退出登录',
            onTap: onLogout,
          ),
        ],
      ),
    );
  }
}

Future<void> _confirmSetupLogout(BuildContext context, WidgetRef ref) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '退出登录',
    message: '退出后可以使用其他手机号登录。当前首次设置进度会保留在这个账号和家庭空间里。',
    confirmLabel: '退出登录',
    danger: true,
  );
  if (!confirmed) return;
  await ref.read(authRepositoryProvider).logout();
  await ref.read(setupStoreProvider).clearPendingChildProfile();
  invalidateAuthenticatedSessionData(ref);
  if (context.mounted) context.go(loginPath);
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
  final int? step;

  @override
  Widget build(BuildContext context) {
    final progress = step == null
        ? null
        : (step! / _setupTotalSteps).clamp(0.0, 1.0).toDouble();

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
                if (progress != null) ...[
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
                key: ValueKey('choice_${label}_$option'),
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
    super.key,
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
    this.hintText,
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
  final String? hintText;
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
        final fieldKey = ValueKey('setupField_${widget.label}');
        final inputField = AnimatedContainer(
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
                  key: ValueKey('setupInput_${widget.label}'),
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
                  decoration: InputDecoration(
                    filled: false,
                    fillColor: Colors.transparent,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    errorBorder: InputBorder.none,
                    focusedErrorBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                    hintText: widget.hintText,
                    hintStyle: const TextStyle(
                      color: AppColors.subtle,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      height: 1.2,
                    ),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(vertical: 14),
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
        );
        final interactiveField = widget.readOnly && widget.onTap != null
            ? GestureDetector(
                key: fieldKey,
                behavior: HitTestBehavior.opaque,
                onTap: widget.onTap,
                child: inputField,
              )
            : KeyedSubtree(key: fieldKey, child: inputField);

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _FieldLabel(widget.label),
            const SizedBox(height: 8),
            interactiveField,
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
  showAppToast(context, message);
}
