import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';
import 'package:warm_sight/src/features/student_access/presentation/student_access_management_panel.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_text_field.dart';
import 'package:warm_sight/src/shared/widgets/app_toast.dart';

typedef StudentAccessClock = DateTime Function();

final studentAccessClockProvider = Provider<StudentAccessClock>((ref) {
  return DateTime.now;
});

class StudentAccessPairingPage extends ConsumerWidget {
  const StudentAccessPairingPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final account = ref.watch(accountProfileProvider);
    return account.when(
      skipLoadingOnRefresh: true,
      data: (data) {
        if (!data.can('manage_child_profile')) {
          return const _PairingStatePage(
            child: null,
            state: AppStateVariant.permission,
            title: '需要家庭管理员授权',
            message: '当前账号没有管理孩子资料的权限，请让家庭管理员创建或更新学生登录方式。',
          );
        }
        return _buildForChild(ref);
      },
      loading: () => const _PairingStatePage(
        child: null,
        state: AppStateVariant.loading,
        title: '正在确认家庭权限',
        message: '马上就好。',
      ),
      error: (error, _) => _PairingStatePage(
        child: null,
        state: AppStateVariant.serviceUnavailable,
        title: '家庭权限暂时无法同步',
        message: error is ProfileException ? error.message : '请稍后重试。',
        onRetry: () => ref.invalidate(accountProfileProvider),
      ),
    );
  }

  Widget _buildForChild(WidgetRef ref) {
    final child = ref.watch(currentChildProvider);
    return child.when(
      skipLoadingOnRefresh: true,
      data: (data) {
        if (data == null) {
          return const _PairingStatePage(
            child: null,
            state: AppStateVariant.noData,
            title: '还没有孩子资料',
            message: '请先完成孩子资料，再创建学生学习空间。',
          );
        }
        final grade =
            ChildGradeOption.fromCode(data.gradeCode) ??
            ChildGradeOption.fromLegacy(
              educationStage: data.educationStage,
              grade: data.grade,
            );
        if (grade?.isPrimary != true) {
          return _PairingStatePage(
            child: data,
            state: AppStateVariant.noData,
            title: '当前年级暂不支持学生学习空间',
            message: '学生学习空间仅面向已开放年级，请先在孩子资料中确认。',
          );
        }
        return _buildForAvailability(ref, data);
      },
      loading: () => const _PairingStatePage(
        child: null,
        state: AppStateVariant.loading,
        title: '正在同步孩子资料',
        message: '马上就好。',
      ),
      error: (error, _) => _PairingStatePage(
        child: null,
        state: AppStateVariant.serviceUnavailable,
        title: '孩子资料暂时无法同步',
        message: error is ProfileException ? error.message : '请稍后重试。',
        onRetry: () => ref.invalidate(currentChildProvider),
      ),
    );
  }

  Widget _buildForAvailability(WidgetRef ref, ChildProfile child) {
    final provider = studentAccessAvailabilityProvider(
      studentAccessScope(child),
    );
    final availability = ref.watch(provider);
    return availability.when(
      skipLoadingOnRefresh: false,
      skipLoadingOnReload: false,
      data: (value) {
        if (!_canAccessStudentWorkspace(child, value)) {
          return _PairingStatePage(
            child: child,
            state: AppStateVariant.noData,
            title: '当前暂不能登录学习空间',
            message: '请确认孩子已选择开放年级，并完成年级设置。',
          );
        }
        return _StudentPairingExperience(
          child: child,
          studentWebUrl: ref.watch(appEnvironmentProvider).studentWebBaseUrl,
        );
      },
      loading: () => _PairingStatePage(
        child: child,
        state: AppStateVariant.loading,
        title: '正在确认学习空间权限',
        message: '确认后即可创建登录配对码。',
      ),
      error: (_, _) => _PairingStatePage(
        child: child,
        state: AppStateVariant.serviceUnavailable,
        title: '学习空间权限暂时无法同步',
        message: '请检查网络后重试；状态确认前不会创建配对码。',
        onRetry: () => ref.invalidate(provider),
      ),
    );
  }
}

