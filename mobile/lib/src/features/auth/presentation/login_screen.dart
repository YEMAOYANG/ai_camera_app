import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:guardian_parent_app/src/app/router/app_route.dart';
import 'package:guardian_parent_app/src/core/config/app_environment.dart';
import 'package:guardian_parent_app/src/core/theme/app_system_ui.dart';
import 'package:guardian_parent_app/src/core/theme/app_tokens.dart';
import 'package:guardian_parent_app/src/features/auth/application/auth_repository.dart';
import 'package:guardian_parent_app/src/features/auth/application/session_data_invalidation.dart';
import 'package:guardian_parent_app/src/features/profile/application/profile_repository.dart';
import 'package:guardian_parent_app/src/features/profile/domain/profile_models.dart';
import 'package:guardian_parent_app/src/features/setup/application/setup_draft.dart';
import 'package:guardian_parent_app/src/features/setup/application/setup_repository.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_bottom_sheet.dart';
import 'package:guardian_parent_app/src/shared/widgets/app_button.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen>
    with SingleTickerProviderStateMixin {
  final _phoneController = TextEditingController();
  final _codeController = TextEditingController();
  final _phoneFocus = FocusNode();
  final _codeFocus = FocusNode();

  late final AnimationController _revealController;
  Timer? _countdownTimer;

  String? _phoneError;
  String? _codeError;
  String? _agreementError;
  String? _statusMessage;
  var _agreementAccepted = false;
  var _codeSent = false;
  var _countdown = 0;
  var _loading = false;
  var _success = false;
  var _lastPhoneText = '';
  var _lastCodeText = '';

  @override
  void initState() {
    super.initState();
    _revealController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 520),
    )..forward();
    _phoneController.addListener(_clearPhoneErrorOnEdit);
    _codeController.addListener(_clearCodeErrorOnEdit);
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    _revealController.dispose();
    _phoneController
      ..removeListener(_clearPhoneErrorOnEdit)
      ..dispose();
    _codeController
      ..removeListener(_clearCodeErrorOnEdit)
      ..dispose();
    _phoneFocus.dispose();
    _codeFocus.dispose();
    super.dispose();
  }

  void _clearPhoneErrorOnEdit() {
    final text = _phoneController.text;
    if (text == _lastPhoneText) return;
    _lastPhoneText = text;
    if (_phoneError == null && !_success) return;
    setState(() {
      _phoneError = null;
      _success = false;
    });
  }

  void _clearCodeErrorOnEdit() {
    final text = _codeController.text;
    if (text == _lastCodeText) return;
    _lastCodeText = text;
    if (_codeError == null && !_success) return;
    setState(() {
      _codeError = null;
      _success = false;
    });
  }

  String get _phoneDigits {
    return _phoneController.text.replaceAll(RegExp(r'\D'), '');
  }

  bool get _canSubmit {
    return !_loading;
  }

  bool _validatePhone() {
    final valid = RegExp(r'^1[3-9]\d{9}$').hasMatch(_phoneDigits);
    if (valid) return true;

    setState(() {
      _phoneError = _phoneDigits.isEmpty ? '请填写手机号' : '请输入正确的 11 位手机号';
      _statusMessage = null;
    });
    _phoneFocus.requestFocus();
    return false;
  }

  bool _validateCodeFormat() {
    final code = _codeController.text.trim();
    if (RegExp(r'^\d{4,6}$').hasMatch(code)) return true;

    setState(() {
      _codeError = code.isEmpty ? '请输入验证码' : '请输入完整验证码';
      _statusMessage = null;
    });
    _codeFocus.requestFocus();
    return false;
  }

  Future<void> _requestCode() async {
    if (_loading || _countdown > 0) return;
    if (!_validatePhone()) return;

    late final SmsCodeRequestResult result;
    try {
      result = await ref
          .read(authRepositoryProvider)
          .requestSmsCode(_phoneDigits);
    } on AuthException catch (error) {
      setState(() {
        _phoneError = error.code == 'invalid_phone' ? error.message : null;
        _statusMessage = error.code == 'invalid_phone' ? null : error.message;
      });
      if (error.code == 'invalid_phone') {
        _phoneFocus.requestFocus();
      }
      return;
    }

    final environment = ref.read(appEnvironmentProvider);
    final debugCode =
        environment.flavor == AppFlavor.development ||
            environment.flavor == AppFlavor.test
        ? result.debugCode.trim()
        : '';
    if (debugCode.isNotEmpty) {
      _codeController.value = TextEditingValue(
        text: debugCode,
        selection: TextSelection.collapsed(offset: debugCode.length),
      );
      _lastCodeText = debugCode;
    }

    setState(() {
      _codeSent = result.codeSent;
      _countdown = 59;
      _statusMessage = debugCode.isEmpty
          ? '验证码已发送，未注册手机号验证后会自动创建家庭账户。'
          : '验证码已自动填入，未注册手机号验证后会自动创建家庭账户。';
      _codeError = null;
    });
    _focusCodeField();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusCodeField();
    });
    unawaited(
      Future<void>.delayed(const Duration(milliseconds: 90), _focusCodeField),
    );

    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      if (_countdown <= 1) {
        timer.cancel();
        setState(() => _countdown = 0);
        return;
      }
      setState(() => _countdown -= 1);
    });
  }

  void _toggleAgreement() {
    setState(() {
      _agreementAccepted = !_agreementAccepted;
      _agreementError = null;
    });
  }

  void _openUserAgreement() {
    context.push(userAgreementPath);
  }

  void _openPrivacyPolicy() {
    context.push(privacyPolicyPath);
  }

  Future<void> _submit() async {
    if (_loading) return;

    final phoneDigits = _phoneDigits;
    final code = _codeController.text.trim();
    final phoneValid = RegExp(r'^1[3-9]\d{9}$').hasMatch(phoneDigits);
    final nextPhoneError = phoneValid
        ? null
        : phoneDigits.isEmpty
        ? '请填写手机号'
        : '请输入正确的 11 位手机号';
    final nextCodeError = code.isEmpty
        ? '请输入验证码'
        : !_codeSent
        ? '请先获取验证码'
        : RegExp(r'^\d{4,6}$').hasMatch(code)
        ? null
        : '请输入完整验证码';
    final nextAgreementError = _agreementAccepted ? null : '请先同意用户协议和隐私政策';

    if (nextPhoneError != null ||
        nextCodeError != null ||
        nextAgreementError != null) {
      setState(() {
        _phoneError = nextPhoneError;
        _codeError = nextCodeError;
        _agreementError = nextAgreementError;
        _statusMessage = null;
      });
      if (nextPhoneError != null) {
        _phoneFocus.requestFocus();
      } else if (nextCodeError != null) {
        _codeFocus.requestFocus();
      }
      return;
    }

    if (!_validatePhone()) return;
    if (!_validateCodeFormat()) {
      _codeFocus.requestFocus();
      return;
    }

    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _success = false;
      _agreementError = null;
      _statusMessage = null;
    });

    late final AuthLoginResult loginResult;
    try {
      loginResult = await ref
          .read(authRepositoryProvider)
          .loginWithSms(phone: phoneDigits, code: code);
      invalidateAuthenticatedSessionData(ref);
    } on AuthException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _success = false;
        _statusMessage = null;
        if (error.code == 'invalid_phone') {
          _phoneError = error.message;
        } else if (error.code == 'invalid_code' ||
            error.code == 'missing_code') {
          _codeError = error.message;
        } else {
          _statusMessage = error.message;
        }
      });
      if (error.code == 'invalid_phone') {
        _phoneFocus.requestFocus();
      } else {
        _codeFocus.requestFocus();
      }
      return;
    }
    if (!mounted) return;

    setState(() {
      _loading = false;
      _success = true;
      _statusMessage = '验证通过，家庭账户已准备好。';
    });

    await Future<void>.delayed(const Duration(milliseconds: 420));
    if (!mounted) return;

    if (loginResult.pendingJoins.isNotEmpty) {
      final joinAction = await _showPendingJoins(loginResult.pendingJoins);
      if (!mounted) return;
      if (joinAction == _PendingJoinAction.deferred) {
        await ref.read(authRepositoryProvider).logout();
        invalidateAuthenticatedSessionData(ref);
        if (!mounted) return;
        setState(() {
          _loading = false;
          _success = false;
          _statusMessage = '家庭邀请已保留。下次用这个手机号登录时，还可以继续处理。';
        });
        return;
      }
    }

    await _routeAfterLogin();
  }

  Future<void> _routeAfterLogin() async {
    try {
      final setupStatus = await ref.read(setupRepositoryProvider).status();
      if (!mounted) return;
      syncSetupDraftFromStatus(ref, setupStatus);
      context.go(setupStatus.routePath);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _success = false;
        _statusMessage = error.message;
      });
    }
  }

  Future<_PendingJoinAction> _showPendingJoins(
    List<PendingFamilyJoin> joins,
  ) async {
    return await showAppBottomSheet<_PendingJoinAction>(
          context: context,
          maxHeightFactor: joins.length > 1 ? 0.72 : 0.62,
          child: _PendingJoinSheet(
            joins: joins,
            onAccept: (join) async {
              await ref
                  .read(profileRepositoryProvider)
                  .acceptFamilyInvitation(join.id);
              invalidateAuthenticatedSessionData(ref);
            },
            onDecline: (join) async {
              await ref
                  .read(profileRepositoryProvider)
                  .declineFamilyInvitation(join.id);
            },
          ),
        ) ??
        _PendingJoinAction.deferred;
  }

  void _focusCodeField() {
    if (!mounted) return;
    FocusScope.of(context).requestFocus(_codeFocus);
    unawaited(SystemChannels.textInput.invokeMethod<void>('TextInput.show'));
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final motionDisabled = MediaQuery.of(context).disableAnimations;

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: AppSystemUi.light(),
      child: Scaffold(
        backgroundColor: AppColors.appBackgroundWarm,
        body: Stack(
          children: [
            const Positioned.fill(child: _LoginBackground()),
            SafeArea(
              child: SingleChildScrollView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                padding: EdgeInsets.fromLTRB(20, 18, 20, bottomInset + 28),
                child: SizedBox(
                  width: double.infinity,
                  child: motionDisabled
                      ? _LoginContent(
                          phoneController: _phoneController,
                          codeController: _codeController,
                          phoneFocus: _phoneFocus,
                          codeFocus: _codeFocus,
                          phoneError: _phoneError,
                          codeError: _codeError,
                          codeSent: _codeSent,
                          countdown: _countdown,
                          loading: _loading,
                          success: _success,
                          statusMessage: _statusMessage,
                          agreementError: _agreementError,
                          agreementAccepted: _agreementAccepted,
                          canSubmit: _canSubmit,
                          onRequestCode: _requestCode,
                          onAgreementToggle: _toggleAgreement,
                          onUserAgreementTap: _openUserAgreement,
                          onPrivacyPolicyTap: _openPrivacyPolicy,
                          onSubmit: _submit,
                        )
                      : FadeTransition(
                          opacity: _revealController,
                          child: SlideTransition(
                            position:
                                Tween<Offset>(
                                  begin: const Offset(0, 0.018),
                                  end: Offset.zero,
                                ).animate(
                                  CurvedAnimation(
                                    parent: _revealController,
                                    curve: Curves.easeOutCubic,
                                  ),
                                ),
                            child: _LoginContent(
                              phoneController: _phoneController,
                              codeController: _codeController,
                              phoneFocus: _phoneFocus,
                              codeFocus: _codeFocus,
                              phoneError: _phoneError,
                              codeError: _codeError,
                              codeSent: _codeSent,
                              countdown: _countdown,
                              loading: _loading,
                              success: _success,
                              statusMessage: _statusMessage,
                              agreementError: _agreementError,
                              agreementAccepted: _agreementAccepted,
                              canSubmit: _canSubmit,
                              onRequestCode: _requestCode,
                              onAgreementToggle: _toggleAgreement,
                              onUserAgreementTap: _openUserAgreement,
                              onPrivacyPolicyTap: _openPrivacyPolicy,
                              onSubmit: _submit,
                            ),
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

class _LoginBackground extends StatelessWidget {
  const _LoginBackground();

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
          stops: [0, 0.5, 0.78, 1],
        ),
      ),
    );
  }
}

class _LoginContent extends StatelessWidget {
  const _LoginContent({
    required this.phoneController,
    required this.codeController,
    required this.phoneFocus,
    required this.codeFocus,
    required this.phoneError,
    required this.codeError,
    required this.codeSent,
    required this.countdown,
    required this.loading,
    required this.success,
    required this.statusMessage,
    required this.agreementError,
    required this.agreementAccepted,
    required this.canSubmit,
    required this.onRequestCode,
    required this.onAgreementToggle,
    required this.onUserAgreementTap,
    required this.onPrivacyPolicyTap,
    required this.onSubmit,
  });

  final TextEditingController phoneController;
  final TextEditingController codeController;
  final FocusNode phoneFocus;
  final FocusNode codeFocus;
  final String? phoneError;
  final String? codeError;
  final bool codeSent;
  final int countdown;
  final bool loading;
  final bool success;
  final String? statusMessage;
  final String? agreementError;
  final bool agreementAccepted;
  final bool canSubmit;
  final VoidCallback onRequestCode;
  final VoidCallback onAgreementToggle;
  final VoidCallback onUserAgreementTap;
  final VoidCallback onPrivacyPolicyTap;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _LoginHeader(),
        const SizedBox(height: 18),
        _LoginForm(
          phoneController: phoneController,
          codeController: codeController,
          phoneFocus: phoneFocus,
          codeFocus: codeFocus,
          phoneError: phoneError,
          codeError: codeError,
          codeSent: codeSent,
          countdown: countdown,
          onRequestCode: onRequestCode,
        ),
        const SizedBox(height: 16),
        _AgreementRow(
          accepted: agreementAccepted,
          errorText: agreementError,
          onToggle: onAgreementToggle,
          onUserAgreementTap: onUserAgreementTap,
          onPrivacyPolicyTap: onPrivacyPolicyTap,
        ),
        const SizedBox(height: 16),
        _StatusPanel(success: success, message: statusMessage),
        const SizedBox(height: 18),
        Opacity(
          opacity: canSubmit ? 1 : 0.48,
          child: AppPrimaryButton(
            label: loading ? '正在确认' : '继续',
            loading: loading,
            trailing: const AppButtonGlyph(icon: Icons.arrow_forward),
            onTap: canSubmit ? onSubmit : null,
          ),
        ),
        const SizedBox(height: 16),
        const _TrustNote(),
      ],
    );
  }
}

class _LoginHeader extends StatelessWidget {
  const _LoginHeader();

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned(
          right: -78,
          top: -70,
          width: 210,
          height: 190,
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                colors: [
                  AppColors.brand.withValues(alpha: 0.13),
                  AppColors.brand.withValues(alpha: 0),
                ],
              ),
            ),
          ),
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.ink,
                    borderRadius: BorderRadius.circular(13),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.primaryButtonShadow.withValues(
                          alpha: 0.13,
                        ),
                        blurRadius: 16,
                        offset: const Offset(0, 9),
                      ),
                    ],
                  ),
                  child: const SizedBox(
                    width: 36,
                    height: 36,
                    child: Center(
                      child: Icon(
                        Icons.center_focus_strong_outlined,
                        color: Colors.white,
                        size: 18,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '家庭看护',
                      style: TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                        height: 1.1,
                        letterSpacing: 0,
                      ),
                    ),
                    SizedBox(height: 3),
                    Text(
                      '家庭看护登录',
                      style: TextStyle(
                        color: Color(0x8A526579),
                        fontFamily: AppTypography.systemFont,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        height: 1,
                        letterSpacing: 0,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 24),
            const Text(
              '登录家庭看护空间',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 30,
                fontWeight: FontWeight.w700,
                height: 1.12,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(AppRadii.full),
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        AppColors.brand.withValues(alpha: 0),
                        AppColors.brand.withValues(alpha: 0.42),
                        AppColors.brand.withValues(alpha: 0),
                      ],
                    ),
                  ),
                  child: const SizedBox(width: 2, height: 34),
                ),
                const SizedBox(width: 11),
                const Expanded(
                  child: Text(
                    '手机号验证后继续；未注册手机号会自动创建家庭账户。',
                    style: TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      height: 1.55,
                      letterSpacing: 0,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}

class _LoginForm extends StatelessWidget {
  const _LoginForm({
    required this.phoneController,
    required this.codeController,
    required this.phoneFocus,
    required this.codeFocus,
    required this.phoneError,
    required this.codeError,
    required this.codeSent,
    required this.countdown,
    required this.onRequestCode,
  });

  final TextEditingController phoneController;
  final TextEditingController codeController;
  final FocusNode phoneFocus;
  final FocusNode codeFocus;
  final String? phoneError;
  final String? codeError;
  final bool codeSent;
  final int countdown;
  final VoidCallback onRequestCode;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: Colors.white.withValues(alpha: 0.76)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4C6685).withValues(alpha: 0.07),
            blurRadius: 22,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 16, 14, 14),
        child: Column(
          children: [
            _AuthTextField(
              controller: phoneController,
              focusNode: phoneFocus,
              label: '手机号',
              helper: '用于安全验证',
              placeholder: '请输入手机号',
              icon: Icons.smartphone_outlined,
              errorText: phoneError,
              keyboardType: TextInputType.phone,
              textInputAction: TextInputAction.next,
              inputFormatters: [
                FilteringTextInputFormatter.allow(RegExp(r'[\d\s]')),
                LengthLimitingTextInputFormatter(15),
              ],
              onSubmitted: (_) => codeFocus.requestFocus(),
            ),
            const SizedBox(height: 13),
            _AuthTextField(
              controller: codeController,
              focusNode: codeFocus,
              label: '验证码',
              helper: codeSent ? '已发送' : '短信确认',
              placeholder: '请输入验证码',
              icon: Icons.password_outlined,
              errorText: codeError,
              keyboardType: TextInputType.number,
              textInputAction: TextInputAction.done,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(6),
              ],
              trailing: _CodeRequestButton(
                sent: codeSent,
                countdown: countdown,
                onTap: onRequestCode,
              ),
            ),
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerLeft,
              child: Text(
                codeSent ? '验证码已发送，稍后可重新获取。' : '未注册手机号验证通过后，会自动创建家庭账户。',
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  height: 1.45,
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

class _AuthTextField extends StatelessWidget {
  const _AuthTextField({
    required this.controller,
    required this.focusNode,
    required this.label,
    required this.helper,
    required this.placeholder,
    required this.icon,
    required this.keyboardType,
    required this.textInputAction,
    this.inputFormatters,
    this.errorText,
    this.trailing,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final String label;
  final String helper;
  final String placeholder;
  final IconData icon;
  final TextInputType keyboardType;
  final TextInputAction textInputAction;
  final List<TextInputFormatter>? inputFormatters;
  final String? errorText;
  final Widget? trailing;
  final ValueChanged<String>? onSubmitted;

  @override
  Widget build(BuildContext context) {
    final hasError = errorText != null;

    return ListenableBuilder(
      listenable: Listenable.merge([controller, focusNode]),
      builder: (context, _) {
        final focused = focusNode.hasFocus;
        final filled = controller.text.trim().isNotEmpty;

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  helper,
                  style: const TextStyle(
                    color: AppColors.subtle,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    letterSpacing: 0,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            AnimatedContainer(
              duration: AppMotion.duration(context, 180),
              curve: Curves.easeOutCubic,
              decoration: BoxDecoration(
                color: filled
                    ? AppColors.surfaceElevated
                    : AppColors.surfaceSoft,
                borderRadius: BorderRadius.circular(AppRadii.input),
                border: Border.all(
                  color: hasError
                      ? AppColors.danger
                      : focused
                      ? AppColors.focus
                      : AppColors.borderSoft,
                  width: focused ? 1.1 : 1,
                ),
                boxShadow: focused
                    ? [
                        BoxShadow(
                          color: AppColors.focus.withValues(alpha: 0.08),
                          blurRadius: 12,
                          offset: const Offset(0, 5),
                        ),
                      ]
                    : null,
              ),
              child: Row(
                children: [
                  const SizedBox(width: 13),
                  Icon(
                    icon,
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
                      controller: controller,
                      focusNode: focusNode,
                      keyboardType: keyboardType,
                      textInputAction: textInputAction,
                      inputFormatters: inputFormatters,
                      onSubmitted: onSubmitted,
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontFamily: AppTypography.systemFont,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0,
                      ),
                      decoration: InputDecoration(
                        hintText: placeholder,
                        hintStyle: const TextStyle(
                          color: AppColors.subtle,
                          fontWeight: FontWeight.w500,
                        ),
                        filled: false,
                        fillColor: Colors.transparent,
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        errorBorder: InputBorder.none,
                        focusedErrorBorder: InputBorder.none,
                        disabledBorder: InputBorder.none,
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(
                          vertical: 14,
                        ),
                      ),
                    ),
                  ),
                  if (trailing != null) ...[
                    const SizedBox(width: 8),
                    trailing!,
                    const SizedBox(width: 8),
                  ] else
                    const SizedBox(width: 12),
                ],
              ),
            ),
            AnimatedSwitcher(
              duration: AppMotion.duration(context, 180),
              child: hasError
                  ? Padding(
                      key: ValueKey(errorText),
                      padding: const EdgeInsets.only(top: 7, left: 4),
                      child: Text(
                        errorText!,
                        style: const TextStyle(
                          color: AppColors.danger,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          height: 1.3,
                          letterSpacing: 0,
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
          ],
        );
      },
    );
  }
}

class _CodeRequestButton extends StatelessWidget {
  const _CodeRequestButton({
    required this.sent,
    required this.countdown,
    required this.onTap,
  });

  final bool sent;
  final int countdown;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final active = countdown <= 0;
    final label = active ? (sent ? '重新获取' : '获取验证码') : '$countdown 秒';

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: active ? onTap : null,
      child: AnimatedContainer(
        duration: AppMotion.duration(context, 180),
        height: 36,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        decoration: BoxDecoration(
          color: active
              ? AppColors.brandWash
              : AppColors.disabledFill.withValues(alpha: 0.76),
          borderRadius: BorderRadius.circular(13),
          border: Border.all(
            color: active
                ? AppColors.brand.withValues(alpha: 0.10)
                : AppColors.borderSoft,
          ),
        ),
        child: Center(
          child: Text(
            label,
            style: TextStyle(
              color: active ? AppColors.brandDeep : AppColors.disabledInk,
              fontFamily: AppTypography.systemFont,
              fontSize: 12,
              fontWeight: FontWeight.w600,
              letterSpacing: 0,
            ),
          ),
        ),
      ),
    );
  }
}

class _AgreementRow extends StatelessWidget {
  const _AgreementRow({
    required this.accepted,
    required this.errorText,
    required this.onToggle,
    required this.onUserAgreementTap,
    required this.onPrivacyPolicyTap,
  });

  final bool accepted;
  final String? errorText;
  final VoidCallback onToggle;
  final VoidCallback onUserAgreementTap;
  final VoidCallback onPrivacyPolicyTap;

  @override
  Widget build(BuildContext context) {
    const textStyle = TextStyle(
      color: AppColors.muted,
      fontFamily: AppTypography.systemFont,
      fontSize: 12,
      fontWeight: FontWeight.w600,
      height: 1.55,
      letterSpacing: 0,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onToggle,
              child: Semantics(
                button: true,
                label: accepted ? '取消同意协议' : '同意用户协议和隐私政策',
                child: AnimatedContainer(
                  duration: AppMotion.duration(context, 180),
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    color: accepted ? AppColors.brand : AppColors.surfaceSoft,
                    borderRadius: BorderRadius.circular(7),
                    border: Border.all(
                      color: errorText != null
                          ? AppColors.danger
                          : accepted
                          ? AppColors.brand
                          : AppColors.borderSoft,
                    ),
                    boxShadow: accepted
                        ? [
                            BoxShadow(
                              color: AppColors.brand.withValues(alpha: 0.14),
                              blurRadius: 10,
                              offset: const Offset(0, 5),
                            ),
                          ]
                        : null,
                  ),
                  child: accepted
                      ? const Icon(Icons.check, color: Colors.white, size: 15)
                      : null,
                ),
              ),
            ),
            const SizedBox(width: 11),
            Expanded(
              child: Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: onToggle,
                    child: const Text('我已阅读并同意 ', style: textStyle),
                  ),
                  _AgreementLink(label: '用户协议', onTap: onUserAgreementTap),
                  const Text(' 和 ', style: textStyle),
                  _AgreementLink(label: '隐私政策', onTap: onPrivacyPolicyTap),
                ],
              ),
            ),
          ],
        ),
        AnimatedSwitcher(
          duration: AppMotion.duration(context, 180),
          child: errorText == null
              ? const SizedBox.shrink()
              : Padding(
                  key: ValueKey(errorText),
                  padding: const EdgeInsets.only(left: 35, top: 6),
                  child: Text(
                    errorText!,
                    style: const TextStyle(
                      color: AppColors.danger,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      height: 1.3,
                      letterSpacing: 0,
                    ),
                  ),
                ),
        ),
      ],
    );
  }
}

