import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/platform/contact_picker.dart';
import 'package:warm_sight/src/core/storage/onboarding_store.dart';
import 'package:warm_sight/src/core/theme/app_system_ui.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/auth/application/auth_repository.dart';
import 'package:warm_sight/src/features/auth/application/session_data_invalidation.dart';
import 'package:warm_sight/src/features/care/application/care_repository.dart';
import 'package:warm_sight/src/features/care/domain/care_models.dart';
import 'package:warm_sight/src/features/devices/application/device_repository.dart';
import 'package:warm_sight/src/features/devices/application/selected_device_controller.dart';
import 'package:warm_sight/src/features/devices/domain/device_models.dart';
import 'package:warm_sight/src/features/live_care/application/camera_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_availability_repository.dart';
import 'package:warm_sight/src/features/learning/application/learning_preparation_repository.dart';
import 'package:warm_sight/src/features/learning/domain/learning_preparation_models.dart';
import 'package:warm_sight/src/features/learning/presentation/widgets/learning_preparation_card.dart';
import 'package:warm_sight/src/features/points/application/point_repository.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/rewards/application/reward_repository.dart';
import 'package:warm_sight/src/features/rewards/domain/reward_models.dart';
import 'package:warm_sight/src/features/setup/presentation/add_camera_sheet.dart';
import 'package:warm_sight/src/features/setup/presentation/setup_flow_screens.dart';
import 'package:warm_sight/src/shared/domain/guardian_identity.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_compact_toggle.dart';
import 'package:warm_sight/src/shared/widgets/app_list_row.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_segmented_control.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_text_field.dart';
import 'package:warm_sight/src/shared/widgets/app_time_picker_sheet.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';
import 'package:warm_sight/src/shared/widgets/guardian_identity_selector.dart';
import 'package:warm_sight/src/shared/widgets/status_chip.dart';

const _brandLogoMarkAsset = 'assets/brand/nuantong-logo-mark.png';

class AccountProfilePage extends ConsumerWidget {
  const AccountProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(accountProfileProvider);
    final identityOptions = ref.watch(guardianIdentityOptionsProvider);
    final profileData = profile.asData?.value;
    final optionsData = identityOptions.asData?.value;

    if (profile.isLoading || identityOptions.isLoading) {
      return const _Page(
        title: '个人信息',
        children: [_Loading(title: '正在同步个人信息')],
      );
    }
    if (profile.hasError) {
      return _Page(
        title: '个人信息',
        children: [
          _ErrorState(
            error: profile.error ?? '个人信息暂时无法同步',
            onRetry: () => ref.invalidate(accountProfileProvider),
          ),
        ],
      );
    }
    if (identityOptions.hasError) {
      return _Page(
        title: '个人信息',
        children: [
          _ErrorState(
            error: identityOptions.error ?? '身份配置暂时无法同步',
            onRetry: () => ref.invalidate(guardianIdentityOptionsProvider),
          ),
        ],
      );
    }

    if (profileData == null || optionsData == null) {
      return const _Page(title: '个人信息', children: []);
    }

    return _AccountProfileForm(profile: profileData, options: optionsData);
  }
}

class _AccountProfileForm extends ConsumerStatefulWidget {
  const _AccountProfileForm({required this.profile, required this.options});

  final AccountProfile profile;
  final GuardianIdentityOptions options;

  @override
  ConsumerState<_AccountProfileForm> createState() =>
      _AccountProfileFormState();
}

class _AccountProfileFormState extends ConsumerState<_AccountProfileForm> {
  late final TextEditingController _family;
  late String _relationshipKey;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    _family = TextEditingController(text: widget.profile.familyName);
    _relationshipKey = _initialRelationshipKey();
    _family.addListener(_refreshPreview);
  }

  @override
  void dispose() {
    _family.removeListener(_refreshPreview);
    _family.dispose();
    super.dispose();
  }

  void _refreshPreview() {
    if (mounted) setState(() {});
  }

  String _initialRelationshipKey() {
    final stored = _storedIdentityValue;
    final fromStoredValue = widget.options.keyForValue(stored);
    if (fromStoredValue.isNotEmpty) return fromStoredValue;
    final rawKey = widget.profile.relationshipKey.trim();
    if (widget.options.optionForKey(rawKey) != null) return rawKey;
    return '';
  }

  String get _storedIdentityValue {
    if (widget.profile.relationshipKey.isNotEmpty) {
      return widget.profile.relationshipKey;
    }
    if (widget.profile.relationship.isNotEmpty) {
      return widget.profile.relationship;
    }
    return widget.profile.displayName;
  }

  String get _relationshipLabel {
    final label = _relationshipKey.isNotEmpty
        ? widget.options.labelForKey(_relationshipKey)
        : widget.options.labelForStoredValue(_storedIdentityValue);
    return label.isEmpty ? '监护人' : label;
  }

  String get _identityGroupLabel {
    final group = widget.options.groupForValue(
      _relationshipKey.isNotEmpty ? _relationshipKey : _storedIdentityValue,
    );
    if (group?.label.isNotEmpty == true) return group!.label;
    if (_relationshipKey.isEmpty && _relationshipLabel != '监护人') {
      return '自定义称呼';
    }
    return '家庭身份';
  }

  String get _identityImageAsset {
    if (_relationshipKey.isNotEmpty) {
      final asset = widget.options.imageAssetForKey(_relationshipKey);
      if (asset.isNotEmpty) return asset;
    }
    return 'assets/images/guardian/guardian_default.png';
  }

  @override
  Widget build(BuildContext context) {
    final relationshipLabel = _relationshipLabel;
    final familyName = _family.text.trim().isEmpty
        ? '我的家庭空间'
        : _family.text.trim();
    final roleLabel = widget.options.roleLabelFor(widget.profile.role);
    final normalizedRole = roleLabel.isEmpty ? '管理员' : roleLabel;
    final canEditFamily = widget.profile.can('manage_family_members');
    final canSave = canEditFamily && !_saving && _family.text.trim().isNotEmpty;

    return _PersonalProfileScaffold(
      identityLabel: relationshipLabel,
      identityGroupLabel: _identityGroupLabel,
      identityImageAsset: _identityImageAsset,
      roleLabel: normalizedRole,
      phone: widget.profile.phone,
      familyName: familyName,
      saving: _saving,
      canSave: canSave,
      onBack: _goBack,
      onSave: _save,
      child: _PersonalProfilePanel(
        familyController: _family,
        phone: widget.profile.phone,
        canEditFamily: canEditFamily,
        onPhoneChange: _changePhone,
      ),
    );
  }

  void _goBack() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoute.profile.path);
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .updateAccountProfile(familyName: _family.text.trim());
      ref.invalidate(accountProfileProvider);
      ref.invalidate(profileSummaryProvider);
      if (mounted) _toast(context, '已保存');
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _changePhone() {
    return _showPhoneChangeSheet(context, ref, widget.profile.phone);
  }
}

class _PersonalProfileScaffold extends StatelessWidget {
  const _PersonalProfileScaffold({
    required this.identityLabel,
    required this.identityGroupLabel,
    required this.identityImageAsset,
    required this.roleLabel,
    required this.phone,
    required this.familyName,
    required this.saving,
    required this.canSave,
    required this.onBack,
    required this.onSave,
    required this.child,
  });

  final String identityLabel;
  final String identityGroupLabel;
  final String identityImageAsset;
  final String roleLabel;
  final String phone;
  final String familyName;
  final bool saving;
  final bool canSave;
  final VoidCallback onBack;
  final VoidCallback onSave;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final safe = MediaQuery.paddingOf(context);
    final viewInsets = MediaQuery.viewInsetsOf(context);
    final bottomInset = AppControls.buttonHeight + safe.bottom + 44;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        resizeToAvoidBottomInset: true,
        backgroundColor: AppColors.appBackground,
        body: ListView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: EdgeInsets.only(bottom: bottomInset),
          children: [
            _CompactPersonalHeader(
              safeTop: safe.top,
              identityLabel: identityLabel,
              identityGroupLabel: identityGroupLabel,
              identityImageAsset: identityImageAsset,
              roleLabel: roleLabel,
              phone: phone,
              familyName: familyName,
              onBack: onBack,
            ),
            const SizedBox(height: 14),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: child,
            ),
          ],
        ),
        bottomNavigationBar: AnimatedPadding(
          duration: AppMotion.duration(context, 180),
          curve: Curves.easeOutCubic,
          padding: EdgeInsets.fromLTRB(
            16,
            8,
            16,
            viewInsets.bottom > 0 ? viewInsets.bottom + 8 : safe.bottom + 18,
          ),
          child: AppPrimaryButton(
            label: saving ? '保存中' : '保存',
            loading: saving,
            onTap: canSave ? onSave : null,
          ),
        ),
      ),
    );
  }
}

class _CompactPersonalHeader extends StatelessWidget {
  const _CompactPersonalHeader({
    required this.safeTop,
    required this.identityLabel,
    required this.identityGroupLabel,
    required this.identityImageAsset,
    required this.roleLabel,
    required this.phone,
    required this.familyName,
    required this.onBack,
  });

  final double safeTop;
  final String identityLabel;
  final String identityGroupLabel;
  final String identityImageAsset;
  final String roleLabel;
  final String phone;
  final String familyName;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final headerHeight = safeTop + 178;

    return SizedBox(
      height: headerHeight,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AppColors.surfaceElevated,
              AppColors.appBackgroundMid,
              AppColors.brandSageWash,
            ],
          ),
        ),
        child: Stack(
          children: [
            Positioned(
              left: 18,
              right: 18,
              top: safeTop + 8,
              child: Row(
                children: [
                  _CompactBackButton(onTap: onBack),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text(
                      '个人信息',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 20,
                        fontWeight: FontWeight.w900,
                        height: 1.15,
                        letterSpacing: 0,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Positioned(
              right: 10,
              bottom: 0,
              width: 122,
              height: 138,
              child: IgnorePointer(
                child: Image.asset(
                  identityImageAsset,
                  fit: BoxFit.contain,
                  alignment: Alignment.bottomCenter,
                  filterQuality: FilterQuality.medium,
                  errorBuilder: (_, _, _) => Image.asset(
                    'assets/images/guardian/guardian_default.png',
                    fit: BoxFit.contain,
                    alignment: Alignment.bottomCenter,
                  ),
                ),
              ),
            ),
            Positioned(
              left: 18,
              right: 132,
              bottom: 18,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _HeaderFamilyPill(label: familyName),
                  const SizedBox(height: 10),
                  Text(
                    identityLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.ink,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 26,
                      fontWeight: FontWeight.w900,
                      height: 1.06,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '${_phoneMask(phone)} · $identityGroupLabel · $roleLabel',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                      height: 1.25,
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

class _PersonalProfilePanel extends StatelessWidget {
  const _PersonalProfilePanel({
    required this.familyController,
    required this.phone,
    required this.canEditFamily,
    required this.onPhoneChange,
  });

  final TextEditingController familyController;
  final String phone;
  final bool canEditFamily;
  final VoidCallback onPhoneChange;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 10),
        _ProfileTextField(
          icon: Icons.home_work_outlined,
          label: '家庭空间名称',
          controller: familyController,
          hint: '例如：我的家庭空间',
          readOnly: !canEditFamily,
        ),
        const SizedBox(height: 12),
        AppListRow(
          icon: Icons.smartphone_outlined,
          title: '手机号',
          subtitle: '${_phoneMask(phone)}，用于登录和安全验证',
          tone: AppListRowTone.blue,
          trailing: const _InlineAction(label: '更换'),
          onTap: onPhoneChange,
        ),
      ],
    );
  }
}

class _CompactBackButton extends StatelessWidget {
  const _CompactBackButton({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surfaceElevated.withValues(alpha: 0.86),
      borderRadius: BorderRadius.circular(AppRadii.full),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.full),
        onTap: onTap,
        child: const SizedBox(
          width: AppControls.iconButtonSize,
          height: AppControls.iconButtonSize,
          child: Center(
            child: Icon(
              Icons.arrow_back_ios_new,
              color: AppColors.ink,
              size: 18,
            ),
          ),
        ),
      ),
    );
  }
}

class _HeaderFamilyPill extends StatelessWidget {
  const _HeaderFamilyPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceElevated.withValues(alpha: 0.74),
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.home_work_outlined,
              color: AppColors.brandSage,
              size: 14,
            ),
            const SizedBox(width: 7),
            Flexible(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.ink.withValues(alpha: 0.82),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  height: 1.2,
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

class _ProfileTextField extends StatelessWidget {
  const _ProfileTextField({
    required this.icon,
    required this.label,
    required this.controller,
    this.hint,
    this.readOnly = false,
  });

  final IconData icon;
  final String label;
  final TextEditingController controller;
  final String? hint;
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    return AppTextField(
      label: label,
      icon: icon,
      controller: controller,
      hintText: hint,
      readOnly: readOnly,
    );
  }
}

class _InlineAction extends StatelessWidget {
  const _InlineAction({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brandWash.withValues(alpha: 0.62),
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
        child: Text(
          label,
          style: const TextStyle(
            color: AppColors.brandDeep,
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

class AccountSecurityPage extends ConsumerStatefulWidget {
  const AccountSecurityPage({super.key});

  @override
  ConsumerState<AccountSecurityPage> createState() =>
      _AccountSecurityPageState();
}

class _AccountSecurityPageState extends ConsumerState<AccountSecurityPage> {
  String? _revokingSessionId;
  var _deletingAccount = false;

  @override
  Widget build(BuildContext context) {
    final security = ref.watch(accountSecurityProvider);
    return _Page(
      title: '账号安全',
      subtitle: '管理已登录设备，处理账号注销。',
      children: security.when(
        data: (data) => [
          _AccountSecurityOverview(security: data),
          const SizedBox(height: 16),
          _LoginDeviceSection(
            devices: data.loginDevices,
            revokingSessionId: _revokingSessionId,
            onRevoke: _confirmRevokeDevice,
          ),
          const SizedBox(height: 16),
          _AccountDeletionSection(
            deleting: _deletingAccount,
            onDelete: _confirmAccountDeletion,
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

  Future<void> _confirmRevokeDevice(LoginDevice device) async {
    if (device.current || _revokingSessionId != null) return;
    final deviceLabel = _displayDeviceLabel(context, device);
    final confirmed = await showAppConfirmSheet(
      context: context,
      title: '移除登录设备',
      message: '移除后，$deviceLabel 会退出登录，需要重新通过手机号验证码登录。当前设备不会受到影响。',
      confirmLabel: '移除',
      danger: true,
    );
    if (!confirmed || !mounted) return;
    setState(() => _revokingSessionId = device.id);
    try {
      await ref.read(profileRepositoryProvider).revokeLoginDevice(device.id);
      ref.invalidate(accountSecurityProvider);
      await ref.read(accountSecurityProvider.future);
      if (mounted) {
        showAppToast(context, '登录设备已移除', tone: AppToastTone.success);
      }
    } on ProfileException catch (error) {
      if (mounted) {
        showAppToast(context, error.message, tone: AppToastTone.danger);
      }
    } finally {
      if (mounted) setState(() => _revokingSessionId = null);
    }
  }

  Future<void> _confirmAccountDeletion() async {
    if (_deletingAccount) return;
    final confirmed = await _showAccountDeletionSheet(context);
    if (!confirmed || !mounted) return;
    setState(() => _deletingAccount = true);
    try {
      await ref.read(profileRepositoryProvider).requestAccountDeletion();
      await ref.read(authRepositoryProvider).logout();
      invalidateAuthenticatedSessionData(ref);
      if (mounted) context.go(loginPath);
    } on ProfileException catch (error) {
      if (mounted) {
        showAppToast(context, error.message, tone: AppToastTone.danger);
      }
    } finally {
      if (mounted) setState(() => _deletingAccount = false);
    }
  }
}

class _AccountSecurityOverview extends StatelessWidget {
  const _AccountSecurityOverview({required this.security});

  final AccountSecurity security;

  @override
  Widget build(BuildContext context) {
    final activeCount = security.loginDevices
        .where((item) => item.active)
        .length;
    return AppSurface(
      color: const Color(0xFFEFF8F4),
      borderColor: AppColors.brandSage.withValues(alpha: 0.12),
      child: Row(
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.72),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const SizedBox(
              width: 46,
              height: 46,
              child: Center(
                child: Icon(
                  Icons.admin_panel_settings_outlined,
                  color: AppColors.brandSage,
                  size: 24,
                ),
              ),
            ),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '账号保护中',
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 17,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$activeCount 台设备已登录，用手机号验证码保护账号。',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: _mutedText,
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          StatusChip(label: '正常', tone: StatusTone.success),
        ],
      ),
    );
  }
}

class _LoginDeviceSection extends StatelessWidget {
  const _LoginDeviceSection({
    required this.devices,
    required this.revokingSessionId,
    required this.onRevoke,
  });

  final List<LoginDevice> devices;
  final String? revokingSessionId;
  final ValueChanged<LoginDevice> onRevoke;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _SectionTitle('登录设备'),
        const SizedBox(height: 10),
        if (devices.isEmpty)
          const AppEmptyState(
            icon: Icons.devices_outlined,
            title: '暂无登录设备',
            message: '重新登录后，这里会显示正在使用的手机或电脑。',
          )
        else
          Column(
            children: [
              for (var index = 0; index < devices.length; index++) ...[
                _LoginDeviceCard(
                  device: devices[index],
                  loading: revokingSessionId == devices[index].id,
                  onRevoke: onRevoke,
                ),
                if (index != devices.length - 1) const SizedBox(height: 10),
              ],
            ],
          ),
      ],
    );
  }
}

class _LoginDeviceCard extends StatelessWidget {
  const _LoginDeviceCard({
    required this.device,
    required this.loading,
    required this.onRevoke,
  });

  final LoginDevice device;
  final bool loading;
  final ValueChanged<LoginDevice> onRevoke;

  @override
  Widget build(BuildContext context) {
    final displayLabel = _displayDeviceLabel(context, device);
    return AppSurface(
      padding: const EdgeInsets.fromLTRB(14, 13, 12, 13),
      color: Colors.white.withValues(alpha: 0.88),
      child: Row(
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: device.current
                  ? AppColors.brandWash.withValues(alpha: 0.78)
                  : AppColors.surfaceStrong,
              borderRadius: BorderRadius.circular(14),
            ),
            child: SizedBox(
              width: 46,
              height: 46,
              child: Center(
                child: Icon(
                  _deviceIcon(device),
                  color: device.current ? AppColors.brandSage : AppColors.ink,
                  size: 23,
                ),
              ),
            ),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  displayLabel,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _loginDeviceSubtitle(device),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: _mutedText,
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          if (device.current)
            StatusChip(label: '当前', tone: StatusTone.success)
          else
            _DeviceRemoveButton(
              loading: loading,
              onTap: loading ? null : () => onRevoke(device),
            ),
        ],
      ),
    );
  }
}

class _DeviceRemoveButton extends StatelessWidget {
  const _DeviceRemoveButton({required this.loading, required this.onTap});

  final bool loading;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final visualButton = DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppRadii.full),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: SizedBox(
        height: 34,
        width: 52,
        child: Center(
          child: loading
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text(
                  '移除',
                  style: TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0,
                  ),
                ),
        ),
      ),
    );

    return Semantics(
      button: true,
      label: loading ? '正在移除设备' : '移除设备',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: SizedBox(
          height: 44,
          width: 54,
          child: Center(child: visualButton),
        ),
      ),
    );
  }
}

class _AccountDeletionSection extends StatelessWidget {
  const _AccountDeletionSection({
    required this.deleting,
    required this.onDelete,
  });

  final bool deleting;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.dangerWash.withValues(alpha: 0.50),
      borderColor: AppColors.danger.withValues(alpha: 0.10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.76),
              borderRadius: BorderRadius.circular(14),
            ),
            child: const SizedBox(
              width: 46,
              height: 46,
              child: Center(
                child: Icon(
                  Icons.delete_outline,
                  color: AppColors.danger,
                  size: 24,
                ),
              ),
            ),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '注销账号',
                  style: TextStyle(
                    color: AppColors.danger,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 5),
                const Text(
                  '注销前请确认家庭管理员、设备绑定和儿童数据处理方式。',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    height: 1.42,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 12),
                AppDangerButton(
                  label: deleting ? '提交中' : '注销账号',
                  onTap: deleting ? null : onDelete,
                  trailing: deleting
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.chevron_right, size: 18),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