bool _canAccessStudentWorkspace(
  ChildProfile child,
  LearningAvailability availability,
) {
  return child.id.trim().isNotEmpty &&
      availability.gradeCode == child.gradeCode &&
      availability.canAccessWorkspace;
}

class _PairingStatePage extends StatelessWidget {
  const _PairingStatePage({
    required this.child,
    required this.state,
    required this.title,
    required this.message,
    this.onRetry,
  });

  final ChildProfile? child;
  final AppStateVariant state;
  final String title;
  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return AppScreen(
      title: '学生学习空间',
      subtitle: child?.name,
      reserveBottomNavigation: false,
      backLabel: '返回孩子资料',
      onBack: () => _backToChildProfile(context),
      children: [
        AppStateView(
          variant: state,
          title: title,
          message: message,
          primaryActionLabel: onRetry == null ? null : '重新加载',
          onPrimaryAction: onRetry,
          compact: true,
        ),
      ],
    );
  }
}

class _StudentPairingExperience extends ConsumerStatefulWidget {
  const _StudentPairingExperience({
    required this.child,
    required this.studentWebUrl,
  });

  final ChildProfile child;
  final String studentWebUrl;

  @override
  ConsumerState<_StudentPairingExperience> createState() =>
      _StudentPairingExperienceState();
}

class _StudentPairingExperienceState
    extends ConsumerState<_StudentPairingExperience> {
  final _pinController = TextEditingController();
  final _confirmPinController = TextEditingController();
  StudentPairingCode? _pairing;
  Timer? _timer;
  late DateTime _now;
  String? _requestError;
  var _submitting = false;
  var _regenerating = false;

  @override
  void initState() {
    super.initState();
    _now = ref.read(studentAccessClockProvider)();
    _pinController.addListener(_refreshInputState);
    _confirmPinController.addListener(_refreshInputState);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _pinController
      ..removeListener(_refreshInputState)
      ..dispose();
    _confirmPinController
      ..removeListener(_refreshInputState)
      ..dispose();
    super.dispose();
  }

  void _refreshInputState() {
    if (mounted) setState(() => _requestError = null);
  }

  bool get _pinReady {
    final pin = _pinController.text;
    return pin.length == 4 && _confirmPinController.text == pin;
  }

  String? get _confirmError {
    final confirmation = _confirmPinController.text;
    if (confirmation.length < 4 || confirmation == _pinController.text) {
      return null;
    }
    return '两次输入的 PIN 不一致';
  }

  bool get _expired => _pairing?.isExpiredAt(_now) ?? false;

  @override
  Widget build(BuildContext context) {
    final pairing = _pairing;
    final childName = widget.child.nickname.trim().isNotEmpty
        ? widget.child.nickname.trim()
        : widget.child.name;

    return AppScreen(
      title: '学生学习空间',
      subtitle: '$childName · ${widget.child.grade}',
      reserveBottomNavigation: false,
      avoidFooterOverlap: true,
      backLabel: '返回孩子资料',
      onBack: () => _backToChildProfile(context),
      footer: pairing == null
          ? AppPrimaryButton(
              key: const ValueKey('createStudentPairingCode'),
              label: _submitting ? '正在创建' : '创建配对码',
              loading: _submitting,
              onTap: !_submitting && _pinReady ? _createPairingCode : null,
              trailing: const AppButtonGlyph(icon: Icons.arrow_forward),
            )
          : AppSecondaryButton(
              key: const ValueKey('restartStudentPairing'),
              label: _expired ? '重新设置 PIN' : '重新生成配对码',
              onTap: _prepareRegeneration,
              trailing: Icon(
                _expired ? Icons.lock_reset_outlined : Icons.refresh,
                size: 18,
                color: AppColors.ink,
              ),
            ),
      children: [
        _StudentSpaceIntro(childName: childName),
        const SizedBox(height: 14),
        AnimatedSwitcher(
          duration: AppMotion.duration(context, 220),
          child: pairing == null
              ? _PinSetupPanel(
                  key: const ValueKey('studentPinSetup'),
                  pinController: _pinController,
                  confirmPinController: _confirmPinController,
                  confirmError: _confirmError,
                  requestError: _requestError,
                  regenerating: _regenerating,
                )
              : _PairingCodePanel(
                  key: const ValueKey('studentPairingResult'),
                  pairing: pairing,
                  now: _now,
                  studentWebUrl: widget.studentWebUrl,
                  onCopyCode: _expired ? null : _copyPairingCode,
                  onCopyWebsite: _copyWebsite,
                ),
        ),
        const SizedBox(height: 14),
        StudentAccessManagementPanel(childId: widget.child.id),
      ],
    );
  }

  Future<void> _createPairingCode() async {
    if (!_pinReady || _submitting) return;
    final availability = ref.read(
      studentAccessAvailabilityProvider(studentAccessScope(widget.child)),
    );
    if (availability.isLoading ||
        availability.hasError ||
        !_canAccessStudentWorkspace(widget.child, availability.asData!.value)) {
      setState(() => _requestError = '当前暂不能登录学习空间，暂不能创建配对码。');
      return;
    }
    FocusScope.of(context).unfocus();
    setState(() {
      _submitting = true;
      _requestError = null;
    });
    try {
      final result = await ref
          .read(studentAccessRepositoryProvider)
          .createPairingCode(
            childId: widget.child.id,
            pin: _pinController.text,
          );
      if (!mounted) return;
      _timer?.cancel();
      setState(() {
        _pairing = result;
        _now = ref.read(studentAccessClockProvider)();
        _submitting = false;
      });
      _startCountdown();
    } on StudentAccessException catch (error) {
      if (!mounted) return;
      setState(() {
        _requestError = error.message;
        _submitting = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _requestError = '暂时无法创建配对码，请稍后重试。';
        _submitting = false;
      });
    }
  }

  void _startCountdown() {
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() => _now = ref.read(studentAccessClockProvider)());
      if (_expired) timer.cancel();
    });
  }

  void _prepareRegeneration() {
    _timer?.cancel();
    _pinController.clear();
    _confirmPinController.clear();
    setState(() {
      _pairing = null;
      _regenerating = true;
      _requestError = null;
    });
  }

  Future<void> _copyPairingCode() async {
    final code = _pairing?.code ?? '';
    if (code.isEmpty || _expired) return;
    await Clipboard.setData(ClipboardData(text: code));
    if (mounted) {
      showAppToast(context, '配对码已复制', tone: AppToastTone.success);
    }
  }

  Future<void> _copyWebsite() async {
    await Clipboard.setData(ClipboardData(text: widget.studentWebUrl));
    if (mounted) {
      showAppToast(context, '学生网页地址已复制', tone: AppToastTone.success);
    }
  }
}

