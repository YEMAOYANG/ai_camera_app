import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/app/router/app_route_observer.dart';
import 'package:warm_sight/src/core/config/app_environment.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_availability.dart';
import 'package:warm_sight/src/features/learning/domain/learning_availability_models.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/features/student_access/application/student_access_repository.dart';
import 'package:warm_sight/src/features/student_access/application/student_qr_scanner_lifecycle.dart';
import 'package:warm_sight/src/features/student_access/domain/student_access_models.dart';
import 'package:warm_sight/src/shared/domain/child_grade.dart';
import 'package:warm_sight/src/shared/widgets/app_button.dart';
import 'package:warm_sight/src/shared/widgets/app_screen.dart';
import 'package:warm_sight/src/shared/widgets/app_state_view.dart';
import 'package:warm_sight/src/shared/widgets/app_surface.dart';
import 'package:warm_sight/src/shared/widgets/app_text_field.dart';

typedef StudentQrScannerBuilder =
    Widget Function(BuildContext context, ValueChanged<String> onDetected);

enum _QrFlowPhase { scanning, loading, confirmation, failure, success }

enum _QrFailureKind { invalidCode, expired, requestFailed }

class StudentAccessQrPage extends ConsumerStatefulWidget {
  const StudentAccessQrPage({this.scannerBuilder, super.key});

  final StudentQrScannerBuilder? scannerBuilder;

  @override
  ConsumerState<StudentAccessQrPage> createState() =>
      _StudentAccessQrPageState();
}

class _StudentAccessQrPageState extends ConsumerState<StudentAccessQrPage> {
  final _pinController = TextEditingController();
  final _confirmPinController = TextEditingController();
  final _scannerControl = _StudentQrScannerControl();
  _QrFlowPhase _phase = _QrFlowPhase.scanning;
  _QrFailureKind _failureKind = _QrFailureKind.invalidCode;
  StudentQrChallenge? _challenge;
  StudentQrApproval? _approval;
  Timer? _approvalTimer;
  String? _requestError;
  var _scannerGeneration = 0;
  var _operationGeneration = 0;
  var _submitting = false;

  @override
  void initState() {
    super.initState();
    _pinController.addListener(_handlePinChanged);
    _confirmPinController.addListener(_handlePinChanged);
  }

  @override
  void dispose() {
    _operationGeneration++;
    _approvalTimer?.cancel();
    _pinController
      ..removeListener(_handlePinChanged)
      ..dispose();
    _confirmPinController
      ..removeListener(_handlePinChanged)
      ..dispose();
    super.dispose();
  }

  void _handlePinChanged() {
    if (!mounted) return;
    setState(() => _requestError = null);
  }

  @override
  Widget build(BuildContext context) {
    final profile = ref.watch(profileSummaryProvider);
    return profile.when(
      skipLoadingOnRefresh: true,
      data: (summary) {
        final child = summary.child;
        if (!summary.can('manage_child_profile')) {
          return _gatePage(
            title: '需要家庭管理员授权',
            message: '当前账号没有管理孩子资料的权限，请让家庭管理员完成扫码登录。',
          );
        }
        if (child == null) {
          return _gatePage(title: '还没有孩子资料', message: '请先完成孩子资料，再为学生网页授权登录。');
        }
        final grade =
            ChildGradeOption.fromCode(child.gradeCode) ??
            ChildGradeOption.fromLegacy(
              educationStage: child.educationStage,
              grade: child.grade,
            );
        if (grade?.isPrimary != true) {
          return _gatePage(
            title: '当前年级暂不支持扫码登录',
            message: '学生学习空间仅面向已开放年级，请先在孩子资料中确认。',
          );
        }
        return _buildForAvailability(child);
      },
      loading: () => _statePage(
        variant: AppStateVariant.loading,
        title: '正在确认家庭权限',
        message: '马上就好。',
      ),
      error: (_, _) => _statePage(
        variant: AppStateVariant.serviceUnavailable,
        title: '家庭资料暂时无法同步',
        message: '请检查网络后重试。',
        primaryLabel: '重新加载',
        onPrimary: () => ref.invalidate(profileSummaryProvider),
      ),
    );
  }