Future<bool> _showAccountDeletionSheet(BuildContext context) async {
  return await showAppBottomSheet<bool>(
        context: context,
        maxHeightFactor: 0.66,
        child: AppBottomSheetBody(
          title: '注销账号',
          subtitle: '这是不可逆操作。提交后当前账号会退出登录，并进入注销处理流程。',
          footer: Row(
            children: [
              Expanded(
                child: AppSecondaryButton(
                  label: '再想想',
                  onTap: () => Navigator.of(context).pop(false),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: AppDangerButton(
                  label: '确认注销',
                  onTap: () => Navigator.of(context).pop(true),
                ),
              ),
            ],
          ),
          child: const Column(
            children: [
              _DeletionNoticeRow(
                icon: Icons.person_remove_outlined,
                title: '账号将无法继续登录',
                message: '手机号验证码登录、家庭协作和个人资料入口会停止使用。',
              ),
              SizedBox(height: 10),
              _DeletionNoticeRow(
                icon: Icons.family_restroom_outlined,
                title: '家庭空间可能受影响',
                message: '请先确认管理员转移、家庭成员权限和已绑定设备，避免影响其他家人。',
              ),
              SizedBox(height: 10),
              _DeletionNoticeRow(
                icon: Icons.privacy_tip_outlined,
                title: '个人信息将按规则处理',
                message: '可删除的数据会删除或匿名化；依法需要留存的数据仅用于合规和安全审计。',
              ),
              SizedBox(height: 10),
              _DeletionNoticeRow(
                icon: Icons.logout_outlined,
                title: '所有登录设备会退出',
                message: '提交后当前设备和其他已登录设备都会失效。',
              ),
            ],
          ),
        ),
      ) ??
      false;
}

class _DeletionNoticeRow extends StatelessWidget {
  const _DeletionNoticeRow({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      padding: const EdgeInsets.fromLTRB(13, 12, 13, 12),
      color: Colors.white.withValues(alpha: 0.86),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.dangerWash.withValues(alpha: 0.58),
              borderRadius: BorderRadius.circular(12),
            ),
            child: SizedBox(
              width: 38,
              height: 38,
              child: Center(
                child: Icon(icon, color: AppColors.danger, size: 21),
              ),
            ),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 14,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 3),
                Text(message, style: _mutedText),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

IconData _deviceIcon(LoginDevice device) {
  final value = '${device.deviceType} ${device.platform}'.toLowerCase();
  if (value.contains('phone') ||
      value.contains('ios') ||
      value.contains('android')) {
    return Icons.smartphone_outlined;
  }
  if (value.contains('browser') || value.contains('desktop')) {
    return Icons.desktop_windows_outlined;
  }
  return Icons.devices_outlined;
}

String _displayDeviceLabel(BuildContext context, LoginDevice device) {
  final label = device.label.trim();
  if (_hasSpecificDeviceLabel(label)) return label;
  if (device.model.isNotEmpty &&
      !device.model.toLowerCase().contains('iphone')) {
    return device.model;
  }
  if (device.hardware.isNotEmpty) return device.hardware;
  final platformLabel = _devicePlatformLabel(device.platform);
  if (platformLabel.isNotEmpty) return platformLabel;
  if (!device.current) return '其他登录设备';
  return switch (Theme.of(context).platform) {
    TargetPlatform.iOS => '本机 iPhone',
    TargetPlatform.android => 'Android 手机',
    TargetPlatform.macOS => 'Mac 设备',
    TargetPlatform.windows => 'Windows 设备',
    TargetPlatform.linux => 'Linux 设备',
    TargetPlatform.fuchsia => '其他登录设备',
  };
}

String _loginDeviceSubtitle(LoginDevice device) {
  final parts = <String>[
    _formatSessionTime(device.lastActiveAt),
    device.current ? '当前设备' : '已登录',
  ];
  if (device.osVersion.isNotEmpty) parts.add(device.osVersion);
  if (device.appVersion.isNotEmpty) parts.add('App ${device.appVersion}');
  if (_hasIncompleteDeviceInfo(device)) {
    parts.add('设备信息不完整');
  }
  return parts.join(' · ');
}

bool _hasSpecificDeviceLabel(String label) {
  final normalized = label.trim().toLowerCase();
  return normalized.isNotEmpty &&
      normalized != '已登录设备' &&
      normalized != '其他登录设备' &&
      normalized != 'unknown' &&
      normalized != 'unknown device';
}

String _devicePlatformLabel(String platform) {
  final normalized = platform.toLowerCase();
  if (normalized.contains('ios') || normalized.contains('iphone')) {
    return 'iPhone 设备';
  }
  if (normalized.contains('android')) return 'Android 手机';
  if (normalized.contains('mac')) return 'Mac 设备';
  if (normalized.contains('windows')) return 'Windows 设备';
  if (normalized.contains('linux')) return 'Linux 设备';
  return '';
}

bool _hasIncompleteDeviceInfo(LoginDevice device) {
  return !_hasSpecificDeviceLabel(device.label) &&
      device.model.trim().isEmpty &&
      device.hardware.trim().isEmpty &&
      _devicePlatformLabel(device.platform).isEmpty;
}

String _formatSessionTime(int epochMillis) {
  if (epochMillis <= 0) return '最近活跃';
  final time = DateTime.fromMillisecondsSinceEpoch(epochMillis);
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(time.year, time.month, time.day);
  final hour = time.hour.toString().padLeft(2, '0');
  final minute = time.minute.toString().padLeft(2, '0');
  if (day == today) return '今天 $hour:$minute 活跃';
  if (day == today.subtract(const Duration(days: 1))) {
    return '昨天 $hour:$minute 登录';
  }
  return '${time.month}月${time.day}日 $hour:$minute 登录';
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
          ],
        ),
      ],
    );
  }
}

class ReportsHubPage extends ConsumerStatefulWidget {
  const ReportsHubPage({this.initialIndex = 0, super.key});

  final int initialIndex;

  @override
  ConsumerState<ReportsHubPage> createState() => _ReportsHubPageState();
}

class _ReportsHubPageState extends ConsumerState<ReportsHubPage> {
  late int _index = widget.initialIndex.clamp(0, 1).toInt();

  @override
  Widget build(BuildContext context) {
    return _Page(
      title: '看护报告',
      subtitle: '日报和周报',
      children: [
        AppSegmentedControl<int>(
          value: _index,
          semanticLabel: '报告类型',
          onChanged: (value) => setState(() => _index = value),
          options: const [
            AppSegmentOption(value: 0, label: '今日报告'),
            AppSegmentOption(value: 1, label: '周报'),
          ],
        ),
        const SizedBox(height: 12),
        switch (_index) {
          0 => _ReportPane(provider: dailyReportProvider),
          _ => _ReportPane(provider: weeklyReportProvider),
        },
      ],
    );
  }
}

class RulesReminderHubPage extends StatelessWidget {
  const RulesReminderHubPage({super.key});

  @override
  Widget build(BuildContext context) {
    return _Page(
      title: 'AI 规则与提醒',
      subtitle: '提醒方式、语音提醒和通知节奏',
      children: [
        AppSurface(
          child: Column(
            children: [
              AppListRow(
                icon: Icons.record_voice_over_outlined,
                title: '语音与称呼',
                subtitle: '唤醒名、声线和睡前边界',
                tone: AppListRowTone.blue,
                onTap: () => context.push(profileConversationPath),
              ),
              const _CompactDivider(),
              AppListRow(
                icon: Icons.volunteer_activism_outlined,
                title: '看护能力',
                subtitle: '坐姿、收纳、用餐和睡眠提醒',
                tone: AppListRowTone.neutral,
                onTap: () => context.push(profileCareCapabilitiesPath),
              ),
              const _CompactDivider(),
              AppListRow(
                icon: Icons.schedule_outlined,
                title: '作息时间',
                subtitle: '上学日和周末提醒时间',
                tone: AppListRowTone.amber,
                onTap: () => context.push(profileRoutineWindowsPath),
              ),
              const _CompactDivider(),
              AppListRow(
                icon: Icons.notifications_outlined,
                title: '通知与提醒',
                subtitle: '家长通知、设备和日报提醒',
                tone: AppListRowTone.neutral,
                onTap: () => context.push(profileNotificationsPath),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _CompactDivider extends StatelessWidget {
  const _CompactDivider();

  @override
  Widget build(BuildContext context) {
    return Divider(
      height: 1,
      thickness: 1,
      indent: 50,
      color: AppColors.borderSoft.withValues(alpha: 0.86),
    );
  }
}

class FamilyMembersPage extends ConsumerWidget {
  const FamilyMembersPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final members = ref.watch(familyMembersProvider);
    final invitations = ref.watch(familyInvitationsProvider);
    final account = ref.watch(accountProfileProvider).asData?.value;
    final canManage = account?.can('manage_family_members') ?? false;
    final canManageFamilyCode = account?.can('manage_family_code') ?? false;
    final familyCode = ref.watch(familyCodeProvider);
    final identityOptions = ref
        .watch(guardianIdentityOptionsProvider)
        .asData
        ?.value;
    return _Page(
      title: '家庭成员',
      subtitle: canManage ? '邀请成员，管理加入状态' : '查看家庭成员和邀请状态',
      trailing: canManage
          ? AppIconButton(
              icon: Icons.person_add_outlined,
              label: '新增成员',
              onTap: () => _editMember(context, ref),
            )
          : null,
      children: members.when(
        data: (items) => [
          familyCode.when(
            data: (code) => _FamilyCodePanel(
              code: code,
              canReset: canManageFamilyCode,
              onCopy: () => _copyFamilyCode(context, code),
              onReset: canManageFamilyCode
                  ? () => _resetFamilyCode(context, ref)
                  : null,
            ),
            loading: () => const _FamilyPanel(
              title: '家庭号',
              subtitle: '正在同步家庭号',
              child: AppLoadingState(
                title: '正在同步家庭号',
                message: '请稍候。',
                compact: true,
              ),
            ),
            error: (error, _) => AppStateView(
              variant: AppStateVariant.serviceUnavailable,
              title: '家庭号暂时无法同步',
              message: error is ProfileException ? error.message : '请稍后重试。',
              primaryActionLabel: '重新加载',
              onPrimaryAction: () => ref.invalidate(familyCodeProvider),
              compact: true,
            ),
          ),
          const SizedBox(height: 14),
          if (items.isEmpty)
            _FamilyEmptyPanel(
              canManage: canManage,
              onAdd: canManage ? () => _editMember(context, ref) : null,
            )
          else
            _FamilyMembersPanel(
              members: items,
              account: account,
              options: identityOptions,
              canManage: canManage,
              onMemberAction: (member) =>
                  _showMemberActions(context, ref, member, account),
            ),
          const SizedBox(height: 14),
          invitations.when(
            data: (pending) => pending.isEmpty
                ? const SizedBox.shrink()
                : _FamilyInvitationsPanel(
                    invitations: pending,
                    options: identityOptions,
                    canManage: canManage,
                    onResend: (invitation) =>
                        _resendInvitation(context, ref, invitation),
                    onCancel: (invitation) =>
                        _cancelInvitation(context, ref, invitation),
                  ),
            loading: () => const SizedBox.shrink(),
            error: (error, _) => const SizedBox.shrink(),
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

class _FamilyMembersPanel extends StatelessWidget {
  const _FamilyMembersPanel({
    required this.members,
    required this.account,
    required this.options,
    required this.canManage,
    required this.onMemberAction,
  });

  final List<FamilyMember> members;
  final AccountProfile? account;
  final GuardianIdentityOptions? options;
  final bool canManage;
  final ValueChanged<FamilyMember> onMemberAction;

  @override
  Widget build(BuildContext context) {
    return _FamilyPanel(
      title: '已加入成员',
      subtitle: canManage ? '管理员可以调整成员与设备权限。' : '成员权限由家庭管理员维护。',
      child: Column(
        children: [
          for (var index = 0; index < members.length; index++) ...[
            _FamilyMemberTile(
              member: members[index],
              title: _familyMemberTitle(members[index], options),
              roleLabel: _familyRoleLabel(
                options,
                members[index].role,
                members[index].roleLabel,
              ),
              isCurrentUser:
                  members[index].userId.isNotEmpty &&
                  members[index].userId == account?.userId,
              canManage: canManage,
              onManage: () => onMemberAction(members[index]),
            ),
            if (index != members.length - 1) const _FamilyDivider(),
          ],
        ],
      ),
    );
  }
}

class _FamilyCodePanel extends StatelessWidget {
  const _FamilyCodePanel({
    required this.code,
    required this.canReset,
    required this.onCopy,
    required this.onReset,
  });

  final FamilyCodeInfo code;
  final bool canReset;
  final VoidCallback onCopy;
  final VoidCallback? onReset;

  @override
  Widget build(BuildContext context) {
    final displayCode = code.code.isEmpty ? '未生成' : code.code;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(22),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.brandWash.withValues(alpha: 0.86),
            Colors.white.withValues(alpha: 0.92),
          ],
        ),
        border: Border.all(color: AppColors.brand.withValues(alpha: 0.14)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF557A86).withValues(alpha: 0.06),
            blurRadius: 14,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(15, 14, 13, 13),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(
              children: [
                _FamilyAvatar(
                  icon: Icons.tag_outlined,
                  tone: AppColors.brand,
                  fill: Colors.white,
                ),
                SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('家庭号', style: _sectionTitleStyle),
                      SizedBox(height: 5),
                      Text(
                        '输入家庭号会以临时查看者加入。',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: _mutedText,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 13),
            DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.84),
                borderRadius: BorderRadius.circular(17),
                border: Border.all(
                  color: AppColors.brand.withValues(alpha: 0.10),
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        displayCode,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontFamily: 'SF Mono',
                          fontSize: 20,
                          fontWeight: FontWeight.w900,
                          height: 1,
                          letterSpacing: 1.2,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    _FamilyCodeActionButton(
                      icon: Icons.content_copy_outlined,
                      label: '复制',
                      onTap: onCopy,
                    ),
                    if (canReset && onReset != null) ...[
                      const SizedBox(width: 7),
                      _FamilyCodeActionButton(
                        icon: Icons.refresh_outlined,
                        label: '重置',
                        danger: true,
                        onTap: onReset!,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 9),
            Text(
              canReset ? '重置只会让旧家庭号失效，不影响已加入成员。' : '只有家庭管理员可以重置家庭号。',
              style: _mutedText,
            ),
          ],
        ),
      ),
    );
  }
}

class _FamilyCodeActionButton extends StatelessWidget {
  const _FamilyCodeActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.danger = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final tone = danger ? AppColors.danger : AppColors.brand;
    return Material(
      color: tone.withValues(alpha: danger ? 0.08 : 0.10),
      borderRadius: BorderRadius.circular(AppRadii.full),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.full),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, color: tone, size: 15),
              const SizedBox(width: 4),
              Text(
                label,
                style: TextStyle(
                  color: tone,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                  height: 1,
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

class _FamilyInvitationsPanel extends StatelessWidget {
  const _FamilyInvitationsPanel({
    required this.invitations,
    required this.options,
    required this.canManage,
    required this.onResend,
    required this.onCancel,
  });

  final List<FamilyInvitation> invitations;
  final GuardianIdentityOptions? options;
  final bool canManage;
  final ValueChanged<FamilyInvitation> onResend;
  final ValueChanged<FamilyInvitation> onCancel;

  @override
  Widget build(BuildContext context) {
    return _FamilyPanel(
      title: '待接受邀请',
      subtitle: '对方接受后会加入家庭空间。',
      accent: AppColors.warning,
      child: Column(
        children: [
          for (var index = 0; index < invitations.length; index++) ...[
            _FamilyInvitationTile(
              invitation: invitations[index],
              roleLabel: _familyRoleLabel(
                options,
                invitations[index].role,
                invitations[index].roleLabel,
              ),
              canManage: canManage,
              onResend: () => onResend(invitations[index]),
              onCancel: () => onCancel(invitations[index]),
            ),
            if (index != invitations.length - 1) const _FamilyDivider(),
          ],
        ],
      ),
    );
  }
}

class _FamilyPanel extends StatelessWidget {
  const _FamilyPanel({
    required this.title,
    required this.subtitle,
    required this.child,
    this.accent = AppColors.brandSage,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.90),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AppColors.borderSoft),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF31445A).withValues(alpha: 0.045),
            blurRadius: 12,
            offset: const Offset(0, 7),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(15, 15, 15, 13),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: SizedBox(
                    width: 7,
                    height: 24,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: accent.withValues(alpha: 0.32),
                        borderRadius: BorderRadius.circular(99),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: _sectionTitleStyle),
                      const SizedBox(height: 3),
                      Text(
                        subtitle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: _mutedText,
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}

class _FamilyMemberTile extends StatelessWidget {
  const _FamilyMemberTile({
    required this.member,
    required this.title,
    required this.roleLabel,
    required this.isCurrentUser,
    required this.canManage,
    required this.onManage,
  });

  final FamilyMember member;
  final String title;
  final String roleLabel;
  final bool isCurrentUser;
  final bool canManage;
  final VoidCallback onManage;

  @override
  Widget build(BuildContext context) {
    final isAdmin = member.role == 'admin';
    final tone = isAdmin ? AppColors.brandSage : AppColors.brand;
    final fill = isAdmin ? AppColors.brandSageWash : AppColors.brandWash;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          _FamilyAvatar(
            icon: isAdmin
                ? Icons.admin_panel_settings_outlined
                : Icons.person_outline,
            tone: tone,
            fill: fill,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 15,
                          fontWeight: FontWeight.w900,
                          height: 1.18,
                          letterSpacing: 0,
                        ),
                      ),
                    ),
                    if (isCurrentUser) ...[
                      const SizedBox(width: 8),
                      const StatusChip(label: '本人', tone: StatusTone.success),
                    ],
                  ],
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 7,
                  runSpacing: 5,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _SoftTextBadge(label: roleLabel, tone: tone, fill: fill),
                    if (member.phone.isNotEmpty)
                      _SoftTextBadge(
                        label: _phoneMask(member.phone),
                        tone: AppColors.ink,
                        fill: AppColors.surfaceStrong,
                      ),
                  ],
                ),
              ],
            ),
          ),
          if (canManage && !isCurrentUser) ...[
            const SizedBox(width: 8),
            _MiniActionButton(label: '管理', onTap: onManage),
          ],
        ],
      ),
    );
  }
}

class _FamilyInvitationTile extends StatelessWidget {
  const _FamilyInvitationTile({
    required this.invitation,
    required this.roleLabel,
    required this.canManage,
    required this.onResend,
    required this.onCancel,
  });

  final FamilyInvitation invitation;
  final String roleLabel;
  final bool canManage;
  final VoidCallback onResend;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _FamilyAvatar(
            icon: Icons.mail_outline,
            tone: AppColors.warning,
            fill: AppColors.warningWash,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  invitation.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    height: 1.18,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 7,
                  runSpacing: 5,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    _SoftTextBadge(
                      label: roleLabel,
                      tone: AppColors.warning,
                      fill: AppColors.warningWash,
                    ),
                    _SoftTextBadge(
                      label: invitation.statusLabel,
                      tone: AppColors.ink,
                      fill: AppColors.surfaceStrong,
                    ),
                    if (invitation.phone.isNotEmpty)
                      Text(_phoneMask(invitation.phone), style: _mutedText),
                  ],
                ),
                if (canManage) ...[
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      _MiniActionButton(label: '重发邀请', onTap: onResend),
                      const SizedBox(width: 8),
                      _MiniActionButton(
                        label: '取消',
                        danger: true,
                        onTap: onCancel,
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FamilyEmptyPanel extends StatelessWidget {
  const _FamilyEmptyPanel({required this.canManage, required this.onAdd});

  final bool canManage;
  final VoidCallback? onAdd;

  @override
  Widget build(BuildContext context) {
    return AppStateView(
      variant: AppStateVariant.noData,
      title: '还没有家庭成员',
      message: canManage ? '邀请照护人后，可以一起处理任务确认和重要提醒。' : '管理员邀请成员后会显示在这里。',
      primaryActionLabel: canManage ? '邀请成员' : null,
      onPrimaryAction: onAdd,
      compact: true,
    );
  }
}

class _FamilyAvatar extends StatelessWidget {
  const _FamilyAvatar({
    required this.icon,
    required this.tone,
    required this.fill,
  });

  final IconData icon;
  final Color tone;
  final Color fill;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(15),
      ),
      child: SizedBox(
        width: 46,
        height: 46,
        child: Center(child: Icon(icon, color: tone, size: 21)),
      ),
    );
  }
}

