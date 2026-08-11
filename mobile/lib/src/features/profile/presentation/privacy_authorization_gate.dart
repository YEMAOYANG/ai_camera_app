import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:warm_sight/src/app/router/app_route.dart';
import 'package:warm_sight/src/core/theme/app_tokens.dart';
import 'package:warm_sight/src/features/profile/application/profile_repository.dart';
import 'package:warm_sight/src/features/profile/domain/profile_models.dart';
import 'package:warm_sight/src/shared/widgets/app_bottom_sheet.dart';

typedef PrivacySecondaryOverlayBuilder = Widget Function(Widget child);

/// Resolves the family-level child-image decision before other automatic
/// sheets are allowed to present inside the authenticated application shell.
class PrivacyAuthorizationGate extends ConsumerStatefulWidget {
  const PrivacyAuthorizationGate({
    required this.child,
    required this.secondaryOverlayBuilder,
    super.key,
  });

  final Widget child;
  final PrivacySecondaryOverlayBuilder secondaryOverlayBuilder;

  @override
  ConsumerState<PrivacyAuthorizationGate> createState() =>
      _PrivacyAuthorizationGateState();
}

class _PrivacyAuthorizationGateState
    extends ConsumerState<PrivacyAuthorizationGate> {
  bool _resolvedThisSession = false;
  bool _pendingDecision = false;
  bool _presentationLoopActive = false;
  bool _presenting = false;

  @override
  Widget build(BuildContext context) {
    final summaryState = ref.watch(profileSummaryProvider);
    final privacyState = ref.watch(profileSettingProvider('privacy'));
    final summary = summaryState.asData?.value;
    final privacy = privacyState.asData?.value;

    final needsDecision =
        !_resolvedThisSession &&
        summary != null &&
        privacy != null &&
        summary.deviceCount > 0 &&
        summary.can('manage_privacy') &&
        !privacy.isConfigured;
    _pendingDecision = needsDecision;
    if (needsDecision) {
      _queuePresentation();
    }

    final canPresentSecondaryOverlays =
        _resolvedThisSession ||
        summaryState.hasError ||
        privacyState.hasError ||
        (summary != null &&
            (summary.deviceCount == 0 ||
                !summary.can('manage_privacy') ||
                (privacy != null && privacy.isConfigured)));

    return canPresentSecondaryOverlays
        ? widget.secondaryOverlayBuilder(widget.child)
        : widget.child;
  }

  void _queuePresentation() {
    if (_presentationLoopActive || _presenting) return;
    _presentationLoopActive = true;
    unawaited(_waitForPresentationSlot());
  }

  Future<void> _waitForPresentationSlot() async {
    try {
      while (mounted && _pendingDecision && !_resolvedThisSession) {
        await Future<void>.delayed(const Duration(milliseconds: 160));
        if (!mounted || !_pendingDecision || _resolvedThisSession) return;
        final route = ModalRoute.of(context);
        if (route != null && !route.isCurrent) continue;
        await _presentAuthorization();
        return;
      }
    } finally {
      _presentationLoopActive = false;
    }
  }

  Future<void> _presentAuthorization() async {
    if (!mounted || _presenting || !_pendingDecision) return;
    _presenting = true;
    try {
      await showPrivacyAuthorizationSheet(context, onDecision: _saveDecision);
      if (!mounted) return;
      setState(() {
        // Closing the sheet only suppresses it for this running session.
        // Without a saved backend decision it will be offered next launch.
        _resolvedThisSession = true;
        _pendingDecision = false;
      });
    } finally {
      _presenting = false;
    }
  }

  Future<void> _saveDecision(bool enabled) async {
    final cached = ref.read(profileSettingProvider('privacy')).asData?.value;
    final ProfileSetting setting;
    if (cached != null) {
      setting = cached;
    } else {
      setting = await ref.read(profileSettingProvider('privacy').future);
    }
    final value = Map<String, dynamic>.from(setting.value)
      ..['cameraCollectionAuthorized'] = enabled
      ..['childPrivacyAuthorized'] = enabled;
    await ref.read(profileRepositoryProvider).updateSetting('privacy', value);
    ref.invalidate(profileSettingProvider('privacy'));
  }
}