  Widget _buildForAvailability(ChildProfile child) {
    final provider = studentAccessAvailabilityProvider(
      studentAccessScope(child),
    );
    final availability = ref.watch(provider);
    return availability.when(
      skipLoadingOnRefresh: false,
      skipLoadingOnReload: false,
      data: (value) {
        if (!_canAccessStudentWorkspace(child, value)) {
          return _statePage(
            variant: AppStateVariant.noData,
            title: '当前暂不能登录学习空间',
            message: '请确认孩子已选择开放年级，并完成年级设置。',
            primaryLabel: '返回首页',
            onPrimary: _close,
          );
        }
        return _buildFlow(child);
      },
      loading: () => _statePage(
        variant: AppStateVariant.loading,
        title: '正在确认学习空间权限',
        message: '确认后即可扫码登录。',
      ),
      error: (_, _) => _statePage(
        variant: AppStateVariant.serviceUnavailable,
        title: '学习空间权限暂时无法同步',
        message: '请检查网络后重试；状态确认前不会启用扫描器。',
        primaryLabel: '重新加载',
        onPrimary: () => ref.invalidate(provider),
      ),
    );
  }

  Widget _buildFlow(ChildProfile child) {
    return switch (_phase) {
      _QrFlowPhase.scanning => _scannerPage(child),
      _QrFlowPhase.loading => _statePage(
        variant: AppStateVariant.loading,
        title: '正在读取登录请求',
        message: '正在确认浏览器和请求有效期。',
      ),
      _QrFlowPhase.confirmation => _confirmationPage(child),
      _QrFlowPhase.failure => _failurePage(),
      _QrFlowPhase.success => _successPage(child),
    };
  }

  Widget _scannerPage(ChildProfile child) {
    final scannerBuilder =
        widget.scannerBuilder ??
        (context, onDetected) => _MobileStudentQrScanner(
          key: ValueKey(_scannerGeneration),
          onDetected: onDetected,
          control: _scannerControl,
        );
    return AppScreen(
      key: const ValueKey('studentQrScannerPage'),
      title: '扫码登录学习网页',
      subtitle: '只识别暖瞳学生网页二维码',
      reserveBottomNavigation: false,
      backLabel: '返回首页',
      onBack: _close,
      children: [
        _ScannerIntro(onOpenPairingCode: _openPairingCode),
        const SizedBox(height: 14),
        _ScannerFrame(
          child: scannerBuilder(
            context,
            (rawValue) => _handleScannedValue(rawValue, child),
          ),
        ),
        const SizedBox(height: 14),
        const _SecurityNotice(),
      ],
    );
  }