class _SoftTextBadge extends StatelessWidget {
  const _SoftTextBadge({
    required this.label,
    required this.tone,
    required this.fill,
  });

  final String label;
  final Color tone;
  final Color fill;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        child: Text(
          label,
          style: TextStyle(
            color: tone,
            fontFamily: AppTypography.systemFont,
            fontSize: 11.5,
            fontWeight: FontWeight.w800,
            height: 1,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class _MiniActionButton extends StatelessWidget {
  const _MiniActionButton({
    required this.label,
    required this.onTap,
    this.danger = false,
  });

  final String label;
  final VoidCallback onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger ? AppColors.danger : AppColors.brandDeep;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: ConstrainedBox(
        constraints: const BoxConstraints(minHeight: 44, minWidth: 54),
        child: Align(
          alignment: Alignment.centerLeft,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: color.withValues(alpha: danger ? 0.10 : 0.09),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: color.withValues(alpha: 0.12)),
            ),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 8),
              child: Text(
                label,
                style: TextStyle(
                  color: color,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w900,
                  height: 1,
                  letterSpacing: 0,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _FamilyDivider extends StatelessWidget {
  const _FamilyDivider();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 58),
      child: Divider(
        height: 1,
        thickness: 1,
        color: AppColors.borderSoft.withValues(alpha: 0.80),
      ),
    );
  }
}

class ChildProfilePage extends ConsumerWidget {
  const ChildProfilePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final child = ref.watch(currentChildProvider);
    return child.when(
      data: (data) => data == null
          ? const _Page(
              title: '孩子资料',
              children: [
                AppStateView(
                  variant: AppStateVariant.noData,
                  title: '还没有孩子资料',
                  message: '请先完成首次设置，之后可以在这里维护资料。',
                  compact: true,
                ),
              ],
            )
          : _ChildProfileForm(child: data),
      loading: () => const _Page(
        title: '孩子资料',
        children: [_Loading(title: '正在同步孩子资料')],
      ),
      error: (error, _) => _Page(
        title: '孩子资料',
        children: [
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
  late ChildProfileEditorValue _value;
  var _saving = false;
  var _retryingPreparation = false;

  @override
  void initState() {
    super.initState();
    _draft = widget.child;
    final gradeOption =
        ChildGradeOption.fromCode(_draft.gradeCode) ??
        ChildGradeOption.fromLegacy(
          educationStage: _draft.educationStage,
          grade: _draft.grade,
        );
    _value = ChildProfileEditorValue(
      name: _draft.nickname.trim().isEmpty ? _draft.name : _draft.nickname,
      birthday: _draft.birthday,
      sleepTime: _draft.sleepTime.isEmpty ? '21:00' : _draft.sleepTime,
      gender: _draft.gender,
      stage: gradeOption?.stageLabel ?? _draft.educationStage,
      grade: gradeOption?.gradeLabel ?? _draft.grade,
      schoolName: _draft.schoolName,
      interestsText: _draft.interests.join('、'),
    );
  }

  @override
  Widget build(BuildContext context) {
    final account = ref.watch(accountProfileProvider).asData?.value;
    final canManageChildProfile = account?.can('manage_child_profile') ?? false;
    final gradeOption = ChildGradeOption.fromLegacy(
      educationStage: _value.normalizedStage,
      grade: _value.normalizedGrade,
    );
    final savedGradeOption =
        ChildGradeOption.fromCode(_draft.gradeCode) ??
        ChildGradeOption.fromLegacy(
          educationStage: _draft.educationStage,
          grade: _draft.grade,
        );
    final canSave = !_saving && gradeOption != null;
    final isSavedPrimary = savedGradeOption?.isPrimary == true;
    final preparation = isSavedPrimary && _draft.id.trim().isNotEmpty
        ? ref.watch(currentLearningPreparationProvider(_draft.id))
        : null;
    final availability = isSavedPrimary && _draft.id.trim().isNotEmpty
        ? ref.watch(currentLearningAvailabilityProvider(_draft.id))
        : null;
    final currentAvailability = availability?.asData?.value;
    final canLearnNow =
        currentAvailability?.gradeCode == savedGradeOption?.code &&
        currentAvailability?.canLearnNow == true;
    final canAccessWorkspace =
        currentAvailability?.gradeCode == savedGradeOption?.code &&
        currentAvailability?.canAccessWorkspace == true;
    final canCreateStudentAccess = canManageChildProfile && canAccessWorkspace;

    return AppScreen(
      title: '孩子资料',
      fixedHeader: true,
      reserveBottomNavigation: false,
      backLabel: '返回我的',
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoute.profile.path);
        }
      },
      footer: AppPrimaryButton(
        label: !canManageChildProfile
            ? '仅可查看'
            : _saving
            ? '保存中'
            : '保存资料',
        loading: _saving,
        onTap: canManageChildProfile && canSave ? _save : null,
      ),
      children: [
        AppSurface(
          radius: 22,
          padding: const EdgeInsets.fromLTRB(15, 16, 15, 15),
          child: AbsorbPointer(
            absorbing: !canManageChildProfile,
            child: Opacity(
              opacity: canManageChildProfile ? 1 : 0.76,
              child: ChildProfileEditorPanel(
                value: _value,
                includeExtendedFields: false,
                includeGender: false,
                includeBirthday: false,
                includeSleepTime: false,
                stageOptions: const ['幼儿园', '小学'],
                showStageSelector: true,
                recommendEducationFromBirthday: false,
                noteText: '称呼和就读阶段可随时修改；学习内容按你确认的年级匹配。',
                onChanged: (value) {
                  if (canManageChildProfile) setState(() => _value = value);
                },
              ),
            ),
          ),
        ),
        const SizedBox(height: 14),
        if (preparation != null &&
            availability?.hasValue == true &&
            !canLearnNow) ...[
          preparation.when(
            loading: () => const LearningPreparationLoadingCard(),
            error: (error, _) => LearningPreparationNetworkErrorCard(
              onRetry: () => _refreshPreparation(),
            ),
            data: (value) {
              if (value == null) {
                return LearningPreparationMissingCard(
                  onRefresh: () => _refreshPreparation(),
                );
              }
              return LearningPreparationCard(
                preparation: value,
                awaitingPublication: value.isReady,
                onRefresh: () => _refreshPreparation(),
                onRetry: value.canRetry ? () => _retryPreparation(value) : null,
                retrying: _retryingPreparation,
              );
            },
          ),
          const SizedBox(height: 14),
        ],
        AppSurface(
          key: const ValueKey('studentLearningSpaceEntry'),
          color: AppColors.brandWash.withValues(alpha: 0.62),
          borderColor: AppColors.brand.withValues(alpha: 0.10),
          radius: AppRadii.cardLarge,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
          child: AppListRow(
            icon: Icons.school_outlined,
            title: '学生学习空间',
            subtitle: savedGradeOption?.isPrimary != true
                ? '当前正式学习空间仅面向已开放年级'
                : !canManageChildProfile
                ? '仅家庭管理员可创建或更新学生登录方式'
                : availability?.isLoading == true
                ? '正在确认学习空间权限'
                : availability?.hasError == true
                ? '学习空间权限加载失败，请检查网络后重试'
                : !canAccessWorkspace
                ? '请确认已选择开放年级并完成设置'
                : '设置学习 PIN，生成 10 分钟有效的网页配对码',
            tone: AppListRowTone.blue,
            onTap: canCreateStudentAccess
                ? () => context.push(profileStudentAccessPath)
                : null,
          ),
        ),
      ],
    );
  }

  Future<void> _save() async {
    final name = _value.name.trim();
    final gradeOption = ChildGradeOption.fromLegacy(
      educationStage: _value.normalizedStage,
      grade: _value.normalizedGrade,
    );
    if (gradeOption == null) {
      _toast(context, '请选择孩子当前年级');
      return;
    }

    setState(() => _saving = true);
    final ageStage = _value.normalizedGrade.isEmpty
        ? _value.normalizedStage
        : '${_value.normalizedStage} ${_value.normalizedGrade}';
    final next = ChildProfile(
      id: _draft.id,
      name: name.isEmpty ? _draft.name : name,
      nickname: name.isEmpty ? _draft.nickname : name,
      gender: _draft.gender,
      birthday: _draft.birthday,
      sleepTime: _value.normalizedSleepTime,
      ageStage: ageStage,
      educationStage: _value.normalizedStage,
      grade: _value.normalizedGrade,
      gradeCode: gradeOption.code,
      educationStageCode: gradeOption.stageCode,
      contentMode: gradeOption.contentMode,
      schoolYearStartYear: gradeSchoolYearStartYear(),
      gradeConfirmedAt: _draft.gradeConfirmedAt,
      schoolName: _value.schoolName.trim(),
      interests: _value.interests,
      taskPreferences: _draft.taskPreferences,
    );
    try {
      final before = _normalizedPersistedGrade(_draft);
      final saved = await ref.read(profileRepositoryProvider).updateChild(next);
      final gradeChanged = before != _normalizedPersistedGrade(saved);
      _draft = saved;
      final savedGrade = ChildGradeOption.fromCode(saved.gradeCode);
      ref.invalidate(currentChildProvider);
      ref.invalidate(profileSummaryProvider);
      // Saving an unchanged grade can attach a newly available shared catalog.
      // Refresh its access gate even when the grade itself did not change.
      ref.invalidate(currentLearningAvailabilityProvider(_draft.id));
      if (gradeChanged && savedGrade?.isPrimary == true) {
        ref.invalidate(currentLearningPreparationProvider(_draft.id));
      }
      if (mounted) {
        final message = !gradeChanged
            ? '孩子资料已保存'
            : savedGrade?.isPrimary == true
            ? '年级已保存，课程将在后台准备'
            : '年级已保存';
        _toast(context, message);
      }
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _refreshPreparation() async {
    try {
      final _ = await ref.refresh(
        currentLearningPreparationProvider(_draft.id).future,
      );
    } catch (_) {
      // The provider remains in error and renders the explicit refresh action.
    }
    try {
      final _ = await ref.refresh(
        currentLearningAvailabilityProvider(_draft.id).future,
      );
    } catch (_) {
      // Keep the availability error visible next to the student-space entry.
    }
  }

  Future<void> _retryPreparation(LearningPreparation preparation) async {
    if (_retryingPreparation) return;
    setState(() => _retryingPreparation = true);
    final requestId =
        'parent-prep-retry:${preparation.id}:${DateTime.now().millisecondsSinceEpoch}';
    try {
      await ref
          .read(learningPreparationRepositoryProvider)
          .retry(planId: preparation.id, requestId: requestId);
      final _ = await ref.refresh(
        currentLearningPreparationProvider(_draft.id).future,
      );
      final _ = await ref.refresh(
        currentLearningAvailabilityProvider(_draft.id).future,
      );
    } catch (error) {
      var reconciled = false;
      try {
        final current = await ref.refresh(
          currentLearningPreparationProvider(_draft.id).future,
        );
        reconciled = current != null && current.id != preparation.id;
      } catch (_) {
        // Keep the original failure when current status cannot reconcile it.
      }
      if (mounted && !reconciled) {
        _toast(
          context,
          error is LearningPreparationException
              ? error.message
              : '课程重新准备失败，请稍后重试',
        );
      }
    } finally {
      if (mounted) setState(() => _retryingPreparation = false);
    }
  }
}

({String gradeCode, int? schoolYearStartYear}) _normalizedPersistedGrade(
  ChildProfile child,
) {
  final normalizedCode = child.gradeCode.trim();
  final grade =
      ChildGradeOption.fromCode(normalizedCode) ??
      ChildGradeOption.fromLegacy(
        educationStage: child.educationStage.trim(),
        grade: child.grade.trim(),
      );
  return (
    gradeCode: grade?.code ?? normalizedCode,
    schoolYearStartYear: child.schoolYearStartYear,
  );
}

class EmergencyContactsPage extends ConsumerWidget {
  const EmergencyContactsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final contacts = ref.watch(emergencyContactsProvider);
    final identityOptions = ref
        .watch(guardianIdentityOptionsProvider)
        .asData
        ?.value;
    final account = ref.watch(accountProfileProvider).asData?.value;
    final canManageContacts =
        account?.can('manage_emergency_contacts') ?? false;
    return _Page(
      title: '紧急联系人',
      subtitle: canManageContacts ? '维护重要情况通知对象' : '查看重要情况通知对象',
      trailing: canManageContacts
          ? AppIconButton(
              icon: Icons.add,
              label: '新增联系人',
              onTap: () => _editContact(context, ref),
            )
          : null,
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
                      subtitle: _contactSubtitle(identityOptions, contact),
                      tone: contact.defaultNotify
                          ? AppListRowTone.green
                          : AppListRowTone.neutral,
                      trailing: canManageContacts
                          ? TextButton(
                              style: _inlineTextButtonStyle(),
                              onPressed: () =>
                                  _editContact(context, ref, contact: contact),
                              child: const Text('编辑'),
                            )
                          : null,
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

class _SelectedDevicePanel extends StatelessWidget {
  const _SelectedDevicePanel({required this.device});

  final GuardianDevice? device;

  @override
  Widget build(BuildContext context) {
    if (device == null) {
      return const AppStateView(
        variant: AppStateVariant.deviceOffline,
        title: '还没有可用摄像头',
        message: '添加摄像头后，可以设置看护能力和作息提醒。',
        compact: true,
      );
    }
    return AppSurface(
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
                Text('当前看护设备', style: _darkSub),
                const SizedBox(height: 5),
                Text(device!.displayName, style: _darkTitle),
                const SizedBox(height: 5),
                Text(device!.displayLocation, style: _darkSub),
              ],
            ),
          ),
          StatusChip(
            label: device!.isDefault ? '默认' : '已选择',
            tone: StatusTone.success,
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
    final selected = ref.watch(selectedDeviceProvider);
    return _Page(
      title: '摄像头管理',
      subtitle: '摄像头、房间和默认设备',
      trailing: devices.maybeWhen<Widget?>(
        data: (items) => items.isEmpty
            ? null
            : IconButton(
                tooltip: '添加摄像头',
                onPressed: () => showAddCameraSheet(context),
                icon: const Icon(Icons.add_circle_outline),
              ),
        orElse: () => null,
      ),
      children: devices.when(
        data: (items) => [
          if (items.isEmpty)
            AppStateView(
              variant: AppStateVariant.deviceOffline,
              title: '还没有可用摄像头',
              message: '添加摄像头后，可以在这里查看状态和管理设备。',
              primaryActionLabel: '添加摄像头',
              onPrimaryAction: () => showAddCameraSheet(context),
              compact: true,
            )
          else
            selected.when(
              data: (selectedDevice) => AppSurface(
                child: Column(
                  children: [
                    for (var index = 0; index < items.length; index++) ...[
                      if (index > 0) const _CompactDivider(),
                      Builder(
                        builder: (context) {
                          final device = items[index];
                          return AppListRow(
                            icon: Icons.videocam_outlined,
                            title: device.displayName,
                            subtitle: _deviceListSubtitle(device),
                            tone: device.isOnlineLike
                                ? AppListRowTone.green
                                : AppListRowTone.neutral,
                            trailing: StatusChip(
                              label: _deviceListStatusLabel(
                                device,
                                selectedDevice?.id,
                              ),
                              tone: device.status == 'unbound'
                                  ? StatusTone.neutral
                                  : device.isOnlineLike
                                  ? StatusTone.success
                                  : StatusTone.danger,
                            ),
                            onTap: () => context.push(
                              '$profileDeviceDetailPath/${device.id}',
                            ),
                          );
                        },
                      ),
                    ],
                  ],
                ),
              ),
              loading: () => const _Loading(title: '正在同步摄像头'),
              error: (error, _) => _ErrorState(
                error: error,
                onRetry: () => ref.invalidate(selectedDeviceProvider),
              ),
            ),
        ],
        loading: () => const [_Loading(title: '正在同步摄像头')],
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

String _deviceListSubtitle(GuardianDevice device) {
  final location = device.displayLocation;
  if (device.isDefault) return '$location · 当前默认';
  if (device.status == 'unbound') return '$location · 已停止使用';
  return location;
}

String _deviceListStatusLabel(GuardianDevice device, String? selectedDeviceId) {
  final isCurrent = selectedDeviceId != null && selectedDeviceId == device.id;
  if (device.isDefault && isCurrent) return '默认 · 当前';
  if (device.isDefault) return '默认';
  if (isCurrent) return '当前';
  if (device.status == 'unbound') return '已解绑';
  return device.isOnlineLike ? '在线' : '离线';
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
    final canManage =
        ref.watch(accountProfileProvider).asData?.value.can('manage_devices') ??
        false;
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
              canManage: canManage,
              onSave: _save,
              onSetDefault: data.device.isDefault ? null : _setDefault,
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
      _refreshDeviceAndLiveCare(ref, deviceId: widget.deviceId);
      if (mounted) _toast(context, '设备信息已保存');
    } on DeviceException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _setDefault() async {
    try {
      await ref
          .read(deviceRepositoryProvider)
          .setDefaultDevice(widget.deviceId);
      await selectDevice(ref, widget.deviceId);
      _refreshDeviceAndLiveCare(ref, deviceId: widget.deviceId);
      if (mounted) _toast(context, '已设为默认设备');
    } on DeviceException catch (error) {
      if (mounted) _toast(context, error.message);
    }
  }

  Future<void> _unbind() async {
    final confirmed = await _confirm(
      context,
      title: '解绑设备',
      message: '解绑后将停止这台摄像头的远程看护和提醒，确认继续吗？',
      danger: true,
    );
    if (!confirmed) return;
    try {
      final wasSelected = ref.read(selectedDeviceIdProvider) == widget.deviceId;
      final wasDefault =
          ref
              .read(deviceOverviewProvider(widget.deviceId))
              .asData
              ?.value
              .device
              .isDefault ==
          true;
      final result = await ref
          .read(deviceRepositoryProvider)
          .unbindDevice(widget.deviceId);
      final fallback = result.defaultDevice;
      if (fallback != null && (wasSelected || wasDefault)) {
        await selectDevice(ref, fallback.id);
      } else if (wasSelected || fallback == null) {
        await ref
            .read(sharedPreferencesProvider)
            .remove(selectedDeviceIdPreferenceKey);
        ref.read(selectedDeviceIdProvider.notifier).state = null;
        ref.read(selectedDeviceChangeEpochProvider.notifier).state++;
      }
      _refreshDeviceAndLiveCare(ref, deviceId: widget.deviceId);
      if (mounted) context.pop();
    } on DeviceException catch (error) {
      if (mounted) _toast(context, error.message);
    }
  }
}

void _refreshDeviceAndLiveCare(WidgetRef ref, {String? deviceId}) {
  ref
    ..invalidate(devicesProvider)
    ..invalidate(selectedDeviceProvider)
    ..invalidate(primaryDeviceOverviewProvider)
    ..invalidate(primaryFirmwareStatusProvider)
    ..invalidate(profileSummaryProvider)
    ..invalidate(cameraHealthProvider)
    ..invalidate(cameraRuntimeProvider)
    ..invalidate(cameraStatusProvider)
    ..invalidate(cameraMonitorStatusProvider)
    ..invalidate(cameraSnapshotProvider)
    ..invalidate(cameraEventsProvider)
    ..invalidate(liveCareStatusProvider);
  if (deviceId != null && deviceId.isNotEmpty) {
    ref.invalidate(deviceOverviewProvider(deviceId));
  }
}

class _DeviceDetailBody extends StatelessWidget {
  const _DeviceDetailBody({
    required this.overview,
    required this.name,
    required this.location,
    required this.saving,
    required this.canManage,
    required this.onSave,
    required this.onSetDefault,
    required this.onUnbind,
  });

  final DeviceOverview overview;
  final TextEditingController name;
  final TextEditingController location;
  final bool saving;
  final bool canManage;
  final VoidCallback onSave;
  final VoidCallback? onSetDefault;
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
              _Input(label: '设备名称', controller: name, readOnly: !canManage),
              const SizedBox(height: 12),
              _Input(label: '房间位置', controller: location, readOnly: !canManage),
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
        if (canManage) ...[
          if (onSetDefault != null) ...[
            AppSecondaryButton(label: '设为默认设备', onTap: onSetDefault),
            const SizedBox(height: 10),
          ],
          AppPrimaryButton(
            label: saving ? '保存中' : '保存设备信息',
            onTap: saving ? null : onSave,
          ),
          const SizedBox(height: 10),
          AppDangerButton(
            label: '解绑设备',
            trailing: const Icon(Icons.power_settings_new_outlined, size: 18),
            onTap: onUnbind,
          ),
        ],
      ],
    );
  }
}

class AiCareRulesPage extends StatelessWidget {
  const AiCareRulesPage({super.key});

  @override
  Widget build(BuildContext context) => const _HubPage(
    title: 'AI 规则与提醒',
    sections: [
      _HubSection(
        title: '看护提醒',
        rows: [
          _HubRow(
            icon: Icons.volunteer_activism_outlined,
            title: '看护能力',
            subtitle: '坐姿、收纳、用餐和睡眠提醒',
            path: profileCareCapabilitiesPath,
            tone: AppListRowTone.green,
          ),
          _HubRow(
            icon: Icons.schedule_outlined,
            title: '作息时间',
            subtitle: '上学日和周末的提醒时间',
            path: profileRoutineWindowsPath,
            tone: AppListRowTone.amber,
          ),
          _HubRow(
            icon: Icons.notifications_outlined,
            title: '通知与提醒',
            subtitle: '家长通知和夜间免打扰',
            path: profileNotificationsPath,
          ),
        ],
      ),
      _HubSection(
        title: '边界',
        rows: [
          _HubRow(
            icon: Icons.record_voice_over_outlined,
            title: '语音与称呼',
            subtitle: '唤醒名、声线和聊天边界',
            path: profileConversationPath,
            tone: AppListRowTone.blue,
          ),
          _HubRow(
            icon: Icons.lock_outline,
            title: '隐私与授权',
            subtitle: '查看、播报和数据保留',
            path: profilePrivacyPath,
          ),
        ],
      ),
    ],
  );
}

class CareCapabilitiesPage extends ConsumerStatefulWidget {
  const CareCapabilitiesPage({super.key});

  @override
  ConsumerState<CareCapabilitiesPage> createState() =>
      _CareCapabilitiesPageState();
}

class _CareCapabilitiesPageState extends ConsumerState<CareCapabilitiesPage> {
  final Set<String> _savingKeys = <String>{};

  @override
  Widget build(BuildContext context) {
    final selectedDevice = ref.watch(selectedDeviceProvider);
    final child = ref.watch(currentChildProvider);
    final childId = child.asData?.value?.id;
    final device = selectedDevice.asData?.value;
    final query = CareCapabilitiesQuery(childId: childId, deviceId: device?.id);
    final canManage =
        ref
            .watch(profileSummaryProvider)
            .asData
            ?.value
            .can('manage_child_settings') ??
        false;
    final capabilities = ref.watch(careCapabilitiesProvider(query));

    return _Page(
      title: '看护能力',
      subtitle: '根据画面状态，在需要时轻声提醒。',
      children: [
        if (selectedDevice.isLoading)
          const _Loading(title: '正在同步当前摄像头')
        else if (device == null)
          const AppListRow(
            icon: Icons.videocam_off_outlined,
            title: '未连接摄像头',
            subtitle: '可以先保存提醒规则，连接后按这些设置提醒。',
            tone: AppListRowTone.neutral,
          )
        else
          _SelectedDevicePanel(device: device),
        const SizedBox(height: 14),
        ...capabilities.when(
          data: (items) => _capabilitySections(
            items,
            canManage: canManage,
            query: query,
            childId: childId,
            deviceId: device?.id,
          ),
          loading: () => const [_Loading(title: '正在同步看护能力')],
          error: (error, _) => [
            _ErrorState(
              error: error,
              onRetry: () => ref.invalidate(careCapabilitiesProvider(query)),
            ),
          ],
        ),
      ],
    );
  }

  List<Widget> _capabilitySections(
    List<CareCapability> items, {
    required bool canManage,
    required CareCapabilitiesQuery query,
    required String? childId,
    required String? deviceId,
  }) {
    if (items.isEmpty) {
      return const [
        AppStateView(
          variant: AppStateVariant.noData,
          title: '看护能力待同步',
          message: '请稍后刷新，或先确认孩子资料已完善。',
          compact: true,
        ),
      ];
    }
    final ordered = [...items]
      ..sort(
        (a, b) => _capabilityOrder(
          a.scenario,
        ).compareTo(_capabilityOrder(b.scenario)),
      );
    // V1 hides transition as a future composite scene, while keeping backend config
    // available for the later recognition phase.
    final visible = ordered
        .where((item) => _v1VisibleCareScenarios.contains(item.scenario))
        .toList();
    return [
      AppSurface(
        child: Column(
          children: [
            for (var index = 0; index < visible.length; index++) ...[
              if (index > 0) const _CompactDivider(),
              _CareCapabilityRow(
                capability: visible[index],
                savingEnabled: _savingKeys.contains(
                  '${visible[index].scenario}:enabled',
                ),
                savingVoice: _savingKeys.contains(
                  '${visible[index].scenario}:voice',
                ),
                savingRules: _savingKeys.contains(
                  '${visible[index].scenario}:rules',
                ),
                canManage: canManage,
                onEnabledChanged: (value) => _saveCapability(
                  query: query,
                  childId: childId,
                  deviceId: deviceId,
                  capability: visible[index],
                  key: 'enabled',
                  value: value,
                ),
                onVoiceChanged: (value) => _saveCapability(
                  query: query,
                  childId: childId,
                  deviceId: deviceId,
                  capability: visible[index],
                  key: 'allowSpeaker',
                  value: value,
                ),
                onOpenRules:
                    _careReminderRuleScenarios.contains(visible[index].scenario)
                    ? () => _openCareReminderRules(
                        query: query,
                        childId: childId,
                        deviceId: deviceId,
                        capability: visible[index],
                      )
                    : null,
              ),
            ],
          ],
        ),
      ),
      if (!canManage) ...[
        const SizedBox(height: 12),
        const AppListRow(
          icon: Icons.lock_outline,
          title: '当前为只读',
          subtitle: '看护能力由家庭管理员维护。',
          tone: AppListRowTone.neutral,
        ),
      ],
    ];
  }

  Future<void> _saveCapability({
    required CareCapabilitiesQuery query,
    required String? childId,
    required String? deviceId,
    required CareCapability capability,
    required String key,
    required bool value,
  }) async {
    await _saveCapabilityValues(
      query: query,
      childId: childId,
      deviceId: deviceId,
      capability: capability,
      savingKey:
          '${capability.scenario}:${key == 'allowSpeaker' ? 'voice' : key}',
      values: {key: value},
    );
  }

  Future<void> _saveCapabilityValues({
    required CareCapabilitiesQuery query,
    required String? childId,
    required String? deviceId,
    required CareCapability capability,
    required String savingKey,
    required Map<String, Object?> values,
  }) async {
    setState(() => _savingKeys.add(savingKey));
    try {
      await ref
          .read(careRepositoryProvider)
          .updateCapabilities(
            childId: childId,
            deviceId: deviceId,
            capabilities: [
              {'scenario': capability.scenario, ...values},
            ],
          );
      ref.invalidate(careCapabilitiesProvider(query));
      ref.invalidate(careSummaryProvider(childId));
      ref
        ..invalidate(cameraEventsProvider)
        ..invalidate(cameraMonitorStatusProvider)
        ..invalidate(liveCareStatusProvider);
      if (mounted) _toast(context, '已保存');
    } on CareException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _savingKeys.remove(savingKey));
    }
  }

  Future<void> _openCareReminderRules({
    required CareCapabilitiesQuery query,
    required String? childId,
    required String? deviceId,
    required CareCapability capability,
  }) async {
    final result = await _showCareReminderRulesSheet(context, capability);
    if (result == null) return;
    await _saveCapabilityValues(
      query: query,
      childId: childId,
      deviceId: deviceId,
      capability: capability,
      savingKey: '${capability.scenario}:rules',
      values: result,
    );
  }
}

class _CareCapabilityRow extends StatelessWidget {
  const _CareCapabilityRow({
    required this.capability,
    required this.savingEnabled,
    required this.savingVoice,
    required this.savingRules,
    required this.canManage,
    required this.onEnabledChanged,
    required this.onVoiceChanged,
    this.onOpenRules,
  });

  final CareCapability capability;
  final bool savingEnabled;
  final bool savingVoice;
  final bool savingRules;
  final bool canManage;
  final ValueChanged<bool> onEnabledChanged;
  final ValueChanged<bool> onVoiceChanged;
  final VoidCallback? onOpenRules;

  @override
  Widget build(BuildContext context) {
    final disabled = !canManage || savingEnabled || savingVoice || savingRules;
    final hasReminderRules = _careReminderRuleScenarios.contains(
      capability.scenario,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        children: [
          _SwitchRow(
            title: _capabilityTitle(capability.scenario),
            subtitle: savingEnabled
                ? '保存中'
                : _capabilityDescription(capability.scenario),
            value: capability.enabled,
            onChanged: disabled ? null : onEnabledChanged,
          ),
          _SwitchRow(
            title: '摄像头语音提醒',
            subtitle: savingVoice
                ? '保存中'
                : capability.allowSpeaker
                ? capability.scenario == 'toy_cleanup'
                      ? '孩子离开后轻声提醒。'
                      : '会在合适时间轻声提醒。'
                : '只记录给家长查看。',
            value: capability.allowSpeaker,
            onChanged: disabled || !capability.enabled ? null : onVoiceChanged,
          ),
          if (hasReminderRules) ...[
            AppListRow(
              icon: Icons.timer_outlined,
              title: '提醒方式',
              subtitle: savingRules
                  ? '保存中'
                  : _careReminderRuleSummary(capability),
              tone: AppListRowTone.amber,
              onTap: disabled || onOpenRules == null ? null : onOpenRules,
            ),
          ],
        ],
      ),
    );
  }
}

Future<Map<String, Object?>?> _showCareReminderRulesSheet(
  BuildContext context,
  CareCapability capability,
) {
  final isToyCleanup = capability.scenario == 'toy_cleanup';
  final isScreenUse = capability.scenario == 'screen_use';
  final hasObservationDelay = isToyCleanup || isScreenUse;
  var observationMinutes = _secondsToMinutes(
    capability.minObservationSeconds,
    min: 1,
  );
  final intervalMinutesFloor = isScreenUse
      ? _screenUseReminderIntervalMinutesMin
      : _defaultCareReminderIntervalMinutesMin;
  var intervalMinutes = _secondsToMinutes(
    capability.cooldownSeconds,
    min: intervalMinutesFloor,
  );
  var dailyLimit = capability.dailyLimit <= 0 ? 3 : capability.dailyLimit;

  return showAppBottomSheet<Map<String, Object?>>(
    context: context,
    maxHeightFactor: hasObservationDelay ? 0.64 : 0.56,
    child: StatefulBuilder(
      builder: (context, setSheetState) {
        return AppBottomSheetBody(
          title: _capabilityTitle(capability.scenario),
          subtitle: switch (capability.scenario) {
            'toy_cleanup' => '孩子玩完离开后，摄像头会轻声提醒收好玩具。',
            'screen_use' => '持续看屏达到设定时间后，摄像头会轻声提醒休息或拉开距离。',
            _ => '设置提醒间隔和今日最多次数，超过后改为通知家长。',
          },
          footer: AppPrimaryButton(
            label: '保存提醒方式',
            onTap: () => Navigator.of(context).pop({
              if (hasObservationDelay)
                'minObservationSeconds': observationMinutes * 60,
              'cooldownSeconds': intervalMinutes * 60,
              'dailyLimit': dailyLimit,
              'parentNotifyThreshold': dailyLimit,
            }),
          ),
          child: Column(
            children: [
              if (isToyCleanup) ...[
                _MinuteStepperRow(
                  title: '离开多久后提醒',
                  subtitle: '默认等一会儿，避免刚离开就打扰。',
                  value: observationMinutes,
                  min: 1,
                  max: 10,
                  step: 1,
                  enabled: true,
                  onChanged: (value) =>
                      setSheetState(() => observationMinutes = value),
                ),
                const _CompactDivider(),
              ],
              if (isScreenUse) ...[
                _MinuteStepperRow(
                  title: '持续观看多久后提醒',
                  subtitle: '默认稍等一会儿，避免刚拿起手机就打扰。',
                  value: observationMinutes,
                  min: 1,
                  max: 5,
                  step: 1,
                  enabled: true,
                  onChanged: (value) =>
                      setSheetState(() => observationMinutes = value),
                ),
                const _CompactDivider(),
              ],
              _MinuteStepperRow(
                title: '提醒间隔',
                subtitle: isScreenUse ? '看屏较敏感，可按需设较短间隔。' : '两次提醒之间留出安静时间。',
                value: intervalMinutes,
                min: intervalMinutesFloor,
                max: 60,
                step: isScreenUse ? _screenUseReminderIntervalMinutesMin : 5,
                enabled: true,
                onChanged: (value) =>
                    setSheetState(() => intervalMinutes = value),
              ),
              const _CompactDivider(),
              _MinuteStepperRow(
                title: '今日最多提醒',
                subtitle: '超过 $dailyLimit 次后改为通知家长。',
                value: dailyLimit,
                min: 1,
                max: 6,
                step: 1,
                suffix: '次',
                enabled: true,
                onChanged: (value) => setSheetState(() => dailyLimit = value),
              ),
            ],
          ),
        );
      },
    ),
  );
}

String _careReminderRuleSummary(CareCapability capability) {
  return switch (capability.scenario) {
    'toy_cleanup' => _toyCleanupRuleSummary(capability),
    'screen_use' => _screenUseRuleSummary(capability),
    _ => _genericCareReminderRuleSummary(capability),
  };
}

String _genericCareReminderRuleSummary(CareCapability capability) {
  final intervalMinutes = _secondsToMinutes(
    capability.cooldownSeconds,
    min: 10,
  );
  final dailyLimit = capability.dailyLimit <= 0 ? 3 : capability.dailyLimit;
  final threshold = capability.parentNotifyThreshold <= 0
      ? dailyLimit
      : capability.parentNotifyThreshold;
  return '间隔 $intervalMinutes 分钟 · 今日最多 $dailyLimit 次 · 超过后通知家长（$threshold 次）';
}

String _screenUseRuleSummary(CareCapability capability) {
  final sustainedMinutes = _secondsToMinutes(
    capability.minObservationSeconds,
    min: 1,
  );
  final intervalMinutes = _secondsToMinutes(
    capability.cooldownSeconds,
    min: _screenUseReminderIntervalMinutesMin,
  );
  final dailyLimit = capability.dailyLimit <= 0 ? 3 : capability.dailyLimit;
  final threshold = capability.parentNotifyThreshold <= 0
      ? dailyLimit
      : capability.parentNotifyThreshold;
  return '持续 $sustainedMinutes 分钟后提醒 · 间隔 $intervalMinutes 分钟 · 今日最多 $dailyLimit 次 · 超过后通知家长（$threshold 次）';
}

String _toyCleanupRuleSummary(CareCapability capability) {
  final leaveMinutes = _secondsToMinutes(
    capability.minObservationSeconds,
    min: 1,
  );
  final intervalMinutes = _secondsToMinutes(
    capability.cooldownSeconds,
    min: 10,
  );
  final dailyLimit = capability.dailyLimit <= 0 ? 3 : capability.dailyLimit;
  final threshold = capability.parentNotifyThreshold <= 0
      ? dailyLimit
      : capability.parentNotifyThreshold;
  return '离开 $leaveMinutes 分钟后提醒 · 间隔 $intervalMinutes 分钟 · 今日最多 $dailyLimit 次 · 超过后通知家长（$threshold 次）';
}

int _secondsToMinutes(int seconds, {required int min}) {
  if (seconds <= 0) return min;
  return math.max(min, (seconds / 60).ceil());
}

class RoutineWindowsPage extends ConsumerStatefulWidget {
  const RoutineWindowsPage({super.key});

  @override
  ConsumerState<RoutineWindowsPage> createState() => _RoutineWindowsPageState();
}

class _RoutineWindowsPageState extends ConsumerState<RoutineWindowsPage> {
  String _dayType = 'school_day';
  List<RoutineWindow>? _draft;
  String? _draftKey;
  var _saving = false;

  @override
  Widget build(BuildContext context) {
    final child = ref.watch(currentChildProvider);
    final childId = child.asData?.value?.id;
    final query = RoutineWindowsQuery(childId: childId, dayType: _dayType);
    final windows = ref.watch(routineWindowsProvider(query));
    final canManage =
        ref
            .watch(profileSummaryProvider)
            .asData
            ?.value
            .can('manage_child_settings') ??
        false;
    final canSaveRoutine = canManage && !_saving && windows.hasValue;

    return _Page(
      title: '作息节奏',
      subtitle: '设置大概时间段，摄像头会轻声提醒。',
      avoidFooterOverlap: true,
      footer: canManage
          ? AppPrimaryButton(
              label: _saving ? '保存中' : '保存作息',
              loading: _saving,
              onTap: canSaveRoutine ? () => _save(query) : null,
            )
          : null,
      children: [
        _DayTypeSelector(
          value: _dayType,
          onChanged: _saving
              ? null
              : (value) => setState(() {
                  _dayType = value;
                  _draft = null;
                  _draftKey = null;
                }),
        ),
        const SizedBox(height: 14),
        ...windows.when(
          data: (items) {
            final key = '${query.childId ?? ''}:${query.dayType}';
            if (_draftKey != key) {
              _draft = _routineDraft(
                items,
                childId: childId,
                dayType: _dayType,
              );
              _draftKey = key;
            }
            return [
              AppSurface(
                child: Column(
                  children: [
                    for (var index = 0; index < _draft!.length; index++) ...[
                      if (index > 0) const _CompactDivider(),
                      _RoutineWindowRow(
                        window: _draft![index],
                        canManage: canManage && !_saving,
                        onToggle: (value) => _updateWindow(
                          index,
                          _draft![index].copyWith(enabled: value),
                        ),
                        onEditStart: () => _pickTime(index, start: true),
                        onEditEnd: () => _pickTime(index, start: false),
                      ),
                    ],
                  ],
                ),
              ),
              if (!canManage) ...[
                const SizedBox(height: 12),
                const AppListRow(
                  icon: Icons.lock_outline,
                  title: '当前为只读',
                  subtitle: '作息时间由家庭管理员维护。',
                  tone: AppListRowTone.neutral,
                ),
              ],
            ];
          },
          loading: () => const [_Loading(title: '正在同步作息时间')],
          error: (error, _) => [
            _ErrorState(
              error: error,
              onRetry: () => ref.invalidate(routineWindowsProvider(query)),
            ),
          ],
        ),
      ],
    );
  }

  void _updateWindow(int index, RoutineWindow window) {
    final next = [...?_draft];
    next[index] = window;
    setState(() => _draft = next);
  }

  Future<void> _pickTime(int index, {required bool start}) async {
    final window = _draft?[index];
    if (window == null) return;
    final picked = await showAppTimePickerSheet(
      context: context,
      initialValue: start ? window.startTime : window.endTime,
      title: start ? '开始时间' : '结束时间',
      subtitle: _routineTitle(window.windowType),
    );
    if (picked == null || !mounted) return;
    _updateWindow(
      index,
      start
          ? window.copyWith(startTime: picked)
          : window.copyWith(endTime: picked),
    );
  }

  Future<void> _save(RoutineWindowsQuery query) async {
    final draft = _draft;
    if (draft == null) return;
    setState(() => _saving = true);
    try {
      final visibleDraft = draft
          .where((item) => _visibleRoutineWindowTypes.contains(item.windowType))
          .toList();
      await ref
          .read(careRepositoryProvider)
          .replaceRoutineWindows(
            childId: query.childId,
            dayType: query.dayType,
            windows: visibleDraft,
          );
      ref.invalidate(routineWindowsProvider(query));
      ref.invalidate(careSummaryProvider(query.childId));
      ref
        ..invalidate(cameraEventsProvider)
        ..invalidate(cameraMonitorStatusProvider)
        ..invalidate(liveCareStatusProvider);
      if (mounted) _toast(context, '作息时间已保存');
    } on CareException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }
}

class _DayTypeSelector extends StatelessWidget {
  const _DayTypeSelector({required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String>? onChanged;

  @override
  Widget build(BuildContext context) {
    return AppSegmentedControl<String>(
      value: value,
      semanticLabel: '作息类型',
      onChanged: onChanged,
      options: const [
        AppSegmentOption(value: 'school_day', label: '上学日'),
        AppSegmentOption(value: 'weekend', label: '周末'),
      ],
    );
  }
}

class _RoutineWindowRow extends StatelessWidget {
  const _RoutineWindowRow({
    required this.window,
    required this.canManage,
    required this.onToggle,
    required this.onEditStart,
    required this.onEditEnd,
  });

  final RoutineWindow window;
  final bool canManage;
  final ValueChanged<bool> onToggle;
  final VoidCallback onEditStart;
  final VoidCallback onEditEnd;

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
                Text(_routineTitle(window.windowType), style: _rowTitle),
                const SizedBox(height: 4),
                Text(_routineSubtitle(window.windowType), style: _mutedText),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    _TimeChip(
                      label: window.startTime,
                      enabled: canManage,
                      onTap: onEditStart,
                    ),
                    _TimeChip(
                      label: window.endTime,
                      enabled: canManage,
                      onTap: onEditEnd,
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          AppCompactToggle(
            value: window.enabled,
            onChanged: canManage ? onToggle : null,
            label: _routineTitle(window.windowType),
          ),
        ],
      ),
    );
  }
}

class _TimeChip extends StatelessWidget {
  const _TimeChip({
    required this.label,
    required this.enabled,
    required this.onTap,
  });