class _StudentSpaceIntro extends StatelessWidget {
  const _StudentSpaceIntro({required this.childName});

  final String childName;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.brandWash.withValues(alpha: 0.74),
      borderColor: AppColors.brand.withValues(alpha: 0.10),
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.88),
              borderRadius: BorderRadius.circular(15),
            ),
            child: const SizedBox(
              width: 48,
              height: 48,
              child: Icon(
                Icons.school_outlined,
                color: AppColors.brandDeep,
                size: 25,
              ),
            ),
          ),
          const SizedBox(width: 13),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '为 $childName 开通学习网页',
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 17,
                    fontWeight: FontWeight.w900,
                    height: 1.2,
                  ),
                ),
                const SizedBox(height: 5),
                const Text(
                  '配对成功后，孩子可在电脑或平板上上课；家长账号和摄像头权限不会共享。',
                  style: TextStyle(
                    color: AppColors.muted,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PinSetupPanel extends StatelessWidget {
  const _PinSetupPanel({
    required this.pinController,
    required this.confirmPinController,
    required this.confirmError,
    required this.requestError,
    required this.regenerating,
    super.key,
  });

  final TextEditingController pinController;
  final TextEditingController confirmPinController;
  final String? confirmError;
  final String? requestError;
  final bool regenerating;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '设置 4 位学习 PIN',
            style: TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 19,
              fontWeight: FontWeight.w900,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            '孩子以后在这台浏览器进入学习空间时，用这个 PIN 解锁。',
            style: TextStyle(
              color: AppColors.muted,
              fontFamily: AppTypography.systemFont,
              fontSize: 13,
              fontWeight: FontWeight.w600,
              height: 1.45,
            ),
          ),
          if (regenerating) ...[
            const SizedBox(height: 12),
            const _InlineNotice(
              icon: Icons.info_outline,
              text: '创建新配对码后，上一个未使用的配对码会立即失效。',
              color: AppColors.warning,
              background: AppColors.warningWash,
            ),
          ],
          const SizedBox(height: 16),
          AppTextField(
            key: const ValueKey('studentPinField'),
            label: '学习 PIN',
            icon: Icons.lock_outline,
            controller: pinController,
            hintText: '请输入 4 位数字',
            keyboardType: TextInputType.number,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(4),
            ],
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
          ),
          const SizedBox(height: 14),
          AppTextField(
            key: const ValueKey('studentPinConfirmField'),
            label: '再次输入 PIN',
            icon: Icons.verified_user_outlined,
            controller: confirmPinController,
            hintText: '请再次输入',
            keyboardType: TextInputType.number,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(4),
            ],
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
            errorText: confirmError,
          ),
          if (requestError != null) ...[
            const SizedBox(height: 12),
            _InlineNotice(
              key: const ValueKey('studentPairingError'),
              icon: Icons.error_outline,
              text: requestError!,
              color: AppColors.danger,
              background: AppColors.dangerWash,
            ),
          ],
          const SizedBox(height: 14),
          const _SecurityNote(),
        ],
      ),
    );
  }
}