  Widget _confirmationPage(ChildProfile child) {
    final challenge = _challenge!;
    final childName = _childName(child);
    final pinReady = _pinReady(challenge);
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) unawaited(_rejectAndClose(child.id));
      },
      child: AppScreen(
        key: const ValueKey('studentQrConfirmationPage'),
        title: '确认网页登录',
        subtitle: '确认后，这台浏览器将进入 $childName 的学习空间',
        reserveBottomNavigation: false,
        avoidFooterOverlap: true,
        backLabel: '取消并重扫',
        onBack: () => unawaited(_rejectAndRestart(child.id)),
        footer: AppPrimaryButton(
          key: const ValueKey('approveStudentQrChallenge'),
          label: _submitting ? '正在确认' : '确认登录',
          loading: _submitting,
          onTap: !_submitting && pinReady ? () => _approve(child) : null,
          trailing: const AppButtonGlyph(icon: Icons.verified_user_outlined),
        ),
        children: [
          _LoginRequestPanel(challenge: challenge),
          const SizedBox(height: 14),
          _SelectedChildPanel(child: child),
          const SizedBox(height: 14),
          _QrPinPanel(
            requiresPin: challenge.requiresPin,
            pinConfigured: challenge.pinConfigured,
            pinController: _pinController,
            confirmPinController: _confirmPinController,
            confirmError: _confirmPinError(challenge),
            requestError: _requestError,
          ),
          const SizedBox(height: 14),
          const _SecurityNotice(),
        ],
      ),
    );
  }

  Widget _failurePage() {
    final title = switch (_failureKind) {
      _QrFailureKind.invalidCode => '这不是有效的学习网页二维码',
      _QrFailureKind.expired => '登录请求已过期',
      _QrFailureKind.requestFailed => '暂时无法读取登录请求',
    };
    final message = switch (_failureKind) {
      _QrFailureKind.invalidCode => '请在暖瞳学生网页的登录页面重新展示二维码，不要扫描聊天或浏览器中的其他链接。',
      _QrFailureKind.expired => '请让孩子在学习网页刷新二维码，然后用家长 App 重新扫描。',
      _QrFailureKind.requestFailed => _requestError ?? '请检查网络后再试。',
    };
    return _statePage(
      key: const ValueKey('studentQrFailurePage'),
      variant: _failureKind == _QrFailureKind.requestFailed
          ? AppStateVariant.networkUnavailable
          : AppStateVariant.noData,
      title: title,
      message: message,
      primaryLabel: '重新扫码',
      onPrimary: _restartScanning,
      secondaryLabel: '改用配对码',
      onSecondary: _openPairingCode,
    );
  }

  Widget _successPage(ChildProfile child) {
    final approval = _approval!;
    final remaining = approval.remainingAt(DateTime.now());
    final seconds = remaining.inSeconds;
    final waitingMessage = seconds > 0
        ? '已授权给刚才的浏览器，请保持网页打开；网页需在 $seconds 秒内完成登录。'
        : '授权窗口已结束。如果网页还没有进入学习空间，请重新扫码。';
    return _statePage(
      key: const ValueKey('studentQrSuccessPage'),
      variant: AppStateVariant.saved,
      title: '已授权，等待网页完成登录',
      message: '$waitingMessage\n${_childName(child)} 的学习空间不会共享家长账号或摄像头权限。',
      primaryLabel: '完成',
      onPrimary: _close,
      secondaryLabel: '继续扫码另一台设备',
      onSecondary: _restartScanning,
    );
  }

  Widget _gatePage({required String title, required String message}) {
    return _statePage(
      variant: AppStateVariant.permission,
      title: title,
      message: message,
      primaryLabel: '返回首页',
      onPrimary: _close,
    );
  }

  Widget _statePage({
    Key? key,
    required AppStateVariant variant,
    required String title,
    required String message,
    String? primaryLabel,
    VoidCallback? onPrimary,
    String? secondaryLabel,
    VoidCallback? onSecondary,
  }) {
    return AppScreen(
      key: key,
      title: '扫码登录学习网页',
      reserveBottomNavigation: false,
      backLabel: '返回首页',
      onBack: _close,
      children: [
        AppStateView(
          variant: variant,
          title: title,
          message: message,
          primaryActionLabel: primaryLabel,
          onPrimaryAction: onPrimary,
          secondaryActionLabel: secondaryLabel,
          onSecondaryAction: onSecondary,
          compact: true,
        ),
      ],
    );
  }

  Future<void> _handleScannedValue(String rawValue, ChildProfile child) async {
    if (_phase != _QrFlowPhase.scanning) return;
    final availability = ref.read(
      studentAccessAvailabilityProvider(studentAccessScope(child)),
    );
    if (availability.isLoading ||
        availability.hasError ||
        !_canAccessStudentWorkspace(child, availability.asData!.value)) {
      return;
    }
    final link = StudentQrChallengeLink.tryParse(
      rawValue: rawValue,
      studentWebBaseUrl: ref.read(appEnvironmentProvider).studentWebBaseUrl,
    );
    if (link == null) {
      setState(() {
        _failureKind = _QrFailureKind.invalidCode;
        _phase = _QrFlowPhase.failure;
      });
      return;
    }

    final generation = ++_operationGeneration;
    setState(() {
      _phase = _QrFlowPhase.loading;
      _requestError = null;
    });
    try {
      final challenge = await ref
          .read(studentAccessRepositoryProvider)
          .getQrChallenge(challengeId: link.challengeId, childId: child.id);
      if (!mounted || generation != _operationGeneration) return;
      if (challenge.id != link.challengeId ||
          !challenge.canApprove ||
          challenge.isExpiredAt(DateTime.now())) {
        setState(() {
          _failureKind = _QrFailureKind.expired;
          _phase = _QrFlowPhase.failure;
        });
        return;
      }
      _pinController.clear();
      _confirmPinController.clear();
      setState(() {
        _challenge = challenge;
        _phase = _QrFlowPhase.confirmation;
      });
    } on StudentAccessException catch (error) {
      if (!mounted || generation != _operationGeneration) return;
      final expired = {
        'student_qr_challenge_expired',
        'qr_challenge_expired',
        'challenge_expired',
        'challenge_not_found',
        'student_qr_challenge_unavailable',
        'invalid_student_qr_challenge',
        'student_qr_challenge_consumed',
      }.contains(error.code);
      setState(() {
        _failureKind = expired
            ? _QrFailureKind.expired
            : _QrFailureKind.requestFailed;
        _requestError = error.message;
        _phase = _QrFlowPhase.failure;
      });
    } catch (_) {
      if (!mounted || generation != _operationGeneration) return;
      setState(() {
        _failureKind = _QrFailureKind.requestFailed;
        _requestError = '暂时无法读取登录请求，请检查网络后重试。';
        _phase = _QrFlowPhase.failure;
      });
    }
  }

  Future<void> _approve(ChildProfile child) async {
    final challenge = _challenge;
    if (challenge == null || !_pinReady(challenge) || _submitting) return;
    final availability = ref.read(
      studentAccessAvailabilityProvider(studentAccessScope(child)),
    );
    if (availability.isLoading ||
        availability.hasError ||
        !_canAccessStudentWorkspace(child, availability.asData!.value)) {
      return;
    }
    FocusScope.of(context).unfocus();
    final generation = ++_operationGeneration;
    setState(() {
      _submitting = true;
      _requestError = null;
    });
    try {
      final approval = await ref
          .read(studentAccessRepositoryProvider)
          .approveQrChallenge(
            challengeId: challenge.id,
            childId: child.id,
            pin: _pinController.text,
          );
      if (!mounted || generation != _operationGeneration) return;
      if (approval.challengeId != challenge.id ||
          approval.status != 'approved') {
        throw const StudentAccessException('登录请求未完成，请重新扫码。');
      }
      setState(() {
        _submitting = false;
        _approval = approval;
        _phase = _QrFlowPhase.success;
      });
      _startApprovalCountdown();
    } on StudentAccessException catch (error) {
      if (!mounted || generation != _operationGeneration) return;
      final expired = {
        'student_qr_challenge_expired',
        'qr_challenge_expired',
        'challenge_expired',
        'challenge_not_found',
        'student_qr_challenge_unavailable',
        'invalid_student_qr_challenge',
        'student_qr_challenge_consumed',
      }.contains(error.code);
      if (expired) {
        setState(() {
          _submitting = false;
          _failureKind = _QrFailureKind.expired;
          _requestError = error.message;
          _phase = _QrFlowPhase.failure;
        });
      } else {
        setState(() {
          _submitting = false;
          _requestError = error.message;
        });
      }
    } catch (_) {
      if (!mounted || generation != _operationGeneration) return;
      setState(() {
        _submitting = false;
        _requestError = '暂时无法确认登录，请检查网络后重试。';
      });
    }
  }

  bool _pinReady(StudentQrChallenge challenge) {
    final pin = _pinController.text;
    if (!challenge.requiresPin) return pin.isEmpty || pin.length == 4;
    return pin.length == 4 && _confirmPinController.text == pin;
  }

  String? _confirmPinError(StudentQrChallenge challenge) {
    final pin = _pinController.text;
    if (!challenge.requiresPin) {
      if (pin.isNotEmpty && pin.length < 4) return '请输入完整的 4 位 PIN，或留空';
      return null;
    }
    final confirmation = _confirmPinController.text;
    if (confirmation.isEmpty || confirmation == pin) return null;
    if (confirmation.length >= 4) return '两次输入的 PIN 不一致';
    return null;
  }

  void _restartScanning() {
    _operationGeneration++;
    _approvalTimer?.cancel();
    _pinController.clear();
    _confirmPinController.clear();
    setState(() {
      _scannerGeneration++;
      _phase = _QrFlowPhase.scanning;
      _challenge = null;
      _approval = null;
      _requestError = null;
      _submitting = false;
    });
  }

  void _startApprovalCountdown() {
    _approvalTimer?.cancel();
    final approval = _approval;
    if (approval == null ||
        !approval.approvalExpiresAt.isAfter(DateTime.now())) {
      return;
    }
    _approvalTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || _phase != _QrFlowPhase.success) {
        timer.cancel();
        return;
      }
      setState(() {});
      if (!_approval!.approvalExpiresAt.isAfter(DateTime.now())) {
        timer.cancel();
      }
    });
  }

  Future<void> _openPairingCode() async {
    await _scannerControl.pause();
    if (!mounted) return;
    await context.push(profileStudentAccessPath);
    if (mounted && _phase == _QrFlowPhase.scanning) {
      await _scannerControl.resume();
    }
  }

  Future<void> _rejectAndRestart(String childId) async {
    await _rejectActiveChallenge(childId);
    if (mounted) _restartScanning();
  }

  Future<void> _rejectAndClose(String childId) async {
    await _rejectActiveChallenge(childId);
    if (mounted) context.go(AppRoute.home.path);
  }

  Future<void> _rejectActiveChallenge(String childId) async {
    final challenge = _challenge;
    if (challenge == null) return;
    final generation = ++_operationGeneration;
    try {
      await ref
          .read(studentAccessRepositoryProvider)
          .rejectQrChallenge(challengeId: challenge.id, childId: childId);
    } on StudentAccessException {
      // Cancellation is fail-closed in the UI; an expired/unavailable request
      // cannot be approved locally and the web challenge expires server-side.
    }
    if (!mounted || generation != _operationGeneration) return;
  }

  void _close() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoute.home.path);
    }
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