  final String label;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: enabled ? onTap : null,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.surfaceStrong,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: AppColors.borderSoft),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Text(
            label,
            style: TextStyle(
              color: enabled ? AppColors.ink : AppColors.disabledInk,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

List<RoutineWindow> _routineDraft(
  List<RoutineWindow> items, {
  required String? childId,
  required String dayType,
}) {
  final byType = {for (final item in items) item.windowType: item};
  return [
    for (final type in _routineWindowOrder)
      byType[type] ??
          RoutineWindow(
            id: '',
            childId: childId ?? '',
            dayType: dayType,
            windowType: type,
            startTime: _defaultRoutineTime(type).$1,
            endTime: _defaultRoutineTime(type).$2,
            enabled: true,
            timezone: 'Asia/Shanghai',
          ),
  ];
}

const _routineWindowOrder = [
  'wake_up',
  'breakfast',
  'lunch',
  'nap',
  'dinner',
  'bedtime',
];

const _visibleRoutineWindowTypes = {
  'wake_up',
  'breakfast',
  'lunch',
  'nap',
  'dinner',
  'bedtime',
};

(String, String) _defaultRoutineTime(String type) {
  return switch (type) {
    'wake_up' => ('07:00', '07:40'),
    'breakfast' => ('07:30', '08:10'),
    'lunch' => ('11:40', '12:30'),
    'nap' => ('12:40', '14:20'),
    'dinner' => ('18:00', '19:00'),
    'bedtime' => ('20:30', '21:20'),
    _ => ('19:00', '20:00'),
  };
}

String _routineTitle(String type) {
  return switch (type) {
    'wake_up' => '起床',
    'breakfast' => '早餐',
    'lunch' => '午餐',
    'nap' => '午睡',
    'dinner' => '晚餐',
    'bedtime' => '晚上睡觉',
    _ => '作息时间',
  };
}

String _routineSubtitle(String type) {
  return switch (type) {
    'wake_up' => '温和唤醒，不催促。',
    'breakfast' => '准备开始一天。',
    'lunch' => '按午餐节奏轻提醒。',
    'nap' => '午睡前后更安静。',
    'dinner' => '晚餐时保持坐好慢慢吃。',
    'bedtime' => '睡前提醒会更轻。',
    _ => '按时间段轻声提醒。',
  };
}

const _v1VisibleCareScenarios = {
  'posture',
  'toy_cleanup',
  'meal_habit',
  'screen_use',
};

const _careReminderRuleScenarios = {'toy_cleanup', 'screen_use'};

/// 屏幕使用提醒允许更短间隔，便于家长对看屏行为密集提醒。
const _screenUseReminderIntervalMinutesMin = 1;
const _defaultCareReminderIntervalMinutesMin = 10;

int _capabilityOrder(String scenario) {
  return switch (scenario) {
    'posture' => 0,
    'toy_cleanup' => 1,
    'meal_habit' => 2,
    'screen_use' => 3,
    'transition' => 4,
    _ => 99,
  };
}

String _capabilityTitle(String scenario) {
  return switch (scenario) {
    'posture' => '坐姿提醒',
    'toy_cleanup' => '玩具收纳与安全',
    'meal_habit' => '用餐习惯提醒',
    'screen_use' => '屏幕使用提醒',
    'meal_start' => '用餐开始提醒',
    'nap_time' => '午睡提醒',
    'bedtime' => '晚上入睡提醒',
    'wake_up' => '起床提醒',
    'transition' => '转场提醒',
    _ => '看护提醒',
  };
}

String _capabilityDescription(String scenario) {
  return switch (scenario) {
    'posture' => '低头、趴桌或靠太近时，轻声提醒孩子调整。',
    'toy_cleanup' => '玩完离开、玩具散落或玩法需要留意时提醒。',
    'meal_habit' => '只在早餐、午餐、晚餐时间内，看到离座、分心或边吃边玩时提醒。',
    'screen_use' => '长时间玩手机、看屏幕太近或用眼距离需要留意时提醒。',
    'meal_start' => '到用餐时间，提醒坐好开始吃饭。',
    'nap_time' => '到午睡时间，摄像头会按作息轻声提醒。',
    'bedtime' => '到睡觉时间，摄像头会提醒孩子准备休息。',
    'wake_up' => '到起床时间，摄像头会轻声提醒。',
    'transition' => '准备出门、洗漱等换场景提醒。',
    _ => '按时间段轻声提醒。',
  };
}

class NotificationSettingsPage extends StatelessWidget {
  const NotificationSettingsPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '通知与提醒',
    settingKey: 'notifications',
    rows: [
      _SettingRowSpec('taskReminder', '作息提醒', '到点前提醒家长和摄像头。'),
      _SettingRowSpec('parentActionReminder', '待确认事项', '需要家长判断时集中提醒。'),
      _SettingRowSpec('taskEndReminder', '完成提醒', '孩子完成后提醒家长查看。'),
      _SettingRowSpec('deviceOfflineReminder', '设备离线提醒', '设备离线时通知家长。'),
      _SettingRowSpec('pointsRewardReminder', '积分奖励提醒', '积分发放和奖励兑现时提醒。'),
      _SettingRowSpec('dailySummary', '日报摘要', '每天一次汇总，不打扰工作时间。'),
      _SettingRowSpec('quietHoursEnabled', '夜间免打扰', '夜间只保留晨起闹铃和家长主动通话。'),
    ],
  );
}

class PrivacyPermissionsPage extends StatelessWidget {
  const PrivacyPermissionsPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '隐私与数据',
    settingKey: 'privacy',
    rows: [
      _SettingRowSpec(
        'cameraCollectionAuthorized',
        '画面看护授权',
        '允许设备在看护开启时分析必要画面。',
      ),
      _SettingRowSpec('voiceBroadcastAuthorized', '语音播报授权', '允许设备进行看护提醒和温和提示。'),
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

class ConversationRulesPage extends ConsumerStatefulWidget {
  const ConversationRulesPage({super.key});

  @override
  ConsumerState<ConversationRulesPage> createState() =>
      _ConversationRulesPageState();
}

class _ConversationRulesPageState extends ConsumerState<ConversationRulesPage> {
  final _wakeName = TextEditingController();
  Map<String, dynamic>? _draft;
  var _saving = false;

  @override
  void dispose() {
    _wakeName.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final setting = ref.watch(profileSettingProvider('conversation'));
    final settingData = setting.asData?.value;
    if (_draft == null && settingData != null) {
      _initializeDraft(settingData.value);
    }
    final child = ref.watch(currentChildProvider).asData?.value;
    final sleepTime = child?.sleepTime.trim().isNotEmpty == true
        ? child!.sleepTime
        : '21:00';
    final canManageSetting =
        ref
            .watch(profileSummaryProvider)
            .asData
            ?.value
            .can('manage_child_settings') ??
        false;
    final canSave = canManageSetting && !_saving && _draft != null;
    return _Page(
      title: '语音与称呼',
      footer: canManageSetting
          ? AppPrimaryButton(
              label: _saving ? '保存中' : '保存设置',
              loading: _saving,
              onTap: canSave ? _save : null,
            )
          : null,
      children: setting.when(
        data: (data) {
          _initializeDraft(data.value);
          final draft = _draft!;
          final boundaryLevel = _textValue(draft['boundaryLevel'], 'balanced');
          final boundary = _conversationBoundaryPlan(boundaryLevel);
          final singleMinutes = _intValue(
            draft['freeChatSingleMinutes'],
            boundary.singleMinutes,
            min: 3,
            max: 30,
          );
          final dailyMinutes = _intValue(
            draft['freeChatDailyMinutes'],
            boundary.dailyMinutes,
            min: singleMinutes,
            max: 120,
          );
          return [
            AppSurface(
              child: Column(
                children: [
                  _Input(
                    label: '摄像头唤醒名',
                    controller: _wakeName,
                    readOnly: !canManageSetting,
                  ),
                  const SizedBox(height: 8),
                  const Text('请让孩子说：小暖小暖，或小暖你好。', style: _mutedText),
                  const SizedBox(height: 12),
                  ref
                      .watch(voiceRuntimeProvider)
                      .when(
                        data: (runtime) => AppListRow(
                          icon: Icons.mic_none_outlined,
                          title: '语音服务状态',
                          subtitle: _voiceRuntimeStatusText(runtime),
                          tone: _profileMap(runtime['voice'])['running'] == true
                              ? AppListRowTone.green
                              : AppListRowTone.neutral,
                        ),
                        loading: () => const AppListRow(
                          icon: Icons.mic_none_outlined,
                          title: '语音服务状态',
                          subtitle: '正在查询…',
                          tone: AppListRowTone.neutral,
                        ),
                        error: (_, _) => const AppListRow(
                          icon: Icons.mic_none_outlined,
                          title: '语音服务状态',
                          subtitle: '暂时无法连接语音服务',
                          tone: AppListRowTone.neutral,
                        ),
                      ),
                  const SizedBox(height: 12),
                  const _FixedSettingOption(
                    icon: Icons.record_voice_over_outlined,
                    label: '原创声线',
                    value: _defaultConversationVoiceStyle,
                    badge: '默认',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            AppSurface(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('边界方案', style: _rowTitle),
                            SizedBox(height: 4),
                            Text('控制自由聊天时长和继续提醒节奏。', style: _mutedText),
                          ],
                        ),
                      ),
                      _SoftTextBadge(
                        label: boundary.label,
                        tone: AppColors.brand,
                        fill: AppColors.brandWash,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(boundary.description, style: _mutedText),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      for (final option in _conversationBoundaryPlans) ...[
                        Expanded(
                          child: _BoundaryChoiceButton(
                            label: option.label,
                            selected: option.key == boundary.key,
                            onTap: canManageSetting
                                ? () => setState(() {
                                    draft['boundaryLevel'] = option.key;
                                    draft['freeChatSingleMinutes'] =
                                        option.singleMinutes;
                                    draft['freeChatDailyMinutes'] =
                                        option.dailyMinutes;
                                  })
                                : null,
                          ),
                        ),
                        if (option != _conversationBoundaryPlans.last)
                          const SizedBox(width: 8),
                      ],
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            AppSurface(
              child: Column(
                children: [
                  _SwitchRow(
                    title: '自由聊天',
                    subtitle: '开启后按下面的单次和每日时长控制。',
                    value: draft['freeChatEnabled'] == true,
                    onChanged: canManageSetting
                        ? (value) =>
                              setState(() => draft['freeChatEnabled'] = value)
                        : null,
                  ),
                  _MinuteStepperRow(
                    title: '单次自由聊天',
                    subtitle: '到时后设备会温和收束话题。',
                    value: singleMinutes,
                    min: 3,
                    max: 30,
                    step: 1,
                    enabled:
                        canManageSetting && draft['freeChatEnabled'] == true,
                    onChanged: (value) => setState(() {
                      draft['freeChatSingleMinutes'] = value;
                      if (_intValue(
                            draft['freeChatDailyMinutes'],
                            dailyMinutes,
                            min: 3,
                            max: 120,
                          ) <
                          value) {
                        draft['freeChatDailyMinutes'] = value;
                      }
                    }),
                  ),
                  _MinuteStepperRow(
                    title: '每日自由聊天',
                    subtitle: '用于控制一天内的主动陪聊总量。',
                    value: dailyMinutes,
                    min: singleMinutes,
                    max: 120,
                    step: 5,
                    enabled:
                        canManageSetting && draft['freeChatEnabled'] == true,
                    onChanged: (value) =>
                        setState(() => draft['freeChatDailyMinutes'] = value),
                  ),
                  _SwitchRow(
                    title: '专注时间限制',
                    subtitle: '专注时间只保留当前事情相关问答和温和提示。',
                    value: draft['homeworkModeRestricted'] == true,
                    onChanged: canManageSetting
                        ? (value) => setState(
                            () => draft['homeworkModeRestricted'] = value,
                          )
                        : null,
                  ),
                  _SwitchRow(
                    title: '睡前不主动聊天',
                    subtitle: '$sleepTime 后不主动开启长时间自由聊天，时间在孩子资料里维护。',
                    value: draft['bedtimeQuietEnabled'] == true,
                    onChanged: canManageSetting
                        ? (value) => setState(
                            () => draft['bedtimeQuietEnabled'] = value,
                          )
                        : null,
                  ),
                ],
              ),
            ),
            if (!canManageSetting) ...[
              const SizedBox(height: 12),
              const AppListRow(
                icon: Icons.lock_outline,
                title: '当前为只读',
                subtitle: '查看者不能修改孩子看护设置。',
                tone: AppListRowTone.neutral,
              ),
            ],
          ];
        },
        loading: () => const [_Loading(title: '正在同步设置')],
        error: (error, _) => [
          _ErrorState(
            error: error,
            onRetry: () =>
                ref.invalidate(profileSettingProvider('conversation')),
          ),
        ],
      ),
    );
  }

  void _initializeDraft(Map<String, dynamic> value) {
    if (_draft != null) return;
    _draft = Map<String, dynamic>.from(value);
    _wakeName.text = _textValue(_draft!['wakeName'], '小暖');
    final boundary = _conversationBoundaryPlan(
      _textValue(_draft!['boundaryLevel'], 'balanced'),
    );
    _draft!.putIfAbsent('freeChatSingleMinutes', () => boundary.singleMinutes);
    _draft!.putIfAbsent('freeChatDailyMinutes', () => boundary.dailyMinutes);
    _draft!['voiceStyle'] = _defaultConversationVoiceStyle;
  }

  Future<void> _save() async {
    final value = _draft;
    if (value == null) return;
    final nextValue = Map<String, dynamic>.from(value)
      ..['wakeName'] = _wakeName.text.trim().isEmpty
          ? '小暖'
          : _wakeName.text.trim()
      ..['voiceStyle'] = _defaultConversationVoiceStyle;
    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .updateSetting('conversation', nextValue);
      ref.invalidate(profileSettingProvider('conversation'));
      ref.invalidate(voiceRuntimeProvider);
      if (!mounted) return;
      try {
        final policy = await ref
            .read(profileRepositoryProvider)
            .conversationPolicy();
        if (!mounted) return;
        final wakeName = _profileMap(policy['interactionProfile'])['wakeName'];
        _toast(
          context,
          wakeName == null || '$wakeName'.isEmpty
              ? '设置已保存'
              : '设置已保存，唤醒名已同步：$wakeName',
        );
      } on ProfileException {
        if (mounted) _toast(context, '设置已保存');
      }
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _voiceRuntimeStatusText(Map<String, dynamic> runtime) {
    final voice = _profileMap(runtime['voice']);
    final wakeName = '${voice['wakeName'] ?? _wakeName.text.trim()}'.trim();
    final running = voice['running'] == true;
    final state = '${voice['state'] ?? 'idle'}';
    if (!running) {
      return wakeName.isEmpty ? '语音服务未启动' : '已保存：$wakeName · 语音服务未启动';
    }
    if (state == 'listening') {
      return '已同步：$wakeName · 正在监听';
    }
    if (state == 'wake_detected') {
      return '已同步：$wakeName · 刚刚被唤醒';
    }
    if (state == 'speaking') {
      return '已同步：$wakeName · 正在回复';
    }
    return wakeName.isEmpty ? '语音服务已连接' : '已同步：$wakeName';
  }
}

String _textValue(Object? value, String fallback) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

int _intValue(
  Object? value,
  int fallback, {
  required int min,
  required int max,
}) {
  final parsed = switch (value) {
    int number => number,
    num number => number.toInt(),
    String text => int.tryParse(text.trim()),
    _ => null,
  };
  return (parsed ?? fallback).clamp(min, max).toInt();
}

const _defaultConversationVoiceStyle = '温柔女声，语速偏慢';

class EducationContentPage extends StatelessWidget {
  const EducationContentPage({super.key});

  @override
  Widget build(BuildContext context) => const _BooleanSettingsPage(
    title: '学习内容',
    settingKey: 'education',
    rows: [
      _SettingRowSpec('schoolbagEnabled', '小书包提醒', '按课程表和家长设置准备物品。'),
      _SettingRowSpec('courseScheduleEnabled', '课程表', '用于辅助生成准备提醒。'),
      _SettingRowSpec('teacherNoticeEnabled', '老师通知材料', '把老师通知和临时活动转成准备清单。'),
      _SettingRowSpec('ageTemplateEnabled', '按学段推荐', '根据生日、学段和年级推荐合适任务模板。'),
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
    final settingData = setting.asData?.value;
    _draft ??= settingData == null
        ? null
        : Map<String, dynamic>.from(settingData.value);
    final requiredCapability = widget.settingKey == 'privacy'
        ? 'manage_privacy'
        : 'manage_child_settings';
    final canManageSetting =
        ref
            .watch(profileSummaryProvider)
            .asData
            ?.value
            .can(requiredCapability) ??
        false;
    final canSave = canManageSetting && !_saving && _draft != null;
    return _Page(
      title: widget.title,
      footer: canManageSetting
          ? AppPrimaryButton(
              label: _saving ? '保存中' : '保存设置',
              loading: _saving,
              onTap: canSave ? _save : null,
            )
          : null,
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
                      onChanged: canManageSetting
                          ? (value) => setState(() => _draft![row.key] = value)
                          : null,
                    ),
                ],
              ),
            ),
            if (!canManageSetting) ...[
              const SizedBox(height: 12),
              AppListRow(
                icon: Icons.lock_outline,
                title: '当前为只读',
                subtitle: widget.settingKey == 'privacy'
                    ? '隐私授权由家庭管理员维护。'
                    : '查看者不能修改孩子看护设置。',
                tone: AppListRowTone.neutral,
              ),
            ],
            if (widget.extraLegalLink) ...[
              const SizedBox(height: 14),
              AppSecondaryButton(
                label: '儿童隐私授权说明',
                trailing: const Icon(Icons.description_outlined, size: 18),
                onTap: () => context.push(profileChildPrivacyPath),
              ),
            ],
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
    final firmware = ref.watch(primaryFirmwareStatusProvider);
    return _Page(
      title: '关于我们',
      subtitle: '应用版本、设备升级和产品原则。',
      children: about.when(
        data: (data) => [
          _AboutHero(data: data),
          const SizedBox(height: 14),
          const _SectionTitle('应用信息'),
          const SizedBox(height: 10),
          AppSurface(
            child: Column(
              children: [
                AppListRow(
                  icon: Icons.feedback_outlined,
                  title: '帮助与反馈',
                  subtitle: '问题、建议和误判样例',
                  tone: AppListRowTone.green,
                  onTap: () => context.push(profileFeedbackPath),
                ),
                AppListRow(
                  icon: Icons.system_update_alt_outlined,
                  title: '当前版本',
                  subtitle: _aboutVersionText(data),
                  tone: AppListRowTone.blue,
                  trailing: _InlineAction(label: '检查更新'),
                  onTap: () {
                    ref.invalidate(aboutInfoProvider);
                    _toast(
                      context,
                      data.appUpdate.updateAvailable
                          ? '发现新版本 ${data.appUpdate.latestVersion}'
                          : '当前已是最新版本',
                    );
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          const _SectionTitle('设备与升级'),
          const SizedBox(height: 10),
          _AboutFirmwareSection(firmware: firmware),
          const SizedBox(height: 16),
          const _SectionTitle('产品原则'),
          const SizedBox(height: 10),
          _AboutPrinciples(principles: data.principles),
          const SizedBox(height: 16),
          const _SectionTitle('法律与隐私'),
          const SizedBox(height: 10),
          AppSurface(
            child: Column(
              children: [
                AppListRow(
                  icon: Icons.lock_outline,
                  title: '隐私政策',
                  subtitle: '儿童数据、权限和删除说明',
                  onTap: () => context.push(privacyPolicyPath),
                ),
                AppListRow(
                  icon: Icons.description_outlined,
                  title: '服务协议',
                  subtitle: '服务条款和家庭使用边界',
                  onTap: () => context.push(userAgreementPath),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          Center(child: Text('© 2026 暖瞳 WarmSight', style: _mutedText)),
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

class _AboutHero extends StatelessWidget {
  const _AboutHero({required this.data});

  final AboutInfo data;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const _BrandLogoTile(),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      data.appName.isNotEmpty ? data.appName : data.displayName,
                      style: _darkTitle,
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'WarmSight · 陪在成长的每一天',
                      style: TextStyle(
                        color: Color(0xCCFFFFFF),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        height: 1.2,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(data.description, style: _darkSub),
        ],
      ),
    );
  }
}

class _AboutFirmwareSection extends StatelessWidget {
  const _AboutFirmwareSection({required this.firmware});

  final AsyncValue<DeviceFirmwareStatus?> firmware;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      child: firmware.when(
        data: (status) {
          if (status == null) {
            return Column(
              children: [
                AppListRow(
                  icon: Icons.memory_outlined,
                  title: '设备固件',
                  subtitle: '绑定摄像头后，这里会显示固件版本和升级状态。',
                  onTap: () => context.push(profileDevicesPath),
                ),
                const AppListRow(
                  icon: Icons.published_with_changes_outlined,
                  title: 'OTA 升级',
                  subtitle: '后续用于固件包、灰度发布和设备回执追踪。',
                  tone: AppListRowTone.amber,
                ),
              ],
            );
          }
          return Column(
            children: [
              AppListRow(
                icon: Icons.memory_outlined,
                title: '设备固件',
                subtitle: status.versionLine,
                tone: status.updateAvailable
                    ? AppListRowTone.amber
                    : AppListRowTone.green,
                trailing: StatusChip(
                  label: status.statusLabel,
                  tone: status.tone,
                ),
                onTap: () => context.push(
                  '$profileDeviceDetailPath/${status.device.id}',
                ),
              ),
              AppListRow(
                icon: Icons.published_with_changes_outlined,
                title: 'OTA 升级',
                subtitle: _firmwareOtaSubtitle(status),
                tone: AppListRowTone.blue,
                onTap: () => context.push(
                  '$profileDeviceDetailPath/${status.device.id}',
                ),
              ),
            ],
          );
        },
        loading: () => const _Loading(title: '正在同步设备升级状态'),
        error: (error, _) => AppStateView(
          variant: AppStateVariant.serviceUnavailable,
          title: '设备升级状态暂时不可用',
          message: error is DeviceException ? error.message : '请稍后重试。',
          compact: true,
        ),
      ),
    );
  }
}

class _AboutPrinciples extends StatelessWidget {
  const _AboutPrinciples({required this.principles});

  final List<String> principles;

  @override
  Widget build(BuildContext context) {
    final items = principles.isEmpty
        ? const ['儿童隐私优先', '温和提醒，不过度打扰']
        : principles;
    final icons = [
      Icons.verified_user_outlined,
      Icons.favorite_border,
      Icons.family_restroom_outlined,
    ];
    return AppSurface(
      child: Column(
        children: [
          for (var index = 0; index < items.length; index++)
            AppListRow(
              icon: icons[index % icons.length],
              title: items[index],
              subtitle: index == 0
                  ? '最小必要采集、监护人授权、可撤回。'
                  : index == 1
                  ? '提醒保持克制，关键决定交给家长。'
                  : '围绕真实家庭生活，而不是制造打扰。',
              tone: index == 0 ? AppListRowTone.green : AppListRowTone.amber,
            ),
        ],
      ),
    );
  }
}

String _aboutVersionText(AboutInfo data) {
  final version = data.version.isNotEmpty ? data.version : '待同步';
  final parts = <String>[
    'v$version',
    if (data.build.isNotEmpty) data.build,
    data.appUpdate.statusLabel,
  ];
  return parts.join(' · ');
}

String _firmwareOtaSubtitle(DeviceFirmwareStatus status) {
  final job = status.lastJob;
  if (job != null) return '${status.device.displayName} · ${job.statusLabel}';
  if (status.updateAvailable && status.latestPackage != null) {
    return '${status.device.displayName} · ${status.latestPackage!.notes}';
  }
  return '${status.device.displayName} · 等待固件包和设备回执';
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
    final canManageSubscription =
        ref
            .watch(profileSummaryProvider)
            .asData
            ?.value
            .can('manage_subscription') ??
        false;
    return _subscriptionScreen(
      subscription,
      plans,
      entitlements,
      canManageSubscription,
    );
  }

  Widget _subscriptionScreen(
    AsyncValue<SubscriptionStatus> subscription,
    AsyncValue<List<SubscriptionPlan>> plans,
    AsyncValue<List<SubscriptionFeatureComparison>> entitlements,
    bool canManageSubscription,
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
      canManageSubscription: canManageSubscription,
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
    final canManageSubscription =
        ref
            .read(profileSummaryProvider)
            .asData
            ?.value
            .can('manage_subscription') ??
        false;
    if (!canManageSubscription) {
      await _showSubscriptionResult(
        context,
        title: plan.title,
        message: '当前身份不能开通或变更套餐，请联系家庭管理员。',
      );
      return;
    }
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
    final canManageSubscription =
        ref
            .read(profileSummaryProvider)
            .asData
            ?.value
            .can('manage_subscription') ??
        false;
    if (!canManageSubscription) {
      await _showSubscriptionResult(
        context,
        title: '恢复购买',
        message: '当前身份不能恢复购买，请联系家庭管理员。',
      );
      return;
    }
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
    required this.canManageSubscription,
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
  final bool canManageSubscription;
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
      value: AppSystemUi.dark(),
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
                        '长期报告、趋势洞察和更细的看护提醒，帮你少盯屏幕，多看重点。',
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
                    canManageSubscription: canManageSubscription,
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
                canManageSubscription: canManageSubscription,
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
    required this.canManageSubscription,
    required this.onRestore,
    required this.onUserAgreement,
    required this.onPrivacyPolicy,
    required this.onChildPrivacy,
  });

  final bool restoring;
  final bool canManageSubscription;
  final VoidCallback onRestore;
  final VoidCallback onUserAgreement;
  final VoidCallback onPrivacyPolicy;
  final VoidCallback onChildPrivacy;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TextButton(
          style: _inlineTextButtonStyle(),
          onPressed: restoring || !canManageSubscription ? null : onRestore,
          child: Text(
            restoring
                ? '恢复中'
                : canManageSubscription
                ? '恢复购买'
                : '仅管理员可恢复购买',
            style: _paywallLinkText,
          ),
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
    required this.canManageSubscription,
    required this.onCheckout,
  });

  final double safeBottom;
  final SubscriptionPlan plan;
  final bool active;
  final bool loading;
  final bool canManageSubscription;
  final VoidCallback onCheckout;

  @override
  Widget build(BuildContext context) {
    final enabled = !active && !loading && canManageSubscription;
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
              label: active
                  ? '当前套餐'
                  : canManageSubscription
                  ? plan.ctaLabel
                  : '当前身份不可开通',
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: enabled ? onCheckout : null,
                child: AnimatedContainer(
                  duration: AppMotion.duration(context, 190),
                  curve: Curves.easeOutCubic,
                  height: 54,
                  decoration: BoxDecoration(
                    color: active || !canManageSubscription
                        ? Colors.white.withValues(alpha: 0.16)
                        : const Color(0xFFB8F2CF),
                    borderRadius: BorderRadius.circular(AppRadii.full),
                    boxShadow: [
                      if (!active && canManageSubscription)
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
                        loading
                            ? '处理中'
                            : active
                            ? '当前套餐'
                            : canManageSubscription
                            ? plan.ctaLabel
                            : '当前身份不可开通',
                        style: TextStyle(
                          color: active || !canManageSubscription
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

class DailyReportPage extends StatelessWidget {
  const DailyReportPage({super.key});

  @override
  Widget build(BuildContext context) => const ReportsHubPage(initialIndex: 0);
}

class WeeklyReportPage extends StatelessWidget {
  const WeeklyReportPage({super.key});

  @override
  Widget build(BuildContext context) => const ReportsHubPage(initialIndex: 1);
}

class _ReportPane extends ConsumerWidget {
  const _ReportPane({required this.provider});

  final FutureProvider<ReportData> provider;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final report = ref.watch(provider);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: report.when(
        data: _reportSections,
        loading: () => const [_Loading(title: '正在生成报告')],
        error: (error, _) => [
          _ErrorState(error: error, onRetry: () => ref.invalidate(provider)),
        ],
      ),
    );
  }
}

List<Widget> _reportSections(ReportData data) {
  final sections = <Widget>[
    _ReportHero(data: data),
    if (data.skills.isNotEmpty) _ReportSkillMap(skills: data.skills),
    _ReportSectionBlock(
      title: '成长亮点',
      items: data.highlights,
      fallback: '还没有足够亮点记录，完成任务后这里会自动生成。',
    ),
    _ReportSectionBlock(
      title: '待加强',
      items: data.improvements,
      fallback: '暂时没有明显待加强项。',
    ),
    if (data.tasks.isNotEmpty) _ReportTaskReview(tasks: data.tasks),
    _ReportSectionBlock(
      title: '看护记录',
      items: data.observations,
      fallback: '暂无摄像头或 AI 观察记录。',
    ),
    _ReportSectionBlock(
      title: '下次建议',
      items: data.nextActions,
      fallback: '继续保持当前任务节奏。',
    ),
  ];
  return [
    for (var index = 0; index < sections.length; index++) ...[
      if (index > 0) const SizedBox(height: 12),
      sections[index],
    ],
  ];
}

class _ReportHero extends StatelessWidget {
  const _ReportHero({required this.data});

  final ReportData data;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.ink,
      borderColor: AppColors.ink,
      radius: 24,
      padding: const EdgeInsets.fromLTRB(16, 17, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  data.headline.isEmpty ? data.summary : data.headline,
                  style: _darkTitle,
                ),
              ),
              if (data.periodLabel.isNotEmpty) ...[
                const SizedBox(width: 10),
                _ReportDarkPill(label: data.periodLabel),
              ],
            ],
          ),
          if (data.body.isNotEmpty) ...[
            const SizedBox(height: 9),
            Text(data.body, style: _darkSub),
          ],
          const SizedBox(height: 16),
          Row(
            children: [
              _Metric(
                label: '任务完成',
                value: '${data.taskCompleted}/${data.taskTotal}',
              ),
              const SizedBox(width: 8),
              _Metric(label: '积分', value: '+${data.pointsEarned}'),
              const SizedBox(width: 8),
              _Metric(label: '完成率', value: '${data.completionRate}%'),
            ],
          ),
          if (data.pendingItems > 0) ...[
            const SizedBox(height: 10),
            _ReportAttentionBar(count: data.pendingItems),
          ],
        ],
      ),
    );
  }
}

class _ReportDarkPill extends StatelessWidget {
  const _ReportDarkPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 184),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppRadii.full),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.78),
              fontFamily: AppTypography.systemFont,
              fontSize: 11,
              fontWeight: FontWeight.w800,
              height: 1.1,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

class _ReportAttentionBar extends StatelessWidget {
  const _ReportAttentionBar({required this.count});

  final int count;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.warning.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        child: Row(
          children: [
            const Icon(
              Icons.flag_outlined,
              color: AppColors.brandWarm,
              size: 17,
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '还有 $count 项需要家长处理',
                style: const TextStyle(
                  color: Color(0xFFFFD08A),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                  height: 1.2,
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

class _ReportSkillMap extends StatelessWidget {
  const _ReportSkillMap({required this.skills});

  final List<ReportSkill> skills;

  @override
  Widget build(BuildContext context) {
    final ranked = [...skills]..sort((a, b) => b.score.compareTo(a.score));
    final strongest = ranked.isEmpty ? null : ranked.first;
    final focus = ranked.isEmpty ? null : ranked.last;
    return AppSurface(
      radius: 22,
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _ReportIconBadge(
                icon: Icons.radar_outlined,
                color: AppColors.brand,
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('成长能力图谱', style: _reportTitleStyle),
                    SizedBox(height: 4),
                    Text('根据任务完成和看护记录生成', style: _reportBodyStyle),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 188,
            child: CustomPaint(
              painter: _ReportSkillRadarPainter(skills: skills),
              child: const SizedBox.expand(),
            ),
          ),
          if (strongest != null && focus != null) ...[
            const SizedBox(height: 14),
            _ReportSkillSummary(strongest: strongest, focus: focus),
            const SizedBox(height: 14),
            _ReportSkillMeterList(skills: skills, topKey: strongest.key),
            const SizedBox(height: 12),
            Text(
              '${strongest.label}: ${strongest.detail}',
              style: _reportBodyStyle,
            ),
          ],
        ],
      ),
    );
  }
}

class _ReportSkillSummary extends StatelessWidget {
  const _ReportSkillSummary({required this.strongest, required this.focus});

  final ReportSkill strongest;
  final ReportSkill focus;

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        children: [
          Expanded(
            child: _ReportSkillSpotlight(
              eyebrow: '优势能力',
              skill: strongest,
              color: AppColors.brand,
            ),
          ),
          const VerticalDivider(
            width: 22,
            thickness: 1,
            color: AppColors.borderSoft,
          ),
          Expanded(
            child: _ReportSkillSpotlight(
              eyebrow: '重点关注',
              skill: focus,
              color: AppColors.brandWarm,
            ),
          ),
        ],
      ),
    );
  }
}

class _ReportSkillSpotlight extends StatelessWidget {
  const _ReportSkillSpotlight({
    required this.eyebrow,
    required this.skill,
    required this.color,
  });

  final String eyebrow;
  final ReportSkill skill;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow,
          style: const TextStyle(
            color: AppColors.subtle,
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            height: 1.2,
            letterSpacing: 0,
          ),
        ),
        const SizedBox(height: 5),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(child: Text(skill.label, style: _reportRowTitle)),
            Text(
              '${skill.score}',
              style: TextStyle(
                color: color,
                fontFamily: AppTypography.systemFont,
                fontSize: 18,
                fontWeight: FontWeight.w900,
                height: 1,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
        const SizedBox(height: 5),
        Text(skill.level, style: _reportMetaStyle),
      ],
    );
  }
}

class _ReportSkillMeterList extends StatelessWidget {
  const _ReportSkillMeterList({required this.skills, required this.topKey});

  final List<ReportSkill> skills;
  final String topKey;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (var index = 0; index < skills.length; index++) ...[
          _ReportSkillMeterRow(
            skill: skills[index],
            active: skills[index].key == topKey,
          ),
          if (index != skills.length - 1) const SizedBox(height: 9),
        ],
      ],
    );
  }
}

class _ReportSkillMeterRow extends StatelessWidget {
  const _ReportSkillMeterRow({required this.skill, required this.active});

  final ReportSkill skill;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.brandDeep : AppColors.brandSoft;
    return Row(
      children: [
        SizedBox(
          width: 48,
          child: Text(
            skill.label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: active ? AppColors.brandDeep : AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w800,
              height: 1.1,
              letterSpacing: 0,
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadii.full),
            child: SizedBox(
              height: 7,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const ColoredBox(color: AppColors.surfaceStrong),
                  FractionallySizedBox(
                    widthFactor: skill.ratio,
                    alignment: Alignment.centerLeft,
                    child: ColoredBox(color: color),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 28,
          child: Text(
            '${skill.score}',
            textAlign: TextAlign.right,
            style: TextStyle(
              color: active ? AppColors.brandDeep : AppColors.subtle,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w900,
              height: 1.1,
              letterSpacing: 0,
            ),
          ),
        ),
      ],
    );
  }
}

class _ReportSkillRadarPainter extends CustomPainter {
  const _ReportSkillRadarPainter({required this.skills});

  final List<ReportSkill> skills;

  @override
  void paint(Canvas canvas, Size size) {
    if (skills.length < 3) return;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) * 0.35;
    final gridPaint = Paint()
      ..color = AppColors.border.withValues(alpha: 0.82)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    final axisPaint = Paint()
      ..color = AppColors.border.withValues(alpha: 0.72)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    final fillPaint = Paint()
      ..color = AppColors.brand.withValues(alpha: 0.16)
      ..style = PaintingStyle.fill;
    final linePaint = Paint()
      ..color = AppColors.brand
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeJoin = StrokeJoin.round;
    final pointPaint = Paint()
      ..color = AppColors.ink
      ..style = PaintingStyle.fill;

    for (var level = 1; level <= 4; level++) {
      final path = Path();
      for (var index = 0; index < skills.length; index++) {
        final point = _radarPoint(
          center,
          radius * level / 4,
          index,
          skills.length,
        );
        if (index == 0) {
          path.moveTo(point.dx, point.dy);
        } else {
          path.lineTo(point.dx, point.dy);
        }
      }
      path.close();
      canvas.drawPath(path, gridPaint);
    }

    final valuePath = Path();
    for (var index = 0; index < skills.length; index++) {
      final axis = _radarPoint(center, radius, index, skills.length);
      canvas.drawLine(center, axis, axisPaint);
      final point = _radarPoint(
        center,
        radius * skills[index].ratio,
        index,
        skills.length,
      );
      if (index == 0) {
        valuePath.moveTo(point.dx, point.dy);
      } else {
        valuePath.lineTo(point.dx, point.dy);
      }
    }
    valuePath.close();
    canvas.drawPath(valuePath, fillPaint);
    canvas.drawPath(valuePath, linePaint);

    for (var index = 0; index < skills.length; index++) {
      final point = _radarPoint(
        center,
        radius * skills[index].ratio,
        index,
        skills.length,
      );
      canvas.drawCircle(point, 4, pointPaint);
      final labelPoint = _radarPoint(center, radius + 24, index, skills.length);
      final painter = TextPainter(
        text: TextSpan(
          text: skills[index].label,
          style: const TextStyle(
            color: AppColors.muted,
            fontFamily: AppTypography.systemFont,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 0,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: 64);
      painter.paint(
        canvas,
        labelPoint - Offset(painter.width / 2, painter.height / 2),
      );
    }
  }

  Offset _radarPoint(Offset center, double radius, int index, int count) {
    final angle = -math.pi / 2 + (math.pi * 2 * index / count);
    return Offset(
      center.dx + math.cos(angle) * radius,
      center.dy + math.sin(angle) * radius,
    );
  }

  @override
  bool shouldRepaint(covariant _ReportSkillRadarPainter oldDelegate) {
    return oldDelegate.skills != skills;
  }
}

class _ReportSectionBlock extends StatelessWidget {
  const _ReportSectionBlock({
    required this.title,
    required this.items,
    required this.fallback,
  });

  final String title;
  final List<ReportSectionItem> items;
  final String fallback;

  @override
  Widget build(BuildContext context) {
    final visibleItems = items.isEmpty
        ? [
            ReportSectionItem(
              title: '暂无记录',
              detail: fallback,
              tone: 'neutral',
              source: '系统',
            ),
          ]
        : items;
    return AppSurface(
      radius: 22,
      padding: const EdgeInsets.fromLTRB(16, 15, 16, 7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: _reportTitleStyle),
          const SizedBox(height: 10),
          for (var index = 0; index < visibleItems.length; index++) ...[
            _ReportInsightRow(item: visibleItems[index]),
            if (index != visibleItems.length - 1)
              const Divider(height: 1, color: AppColors.borderSoft),
          ],
        ],
      ),
    );
  }
}

class _ReportInsightRow extends StatelessWidget {
  const _ReportInsightRow({required this.item});

  final ReportSectionItem item;

  @override
  Widget build(BuildContext context) {
    final color = _reportToneColor(item.tone);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ReportIconBadge(icon: _reportToneIcon(item.tone), color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: Text(item.title, style: _reportRowTitle)),
                    if (item.source.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      _ReportSourcePill(label: item.source, color: color),
                    ],
                  ],
                ),
                if (item.detail.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(item.detail, style: _reportBodyStyle),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReportTaskReview extends StatelessWidget {
  const _ReportTaskReview({required this.tasks});

  final List<ReportTaskItem> tasks;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: 22,
      padding: const EdgeInsets.fromLTRB(16, 15, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('任务回顾', style: _reportTitleStyle),
          const SizedBox(height: 11),
          for (var index = 0; index < tasks.length; index++) ...[
            _ReportTaskRow(task: tasks[index]),
            if (index != tasks.length - 1)
              const Divider(height: 1, color: AppColors.borderSoft),
          ],
        ],
      ),
    );
  }
}