class _PairingCodePanel extends StatelessWidget {
  const _PairingCodePanel({
    required this.pairing,
    required this.now,
    required this.studentWebUrl,
    required this.onCopyCode,
    required this.onCopyWebsite,
    super.key,
  });

  final StudentPairingCode pairing;
  final DateTime now;
  final String studentWebUrl;
  final VoidCallback? onCopyCode;
  final VoidCallback onCopyWebsite;

  @override
  Widget build(BuildContext context) {
    final remaining = pairing.remainingAt(now);
    final expired = remaining == Duration.zero;
    return AppSurface(
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.fromLTRB(16, 18, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  expired ? '配对码已过期' : '配对码已准备好',
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 19,
                    fontWeight: FontWeight.w900,
                    height: 1.2,
                  ),
                ),
              ),
              _CountdownBadge(remaining: remaining),
            ],
          ),
          const SizedBox(height: 14),
          _PairingCodeDigits(code: pairing.code, expired: expired),
          const SizedBox(height: 12),
          AppSecondaryButton(
            key: const ValueKey('copyStudentPairingCode'),
            label: expired ? '配对码不可用' : '复制配对码',
            onTap: onCopyCode,
            trailing: Icon(
              Icons.copy_outlined,
              size: 17,
              color: expired ? AppColors.disabledInk : AppColors.ink,
            ),
          ),
          const SizedBox(height: 16),
          const Divider(height: 1, color: AppColors.borderSoft),
          const SizedBox(height: 16),
          const Text(
            '在孩子的电脑或平板打开',
            style: TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 14,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          _WebsiteAddress(url: studentWebUrl, onCopy: onCopyWebsite),
          const SizedBox(height: 14),
          const _PairingSteps(),
          const SizedBox(height: 14),
          _InlineNotice(
            icon: expired ? Icons.timer_off_outlined : Icons.timer_outlined,
            text: expired
                ? '这个配对码已失效，请重新设置 PIN 并创建新码。'
                : '配对码仅可使用一次，并会在 10 分钟后自动失效。',
            color: expired ? AppColors.danger : AppColors.brandDeep,
            background: expired ? AppColors.dangerWash : AppColors.brandWash,
          ),
        ],
      ),
    );
  }
}

class _PairingCodeDigits extends StatelessWidget {
  const _PairingCodeDigits({required this.code, required this.expired});

  final String code;
  final bool expired;