class _AgreementLink extends StatelessWidget {
  const _AgreementLink({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onTap,
      style: TextButton.styleFrom(
        foregroundColor: AppColors.ink,
        minimumSize: Size.zero,
        padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 1),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        visualDensity: VisualDensity.compact,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadii.card),
        ),
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: AppColors.ink,
          fontFamily: AppTypography.systemFont,
          fontSize: 12,
          fontWeight: FontWeight.w800,
          height: 1.55,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _StatusPanel extends StatelessWidget {
  const _StatusPanel({required this.success, required this.message});

  final bool success;
  final String? message;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: AppMotion.duration(context, 220),
      child: message == null
          ? const SizedBox.shrink()
          : DecoratedBox(
              key: ValueKey('$success-$message'),
              decoration: BoxDecoration(
                color: success
                    ? const Color(0xFF2F8F68).withValues(alpha: 0.1)
                    : AppColors.brand.withValues(alpha: 0.09),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: success
                      ? const Color(0xFF2F8F68).withValues(alpha: 0.18)
                      : AppColors.brand.withValues(alpha: 0.14),
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 13,
                  vertical: 12,
                ),
                child: Row(
                  children: [
                    Icon(
                      success
                          ? Icons.check_circle_outline
                          : Icons.mark_email_read_outlined,
                      color: success
                          ? const Color(0xFF2F8F68)
                          : AppColors.brand,
                      size: 18,
                    ),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Text(
                        message!,
                        style: TextStyle(
                          color: success
                              ? const Color(0xFF2F6F55)
                              : AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          height: 1.45,
                          letterSpacing: 0,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}

class _PendingJoinSheet extends StatefulWidget {
  const _PendingJoinSheet({
    required this.joins,
    required this.onAccept,
    required this.onDecline,
  });

  final List<PendingFamilyJoin> joins;
  final Future<void> Function(PendingFamilyJoin join) onAccept;
  final Future<void> Function(PendingFamilyJoin join) onDecline;

  @override
  State<_PendingJoinSheet> createState() => _PendingJoinSheetState();
}

enum _PendingJoinAction { accepted, declined, deferred }

class _PendingJoinSheetState extends State<_PendingJoinSheet> {
  var _selectedIndex = 0;
  var _loading = false;
  String? _error;

  PendingFamilyJoin get _selected => widget.joins[_selectedIndex];

  Future<void> _run(
    Future<void> Function(PendingFamilyJoin join) action,
    _PendingJoinAction result,
  ) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await action(_selected);
      if (!mounted) return;
      Navigator.of(context).pop(result);
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
        _error = '家庭邀请暂时无法处理，请稍后再试。';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    return AppBottomSheetBody(
      title: '家庭邀请',
      subtitle: '这个手机号收到了家庭空间邀请。确认后会加入对方家庭，管理员之后可以调整你的权限。',
      footer: Column(
        children: [
          AppPrimaryButton(
            label: '接受并加入家庭',
            loading: _loading,
            trailing: const AppButtonGlyph(icon: Icons.arrow_forward),
            onTap: _loading
                ? null
                : () => unawaited(
                    _run(widget.onAccept, _PendingJoinAction.accepted),
                  ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: AppSecondaryButton(
                  label: '稍后再决定',
                  onTap: _loading
                      ? null
                      : () => Navigator.of(
                          context,
                        ).pop(_PendingJoinAction.deferred),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: AppDangerButton(
                  label: '拒绝邀请',
                  onTap: _loading
                      ? null
                      : () => unawaited(
                          _run(widget.onDecline, _PendingJoinAction.declined),
                        ),
                ),
              ),
            ],
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _PendingJoinHero(join: selected),
          const SizedBox(height: 14),
          const _PendingJoinEffectRow(
            icon: Icons.home_work_outlined,
            title: '接受后',
            message: '你会加入这个家庭空间，并按邀请里的身份参与看护协作。',
          ),
          const SizedBox(height: 10),
          const _PendingJoinEffectRow(
            icon: Icons.schedule_outlined,
            title: '稍后再决定',
            message: '不改变邀请状态，也不会进入创建家庭流程。你会回到登录页，下次登录仍可处理。',
          ),
          const SizedBox(height: 10),
          const _PendingJoinEffectRow(
            icon: Icons.block_outlined,
            title: '拒绝邀请',
            message: '邀请会被标记为已拒绝，不会加入对方家庭；需要对方重新邀请才会再次出现。',
            danger: true,
          ),
          if (widget.joins.length > 1) ...[
            const SizedBox(height: 16),
            const Text(
              '选择要处理的邀请',
              style: TextStyle(
                color: AppColors.ink,
                fontFamily: AppTypography.systemFont,
                fontSize: 13.5,
                fontWeight: FontWeight.w900,
                height: 1.2,
                letterSpacing: 0,
              ),
            ),
            const SizedBox(height: 10),
          ],
          for (var index = 0; index < widget.joins.length; index++) ...[
            if (widget.joins.length > 1) ...[
              _PendingJoinOption(
                join: widget.joins[index],
                selected: index == _selectedIndex,
                onTap: _loading
                    ? null
                    : () => setState(() {
                        _selectedIndex = index;
                        _error = null;
                      }),
              ),
              if (index < widget.joins.length - 1) const SizedBox(height: 10),
            ],
          ],
          if (_error != null) ...[
            const SizedBox(height: 12),
            _SheetErrorText(_error!),
          ],
        ],
      ),
    );
  }
}

class _PendingJoinHero extends StatelessWidget {
  const _PendingJoinHero({required this.join});

  final PendingFamilyJoin join;

  @override
  Widget build(BuildContext context) {
    final familyName = join.familyName.isEmpty ? '家庭空间邀请' : join.familyName;
    final inviter = join.name.isEmpty ? '家庭成员' : join.name;
    final roleLabel = join.roleLabel.isEmpty ? join.role : join.roleLabel;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.brandSageWash.withValues(alpha: 0.96),
            Colors.white.withValues(alpha: 0.96),
          ],
        ),
        border: Border.all(color: AppColors.brandSage.withValues(alpha: 0.14)),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4B7568).withValues(alpha: 0.08),
            blurRadius: 18,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 15),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.82),
                    borderRadius: BorderRadius.circular(17),
                    border: Border.all(
                      color: AppColors.brandSage.withValues(alpha: 0.10),
                    ),
                  ),
                  child: const SizedBox(
                    width: 50,
                    height: 50,
                    child: Center(
                      child: Icon(
                        Icons.family_restroom_outlined,
                        color: AppColors.brandSage,
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
                        familyName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AppColors.ink,
                          fontFamily: AppTypography.systemFont,
                          fontSize: 17,
                          fontWeight: FontWeight.w900,
                          height: 1.15,
                          letterSpacing: 0,
                        ),
                      ),
                      const SizedBox(height: 7),
                      Wrap(
                        spacing: 7,
                        runSpacing: 6,
                        children: [
                          _PendingJoinBadge(
                            label: inviter,
                            tone: AppColors.ink,
                            fill: Colors.white.withValues(alpha: 0.74),
                          ),
                          _PendingJoinBadge(
                            label: roleLabel,
                            tone: AppColors.brandSage,
                            fill: AppColors.brandSage.withValues(alpha: 0.10),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              '这是一个家庭空间协作邀请。接受后，这个手机号会绑定到对方家庭。',
              style: TextStyle(
                color: AppColors.ink.withValues(alpha: 0.70),
                fontFamily: AppTypography.systemFont,
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                height: 1.42,
                letterSpacing: 0,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PendingJoinEffectRow extends StatelessWidget {
  const _PendingJoinEffectRow({
    required this.icon,
    required this.title,
    required this.message,
    this.danger = false,
  });

  final IconData icon;
  final String title;
  final String message;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final tone = danger ? AppColors.danger : AppColors.brand;
    final fill = danger ? AppColors.dangerWash : AppColors.brandWash;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surfaceSoft.withValues(alpha: 0.76),
        borderRadius: BorderRadius.circular(17),
        border: Border.all(color: AppColors.borderSoft),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(13, 12, 13, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                color: fill,
                borderRadius: BorderRadius.circular(13),
              ),
              child: SizedBox(
                width: 38,
                height: 38,
                child: Center(child: Icon(icon, color: tone, size: 18)),
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
                      fontSize: 13.5,
                      fontWeight: FontWeight.w900,
                      height: 1.2,
                      letterSpacing: 0,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Text(
                    message,
                    style: const TextStyle(
                      color: AppColors.muted,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      height: 1.42,
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

class _PendingJoinOption extends StatelessWidget {
  const _PendingJoinOption({
    required this.join,
    required this.selected,
    required this.onTap,
  });

  final PendingFamilyJoin join;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: AppMotion.duration(context, 180),
      decoration: BoxDecoration(
        color: selected
            ? AppColors.brandWash.withValues(alpha: 0.72)
            : AppColors.surfaceElevated,
        borderRadius: BorderRadius.circular(17),
        border: Border.all(
          color: selected
              ? AppColors.brand.withValues(alpha: 0.32)
              : AppColors.borderSoft,
        ),
      ),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(13, 12, 12, 12),
          child: Row(
            children: [
              Icon(
                selected ? Icons.check_circle : Icons.circle_outlined,
                color: selected ? AppColors.brand : AppColors.muted,
                size: 20,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  join.familyName.isEmpty ? '家庭空间邀请' : join.familyName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: AppColors.ink,
                    fontFamily: AppTypography.systemFont,
                    fontSize: 13.5,
                    fontWeight: FontWeight.w900,
                    height: 1.2,
                    letterSpacing: 0,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              _PendingJoinBadge(
                label: join.roleLabel.isEmpty ? join.role : join.roleLabel,
                tone: AppColors.brand,
                fill: Colors.white.withValues(alpha: 0.74),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PendingJoinBadge extends StatelessWidget {
  const _PendingJoinBadge({
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
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
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

class _SheetErrorText extends StatelessWidget {
  const _SheetErrorText(this.message);

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
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TrustNote extends StatelessWidget {
  const _TrustNote();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Text(
        '儿童音视频采集会在绑定设备后单独授权',
        textAlign: TextAlign.center,
        style: TextStyle(
          color: Color(0x85526579),
          fontFamily: AppTypography.systemFont,
          fontSize: 12,
          fontWeight: FontWeight.w700,
          height: 1.5,
          letterSpacing: 0,
        ),
      ),
    );
  }
}