class _ReportTaskRow extends StatelessWidget {
  const _ReportTaskRow({required this.task});

  final ReportTaskItem task;

  @override
  Widget build(BuildContext context) {
    final color = _reportToneColor(task.tone);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ReportIconBadge(icon: Icons.checklist_rtl_outlined, color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: Text(task.title, style: _reportRowTitle)),
                    _ReportSourcePill(label: task.statusLabel, color: color),
                  ],
                ),
                const SizedBox(height: 5),
                Text(
                  [
                    if (task.typeLabel.isNotEmpty) task.typeLabel,
                    if (task.time.isNotEmpty) task.time,
                    if (task.points > 0) '+${task.points} 积分',
                  ].join(' · '),
                  style: _reportMetaStyle,
                ),
                if (task.detail.isNotEmpty) ...[
                  const SizedBox(height: 5),
                  Text(task.detail, style: _reportBodyStyle),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReportIconBadge extends StatelessWidget {
  const _ReportIconBadge({required this.icon, required this.color});

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.11),
        borderRadius: BorderRadius.circular(14),
      ),
      child: SizedBox(
        width: 40,
        height: 40,
        child: Center(child: Icon(icon, color: color, size: 20)),
      ),
    );
  }
}

class _ReportSourcePill extends StatelessWidget {
  const _ReportSourcePill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
        child: Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: color,
            fontFamily: AppTypography.systemFont,
            fontSize: 10,
            fontWeight: FontWeight.w900,
            height: 1,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}