Future<bool?> showPrivacyAuthorizationSheet(
  BuildContext context, {
  required Future<void> Function(bool enabled) onDecision,
}) {
  return showAppBottomSheet<bool>(
    context: context,
    maxHeightFactor: 0.58,
    child: PrivacyAuthorizationSheet(onDecision: onDecision),
  );
}

class PrivacyAuthorizationSheet extends StatefulWidget {
  const PrivacyAuthorizationSheet({required this.onDecision, super.key});

  final Future<void> Function(bool enabled) onDecision;

  @override
  State<PrivacyAuthorizationSheet> createState() =>
      _PrivacyAuthorizationSheetState();
}

class _PrivacyAuthorizationSheetState extends State<PrivacyAuthorizationSheet> {
  bool _saving = false;
  String? _errorMessage;

  @override
  Widget build(BuildContext context) {
    return AppBottomSheetBody(
      title: '开启画面看护',
      subtitle: '用于识别孩子当前状态，并在需要时生成看护提醒。',
      footer: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AppSheetPrimaryButton(
            key: const ValueKey('privacy_authorization_enable'),
            label: _saving ? '正在保存' : '同意并开启看护',
            loading: _saving,
            onTap: _saving ? null : () => _decide(true),
          ),
          const SizedBox(height: 8),
          AppSheetSecondaryButton(
            key: const ValueKey('privacy_authorization_later'),
            label: '暂不开启',
            onTap: _saving ? null : () => _decide(false),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _PrivacyPromiseRow(
            icon: Icons.center_focus_strong_outlined,
            title: '只分析必要画面',
            detail: '仅在看护规则需要时识别状态，不保存全天连续录像。',
          ),
          const SizedBox(height: 14),
          const _PrivacyPromiseRow(
            icon: Icons.photo_outlined,
            title: '默认只保留必要结果',
            detail: '只保存必要的事件截图、提醒结果和家长确认记录。',
          ),
          const SizedBox(height: 14),
          const _PrivacyPromiseRow(
            icon: Icons.tune_outlined,
            title: '之后可以随时关闭',
            detail: '在「我的 · 隐私与数据」中可重新调整授权和记录策略。',
          ),
          if (_errorMessage != null) ...[
            const SizedBox(height: 14),
            Text(
              _errorMessage!,
              key: const ValueKey('privacy_authorization_error'),
              style: const TextStyle(
                color: AppColors.danger,
                fontFamily: AppTypography.systemFont,
                fontSize: 13,
                fontWeight: FontWeight.w700,
                height: 1.45,
              ),
            ),
          ],
          const SizedBox(height: 4),
          Center(
            child: TextButton(
              onPressed: _saving
                  ? null
                  : () => context.push(profileChildPrivacyPath),
              child: const Text('查看儿童隐私授权说明'),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _decide(bool enabled) async {
    if (_saving) return;
    setState(() {
      _saving = true;
      _errorMessage = null;
    });
    try {
      await widget.onDecision(enabled);
      if (mounted) Navigator.of(context).pop(enabled);
    } on ProfileException catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _errorMessage = error.message;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _errorMessage = '设置暂时没有保存，请检查网络后重试。';
      });
    }
  }
}

class _PrivacyPromiseRow extends StatelessWidget {
  const _PrivacyPromiseRow({
    required this.icon,
    required this.title,
    required this.detail,
  });

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.brandWash,
            borderRadius: BorderRadius.circular(AppRadii.control),
          ),
          child: SizedBox(
            width: 42,
            height: 42,
            child: Icon(icon, color: AppColors.brandDeep, size: 21),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: AppColors.ink,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 14.5,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                detail,
                style: const TextStyle(
                  color: AppColors.muted,
                  fontFamily: AppTypography.systemFont,
                  fontSize: 12.5,
                  fontWeight: FontWeight.w600,
                  height: 1.45,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