class _MobileStudentQrScanner extends StatefulWidget {
  const _MobileStudentQrScanner({
    required this.onDetected,
    required this.control,
    super.key,
  });

  final ValueChanged<String> onDetected;
  final _StudentQrScannerControl control;

  @override
  State<_MobileStudentQrScanner> createState() =>
      _MobileStudentQrScannerState();
}

class _MobileStudentQrScannerState extends State<_MobileStudentQrScanner>
    with WidgetsBindingObserver, RouteAware {
  late final MobileScannerController _controller;
  late final StudentQrScannerLifecycle _lifecycle;
  ModalRoute<dynamic>? _route;
  var _delivered = false;

  @override
  void initState() {
    super.initState();
    _controller = MobileScannerController(
      autoStart: false,
      formats: const [BarcodeFormat.qrCode],
      detectionSpeed: DetectionSpeed.noDuplicates,
      facing: CameraFacing.back,
    );
    final bindingState = WidgetsBinding.instance.lifecycleState;
    _lifecycle = StudentQrScannerLifecycle(
      startCamera: _controller.start,
      stopCamera: _controller.stop,
      disposeCamera: _controller.dispose,
    );
    _ignore(
      _lifecycle.setAppActive(
        bindingState == null || bindingState == AppLifecycleState.resumed,
      ),
    );
    WidgetsBinding.instance.addObserver(this);
    widget.control.attach(
      owner: this,
      pause: _lifecycle.pause,
      resume: _lifecycle.resume,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final nextRoute = ModalRoute.of(context);
    if (!identical(nextRoute, _route)) {
      if (_route != null) appRouteObserver.unsubscribe(this);
      _route = nextRoute;
      if (nextRoute != null) appRouteObserver.subscribe(this, nextRoute);
    }
    _ignore(_lifecycle.setRouteCurrent(nextRoute?.isCurrent ?? true));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _ignore(_lifecycle.setAppActive(state == AppLifecycleState.resumed));
  }

  @override
  void didPush() => _ignore(_lifecycle.setRouteCurrent(true));

  @override
  void didPopNext() => _ignore(_lifecycle.setRouteCurrent(true));

  @override
  void didPushNext() => _ignore(_lifecycle.setRouteCurrent(false));

  @override
  void didPop() => _ignore(_lifecycle.setRouteCurrent(false));

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    appRouteObserver.unsubscribe(this);
    widget.control.detach(this);
    _ignore(_lifecycle.close());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MobileScanner(
      controller: _controller,
      fit: BoxFit.cover,
      onDetect: _handleCapture,
      placeholderBuilder: (_) => const ColoredBox(
        color: Color(0xFF152033),
        child: Center(
          child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
        ),
      ),
      errorBuilder: (context, error) => _ScannerCameraError(
        permissionDenied:
            error.errorCode == MobileScannerErrorCode.permissionDenied,
        onRetry: _retry,
      ),
    );
  }

  void _handleCapture(BarcodeCapture capture) {
    if (_delivered) return;
    for (final barcode in capture.barcodes) {
      final rawValue = barcode.rawValue?.trim() ?? '';
      if (rawValue.isEmpty) continue;
      _delivered = true;
      unawaited(_deliver(rawValue));
      return;
    }
  }

  Future<void> _deliver(String rawValue) async {
    try {
      await _lifecycle.markDelivered();
    } on MobileScannerException {
      // Delivery still proceeds; no camera work is started after this point.
    }
    if (mounted) widget.onDetected(rawValue);
  }

  Future<void> _retry() async {
    _delivered = false;
    try {
      await _lifecycle.retry();
    } on MobileScannerException {
      // The scanner's errorBuilder keeps the permission or camera state visible.
    }
  }

  void _ignore(Future<void> operation) {
    unawaited(operation.catchError((Object _, StackTrace _) {}));
  }
}