class GrowthMomentsPage extends StatelessWidget {
  const GrowthMomentsPage({super.key});

  @override
  Widget build(BuildContext context) => const ReportsHubPage(initialIndex: 0);
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
          ? TextButton(
              style: _inlineTextButtonStyle(),
              onPressed: () => _fulfill(ref),
              child: const Text('兑现'),
            )
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
    final profile = ref.watch(profileSummaryProvider);
    if (profile.isLoading) {
      return const _Page(
        title: '奖励',
        children: [_Loading(title: '正在确认权限')],
      );
    }
    final canManageRewards =
        profile.asData?.value.can('manage_rewards') ?? false;
    if (!canManageRewards) {
      return const _Page(
        title: '奖励',
        children: [
          AppStateView(
            variant: AppStateVariant.noData,
            title: '当前身份不能管理奖励',
            message: '你可以查看奖励和兑换记录，新增、编辑和删除由管理员处理。',
            compact: true,
          ),
        ],
      );
    }
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
          AppDangerButton(
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
    this.footer,
    this.avoidFooterOverlap = false,
  });

  final String title;
  final String? subtitle;
  final List<Widget> children;
  final Widget? trailing;
  final Widget? headerContent;
  final Widget? footer;
  final bool avoidFooterOverlap;

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
      footer: footer,
      avoidFooterOverlap: avoidFooterOverlap,
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
    '家庭与成员' => '成员协作和紧急联系人',
    '设备管理' => '设备状态、网络和声音能力',
    '任务与奖励' => '积分、奖励和成长记录',
    '积分与奖励' => '积分、奖励和兑换记录',
    '看护报告' => '日报和周报',
    'AI 规则与提醒' => '提醒方式、语音提醒和通知节奏',
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