  @override
  Widget build(BuildContext context) {
    final characters = code.padRight(8).substring(0, 8).split('');
    return Row(
      key: const ValueKey('studentPairingCode'),
      children: [
        for (var index = 0; index < characters.length; index++) ...[
          if (index > 0) const SizedBox(width: 5),
          Expanded(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: expired ? AppColors.disabledBg : AppColors.brandWash,
                borderRadius: BorderRadius.circular(11),
                border: Border.all(
                  color: expired
                      ? AppColors.border
                      : AppColors.brand.withValues(alpha: 0.14),
                ),
              ),
              child: SizedBox(
                height: 48,
                child: Center(
                  child: Text(
                    characters[index],
                    style: TextStyle(
                      color: expired
                          ? AppColors.disabledInk
                          : AppColors.brandDeep,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 20,
                      fontWeight: FontWeight.w900,
                      height: 1,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _CountdownBadge extends StatelessWidget {
  const _CountdownBadge({required this.remaining});

  final Duration remaining;

  @override
  Widget build(BuildContext context) {
    final expired = remaining == Duration.zero;
    final minutes = remaining.inMinutes
        .remainder(60)
        .toString()
        .padLeft(2, '0');
    final seconds = remaining.inSeconds
        .remainder(60)
        .toString()
        .padLeft(2, '0');
    return DecoratedBox(
      decoration: BoxDecoration(
        color: expired ? AppColors.dangerWash : AppColors.successWash,
        borderRadius: BorderRadius.circular(AppRadii.full),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        child: Text(
          expired ? '已失效' : '$minutes:$seconds',
          key: const ValueKey('studentPairingCountdown'),
          style: TextStyle(
            color: expired ? AppColors.danger : AppColors.success,
            fontFamily: AppTypography.systemFont,
            fontSize: 12.5,
            fontWeight: FontWeight.w900,
            height: 1,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
      ),
    );
  }
}

class _WebsiteAddress extends StatelessWidget {
  const _WebsiteAddress({required this.url, required this.onCopy});

  final String url;
  final VoidCallback onCopy;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceTinted,
        borderRadius: BorderRadius.circular(AppRadii.control),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 7, 6, 7),
        child: Row(
          children: [
            const Icon(Icons.language, color: AppColors.brandDeep, size: 18),
            const SizedBox(width: 9),
            Expanded(
              child: SelectableText(
                url,
                maxLines: 2,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  height: 1.3,
                ),
              ),
            ),
            IconButton(
              key: const ValueKey('copyStudentWebsite'),
              tooltip: '复制学生网页地址',
              onPressed: onCopy,
              icon: const Icon(Icons.copy_outlined, size: 18),
              color: AppColors.muted,
              constraints: const BoxConstraints(
                minWidth: AppControls.minTouchTarget,
                minHeight: AppControls.minTouchTarget,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PairingSteps extends StatelessWidget {
  const _PairingSteps();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        _PairingStep(number: '1', text: '打开学生网页，选择“家长配对”。'),
        SizedBox(height: 9),
        _PairingStep(number: '2', text: '输入上方 8 位配对码。'),
        SizedBox(height: 9),
        _PairingStep(number: '3', text: '配对成功后，孩子使用学习 PIN 解锁。'),
      ],
    );
  }
}

class _PairingStep extends StatelessWidget {
  const _PairingStep({required this.number, required this.text});

  final String number;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DecoratedBox(
          decoration: const BoxDecoration(
            color: AppColors.brandWash,
            shape: BoxShape.circle,
          ),
          child: SizedBox(
            width: 24,
            height: 24,
            child: Center(
              child: Text(
                number,
                style: const TextStyle(
                  color: AppColors.brandDeep,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: 9),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              text,
              style: const TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w600,
                height: 1.45,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SecurityNote extends StatelessWidget {
  const _SecurityNote();

  @override
  Widget build(BuildContext context) {
    return const _InlineNotice(
      icon: Icons.shield_outlined,
      text: '不要使用生日或连续数字。PIN 只用于学生网页，不会修改家长 App 登录方式。',
      color: AppColors.brandSage,
      background: AppColors.brandSageWash,
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({
    required this.icon,
    required this.text,
    required this.color,
    required this.background,
    super.key,
  });

  final IconData icon;
  final String text;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppRadii.control),
      ),
      child: Padding(
        padding: const EdgeInsets.all(11),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                text,
                style: TextStyle(
                  color: color,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  height: 1.45,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

void _backToChildProfile(BuildContext context) {
  if (context.canPop()) {
    context.pop();
  } else {
    context.go(profileChildPath);
  }
}