class _StudentQrScannerControl {
  Object? _owner;
  Future<void> Function()? _pause;
  Future<void> Function()? _resume;

  void attach({
    required Object owner,
    required Future<void> Function() pause,
    required Future<void> Function() resume,
  }) {
    _owner = owner;
    _pause = pause;
    _resume = resume;
  }

  void detach(Object owner) {
    if (!identical(_owner, owner)) return;
    _owner = null;
    _pause = null;
    _resume = null;
  }

  Future<void> pause() async => _pause?.call();

  Future<void> resume() async => _resume?.call();
}

class _ScannerFrame extends StatelessWidget {
  const _ScannerFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final height = (constraints.maxWidth * 1.02).clamp(300.0, 390.0);
        return ClipRRect(
          borderRadius: BorderRadius.circular(AppRadii.cardLarge),
          child: SizedBox(
            key: const ValueKey('studentQrScannerViewport'),
            height: height,
            width: double.infinity,
            child: Stack(
              fit: StackFit.expand,
              children: [
                ColoredBox(color: const Color(0xFF152033), child: child),
                const IgnorePointer(child: _QrScanOverlay()),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _QrScanOverlay extends StatelessWidget {
  const _QrScanOverlay();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: FractionallySizedBox(
        widthFactor: 0.72,
        heightFactor: 0.66,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: Colors.white, width: 2),
            boxShadow: [
              BoxShadow(
                color: AppColors.brand.withValues(alpha: 0.48),
                blurRadius: 18,
              ),
            ],
          ),
          child: const Align(
            alignment: Alignment.bottomCenter,
            child: Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Color(0xAA111827),
                  borderRadius: BorderRadius.all(Radius.circular(999)),
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: 13, vertical: 7),
                  child: Text(
                    '将二维码放入框内',
                    style: TextStyle(
                      color: Colors.white,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ScannerCameraError extends StatelessWidget {
  const _ScannerCameraError({
    required this.permissionDenied,
    required this.onRetry,
  });

  final bool permissionDenied;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: const Color(0xFF152033),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                permissionDenied
                    ? Icons.no_photography_outlined
                    : Icons.camera_alt_outlined,
                color: Colors.white,
                size: 38,
              ),
              const SizedBox(height: 12),
              Text(
                permissionDenied ? '需要相机权限才能扫码' : '相机暂时不可用',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 7),
              Text(
                permissionDenied ? '请在系统设置中允许暖瞳使用相机。' : '请确认没有其他应用占用相机后重试。',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.72),
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  height: 1.45,
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: 210,
                child: FilledButton(
                  onPressed: permissionDenied
                      ? () => openAppSettings()
                      : onRetry,
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: AppColors.ink,
                    minimumSize: const Size.fromHeight(44),
                  ),
                  child: Text(permissionDenied ? '打开系统设置' : '重新尝试'),
                ),
              ),
              if (permissionDenied) ...[
                const SizedBox(height: 8),
                TextButton(
                  onPressed: onRetry,
                  child: const Text(
                    '我已允许，重新尝试',
                    style: TextStyle(color: Colors.white),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ScannerIntro extends StatelessWidget {
  const _ScannerIntro({required this.onOpenPairingCode});

  final VoidCallback onOpenPairingCode;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.brandWash.withValues(alpha: 0.72),
      borderColor: AppColors.brand.withValues(alpha: 0.10),
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.all(15),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SoftIcon(icon: Icons.qr_code_scanner),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('扫描孩子网页上的二维码', style: _panelTitleStyle),
                const SizedBox(height: 5),
                const Text('扫码后会先显示浏览器信息，只有你确认后才会登录。', style: _panelBodyStyle),
                const SizedBox(height: 7),
                GestureDetector(
                  onTap: onOpenPairingCode,
                  child: const Text(
                    '无法扫码？改用配对码',
                    style: TextStyle(
                      color: AppColors.brandDeep,
                      fontFamily: AppTypography.systemFont,
                      fontSize: 13,
                      fontWeight: FontWeight.w800,
                    ),
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

class _LoginRequestPanel extends StatelessWidget {
  const _LoginRequestPanel({required this.challenge});

  final StudentQrChallenge challenge;

  @override
  Widget build(BuildContext context) {
    final requestedAt = DateFormat(
      'M月d日 HH:mm',
    ).format(challenge.requestedAt.toLocal());
    return AppSurface(
      key: const ValueKey('studentQrChallengePreview'),
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.fromLTRB(16, 17, 16, 15),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              _SoftIcon(icon: Icons.computer_outlined),
              SizedBox(width: 12),
              Expanded(child: Text('网页登录请求', style: _panelTitleStyle)),
            ],
          ),
          const SizedBox(height: 15),
          _DisplayCodePanel(code: challenge.displayCode),
          const SizedBox(height: 15),
          _DetailRow(
            icon: Icons.language_outlined,
            label: '浏览器',
            value: challenge.clientDevice.browserLabel,
          ),
          const SizedBox(height: 11),
          _DetailRow(
            icon: Icons.devices_outlined,
            label: '系统',
            value: challenge.clientDevice.systemLabel,
          ),
          const SizedBox(height: 11),
          _DetailRow(
            icon: Icons.schedule_outlined,
            label: '请求时间',
            value: requestedAt,
          ),
        ],
      ),
    );
  }
}

class _DisplayCodePanel extends StatelessWidget {
  const _DisplayCodePanel({required this.code});

  final String code;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brandWash.withValues(alpha: 0.78),
        borderRadius: BorderRadius.circular(AppRadii.control),
        border: Border.all(color: AppColors.brand.withValues(alpha: 0.16)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 13, 14, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '请与网页上的 4 位数字核对',
              textAlign: TextAlign.center,
              style: _panelBodyStyle,
            ),
            const SizedBox(height: 7),
            Text(
              code.split('').join('  '),
              key: const ValueKey('studentQrDisplayCode'),
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.brandDeep,
                fontFamily: AppTypography.systemFont,
                fontSize: 28,
                fontWeight: FontWeight.w900,
                letterSpacing: 3,
              ),
            ),
            const SizedBox(height: 5),
            const Text(
              '数字不一致时不要确认登录',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.warning,
                fontFamily: AppTypography.systemFont,
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectedChildPanel extends StatelessWidget {
  const _SelectedChildPanel({required this.child});

  final ChildProfile child;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      key: const ValueKey('studentQrSelectedChild'),
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.all(15),
      child: Row(
        children: [
          const _SoftIcon(icon: Icons.school_outlined),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('登录到孩子的学习空间', style: _panelBodyStyle),
                const SizedBox(height: 4),
                Text(
                  '${_childName(child)} · ${child.grade}',
                  style: _panelTitleStyle,
                ),
              ],
            ),
          ),
          const Icon(Icons.check_circle, color: AppColors.success, size: 23),
        ],
      ),
    );
  }
}

class _QrPinPanel extends StatelessWidget {
  const _QrPinPanel({
    required this.requiresPin,
    required this.pinConfigured,
    required this.pinController,
    required this.confirmPinController,
    required this.confirmError,
    required this.requestError,
  });

  final bool requiresPin;
  final bool pinConfigured;
  final TextEditingController pinController;
  final TextEditingController confirmPinController;
  final String? confirmError;
  final String? requestError;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      radius: AppRadii.cardLarge,
      padding: const EdgeInsets.fromLTRB(16, 17, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            requiresPin ? '首次设置学习 PIN' : '学习 PIN（可选）',
            style: _panelTitleStyle,
          ),
          const SizedBox(height: 5),
          Text(
            requiresPin
                ? '设置 4 位数字，孩子以后可用它解锁学习空间。'
                : pinConfigured
                ? '留空即可继续使用现有 PIN；本次登录不会修改它。'
                : '可设置新的 4 位学习 PIN，也可以留空继续。',
            style: _panelBodyStyle,
          ),
          const SizedBox(height: 14),
          AppTextField(
            key: const ValueKey('studentQrPinField'),
            label: requiresPin ? '学习 PIN' : '新的学习 PIN（可留空）',
            icon: Icons.lock_outline,
            controller: pinController,
            hintText: '4 位数字',
            keyboardType: TextInputType.number,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(4),
            ],
            obscureText: true,
            enableSuggestions: false,
            autocorrect: false,
            errorText: requiresPin ? null : confirmError,
          ),
          if (requiresPin) ...[
            const SizedBox(height: 13),
            AppTextField(
              key: const ValueKey('studentQrPinConfirmField'),
              label: '再次输入 PIN',
              icon: Icons.verified_user_outlined,
              controller: confirmPinController,
              hintText: '再次输入 4 位数字',
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
          ],
          if (requestError != null) ...[
            const SizedBox(height: 12),
            _InlineError(message: requestError!),
          ],
        ],
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, color: AppColors.subtle, size: 18),
        const SizedBox(width: 9),
        SizedBox(width: 64, child: Text(label, style: _panelBodyStyle)),
        Expanded(
          child: Text(
            value,
            textAlign: TextAlign.right,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: AppColors.ink,
              fontFamily: AppTypography.systemFont,
              fontSize: 13.5,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );
  }
}

class _SecurityNotice extends StatelessWidget {
  const _SecurityNotice();

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      color: AppColors.successWash.withValues(alpha: 0.72),
      borderColor: AppColors.success.withValues(alpha: 0.10),
      radius: AppRadii.cardMedium,
      padding: const EdgeInsets.all(13),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.shield_outlined, color: AppColors.success, size: 19),
          SizedBox(width: 9),
          Expanded(
            child: Text(
              '二维码只用于授权学生学习空间，不会把家长账号、相册或摄像头权限交给网页。',
              style: TextStyle(
                color: AppColors.muted,
                fontFamily: AppTypography.systemFont,
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
                height: 1.45,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SoftIcon extends StatelessWidget {
  const _SoftIcon({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.brandWash,
        borderRadius: BorderRadius.circular(AppRadii.control),
      ),
      child: SizedBox(
        width: 44,
        height: 44,
        child: Icon(icon, color: AppColors.brandDeep, size: 23),
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.dangerWash,
        borderRadius: BorderRadius.circular(AppRadii.control),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 18),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(
                  color: AppColors.danger,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _childName(ChildProfile child) {
  final nickname = child.nickname.trim();
  return nickname.isNotEmpty ? nickname : child.name;
}

const _panelTitleStyle = TextStyle(
  color: AppColors.ink,
  fontFamily: AppTypography.systemFont,
  fontSize: 16,
  fontWeight: FontWeight.w900,
  height: 1.25,
);

const _panelBodyStyle = TextStyle(
  color: AppColors.muted,
  fontFamily: AppTypography.systemFont,
  fontSize: 13,
  fontWeight: FontWeight.w600,
  height: 1.45,
);