class _BrandLogoTile extends StatelessWidget {
  const _BrandLogoTile();

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFFFFF7EA),
        borderRadius: BorderRadius.circular(16),
      ),
      child: SizedBox(
        width: 48,
        height: 48,
        child: Center(
          child: Image.asset(
            _brandLogoMarkAsset,
            semanticLabel: '暖瞳',
            width: 36,
            height: 36,
            fit: BoxFit.contain,
          ),
        ),
      ),
    );
  }
}

class _Input extends StatelessWidget {
  const _Input({
    required this.label,
    required this.controller,
    this.minLines = 1,
    this.keyboardType,
    this.readOnly = false,
  });

  final String label;
  final TextEditingController controller;
  final int minLines;
  final TextInputType? keyboardType;
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    return AppTextField(
      label: label,
      icon: _defaultInputIcon(label),
      controller: controller,
      minLines: minLines,
      keyboardType: keyboardType,
      readOnly: readOnly,
    );
  }
}

IconData _defaultInputIcon(String label) {
  if (label.contains('手机') || label.contains('电话')) {
    return Icons.phone_outlined;
  }
  if (label.contains('设备') || label.contains('摄像')) {
    return Icons.videocam_outlined;
  }
  if (label.contains('房间') || label.contains('位置')) {
    return Icons.meeting_room_outlined;
  }
  if (label.contains('积分')) {
    return Icons.toll_outlined;
  }
  if (label.contains('奖励')) {
    return Icons.redeem_outlined;
  }
  if (label.contains('反馈') || label.contains('说明')) {
    return Icons.notes_outlined;
  }
  return Icons.person_add_alt_outlined;
}

Future<void> _showPhoneChangeSheet(
  BuildContext context,
  WidgetRef ref,
  String currentPhone,
) async {
  final changed = await showAppBottomSheet<bool>(
    context: context,
    maxHeightFactor: 0.62,
    child: _ChangePhoneSheet(currentPhone: currentPhone),
  );
  if (changed != true || !context.mounted) return;
  ref.invalidate(accountProfileProvider);
  ref.invalidate(accountSecurityProvider);
  ref.invalidate(profileSummaryProvider);
  ref.invalidate(familyMembersProvider);
  _toast(context, '手机号已更新');
}

class _ChangePhoneSheet extends ConsumerStatefulWidget {
  const _ChangePhoneSheet({required this.currentPhone});

  final String currentPhone;

  @override
  ConsumerState<_ChangePhoneSheet> createState() => _ChangePhoneSheetState();
}

class _ChangePhoneSheetState extends ConsumerState<_ChangePhoneSheet> {
  late final TextEditingController _phone;
  late final TextEditingController _code;
  String? _phoneError;
  String? _codeError;
  var _requesting = false;
  var _saving = false;
  var _codeSent = false;

  @override
  void initState() {
    super.initState();
    _phone = TextEditingController();
    _code = TextEditingController();
  }

  @override
  void dispose() {
    _phone.dispose();
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final canSubmit = !_saving && !_requesting;
    return AppBottomSheetBody(
      title: '更换手机号',
      subtitle: '更换后会用于登录、安全验证和重要通知。',
      footer: AppSheetFooterActions(
        children: [
          AppSheetSecondaryButton(
            label: '取消',
            onTap: _saving ? null : () => Navigator.of(context).pop(false),
          ),
          AppSheetPrimaryButton(
            label: _saving ? '更换中' : '确认更换',
            loading: _saving,
            onTap: canSubmit ? _submit : null,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AppTextField(
            label: '当前手机号',
            icon: Icons.smartphone_outlined,
            value: _phoneMask(widget.currentPhone),
            readOnly: true,
          ),
          const SizedBox(height: 12),
          AppTextField(
            label: '新手机号',
            icon: Icons.smartphone_outlined,
            controller: _phone,
            keyboardType: TextInputType.phone,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(11),
            ],
            hintText: '请输入新的手机号',
            errorText: _phoneError,
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: AppTextField(
                  label: '验证码',
                  icon: Icons.password_outlined,
                  controller: _code,
                  keyboardType: TextInputType.number,
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                    LengthLimitingTextInputFormatter(6),
                  ],
                  hintText: '短信验证码',
                  errorText: _codeError,
                ),
              ),
              const SizedBox(width: 10),
              Padding(
                padding: const EdgeInsets.only(top: 29),
                child: SizedBox(
                  width: 104,
                  child: AppSecondaryButton(
                    label: _requesting
                        ? '发送中'
                        : _codeSent
                        ? '重新获取'
                        : '获取验证码',
                    height: AppControls.buttonHeight,
                    onTap: _requesting || _saving ? null : _requestCode,
                  ),
                ),
              ),
            ],
          ),
          AnimatedSwitcher(
            duration: AppMotion.duration(context, 160),
            child: _codeSent
                ? const Padding(
                    key: ValueKey('phone-code-sent'),
                    padding: EdgeInsets.only(top: 8),
                    child: Text('验证码已发送，请留意短信。', style: _mutedText),
                  )
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }

  Future<void> _requestCode() async {
    if (!_validatePhone()) return;
    setState(() => _requesting = true);
    try {
      final result = await ref
          .read(profileRepositoryProvider)
          .requestAccountPhoneCode(_phoneDigits(_phone.text));
      if (!mounted) return;
      setState(() => _codeSent = result.codeSent);
      _toast(context, result.message);
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _requesting = false);
    }
  }

  Future<void> _submit() async {
    final phoneOk = _validatePhone();
    final code = _code.text.trim();
    setState(() {
      _codeError = code.isEmpty ? '请输入验证码' : null;
    });
    if (!phoneOk || code.isEmpty) return;

    setState(() => _saving = true);
    try {
      await ref
          .read(profileRepositoryProvider)
          .updateAccountPhone(phone: _phoneDigits(_phone.text), code: code);
      if (mounted) Navigator.of(context).pop(true);
    } on ProfileException catch (error) {
      if (mounted) _toast(context, error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  bool _validatePhone() {
    final phone = _phoneDigits(_phone.text);
    final current = _phoneDigits(widget.currentPhone);
    final error = phone.isEmpty
        ? '请输入新手机号'
        : phone.length != 11
        ? '请输入正确的 11 位手机号'
        : phone == current
        ? '请填写一个新的手机号'
        : null;
    setState(() => _phoneError = error);
    return error == null;
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
  final ValueChanged<bool>? onChanged;

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
          AppCompactToggle(value: value, onChanged: onChanged, label: title),
        ],
      ),
    );
  }
}

class _FixedSettingOption extends StatelessWidget {
  const _FixedSettingOption({
    required this.icon,
    required this.label,
    required this.value,
    required this.badge,
  });

  final IconData icon;
  final String label;
  final String value;
  final String badge;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceElevated,
        borderRadius: BorderRadius.circular(AppRadii.input),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(13, 12, 12, 12),
        child: Row(
          children: [
            Icon(icon, color: AppColors.brandDeep, size: 18),
            const SizedBox(width: 10),
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
            const SizedBox(width: 10),
            _SoftTextBadge(
              label: badge,
              tone: AppColors.brandDeep,
              fill: AppColors.brandWash,
            ),
          ],
        ),
      ),
    );
  }
}

class _MinuteStepperRow extends StatelessWidget {
  const _MinuteStepperRow({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.min,
    required this.max,
    required this.step,
    required this.enabled,
    required this.onChanged,
    this.suffix = '分',
  });

  final String title;
  final String subtitle;
  final int value;
  final int min;
  final int max;
  final int step;
  final bool enabled;
  final ValueChanged<int> onChanged;
  final String suffix;

  @override
  Widget build(BuildContext context) {
    final canDecrease = enabled && value > min;
    final canIncrease = enabled && value < max;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 9),
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
          const SizedBox(width: 12),
          _StepperButton(
            icon: Icons.remove,
            label: '减少$title',
            onTap: canDecrease
                ? () => onChanged((value - step).clamp(min, max).toInt())
                : null,
          ),
          const SizedBox(width: 6),
          SizedBox(
            width: 56,
            child: Center(
              child: Text(
                '$value $suffix',
                maxLines: 1,
                style: TextStyle(
                  color: enabled ? AppColors.ink : AppColors.disabledInk,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0,
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),
          _StepperButton(
            icon: Icons.add,
            label: '增加$title',
            onTap: canIncrease
                ? () => onChanged((value + step).clamp(min, max).toInt())
                : null,
          ),
        ],
      ),
    );
  }
}

class _StepperButton extends StatelessWidget {
  const _StepperButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Semantics(
        button: true,
        enabled: enabled,
        label: label,
        child: Opacity(
          opacity: enabled ? 1 : 0.45,
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: AppColors.surfaceSoft,
              borderRadius: BorderRadius.circular(AppRadii.control),
              border: Border.all(color: AppColors.borderSoft),
            ),
            child: SizedBox(
              width: AppControls.minTouchTarget,
              height: AppControls.minTouchTarget,
              child: Center(child: Icon(icon, color: AppColors.ink, size: 17)),
            ),
          ),
        ),
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

const _conversationBoundaryPlans = [
  _ConversationBoundaryPlan(
    key: 'loose',
    label: '宽松',
    singleMinutes: 12,
    dailyMinutes: 35,
    description: '适合周末或家长在旁边时使用，自由聊天更长，继续提醒更少。',
  ),
  _ConversationBoundaryPlan(
    key: 'balanced',
    label: '平衡',
    singleMinutes: 8,
    dailyMinutes: 25,
    description: '默认方案，兼顾陪伴感和防沉迷，不打断正常任务节奏。',
  ),
  _ConversationBoundaryPlan(
    key: 'strict',
    label: '严格',
    singleMinutes: 5,
    dailyMinutes: 15,
    description: '适合上学日或睡前更容易兴奋的孩子，提醒更克制。',
  ),
];

class _ConversationBoundaryPlan {
  const _ConversationBoundaryPlan({
    required this.key,
    required this.label,
    required this.singleMinutes,
    required this.dailyMinutes,
    required this.description,
  });

  final String key;
  final String label;
  final int singleMinutes;
  final int dailyMinutes;
  final String description;
}

_ConversationBoundaryPlan _conversationBoundaryPlan(String key) {
  for (final option in _conversationBoundaryPlans) {
    if (option.key == key) return option;
  }
  return _conversationBoundaryPlans[1];
}

class _BoundaryChoiceButton extends StatelessWidget {
  const _BoundaryChoiceButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.ink : AppColors.surfaceSoft,
      borderRadius: BorderRadius.circular(AppRadii.full),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadii.full),
        onTap: onTap,
        child: SizedBox(
          height: 42,
          child: Center(
            child: Text(
              label,
              style: TextStyle(
                color: selected ? Colors.white : AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w900,
                letterSpacing: 0,
              ),
            ),
          ),
        ),
      ),
    );
  }
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

Future<void> _copyFamilyCode(BuildContext context, FamilyCodeInfo code) async {
  await Clipboard.setData(ClipboardData(text: code.code));
  if (context.mounted) _toast(context, '家庭号已复制');
}

Future<void> _resetFamilyCode(BuildContext context, WidgetRef ref) async {
  final confirmed = await _confirmFamilyCodeResetDialog(context);
  if (!confirmed || !context.mounted) return;
  try {
    await ref.read(profileRepositoryProvider).resetFamilyCode();
    ref.invalidate(familyCodeProvider);
    if (context.mounted) _toast(context, '家庭号已重置');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<bool> _confirmFamilyCodeResetDialog(BuildContext context) async {
  return await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('重置家庭号'),
          content: const Text('重置后旧家庭号不能再用于新加入。已经加入家庭的成员不会被移出，权限也不会改变。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              style: TextButton.styleFrom(foregroundColor: AppColors.danger),
              child: const Text('确认重置'),
            ),
          ],
        ),
      ) ??
      false;
}

Future<void> _showMemberActions(
  BuildContext context,
  WidgetRef ref,
  FamilyMember member,
  AccountProfile? account,
) async {
  final canTransfer =
      member.userId.isNotEmpty &&
      member.userId != account?.userId &&
      member.status == 'active';
  final action = await showAppBottomSheet<String>(
    context: context,
    maxHeightFactor: 0.56,
    child: AppBottomSheetBody(
      title: '管理成员',
      subtitle: '${member.name} · ${member.statusLabel}',
      footer: AppSheetSecondaryButton(
        label: '取消',
        onTap: () => Navigator.of(context).pop(),
      ),
      child: Column(
        children: [
          if (member.userId.isEmpty)
            AppListRow(
              icon: Icons.edit_outlined,
              title: '编辑成员资料',
              subtitle: '调整称呼、手机号和权限角色。',
              tone: AppListRowTone.blue,
              onTap: () => Navigator.of(context).pop('edit'),
            ),
          if (canTransfer)
            AppListRow(
              icon: Icons.admin_panel_settings_outlined,
              title: '转移管理员',
              subtitle: '对方将成为家庭管理员，你会变为监护人。',
              tone: AppListRowTone.amber,
              onTap: () => Navigator.of(context).pop('transfer'),
            ),
          AppListRow(
            icon: Icons.person_remove_outlined,
            title: '移除成员',
            subtitle: '移除后，对方不能再查看这个家庭空间。',
            tone: AppListRowTone.red,
            onTap: () => Navigator.of(context).pop('remove'),
          ),
        ],
      ),
    ),
  );
  if (action == null || !context.mounted) return;
  switch (action) {
    case 'edit':
      await _editMember(context, ref, member: member);
      break;
    case 'transfer':
      await _transferAdmin(context, ref, member);
      break;
    case 'remove':
      await _removeMember(context, ref, member);
      break;
  }
}

