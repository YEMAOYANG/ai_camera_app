import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mira_guardian_app/src/app/router/app_route.dart';
import 'package:mira_guardian_app/src/core/storage/auth_session_store.dart';
import 'package:mira_guardian_app/src/core/storage/onboarding_store.dart';
import 'package:mira_guardian_app/src/features/setup/application/setup_repository.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_background.dart';
import 'package:mira_guardian_app/src/shared/widgets/mira_state_view.dart';

class StartupGate extends ConsumerStatefulWidget {
  const StartupGate({super.key});

  @override
  ConsumerState<StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends ConsumerState<StartupGate> {
  String? _errorText;
  var _checking = true;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_resolve);
  }

  Future<void> _resolve() async {
    setState(() {
      _checking = true;
      _errorText = null;
    });

    final onboardingStore = ref.read(onboardingStoreProvider);
    if (!onboardingStore.hasSeenOnboarding) {
      if (mounted) context.go(welcomePath);
      return;
    }

    final sessionStore = ref.read(authSessionStoreProvider);
    if (!sessionStore.hasUsableSession) {
      if (mounted) context.go(loginPath);
      return;
    }

    try {
      final setupStatus = await ref.read(setupRepositoryProvider).status();
      if (!mounted) return;
      context.go(setupStatus.routePath);
    } on SetupException catch (error) {
      if (!mounted) return;
      setState(() {
        _checking = false;
        _errorText = error.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return MiraBackgroundScaffold(
      child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: _checking
                ? const MiraLoadingState(
                    title: '正在确认家庭信息',
                    message: '正在同步登录状态和首次设置进度。',
                  )
                : MiraStateView(
                    variant: MiraStateVariant.serviceUnavailable,
                    title: '暂时连不上服务',
                    message: _serviceUnavailableMessage(_errorText),
                    primaryActionLabel: '重新连接',
                    onPrimaryAction: _resolve,
                  ),
          ),
        ),
      ),
    );
  }

  String _serviceUnavailableMessage(String? errorText) {
    if (errorText == null || errorText.isEmpty) {
      return '可能是网络不稳定，或者服务正在重启。你可以稍后再试。';
    }
    return '我们没有拿到最新数据。可能是网络不稳定，或者服务正在重启。你可以稍后再试。';
  }
}