Future<void> _editMember(
  BuildContext context,
  WidgetRef ref, {
  FamilyMember? member,
}) async {
  final identityOptions = ref
      .read(guardianIdentityOptionsProvider)
      .asData
      ?.value;
  if (identityOptions == null) {
    ref.invalidate(guardianIdentityOptionsProvider);
    if (context.mounted) _toast(context, '正在同步身份配置，请稍后再试');
    return;
  }
  final members = ref.read(familyMembersProvider).asData?.value ?? const [];
  final invitations =
      ref.read(familyInvitationsProvider).asData?.value ?? const [];
  final account = ref.read(accountProfileProvider).asData?.value;
  final reservedIdentityKeys = _reservedGuardianIdentityKeys(
    identityOptions,
    account: account,
    members: members,
    invitations: invitations,
    excludeMemberId: member?.id,
  );
  final reservedRoleKeys = _reservedFamilyRoleKeys(
    members: members,
    invitations: invitations,
    excludeMemberId: member?.id,
  );
  final result = await showAppBottomSheet<_MemberEditResult>(
    context: context,
    maxHeightFactor: 0.72,
    child: _MemberEditSheet(
      member: member,
      options: identityOptions,
      reservedIdentityKeys: reservedIdentityKeys,
      reservedRoleKeys: reservedRoleKeys,
      submitLabel: member == null ? '发送邀请' : '保存',
    ),
  );
  if (result == null) return;
  try {
    final repository = ref.read(profileRepositoryProvider);
    FamilyInvitation? invitation;
    if (member == null) {
      invitation = await repository.sendFamilyInvitation(
        name: result.name,
        relationshipKey: result.relationshipKey,
        phone: result.phone,
        role: result.role,
      );
    } else {
      await repository.saveFamilyMember(
        id: member.id,
        name: result.name,
        relationshipKey: result.relationshipKey,
        phone: result.phone,
        role: result.role,
      );
    }
    ref.invalidate(familyMembersProvider);
    ref.invalidate(familyInvitationsProvider);
    ref.invalidate(profileSummaryProvider);
    if (context.mounted) {
      final notice = invitation?.deliveryNotice.trim();
      _toast(
        context,
        notice != null && notice.isNotEmpty
            ? notice
            : member == null
            ? '邀请已保存'
            : '已保存',
      );
    }
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _transferAdmin(
  BuildContext context,
  WidgetRef ref,
  FamilyMember member,
) async {
  final confirmed = await showAppConfirmSheet(
    context: context,
    title: '转移管理员',
    message: '确认把家庭管理员转移给${member.name}吗？转移后，你将变为监护人，不能继续管理成员和设备。',
    confirmLabel: '确认转移',
  );
  if (!confirmed) return;
  try {
    await ref.read(profileRepositoryProvider).transferFamilyAdmin(member.id);
    ref.invalidate(familyMembersProvider);
    ref.invalidate(accountProfileProvider);
    ref.invalidate(profileSummaryProvider);
    if (context.mounted) _toast(context, '管理员已转移');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _removeMember(
  BuildContext context,
  WidgetRef ref,
  FamilyMember member,
) async {
  final confirmed = await _confirm(
    context,
    title: '移除成员',
    message: '确认移除${member.name}吗？移除后，对方不能再查看这个家庭空间。',
    danger: true,
  );
  if (!confirmed) return;
  try {
    await ref.read(profileRepositoryProvider).deleteFamilyMember(member.id);
    ref.invalidate(familyMembersProvider);
    ref.invalidate(profileSummaryProvider);
    if (context.mounted) _toast(context, '成员已移除');
  } on ProfileException catch (error) {
    if (context.mounted) _toast(context, error.message);
  }
}

Future<void> _editContact(
  BuildContext context,
  WidgetRef ref, {
  EmergencyContact? contact,
}) async {
  final identityOptions = ref
      .read(guardianIdentityOptionsProvider)
      .asData
      ?.value;
  if (identityOptions == null) {
    ref.invalidate(guardianIdentityOptionsProvider);
    if (context.mounted) _toast(context, '正在同步身份配置，请稍后再试');
    return;
  }
  final contacts =
      ref.read(emergencyContactsProvider).asData?.value ?? const [];
  final reservedIdentityKeys = _reservedContactIdentityKeys(
    identityOptions,
    contacts: contacts,
    excludeContactId: contact?.id,
  );
  final result = await showAppBottomSheet<_ContactEditResult>(
    context: context,
    maxHeightFactor: 0.78,
    child: _ContactEditSheet(
      contact: contact,
      options: identityOptions,
      reservedIdentityKeys: reservedIdentityKeys,
    ),
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
          relationshipKey: result.relationshipKey,
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
    final updatedInvitation = await ref
        .read(profileRepositoryProvider)
        .resendFamilyInvitation(invitation.id);
    ref.invalidate(familyInvitationsProvider);
    if (context.mounted) {
      final notice = updatedInvitation.deliveryNotice.trim();
      _toast(context, notice.isEmpty ? '邀请已重发' : notice);
    }
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
    required this.relationshipKey,
    required this.phone,
    required this.role,
  });

  final String name;
  final String relationshipKey;
  final String phone;
  final String role;
}

class _MemberEditSheet extends StatefulWidget {
  const _MemberEditSheet({
    required this.submitLabel,
    required this.options,
    required this.reservedIdentityKeys,
    required this.reservedRoleKeys,
    this.member,
  });

  final FamilyMember? member;
  final GuardianIdentityOptions options;
  final Set<String> reservedIdentityKeys;
  final Set<String> reservedRoleKeys;
  final String submitLabel;

  @override
  State<_MemberEditSheet> createState() => _MemberEditSheetState();
}

class _MemberEditSheetState extends State<_MemberEditSheet> {
  late final TextEditingController _phone;
  late String _relationshipKey;
  late String _role;

  @override
  void initState() {
    super.initState();
    _phone = TextEditingController(text: widget.member?.phone ?? '');
    final memberIdentityKey = widget.options.keyForValue(
      widget.member?.name ?? '',
    );
    _relationshipKey = memberIdentityKey.isNotEmpty
        ? memberIdentityKey
        : _defaultFamilyRelationshipKey(
            widget.options,
            widget.reservedIdentityKeys,
          );
    if (widget.reservedIdentityKeys.contains(_relationshipKey)) {
      _relationshipKey = _defaultFamilyRelationshipKey(
        widget.options,
        widget.reservedIdentityKeys,
      );
    }
    final rawMemberRole = widget.member?.role.trim() ?? '';
    final memberRoleKey = rawMemberRole.isEmpty
        ? ''
        : widget.options.roleKeyFor(rawMemberRole);
    _role = memberRoleKey.isNotEmpty
        ? memberRoleKey
        : _defaultFamilyRoleKey(widget.options, widget.reservedRoleKeys);
    if (widget.reservedRoleKeys.contains(_role)) {
      _role = _defaultFamilyRoleKey(widget.options, widget.reservedRoleKeys);
    }
  }

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final relationshipLabel = widget.options.labelForStoredValue(
      _relationshipKey.isNotEmpty
          ? _relationshipKey
          : _defaultFamilyRelationshipKey(
              widget.options,
              widget.reservedIdentityKeys,
            ),
    );
    final canSubmit =
        !widget.reservedIdentityKeys.contains(_relationshipKey) &&
        !widget.reservedRoleKeys.contains(_role);
    return AppBottomSheetBody(
      title: widget.member == null ? '邀请家庭成员' : '编辑家庭成员',
      subtitle: widget.member == null
          ? '填写手机号后发送邀请，对方接受后加入家庭空间。'
          : '调整称呼和权限范围。',
      padding: const EdgeInsets.fromLTRB(18, 8, 18, 12),
      handleTitleGap: 8,
      headerBottomGap: 12,
      titleFontSize: 21,
      footer: AppSheetFooterActions(
        children: [
          AppSheetSecondaryButton(
            label: '取消',
            onTap: () => Navigator.of(context).pop(),
          ),
          AppSheetPrimaryButton(
            label: widget.submitLabel,
            onTap: canSubmit
                ? () => Navigator.of(context).pop(
                    _MemberEditResult(
                      name: relationshipLabel,
                      relationshipKey: _relationshipKey,
                      phone: _phone.text.trim(),
                      role: _role,
                    ),
                  )
                : null,
          ),
        ],
      ),
      child: Column(
        children: [
          GuardianIdentitySelector(
            value: _relationshipKey,
            options: widget.options,
            disabledKeys: widget.reservedIdentityKeys,
            groupKey: const ValueKey('memberIdentityGroupSelect'),
            cardListKey: const ValueKey('memberDisplayNameCards'),
            cardKeyPrefix: 'memberDisplayNameCard',
            onChanged: (value) => setState(() => _relationshipKey = value),
          ),
          const SizedBox(height: 12),
          _Input(
            label: '手机号',
            controller: _phone,
            keyboardType: TextInputType.phone,
          ),
          const SizedBox(height: 12),
          _MemberRoleSelector(
            roles: widget.options.familyRoles,
            selected: _role,
            disabledKeys: widget.reservedRoleKeys,
            onChanged: (role) => setState(() => _role = role),
          ),
        ],
      ),
    );
  }
}

class _MemberRoleSelector extends StatelessWidget {
  const _MemberRoleSelector({
    required this.roles,
    required this.selected,
    required this.disabledKeys,
    required this.onChanged,
  });

  final List<FamilyRoleOption> roles;
  final String selected;
  final Set<String> disabledKeys;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    FamilyRoleOption? selectedRole;
    for (final role in roles) {
      if (role.key == selected) {
        selectedRole = role;
        break;
      }
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          '权限角色',
          style: TextStyle(
            color: AppColors.ink,
            fontFamily: AppTypography.systemFont,
            fontSize: 12.5,
            fontWeight: FontWeight.w900,
            letterSpacing: 0,
            height: 1.1,
          ),
        ),
        const SizedBox(height: 7),
        AppSegmentedControl<String>(
          value: selected,
          semanticLabel: '权限角色',
          compact: true,
          onChanged: onChanged,
          options: [
            for (final role in roles)
              AppSegmentOption<String>(
                value: role.key,
                label: role.label,
                key: ValueKey('memberRoleSegment_${role.key}'),
                enabled:
                    !disabledKeys.contains(role.key) || role.key == selected,
              ),
          ],
        ),
        AnimatedSwitcher(
          duration: AppMotion.duration(context, 160),
          switchInCurve: Curves.easeOutCubic,
          switchOutCurve: Curves.easeOutCubic,
          child: selectedRole == null || selectedRole.description.isEmpty
              ? const SizedBox(height: 8)
              : Padding(
                  key: ValueKey('memberRoleDescription_${selectedRole.key}'),
                  padding: const EdgeInsets.fromLTRB(2, 7, 2, 0),
                  child: Text(
                    selectedRole.description,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      height: 1.35,
                      letterSpacing: 0,
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}

class _ContactEditResult {
  const _ContactEditResult({
    required this.name,
    required this.phone,
    required this.relationship,
    required this.relationshipKey,
    required this.defaultNotify,
    this.deleteRequested = false,
  });

  final String name;
  final String phone;
  final String relationship;
  final String relationshipKey;
  final bool defaultNotify;
  final bool deleteRequested;
}

class _ContactEditSheet extends StatefulWidget {
  const _ContactEditSheet({
    required this.options,
    required this.reservedIdentityKeys,
    this.contact,
  });

  final EmergencyContact? contact;
  final GuardianIdentityOptions options;
  final Set<String> reservedIdentityKeys;

  @override
  State<_ContactEditSheet> createState() => _ContactEditSheetState();
}

class _ContactEditSheetState extends State<_ContactEditSheet> {
  late final TextEditingController _name;
  late final TextEditingController _phone;
  late String _relationshipKey;
  late bool _notify;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.contact?.name ?? '');
    _phone = TextEditingController(text: widget.contact?.phone ?? '');
    _relationshipKey = _initialContactRelationshipKey(
      widget.options,
      widget.contact,
      widget.reservedIdentityKeys,
    );
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
    final relationshipLabel = widget.options.labelForStoredValue(
      _relationshipKey.isNotEmpty
          ? _relationshipKey
          : _defaultContactRelationshipKey(
              widget.options,
              widget.reservedIdentityKeys,
            ),
    );
    final canSubmit = !widget.reservedIdentityKeys.contains(_relationshipKey);
    return AppBottomSheetBody(
      title: widget.contact == null ? '添加紧急联系人' : '编辑紧急联系人',
      subtitle: '选择联系人在家庭中的称呼，用于通知和看护协作记录。',
      footer: AppSheetFooterActions(
        children: [
          if (widget.contact != null) ...[
            AppSheetDangerButton(
              label: '删除',
              onTap: () => Navigator.of(context).pop(
                _ContactEditResult(
                  name: _name.text.trim(),
                  phone: _phone.text.trim(),
                  relationship: relationshipLabel,
                  relationshipKey: _relationshipKey,
                  defaultNotify: _notify,
                  deleteRequested: true,
                ),
              ),
            ),
          ],
          AppSheetSecondaryButton(
            label: '取消',
            onTap: () => Navigator.of(context).pop(),
          ),
          AppSheetPrimaryButton(
            label: '保存',
            onTap: canSubmit
                ? () => Navigator.of(context).pop(
                    _ContactEditResult(
                      name: _name.text.trim(),
                      phone: _phone.text.trim(),
                      relationship: relationshipLabel,
                      relationshipKey: _relationshipKey,
                      defaultNotify: _notify,
                    ),
                  )
                : null,
          ),
        ],
      ),
      child: Column(
        children: [
          AppSecondaryButton(
            label: '从通讯录选择',
            trailing: const Icon(Icons.contacts_outlined, size: 17),
            onTap: _pickFromContacts,
          ),
          const SizedBox(height: 12),
          _Input(label: '姓名', controller: _name),
          const SizedBox(height: 12),
          _Input(
            label: '手机号',
            controller: _phone,
            keyboardType: TextInputType.phone,
          ),
          const SizedBox(height: 12),
          GuardianIdentitySelector(
            value: _relationshipKey,
            options: widget.options,
            disabledKeys: widget.reservedIdentityKeys,
            groupKey: const ValueKey('contactIdentityGroupSelect'),
            cardListKey: const ValueKey('contactDisplayNameCards'),
            cardKeyPrefix: 'contactDisplayNameCard',
            onChanged: (value) => setState(() => _relationshipKey = value),
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
                AppCompactToggle(
                  value: _notify,
                  onChanged: (value) => setState(() => _notify = value),
                  label: '默认通知这个联系人',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _pickFromContacts() async {
    try {
      final picked = await pickPhoneContact();
      if (!mounted || picked == null) return;
      final candidateKey = widget.options.keyForValue(picked.name);
      setState(() {
        if (picked.name.isNotEmpty) _name.text = picked.name;
        if (picked.phone.isNotEmpty) _phone.text = picked.phone;
        if (candidateKey.isNotEmpty &&
            !widget.reservedIdentityKeys.contains(candidateKey)) {
          _relationshipKey = candidateKey;
        }
      });
      if (picked.phone.isEmpty) {
        _toast(context, '这个联系人没有可用手机号，请手动填写');
      }
    } on ContactPickerException catch (error) {
      if (mounted) _toast(context, error.message);
    }
  }
}

String _familyRoleLabel(
  GuardianIdentityOptions? options,
  String role,
  String fallback,
) {
  final label = options?.roleLabelFor(role) ?? '';
  return label.isEmpty || label == role ? fallback : label;
}

String _defaultFamilyRelationshipKey(
  GuardianIdentityOptions options,
  Set<String> reservedIdentityKeys,
) {
  return options.firstSelectableKeyForGroup(
    options.defaultGroupKey,
    reservedIdentityKeys,
  );
}

String _defaultContactRelationshipKey(
  GuardianIdentityOptions options,
  Set<String> reservedIdentityKeys,
) {
  return options.firstSelectableKeyForGroup(
    options.defaultGroupKey,
    reservedIdentityKeys,
  );
}

String _initialContactRelationshipKey(
  GuardianIdentityOptions options,
  EmergencyContact? contact,
  Set<String> reservedIdentityKeys,
) {
  if (contact == null) {
    return _defaultContactRelationshipKey(options, reservedIdentityKeys);
  }
  final keyFromApi = options.keyForValue(contact.relationshipKey);
  if (keyFromApi.isNotEmpty) return keyFromApi;
  final keyFromLabel = options.keyForValue(contact.relationship);
  if (keyFromLabel.isNotEmpty) return keyFromLabel;
  if (_looksLikeStoredRelationshipKey(contact.relationship) ||
      _looksLikeStoredRelationshipKey(contact.relationshipKey)) {
    return options.keyForValue('family_default').isNotEmpty
        ? 'family_default'
        : _defaultContactRelationshipKey(options, reservedIdentityKeys);
  }
  return _defaultContactRelationshipKey(options, reservedIdentityKeys);
}

String _defaultFamilyRoleKey(
  GuardianIdentityOptions options,
  Set<String> reservedRoleKeys,
) {
  for (final preferred in const ['guardian', 'viewer', 'admin']) {
    if (!reservedRoleKeys.contains(preferred) &&
        options.familyRoles.any((role) => role.key == preferred)) {
      return preferred;
    }
  }
  for (final role in options.familyRoles) {
    if (!reservedRoleKeys.contains(role.key)) return role.key;
  }
  return options.defaultRoleKey;
}

Set<String> _reservedGuardianIdentityKeys(
  GuardianIdentityOptions options, {
  AccountProfile? account,
  List<FamilyMember> members = const [],
  List<FamilyInvitation> invitations = const [],
  String? excludeMemberId,
  String? excludeInvitationId,
  bool excludeAccount = false,
}) {
  final keys = <String>{};
  void addKey(String value) {
    final key = options.keyForValue(value);
    if (key.isNotEmpty && options.isExclusiveIdentityKey(key)) {
      keys.add(key);
    }
  }

  if (!excludeAccount && account != null) {
    addKey(
      account.relationshipKey.isNotEmpty
          ? account.relationshipKey
          : account.relationship,
    );
  }
  for (final member in members) {
    if (member.id == excludeMemberId) continue;
    if (excludeAccount &&
        account != null &&
        member.userId.isNotEmpty &&
        member.userId == account.userId) {
      continue;
    }
    addKey(
      member.relationshipKey.isNotEmpty ? member.relationshipKey : member.name,
    );
  }
  for (final invitation in invitations) {
    if (invitation.id == excludeInvitationId) continue;
    addKey(
      invitation.relationshipKey.isNotEmpty
          ? invitation.relationshipKey
          : invitation.name,
    );
  }
  return keys;
}

Set<String> _reservedContactIdentityKeys(
  GuardianIdentityOptions options, {
  List<EmergencyContact> contacts = const [],
  String? excludeContactId,
}) {
  final keys = <String>{};
  void addKey(String value) {
    final key = options.keyForValue(value);
    if (key.isNotEmpty && options.isExclusiveIdentityKey(key)) {
      keys.add(key);
    }
  }

  for (final contact in contacts) {
    if (contact.id == excludeContactId) continue;
    addKey(
      contact.relationshipKey.isNotEmpty
          ? contact.relationshipKey
          : contact.relationship,
    );
  }
  return keys;
}

Set<String> _reservedFamilyRoleKeys({
  List<FamilyMember> members = const [],
  List<FamilyInvitation> invitations = const [],
  String? excludeMemberId,
  String? excludeInvitationId,
}) {
  final hasAdminMember = members.any(
    (member) => member.id != excludeMemberId && member.role == 'admin',
  );
  final hasAdminInvitation = invitations.any(
    (invitation) =>
        invitation.id != excludeInvitationId && invitation.role == 'admin',
  );
  return hasAdminMember || hasAdminInvitation ? {'admin'} : const {};
}

String _contactRelationshipLabel(
  GuardianIdentityOptions? options, {
  required String relationship,
  String relationshipKey = '',
}) {
  final keyLabel = options?.labelForKey(relationshipKey.trim()) ?? '';
  if (keyLabel.isNotEmpty) return keyLabel;
  final normalized = relationship.trim();
  if (normalized.isEmpty) return '联系人';
  final label = options?.labelForStoredValue(normalized) ?? normalized;
  if (label == normalized && _looksLikeStoredRelationshipKey(normalized)) {
    return '其他家人';
  }
  return label;
}

String _contactSubtitle(
  GuardianIdentityOptions? options,
  EmergencyContact contact,
) {
  final relationship = _contactRelationshipLabel(
    options,
    relationship: contact.relationship,
    relationshipKey: contact.relationshipKey,
  );
  return '$relationship · ${_phoneMask(contact.phone)}';
}

bool _looksLikeStoredRelationshipKey(String value) {
  return RegExp(r'^[a-z][a-z0-9_ -]*$').hasMatch(value.trim());
}

String _familyMemberTitle(
  FamilyMember member,
  GuardianIdentityOptions? options,
) {
  final relationshipKey = member.relationshipKey.trim();
  if (relationshipKey.isNotEmpty) {
    final label = options?.labelForKey(relationshipKey) ?? '';
    if (label.isNotEmpty) return label;
  }
  return member.name;
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

void _toast(BuildContext context, String message) {
  showAppToast(context, message);
}

String _phoneMask(String phone) {
  if (phone.length < 7) return phone;
  return '${phone.substring(0, 3)} **** ${phone.substring(phone.length - 4)}';
}

String _phoneDigits(String value) {
  return value.replaceAll(RegExp(r'\D'), '');
}

ButtonStyle _inlineTextButtonStyle({bool danger = false}) {
  return TextButton.styleFrom(
    foregroundColor: danger ? AppColors.danger : AppColors.brandDeep,
    minimumSize: const Size(
      AppControls.minTouchTarget,
      AppControls.buttonHeight,
    ),
    padding: const EdgeInsets.symmetric(horizontal: 10),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    textStyle: const TextStyle(
      fontFamily: AppTypography.systemFont,
      fontSize: 13,
      fontWeight: FontWeight.w800,
      letterSpacing: 0,
    ),
  );
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

Color _reportToneColor(String tone) {
  return switch (tone) {
    'blue' => AppColors.brand,
    'green' => AppColors.success,
    'amber' => AppColors.warning,
    'red' => AppColors.danger,
    _ => AppColors.ink,
  };
}

IconData _reportToneIcon(String tone) {
  return switch (tone) {
    'green' => Icons.check_circle_outline,
    'amber' => Icons.flag_outlined,
    'red' => Icons.error_outline,
    'blue' => Icons.auto_awesome_outlined,
    _ => Icons.notes_outlined,
  };
}

const _reportTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 16,
  fontWeight: FontWeight.w900,
  height: 1.18,
  letterSpacing: 0,
);

const _reportRowTitle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 14,
  fontWeight: FontWeight.w800,
  height: 1.24,
  letterSpacing: 0,
);

const _reportBodyStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 12,
  fontWeight: FontWeight.w600,
  height: 1.45,
  letterSpacing: 0,
);

const _reportMetaStyle = TextStyle(
  color: AppColors.subtle,
  fontFamily: AppTypography.systemFont,
  fontSize: 11,
  fontWeight: FontWeight.w700,
  height: 1.25,
  letterSpacing: 0,
);

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

Map<String, dynamic> _profileMap(dynamic value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, item) => MapEntry('$key', item));
  }
  return const {};
}
